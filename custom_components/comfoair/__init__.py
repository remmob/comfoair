"""The ComfoAir Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ALARM_DELAY,
    CONF_ALARM_NOTIFICATION_TITLE,
    CONF_ALARM_NOTIFY_RECOVERY,
    CONF_ALARM_QUIET_ENABLED,
    CONF_ALARM_QUIET_END,
    CONF_ALARM_QUIET_START,
    CONF_CONDENSATION_MAX_CHANGE,
    CONF_CONDENSATION_SOURCE,
    CONF_CONNECTION_ERROR_DELAY,
    CONF_CONNECTION_ERROR_NOTIFICATION_TITLE,
    CONF_CONNECTION_NOTIFY_RECOVERY,
    CONF_CONNECTION_QUIET_ENABLED,
    CONF_CONNECTION_QUIET_END,
    CONF_CONNECTION_QUIET_START,
    CONF_CONTROL_TYPE,
    CONF_DEWPOINT_DELTA,
    CONF_NOTIFY_ALARMS_MOBILE,
    CONF_NOTIFY_ALARMS_PERSISTENT,
    CONF_NOTIFY_ALARMS_SERVICES,
    CONF_NOTIFY_CONNECTION_ERRORS_MOBILE,
    CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    CONF_NOTIFY_CONNECTION_ERRORS_SERVICES,
    CONF_NOTIFY_PERSISTENT,
    CONF_NOTIFY_WARNINGS_MOBILE,
    CONF_NOTIFY_WARNINGS_SERVICES,
    CONF_WARNING_DELAY,
    CONF_WARNING_NOTIFICATION_TITLE,
    CONF_WARNING_NOTIFY_RECOVERY,
    CONF_WARNING_QUIET_ENABLED,
    CONF_WARNING_QUIET_END,
    CONF_WARNING_QUIET_START,
    CONTROL_TYPE_MANUAL,
    DEFAULT_ALARM_DELAY,
    DEFAULT_ALARM_NOTIFICATION_TITLE,
    DEFAULT_CONDENSATION_MAX_CHANGE,
    DEFAULT_CONDENSATION_SOURCE,
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
    DEFAULT_NOTIFY_RECOVERY,
    DEFAULT_QUIET_HOURS_ENABLED,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WARNING_NOTIFICATION_TITLE,
    DEFAULT_WARNING_QUIET_HOURS_ENABLED,
    DOMAIN,
    PLATFORMS,
)
from .alarm_monitor import AlarmMonitor
from .connection import active_method, async_setup_unit, build_params
from .hub import ComfoAirHub

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _persistent_enabled(data: dict) -> bool:
    """Shared persistent toggle, falling back to the legacy per-category ones."""
    legacy = data.get(
        CONF_NOTIFY_ALARMS_PERSISTENT, DEFAULT_NOTIFY_ALARMS_PERSISTENT
    ) or data.get(
        CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
        DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    )
    return data.get(CONF_NOTIFY_PERSISTENT, legacy)


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
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    notify_persistent = _persistent_enabled(entry.data)

    _LOGGER.info("Setting up %s.%s", DOMAIN, name)
    _LOGGER.info("%s is using connection method: %s", name, active_method())
    _LOGGER.debug(
        "Connection error delay configured: %s seconds",
        entry.data.get(CONF_CONNECTION_ERROR_DELAY, DEFAULT_CONNECTION_ERROR_DELAY),
    )
    _LOGGER.debug("Alarm delay configured: %s seconds", entry.data.get(CONF_ALARM_DELAY, DEFAULT_ALARM_DELAY))

    params = build_params(entry.data)
    unit = async_setup_unit(hass, entry, params, DEFAULT_DEVICE_ID)

    hub = ComfoAirHub(
        hass=hass,
        name=name,
        unit=unit,
        scan_interval=scan_interval,
        dewpoint_delta=entry.data.get(CONF_DEWPOINT_DELTA, DEFAULT_DEWPOINT_DELTA),
        condensation_source=entry.data.get(CONF_CONDENSATION_SOURCE, DEFAULT_CONDENSATION_SOURCE),
        condensation_max_change=entry.data.get(
            CONF_CONDENSATION_MAX_CHANGE, DEFAULT_CONDENSATION_MAX_CHANGE
        ),
        notify_connection_errors_mobile=entry.data.get(
            CONF_NOTIFY_CONNECTION_ERRORS_MOBILE, DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE
        ),
        notify_connection_errors_persistent=notify_persistent,
        notify_recovery=entry.data.get(CONF_CONNECTION_NOTIFY_RECOVERY, DEFAULT_NOTIFY_RECOVERY),
        notify_services=entry.data.get(
            CONF_NOTIFY_CONNECTION_ERRORS_SERVICES, DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES
        ),
        connection_error_notification_title=entry.data.get(
            CONF_CONNECTION_ERROR_NOTIFICATION_TITLE, DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE
        ),
        connection_error_delay=entry.data.get(CONF_CONNECTION_ERROR_DELAY, DEFAULT_CONNECTION_ERROR_DELAY),
        connection_quiet_enabled=entry.data.get(CONF_CONNECTION_QUIET_ENABLED, DEFAULT_QUIET_HOURS_ENABLED),
        connection_quiet_start=entry.data.get(CONF_CONNECTION_QUIET_START, DEFAULT_QUIET_HOURS_START),
        connection_quiet_end=entry.data.get(CONF_CONNECTION_QUIET_END, DEFAULT_QUIET_HOURS_END),
    )
    await hub.async_config_entry_first_refresh()
    hub.start_notifications()

    # Warnings used to be part of the alarm category, so entries created before
    # the split inherit their alarm settings.
    alarm_mobile = entry.data.get(CONF_NOTIFY_ALARMS_MOBILE, DEFAULT_NOTIFY_ALARMS_MOBILE)
    alarm_services = entry.data.get(CONF_NOTIFY_ALARMS_SERVICES, DEFAULT_NOTIFY_ALARMS_SERVICES)
    alarm_delay = entry.data.get(CONF_ALARM_DELAY, DEFAULT_ALARM_DELAY)

    alarm_monitor = AlarmMonitor(
        hass=hass,
        name=name,
        hub=hub,
        notify_alarms_mobile=alarm_mobile,
        notify_warnings_mobile=entry.data.get(CONF_NOTIFY_WARNINGS_MOBILE, alarm_mobile),
        notify_persistent=notify_persistent,
        alarm_notify_recovery=entry.data.get(CONF_ALARM_NOTIFY_RECOVERY, DEFAULT_NOTIFY_RECOVERY),
        warning_notify_recovery=entry.data.get(CONF_WARNING_NOTIFY_RECOVERY, DEFAULT_NOTIFY_RECOVERY),
        alarm_services=alarm_services,
        warning_services=entry.data.get(CONF_NOTIFY_WARNINGS_SERVICES, alarm_services),
        alarm_title=entry.data.get(CONF_ALARM_NOTIFICATION_TITLE, DEFAULT_ALARM_NOTIFICATION_TITLE),
        warning_title=entry.data.get(CONF_WARNING_NOTIFICATION_TITLE, DEFAULT_WARNING_NOTIFICATION_TITLE),
        alarm_delay=alarm_delay,
        warning_delay=entry.data.get(CONF_WARNING_DELAY, alarm_delay),
        alarm_quiet_enabled=entry.data.get(CONF_ALARM_QUIET_ENABLED, DEFAULT_QUIET_HOURS_ENABLED),
        alarm_quiet_start=entry.data.get(CONF_ALARM_QUIET_START, DEFAULT_QUIET_HOURS_START),
        alarm_quiet_end=entry.data.get(CONF_ALARM_QUIET_END, DEFAULT_QUIET_HOURS_END),
        warning_quiet_enabled=entry.data.get(
            CONF_WARNING_QUIET_ENABLED, DEFAULT_WARNING_QUIET_HOURS_ENABLED
        ),
        warning_quiet_start=entry.data.get(CONF_WARNING_QUIET_START, DEFAULT_QUIET_HOURS_START),
        warning_quiet_end=entry.data.get(CONF_WARNING_QUIET_END, DEFAULT_QUIET_HOURS_END),
    )

    firmware_version = None
    model_display = None
    serial_number = None
    if isinstance(hub.data, dict):
        firmware_version = hub.data.get("firmware_version")
        # A model or orientation register that is not in the enum mapping falls
        # back to its raw numeric value, so cast before joining.
        model_parts = ["ComfoAir", hub.data.get("112"), hub.data.get("111")]
        model_display = " ".join(str(p) for p in model_parts if p not in (None, "")) or None
        serial_number = hub.data.get("serial_number")

    hass.data[DOMAIN][name] = {
        "hub": hub,
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
