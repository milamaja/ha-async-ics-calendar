"""Calendar entities for Async ICS Calendar.

Calendars are set up in the UI. A YAML `calendar:` platform entry is imported
into a config entry once, keeping its entity, and Home Assistant shows a
repair asking to remove the YAML.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import voluptuous as vol

from homeassistant.components.calendar import (
    PLATFORM_SCHEMA as CALENDAR_PLATFORM_SCHEMA,
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL, CONF_URL
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from . import AsyncIcsConfigEntry
from .const import (
    CONF_DAYS_BACKWARD,
    CONF_DAYS_FORWARD,
    CONF_REFRESH_MINUTES,
    DEFAULT_DAYS_BACKWARD,
    DEFAULT_DAYS_FORWARD,
    DEFAULT_NAME,
    DEFAULT_REFRESH_MINUTES,
    DOMAIN,
    TITLE,
)
from .coordinator import AsyncIcsCalendarCoordinator, as_aware

PLATFORM_SCHEMA = CALENDAR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=timedelta(minutes=DEFAULT_REFRESH_MINUTES)
        ): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_DAYS_BACKWARD, default=DEFAULT_DAYS_BACKWARD): vol.Coerce(int),
        vol.Optional(CONF_DAYS_FORWARD, default=DEFAULT_DAYS_FORWARD): vol.Coerce(int),
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import a YAML calendar into a config entry; the entry creates the entity."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_URL: config[CONF_URL],
            CONF_NAME: config[CONF_NAME],
            CONF_REFRESH_MINUTES: max(1, round(config[CONF_SCAN_INTERVAL].total_seconds() / 60)),
            CONF_DAYS_BACKWARD: config[CONF_DAYS_BACKWARD],
            CONF_DAYS_FORWARD: config[CONF_DAYS_FORWARD],
        },
    )
    if result["type"] is FlowResultType.CREATE_ENTRY or result.get("reason") == "already_configured":
        ir.async_create_issue(
            hass,
            HOMEASSISTANT_DOMAIN,
            f"deprecated_yaml_{DOMAIN}",
            breaks_in_ha_version=None,
            is_fixable=False,
            is_persistent=False,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={"domain": DOMAIN, "integration_title": TITLE},
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AsyncIcsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the calendar entity of a config entry."""
    async_add_entities([AsyncIcsCalendarEntity(entry.runtime_data, entry)])


class AsyncIcsCalendarEntity(CoordinatorEntity[AsyncIcsCalendarCoordinator], CalendarEntity):
    """Calendar entity backed by the parsed ICS feed."""

    def __init__(self, coordinator: AsyncIcsCalendarCoordinator, entry: AsyncIcsConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = entry.data.get(CONF_NAME, entry.title)
        # The same id the YAML platform used, so an imported calendar keeps
        # its entity (and entity id). It stays when the URL is changed later.
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}"

    @property
    def event(self) -> CalendarEvent | None:
        events = self.coordinator.data or []
        now = dt_util.now()
        for evt in events:
            if as_aware(evt.start) <= now < as_aware(evt.end):
                return evt
        for evt in events:
            if as_aware(evt.start) > now:
                return evt
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = self.coordinator.data or []
        return [
            evt
            for evt in events
            if as_aware(evt.start) < end_date and as_aware(evt.end) > start_date
        ]
