"""Async ICS Calendar platform for Home Assistant.

Fetches an ICS/iCalendar feed and parses it with `icalendar` +
`recurring_ical_events`, keeping the (potentially slow) parse off the event
loop by running it in an executor thread.

Home Assistant's built-in `remote_calendar` integration parses ICS
synchronously inside the event loop via `IcsCalendarStream.calendar_from_ics()`,
which is a known upstream bug that can block Home Assistant's entire event
loop for several seconds on large or slow feeds:
  - https://github.com/home-assistant/core/issues/155008
  - https://github.com/home-assistant/core/issues/159051
  - https://github.com/home-assistant/core/issues/148315

This integration avoids that class of bug entirely by doing all ICS parsing
and RRULE expansion in a worker thread via `hass.async_add_executor_job()`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import logging

import aiohttp
import icalendar
import recurring_ical_events
import voluptuous as vol

from homeassistant.components.calendar import (
    PLATFORM_SCHEMA,
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
import homeassistant.util.dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "ICS Calendar"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=15)

CONF_DAYS_BACKWARD = "days_backward"
CONF_DAYS_FORWARD = "days_forward"
DEFAULT_DAYS_BACKWARD = 3
DEFAULT_DAYS_FORWARD = 60

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            cv.time_period, cv.positive_timedelta
        ),
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
    """Set up the Async ICS Calendar platform from YAML."""
    url = config[CONF_URL]
    coordinator = AsyncIcsCalendarCoordinator(
        hass,
        url,
        scan_interval=config[CONF_SCAN_INTERVAL],
        days_backward=config[CONF_DAYS_BACKWARD],
        days_forward=config[CONF_DAYS_FORWARD],
    )
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise PlatformNotReady(
            f"Initial fetch of ICS feed failed: {coordinator.last_exception}"
        )
    async_add_entities([AsyncIcsCalendarEntity(coordinator, config[CONF_NAME], url)])


def _as_aware(value: date | datetime) -> datetime:
    """Normalize a date/datetime to an aware local datetime for comparisons."""
    if isinstance(value, datetime):
        return dt_util.as_local(value) if value.tzinfo is None else value
    return dt_util.start_of_local_day(value)


def _parse_and_expand(
    raw_ics: bytes, window_start: datetime, window_end: datetime
) -> list[CalendarEvent]:
    """Parse ICS bytes and expand recurrences for a window. Runs in executor."""
    calendar = icalendar.Calendar.from_ical(raw_ics)
    occurrences = recurring_ical_events.of(calendar).between(window_start, window_end)

    events: list[CalendarEvent] = []
    for comp in occurrences:
        start = comp["DTSTART"].dt
        dtend = comp.get("DTEND")
        if dtend is not None:
            end = dtend.dt
        else:
            duration = comp.get("DURATION")
            end = (start + duration.dt) if duration is not None else start

        events.append(
            CalendarEvent(
                start=start,
                end=end,
                summary=str(comp.get("SUMMARY", "")),
                description=str(comp.get("DESCRIPTION")) if comp.get("DESCRIPTION") else None,
                location=str(comp.get("LOCATION")) if comp.get("LOCATION") else None,
                uid=str(comp.get("UID")) if comp.get("UID") else None,
            )
        )

    events.sort(key=lambda e: _as_aware(e.start))
    return events


class AsyncIcsCalendarCoordinator(DataUpdateCoordinator[list[CalendarEvent]]):
    """Fetch the ICS feed and keep parsing off the event loop."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        *,
        scan_interval: timedelta,
        days_backward: int,
        days_forward: int,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=scan_interval)
        self._url = url
        self._lookback = timedelta(days=days_backward)
        self._lookahead = timedelta(days=days_forward)
        self._session = aiohttp.ClientSession()

        async def _close_session(_event: Event) -> None:
            await self._session.close()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _close_session)

    async def _async_update_data(self) -> list[CalendarEvent]:
        try:
            async with self._session.get(self._url, timeout=FETCH_TIMEOUT) as resp:
                resp.raise_for_status()
                raw = await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching ICS feed: {err}") from err

        now = dt_util.now()
        window_start = now - self._lookback
        window_end = now + self._lookahead

        try:
            return await self.hass.async_add_executor_job(
                _parse_and_expand, raw, window_start, window_end
            )
        except UpdateFailed:
            raise
        except Exception as err:  # noqa: BLE001 - surface parser errors clearly
            raise UpdateFailed(f"Error parsing ICS feed: {err}") from err


class AsyncIcsCalendarEntity(CoordinatorEntity[AsyncIcsCalendarCoordinator], CalendarEntity):
    """Calendar entity backed by the parsed ICS feed."""

    def __init__(self, coordinator: AsyncIcsCalendarCoordinator, name: str, url: str) -> None:
        super().__init__(coordinator)
        self._attr_name = name
        url_hash = hashlib.sha1(url.encode()).hexdigest()[:12]
        self._attr_unique_id = f"{DOMAIN}_{url_hash}"

    @property
    def event(self) -> CalendarEvent | None:
        events = self.coordinator.data or []
        now = dt_util.now()
        for evt in events:
            if _as_aware(evt.start) <= now < _as_aware(evt.end):
                return evt
        for evt in events:
            if _as_aware(evt.start) > now:
                return evt
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = self.coordinator.data or []
        return [
            evt
            for evt in events
            if _as_aware(evt.start) < end_date and _as_aware(evt.end) > start_date
        ]
