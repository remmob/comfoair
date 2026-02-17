"""Sensors for ComfoAir Modbus."""

from __future__ import annotations
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_NAME
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CONTROL_TYPE,
    CONTROL_TYPE_SENSOR_KEYS,
    CONTROL_TYPE_SENSOR_KEYS_BY_TYPE,
    DEFAULT_CONTROL_TYPE,
    DOMAIN,
    SENSOR_TYPES,
    ComfoAirModbusSensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up sensor platform from config entry."""
    hub_name = entry.data[CONF_NAME]
    hub = hass.data[DOMAIN][hub_name]["hub"]
    device_info = hass.data[DOMAIN][hub_name]["device_info"]
    selected_control_type = entry.data.get(CONF_CONTROL_TYPE, DEFAULT_CONTROL_TYPE)
    active_control_sensor_keys = CONTROL_TYPE_SENSOR_KEYS_BY_TYPE.get(
        selected_control_type,
        CONTROL_TYPE_SENSOR_KEYS_BY_TYPE[DEFAULT_CONTROL_TYPE],
    )

    entities = []
    for sensor_description in SENSOR_TYPES.values():
        sensor_key = sensor_description.key
        enabled_default = True
        if sensor_key in CONTROL_TYPE_SENSOR_KEYS:
            enabled_default = sensor_key in active_control_sensor_keys

        entities.append(
            ComfoAirSensor(
                hub_name,
                hub,
                device_info,
                sensor_description,
                enabled_default,
            )
        )
    async_add_entities(entities)

    entity_registry = er.async_get(hass)
    for sensor_key in CONTROL_TYPE_SENSOR_KEYS:
        unique_id = f"{hub_name}_{sensor_key}"
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id is None:
            continue

        if sensor_key in active_control_sensor_keys:
            entity_registry.async_update_entity(entity_id, disabled_by=None)
        else:
            entity_registry.async_update_entity(
                entity_id,
                disabled_by=RegistryEntryDisabler.INTEGRATION,
            )


class ComfoAirSensor(CoordinatorEntity, SensorEntity):
    """ComfoAir sensor entity."""

    def __init__(
        self,
        platform_name,
        hub,
        device_info,
        description: ComfoAirModbusSensorEntityDescription,
        enabled_default: bool,
    ) -> None:
        self._platform_name = platform_name
        self._attr_device_info = device_info
        self.entity_description: ComfoAirModbusSensorEntityDescription = description
        self._attr_entity_registry_enabled_default = enabled_default
        super().__init__(coordinator=hub)

    @property
    def name(self):
        return f"{self._platform_name} {self.entity_description.name}"

    @property
    def unique_id(self):
        return f"{self._platform_name}_{self.entity_description.key}"

    @property
    def native_value(self):
        if self.entity_description.key not in self.coordinator.data:
            return None

        value = self.coordinator.data[self.entity_description.key]
        if value is None:
            return None

        if self.entity_description.native_min_value is not None and value < self.entity_description.native_min_value:
            _LOGGER.debug("%s: value %s below minimum %s", self.name, value, self.entity_description.native_min_value)
            return None

        if self.entity_description.native_max_value is not None and value > self.entity_description.native_max_value:
            _LOGGER.debug("%s: value %s above maximum %s", self.name, value, self.entity_description.native_max_value)
            return None

        return value
