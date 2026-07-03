"""Alarm monitoring for the ComfoAir integration."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.persistent_notification import async_create as create_persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import (
    ALARM_BITS,
    DOMAIN,
    GATED_WARNING_KEYS,
    WARNING_QUIET_HOUR_END,
    WARNING_QUIET_HOUR_START,
    alarm_data_key,
)

_LOGGER = logging.getLogger(__name__)

_DESCRIPTIONS: dict[str, str] = {
    alarm_data_key(reg_str, bit_pos): description
    for reg_str, bits in ALARM_BITS.items()
    for bit_pos, description in bits
}
_DESCRIPTIONS["supply_condensation_alarm"] = "condensation alarm"

ALL_ALARM_KEYS: set[str] = set(_DESCRIPTIONS)


class AlarmMonitor:
    """Monitor ComfoAir alarm/warning bits and send notifications."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        hub,
        notify_alarms_mobile: bool = False,
        notify_alarms_persistent: bool = False,
        notify_services: str = "",
        notification_title: str = "ComfoAir in storing!",
        alarm_delay: int = 60,
    ) -> None:
        """Initialize the alarm monitor."""
        self.hass = hass
        self.name = name
        self._hub = hub
        self._notify_alarms_mobile = notify_alarms_mobile
        self._notify_alarms_persistent = notify_alarms_persistent
        self._notify_services = (
            [s.strip() for s in notify_services.split(",") if s.strip()] if notify_services else []
        )
        self._notification_title = notification_title
        self._alarm_delay = alarm_delay
        self._active: dict[str, bool] = {}
        self._pending_gated: set[str] = set()
        self._remove_listener = None
        self._remove_quiet_hour_trigger = None

    def start_monitoring(self) -> None:
        """Start monitoring hub data updates for alarm bit transitions."""
        if not self._notify_alarms_mobile and not self._notify_alarms_persistent:
            _LOGGER.debug("Alarm notifications disabled, not starting monitor")
            return

        self._remove_listener = self._hub.async_add_listener(self._handle_hub_update)
        self._remove_quiet_hour_trigger = async_track_time_change(
            self.hass,
            self._flush_pending_gated,
            hour=WARNING_QUIET_HOUR_END,
            minute=0,
            second=0,
        )
        _LOGGER.info("Started ComfoAir alarm monitoring for %s", self.name)

    @callback
    def _handle_hub_update(self) -> None:
        data = self._hub.data
        if not isinstance(data, dict):
            return

        for key in ALL_ALARM_KEYS:
            new_value = data.get(key)
            if new_value is None:
                continue
            new_value = bool(new_value)
            old_value = self._active.get(key)
            self._active[key] = new_value

            if old_value is False and new_value is True:
                self.hass.loop.call_later(
                    self._alarm_delay,
                    lambda k=key: self.hass.async_create_task(self._maybe_notify(k)),
                )
                _LOGGER.debug("%s triggered, will notify after %ss", key, self._alarm_delay)
            elif old_value is True and new_value is False:
                self._pending_gated.discard(key)
                _LOGGER.debug("%s cleared", key)

    async def _maybe_notify(self, key: str) -> None:
        """Send the notification if the alarm/warning is still active after the delay.

        The persistent notification is never time-gated (it doesn't wake anyone up).
        Only the mobile push for the two "warning" bits is held outside 07:00-23:00,
        since that's the one that would wake you up for a non-urgent warning.
        """
        data = self._hub.data
        if not isinstance(data, dict) or not data.get(key):
            _LOGGER.debug("%s was cleared before the notification delay elapsed", key)
            return

        description = _DESCRIPTIONS.get(key, key)
        message = f"{self.name} {description}"

        if self._notify_alarms_persistent:
            self._send_persistent(key, message)

        if self._notify_alarms_mobile:
            if key in GATED_WARNING_KEYS and not self._in_notification_window():
                self._pending_gated.add(key)
                _LOGGER.debug(
                    "%s mobile notification held until %02d:00 (outside %02d:00-%02d:00 window)",
                    key,
                    WARNING_QUIET_HOUR_END,
                    WARNING_QUIET_HOUR_END,
                    WARNING_QUIET_HOUR_START,
                )
            else:
                await self._send_mobile(message)

    @staticmethod
    def _in_notification_window() -> bool:
        hour = datetime.now().hour
        return WARNING_QUIET_HOUR_END <= hour < WARNING_QUIET_HOUR_START

    @callback
    def _flush_pending_gated(self, _now) -> None:
        """Send any mobile warning notifications that were held overnight."""
        if not self._pending_gated:
            return

        data = self._hub.data
        pending = list(self._pending_gated)
        self._pending_gated.clear()

        for key in pending:
            if isinstance(data, dict) and data.get(key):
                description = _DESCRIPTIONS.get(key, key)
                self.hass.async_create_task(self._send_mobile(f"{self.name} {description}"))

    def _send_persistent(self, key: str, message: str) -> None:
        create_persistent_notification(
            self.hass, message, self._notification_title, f"{DOMAIN}_{self.name}_{key}"
        )

    async def _send_mobile(self, message: str) -> None:
        for service_name in self._notify_services:
            try:
                await self.hass.services.async_call(
                    "notify",
                    service_name,
                    {"title": self._notification_title, "message": message},
                )
                _LOGGER.debug("Sent mobile notification to %s", service_name)
            except Exception as err:
                _LOGGER.error("Failed to send notification to %s: %s", service_name, err)

    def stop_monitoring(self) -> None:
        """Stop monitoring hub data updates."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        if self._remove_quiet_hour_trigger is not None:
            self._remove_quiet_hour_trigger()
            self._remove_quiet_hour_trigger = None
        _LOGGER.debug("Stopped ComfoAir alarm monitoring for %s", self.name)
