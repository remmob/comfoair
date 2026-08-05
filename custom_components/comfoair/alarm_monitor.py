"""Alarm and warning monitoring for the ComfoAir integration.

Alarms and warnings are tracked separately: each has its own confirmation
delay, notification title, mobile notify services and quiet-hours window.
Persistent notifications are always sent immediately; mobile notifications are
routed through the matching QuietHours instance so they can be held overnight.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback

from .const import (
    ALARM_BITS,
    DEFAULT_ALARM_DELAY,
    DEFAULT_ALARM_NOTIFICATION_TITLE,
    DEFAULT_WARNING_DELAY,
    DEFAULT_WARNING_NOTIFICATION_TITLE,
    WARNING_KEYS,
    alarm_data_key,
)
from .notifications import QuietHours, parse_services, send_mobile, send_persistent

_LOGGER = logging.getLogger(__name__)

CATEGORY_ALARM = "alarm"
CATEGORY_WARNING = "warning"

_DESCRIPTIONS: dict[str, str] = {
    alarm_data_key(reg_str, bit_pos): description
    for reg_str, bits in ALARM_BITS.items()
    for bit_pos, description in bits
}
_DESCRIPTIONS["supply_condensation_alarm"] = "condensation alarm"

ALL_ALARM_KEYS: set[str] = set(_DESCRIPTIONS)


def _category(key: str) -> str:
    """Which notification category an alarm bit belongs to."""
    return CATEGORY_WARNING if key in WARNING_KEYS else CATEGORY_ALARM


class AlarmMonitor:
    """Monitor ComfoAir alarm/warning bits and send notifications."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        hub,
        notify_alarms_mobile: bool = False,
        notify_warnings_mobile: bool = False,
        notify_persistent: bool = False,
        alarm_notify_recovery: bool = True,
        warning_notify_recovery: bool = True,
        alarm_services: str = "",
        warning_services: str = "",
        alarm_title: str = DEFAULT_ALARM_NOTIFICATION_TITLE,
        warning_title: str = DEFAULT_WARNING_NOTIFICATION_TITLE,
        alarm_delay: int = DEFAULT_ALARM_DELAY,
        warning_delay: int = DEFAULT_WARNING_DELAY,
        alarm_quiet_enabled: bool = False,
        alarm_quiet_start=None,
        alarm_quiet_end=None,
        warning_quiet_enabled: bool = True,
        warning_quiet_start=None,
        warning_quiet_end=None,
    ) -> None:
        """Initialize the alarm monitor."""
        self.hass = hass
        self.name = name
        self._hub = hub
        self._notify_mobile = {
            CATEGORY_ALARM: notify_alarms_mobile,
            CATEGORY_WARNING: notify_warnings_mobile,
        }
        self._notify_persistent = notify_persistent
        self._notify_recovery = {
            CATEGORY_ALARM: alarm_notify_recovery,
            CATEGORY_WARNING: warning_notify_recovery,
        }
        self._services = {
            CATEGORY_ALARM: parse_services(alarm_services),
            CATEGORY_WARNING: parse_services(warning_services),
        }
        self._titles = {
            CATEGORY_ALARM: alarm_title,
            CATEGORY_WARNING: warning_title,
        }
        self._delays = {
            CATEGORY_ALARM: alarm_delay,
            CATEGORY_WARNING: warning_delay,
        }
        self._active: dict[str, bool] = {}
        self._notified: set[str] = set()
        self._remove_listener = None

        # A separate quiet-hours window per category.
        self._quiet = {
            CATEGORY_ALARM: QuietHours(
                hass,
                f"{name} alarm",
                alarm_quiet_enabled,
                alarm_quiet_start,
                alarm_quiet_end,
                self._mobile_sender(CATEGORY_ALARM),
            ),
            CATEGORY_WARNING: QuietHours(
                hass,
                f"{name} warning",
                warning_quiet_enabled,
                warning_quiet_start,
                warning_quiet_end,
                self._mobile_sender(CATEGORY_WARNING),
            ),
        }

    def _mobile_sender(self, category: str):
        """Return a coroutine that sends mobile notifications for this category."""

        async def _send(message: str) -> None:
            await send_mobile(
                self.hass, self._services[category], self._titles[category], message
            )

        return _send

    def _enabled(self, category: str) -> bool:
        """Whether this category notifies on any channel."""
        return self._notify_mobile[category] or self._notify_persistent

    def start_monitoring(self) -> None:
        """Start monitoring hub data updates for alarm bit transitions."""
        if not any(self._enabled(category) for category in self._quiet):
            _LOGGER.debug("Alarm notifications disabled, not starting monitor")
            return

        for category, quiet in self._quiet.items():
            if self._enabled(category):
                quiet.start()

        self._remove_listener = self._hub.async_add_listener(self._handle_hub_update)
        _LOGGER.info("Started ComfoAir alarm monitoring for %s", self.name)

    def stop_monitoring(self) -> None:
        """Stop monitoring hub data updates."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        for quiet in self._quiet.values():
            quiet.stop()
        _LOGGER.debug("Stopped ComfoAir alarm monitoring for %s", self.name)

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

            category = _category(key)
            if not self._enabled(category):
                continue

            if old_value is False and new_value is True:
                # Re-check after the configured delay to skip transient bits.
                self.hass.loop.call_later(
                    self._delays[category],
                    lambda k=key: self.hass.async_create_task(self._maybe_notify(k)),
                )
                _LOGGER.debug(
                    "%s triggered, will notify after %ss", key, self._delays[category]
                )
            elif old_value is True and new_value is False:
                self._handle_recovery(key)

    async def _maybe_notify(self, key: str) -> None:
        """Send the notification if the alarm/warning is still active after the delay."""
        data = self._hub.data
        if not isinstance(data, dict) or not data.get(key):
            _LOGGER.debug("%s was cleared before the notification delay elapsed", key)
            return

        description = _DESCRIPTIONS.get(key, key)
        self._notified.add(key)
        await self._send(key, f"{self.name} {description}")

    def _handle_recovery(self, key: str) -> None:
        """Announce that an alarm/warning cleared, if it was notified before."""
        was_notified = key in self._notified
        self._notified.discard(key)
        category = _category(key)
        # A held mobile notification is no longer relevant once the bit cleared.
        self._quiet[category].clear_held()
        _LOGGER.debug("%s cleared", key)

        if not self._notify_recovery[category] or not was_notified:
            return

        description = _DESCRIPTIONS.get(key, key)
        self.hass.async_create_task(
            self._send(key, f"{self.name} {description} hersteld")
        )

    async def _send(self, key: str, message: str) -> None:
        """Persistent immediately, mobile through the category's quiet hours."""
        category = _category(key)
        if self._notify_persistent:
            send_persistent(
                self.hass, self.name, message, self._titles[category], key
            )
        if self._notify_mobile[category]:
            await self._quiet[category].deliver(message)
