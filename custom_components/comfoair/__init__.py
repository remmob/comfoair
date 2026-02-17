"""The ComfoAir Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_COPYRIGHT,
    ATTR_MANUFACTURER,
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_CONTROL_TYPE,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_MODE,
    CONF_PARITY,
    CONF_STOPBITS,
    CONTROL_TYPE_MANUAL,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_DEVICE_ID,
    DEFAULT_PARITY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOPBITS,
    DOMAIN,
    PLATFORMS,
)
from .hub import ComfoAirHub

_LOGGER = logging.getLogger(__name__)


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

    hub = ComfoAirHub(
        hass=hass,
        name=name,
        scan_interval=scan_interval,
        mode=mode,
        device_id=entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID),
        host=entry.data.get(CONF_HOST),
        port=entry.data.get(CONF_PORT),
        device=entry.data.get(CONF_DEVICE),
        baudrate=entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        bytesize=entry.data.get(CONF_BYTESIZE, DEFAULT_BYTESIZE),
        parity=entry.data.get(CONF_PARITY, DEFAULT_PARITY),
        stopbits=entry.data.get(CONF_STOPBITS, DEFAULT_STOPBITS),
    )
    await hub.async_config_entry_first_refresh()

    firmware_version = None
    if isinstance(hub.data, dict):
        firmware_version = hub.data.get("firmware_version")

    hass.data[DOMAIN][name] = {
        "hub": hub,
        "mode": mode,
        "device_info": {
            "identifiers": {(DOMAIN, name)},
            "name": name,
            "model": ATTR_MANUFACTURER,
            "manufacturer": ATTR_COPYRIGHT,
            "sw_version": firmware_version,
        },
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        item = hass.data[DOMAIN].pop(entry.data[CONF_NAME])
        hub: ComfoAirHub = item["hub"]
        hub.close()
    return unload_ok
