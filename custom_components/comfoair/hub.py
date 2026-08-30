"""ComfoAir Modbus Hub/coordinator."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta

from modbus_connection import ModbusError, ModbusTimeoutError, ModbusUnit
from modbus_connection.model import ManualComponent
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ALARM_BITS,
    BOOLEAN_REGISTERS,
    DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE,
    ENUM_REGISTERS,
    FIRMWARE_REGISTER,
    ON_OFF_STATUS,
    SENSOR_TYPES,
    alarm_data_key,
)
from .device import build_realtime_component, build_static_component
from .notifications import QuietHours, parse_services, send_mobile, send_persistent

_LOGGER = logging.getLogger(__name__)

MAX_READ_RETRIES = 3

# This many consecutive timeouts means a stuck link: the socket is still open
# but the device behind it has stopped responding, so automatic reconnection
# has nothing to reconnect. See read_modbus_realtime_data() below.
STUCK_LINK_TIMEOUTS = 3


class ComfoAirHub(DataUpdateCoordinator[dict]):
    """Coordinator that polls the ComfoAir over a Modbus unit."""

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
        unit: ModbusUnit,
        scan_interval: int,
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
        self._dewpoint_delta = float(dewpoint_delta)
        self._condensation_source = condensation_source or ""
        self._condensation_max_change = max(0.0, float(condensation_max_change))
        self._condensation_limit_raw: float | None = None
        self._limit_value: float | None = None
        self._limit_updated: float | None = None

        self._unit = unit
        self._realtime: ManualComponent = build_realtime_component(unit)
        self._static: ManualComponent = build_static_component(unit)
        self._static_data: dict = {}
        # Number of consecutive polls that ended in a timeout. See
        # read_modbus_realtime_data() for where this resets and what happens
        # when the counter fills up.
        self._consecutive_timeouts = 0

        self._notify_connection_errors_mobile = notify_connection_errors_mobile
        self._notify_connection_errors_persistent = notify_connection_errors_persistent
        self._notify_recovery = notify_recovery
        self._notify_services = parse_services(notify_services)
        self._connection_error_notification_title = connection_error_notification_title
        self._consecutive_failures = 0
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

    def start_notifications(self) -> None:
        """Start the quiet-hours release trigger for connection notifications."""
        self._quiet.start()

    def close(self) -> None:
        """Stop the quiet-hours trigger.

        The Modbus connection itself is not ours to close: connection.py
        registered its own teardown (entry.async_on_unload) when the unit was
        set up, whether that is Home Assistant's shared connection or one we
        opened ourselves.
        """
        self._quiet.stop()

    async def _update_component_with_retry(self, component: ManualComponent, label: str) -> None:
        """Update a component, retrying failures up to MAX_READ_RETRIES times.

        Raises the last error once every attempt has failed.
        """
        last_error: ModbusError | None = None

        for attempt in range(MAX_READ_RETRIES):
            try:
                await component.async_update()
                return
            except ModbusError as err:
                last_error = err
                _LOGGER.warning(
                    "Attempt %s/%s failed reading %s: %s", attempt + 1, MAX_READ_RETRIES, label, err
                )
                if attempt < MAX_READ_RETRIES - 1:
                    await asyncio.sleep(0.3)

        assert last_error is not None
        raise last_error

    async def _async_update_data(self) -> dict:
        """Fetch Modbus data with fallback to previous values."""
        data = {**self.data_store.get("realtime_data", {})}

        realtime = await self.read_modbus_realtime_data()

        if realtime is None:
            data["connection_status"] = "Failed"
            await self._handle_connection_failure()
            return data

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

    async def _read_static_data(self) -> None:
        """Read static device registers once and cache them in _static_data."""
        _LOGGER.debug("Start reading static data")
        try:
            await self._update_component_with_retry(self._static, "static data")
        except ModbusError as err:
            _LOGGER.warning("Reading static data failed: %s", err)
            return  # self._static_data stays empty; retried on the next poll

        static: dict = {}

        for register in ("105", "111", "112"):
            raw = self._static.get(register)
            static[register] = ENUM_REGISTERS[register].get(raw, raw)

        static["firmware_version"] = self._format_firmware_version(
            self._static.get(str(FIRMWARE_REGISTER))
        )

        raw_bl = self._static.get(str(FIRMWARE_REGISTER + 3))
        if raw_bl > 0:
            bl_major = raw_bl // 100
            bl_minor = raw_bl % 100
            static["bootloader_version"] = f"{bl_major}.{bl_minor:02d}"
            static["hardware_version"] = f"{bl_minor:02d}"
        else:
            static["bootloader_version"] = None
            static["hardware_version"] = None

        serial_chars = [
            chr(value)
            for reg in range(115, 131)
            if 0x20 <= (value := self._static.get(str(reg))) <= 0x7E
        ]
        static["serial_number"] = "".join(serial_chars).rstrip() or None

        self._static_data = static
        _LOGGER.debug("Finished reading static data")

    async def read_modbus_realtime_data(self) -> dict | None:
        """Read realtime sensor values. Returns None if the read failed."""
        if not self._static_data:
            await self._read_static_data()

        _LOGGER.debug("Start reading realtime data")
        try:
            await self._update_component_with_retry(self._realtime, "realtime data")
        except ModbusTimeoutError:
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= STUCK_LINK_TIMEOUTS:
                _LOGGER.warning(
                    "%s consecutive polls timed out; the connection appears "
                    "stuck. Disconnecting so the next poll opens a fresh "
                    "connection.",
                    self._consecutive_timeouts,
                )
                await self._unit.disconnect()
                # Reset to zero, otherwise every following poll would
                # disconnect again and a fresh connection would never get a
                # chance to prove itself.
                self._consecutive_timeouts = 0
            return None
        except ModbusError as err:
            _LOGGER.warning("Reading realtime data failed: %s", err)
            return None

        self._consecutive_timeouts = 0

        data = {}
        for register in SENSOR_TYPES:
            if not register.isdigit():
                continue

            raw_value = self._realtime.get(register)
            if raw_value is None:
                data[register] = None
                continue

            if register in ENUM_REGISTERS:
                data[register] = ENUM_REGISTERS[register].get(raw_value, raw_value)
                continue

            if register in BOOLEAN_REGISTERS:
                data[register] = ON_OFF_STATUS.get(raw_value, raw_value)
                continue

            # Already sign-decoded and scaled by the register field in device.py
            data[register] = raw_value

        data.update(self._static_data)

        for reg_str, bits in ALARM_BITS.items():
            raw = self._realtime.get(reg_str)
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

        _LOGGER.debug("Finished reading realtime data")
        return data
