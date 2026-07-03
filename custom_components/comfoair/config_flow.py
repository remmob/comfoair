"""Config flow for ComfoAir Modbus integration."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re

import serial.tools.list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

_LOGGER = logging.getLogger(__name__)

from .const import (
    ALLOWED_BAUDRATES,
    ALLOWED_BYTESIZES,
    ALLOWED_DEVICE_IDS,
    ALLOWED_PARITIES,
    ALLOWED_STOPBITS,
    CONF_ALARM_DELAY,
    CONF_ALARM_NOTIFICATION_TITLE,
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_CONNECTION_ERROR_DELAY,
    CONF_CONNECTION_ERROR_NOTIFICATION_TITLE,
    CONF_CONTROL_TYPE,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_DEWPOINT_DELTA,
    CONF_MODE,
    CONF_NOTIFY_ALARMS_MOBILE,
    CONF_NOTIFY_ALARMS_PERSISTENT,
    CONF_NOTIFY_ALARMS_SERVICES,
    CONF_NOTIFY_CONNECTION_ERRORS_MOBILE,
    CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    CONF_NOTIFY_CONNECTION_ERRORS_SERVICES,
    CONF_PARITY,
    CONF_STOPBITS,
    CONTROL_TYPE_0_10V,
    CONTROL_TYPE_MANUAL,
    CONTROL_TYPE_RF,
    DEFAULT_ALARM_DELAY,
    DEFAULT_ALARM_NOTIFICATION_TITLE,
    DEFAULT_BAUDRATE,
    DEFAULT_CONTROL_TYPE,
    DEFAULT_BYTESIZE,
    DEFAULT_CONNECTION_ERROR_DELAY,
    DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE,
    DEFAULT_DEWPOINT_DELTA,
    DEFAULT_DEVICE_ID,
    DEFAULT_NAME,
    DEFAULT_NOTIFY_ALARMS_MOBILE,
    DEFAULT_NOTIFY_ALARMS_PERSISTENT,
    DEFAULT_NOTIFY_ALARMS_SERVICES,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES,
    DEFAULT_PARITY,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOPBITS,
    DOMAIN,
    MODE_SERIAL,
    MODE_TCP,
    MODES,
)


def host_valid(host: str) -> bool:
    """Return True if hostname or IP address is valid."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        disallowed = re.compile(r"[^a-zA-Z\d\-]")
        return all(part and not disallowed.search(part) for part in host.split("."))


def _connection_unique_id(data: dict) -> str:
    mode = data[CONF_MODE]
    if mode == MODE_SERIAL:
        return f"{MODE_SERIAL}:{data[CONF_DEVICE]}:{data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)}"
    return f"{MODE_TCP}:{data[CONF_HOST]}:{data[CONF_PORT]}:{data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)}"


def _get_notify_service_options(hass: HomeAssistant) -> list[str]:
    services = hass.services.async_services().get("notify", {})
    return sorted(name for name in services if name.startswith("mobile_app_"))


