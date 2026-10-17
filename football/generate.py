#!/usr/bin/env python3
"""Generate public, subscribable NFL calendars (.ics) for GitHub Pages.

Outputs (relative to the repo root):
  docs/football/<abbr>.ics      one calendar per team (all 32)
  docs/football/primetime.ics   all prime-time / national-window games + playoffs
  docs/football/index.html      subscribe page

Data: ESPN's public (unofficial) scoreboard API. Python 3 stdlib only.
Unofficial; not affiliated with the NFL or ESPN.

Usage: python3 football/generate.py [--season YEAR] [--out DIR]
Exit codes: 0 = ok (files written only if content changed), 1 = fetch/validation failure
(nothing is overwritten in that case).
"""
import argparse
import html
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

# ---- Change this if the site is hosted somewhere else (must end with "/") ----
BASE_URL = os.environ.get("CAL_BASE_URL", "https://jaxzn.github.io/calendars/football/")

API = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ET = ZoneInfo("America/New_York")
UID_DOMAIN = "nfl-calendars"
REG_WEEKS = range(1, 19)
POST_WEEKS = range(1, 6)  # Wild Card, Divisional, Conference, Super Bowl (+ spare)
GAME_HOURS = 3
REFRESH = "PT6H"
PRODID = "-//jaxzn//NFL Calendars//EN"

DIVISIONS = [
    ("AFC East", [("BUF", "Buffalo Bills"), ("MIA", "Miami Dolphins"), ("NE", "New England Patriots"), ("NYJ", "New York Jets")]),
    ("AFC North", [("BAL", "Baltimore Ravens"), ("CIN", "Cincinnati Bengals"), ("CLE", "Cleveland Browns"), ("PIT", "Pittsburgh Steelers")]),
    ("AFC South", [("HOU", "Houston Texans"), ("IND", "Indianapolis Colts"), ("JAX", "Jacksonville Jaguars"), ("TEN", "Tennessee Titans")]),
    ("AFC West", [("DEN", "Denver Broncos"), ("KC", "Kansas City Chiefs"), ("LV", "Las Vegas Raiders"), ("LAC", "Los Angeles Chargers")]),
    ("NFC East", [("DAL", "Dallas Cowboys"), ("NYG", "New York Giants"), ("PHI", "Philadelphia Eagles"), ("WSH", "Washington Commanders")]),
    ("NFC North", [("CHI", "Chicago Bears"), ("DET", "Detroit Lions"), ("GB", "Green Bay Packers"), ("MIN", "Minnesota Vikings")]),
    ("NFC South", [("ATL", "Atlanta Falcons"), ("CAR", "Carolina Panthers"), ("NO", "New Orleans Saints"), ("TB", "Tampa Bay Buccaneers")]),
    ("NFC West", [("ARI", "Arizona Cardinals"), ("LAR", "Los Angeles Rams"), ("SF", "San Francisco 49ers"), ("SEA", "Seattle Seahawks")]),
]
TEAMS = {abbr: name for _, teams in DIVISIONS for abbr, name in teams}
POST_ROUNDS = {1: "Wild Card", 2: "Divisional Round", 3: "Conference Championship", 4: "Super Bowl", 5: "Super Bowl"}


def norm_hex(value):
    s = (value or "").strip().lstrip("#")
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return s.lower()
    return ""


def _channel(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex6):
    r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(a, b, t):
    out = []
    for i in (0, 2, 4):
        av, bv = int(a[i:i + 2], 16), int(b[i:i + 2], 16)
        out.append(f"{round(av + (bv - av) * t):02x}")
    return "".join(out)


def readable_swatch(primary):
    """Swatch fill and text color with at least 4.5:1 contrast when possible."""
    ink = "ffffff" if contrast(primary, "ffffff") >= contrast(primary, "1c1915") else "1c1915"
    bg = primary
    toward = "000000" if ink == "ffffff" else "ffffff"
    for _ in range(10):
        if contrast(bg, ink) >= 4.5:
            return bg, ink
        bg = _mix(bg, toward, 0.14)
    return bg, ink


# ----------------------------------------------------------------- fetching
def fetch_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nfl-calendars/1.0 (+github.com/jaxzn)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def detect_season():
    """Season year from ESPN's current scoreboard, else a date heuristic
    (Jan-Feb belong to the previous season)."""
    try:
        d = fetch_json(API)
        y = (d.get("season") or {}).get("year") or d["leagues"][0]["season"]["year"]
        return int(y)
    except Exception as e:  # noqa: BLE001
        now = datetime.now(ET)
        y = now.year if now.month >= 3 else now.year - 1
        print(f"warning: season auto-detect via ESPN failed ({e}); using {y}", file=sys.stderr)
        return y


