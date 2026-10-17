#!/usr/bin/env python3
"""Generate public, subscribable NBA calendars (.ics) for GitHub Pages.

Outputs (relative to the repo root):
  docs/basketball/<abbr>.ics   one calendar per team (all 30)
  docs/basketball/national.ics nationally televised games
  docs/basketball/index.html   subscribe page

Data: ESPN's public (unofficial) NBA API. Python 3 stdlib only.
Unofficial; not affiliated with the NBA or ESPN.

Season year: ESPN's season year is the year the season *ends* (2027 is the
2026-27 season; the subscribe page says "2026-27"). Calendar names do not
include a year.

Which games:
  seasontype 2  regular season, including NBA Cup games ESPN files there
                (group play, and knockout rounds once they are scheduled)
  seasontype 5  play-in
  seasontype 3  playoffs
  Preseason (seasontype 1) and the All-Star game are skipped.

National TV: a broadcast counts as national when ESPN marks its market as
national (market type "National") and the medium is TV or streaming, not
radio. Networks that appear that way include ESPN, ESPN2, ABC, NBC, NBCSN,
Peacock, Prime Video, and NBA TV. NBA League Pass is not treated as a
national broadcast. The event summary is "Away @ Home (TV)": TV is the
national channel(s) when any exist, otherwise the home and away broadcasters.

Regular-season count: a full schedule is 82 games. ESPN leaves about two
games per team off the feed until NBA Cup knockout dates are placed (group
play is already included). In 2025-26 the championship was an extra regular-
season event, so the two finalists listed 83 games and everyone else 82.
This script accepts 80–83 regular-season games per team and refuses anything
outside that range.

Usage: python3 basketball/generate.py [--season YEAR] [--out DIR]
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
BASE_URL = os.environ.get("NBA_CAL_BASE_URL", "https://jaxzn.github.io/calendars/basketball/")

API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ET = ZoneInfo("America/New_York")
UID_DOMAIN = "nba-calendars"
GAME_DURATION = timedelta(minutes=150)
REFRESH = "PT6H"
PRODID = "-//jaxzn//NBA Calendars//EN"
# 82 is a full regular season. 80–81: NBA Cup knockout dates not all published
# yet. 83: Cup championship finalist (an extra seasontype-2 game in 2025-26).
REG_LO, REG_HI = 80, 83
SEASON_TYPES = (2, 3, 5)  # regular (incl. NBA Cup), playoffs, play-in

# (abbr, display name, ESPN team id). Abbreviations match ESPN's feed.
CONFERENCES = [
    ("Eastern Conference", [
        ("Atlantic", [
            ("BOS", "Boston Celtics", "2"),
            ("BKN", "Brooklyn Nets", "17"),
            ("NY", "New York Knicks", "18"),
            ("PHI", "Philadelphia 76ers", "20"),
            ("TOR", "Toronto Raptors", "28"),
        ]),
        ("Central", [
            ("CHI", "Chicago Bulls", "4"),
            ("CLE", "Cleveland Cavaliers", "5"),
            ("DET", "Detroit Pistons", "8"),
            ("IND", "Indiana Pacers", "11"),
            ("MIL", "Milwaukee Bucks", "15"),
        ]),
        ("Southeast", [
            ("ATL", "Atlanta Hawks", "1"),
            ("CHA", "Charlotte Hornets", "30"),
            ("MIA", "Miami Heat", "14"),
            ("ORL", "Orlando Magic", "19"),
            ("WSH", "Washington Wizards", "27"),
        ]),
    ]),
    ("Western Conference", [
        ("Northwest", [
            ("DEN", "Denver Nuggets", "7"),
            ("MIN", "Minnesota Timberwolves", "16"),
            ("OKC", "Oklahoma City Thunder", "25"),
            ("POR", "Portland Trail Blazers", "22"),
            ("UTAH", "Utah Jazz", "26"),
        ]),
        ("Pacific", [
            ("GS", "Golden State Warriors", "9"),
            ("LAC", "LA Clippers", "12"),
            ("LAL", "Los Angeles Lakers", "13"),
            ("PHX", "Phoenix Suns", "21"),
            ("SAC", "Sacramento Kings", "23"),
        ]),
        ("Southwest", [
            ("DAL", "Dallas Mavericks", "6"),
            ("HOU", "Houston Rockets", "10"),
            ("MEM", "Memphis Grizzlies", "29"),
            ("NO", "New Orleans Pelicans", "3"),
            ("SA", "San Antonio Spurs", "24"),
        ]),
    ]),
]
TEAMS = {abbr: name for _, divs in CONFERENCES for _, teams in divs for abbr, name, _id in teams}
TEAM_IDS = {abbr: tid for _, divs in CONFERENCES for _, teams in divs for abbr, _name, tid in teams}


# ----------------------------------------------------------------- fetching
def fetch_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nba-calendars/1.0 (+github.com/jaxzn)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def season_label(year):
    """ESPN year is the year the season ends: 2027 -> 2026-27."""
    return f"{year - 1}-{year % 100:02d}"


def detect_season():
    """ESPN season year from the current scoreboard, else a date heuristic
    (July–December belong to the season that ends the next calendar year)."""
    try:
        d = fetch_json(f"{API}/scoreboard")
        y = (d.get("season") or {}).get("year") or d["leagues"][0]["season"]["year"]
        return int(y)
    except Exception as e:  # noqa: BLE001
        now = datetime.now(ET)
        y = now.year if now.month <= 6 else now.year + 1
        print(f"warning: season auto-detect via ESPN failed ({e}); using {y}", file=sys.stderr)
        return y


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
    """Swatch fill and text color. The color bar keeps the true team color;
    the swatch is nudged only when the abbreviation would fail contrast."""
    ink = "ffffff" if contrast(primary, "ffffff") >= contrast(primary, "1c1915") else "1c1915"
    bg = primary
    toward = "000000" if ink == "ffffff" else "ffffff"
    for _ in range(10):
        if contrast(bg, ink) >= 4.5:
            return bg, ink
        bg = _mix(bg, toward, 0.14)
    return bg, ink


# ----------------------------------------------------------------- parsing
def broadcast_lists(comp):
    """Return (national_names, local_names). See module docstring for the rule."""
    national, local = [], []
    for b in comp.get("broadcasts") or []:
        market = b.get("market")
        if isinstance(market, dict):
            market_type = (market.get("type") or "").strip().lower()
        else:
            market_type = str(market or "").strip().lower()
        btype = b.get("type")
        if isinstance(btype, dict):
            kind = (btype.get("shortName") or "").strip().lower()
        else:
            kind = str(btype or "").strip().lower()
        if kind == "radio":
            continue
        media = b.get("media") if isinstance(b.get("media"), dict) else {}
        label = (media.get("shortName") or "").strip()
        if not label:
            names = b.get("names") or []
            label = names[0].strip() if names else ""
        if not label or "league pass" in label.lower():
            continue
        if kind not in ("tv", "streaming", ""):
            continue
        bucket = national if market_type == "national" else local if market_type in ("home", "away", "") else None
        if bucket is not None and label not in bucket:
            bucket.append(label)
    return national, local


def parse_event(e, seasontype):
    c = e["competitions"][0]
    sides = {x["homeAway"]: x for x in c["competitors"]}
    away, home = sides["away"]["team"], sides["home"]["team"]
    st = e.get("seasonType") or {}
    if isinstance(st, dict) and st.get("type"):
        seasontype = int(st["type"])
    notes = [n.get("headline") for n in c.get("notes") or [] if n.get("headline")]
    headline = notes[0] if notes else ""
    blob = f"{e.get('name', '')} {headline}".lower()
    if "all-star" in blob or "all star" in blob:
        return None  # exhibition; not a team game
    if seasontype == 1:
        return None
    status = ((e.get("status") or {}).get("type") or (c.get("status") or {}).get("type") or {})
    if "CANCEL" in (status.get("name") or "").upper():
        return None
    start = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
    if "timeValid" in c:
        valid = bool(c.get("timeValid"))
    else:
        valid = bool(e.get("timeValid", True))
    venue = c.get("venue") or {}
    if isinstance(venue, str):
        venue = {"fullName": venue}
    addr = venue.get("address") or {}
    place = ", ".join(x for x in (addr.get("city"), addr.get("state") or addr.get("country")) if x)
    national, local = broadcast_lists(c)
    shown = national or local
    colors = {}
    for team in (away, home):
        ab = team.get("abbreviation")
        primary = norm_hex(team.get("color"))
        if ab and primary:
            colors[ab] = (primary, norm_hex(team.get("alternateColor")) or primary)
    return dict(
        id=str(e["id"]), seasontype=seasontype, start=start, valid=valid,
        away_abbr=away.get("abbreviation") or "TBD", home_abbr=home.get("abbreviation") or "TBD",
        away=away.get("shortDisplayName") or away.get("displayName") or "TBD",
        home=home.get("shortDisplayName") or home.get("displayName") or "TBD",
        away_full=away.get("displayName") or "", home_full=home.get("displayName") or "",
        national=national, local=local, tv=" / ".join(shown),
        venue=venue.get("fullName") or "", place=place,
        completed=bool(status.get("completed")),
        away_score=sides["away"].get("score"), home_score=sides["home"].get("score"),
        headline=headline, colors=colors,
    )


def richer(a, b):
    """Prefer the copy of a game that has more broadcast names."""
    return b if len(b["national"]) + len(b["local"]) > len(a["national"]) + len(a["local"]) else a


def fetch_team_meta():
    """Colors and names from the teams endpoint. Logo URLs are ignored."""
    d = fetch_json(f"{API}/teams?limit=50")
    found = {}
    for t in d["sports"][0]["leagues"][0]["teams"]:
        tm = t.get("team") or t
        abbr = tm.get("abbreviation")
        if not abbr or tm.get("isAllStar"):
            continue
        found[abbr] = (
            tm.get("displayName") or "",
            norm_hex(tm.get("color")),
            norm_hex(tm.get("alternateColor")),
        )
    return found


def collect(season):
    games, label = {}, None
    for abbr, tid in TEAM_IDS.items():
        for st in SEASON_TYPES:
            d = fetch_json(f"{API}/teams/{tid}/schedule?season={season}&seasontype={st}")
            if st == 2:
                label = ((d.get("season") or {}).get("displayName")
                         or (d.get("requestedSeason") or {}).get("displayName")
                         or label)
            for e in d.get("events") or []:
                try:
                    g = parse_event(e, st)
                except Exception as err:  # noqa: BLE001
                    raise RuntimeError(f"could not parse event {e.get('id')}: {err}") from err
                if g is None:
                    continue
                games[g["id"]] = richer(games[g["id"]], g) if g["id"] in games else g
    return list(games.values()), label or season_label(season)


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


def round_label(g):
    if g["seasontype"] == 2:
        return g["headline"] or "Regular Season"
    if g["seasontype"] == 5:
        return g["headline"] or "Play-In"
    return g["headline"] or "Playoffs"


def game_title(g):
    t = f"{g['away']} @ {g['home']}"
    if g["tv"]:
        t += f" ({g['tv']})"
    return t


def vevent(g, dtstamp):
    lines = ["BEGIN:VEVENT", f"UID:espn-{g['id']}@{UID_DOMAIN}", f"DTSTAMP:{dtstamp}"]
    if g["valid"]:
        s = g["start"]
        lines += [f"DTSTART:{s:%Y%m%dT%H%M%SZ}", f"DTEND:{(s + GAME_DURATION):%Y%m%dT%H%M%SZ}"]
    else:
        day = g["start"].astimezone(ET).date()
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    lines.append("SUMMARY:" + esc(game_title(g)))
    loc = ", ".join(x for x in (g["venue"], g["place"]) if x)
    if loc:
        lines.append("LOCATION:" + esc(loc))
    desc = [round_label(g), f"TV: {g['tv'] or 'TBD'}", f"Venue: {loc or 'TBD'}"]
    if not g["valid"]:
        desc.append("Date/time not yet set by the NBA; this is a placeholder.")
    if g["completed"] and g["away_score"] not in (None, ""):
        desc.append(f"Final: {g['away']} {g['away_score']}, {g['home']} {g['home_score']}")
    desc.append("Unofficial calendar; not affiliated with the NBA or ESPN. Times may change.")
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
# index.html loads docs/assets/subscribe.js. That script opens webcal:// links
# from a throwaway iframe on iOS WKWebView browsers so the tab does not keep a
# failed main-frame navigation. Keep the script tag. The plain href is the
# no-JS, Safari, and desktop fallback.
def swatch_style(pair):
    if not pair or not pair[0]:
        return ""
    primary, alt = pair
    bg, ink = readable_swatch(primary)
    return f' style="--team:#{primary};--alt:#{alt or primary};--swatch:#{bg};--on:#{ink}"'


def index_html(label, names, colors):
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

    blocks = []
    for conference, divisions in CONFERENCES:
        parts = []
        for division, teams in divisions:
            cards = "\n".join(team_card(a, n) for a, n, _tid in teams)
            parts.append(
                f'<section class="division" data-division><h3>{html.escape(division)}</h3>'
                f'<div class="grid">\n{cards}\n</div></section>'
            )
        blocks.append(
            f'<section class="conference" data-conference><h2 class="conf">{html.escape(conference)}</h2>'
            f'{"".join(parts)}</section>'
        )
    feature = (
        '<article class="card feature"><div class="feature-copy">'
        '<p class="eyebrow">National TV</p><h2>NBA National TV</h2>'
        "<p>Games ESPN lists on a national broadcast: ESPN, ABC, NBC, Peacock, Prime Video, NBA TV, and the other national channels. "
        "Play-in and playoff games join this calendar once they are scheduled.</p></div>"
        f'{actions("national", "NBA National TV")}</article>'
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NBA {label} Calendars – subscribe to any team</title>
<meta name="description" content="Free, auto-updating NBA {label} schedule calendars for all 30 teams plus nationally televised games. Works with Apple, Google and Outlook Calendar.">
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<a class="skip" href="#calendars">Skip to calendars</a>
<div class="wrap">
<header class="top">
  <div>
    <p class="kicker"><a href="../">Calendars</a></p>
    <h1>NBA {label} Calendars</h1>
    <p class="lead">Every team's schedule, plus a national-TV calendar. Subscribe once and tip-off times, channels, NBA Cup games, the play-in, and the playoffs update automatically.</p>
  </div>
  <div class="find" role="search">
    <label for="team-search">Find a team</label>
    <input id="team-search" type="search" data-search placeholder="Name or abbreviation" autocomplete="off" enterkeyhint="search">
  </div>
</header>
<main id="calendars">
{feature}
<p class="empty" data-empty hidden>No teams match that search.</p>
{"".join(blocks)}
</main>
<section class="howto">
<h2>How to subscribe</h2>
<details open><summary>Apple Calendar (iPhone, iPad, Mac)</summary>
<p>Tap <b>Subscribe</b>, then confirm. On a Mac you can also use <i>File → New Calendar Subscription…</i> and paste the link from <b>Copy link</b>. Set auto-refresh to every hour or day, and choose iCloud if you want it on all your devices.</p></details>
<details><summary>Google Calendar</summary>
<p>Click <b>Google Calendar</b> (on a computer), or in Google Calendar on the web go to <i>Other calendars → + → From URL</i> and paste the link from <b>Copy link</b>. It then shows up on your phone too. Google refreshes subscribed calendars on its own schedule, often every 8–24 hours.</p></details>
<details><summary>Outlook</summary>
<p>Outlook.com / Microsoft 365: <i>Calendar → Add calendar → Subscribe from web</i>, paste the link from <b>Copy link</b>. Classic Outlook for Windows: <i>Add Calendar → From Internet</i>.</p></details>
<p>Subscribe instead of importing a one-time download, or the calendar will not update. Tip-offs are stored in UTC so your calendar shows them in your own time zone. Games whose date or time is not set yet appear as all-day placeholders until the NBA schedules them.</p>
</section>
<footer>
<p>Unofficial and not affiliated with, endorsed by, or connected to the NBA, its teams, or ESPN. Schedule data comes from ESPN's public scoreboard feed and is refreshed automatically. Always confirm times with an official source.</p>
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
    ap.add_argument("--season", type=int, help="ESPN season year, the year the season ends (2027 is 2026-27)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "basketball"))
    a = ap.parse_args()

    season = a.season or detect_season()
    try:
        games, label = collect(season)
        meta = fetch_team_meta()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}\nNo files were changed.", file=sys.stderr)
        return 1

    names, colors, by_team = {}, {}, {t: [] for t in TEAMS}
    for abbr, (display, primary, alt) in meta.items():
        if abbr not in TEAMS:
            continue
        if display:
            names[abbr] = display
        if primary:
            colors[abbr] = (primary, alt or primary)
    for g in games:
        for side in ("away", "home"):
            ab = g[side + "_abbr"]
            if ab in TEAMS:
                by_team[ab].append(g)
                if ab not in names and g[side + "_full"]:
                    names[ab] = g[side + "_full"]
                if ab not in colors and g["colors"].get(ab):
                    colors[ab] = g["colors"][ab]
    extra = sorted(set(meta) - set(TEAMS))
    missing = sorted(set(TEAMS) - set(meta))
    if extra or missing:
        print("ERROR: sanity check failed; no files were changed:\n  "
              f"team list mismatch: missing {missing} extra {extra}", file=sys.stderr)
        return 1

    def reg_count(gs):
        return sum(g["seasontype"] == 2 for g in gs)

    problems = []
    counts = {t: reg_count(gs) for t, gs in by_team.items()}
    for t, n in sorted(counts.items()):
        if not REG_LO <= n <= REG_HI:
            problems.append(f"{t}: {n} regular-season games (expected {REG_LO}–{REG_HI})")
    reg_games = [g for g in games if g["seasontype"] == 2]
    slots = sum(1 for g in reg_games for s in ("away", "home") if g[s + "_abbr"] in TEAMS)
    if slots != len(reg_games) * 2:
        problems.append(f"regular-season games are not all between two known teams ({slots} team-slots, {len(reg_games)} games)")
    unknown = {g[s + "_abbr"] for g in reg_games for s in ("away", "home")} - set(TEAMS)
    if unknown:
        problems.append(f"unknown team abbreviations in feed: {sorted(unknown)}")
    if len(TEAMS) != 30:
        problems.append(f"expected 30 teams, have {len(TEAMS)}")
    missing_colors = sorted(t for t in TEAMS if t not in colors)
    if missing_colors:
        problems.append(f"missing team colors: {missing_colors}")
    if problems:
        print("ERROR: sanity check failed; no files were changed:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1

    try:
        page = index_html(label, names, colors)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}\nNo files were changed.", file=sys.stderr)
        return 1

    os.makedirs(a.out, exist_ok=True)
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    changed = []
    for t, gs in by_team.items():
        # No season year: calendar apps keep X-WR-CALNAME from subscribe time.
        name = names.get(t, TEAMS[t])
        c = calendar(name, f"{name} NBA schedule (unofficial, auto-updated)", gs, dtstamp)
        if write_if_changed(os.path.join(a.out, t.lower() + ".ics"), c, True):
            changed.append(t.lower() + ".ics")
    nat = [g for g in games if g["national"]]
    c = calendar("NBA National TV",
                 "NBA nationally televised games (unofficial, auto-updated)", nat, dtstamp)
    if write_if_changed(os.path.join(a.out, "national.ics"), c, True):
        changed.append("national.ics")
    if write_if_changed(os.path.join(a.out, "index.html"), page):
        changed.append("index.html")

    playin = sum(g["seasontype"] == 5 for g in games)
    post = sum(g["seasontype"] == 3 for g in games)
    lo, hi = min(counts.values()), max(counts.values())
    print(f"season {season} ({label}): {len(reg_games)} regular-season + {playin} play-in + {post} playoff games; "
          f"national.ics={len(nat)} events; per-team regular season {lo}–{hi}")
    for t in sorted(counts):
        gs = by_team[t]
        print(f"  {t}: regular={counts[t]} play-in={sum(g['seasontype']==5 for g in gs)} "
              f"playoffs={sum(g['seasontype']==3 for g in gs)} total={len(gs)}")
    print(f"changed: {', '.join(changed) or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
