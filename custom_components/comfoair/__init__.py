"""The ComfoAir Modbus integration."""

from __future__ import annotations

import logging

import pymodbus

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
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
    CONTROL_TYPE_MANUAL,
    DEFAULT_ALARM_DELAY,
    DEFAULT_ALARM_NOTIFICATION_TITLE,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_CONNECTION_ERROR_DELAY,
    DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE,
    DEFAULT_DEVICE_ID,
    DEFAULT_DEWPOINT_DELTA,
    DEFAULT_NOTIFY_ALARMS_MOBILE,
    DEFAULT_NOTIFY_ALARMS_PERSISTENT,
    DEFAULT_NOTIFY_ALARMS_SERVICES,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES,
    DEFAULT_PARITY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOPBITS,
    DOMAIN,
    PLATFORMS,
)
from .alarm_monitor import AlarmMonitor
from .hub import ComfoAirHub

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(_hass: HomeAssistant, _config: dict) -> bool:
    """Set up via YAML is not supported."""
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the latest format."""
    if entry.version < 2:
        data = dict(entry.data)
        control_type = data.get(CONF_CONTROL_TYPE)

        if control_type in {"manueel", "3-way switch"}:
            data[CONF_CONTROL_TYPE] = CONTROL_TYPE_MANUAL

        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.info("Migrated ComfoAir entry %s to version 2", entry.entry_id)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ComfoAir from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    name = entry.data[CONF_NAME]
    mode = entry.data[CONF_MODE]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    _LOGGER.info("Setting up %s.%s", DOMAIN, name)
    _LOGGER.debug("Used pymodbus version: %s", pymodbus.__version__)
    _LOGGER.debug(
        "Connection error delay configured: %s seconds",
        entry.data.get(CONF_CONNECTION_ERROR_DELAY, DEFAULT_CONNECTION_ERROR_DELAY),
    )
    _LOGGER.debug("Alarm delay configured: %s seconds", entry.data.get(CONF_ALARM_DELAY, DEFAULT_ALARM_DELAY))

    hub = ComfoAirHub(
        hass=hass,
        name=name,
        scan_interval=scan_interval,
        mode=mode,
        device_id=DEFAULT_DEVICE_ID,
        host=entry.data.get(CONF_HOST),
        port=entry.data.get(CONF_PORT),
        device=entry.data.get(CONF_DEVICE),
        baudrate=entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        bytesize=entry.data.get(CONF_BYTESIZE, DEFAULT_BYTESIZE),
        parity=entry.data.get(CONF_PARITY, DEFAULT_PARITY),
        stopbits=entry.data.get(CONF_STOPBITS, DEFAULT_STOPBITS),
        dewpoint_delta=entry.data.get(CONF_DEWPOINT_DELTA, DEFAULT_DEWPOINT_DELTA),
        notify_connection_errors_mobile=entry.data.get(
            CONF_NOTIFY_CONNECTION_ERRORS_MOBILE, DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE
        ),
        notify_connection_errors_persistent=entry.data.get(
            CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT, DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT
        ),
        notify_services=entry.data.get(
            CONF_NOTIFY_CONNECTION_ERRORS_SERVICES, DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES
        ),
        connection_error_notification_title=entry.data.get(
            CONF_CONNECTION_ERROR_NOTIFICATION_TITLE, DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE
        ),
        connection_error_delay=entry.data.get(CONF_CONNECTION_ERROR_DELAY, DEFAULT_CONNECTION_ERROR_DELAY),
    )
    await hub.async_config_entry_first_refresh()

    alarm_monitor = AlarmMonitor(
        hass=hass,
        name=name,
        hub=hub,
        notify_alarms_mobile=entry.data.get(CONF_NOTIFY_ALARMS_MOBILE, DEFAULT_NOTIFY_ALARMS_MOBILE),
        notify_alarms_persistent=entry.data.get(CONF_NOTIFY_ALARMS_PERSISTENT, DEFAULT_NOTIFY_ALARMS_PERSISTENT),
        notify_services=entry.data.get(CONF_NOTIFY_ALARMS_SERVICES, DEFAULT_NOTIFY_ALARMS_SERVICES),
        notification_title=entry.data.get(CONF_ALARM_NOTIFICATION_TITLE, DEFAULT_ALARM_NOTIFICATION_TITLE),
        alarm_delay=entry.data.get(CONF_ALARM_DELAY, DEFAULT_ALARM_DELAY),
    )

    firmware_version = None
    model_display = None
    serial_number = None
    if isinstance(hub.data, dict):
        firmware_version = hub.data.get("firmware_version")
        model_parts = ["ComfoAir", hub.data.get("112"), hub.data.get("111")]
        model_display = " ".join(p for p in model_parts if p) or None
        serial_number = hub.data.get("serial_number")

    hass.data[DOMAIN][name] = {
        "hub": hub,
        "mode": mode,
        "alarm_monitor": alarm_monitor,
        "device_info": {
            "identifiers": {(DOMAIN, name)},
            "name": name,
            "manufacturer": "Mischa Bommer",
            "model": model_display,
            "sw_version": firmware_version,
            "serial_number": serial_number,
        },
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    alarm_monitor.start_monitoring()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        item = hass.data[DOMAIN].pop(entry.data[CONF_NAME])
        alarm_monitor: AlarmMonitor = item["alarm_monitor"]
        alarm_monitor.stop_monitoring()
        hub: ComfoAirHub = item["hub"]
        hub.close()
    return unload_ok