def _services_default(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def _normalize_services(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value else ""


def _notify_services_selector(hass: HomeAssistant) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_get_notify_service_options(hass),
            multiple=True,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _notification_schema_fields(hass: HomeAssistant, current: dict) -> dict:
    """Shared alarm/connection-error notification fields for the options flow."""
    return {
        # === ALARM NOTIFICATIONS ===
        vol.Optional(
            CONF_NOTIFY_ALARMS_MOBILE,
            default=current.get(CONF_NOTIFY_ALARMS_MOBILE, DEFAULT_NOTIFY_ALARMS_MOBILE),
        ): bool,
        vol.Optional(
            CONF_NOTIFY_ALARMS_PERSISTENT,
            default=current.get(CONF_NOTIFY_ALARMS_PERSISTENT, DEFAULT_NOTIFY_ALARMS_PERSISTENT),
        ): bool,
        vol.Optional(
            CONF_NOTIFY_ALARMS_SERVICES,
            default=_services_default(current.get(CONF_NOTIFY_ALARMS_SERVICES, DEFAULT_NOTIFY_ALARMS_SERVICES)),
        ): _notify_services_selector(hass),
        vol.Optional(
            CONF_ALARM_NOTIFICATION_TITLE,
            default=current.get(CONF_ALARM_NOTIFICATION_TITLE, DEFAULT_ALARM_NOTIFICATION_TITLE),
        ): str,
        vol.Optional(
            CONF_ALARM_DELAY,
            default=current.get(CONF_ALARM_DELAY, DEFAULT_ALARM_DELAY),
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
        # === CONNECTION ERROR NOTIFICATIONS ===
        vol.Optional(
            CONF_NOTIFY_CONNECTION_ERRORS_MOBILE,
            default=current.get(CONF_NOTIFY_CONNECTION_ERRORS_MOBILE, DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE),
        ): bool,
        vol.Optional(
            CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
            default=current.get(
                CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT, DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT
            ),
        ): bool,
        vol.Optional(
            CONF_NOTIFY_CONNECTION_ERRORS_SERVICES,
            default=_services_default(
                current.get(CONF_NOTIFY_CONNECTION_ERRORS_SERVICES, DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES)
            ),
        ): _notify_services_selector(hass),
        vol.Optional(
            CONF_CONNECTION_ERROR_NOTIFICATION_TITLE,
            default=current.get(
                CONF_CONNECTION_ERROR_NOTIFICATION_TITLE, DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE
            ),
        ): str,
        vol.Optional(
            CONF_CONNECTION_ERROR_DELAY,
            default=current.get(CONF_CONNECTION_ERROR_DELAY, DEFAULT_CONNECTION_ERROR_DELAY),
        ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
    }


def _options_selector(options: list) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=str(opt), label=str(opt)) for opt in options],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _device_id_selector(default_value: int):
    return vol.All(_options_selector(ALLOWED_DEVICE_IDS), vol.Coerce(int))


def _baudrate_selector():
    return vol.All(_options_selector(ALLOWED_BAUDRATES), vol.Coerce(int))


def _bytesize_selector():
    return vol.All(_options_selector(ALLOWED_BYTESIZES), vol.Coerce(int))


def _stopbits_selector():
    return vol.All(_options_selector(ALLOWED_STOPBITS), vol.Coerce(int))


def _tcp_schema_fields(current: dict) -> dict:
    """Shared TCP connection fields for the setup, reconfigure and options flows."""
    return {
        vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
        vol.Required(
            CONF_PORT,
            default=current.get(CONF_PORT, DEFAULT_PORT),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional(
            CONF_SCAN_INTERVAL,
            default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
    }


def _serial_schema_fields(current: dict, serial_ports: list[str], default_device: str) -> dict:
    """Shared serial connection fields for the setup, reconfigure and options flows."""
    return {
        vol.Required(CONF_DEVICE, default=default_device): vol.In(serial_ports) if serial_ports else str,
        vol.Required(
            CONF_BAUDRATE,
            default=str(current.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)),
        ): _baudrate_selector(),
        vol.Required(
            CONF_BYTESIZE,
            default=str(current.get(CONF_BYTESIZE, DEFAULT_BYTESIZE)),
        ): _bytesize_selector(),
        vol.Required(
            CONF_PARITY,
            default=current.get(CONF_PARITY, DEFAULT_PARITY),
        ): vol.In(ALLOWED_PARITIES),
        vol.Required(
            CONF_STOPBITS,
            default=str(current.get(CONF_STOPBITS, DEFAULT_STOPBITS)),
        ): _stopbits_selector(),
        vol.Optional(
            CONF_SCAN_INTERVAL,
            default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
    }


def _control_type_selector(default_value: str):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=CONTROL_TYPE_0_10V, label="Analoog (0-10V)"),
                selector.SelectOptionDict(value=CONTROL_TYPE_RF, label="RF"),
                selector.SelectOptionDict(value=CONTROL_TYPE_MANUAL, label="3-way switch"),
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _normalize_device_id(data: dict) -> dict:
    normalized = dict(data)
    normalized[CONF_DEVICE_ID] = DEFAULT_DEVICE_ID
    return normalized


async def _get_serial_ports() -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: [port.device for port in serial.tools.list_ports.comports()],
    )


@callback
def configured_connections(hass: HomeAssistant) -> set[str]:
    """Return already configured connection ids."""
    configured: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        try:
            configured.add(_connection_unique_id(entry.data))
        except KeyError:
            continue
    return configured


class ComfoAirConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle ComfoAir config flow."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        self._data: dict = {}
        self._reconfigure_data: dict = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ComfoAirOptionsFlow()

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = _normalize_device_id(user_input)
            if self._data[CONF_MODE] == MODE_SERIAL:
                return await self.async_step_serial()
            return await self.async_step_tcp()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_DEVICE_ID, default=str(DEFAULT_DEVICE_ID)): _device_id_selector(
                        DEFAULT_DEVICE_ID
                    ),
                    vol.Required(CONF_MODE, default=MODE_TCP): vol.In(MODES),
                }
            ),
        )

    async def async_step_tcp(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            candidate = _normalize_device_id({**self._data, **user_input})
            host = candidate[CONF_HOST].strip().lower()
            candidate[CONF_HOST] = host

            if not host_valid(host):
                errors[CONF_HOST] = "invalid_host"
            elif not 1 <= candidate[CONF_PORT] <= 65535:
                errors[CONF_PORT] = "invalid_port"
            else:
                self._data = {
                    **candidate,
                    CONF_SCAN_INTERVAL: candidate.get(
                        CONF_SCAN_INTERVAL,
                        DEFAULT_SCAN_INTERVAL,
                    ),
                }
                return await self.async_step_control_type()

        return self.async_show_form(
            step_id="tcp",
            data_schema=vol.Schema(_tcp_schema_fields(self._data)),
            errors=errors,
        )

    async def async_step_serial(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        serial_ports = await _get_serial_ports()
        default_device = self._data.get(CONF_DEVICE) or (serial_ports[0] if serial_ports else "")

        if user_input is not None:
            candidate = _normalize_device_id({**self._data, **user_input})

            if serial_ports and candidate[CONF_DEVICE] not in serial_ports:
                errors[CONF_DEVICE] = "invalid_serial_port"
            else:
                self._data = {
                    **candidate,
                    CONF_SCAN_INTERVAL: candidate.get(
                        CONF_SCAN_INTERVAL,
                        DEFAULT_SCAN_INTERVAL,
                    ),
                }
                return await self.async_step_control_type()

        return self.async_show_form(
            step_id="serial",
            data_schema=vol.Schema(_serial_schema_fields(self._data, serial_ports, default_device)),
            errors=errors,
        )

    async def async_step_control_type(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            candidate = {**self._data, **user_input}
            unique_id = _connection_unique_id(candidate)
            if unique_id in configured_connections(self.hass):
                errors["base"] = "already_configured"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=candidate[CONF_NAME],
                    data=candidate,
                )

        return self.async_show_form(
            step_id="control_type",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONTROL_TYPE,
                        default=self._data.get(CONF_CONTROL_TYPE, DEFAULT_CONTROL_TYPE),
                    ): _control_type_selector(self._data.get(CONF_CONTROL_TYPE, DEFAULT_CONTROL_TYPE)),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        if not self._reconfigure_data:
            self._reconfigure_data = {
                CONF_NAME: entry.data.get(CONF_NAME, DEFAULT_NAME),
                CONF_DEVICE_ID: DEFAULT_DEVICE_ID,
                CONF_MODE: entry.data.get(CONF_MODE, MODE_TCP),
                CONF_CONTROL_TYPE: entry.data.get(CONF_CONTROL_TYPE, DEFAULT_CONTROL_TYPE),
            }

        if user_input is not None:
            self._reconfigure_data.update(_normalize_device_id(user_input))
            if self._reconfigure_data.get(CONF_MODE) == MODE_SERIAL:
                return await self.async_step_reconfigure_serial()
            return await self.async_step_reconfigure_tcp()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=self._reconfigure_data.get(CONF_NAME, DEFAULT_NAME),
                    ): str,
                    vol.Required(
                        CONF_DEVICE_ID,
                        default=str(DEFAULT_DEVICE_ID),
                    ): _device_id_selector(self._reconfigure_data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)),
                    vol.Required(
                        CONF_MODE,
                        default=self._reconfigure_data.get(CONF_MODE, MODE_TCP),
                    ): vol.In(MODES),
                }
            ),
        )

    async def async_step_reconfigure_tcp(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            merged = _normalize_device_id({**entry.data, **self._reconfigure_data, **user_input})
            merged[CONF_MODE] = MODE_TCP
            host = merged[CONF_HOST].strip().lower()
            merged[CONF_HOST] = host

            if not host_valid(host):
                errors[CONF_HOST] = "invalid_host"
            elif not 1 <= merged[CONF_PORT] <= 65535:
                errors[CONF_PORT] = "invalid_port"
            else:
                self._reconfigure_data = merged
                return await self.async_step_reconfigure_control_type()

        return self.async_show_form(
            step_id="reconfigure_tcp",
            data_schema=vol.Schema(_tcp_schema_fields(entry.data)),
            errors=errors,
        )

    async def async_step_reconfigure_serial(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        serial_ports = await _get_serial_ports()

        if user_input is not None:
            merged = _normalize_device_id({**entry.data, **self._reconfigure_data, **user_input})
            merged[CONF_MODE] = MODE_SERIAL

            if serial_ports and merged[CONF_DEVICE] not in serial_ports:
                errors[CONF_DEVICE] = "invalid_serial_port"
            else:
                self._reconfigure_data = merged
                return await self.async_step_reconfigure_control_type()

        default_device = entry.data.get(CONF_DEVICE, serial_ports[0] if serial_ports else "")
        return self.async_show_form(
            step_id="reconfigure_serial",
            data_schema=vol.Schema(_serial_schema_fields(entry.data, serial_ports, default_device)),
            errors=errors,
        )

    async def async_step_reconfigure_control_type(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            merged = _normalize_device_id({**self._reconfigure_data, **user_input})
            new_unique_id = _connection_unique_id(merged)
            if new_unique_id != entry.unique_id:
                if merged.get(CONF_MODE) == MODE_SERIAL:
                    self._async_abort_entries_match(
                        {
                            CONF_MODE: MODE_SERIAL,
                            CONF_DEVICE: merged[CONF_DEVICE],
                            CONF_DEVICE_ID: merged[CONF_DEVICE_ID],
                        }
                    )
                else:
                    self._async_abort_entries_match(
                        {
                            CONF_MODE: MODE_TCP,
                            CONF_HOST: merged[CONF_HOST],
                            CONF_PORT: merged[CONF_PORT],
                            CONF_DEVICE_ID: merged[CONF_DEVICE_ID],
                        }
                    )

            return self.async_update_reload_and_abort(
                entry,
                unique_id=new_unique_id,
                data=merged,
                reason="reconfigure_successful",
            )

        return self.async_show_form(
            step_id="reconfigure_control_type",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONTROL_TYPE,
                        default=self._reconfigure_data.get(CONF_CONTROL_TYPE, DEFAULT_CONTROL_TYPE),
                    ): _control_type_selector(self._reconfigure_data.get(CONF_CONTROL_TYPE, DEFAULT_CONTROL_TYPE)),
                }
            ),
            errors=errors,
        )


class ComfoAirOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ComfoAir."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            _LOGGER.debug("Received user_input: %s", user_input)
            data = _normalize_device_id({**self.config_entry.data, **user_input})
            data[CONF_NOTIFY_ALARMS_SERVICES] = _normalize_services(user_input.get(CONF_NOTIFY_ALARMS_SERVICES))
            data[CONF_NOTIFY_CONNECTION_ERRORS_SERVICES] = _normalize_services(
                user_input.get(CONF_NOTIFY_CONNECTION_ERRORS_SERVICES)
            )
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        mode = self.config_entry.data.get(CONF_MODE, MODE_TCP)

        device_id_field = {
            vol.Required(
                CONF_DEVICE_ID,
                default=str(DEFAULT_DEVICE_ID),
            ): _device_id_selector(self.config_entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID))
        }
        common_fields = {
            vol.Optional(
                CONF_DEWPOINT_DELTA,
                default=self.config_entry.data.get(CONF_DEWPOINT_DELTA, DEFAULT_DEWPOINT_DELTA),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=5.0)),
            **_notification_schema_fields(self.hass, self.config_entry.data),
        }

        if mode == MODE_SERIAL:
            serial_ports = await _get_serial_ports()
            default_device = self.config_entry.data.get(CONF_DEVICE, serial_ports[0] if serial_ports else "")
            schema = vol.Schema(
                {
                    **device_id_field,
                    **_serial_schema_fields(self.config_entry.data, serial_ports, default_device),
                    **common_fields,
                }
            )
        else:
            schema = vol.Schema(
                {
                    **device_id_field,
                    **_tcp_schema_fields(self.config_entry.data),
                    **common_fields,
                }
            )

        return self.async_show_form(step_id="init", data_schema=schema)
