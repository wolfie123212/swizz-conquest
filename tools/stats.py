#!/usr/bin/env python3
"""Builds a private stats page for Swizz Conquest from the anonymous play
counts the game sends to PostHog.

Run from the game folder:
    python3 tools/stats.py          # leaves out your own games (played after visiting the site with ?me)
    python3 tools/stats.py --all    # counts your own games too

It needs private/stats_config.json (never uploaded; the private/ folder is gitignored):
    {"host": "https://us.posthog.com", "project_id": "12345", "personal_key": "phx_..."}

The page is written to private/stats.html and opened in your browser.
"""
import collections
import datetime
import html
import json
import os
import sys
import urllib.request
import webbrowser

CONFIG = "private/stats_config.json"
OUT = "private/stats.html"
EVENTS = ("visit", "game_start", "game_end", "game_quit")
BUILDING_NAMES = {"city": "City", "mine": "Swizz Mine", "station": "Train Station", "port": "Port",
                  "sam": "SAM Site", "fort": "Fort", "silo": "Missile Silo", "rocket": "Launch Site", "sub": "Submarine"}


def fetch(config):
    query = ("select event, distinct_id, timestamp, properties from events where event in ("
             + ", ".join(f"'{e}'" for e in EVENTS) + ") order by timestamp limit 100000")
    request = urllib.request.Request(
        f"{config['host'].rstrip('/')}/api/projects/{config['project_id']}/query/",
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": query}}).encode(),
        headers={"Authorization": f"Bearer {config['personal_key']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        rows = json.load(response)["results"]
    events = []
    for event, who, when, props in rows:
        props = json.loads(props) if isinstance(props, str) else (props or {})
        events.append({"event": event, "who": who, "when": str(when)[:10], "p": props})
    return events


def pct(part, whole):
    return f"{round(100 * part / whole)}%" if whole else "–"


def bars(counts, total=None, color="#3ee6c1", label=lambda k: k):
    """A list of horizontal bars, biggest first."""
    if not counts:
        return "<p class=quiet>No data yet.</p>"
    top = max(counts.values())
    total = total or sum(counts.values())
    out = []
    for key, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        out.append(f"<div class=bar><span class=name>{html.escape(str(label(key)))}</span>"
                   f"<span class=track><span style='width:{100 * n / top:.1f}%;background:{color}'></span></span>"
                   f"<span class=num>{n} <small>({pct(n, total)})</small></span></div>")
    return "".join(out)


def win_table(ends, key):
    groups = collections.defaultdict(lambda: [0, 0])
    for e in ends:
        g = groups[key(e["p"])]
        g[1] += 1
        g[0] += e["p"].get("result") == "win"
    if not groups:
        return "<p class=quiet>No finished games yet.</p>"
    rows = "".join(f"<tr><td>{html.escape(str(k))}</td><td>{w} / {n}</td><td><b>{pct(w, n)}</b></td></tr>"
                   for k, (w, n) in sorted(groups.items(), key=lambda kv: -kv[1][1]))
    return f"<table><tr><th></th><th>Won / finished</th><th>Win rate</th></tr>{rows}</table>"


def heatmap(starts):
    """Where players put their first spot, on a map-shaped grid (the map is 3 wide by 2 tall)."""
    cols, rows = 30, 20
    grid = collections.Counter()
    for e in starts:
        x, y = e["p"].get("start_x"), e["p"].get("start_y")
        if x is not None and y is not None:
            grid[(min(cols - 1, x * cols // 100), min(rows - 1, y * rows // 100))] += 1
    top = max(grid.values(), default=1)
    cells = []
    for r in range(rows):
        for c in range(cols):
            n = grid[(c, r)]
            alpha = 0 if not n else .25 + .75 * n / top
            cells.append(f"<i title='{n} start{'s' if n != 1 else ''}' style='background:rgba(255,209,102,{alpha:.2f})'></i>")
    return f"<div class=heat style='grid-template-columns:repeat({cols},1fr)'>{''.join(cells)}</div>"


def days_chart(events):
    today = datetime.date.today()
    days = [today - datetime.timedelta(days=d) for d in range(29, -1, -1)]
    players = collections.defaultdict(set)
    games = collections.Counter()
    for e in events:
        players[e["when"]].add(e["who"])
        if e["event"] == "game_start":
            games[e["when"]] += 1
    top = max([len(players[str(d)]) for d in days] + [1])
    cols = []
    for d in days:
        n, g = len(players[str(d)]), games[str(d)]
        cols.append(f"<div class=day title='{d:%a %d %b}: {n} player{'s' if n != 1 else ''}, {g} game{'s' if g != 1 else ''}'>"
                    f"<span style='height:{100 * n / top:.0f}%'></span><small>{d.day if d.day in (1, 10, 20) or d == today else ''}</small></div>")
    return f"<div class=days>{''.join(cols)}</div>"


def build_page(events, include_owner):
    if not include_owner:
        events = [e for e in events if not e["p"].get("owner")]
    visits = [e for e in events if e["event"] == "visit"]
    starts = [e for e in events if e["event"] == "game_start"]
    ends = [e for e in events if e["event"] == "game_end"]
    quits = [e for e in events if e["event"] == "game_quit"]
    players = {e["who"] for e in events}
    games_by_player = collections.Counter(e["who"] for e in starts)
    returning = sum(1 for n in games_by_player.values() if n > 1)
    finished = ends + quits
    avg_minutes = sum(e["p"].get("minutes", 0) for e in finished) / len(finished) if finished else 0
    wins = sum(e["p"].get("result") == "win" for e in ends)
    week_ago = str(datetime.date.today() - datetime.timedelta(days=7))
    this_week = {e["who"] for e in events if e["when"] > week_ago}

    endings = collections.Counter()
    for e in ends:
        how = e["p"].get("how", "?")
        if e["p"].get("result") == "win":
            endings[{"conquest": "Won by conquest", "core": "Won by digging to the core", "space": "Won by launching a rocket"}.get(how, "Won")] += 1
        else:
            endings[{"fallen": "Lost: nation wiped out", "conquest": "Lost: a rival conquered the planet",
                     "core": "Lost: a rival reached the core", "space": "Lost: a rival reached space"}.get(how, "Lost")] += 1
    if quits:
        endings["Quit before the end"] = len(quits)

    built_total = collections.Counter()
    for e in finished:
        for kind, n in (e["p"].get("built") or {}).items():
            built_total[BUILDING_NAMES.get(kind, kind)] += n

    spot = collections.Counter()
    for e in starts:
        p = e["p"]
        spot["On an island" if p.get("island") else "On a continent"] += 1
        spot["By the sea" if p.get("coast") else "Inland"] += 1
    start_of = {e["p"].get("game"): e["p"] for e in starts}

    def start_kind(p):
        s = start_of.get(p.get("game"), {})
        return ("Island" if s.get("island") else "Continent") + (", by the sea" if s.get("coast") else ", inland")

    colours = collections.Counter(e["p"].get("color", "?") for e in starts)
    colour_bars = "".join(
        f"<div class=bar><span class=name><b class=swatch style='background:{html.escape(c)}'></b></span>"
        f"<span class=track><span style='width:{100 * n / max(colours.values()):.1f}%;background:{html.escape(c)}'></span></span>"
        f"<span class=num>{n} <small>({pct(n, len(starts))})</small></span></div>"
        for c, n in colours.most_common()) or "<p class=quiet>No data yet.</p>"

    big = lambda value, label: f"<div class=big><b>{value}</b><span>{label}</span></div>"
    return f"""<!DOCTYPE html><html><head><meta charset=utf-8><title>Swizz Conquest stats</title><style>
body {{ background:#16102a; color:#f1ecff; font:15px/1.4 ui-monospace,Menlo,monospace; max-width:960px; margin:30px auto; padding:0 20px; }}
h1 {{ color:#ffd166; margin-bottom:0; }} h2 {{ color:#3ee6c1; font-weight:normal; margin:34px 0 10px; border-bottom:2px solid #3a2c57; padding-bottom:4px; }}
.quiet, small {{ color:#8d7fb0; }}
.bigs {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-top:20px; }}
.big {{ background:#221a3d; border:2px solid #3a2c57; padding:12px; }} .big b {{ display:block; font-size:28px; color:#ffd166; }} .big span {{ color:#b3a4d6; font-size:13px; }}
.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:30px; }} @media (max-width:700px) {{ .cols {{ grid-template-columns:1fr; }} }}
.bar {{ display:grid; grid-template-columns:200px 1fr 110px; gap:10px; align-items:center; margin:5px 0; }}
.track {{ background:#221a3d; height:16px; }} .track span {{ display:block; height:100%; }}
.num {{ text-align:right; }} .swatch {{ display:inline-block; width:40px; height:14px; }}
table {{ border-collapse:collapse; width:100%; }} td, th {{ padding:5px 8px; border-bottom:1px solid #3a2c57; text-align:left; }} th {{ color:#8d7fb0; font-weight:normal; }}
.heat {{ display:grid; aspect-ratio:3/2; background:#0f0b1e; border:2px solid #3a2c57; max-width:600px; }} .heat i {{ display:block; }}
.days {{ display:flex; gap:3px; height:140px; align-items:flex-end; }} .day {{ flex:1; height:100%; display:flex; flex-direction:column; justify-content:flex-end; text-align:center; }}
.day span {{ background:#3ee6c1; min-height:2px; }} .day small {{ height:16px; font-size:10px; }}
</style></head><body>
<h1>Swizz Conquest stats</h1>
<p class=quiet>Updated {datetime.datetime.now():%a %d %b %Y, %H:%M}. {"Includes your own games." if include_owner else "Your own games are left out."} Players are anonymous: each browser counts as one player.</p>
<div class=bigs>
{big(len(players), "players ever")}
{big(len(this_week), "players this week")}
{big(len(starts), "games started")}
{big(returning, "players who came back for more")}
{big(f"{avg_minutes:.0f} min", "average game")}
{big(pct(wins, len(ends)), "of finished games won")}
</div>
<h2>Players each day (last 30 days)</h2>{days_chart(events)}
<div class=cols>
<div><h2>Favourite game mode</h2>{bars(collections.Counter(e["p"].get("mode", "?") for e in starts))}</div>
<div><h2>Favourite difficulty</h2>{bars(collections.Counter(e["p"].get("difficulty", "?") for e in starts), color="#ffd166")}</div>
</div>
<div class=cols>
<div><h2>Win rate by difficulty</h2>{win_table(ends, lambda p: p.get("difficulty", "?"))}</div>
<div><h2>Win rate by game mode</h2>{win_table(ends, lambda p: p.get("mode", "?"))}</div>
</div>
<h2>How games end</h2>{bars(endings, color="#ff6b6b")}
<h2>Where people start</h2>
<p class=quiet>Each square is a part of the map; brighter means more players started there. (Maps are random each game, so this shows the side of the map people like, not one exact place.)</p>
{heatmap(starts)}
<div class=cols>
<div><h2>Kind of starting spot</h2>{bars(spot, total=len(starts), color="#7c8cff")}</div>
<div><h2>Win rate by starting spot</h2>{win_table(ends, start_kind)}</div>
</div>
<div class=cols>
<div><h2>Favourite colour</h2>{colour_bars}</div>
<div><h2>Buildings people had when the game ended</h2>{bars(built_total, color="#c66bff")}</div>
</div>
<h2>Most games played (anonymous players)</h2>
{bars(dict(games_by_player.most_common(10)), total=len(starts), color="#7edc5a")}
<p class=quiet>{len(visits)} visits to the page in total.</p>
</body></html>"""


def main():
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    if not os.path.exists(CONFIG):
        sys.exit(f"Missing {CONFIG}. See the top of this file for what goes in it.")
    config = json.load(open(CONFIG))
    events = fetch(config)
    os.makedirs("private", exist_ok=True)
    open(OUT, "w").write(build_page(events, "--all" in sys.argv))
    print(f"Wrote {OUT} from {len(events)} events")
    if "--no-open" not in sys.argv:
        webbrowser.open("file://" + os.path.abspath(OUT))


if __name__ == "__main__":
    main()
