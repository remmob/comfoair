"""Binary sensors for ComfoAir Modbus."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import CONF_NAME
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALARM_BITS, DOMAIN, GATED_WARNING_KEYS, alarm_data_key


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up binary sensor platform from config entry."""
    hub_name = entry.data[CONF_NAME]
    hub = hass.data[DOMAIN][hub_name]["hub"]
    device_info = hass.data[DOMAIN][hub_name]["device_info"]

    entities: list = [SupplyCondensationAlarmSensor(hub_name, hub, device_info)]
    for reg_str, bits in ALARM_BITS.items():
        for bit_pos, description in bits:
            entities.append(AlarmBitSensor(hub_name, hub, device_info, reg_str, bit_pos, description))

    async_add_entities(entities)


class SupplyCondensationAlarmSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that triggers when supply air dewpoint approaches room temperature."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_icon = "mdi:water-alert"

    def __init__(self, platform_name, hub, device_info) -> None:
        self._platform_name = platform_name
        self._attr_device_info = device_info
        super().__init__(coordinator=hub)

    @property
    def name(self):
        return f"{self._platform_name} condensation alarm"

    @property
    def unique_id(self):
        return f"{self._platform_name}_supply_condensation_alarm"

    @property
    def is_on(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("supply_condensation_alarm")

    @property
    def state(self) -> str | None:
        val = self.is_on
        if val is None:
            return None
        return "warning" if val else "no warning"


class AlarmBitSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for a single bit in an alarm bitmask register."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(self, platform_name, hub, device_info, reg_str, bit_pos, description) -> None:
        self._platform_name = platform_name
        self._attr_device_info = device_info
        self._data_key = alarm_data_key(reg_str, bit_pos)
        self._description = description
        super().__init__(coordinator=hub)

    @property
    def name(self):
        return f"{self._platform_name} {self._description}"

    @property
    def unique_id(self):
        return f"{self._platform_name}_{self._data_key}"

    @property
    def is_on(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._data_key)

    @property
    def state(self) -> str | None:
        val = self.is_on
        if val is None:
            return None
        if self._data_key in GATED_WARNING_KEYS:
            return "warning" if val else "no warning"
        return "alarm" if val else "no alarm"