# ----------------------------------------------------------------- parsing
def tv_string(comp):
    names = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]
    out = []
    for n in names:
        if n == "NFL Net":
            n = "NFL Network"
        if n not in out:
            out.append(n)
    return " / ".join(out)


def is_primetime(dt_et, time_valid):
    # Same rule as the private calendar: any game with a confirmed time that is
    # at/after 7 PM ET, or on any day other than Sunday (TNF, MNF, Saturday,
    # Thanksgiving, Christmas, international Friday games, ...).
    return time_valid and (dt_et.hour >= 19 or dt_et.weekday() != 6)


def parse_event(e, seasontype, week):
    c = e["competitions"][0]
    sides = {x["homeAway"]: x for x in c["competitors"]}
    away, home = sides["away"]["team"], sides["home"]["team"]
    start = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
    valid = bool(c.get("timeValid", True))
    venue = c.get("venue") or {}
    addr = venue.get("address") or {}
    place = ", ".join(x for x in (addr.get("city"), addr.get("state") or addr.get("country")) if x)
    status = (e.get("status") or {}).get("type") or {}
    notes = [n.get("headline") for n in c.get("notes", []) if n.get("headline")]
    g = dict(
        id=str(e["id"]), seasontype=seasontype, week=week, start=start, valid=valid,
        away_abbr=away.get("abbreviation", "TBD"), home_abbr=home.get("abbreviation", "TBD"),
        away=away.get("shortDisplayName") or away.get("displayName") or "TBD",
        home=home.get("shortDisplayName") or home.get("displayName") or "TBD",
        away_full=away.get("displayName", ""), home_full=home.get("displayName", ""),
        away_color=norm_hex(away.get("color")), away_alt=norm_hex(away.get("alternateColor")),
        home_color=norm_hex(home.get("color")), home_alt=norm_hex(home.get("alternateColor")),
        neutral=bool(c.get("neutralSite")), tv=tv_string(c),
        venue=venue.get("fullName", ""), place=place,
        completed=bool(status.get("completed")),
        away_score=sides["away"].get("score"), home_score=sides["home"].get("score"),
        headline=notes[0] if notes else "",
    )
    g["primetime"] = is_primetime(start.astimezone(ET), valid)
    return g


def collect(season):
    games = {}
    for w in REG_WEEKS:
        d = fetch_json(f"{API}?dates={season}&seasontype=2&week={w}")
        evs = d.get("events") or []
        if not evs:
            raise RuntimeError(f"regular-season week {w} returned no games")
        for e in evs:
            games[str(e["id"])] = parse_event(e, 2, w)
    for w in POST_WEEKS:
        d = fetch_json(f"{API}?dates={season}&seasontype=3&week={w}")
        for e in d.get("events") or []:
            if "pro bowl" in (e.get("name", "") + json.dumps(e["competitions"][0].get("notes", []))).lower():
                continue  # exhibition, not a real game for any team
            games.setdefault(str(e["id"]), parse_event(e, 3, w))
    return list(games.values())


# ----------------------------------------------------------------- iCalendar
def esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\\n").replace("\n", "\\n"))


