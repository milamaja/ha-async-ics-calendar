# Async ICS Calendar for Home Assistant

A minimal `calendar` platform that fetches a plain ICS/iCalendar URL and
parses it **without blocking Home Assistant's event loop**.

## Why this exists

Home Assistant ships a built-in [`remote_calendar`](https://www.home-assistant.io/integrations/remote_calendar/)
integration that does the same basic job, but its ICS parsing
(`IcsCalendarStream.calendar_from_ics()`) runs synchronously *inside* the
event loop. On a slow feed or a large calendar, this can stall the entire
Home Assistant instance for several seconds, other integrations stop
responding, physical switches lag, dashboards freeze, every time the
calendar refreshes. This is a known, still-open upstream bug:

- https://github.com/home-assistant/core/issues/155008
- https://github.com/home-assistant/core/issues/159051
- https://github.com/home-assistant/core/issues/148315
- https://github.com/home-assistant/core/issues/143141

This integration fetches the feed asynchronously with `aiohttp` and does all
ICS parsing / recurrence (RRULE) expansion in a worker thread via
`hass.async_add_executor_job()`, using the well-established
[`icalendar`](https://pypi.org/project/icalendar/) and
[`recurring-ical-events`](https://pypi.org/project/recurring-ical-events/)
libraries. The event loop is never touched by the parse.

## Features

- Works with any public or token-protected ICS URL (Google Calendar,
  Outlook/Office 365, Nextcloud, Fastmail, etc., anything that serves a
  standard `.ics` feed).
- Full RRULE/RDATE/EXDATE recurrence expansion.
- Set up and changed in the UI: refresh interval and event window per calendar.
- Multiple calendars: add the integration once per calendar.

<p><img src="https://raw.githubusercontent.com/milamaja/ha-async-ics-calendar/master/images/calendar.png" width="800" alt="Home Assistant's calendar card with two ICS calendars: an autumn holiday, a study day, weekly trainings and matches"></p>

## Installation

### Via HACS (custom repository)

This integration is not in the default HACS store. The button opens it in
HACS (it uses [My Home Assistant](https://www.home-assistant.io/integrations/my/), which is on by default):

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=milamaja&repository=ha-async-ics-calendar&category=integration)

Or add it as a custom repository by hand:

1. HACS → Integrations → ⋮ (top right) → **Custom repositories**.
2. Repository: `https://github.com/milamaja/ha-async-ics-calendar`,
   Category: **Integration**.
3. Install "Async ICS Calendar" from HACS, then restart Home Assistant.

### Manual

1. Copy `custom_components/async_ics_calendar/` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up Async ICS Calendar.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=async_ics_calendar)

Or go to **Settings, Devices & services, Add integration** and search for
**Async ICS Calendar**. Fill in:

- **Name**: the name of the calendar entity, for example `Family`.
- **ICS address (URL)**: the address of the `.ics` feed, such as the secret
  address of a Google, Outlook or Nextcloud calendar. It is checked once
  before the calendar is added, and never written to the log.

<p><img src="https://raw.githubusercontent.com/milamaja/ha-async-ics-calendar/master/images/add-form.png" width="460" alt="The Add an ICS calendar form with a name and an ICS address"></p>

Add the integration again for each calendar.

### Settings

Under **Settings, Devices & services, Async ICS Calendar**, click the gear of a
calendar to change:

| Setting               | Default    | Description                                                   |
| --------------------- | ---------- | ------------------------------------------------------------- |
| Refresh every         | 15 minutes | How often the feed is downloaded and parsed again.            |
| Keep past events for  | 3 days     | Days in the past that events stay available.                  |
| Show events up to     | 60 days    | Days ahead that events, including repeating events, are shown. |

To change the name or the address of a calendar, choose **Reconfigure** in its
menu (three dots). The calendar entity stays the same.

### Coming from YAML

Earlier versions were set up in `configuration.yaml`:

```yaml
calendar:
  - platform: async_ics_calendar
    url: "https://example.com/path/to/calendar.ics"
    name: "Family"
```

These calendars are taken over automatically at the next restart, with their
settings and their entity ids, so dashboards and automations keep working.
Home Assistant then shows a repair: remove the `async_ics_calendar` entries
from `configuration.yaml` and restart once more.

## Limitations

- Read-only: this integration doesn't support creating or editing events.
- If your feed is large or slow enough that even a 15-second HTTP fetch
  times out, requests will fail until the server responds faster, consider
  a caching proxy in front of the feed for that case.

## Contributing

Issues and PRs welcome.

## License

[MIT](LICENSE)
