#!/usr/bin/env python3
"""Generate public, subscribable MLB calendars (.ics) for GitHub Pages.

Outputs (relative to the repo root):
  docs/baseball/<abbr>.ics   one calendar per team (all 30)
  docs/baseball/national.ics nationally televised games
  docs/baseball/index.html   subscribe page

Data: ESPN's public (unofficial) MLB API. Python 3 stdlib only.
Unofficial; not affiliated with MLB or ESPN.

Season year: ESPN's season year is the calendar year of that season (2026).
Calendar names do not include a year. The year is read from ESPN's scoreboard
so it rolls over on its own. While a postseason is still in progress the
scoreboard stays on that season, postseason games included. Next year's schedule
is picked up when ESPN's scoreboard year rolls, or with --season.

Which games:
  seasontype 2  regular season, including doubleheaders and official games
                that were shortened by weather
  seasontype 3  postseason (wild card through the World Series)
  Spring training (seasontype 1) and the All-Star game are skipped.

National TV: a broadcast counts as national when ESPN marks its market as
national (market type "National") and the medium is TV or streaming, not
radio. Networks that appear that way include Fox, FS1, ESPN, TBS, MLB Network,
Apple TV, Peacock, Prime Video, Netflix, and ESPN Unlimited. MLB.TV is on
essentially every game and is not treated as a national broadcast.

Doubleheaders are two ESPN events, so each keeps its own UID. Postponed and
cancelled games stay in the feed as STATUS:CANCELLED under the same
espn-<id> UID; they do not count toward the 162. ESPN's makeup is almost
always a new event (often the other half of a doubleheader) and gets its
own stable UID. Suspended games keep their original UID and move when ESPN
updates that event's date.

Regular-season count: 162 games, give or take rainouts whose makeups are not
listed yet and the occasional game missing from ESPN. This script accepts
154–170 playable games per team once a season is on the board, and still
writes whatever ESPN has published when a future season is not out yet
(every team well short of that range). A mix — some teams in range and some
not — is treated as a bad feed and nothing is overwritten.

Usage: python3 baseball/generate.py [--season YEAR] [--out DIR]
Exit codes: 0 = ok (files written only if content changed), 1 = fetch/validation failure
(nothing is overwritten in that case).
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

# ---- Change this if the site is hosted somewhere else (must end with "/") ----
BASE_URL = os.environ.get("MLB_CAL_BASE_URL", "https://jaxzn.github.io/calendars/baseball/")

API = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
ET = ZoneInfo("America/New_York")
UID_DOMAIN = "mlb-calendars"
GAME_DURATION = timedelta(hours=3)
REFRESH = "PT6H"
PRODID = "-//jaxzn//MLB Calendars//EN"
# 162 is a full regular season. The window covers rainouts whose makeup games
# are not in the feed yet, and a game or two ESPN never lists.
REG_LO, REG_HI = 154, 170
SEASON_TYPES = (2, 3)  # regular, postseason
LEAGUE = "MLB"
NATIONAL_TITLE = "MLB National TV"
TEAM_COUNT = 30

# ESPN truncates a few network names. The feed's shortName is kept otherwise.
DISPLAY_NAMES = {
    "ESPN Unlmtd": "ESPN Unlimited",
    "MLB Net": "MLB Network",
}

# (abbr, display name, ESPN team id). Abbreviations match the schedule feed.
CONFERENCES = [
    ("American League", [
        ("AL East", [
            ("BAL", "Baltimore Orioles", "1"),
            ("BOS", "Boston Red Sox", "2"),
            ("NYY", "New York Yankees", "10"),
            ("TB", "Tampa Bay Rays", "30"),
            ("TOR", "Toronto Blue Jays", "14"),
        ]),
        ("AL Central", [
            ("CHW", "Chicago White Sox", "4"),
            ("CLE", "Cleveland Guardians", "5"),
            ("DET", "Detroit Tigers", "6"),
            ("KC", "Kansas City Royals", "7"),
            ("MIN", "Minnesota Twins", "9"),
        ]),
        ("AL West", [
            ("ATH", "Athletics", "11"),
            ("HOU", "Houston Astros", "18"),
            ("LAA", "Los Angeles Angels", "3"),
            ("SEA", "Seattle Mariners", "12"),
            ("TEX", "Texas Rangers", "13"),
        ]),
    ]),
    ("National League", [
        ("NL East", [
            ("ATL", "Atlanta Braves", "15"),
            ("MIA", "Miami Marlins", "28"),
            ("NYM", "New York Mets", "21"),
            ("PHI", "Philadelphia Phillies", "22"),
            ("WSH", "Washington Nationals", "20"),
        ]),
        ("NL Central", [
            ("CHC", "Chicago Cubs", "16"),
            ("CIN", "Cincinnati Reds", "17"),
            ("MIL", "Milwaukee Brewers", "8"),
            ("PIT", "Pittsburgh Pirates", "23"),
            ("STL", "St. Louis Cardinals", "24"),
        ]),
        ("NL West", [
            ("ARI", "Arizona Diamondbacks", "29"),
            ("COL", "Colorado Rockies", "27"),
            ("LAD", "Los Angeles Dodgers", "19"),
            ("SD", "San Diego Padres", "25"),
            ("SF", "San Francisco Giants", "26"),
        ]),
    ]),
]
TEAMS = {abbr: name for _, divs in CONFERENCES for _, teams in divs for abbr, name, _id in teams}
TEAM_IDS = {abbr: tid for _, divs in CONFERENCES for _, teams in divs for abbr, _name, tid in teams}
ID_TO_ABBR = {tid: abbr for abbr, tid in TEAM_IDS.items()}


# ----------------------------------------------------------------- fetching
def fetch_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mlb-calendars/1.0 (+github.com/jaxzn)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def season_label(year):
    """ESPN year is the calendar year of the season: 2026 -> 2026."""
    return str(year)


def detect_season():
    """ESPN season year from the current scoreboard, else a date heuristic
    (January still belongs to the previous season)."""
    try:
        d = fetch_json(f"{API}/scoreboard")
        y = (d.get("season") or {}).get("year") or d["leagues"][0]["season"]["year"]
        return int(y)
    except Exception as e:  # noqa: BLE001
        now = datetime.now(ET)
        y = now.year if now.month >= 2 else now.year - 1
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
def _market_type(b):
    market = b.get("market")
    if isinstance(market, dict):
        return (market.get("type") or "").strip().lower()
    return str(market or "").strip().lower()


def _medium(b):
    btype = b.get("type")
    if isinstance(btype, dict):
        return (btype.get("shortName") or "").strip().lower()
    return str(btype or "").strip().lower()


def _label(b):
    media = b.get("media") if isinstance(b.get("media"), dict) else {}
    label = (media.get("shortName") or "").strip()
    if not label:
        names = b.get("names") or []
        label = names[0].strip() if names else ""
    return DISPLAY_NAMES.get(label, label)


def _is_pass(label):
    """Out-of-market packages are not a national broadcast."""
    s = label.lower()
    flat = s.replace(".", "").replace(" ", "")
    return "league pass" in s or "mlbtv" in flat


def broadcast_lists(comp):
    """Return (national_names, local_names). See module docstring for the rule."""
    national, local = [], []
    for b in comp.get("broadcasts") or []:
        kind = _medium(b)
        if kind == "radio":
            continue
        label = _label(b)
        if not label or _is_pass(label):
            continue
        if kind not in ("tv", "streaming", ""):
            continue
        market_type = _market_type(b)
        bucket = national if market_type == "national" else local if market_type in ("home", "away", "") else None
        if bucket is not None and label not in bucket:
            bucket.append(label)
    return national, local


def status_type(e, c):
    return ((c.get("status") or {}).get("type") or (e.get("status") or {}).get("type") or {})


def disposition(status):
    """ok, postponed, cancelled, or suspended. Postponed/cancelled stay on the
    calendar as STATUS:CANCELLED; suspended games stay live under the same UID."""
    name = (status.get("name") or "").upper()
    detail = f"{status.get('description') or ''} {status.get('detail') or ''}".upper()
    blob = name + " " + detail
    if "POSTPON" in blob:
        return "postponed"
    if "CANCEL" in blob:
        return "cancelled"
    if "SUSPEND" in blob:
        return "suspended"
    return "ok"


def score_display(score):
    if score is None or score == "":
        return None
    if isinstance(score, dict):
        text = score.get("displayValue")
        if text not in (None, ""):
            return str(text)
        if score.get("value") is None:
            return None
        value = score["value"]
        return str(int(value)) if float(value).is_integer() else str(value)
    return str(score)


def team_abbr(team):
    """Schedule abbreviation, mapped by ESPN team id when we know the club."""
    tid = str(team.get("id") or "")
    if tid in ID_TO_ABBR:
        return ID_TO_ABBR[tid]
    return team.get("abbreviation") or "TBD"


def parse_event(e, seasontype):
    c = e["competitions"][0]
    sides = {x["homeAway"]: x for x in c["competitors"]}
    away_team, home_team = sides["away"]["team"], sides["home"]["team"]
    st = e.get("seasonType") or {}
    if isinstance(st, dict) and st.get("type"):
        seasontype = int(st["type"])
    notes = [n.get("headline") for n in c.get("notes") or [] if n.get("headline")]
    headline = notes[0] if notes else ""
    blob = f"{e.get('name', '')} {headline}".lower()
    if "all-star" in blob or "all star" in blob:
        return None
    if away_team.get("isAllStar") or home_team.get("isAllStar"):
        return None
    if seasontype == 1:
        return None
    status = status_type(e, c)
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
    for team in (away_team, home_team):
        ab = team_abbr(team)
        primary = norm_hex(team.get("color"))
        if ab and primary and ab in TEAMS:
            colors[ab] = (primary, norm_hex(team.get("alternateColor")) or primary)
    return dict(
        id=str(e["id"]), seasontype=seasontype, start=start, valid=valid,
        away_abbr=team_abbr(away_team), home_abbr=team_abbr(home_team),
        away=away_team.get("shortDisplayName") or away_team.get("displayName") or "TBD",
        home=home_team.get("shortDisplayName") or home_team.get("displayName") or "TBD",
        away_full=away_team.get("displayName") or "", home_full=home_team.get("displayName") or "",
        national=national, local=local, tv=" / ".join(shown),
        venue=venue.get("fullName") or "", place=place,
        completed=bool(status.get("completed")),
        away_score=score_display(sides["away"].get("score")),
        home_score=score_display(sides["home"].get("score")),
        headline=headline, colors=colors, disposition=disposition(status),
    )


def richer(a, b):
    """Prefer the copy of a game that has more broadcast names."""
    return b if len(b["national"]) + len(b["local"]) > len(a["national"]) + len(a["local"]) else a


def fetch_team_meta():
    """Colors and names from the teams endpoint, keyed by our schedule abbreviation.
    Logo URLs are ignored."""
    d = fetch_json(f"{API}/teams?limit=50")
    found = {}
    for t in d["sports"][0]["leagues"][0]["teams"]:
        tm = t.get("team") or t
        if tm.get("isAllStar"):
            continue
        tid = str(tm.get("id") or "")
        abbr = ID_TO_ABBR.get(tid) or tm.get("abbreviation")
        if not abbr:
            continue
        found[abbr] = (
            tid,
            tm.get("displayName") or "",
            norm_hex(tm.get("color")),
            norm_hex(tm.get("alternateColor")),
        )
    return found


def collect(season):
    games, label = {}, None
    for _abbr, tid in TEAM_IDS.items():
        for st in SEASON_TYPES:
            d = fetch_json(f"{API}/teams/{tid}/schedule?season={season}&seasontype={st}")
            if st == 2:
                req = d.get("requestedSeason") or {}
                if req.get("displayName"):
                    label = req["displayName"]
            for e in d.get("events") or []:
                try:
                    g = parse_event(e, st)
                except Exception as err:  # noqa: BLE001
                    raise RuntimeError(f"could not parse event {e.get('id')}: {err}") from err
                if g is None:
                    continue
                games[g["id"]] = richer(games[g["id"]], g) if g["id"] in games else g
    return list(games.values()), label or season_label(season)


def playable(g):
    """Games that count toward the regular-season length. Postponed and
    cancelled listings do not; suspended games do, because they will be finished."""
    return g["disposition"] in ("ok", "suspended")


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
    if g["headline"]:
        return g["headline"]
    if g["seasontype"] == 2:
        return "Regular Season"
    return "Postseason"


def game_title(g):
    t = f"{g['away']} @ {g['home']}"
    if g["tv"]:
        t += f" ({g['tv']})"
    if g["disposition"] == "postponed":
        return "Postponed: " + t
    if g["disposition"] == "cancelled":
        return "Cancelled: " + t
    if g["disposition"] == "suspended" and not g["completed"]:
        return "Suspended: " + t
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
    if g["disposition"] == "postponed":
        desc.append("Postponed. This listing stays cancelled under the same id. "
                    "The makeup, when ESPN adds one, is a separate game.")
    elif g["disposition"] == "cancelled":
        desc.append("Cancelled.")
    elif g["disposition"] == "suspended" and not g["completed"]:
        desc.append("Suspended. If the resume date changes, ESPN updates this same game.")
    if not g["valid"] and g["disposition"] == "ok":
        desc.append(f"Date/time not yet set by the {LEAGUE}; this is a placeholder.")
    if g["disposition"] == "suspended" and not g["completed"] and g["away_score"] not in (None, ""):
        desc.append(f"Score at suspension: {g['away']} {g['away_score']}, {g['home']} {g['home_score']}")
    elif g["completed"] and g["disposition"] not in ("postponed", "cancelled") and g["away_score"] not in (None, ""):
        desc.append(f"Final: {g['away']} {g['away_score']}, {g['home']} {g['home_score']}")
    desc.append(f"Unofficial calendar; not affiliated with the {LEAGUE} or ESPN. Times may change.")
    if g["disposition"] in ("postponed", "cancelled"):
        ics_status = "CANCELLED"
    elif g["valid"]:
        ics_status = "CONFIRMED"
    else:
        ics_status = "TENTATIVE"
    lines.append("DESCRIPTION:" + esc("\n".join(desc)))
    lines += [f"STATUS:{ics_status}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    return lines


def calendar(name, desc, games, dtstamp):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:" + esc(name), "X-WR-CALDESC:" + esc(desc), "X-WR-TIMEZONE:America/New_York",
             f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH}", f"X-PUBLISHED-TTL:{REFRESH}"]
    for g in sorted(games, key=lambda g: (g["start"], g["id"])):
        lines += vevent(g, dtstamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def validate_ics(text):
    """Reject a calendar that is not a folded, parseable iCalendar feed."""
    if not text.endswith("\r\n"):
        raise RuntimeError("ICS missing trailing CRLF")
    physical = text.split("\r\n")
    if physical[-1] != "":
        raise RuntimeError("ICS missing trailing newline")
    physical.pop()
    logical = []
    for line in physical:
        if len(line.encode("utf-8")) > 75:
            raise RuntimeError(f"ICS line longer than 75 octets: {line[:40]!r}")
        if line.startswith((" ", "\t")):
            if not logical:
                raise RuntimeError("ICS continuation with nothing to continue")
            logical[-1] += line[1:]
        elif not line:
            raise RuntimeError("blank line inside ICS")
        else:
            logical.append(line)
    if not logical or logical[0] != "BEGIN:VCALENDAR" or logical[-1] != "END:VCALENDAR":
        raise RuntimeError("ICS missing VCALENDAR wrapper")
    props = {}
    depth = 0
    event = None
    uids = set()
    events = 0
    for line in logical:
        if line == "BEGIN:VCALENDAR":
            depth += 1
            continue
        if line == "END:VCALENDAR":
            depth -= 1
            continue
        if line == "BEGIN:VEVENT":
            if event is not None:
                raise RuntimeError("nested VEVENT")
            event = {}
            events += 1
            continue
        if line == "END:VEVENT":
            if event is None:
                raise RuntimeError("END:VEVENT without BEGIN")
            for key in ("UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "STATUS"):
                if key not in event:
                    raise RuntimeError(f"VEVENT missing {key}")
            if event.get("TRANSP") != "TRANSPARENT":
                raise RuntimeError("VEVENT missing TRANSP:TRANSPARENT")
            uid = event["UID"]
            if uid in uids:
                raise RuntimeError(f"duplicate UID {uid}")
            if not re.fullmatch(rf"espn-\d+@{re.escape(UID_DOMAIN)}", uid):
                raise RuntimeError(f"unexpected UID {uid}")
            if event["STATUS"] not in ("CONFIRMED", "TENTATIVE", "CANCELLED"):
                raise RuntimeError(f"bad STATUS {event['STATUS']}")
            start = event["DTSTART"]
            if not (re.fullmatch(r"\d{8}T\d{6}Z", start) or re.fullmatch(r"\d{8}", start)):
                raise RuntimeError(f"bad DTSTART {start}")
            uids.add(uid)
            event = None
            continue
        name, _, value = line.partition(":")
        name = name.split(";", 1)[0]
        if event is not None:
            event[name] = value
        elif depth == 1:
            props[name] = value
    if depth != 0 or event is not None:
        raise RuntimeError("unbalanced ICS components")
    if props.get("REFRESH-INTERVAL") != REFRESH:
        raise RuntimeError("missing REFRESH-INTERVAL PT6H")
    if "X-WR-CALNAME" not in props:
        raise RuntimeError("missing calendar name")
    return events


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
        '<p class="eyebrow">National TV</p><h2>MLB National TV</h2>'
        "<p>Games ESPN lists on a national broadcast: Fox, FS1, ESPN, TBS, MLB Network, Apple TV, Peacock, Prime Video, and the other national channels. "
        "MLB.TV is not treated as a national broadcast. Postseason games join this calendar once they are scheduled.</p></div>"
        f'{actions("national", "MLB National TV")}</article>'
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MLB {label} Calendars – subscribe to any team</title>
<meta name="description" content="Free, auto-updating MLB {label} schedule calendars for all 30 teams plus nationally televised games. Works with Apple, Google and Outlook Calendar.">
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<a class="skip" href="#calendars">Skip to calendars</a>
<div class="wrap">
<header class="top">
  <div>
    <p class="kicker"><a href="../">Calendars</a></p>
    <h1>MLB {label} Calendars</h1>
    <p class="lead">Every team's schedule, plus a national-TV calendar. Subscribe once and first-pitch times, channels, doubleheaders, and the postseason update automatically.</p>
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
<p>Subscribe instead of importing a one-time download, or the calendar will not update. First pitches are stored in UTC so your calendar shows them in your own time zone. Games whose date or time is not set yet appear as all-day placeholders until MLB schedules them. Each game of a doubleheader is its own event. A postponed game stays cancelled under its original listing; the makeup is a separate game once ESPN posts it. A suspended game keeps its original listing and moves if the resume date changes.</p>
</section>
<footer>
<p>Unofficial and not affiliated with, endorsed by, or connected to MLB, its teams, or ESPN. Schedule data comes from ESPN's public scoreboard feed and is refreshed automatically. Always confirm times with an official source.</p>
</footer>
</div>
<script src="../assets/subscribe.js" defer></script>
</body>
</html>
"""
    if "<img" in page or "espncdn" in page or "logo" in page.lower():
        raise RuntimeError("subscribe page would include an image or logo reference")
    return page


