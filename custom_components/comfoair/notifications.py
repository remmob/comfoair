"""Shared notification helpers for the ComfoAir integration.

Persistent notifications are delivered immediately and are never held. Mobile
notifications can be routed through a :class:`QuietHours` instance, which holds
them during a configured period and releases them once that period ends.

Connection errors, alarms and warnings each own an independent QuietHours, so
their quiet windows can be configured separately.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time

from homeassistant.components.persistent_notification import (
    async_create as create_persistent_notification,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import DEFAULT_QUIET_HOURS_START, DOMAIN

_LOGGER = logging.getLogger(__name__)


def parse_services(value) -> list[str]:
    """Turn a stored comma-separated string (or list) into a list of services."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def parse_time(value, fallback: str = DEFAULT_QUIET_HOURS_START) -> time:
    """Parse a "HH:MM" or "HH:MM:SS" string into a time object."""
    for candidate in (value, fallback):
        if isinstance(candidate, str):
            parts = candidate.split(":")
            try:
                return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
            except (ValueError, IndexError):
                _LOGGER.warning("Invalid time value: %s", candidate)
    return time(0, 0)


def send_persistent(
    hass: HomeAssistant, name: str, message: str, title: str, kind: str
) -> None:
    """Create (or replace) a persistent notification for this device + kind."""
    create_persistent_notification(hass, message, title, f"{DOMAIN}_{name}_{kind}")


async def send_mobile(
    hass: HomeAssistant, services: list[str], title: str, message: str
) -> None:
    """Deliver a message to every configured mobile notify service."""
    for service_name in services:
        try:
            await hass.services.async_call(
                "notify", service_name, {"title": title, "message": message}
            )
            _LOGGER.debug("Sent mobile notification to %s", service_name)
        except Exception as err:  # noqa: BLE001 - one bad service must not stop the rest
            _LOGGER.error("Failed to send notification to %s: %s", service_name, err)


class QuietHours:
    """Hold a category's mobile notifications during a quiet period.

    Only the mobile delivery (``send_mobile`` callback) is deferred; persistent
    notifications are sent by the caller regardless. One message is held at a
    time - the most recent one wins.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        label: str,
        enabled: bool,
        start,
        end,
        send_mobile: Callable[[str], Awaitable[None]],
    ) -> None:
        self.hass = hass
        self._label = label
        self._enabled = bool(enabled)
        self._start = parse_time(start)
        self._end = parse_time(end)
        self._send_mobile = send_mobile
        self._held_message: str | None = None
        self._remove_trigger = None

    def start(self) -> None:
        """Register the trigger that releases a held notification at quiet-end."""
        if not self._enabled or self._remove_trigger is not None:
            return
        self._remove_trigger = async_track_time_change(
            self.hass,
            self._release,
            hour=self._end.hour,
            minute=self._end.minute,
            second=0,
        )
        _LOGGER.debug(
            "Quiet hours for %s active between %s and %s",
            self._label,
            self._start.strftime("%H:%M"),
            self._end.strftime("%H:%M"),
        )

    def stop(self) -> None:
        """Remove the release trigger."""
        if self._remove_trigger is not None:
            self._remove_trigger()
            self._remove_trigger = None

    def in_quiet_hours(self, moment: datetime | None = None) -> bool:
        """Whether the given moment (default: now) falls inside the quiet period."""
        if not self._enabled:
            return False
        now = (moment or datetime.now()).time()
        if self._start == self._end:
            return False
        if self._start < self._end:
            return self._start <= now < self._end
        # Period runs across midnight, e.g. 23:00 - 07:00.
        return now >= self._start or now < self._end

    def clear_held(self) -> None:
        """Drop a held message, e.g. because the situation resolved meanwhile."""
        self._held_message = None

    async def deliver(self, message: str) -> None:
        """Send the mobile notification now, or hold it until quiet-end."""
        if self.in_quiet_hours():
            self._held_message = message
            _LOGGER.debug(
                "Holding mobile notification for %s until %s (quiet hours)",
                self._label,
                self._end.strftime("%H:%M"),
            )
            return
        await self._send_mobile(message)

    @callback
    def _release(self, _now) -> None:
        """Deliver the message that was held during the quiet period."""
        if self._held_message is None:
            return
        message = self._held_message
        self._held_message = None
        self.hass.async_create_task(self._send_mobile(message))
