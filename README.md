# Calendars

Free, auto-updating, subscribable sports calendars hosted on GitHub Pages.

**Start here: https://jaxzn.github.io/calendars/**

Subscribe instead of importing a downloaded file, otherwise you won't get updates.
Calendar apps decide how often to refresh; the feeds ask for every 6 hours, but Google
can take up to a day to show a change.

- **Apple Calendar (iPhone/iPad/Mac):** tap *Subscribe* (a `webcal://` link), or on a Mac
  *File → New Calendar Subscription…* and paste the copied link. Pick iCloud to sync all devices.
- **Google Calendar:** use the *Google Calendar* button, or on the web *Other calendars → + → From URL*
  and paste the copied `https://` link.
- **Outlook:** *Add calendar → Subscribe from web* (Outlook.com / Microsoft 365) or
  *Add Calendar → From Internet* (classic Outlook).

## Football (NFL)

**Subscribe page: https://jaxzn.github.io/calendars/football/**

- One calendar per team, all 32 teams (e.g. `hou.ics` for the Houston Texans)
- `primetime.ics`: every prime-time / national-window game (Thursday, Sunday and
  Monday night, Saturday, holiday and international national windows) plus all
  playoff games

Calendar names are the team name or `NFL Prime Time`, with no season year (calendar
apps keep the name from the day you subscribe). The page heading still says which
season it is, for example `NFL 2026 Calendars`.

Each game shows as `Away @ Home (TV)` with a 3-hour block, the TV channel and venue
in the description, and (after the game) the final score. Kickoffs are stored in UTC,
so every calendar app shows them in your own time zone. Games whose date/time hasn't
been set yet (late-season flex games, Week 18) appear as all-day placeholders and
move to the right slot once the NFL schedules them. Playoff games appear as their
slots are announced and join a team's calendar once that team is in the game.

`football/generate.py` (Python 3 standard library only) pulls ESPN's public scoreboard
feed for regular-season weeks 1–18 and the postseason, auto-detects the season, and
writes `docs/football/*.ics` and `docs/football/index.html`. Files are only rewritten
when the schedule actually changes (`DTSTAMP` is ignored), and if any request fails
the script exits non-zero without touching existing files.
`.github/workflows/football.yml` runs it daily (and every 6 hours on Sundays, Mondays
and Thursdays during the season) and commits any changes. It shares a concurrency
group with the basketball workflow so the two jobs never push at the same time.

```sh
python3 football/generate.py            # current season
python3 football/generate.py --season 2026
```

## Basketball (NBA)

**Subscribe page: https://jaxzn.github.io/calendars/basketball/**

- One calendar per team, all 30 teams (e.g. `hou.ics` for the Houston Rockets)
- `national.ics`: nationally televised games (`NBA National TV`)

Calendar names are the team name or `NBA National TV`, with no season year. The page
heading uses the season span, for example `NBA 2026-27 Calendars`. ESPN's season
year is the year the season ends, so `--season 2027` is the 2026-27 season.

Each game shows as `Away @ Home (TV)` with a 2.5-hour block. TV in the title is the
national channel or channels when ESPN lists any, otherwise the home and away
broadcasters. A broadcast is national when ESPN marks its market as national and the
medium is TV or streaming (not radio). That covers ESPN, ESPN2, ABC, NBC, NBCSN,
Peacock, Prime Video, NBA TV, and any other national outlet ESPN adds. NBA League
Pass is not treated as a national broadcast. The description includes the round
(regular season, NBA Cup, play-in, or playoff round), the channel, the venue, and
the final score after the game.

The feed includes the regular season (NBA Cup group play, and Cup knockout games
once ESPN schedules them), the play-in, and the playoffs. Preseason and the All-Star
game are skipped.

A full regular season is 82 games. ESPN leaves about two games per team unpublished
until the NBA Cup knockout dates are placed, so early in the year every team can
list 80. In 2025-26 the Cup championship was an extra regular-season event, so the
finalists listed 83 and everyone else 82. The generator accepts 80–83 regular-season
games per team and refuses anything outside that, so a partial or corrupt feed is
not published.

`basketball/generate.py` reads each team's ESPN schedule. Same write-on-change and
fail-closed behavior as football. `.github/workflows/basketball.yml` runs daily from
October through June (11:00 UTC), plus `workflow_dispatch`.

```sh
python3 basketball/generate.py            # current season
python3 basketball/generate.py --season 2027
```

To host somewhere else, set `CAL_BASE_URL` for football or `NBA_CAL_BASE_URL` for
basketball (each must end with `/`).

GitHub Pages setup: *Settings → Pages → Deploy from a branch → `main` / `docs`*.

## Data source and disclaimer

Schedule data comes from ESPN's public (undocumented) API at `site.api.espn.com`.
This project is unofficial and is not affiliated with, endorsed by, or connected to
the National Football League, the National Basketball Association, any team, or ESPN.
Team names are trademarks of their owners. Schedules change; confirm tip-off and
kickoff times with an official source. Provided as-is with no warranty.
