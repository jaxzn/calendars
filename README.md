# Calendars

Free, auto-updating, subscribable sports calendars hosted on GitHub Pages.

## Football (NFL)

**Subscribe page: https://jaxzn.github.io/calendars/football/**

- One calendar per team, all 32 teams (e.g. `hou.ics` for the Houston Texans)
- `primetime.ics`: every prime-time / national-window game (Thursday, Sunday and
  Monday night, Saturday, holiday and international national windows) plus all
  playoff games

Each game shows as `Away @ Home (TV)` with a 3-hour block, the TV channel and venue
in the description, and (after the game) the final score. Kickoffs are stored in UTC,
so every calendar app shows them in your own time zone. Games whose date/time hasn't
been set yet (late-season flex games, Week 18) appear as all-day placeholders and
move to the right slot once the NFL schedules them. Playoff games appear as their
slots are announced and join a team's calendar once that team is in the game.

### How to subscribe

Use the links on the subscribe page, or add a URL like
`https://jaxzn.github.io/calendars/football/hou.ics` yourself:

- **Apple Calendar (iPhone/iPad/Mac):** tap *Subscribe* (a `webcal://` link), or on a Mac
  *File → New Calendar Subscription…* and paste the URL. Pick iCloud to sync all devices.
- **Google Calendar:** on the web, *Other calendars → + → From URL*, paste the `https://` URL.
- **Outlook:** *Add calendar → Subscribe from web* (Outlook.com / Microsoft 365) or
  *Add Calendar → From Internet* (classic Outlook).

Subscribe instead of importing a downloaded file, otherwise you won't get updates.
Calendar apps decide how often to refresh; the feeds ask for every 6 hours, but Google
can take up to a day to show a change.

### How it works

`football/generate.py` (Python 3 standard library only) pulls ESPN's public scoreboard
feed for regular-season weeks 1–18 and the postseason, auto-detects the season, and
writes `docs/football/*.ics` and `docs/football/index.html`. Files are only rewritten
when the schedule actually changes, and if any request fails the script exits non-zero
without touching existing files. `.github/workflows/football.yml` runs it daily (and every
6 hours on Sundays, Mondays and Thursdays during the season) and commits any changes.

Run locally:

```sh
python3 football/generate.py            # current season
python3 football/generate.py --season 2026
```

To host somewhere else, change `BASE_URL` at the top of `football/generate.py`
(or set the `CAL_BASE_URL` environment variable).

GitHub Pages setup: *Settings → Pages → Deploy from a branch → `main` / `docs`*.

### Data source and disclaimer

Schedule data comes from ESPN's public (undocumented) scoreboard API at
`site.api.espn.com`. This project is unofficial and is not affiliated with, endorsed
by, or connected to the National Football League, any NFL team, or ESPN. Team names
are trademarks of their owners. Schedules change; confirm kickoff times with an
official source. Provided as-is with no warranty.
