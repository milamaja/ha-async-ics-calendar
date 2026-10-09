"""Fetch an ICS feed and parse it off the event loop.

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

from homeassistant.components.calendar import CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FETCH_TIMEOUT = aiohttp.ClientTimeout(total=15)


def url_hash(url: str) -> str:
    """A stable id for a feed URL, without revealing it (URLs often hold a token)."""
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def _describe(err: Exception) -> str:
    """An error description that never contains the feed URL."""
    if isinstance(err, aiohttp.ClientResponseError):
        return f"HTTP {err.status}"
    if isinstance(err, TimeoutError):
        return "timed out"
    return type(err).__name__


def as_aware(value: date | datetime) -> datetime:
    """Normalize a date/datetime to an aware local datetime for comparisons."""
    if isinstance(value, datetime):
        return dt_util.as_local(value) if value.tzinfo is None else value
    return dt_util.start_of_local_day(value)


def parse_and_expand(
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

    events.sort(key=lambda e: as_aware(e.start))
    return events


def _check_ics(raw_ics: bytes) -> None:
    """Raise when the bytes are not an ICS calendar. Runs in executor."""
    calendar = icalendar.Calendar.from_ical(raw_ics)
    if calendar.name != "VCALENDAR":
        raise ValueError("not a VCALENDAR")


async def async_fetch(hass: HomeAssistant, url: str) -> bytes:
    """Download a feed; raises UpdateFailed without the URL in the message."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, timeout=FETCH_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.read()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise UpdateFailed(f"Error fetching ICS feed: {_describe(err)}") from err


async def async_validate(hass: HomeAssistant, url: str) -> str | None:
    """Check a feed URL for the config flow; returns an error key or None."""
    try:
        raw = await async_fetch(hass, url)
    except UpdateFailed:
        return "cannot_connect"
    try:
        await hass.async_add_executor_job(_check_ics, raw)
    except Exception:  # noqa: BLE001 - any parser error means "not a calendar"
        return "invalid_ics"
    return None


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

    async def _async_update_data(self) -> list[CalendarEvent]:
        raw = await async_fetch(self.hass, self._url)
        now = dt_util.now()
        try:
            return await self.hass.async_add_executor_job(
                parse_and_expand, raw, now - self._lookback, now + self._lookahead
            )
        except Exception as err:  # noqa: BLE001 - surface parser errors clearly
            raise UpdateFailed(f"Error parsing ICS feed: {_describe(err)}") from err
