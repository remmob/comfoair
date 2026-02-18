"""ComfoAir Modbus Hub/coordinator."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusIOException
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    BATHROOM_SWITCH_REGISTER,
    BATHROOM_SWITCH_STATUS,
    BOOLEAN_REGISTERS,
    MODE_SERIAL,
    ON_OFF_STATUS,
    READ_RANGES,
    SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

MAX_READ_RETRIES = 3


class ComfoAirHub(DataUpdateCoordinator[dict]):
    """Thread safe wrapper class for pymodbus."""

    @staticmethod
    def _format_firmware_version(raw_value: int) -> str | None:
        """Convert raw firmware register to a readable firmware version string."""
        if raw_value <= 0:
            return None

        major = raw_value // 10000
        minor = (raw_value % 10000) // 100
        patch = raw_value % 100

        if patch > 0:
            return f"{major}.{minor}.{patch}"
        return f"{major}.{minor}"

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

        self._client = None
        self._lock = threading.Lock()
        self._modbus_lock = threading.Lock()
        self._consecutive_failures = 0
        self._last_successful_read = None

        storage_key = f"{name}_data_store"
        if storage_key not in hass.data:
            hass.data[storage_key] = {"realtime_data": {}}
        self.data_store = hass.data[storage_key]

        self._client = self._create_client()

    def _create_client(self):
        if self._mode == MODE_SERIAL:
            return ModbusSerialClient(
                port=self._device,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                parity=self._parity,
                stopbits=self._stopbits,
                timeout=3,
            )
        return ModbusTcpClient(host=self._host, port=self._port, timeout=3)

    def close(self) -> None:
        """Disconnect client."""
        try:
            with self._lock:
                if self._client is not None:
                    self._client.close()
                    self._client = None
        except Exception as err:
            _LOGGER.exception("Error closing Modbus connection: %s", err)

    def _read_holding_registers(self, address: int, count: int):
        """Safely read holding registers with reconnect logic."""
        try:
            if self._client is None or not self._client.connected:
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:
                        pass
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

            if response is None or response.isError() or not hasattr(response, "registers"):
                return None
            return response
        except (ConnectionException, ModbusIOException, OSError) as err:
            _LOGGER.error("Modbus communication error while reading %s-%s: %s", address, address + count - 1, err)
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
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
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                    self._client = None

        data = {**self.data_store.get("realtime_data", {})}

        realtime_result = await self.hass.async_add_executor_job(self.read_modbus_realtime_data)
        if isinstance(realtime_result, tuple):
            realtime, failed_ranges = realtime_result
        else:
            realtime = realtime_result
            failed_ranges = []

        if realtime is None:
            data["connection_status"] = "Failed"
            self._consecutive_failures += 1
            return data

        if failed_ranges:
            data["connection_status"] = "Partial"
        else:
            data["connection_status"] = "OK"
        self._consecutive_failures = 0

        data.update(realtime)
        self.data_store["realtime_data"] = realtime
        return data

    def read_modbus_realtime_data(self) -> tuple[dict, list[tuple[int, int]]] | tuple[None, list[tuple[int, int]]]:
        """Read realtime sensor values."""
        all_registers = []
        failed_ranges = []

        for start, count in READ_RANGES:
            success = False
            for attempt in range(MAX_READ_RETRIES):
                response = self._read_holding_registers(address=start, count=count)
                if response is not None and len(response.registers) >= count:
                    all_registers.extend(response.registers)
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

            if register == BATHROOM_SWITCH_REGISTER:
                data[register] = BATHROOM_SWITCH_STATUS.get(raw_value, raw_value)
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

        firmware_register = 110
        if firmware_register in register_map:
            raw_firmware = decoded[register_map[firmware_register]]
            data["firmware_version"] = self._format_firmware_version(raw_firmware)
        else:
            data["firmware_version"] = None

        self._last_successful_read = datetime.now()
        return data, failed_ranges