def schedule_published(counts):
    """True when ESPN has a real regular-season slate up. All teams short of
    the usual length means the next season is not published yet."""
    vals = list(counts.values())
    return any(n > REG_HI for n in vals) or any(REG_LO <= n <= REG_HI for n in vals)


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, help="ESPN season year, the calendar year of that season (2026)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "baseball"))
    a = ap.parse_args()

    season = a.season or detect_season()
    try:
        games, label = collect(season)
        meta = fetch_team_meta()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}\nNo files were changed.", file=sys.stderr)
        return 1

    names, colors, by_team = {}, {}, {t: [] for t in TEAMS}
    meta_ids = set()
    for abbr, (tid, display, primary, alt) in meta.items():
        meta_ids.add(tid)
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
    extra = sorted(meta_ids - set(TEAM_IDS.values()))
    missing = sorted(set(TEAM_IDS.values()) - meta_ids)
    if extra or missing or len(TEAMS) != TEAM_COUNT:
        print("ERROR: sanity check failed; no files were changed:\n  "
              f"team list mismatch: missing ids {missing} extra ids {extra} "
              f"teams={len(TEAMS)}", file=sys.stderr)
        return 1

    def reg_count(gs):
        return sum(g["seasontype"] == 2 and playable(g) for g in gs)

    problems = []
    counts = {t: reg_count(gs) for t, gs in by_team.items()}
    published = schedule_published(counts)
    reg_playable = [g for g in games if g["seasontype"] == 2 and playable(g)]
    if published:
        for t, n in sorted(counts.items()):
            if not REG_LO <= n <= REG_HI:
                problems.append(f"{t}: {n} regular-season games (expected {REG_LO}–{REG_HI})")
        slots = sum(1 for g in reg_playable for s in ("away", "home") if g[s + "_abbr"] in TEAMS)
        if slots != len(reg_playable) * 2:
            problems.append(f"regular-season games are not all between two known teams ({slots} team-slots, {len(reg_playable)} games)")
    else:
        lo = min(counts.values()) if counts else 0
        hi = max(counts.values()) if counts else 0
        print(f"warning: {label} regular season is not fully published "
              f"(per-team games {lo}–{hi}, expected {REG_LO}–{REG_HI} once the schedule is out). "
              "Writing the games ESPN has listed.", file=sys.stderr)
    unknown = {g[s + "_abbr"] for g in games if g["seasontype"] == 2 for s in ("away", "home")} - set(TEAMS) - {"TBD"}
    if unknown:
        problems.append(f"unknown team abbreviations in feed: {sorted(unknown)}")
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
    pending = []
    try:
        for t, gs in by_team.items():
            # No season year: calendar apps keep X-WR-CALNAME from subscribe time.
            name = names.get(t, TEAMS[t])
            c = calendar(name, f"{name} MLB schedule (unofficial, auto-updated)", gs, dtstamp)
            validate_ics(c)
            pending.append((os.path.join(a.out, t.lower() + ".ics"), c, True, t.lower() + ".ics"))
        nat = [g for g in games if g["national"]]
        c = calendar(NATIONAL_TITLE,
                     "MLB nationally televised games (unofficial, auto-updated)", nat, dtstamp)
        validate_ics(c)
        pending.append((os.path.join(a.out, "national.ics"), c, True, "national.ics"))
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}\nNo files were changed.", file=sys.stderr)
        return 1

    changed = []
    for path, content, ignore, label_name in pending:
        if write_if_changed(path, content, ignore):
            changed.append(label_name)
    if write_if_changed(os.path.join(a.out, "index.html"), page):
        changed.append("index.html")

    post = sum(g["seasontype"] == 3 and playable(g) for g in games)
    postponed = sum(g["disposition"] == "postponed" for g in games)
    suspended = sum(g["disposition"] == "suspended" for g in games)
    lo, hi = min(counts.values()), max(counts.values())
    print(f"season {season} ({label}): {len(reg_playable)} regular-season + {post} postseason games; "
          f"postponed={postponed} suspended={suspended}; "
          f"national.ics={len(nat)} events; per-team regular season {lo}–{hi}")
    for t in sorted(counts):
        gs = by_team[t]
        print(f"  {t}: regular={counts[t]} postseason={sum(g['seasontype']==3 and playable(g) for g in gs)} "
              f"postponed={sum(g['disposition']=='postponed' for g in gs)} total={len(gs)}")
    print(f"changed: {', '.join(changed) or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
