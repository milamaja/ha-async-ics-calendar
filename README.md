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
- Configurable poll interval and event-window size.
- Multiple calendars: just add multiple platform entries.

## Installation

### Via HACS (custom repository)

This integration is not in the default HACS store. Add it as a custom
repository:

1. HACS → Integrations → ⋮ (top right) → **Custom repositories**.
2. Repository: `https://github.com/milamaja/ha-async-ics-calendar`,
   Category: **Integration**.
3. Install "Async ICS Calendar" from HACS, then restart Home Assistant.

### Manual

1. Copy `custom_components/async_ics_calendar/` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

This integration is YAML-only (no config flow / UI setup). Add it under the
`calendar:` key in `configuration.yaml`:

```yaml
calendar:
  - platform: async_ics_calendar
    url: "https://example.com/path/to/calendar.ics"
    name: "Family"
```

### Options

| Key             | Required | Default        | Description                                             |
| --------------- | -------- | -------------- | -------------------------------------------------------- |
| `url`           | yes      | n/a            | The ICS feed URL.                                        |
| `name`          | no       | `ICS Calendar` | Friendly name for the calendar entity.                   |
| `scan_interval` | no       | `00:15:00`     | How often to re-fetch and re-parse the feed.              |
| `days_backward` | no       | `3`            | How many days in the past to keep one-off events for.     |
| `days_forward`  | no       | `60`           | How many days ahead to expand recurring events to.        |

Multiple calendars are just multiple entries:

```yaml
calendar:
  - platform: async_ics_calendar
    name: "Work"
    url: "https://example.com/work.ics"
  - platform: async_ics_calendar
    name: "Family"
    url: "https://example.com/family.ics"
    scan_interval: "00:30:00"
    days_forward: 90
```

## Limitations

- YAML configuration only, there's no config flow / UI setup screen (see
  [Contributing](#contributing) if you'd like to add one).
- Read-only: this integration doesn't support creating or editing events.
- If your feed is large or slow enough that even a 15-second HTTP fetch
  times out, requests will fail until the server responds faster, consider
  a caching proxy in front of the feed for that case.

## Contributing

Issues and PRs welcome. A config-flow (UI-configurable) version would be a
reasonable enhancement if there's interest.

## License

[MIT](LICENSE)