def fold(line):
    """Fold to <=75 octets per line (RFC 5545 3.1) without splitting UTF-8 chars."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    parts, cur, limit = [], b"", 75
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > limit:
            parts.append(cur.decode("utf-8"))
            cur, limit = b"", 74  # continuation lines start with a space
        cur += cb
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def game_title(g):
    if g["away_abbr"] in TEAMS or g["home_abbr"] in TEAMS:
        sep = "vs" if g["seasontype"] == 3 and g["neutral"] else "@"
        t = f"{g['away']} {sep} {g['home']}"
        if g["seasontype"] == 3:
            t = f"{g['headline'] or POST_ROUNDS.get(g['week'], 'Playoffs')}: {t}"
    else:  # playoff slot, teams not decided yet
        t = f"{g['headline'] or POST_ROUNDS.get(g['week'], 'Playoffs')} (teams TBD)"
    if g["tv"]:
        t += f" ({g['tv']})"
    return t


def vevent(g, dtstamp):
    lines = ["BEGIN:VEVENT", f"UID:espn-{g['id']}@{UID_DOMAIN}", f"DTSTAMP:{dtstamp}"]
    if g["valid"]:
        s = g["start"]
        lines += [f"DTSTART:{s:%Y%m%dT%H%M%SZ}", f"DTEND:{s + timedelta(hours=GAME_HOURS):%Y%m%dT%H%M%SZ}"]
    else:
        day = g["start"].astimezone(ET).date()
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    lines.append("SUMMARY:" + esc(game_title(g)))
    loc = ", ".join(x for x in (g["venue"], g["place"]) if x)
    if loc:
        lines.append("LOCATION:" + esc(loc))
    rnd = f"Week {g['week']}" if g["seasontype"] == 2 else (g["headline"] or POST_ROUNDS.get(g["week"], "Playoffs"))
    desc = [f"{rnd}", f"TV: {g['tv'] or 'TBD'}", f"Venue: {loc or 'TBD'}"]
    if not g["valid"]:
        desc.append("Date/time not yet set by the NFL; this is a placeholder.")
    if g["completed"] and g["away_score"] is not None:
        desc.append(f"Final: {g['away']} {g['away_score']}, {g['home']} {g['home_score']}")
    desc.append("Unofficial calendar; not affiliated with the NFL or ESPN. Times may change (flex scheduling).")
    lines.append("DESCRIPTION:" + esc("\n".join(desc)))
    lines += [f"STATUS:{'CONFIRMED' if g['valid'] else 'TENTATIVE'}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    return lines


def calendar(name, desc, games, dtstamp):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:" + esc(name), "X-WR-CALDESC:" + esc(desc), "X-WR-TIMEZONE:America/New_York",
             f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH}", f"X-PUBLISHED-TTL:{REFRESH}"]
    for g in sorted(games, key=lambda g: (g["start"], g["id"])):
        lines += vevent(g, dtstamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def strip_volatile(text):
    return "\n".join(l for l in text.replace("\r\n ", "").splitlines() if not l.startswith("DTSTAMP:"))


def write_if_changed(path, content, ignore_dtstamp=False):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            old = f.read()
    except FileNotFoundError:
        old = None
    if old is not None:
        same = strip_volatile(old) == strip_volatile(content) if ignore_dtstamp else old == content
        if same:
            return False
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    os.replace(tmp, path)
    return True


# ----------------------------------------------------------------- HTML
def swatch_style(pair):
    if not pair or not pair[0]:
        return ""
    primary, alt = pair
    bg, ink = readable_swatch(primary)
    return f' style="--team:#{primary};--alt:#{alt or primary};--swatch:#{bg};--on:#{ink}"'


def index_html(season, names, colors):
    base = BASE_URL if BASE_URL.endswith("/") else BASE_URL + "/"
    webcal = "webcal://" + base.split("://", 1)[1]

    def actions(slug, text):
        https, wc = base + slug + ".ics", webcal + slug + ".ics"
        g = "https://calendar.google.com/calendar/r?cid=" + quote(wc, safe="")
        safe = html.escape(text)
        return (
            '<div class="actions">'
            f'<a class="btn primary" href="{html.escape(wc)}">Subscribe</a>'
            f'<a class="btn" href="{html.escape(g)}" target="_blank" rel="noopener">Google Calendar</a>'
            f'<button type="button" class="btn" data-copy="{html.escape(https)}" data-label="Copy link" '
            f'aria-label="Copy {safe} calendar link">Copy link</button>'
            "</div>"
        )

    def team_card(abbr, fallback):
        text = names.get(abbr, fallback)
        key = html.escape(f"{text} {abbr}".lower(), quote=True)
        return (
            f'<article class="card" data-team="{key}"{swatch_style(colors.get(abbr))}>'
            f'<div class="card-main"><p class="abbr" aria-hidden="true">{html.escape(abbr)}</p>'
            f"<h3>{html.escape(text)}</h3></div>"
            f"{actions(abbr.lower(), text)}</article>"
        )

    divs = []
    for div, teams in DIVISIONS:
        cards = "\n".join(team_card(a, n) for a, n in teams)
        divs.append(
            f'<section class="division" data-division><h2>{html.escape(div)}</h2>'
            f'<div class="grid">\n{cards}\n</div></section>'
        )
    feature = (
        '<article class="card feature"><div class="feature-copy">'
        '<p class="eyebrow">Prime time</p><h2>NFL Prime Time</h2>'
        "<p>Thursday, Sunday, and Monday night games, plus Saturday, holiday, and international national windows, and the playoffs.</p></div>"
        f'{actions("primetime", "NFL Prime Time")}</article>'
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NFL {season} Calendars – subscribe to any team</title>
<meta name="description" content="Free, auto-updating NFL {season} schedule calendars for all 32 teams plus prime-time games. Works with Apple, Google and Outlook Calendar.">
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<a class="skip" href="#calendars">Skip to calendars</a>
<div class="wrap">
<header class="top">
  <div>
    <p class="kicker"><a href="../">Calendars</a></p>
    <h1>NFL {season} Calendars</h1>
    <p class="lead">Every team's full schedule, plus prime time. Subscribe once and kickoff times, flex changes, TV channels, and playoff games update automatically.</p>
  </div>
  <div class="find" role="search">
    <label for="team-search">Find a team</label>
    <input id="team-search" type="search" data-search placeholder="Name or abbreviation" autocomplete="off" enterkeyhint="search">
  </div>
</header>
<main id="calendars">
{feature}
<p class="empty" data-empty hidden>No teams match that search.</p>
{"".join(divs)}
</main>
<section class="howto">
<h2>How to subscribe</h2>
<details open><summary>Apple Calendar (iPhone, iPad, Mac)</summary>
<p>Tap <b>Subscribe</b>, then confirm. On a Mac you can also use <i>File → New Calendar Subscription…</i> and paste the link from <b>Copy link</b>. Set auto-refresh to every hour or day, and choose iCloud if you want it on all your devices.</p></details>
<details><summary>Google Calendar</summary>
<p>Click <b>Google Calendar</b> (on a computer), or in Google Calendar on the web go to <i>Other calendars → + → From URL</i> and paste the link from <b>Copy link</b>. It then shows up on your phone too. Google refreshes subscribed calendars on its own schedule, often every 8–24 hours.</p></details>
<details><summary>Outlook</summary>
<p>Outlook.com / Microsoft 365: <i>Calendar → Add calendar → Subscribe from web</i>, paste the link from <b>Copy link</b>. Classic Outlook for Windows: <i>Add Calendar → From Internet</i>.</p></details>
<p>Subscribe instead of importing a one-time download, or the calendar will not update. Kickoffs are stored in UTC so your calendar shows them in your own time zone. Games whose date or time the NFL hasn't set yet (for example Week 18) appear as all-day placeholders until they're scheduled.</p>
</section>
<footer>
<p>Unofficial and not affiliated with, endorsed by, or connected to the NFL, its teams, or ESPN. Schedule data comes from ESPN's public scoreboard feed and is refreshed automatically. Always confirm times with an official source.</p>
</footer>
</div>
<script src="../assets/subscribe.js" defer></script>
</body>
</html>
"""
    if "<img" in page or "espncdn" in page or "logo" in page.lower():
        raise RuntimeError("subscribe page would include an image or logo reference")
    return page


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, help="season year (default: auto-detect)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "football"))
    a = ap.parse_args()

    season = a.season or detect_season()
    try:
        games = collect(season)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}\nNo files were changed.", file=sys.stderr)
        return 1

    # sanity checks before touching anything
    names, colors, by_team = {}, {}, {t: [] for t in TEAMS}
    for g in games:
        for side in ("away", "home"):
            ab = g[side + "_abbr"]
            if ab in TEAMS:
                by_team[ab].append(g)
                if g[side + "_full"]:
                    names[ab] = g[side + "_full"]
                if g.get(side + "_color") and ab not in colors:
                    colors[ab] = (g[side + "_color"], g.get(side + "_alt") or g[side + "_color"])
    missing_colors = sorted(t for t in TEAMS if t not in colors)
    if missing_colors:
        print("ERROR: sanity check failed; no files were changed:\n  missing team colors: "
              + ", ".join(missing_colors), file=sys.stderr)
        return 1
    problems = [f"{t}: {sum(g['seasontype'] == 2 for g in gs)} regular-season games"
                for t, gs in by_team.items() if sum(g["seasontype"] == 2 for g in gs) != 17]
    unknown = {g[s + "_abbr"] for g in games if g["seasontype"] == 2 for s in ("away", "home")} - set(TEAMS)
    if unknown:
        problems.append(f"unknown team abbreviations in feed: {sorted(unknown)}")
    if problems:
        print("ERROR: sanity check failed; no files were changed:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1

    try:
        page = index_html(season, names, colors)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}\nNo files were changed.", file=sys.stderr)
        return 1

    os.makedirs(a.out, exist_ok=True)
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    changed = []
    for t, gs in by_team.items():
        # No season year: calendar apps keep X-WR-CALNAME from subscribe time.
        name = names.get(t, TEAMS[t])
        c = calendar(name, f"{name} NFL schedule (unofficial, auto-updated)", gs, dtstamp)
        if write_if_changed(os.path.join(a.out, t.lower() + ".ics"), c, True):
            changed.append(t.lower() + ".ics")
    pt = [g for g in games if g["primetime"] or g["seasontype"] == 3]
    c = calendar("NFL Prime Time",
                 "NFL prime-time and national-window games plus playoffs (unofficial, auto-updated)", pt, dtstamp)
    if write_if_changed(os.path.join(a.out, "primetime.ics"), c, True):
        changed.append("primetime.ics")
    if write_if_changed(os.path.join(a.out, "index.html"), page):
        changed.append("index.html")

    reg = sum(g["seasontype"] == 2 for g in games)
    print(f"season {season}: {reg} regular-season + {len(games) - reg} postseason games; "
          f"primetime.ics={len(pt)} events; changed: {', '.join(changed) or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
