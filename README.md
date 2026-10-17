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
group with the basketball, hockey, and baseball workflows so the jobs never push
at the same time.

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

A full regular season is 82 playable games. ESPN leaves about two games per team
unpublished until the NBA Cup knockout dates are placed, so early in the year every
team can list 80. The Cup championship has been an extra regular-season event, so
the finalists list 83 and everyone else 82. The generator accepts 80–83 playable
regular-season games per team and refuses anything outside that, so a partial or
corrupt feed is not published.

Postponed and cancelled games stay in the feed as cancelled events under the same
`espn-<id>@nba-calendars` UID and do not count toward the 82. Suspended games keep
that UID and move when ESPN updates the date. A makeup ESPN files as a new event
gets its own UID.

`basketball/generate.py` reads each team's ESPN schedule. Same write-on-change and
fail-closed behavior as football. `.github/workflows/basketball.yml` runs daily from
October through June (11:00 UTC), plus `workflow_dispatch`. It uses the same
`calendars` concurrency group as the other sports.

```sh
python3 basketball/generate.py            # current season
python3 basketball/generate.py --season 2027
```

## Hockey (NHL)

**Subscribe page: https://jaxzn.github.io/calendars/hockey/**

- One calendar per team, all 32 teams (e.g. `nyr.ics` for the New York Rangers)
- `national.ics`: nationally televised games (`NHL National TV`)

Calendar names are the team name or `NHL National TV`, with no season year. The page
heading uses the season span, for example `NHL 2026-27 Calendars`. ESPN's season
year is the year the season ends, so `--season 2027` is the 2026-27 season.

Each game shows as `Away @ Home (TV)` with a 2.5-hour block. TV in the title is the
national channel or channels when ESPN lists any, otherwise the home and away
broadcasters. A broadcast is national when ESPN marks its market as national and the
medium is TV or streaming (not radio). That covers ESPN, ESPN+, ABC, TNT, truTV,
NHL Network, and any other national outlet ESPN adds. The description includes the
round, the channel, the venue, and the final score after the game.

The feed includes the regular season and the playoffs. Preseason and the All-Star
game are skipped. Playoff games appear as ESPN lists them, including games marked
"if necessary," and drop off a team's calendar once ESPN removes them.

A full regular season was 82 games through 2025-26 and is 84 games starting in
2026-27. The generator accepts 78–88 regular-season games per team once that
season is on the board. If the next season is not published yet (every team well
short of that range), it still writes the games ESPN has, instead of failing the
job. A lopsided feed, some teams in range and some not, is refused.

Postponed and cancelled games stay in the feed as cancelled events under the same
`espn-<id>@nhl-calendars` UID. Suspended games keep that UID and move when ESPN
updates the date. A makeup ESPN files as a new event gets its own UID.

`hockey/generate.py` reads each team's ESPN schedule. Same write-on-change and
fail-closed behavior as the other sports. `.github/workflows/hockey.yml` runs daily
(12:00 UTC), plus `workflow_dispatch`, in the shared `calendars` concurrency group.

```sh
python3 hockey/generate.py            # current season
python3 hockey/generate.py --season 2027
```

## Baseball (MLB)

**Subscribe page: https://jaxzn.github.io/calendars/baseball/**

- One calendar per team, all 30 teams (e.g. `nyy.ics` for the New York Yankees)
- `national.ics`: nationally televised games (`MLB National TV`)

Calendar names are the team name or `MLB National TV`, with no season year. The page
heading uses the season year, for example `MLB 2026 Calendars`. ESPN's season year
is that calendar year, so `--season 2026` is the 2026 season.

Each game shows as `Away @ Home (TV)` with a 3-hour block. TV in the title follows
the same national-or-else-local rule as the NBA calendars. National outlets include
Fox, FS1, ESPN, TBS, MLB Network, Apple TV, Peacock, Prime Video, Netflix, and
ESPN Unlimited. MLB.TV is carried on essentially every game, so it is not treated
as a national broadcast. The description includes the round (regular season,
doubleheader, or postseason round), the channel, the venue, and the final score
after the game.

The feed includes the regular season and the postseason. Spring training and the
All-Star game are skipped. Each game of a doubleheader is its own event. Postponed
and cancelled games stay in the feed as cancelled events under the same
`espn-<id>@mlb-calendars` UID and do not count toward the 162. ESPN's makeup is
usually a new event and gets its own UID. Suspended games keep their original UID
and move when ESPN changes that event's date.

A full regular season is 162 games. The generator accepts 154–170 playable games
per team once that season is on the board, which covers rainouts whose makeups are
not listed yet. In the 2026 feed ESPN is also missing one Yankees–Orioles game, so
those two clubs list 161 completed games and everyone else lists 162. If a future
season is not published yet, the job still writes what ESPN has instead of failing.
While the postseason is in progress, the scoreboard year stays on that season, so
the calendars keep the regular season plus wild-card, division, championship, and
World Series games. "If necessary" games and a World Series opponent of TBD show
up on the qualified team's calendar once ESPN lists them, and on the other team's
calendar when the opponent is filled in. Pass `--season` for the next year when
you want that schedule before ESPN's scoreboard rolls over.

`baseball/generate.py` reads each team's ESPN schedule. Same write-on-change and
fail-closed behavior as the other sports. `.github/workflows/baseball.yml` runs
daily (13:00 UTC), plus `workflow_dispatch`, in the shared `calendars` concurrency
group.

```sh
python3 baseball/generate.py            # current season
python3 baseball/generate.py --season 2026
```

To host somewhere else, set `CAL_BASE_URL` for football, `NBA_CAL_BASE_URL` for
basketball, `NHL_CAL_BASE_URL` for hockey, or `MLB_CAL_BASE_URL` for baseball
(each must end with `/`).

GitHub Pages setup: *Settings → Pages → Deploy from a branch → `main` / `docs`*.

## Data source and disclaimer

Schedule data comes from ESPN's public (undocumented) API at `site.api.espn.com`.
This project is unofficial and is not affiliated with, endorsed by, or connected to
the National Football League, the National Basketball Association, the National
Hockey League, Major League Baseball, any team, or ESPN. Team names are trademarks
of their owners. Schedules change; confirm game times with an official source.
Provided as-is with no warranty.
