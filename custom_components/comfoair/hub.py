"""ComfoAir Modbus Hub/coordinator."""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timedelta

from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusIOException
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    BOOLEAN_REGISTERS,
    DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE,
    ENUM_REGISTERS,
    FIRMWARE_REGISTER,
    MODE_SERIAL,
    ON_OFF_STATUS,
    ALARM_BITS,
    READ_RANGES,
    STATIC_READ_RANGES,
    SENSOR_TYPES,
    alarm_data_key,
)
from .notifications import QuietHours, parse_services, send_mobile, send_persistent

_LOGGER = logging.getLogger(__name__)

MAX_READ_RETRIES = 3


class ComfoAirHub(DataUpdateCoordinator[dict]):
    """Thread safe wrapper class for pymodbus."""

    @staticmethod
    def _calc_absolute_humidity(temp_c: float, rh_percent: float) -> float | None:
        """Absolute humidity in kg/kg dry air (mixing ratio)."""
        try:
            e_s = 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))
            e = (rh_percent / 100.0) * e_s
            return round(0.622 * e / (1013.25 - e), 4)
        except (ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _calc_dewpoint(temp_c: float, rh_percent: float) -> float | None:
        """Dew point temperature in °C (Magnus formula)."""
        try:
            e = (rh_percent / 100.0) * 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))
            ln_e = math.log(e / 6.112)
            return round(243.5 * ln_e / (17.67 - ln_e), 1)
        except (ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _calc_enthalpy(temp_c: float, abs_humidity: float) -> float | None:
        """Enthalpy of moist air in kJ/kg dry air."""
        try:
            return round(1.006 * temp_c + abs_humidity * (2501 + 1.86 * temp_c), 1)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_firmware_version(raw_value: int) -> str | None:
        """Convert raw firmware register to a readable firmware version string."""
        if raw_value <= 0:
            return None

        major = raw_value // 10000
        minor = (raw_value % 10000) // 100
        patch = raw_value % 100

        if patch > 0:
            return f"{major}.{minor:02d}.{patch:02d}"
        return f"{major}.{minor:02d}"

    def __init__(
        self,
        hass,
        name: str,
        scan_interval: int,
        mode: str,
        device_id: int,
        host: str | None = None,
        port: int | None = None,
        device: str | None = None,
        baudrate: int | None = None,
        bytesize: int | None = None,
        parity: str | None = None,
        stopbits: int | None = None,
        dewpoint_delta: float = 1.0,
        condensation_source: str = "",
        condensation_max_change: float = 0.0,
        notify_connection_errors_mobile: bool = False,
        notify_connection_errors_persistent: bool = False,
        notify_recovery: bool = True,
        notify_services: str = "",
        connection_error_notification_title: str = DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE,
        connection_error_delay: int = 60,
        connection_quiet_enabled: bool = False,
        connection_quiet_start=None,
        connection_quiet_end=None,
    ) -> None:
        super().__init__(hass, _LOGGER, name=name, update_interval=timedelta(seconds=scan_interval))
        self._mode = mode
        self._unit = int(device_id)
        self._host = host
        self._port = int(port) if port is not None else None
        self._device = device
        self._baudrate = int(baudrate) if baudrate is not None else None
        self._bytesize = int(bytesize) if bytesize is not None else None
        self._parity = parity
        self._stopbits = int(stopbits) if stopbits is not None else None
        self._dewpoint_delta = float(dewpoint_delta)
        self._condensation_source = condensation_source or ""
        self._condensation_max_change = max(0.0, float(condensation_max_change))
        self._condensation_limit_raw: float | None = None
        self._limit_value: float | None = None
        self._limit_updated: float | None = None

        self._client = None
        self._lock = threading.Lock()
        self._modbus_lock = threading.Lock()
        self._consecutive_failures = 0
        self._static_data: dict = {}
        self._last_successful_read = None

        self._notify_connection_errors_mobile = notify_connection_errors_mobile
        self._notify_connection_errors_persistent = notify_connection_errors_persistent
        self._notify_recovery = notify_recovery
        self._notify_services = parse_services(notify_services)
        self._connection_error_notification_title = connection_error_notification_title
        self._connection_error_notified = False
        self._connection_lost_time = None
        self._failures_for_delay = max(1, int(connection_error_delay / scan_interval))
        _LOGGER.debug(
            "Connection error notification will be sent after %s failures (%ss / %ss)",
            self._failures_for_delay,
            connection_error_delay,
            scan_interval,
        )

        # Connection notifications share one quiet-hours window.
        self._quiet = QuietHours(
            hass,
            f"{name} connection",
            connection_quiet_enabled,
            connection_quiet_start,
            connection_quiet_end,
            self._send_connection_mobile,
        )

        storage_key = f"{name}_data_store"
        if storage_key not in hass.data:
            hass.data[storage_key] = {"realtime_data": {}}
        self.data_store = hass.data[storage_key]

        self._client = self._create_client()

    def _create_client(self):
        if self._mode == MODE_SERIAL:
            _LOGGER.debug(
                "Modbus client initialized for %s (baudrate=%s, bytesize=%s, parity=%s, stopbits=%s)",
                self._device,
                self._baudrate,
                self._bytesize,
                self._parity,
                self._stopbits,
            )
            return ModbusSerialClient(
                port=self._device,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                parity=self._parity,
                stopbits=self._stopbits,
                timeout=3,
            )
        _LOGGER.debug("Modbus client initialized for %s:%s", self._host, self._port)
        return ModbusTcpClient(host=self._host, port=self._port, timeout=3)

    def _reset_client(self) -> None:
        """Close the current Modbus client, if any, so the next read reconnects."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def start_notifications(self) -> None:
        """Start the quiet-hours release trigger for connection notifications."""
        self._quiet.start()

    def close(self) -> None:
        """Disconnect client."""
        self._quiet.stop()
        try:
            with self._lock:
                self._reset_client()
            _LOGGER.debug("Modbus client connection closed")
        except Exception as err:
            _LOGGER.exception("Error closing Modbus connection: %s", err)

    def _read_holding_registers(self, address: int, count: int):
        """Safely read holding registers with reconnect logic."""
        try:
            if self._client is None or not self._client.connected:
                _LOGGER.debug("Modbus client not connected, attempting reconnect...")
                self._reset_client()
                self._client = self._create_client()
                if not self._client.connect():
                    _LOGGER.error("Modbus reconnect failed")
                    return None

            with self._modbus_lock:
                response = self._client.read_holding_registers(
                    address=address,
                    count=count,
                    device_id=self._unit,
                )

            if response is None:
                return None

            if response.isError():
                _LOGGER.warning("Forcing reconnect due to Modbus error frame")
                self._reset_client()
                return None

            if not hasattr(response, "registers"):
                return None
            _LOGGER.debug("Successfully read %s registers from %s-%s", len(response.registers), address, address + count - 1)
            return response
        except (ConnectionException, ModbusIOException, OSError) as err:
            _LOGGER.error("Modbus communication error while reading %s-%s: %s", address, address + count - 1, err)
            self._reset_client()
            return None
        except Exception as err:
            _LOGGER.exception("Unexpected error while reading %s-%s: %s", address, address + count - 1, err)
            return None

    async def _async_update_data(self) -> dict:
        """Fetch Modbus data with fallback to previous values."""
        if self._last_successful_read is not None:
            time_since_success = (datetime.now() - self._last_successful_read).total_seconds()
            if time_since_success > 300:
                _LOGGER.warning(
                    "No successful reads for %ss (>5min), forcing reconnect",
                    int(time_since_success),
                )
                self._reset_client()

        data = {**self.data_store.get("realtime_data", {})}

        realtime_result = await self.hass.async_add_executor_job(self.read_modbus_realtime_data)
        if isinstance(realtime_result, tuple):
            realtime, failed_ranges = realtime_result
        else:
            realtime = realtime_result
            failed_ranges = []

        if realtime is None:
            data["connection_status"] = "Failed"
            await self._handle_connection_failure()
            return data

        if failed_ranges:
            data["connection_status"] = "Partial"
        else:
            data["connection_status"] = "OK"
            await self._handle_connection_restored()

        data.update(realtime)
        self.data_store["realtime_data"] = realtime
        # The alarm uses the unsmoothed limit; a real condensation risk must not
        # wait for the smoothing window to catch up.
        data["supply_condensation_alarm"] = self._condensation_alarm(self._condensation_limit_raw)
        return data

    def _rate_limited(self, raw: float | None) -> float | None:
        """Let the condensation limit move at most so many °C per hour.

        Showering raises the extract humidity sharply for a couple of hours. The
        rate limit flattens that into a small bump, while slow changes such as the
        weather still come through in full.
        """
        if raw is None:
            return None
        if not self._condensation_max_change:
            self._limit_value = raw
            return raw

        now = time.monotonic()
        if self._limit_value is None or self._limit_updated is None:
            self._limit_value = raw
            self._limit_updated = now
            return round(raw, 1)

        max_step = self._condensation_max_change * (now - self._limit_updated) / 3600
        self._limit_updated = now
        if raw > self._limit_value:
            self._limit_value = min(raw, self._limit_value + max_step)
        else:
            self._limit_value = max(raw, self._limit_value - max_step)
        return round(self._limit_value, 1)

    def _condensation_alarm(self, limit: float | None) -> bool | None:
        """Compare the linked temperature entity with the condensation limit.

        Returns None when no entity is linked or its value cannot be read, so the
        binary sensor stays unknown instead of reporting a false all-clear.
        """
        if limit is None or not self._condensation_source:
            return None

        state = self.hass.states.get(self._condensation_source)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug("Condensation source %s has no usable state", self._condensation_source)
            return None

        try:
            return float(state.state) <= limit
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Condensation source %s is not numeric: %s", self._condensation_source, state.state
            )
            return None

    async def _send_connection_mobile(self, message: str) -> None:
        """Deliver a connection message to the mobile notify services."""
        await send_mobile(
            self.hass,
            self._notify_services,
            self._connection_error_notification_title,
            message,
        )

    async def _send_connection_notification(self, message: str, *, recovered: bool = False) -> None:
        """Send a connection message: persistent now, mobile via quiet hours."""
        if self._notify_connection_errors_persistent:
            send_persistent(
                self.hass,
                self.name,
                message,
                self._connection_error_notification_title,
                "connection_error",
            )
        if recovered:
            # A pending "lost" notification is moot once we are back.
            self._quiet.clear_held()
        if self._notify_connection_errors_mobile:
            await self._quiet.deliver(message)

    async def _handle_connection_failure(self) -> None:
        """Track consecutive failures and notify once the configured delay has elapsed."""
        self._consecutive_failures += 1
        if self._consecutive_failures == 1:
            self._connection_lost_time = datetime.now()

        _LOGGER.debug(
            "Consecutive failures: %s/%s, notified: %s, mobile: %s, persistent: %s",
            self._consecutive_failures,
            self._failures_for_delay,
            self._connection_error_notified,
            self._notify_connection_errors_mobile,
            self._notify_connection_errors_persistent,
        )

        if (
            self._consecutive_failures >= self._failures_for_delay
            and (self._notify_connection_errors_mobile or self._notify_connection_errors_persistent)
            and not self._connection_error_notified
        ):
            lost_time = (self._connection_lost_time or datetime.now()).strftime("%d-%m-%Y %H:%M:%S")
            await self._send_connection_notification(
                f"Communicatie met {self.name} verloren sinds {lost_time}"
            )
            self._connection_error_notified = True

    async def _handle_connection_restored(self) -> None:
        """Reset failure tracking and optionally announce recovery."""
        if self._consecutive_failures > 0:
            _LOGGER.debug("Connection restored, resetting %s consecutive failures", self._consecutive_failures)
        was_notified = self._connection_error_notified
        self._consecutive_failures = 0
        self._connection_lost_time = None
        self._connection_error_notified = False

        if was_notified and self._notify_recovery:
            await self._send_connection_notification(
                f"Communicatie met {self.name} hersteld", recovered=True
            )

    def _read_ranges(self, ranges: list[tuple[int, int]]) -> tuple[list[int], list[tuple[int, int]]]:
        """Read a list of (start, count) register ranges, retrying each up to MAX_READ_RETRIES times."""
        all_registers: list[int] = []
        failed_ranges: list[tuple[int, int]] = []

        for start, count in ranges:
            success = False
            for attempt in range(MAX_READ_RETRIES):
                response = self._read_holding_registers(address=start, count=count)
                if response is not None and len(response.registers) >= count:
                    all_registers.extend(response.registers)
                    _LOGGER.debug(
                        "Read %s registers from %s-%s on attempt %s",
                        len(response.registers),
                        start,
                        start + count - 1,
                        attempt + 1,
                    )
                    success = True
                    break
                _LOGGER.warning(
                    "Attempt %s failed for range %s-%s",
                    attempt + 1,
                    start,
                    start + count - 1,
                )
                time.sleep(0.3)
            if not success:
                failed_ranges.append((start, count))

        if failed_ranges:
            _LOGGER.warning("Some ranges failed: %s. Proceeding with available data.", failed_ranges)

        return all_registers, failed_ranges

    def _read_static_data(self) -> None:
        """Read static device registers once and cache them in _static_data."""
        _LOGGER.debug("Start reading static data")
        all_registers, failed_ranges = self._read_ranges(STATIC_READ_RANGES)

        if len(failed_ranges) == len(STATIC_READ_RANGES):
            return

        decoded = all_registers
        register_map: dict[int, int] = {}
        index = 0
        for start, count in STATIC_READ_RANGES:
            if (start, count) not in failed_ranges:
                for offset in range(count):
                    register_map[start + offset] = index
                    index += 1

        static: dict = {}

        for register in ("105", "111", "112"):
            reg_int = int(register)
            if reg_int in register_map:
                raw = decoded[register_map[reg_int]]
                static[register] = ENUM_REGISTERS[register].get(raw, raw)
            else:
                static[register] = None

        if FIRMWARE_REGISTER in register_map:
            static["firmware_version"] = self._format_firmware_version(
                decoded[register_map[FIRMWARE_REGISTER]]
            )
        else:
            static["firmware_version"] = None

        bl_reg = FIRMWARE_REGISTER + 3
        if bl_reg in register_map:
            raw_bl = decoded[register_map[bl_reg]]
            if raw_bl > 0:
                bl_major = raw_bl // 100
                bl_minor = raw_bl % 100
                static["bootloader_version"] = f"{bl_major}.{bl_minor:02d}"
                static["hardware_version"] = f"{bl_minor:02d}"
            else:
                static["bootloader_version"] = None
                static["hardware_version"] = None
        else:
            static["bootloader_version"] = None
            static["hardware_version"] = None

        serial_chars = [
            chr(decoded[register_map[reg]])
            for reg in range(115, 131)
            if reg in register_map and 0x20 <= decoded[register_map[reg]] <= 0x7E
        ]
        static["serial_number"] = "".join(serial_chars).rstrip() or None

        self._static_data = static
        _LOGGER.debug("Finished reading static data")

    def read_modbus_realtime_data(self) -> tuple[dict, list[tuple[int, int]]] | tuple[None, list[tuple[int, int]]]:
        """Read realtime sensor values."""
        if not self._static_data:
            self._read_static_data()

        _LOGGER.debug("Start reading realtime data")
        all_registers, failed_ranges = self._read_ranges(READ_RANGES)

        if not all_registers:
            return None, failed_ranges

        decoded = all_registers

        register_map = {}
        index = 0
        for start, count in READ_RANGES:
            if (start, count) not in failed_ranges:
                for offset in range(count):
                    register_map[start + offset] = index
                    index += 1

        data = {}
        for register, description in SENSOR_TYPES.items():
            if not str(register).isdigit():
                continue

            register_int = int(register)
            if register_int not in register_map:
                data[register] = None
                continue

            raw_value = decoded[register_map[register_int]]

            if register in ENUM_REGISTERS:
                data[register] = ENUM_REGISTERS[register].get(raw_value, raw_value)
                continue

            if register in BOOLEAN_REGISTERS:
                data[register] = ON_OFF_STATUS.get(raw_value, raw_value)
                continue

            if description.signed and raw_value >= 0x8000:
                raw_value -= 0x10000

            value = raw_value * description.scale
            if description.suggested_display_precision is not None:
                value = round(value, description.suggested_display_precision)
            data[register] = value

        data.update(self._static_data)

        for reg_str, bits in ALARM_BITS.items():
            raw = decoded[register_map[int(reg_str)]] if int(reg_str) in register_map else None
            for bit_pos, _ in bits:
                data[alarm_data_key(reg_str, bit_pos)] = bool(raw & (1 << bit_pos)) if raw is not None else None

        for prefix, temp_reg, rh_reg in (
            ("extract", "304", "308"),
            ("exhaust", "305", "309"),
            ("intake", "300", "306"),
            ("supply", "303", "307"),
        ):
            temp = data.get(temp_reg)
            rh = data.get(rh_reg)
            abs_hum = self._calc_absolute_humidity(temp, rh) if temp is not None and rh is not None else None
            data[f"{prefix}_absolute_humidity"] = abs_hum
            data[f"{prefix}_enthalpy"] = self._calc_enthalpy(temp, abs_hum) if temp is not None and abs_hum is not None else None
            data[f"{prefix}_dewpoint"] = self._calc_dewpoint(temp, rh) if temp is not None and rh is not None else None

        t_supply = data.get("303")
        t_extract = data.get("304")
        if t_supply is not None and t_extract is not None and abs(t_extract) >= 1.0:
            raw = (t_supply / t_extract) * 100
            data["temperature_efficiency"] = round(max(0.0, min(100.0, raw)), 1)
        else:
            data["temperature_efficiency"] = None

        supply_flow = data.get("313")
        extract_flow = data.get("312")
        if supply_flow is not None and extract_flow is not None:
            data["flow_balance"] = round(supply_flow - extract_flow, 0)
        else:
            data["flow_balance"] = None

        # Lowest temperature that stays clear of condensation: the dew point of
        # the indoor air (extract) plus the configured margin. The alarm itself is
        # evaluated in _async_update_data, which can read the linked entity.
        extract_dewpoint = data.get("extract_dewpoint")
        if extract_dewpoint is not None:
            raw_limit = round(extract_dewpoint + self._dewpoint_delta, 1)
        else:
            raw_limit = None
        self._condensation_limit_raw = raw_limit
        data["condensation_limit"] = self._rate_limited(raw_limit)

        self._last_successful_read = datetime.now()
        _LOGGER.debug("Finished reading realtime data")
        return data, failed_ranges
