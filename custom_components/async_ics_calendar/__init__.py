"""Async ICS Calendar: a calendar from any ICS/iCalendar URL, parsed off the event loop."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_DAYS_BACKWARD,
    CONF_DAYS_FORWARD,
    CONF_REFRESH_MINUTES,
    DEFAULT_DAYS_BACKWARD,
    DEFAULT_DAYS_FORWARD,
    DEFAULT_REFRESH_MINUTES,
)
from .coordinator import AsyncIcsCalendarCoordinator

PLATFORMS = [Platform.CALENDAR]

type AsyncIcsConfigEntry = ConfigEntry[AsyncIcsCalendarCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AsyncIcsConfigEntry) -> bool:
    """Set up one calendar feed."""
    options = entry.options
    coordinator = AsyncIcsCalendarCoordinator(
        hass,
        entry.data[CONF_URL],
        scan_interval=timedelta(
            minutes=options.get(CONF_REFRESH_MINUTES, DEFAULT_REFRESH_MINUTES)
        ),
        days_backward=options.get(CONF_DAYS_BACKWARD, DEFAULT_DAYS_BACKWARD),
        days_forward=options.get(CONF_DAYS_FORWARD, DEFAULT_DAYS_FORWARD),
    )
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady(str(coordinator.last_exception))
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: AsyncIcsConfigEntry) -> None:
    """Apply changed options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AsyncIcsConfigEntry) -> bool:
    """Unload a calendar feed."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
