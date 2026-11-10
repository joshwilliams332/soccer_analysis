"""Turn raw FPL data into the site's data files.

Reads <out>/raw/ (see fpl.py), writes <out>/build/:
  teams.json     team table: xG for / against (season, last 6, home, away), expected points, finishing, ranks
  players.json   every player who has played: xG, xA, xGI per 90, share of team chances, minutes, availability
  matches.json   finished matches with score and team xG
  fixtures.json  next two gameweeks: projected goals, win / draw / loss, over 2.5, BTTS, clean sheets,
                 likely scores, players to watch, unavailable players
  meta.json      build time, season, gameweek, model settings, warnings
  accuracy.json  season replay score and graded pre-kickoff previews (see accuracy.py)
Also writes <out>/log/previews/<fixture>.json before kickoff (frozen once the match starts).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import accuracy  # noqa: E402
import model  # noqa: E402

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
PLAYER_PRIOR_MIN = 450   # pull per-90 rates toward the position average by 5 matches' worth of minutes
LAST_N = 6               # "recent form" window for teams
MIN_LAST = 4             # matches used for expected minutes
OUT_STATUSES = {"i", "s", "u", "n"}
MODEL_VERSION = model.VERSION


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def r(x, n=2):
    return None if x is None else round(x, n)


def per_game(total, games):
    return total / games if games else None


def load(raw, name):
    with open(os.path.join(raw, name), encoding="utf-8") as fh:
        return json.load(fh)


def save(build, name, data):
    os.makedirs(build, exist_ok=True)
    with open(os.path.join(build, name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))


def rank(rows, key, higher_is_better=True, field=None, eligible=lambda row: True):
    """Write 1 = best into row['ranks'][field] among eligible rows with a value."""
    field = field or key
    pool = [row for row in rows if eligible(row) and row.get(key) is not None]
    pool.sort(key=lambda row: row[key], reverse=higher_is_better)
    for i, row in enumerate(pool):
        row.setdefault("ranks", {})[field] = {"rank": i + 1, "of": len(pool)}


def season_label(events):
    if not events:
        return None
    y = int(events[0]["deadline_time"][:4])
    return f"{y}-{(y + 1) % 100:02d}"


def build(raw_dir, build_dir, now=None, log_dir=None):
    now = now or datetime.now(timezone.utc)
    boot = load(raw_dir, "bootstrap.json")
    fixtures = load(raw_dir, "fixtures.json")
    histories = load(raw_dir, "histories.json")
    warnings = []

    teams = {t["id"]: t for t in boot["teams"]}
    short = {t["id"]: t["short_name"] for t in boot["teams"]}
    elements = {p["id"]: p for p in boot["elements"] if p.get("element_type") in POS}
    fx_by_id = {fx["id"]: fx for fx in fixtures}

    # Team xG / xA per match, summed from the players who played it.
    side_xg, side_xa = {}, {}
    for pid, rows in histories.items():
        for row in rows:
            fx = fx_by_id.get(row.get("fixture"))
            if not fx:
                continue
            side = "h" if row.get("was_home") else "a"
            k = (fx["id"], side)
            side_xg[k] = side_xg.get(k, 0.0) + f(row.get("expected_goals"))
            side_xa[k] = side_xa.get(k, 0.0) + f(row.get("expected_assists"))

    finished = sorted((fx for fx in fixtures if fx.get("finished") and fx.get("kickoff_time")),
                      key=lambda fx: fx["kickoff_time"])
    matches = []
    for fx in finished:
        has_xg = (fx["id"], "h") in side_xg or (fx["id"], "a") in side_xg
        if not has_xg:
            warnings.append(f"no player stats yet for fixture {fx['id']} "
                            f"({short.get(fx['team_h'])}-{short.get(fx['team_a'])}); using goals only")
        matches.append({
            "id": fx["id"], "gw": fx.get("event"), "kickoff": fx["kickoff_time"],
            "home": fx["team_h"], "away": fx["team_a"],
            "hg": fx.get("team_h_score") or 0, "ag": fx.get("team_a_score") or 0,
            "hxg": side_xg.get((fx["id"], "h")) if has_xg else None,
            "axg": side_xg.get((fx["id"], "a")) if has_xg else None,
        })

    priors = model.load_priors({tid: t["name"] for tid, t in teams.items()})
    strengths, avg = model.fit(matches, priors)

    # ---- Teams ----
    team_games = {tid: [] for tid in teams}
    for m in matches:
        for tid, home in ((m["home"], True), (m["away"], False)):
            gf, ga = (m["hg"], m["ag"]) if home else (m["ag"], m["hg"])
            xf, xa = (m["hxg"], m["axg"]) if home else (m["axg"], m["hxg"])
            team_games.setdefault(tid, []).append({
                "id": m["id"], "home": home, "gf": gf, "ga": ga, "xgf": xf, "xga": xa,
                "res": "W" if gf > ga else "D" if gf == ga else "L",
            })

    def split(games):
        xgg = [g for g in games if g["xgf"] is not None]
        return {
            "gp": len(games),
            "gf_pg": r(per_game(sum(g["gf"] for g in games), len(games))),
            "ga_pg": r(per_game(sum(g["ga"] for g in games), len(games))),
            "xgf_pg": r(per_game(sum(g["xgf"] for g in xgg), len(xgg))),
            "xga_pg": r(per_game(sum(g["xga"] for g in xgg), len(xgg))),
        }

    team_rows = []
    for tid, t in teams.items():
        games = team_games.get(tid, [])
        xgg = [g for g in games if g["xgf"] is not None]
        pts = sum(3 if g["res"] == "W" else 1 if g["res"] == "D" else 0 for g in games)
        xpts = sum(model.expected_points(g["xgf"], g["xga"]) for g in xgg)
        pts_xg_games = sum(3 if g["res"] == "W" else 1 if g["res"] == "D" else 0 for g in xgg)
        s = strengths.get(tid, {"att": 1.0, "def": 1.0, "n": 0})
        row = {
            "id": tid, "name": t["name"], "short": t["short_name"],
            "gp": len(games),
            "w": sum(g["res"] == "W" for g in games), "d": sum(g["res"] == "D" for g in games),
            "l": sum(g["res"] == "L" for g in games),
            "gf": sum(g["gf"] for g in games), "ga": sum(g["ga"] for g in games), "pts": pts,
            "xgf": r(sum(g["xgf"] for g in xgg)), "xga": r(sum(g["xga"] for g in xgg)),
            "xgd_pg": r(per_game(sum(g["xgf"] - g["xga"] for g in xgg), len(xgg))),
            "xpts": r(xpts, 1),
            "pts_minus_xpts": r(pts_xg_games - xpts, 1),
            "finishing": r(sum(g["gf"] - g["xgf"] for g in xgg)),       # + = scoring more than chances
            "conceding": r(sum(g["ga"] - g["xga"] for g in xgg)),       # + = conceding more than chances
            "form": [g["res"] for g in games[-LAST_N:]],
            "season": split(games), "last6": split(games[-LAST_N:]),
            "home": split([g for g in games if g["home"]]), "away": split([g for g in games if not g["home"]]),
            "attack": r(s["att"], 3), "defense": r(s["def"], 3),
        }
        for k in ("xgf_pg", "xga_pg", "gf_pg", "ga_pg"):
            row[k] = row["season"][k]
        row["xgf_pg_l6"], row["xga_pg_l6"] = row["last6"]["xgf_pg"], row["last6"]["xga_pg"]
        team_rows.append(row)

    rank(team_rows, "xgf_pg")
    rank(team_rows, "xga_pg", higher_is_better=False)
    rank(team_rows, "xgd_pg")
    rank(team_rows, "xgf_pg_l6")
    rank(team_rows, "xga_pg_l6", higher_is_better=False)
    rank(team_rows, "xpts")
    rank(team_rows, "pts")
    team_rows.sort(key=lambda t: (-t["pts"], -(t["gf"] - t["ga"]), -t["gf"], t["name"]))
    for i, t in enumerate(team_rows):
        t["pos"] = i + 1
        t["gd"] = t["gf"] - t["ga"]

    # ---- Players ----
    team_finished = {tid: [g["id"] for g in games] for tid, games in team_games.items()}
    player_rows = []
    for pid_s, rows in histories.items():
        p = elements.get(int(pid_s))
        if not p:
            continue
        played = [row for row in rows if row.get("minutes", 0) > 0]
        mins = sum(row["minutes"] for row in played)
        tot = lambda k: sum(f(row.get(k)) for row in played)  # noqa: E731
        team_xg_on = sum(side_xg.get((row["fixture"], "h" if row["was_home"] else "a"), 0.0) for row in played)
        team_xa_on = sum(side_xa.get((row["fixture"], "h" if row["was_home"] else "a"), 0.0) for row in played)
        by_fixture = {row["fixture"]: row.get("minutes", 0) for row in rows}
        recent = team_finished.get(p["team"], [])[-MIN_LAST:]
        avg_min = sum(by_fixture.get(fid, 0) for fid in recent) / len(recent) if recent else 0.0
        chance = p.get("chance_of_playing_next_round")
        status = p.get("status", "a")
        if chance is None:
            chance = 0 if status in OUT_STATUSES else 100
        xg, xa = tot("expected_goals"), tot("expected_assists")
        p90 = lambda v: v / mins * 90 if mins else None  # noqa: E731
        player_rows.append({
            "id": p["id"], "name": p["web_name"], "full": f"{p['first_name']} {p['second_name']}",
            "team": p["team"], "team_short": short.get(p["team"]), "pos": POS[p["element_type"]],
            "apps": len(played), "starts": int(tot("starts")), "min": mins,
            "g": int(tot("goals_scored")), "a": int(tot("assists")),
            "xg": r(xg), "xa": r(xa), "xgi": r(xg + xa), "xgc": r(tot("expected_goals_conceded")),
            "xg90": r(p90(xg)), "xa90": r(p90(xa)), "xgi90": r(p90(xg + xa)),
            "xgc90": r(p90(tot("expected_goals_conceded"))),
            "g_minus_xg": r(tot("goals_scored") - xg),
            "dc90": r(p90(tot("defensive_contribution"))), "saves90": r(p90(tot("saves"))),
            "yc": int(tot("yellow_cards")), "rc": int(tot("red_cards")),
            "xg_share": r(xg / team_xg_on, 3) if team_xg_on else None,
            "xa_share": r(xa / team_xa_on, 3) if team_xa_on else None,
            "min_l4": r(avg_min, 1),
            "status": status, "chance": chance, "news": p.get("news") or "",
            "pens": p.get("penalties_order"), "corners": p.get("corners_and_indirect_freekicks_order"),
            "fks": p.get("direct_freekicks_order"),
            "cost": (p.get("now_cost") or 0) / 10, "own": f(p.get("selected_by_percent")),
            "fpl_pts": p.get("total_points", 0), "cs": int(tot("clean_sheets")),
        })

    gws_played = max((m["gw"] or 0 for m in matches), default=0)
    min_minutes = 90 * max(3, int(0.3 * gws_played))
    for pos in POS.values():
        ok = lambda row, pos=pos: row["pos"] == pos and row["min"] >= min_minutes  # noqa: E731
        for key in ("xg90", "xa90", "xgi90", "dc90"):
            rank(player_rows, key, eligible=ok, field=f"{key}_pos")
        if pos in ("GKP", "DEF"):
            rank(player_rows, "xgc90", higher_is_better=False, eligible=ok, field="xgc90_pos")
    player_rows.sort(key=lambda p: -(p["xgi"] or 0))

    # Position average rates, for steadying small samples.
    pos_rate = {}
    for pos in POS.values():
        ps = [p for p in player_rows if p["pos"] == pos]
        m = sum(p["min"] for p in ps)
        pos_rate[pos] = {
            "xg90": sum(p["xg"] for p in ps) / m * 90 if m else 0.0,
            "xa90": sum(p["xa"] for p in ps) / m * 90 if m else 0.0,
        }

    def steady(p, key):
        total = p["xg"] if key == "xg90" else p["xa"]
        return (total + pos_rate[p["pos"]][key] * PLAYER_PRIOR_MIN / 90) / ((p["min"] + PLAYER_PRIOR_MIN) / 90)

    # ---- Upcoming fixtures ----
    events = boot.get("events", [])
    next_gw = next((e["id"] for e in events if e.get("is_next")), None)
    if next_gw is None:
        upcoming_gws = sorted({fx["event"] for fx in fixtures if not fx.get("finished") and fx.get("event")})
        next_gw = upcoming_gws[0] if upcoming_gws else None
    neutral = (avg["home"] + avg["away"]) / 2
    by_team = {}
    for p in player_rows:
        by_team.setdefault(p["team"], []).append(p)

    def side_players(tid, lam):
        s = strengths.get(tid, {"att": 1.0})
        factor = min(max(lam / (neutral * s["att"]), 0.5), 2.0) if neutral else 1.0
        watch, out = [], []
        for p in by_team.get(tid, []):
            exp_min = min(p["min_l4"] * p["chance"] / 100, 90)
            if p["status"] != "a" and p["min"] >= 180:
                out.append({"id": p["id"], "name": p["name"], "pos": p["pos"], "status": p["status"],
                            "chance": p["chance"], "news": p["news"]})
            if exp_min < 30:
                continue
            exg = steady(p, "xg90") * exp_min / 90 * factor
            exa = steady(p, "xa90") * exp_min / 90 * factor
            watch.append({"id": p["id"], "name": p["name"], "pos": p["pos"], "exp_min": r(exp_min, 0),
                          "exp_xg": r(exg), "exp_xa": r(exa),
                          "p_goal": r(model.chance_at_least_one(exg), 3),
                          "p_assist": r(model.chance_at_least_one(exa), 3),
                          "pens": p["pens"] == 1})
        watch.sort(key=lambda w: -(w["exp_xg"] + w["exp_xa"]))
        return watch[:5], out

    upcoming = []
    if next_gw:
        for fx in sorted(fixtures, key=lambda fx: fx.get("kickoff_time") or ""):
            if fx.get("finished") or fx.get("event") not in (next_gw, next_gw + 1):
                continue
            lh, la = model.project(fx["team_h"], fx["team_a"], strengths, avg)
            probs = model.match_probs(lh, la)
            hw, hout = side_players(fx["team_h"], lh)
            aw, aout = side_players(fx["team_a"], la)
            upcoming.append({
                "id": fx["id"], "gw": fx["event"], "kickoff": fx.get("kickoff_time"),
                "home": fx["team_h"], "away": fx["team_a"],
                "home_short": short.get(fx["team_h"]), "away_short": short.get(fx["team_a"]),
                "proj": {"home": r(lh), "away": r(la)},
                "probs": {k: (r(v, 3) if isinstance(v, float) else v) for k, v in probs.items() if k != "scores"},
                "scores": [{"h": s["h"], "a": s["a"], "p": r(s["p"], 3)} for s in probs["scores"]],
                "watch": {"home": hw, "away": aw}, "out": {"home": hout, "away": aout},
            })

    match_rows = [{
        "id": m["id"], "gw": m["gw"], "kickoff": m["kickoff"], "home": m["home"], "away": m["away"],
        "home_short": short.get(m["home"]), "away_short": short.get(m["away"]),
        "hg": m["hg"], "ag": m["ag"], "hxg": r(m["hxg"]), "axg": r(m["axg"]),
    } for m in matches]

    meta = {
        "built": now.isoformat(timespec="seconds"), "season": season_label(events),
        "last_finished_gw": max((e["id"] for e in events if e.get("finished")), default=None),
        "next_gw": next_gw, "matches": len(matches), "players": len(player_rows),
        "league_avg": {"home": r(avg["home"]), "away": r(avg["away"])},
        "model": {"version": MODEL_VERSION, "xg_weight": model.XG_WEIGHT, "half_life": model.HALF_LIFE,
                  "prior_games": model.PRIOR_GAMES, "rho": model.RHO, "promoted": model.PROMOTED,
                  "priors": "last season's end strengths" if priors else "none (league average)",
                  "player_prior_min": PLAYER_PRIOR_MIN,
                  "status": "backtested 2022-23 to 2026-27: better than a base-rate baseline, not better than closing odds"},
        "source": "Fantasy Premier League public data (player xG / xA include penalties)",
        "warnings": warnings,
    }

    # ---- Accuracy: season replay + frozen pre-kickoff previews graded once played ----
    acc = {"replay": accuracy.replay(matches, priors), "replay_from_gw": accuracy.REPLAY_FROM, "live": {"n": 0}, "graded": []}
    if log_dir:
        accuracy.snapshot(log_dir, upcoming, now.strftime("%Y-%m-%dT%H:%M:%SZ"), MODEL_VERSION)
        acc["live"], acc["graded"] = accuracy.grade_live(log_dir, matches)
    save(build_dir, "accuracy.json", acc)

    save(build_dir, "teams.json", team_rows)
    save(build_dir, "players.json", player_rows)
    save(build_dir, "matches.json", match_rows)
    save(build_dir, "fixtures.json", upcoming)
    save(build_dir, "meta.json", meta)

    # ---- Public files (no model output): schedule with free odds, last gameweek ----
    save(build_dir, "schedule.json", schedule(fixtures, next_gw, short, teams, upcoming, raw_dir))
    save(build_dir, "gameweek.json", last_gameweek(matches, histories, elements, short, POS))
    return meta


def american(dec):
    """Decimal odds -> American (e.g. 2.5 -> +150, 1.5 -> -200)."""
    if not dec or dec <= 1:
        return None
    return round((dec - 1) * 100) if dec >= 2 else -round(100 / (dec - 1))


def load_fixture_odds(raw_dir):
    """{(date, home key, away key): odds} from football-data.co.uk fixtures.csv (average of bookmakers)."""
    import csv
    path = os.path.join(raw_dir, "odds_fixtures.csv")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                d = datetime.strptime(r["Date"], "%d/%m/%Y" if len(r["Date"]) == 10 else "%d/%m/%y").date()
            except (KeyError, ValueError):
                continue
            price = {}
            for pre, label in (("Avg", "avg"), ("B365", "b365")):
                h, dr, a = (f(r.get(pre + k)) for k in "HDA")
                if h > 1 and dr > 1 and a > 1:
                    price = {"h": h, "d": dr, "a": a, "src": label}
                    o, u = f(r.get(f"{pre}>2.5")), f(r.get(f"{pre}<2.5"))
                    if o > 1 and u > 1:
                        price.update({"o25": o, "u25": u})
                    break
            if price:
                out[(d, model.team_key(r.get("HomeTeam", "")), model.team_key(r.get("AwayTeam", "")))] = price
    return out


def schedule(fixtures, next_gw, short, teams, upcoming, raw_dir):
    """Next two gameweeks: who's playing, free bookmaker odds when published, injuries. No projections."""
    from datetime import date, timedelta
    odds = load_fixture_odds(raw_dir)
    outs = {fx["id"]: fx["out"] for fx in upcoming}
    rows = []
    if not next_gw:
        return rows
    for fx in sorted(fixtures, key=lambda x: x.get("kickoff_time") or ""):
        if fx.get("finished") or fx.get("event") not in (next_gw, next_gw + 1):
            continue
        hk, ak = model.team_key(teams[fx["team_h"]]["name"]), model.team_key(teams[fx["team_a"]]["name"])
        o = None
        if fx.get("kickoff_time"):
            d = date.fromisoformat(fx["kickoff_time"][:10])
            for dd in (d, d - timedelta(days=1), d + timedelta(days=1)):
                o = odds.get((dd, hk, ak))
                if o:
                    break
        if o:
            inv = [1 / o["h"], 1 / o["d"], 1 / o["a"]]
            o = dict(o, us={k: american(o[k]) for k in ("h", "d", "a", "o25", "u25") if k in o},
                     implied={k: round(x / sum(inv), 3) for k, x in zip("hda", inv)})
        rows.append({"id": fx["id"], "gw": fx["event"], "kickoff": fx.get("kickoff_time"),
                     "home": fx["team_h"], "away": fx["team_a"],
                     "home_short": short.get(fx["team_h"]), "away_short": short.get(fx["team_a"]),
                     "odds": o, "out": outs.get(fx["id"], {"home": [], "away": []})})
    return rows


def last_gameweek(matches, histories, elements, short, pos_names):
    """Latest gameweek with results: score, team xG, how likely that result was from the chances; top performers."""
    done = [m for m in matches if m.get("gw")]
    if not done:
        return {}
    gw = max(m["gw"] for m in done)
    results = []
    for m in (x for x in done if x["gw"] == gw):
        row = {"id": m["id"], "kickoff": m["kickoff"], "home": m["home"], "away": m["away"],
               "home_short": short.get(m["home"]), "away_short": short.get(m["away"]),
               "hg": m["hg"], "ag": m["ag"], "hxg": r(m["hxg"]), "axg": r(m["axg"]), "result_chance": None}
        if m["hxg"] is not None:
            p = model.match_probs(max(m["hxg"], 0.01), max(m["axg"], 0.01), rho=0.0, top=0)
            res = "home" if m["hg"] > m["ag"] else "draw" if m["hg"] == m["ag"] else "away"
            row["result_chance"] = round(p[res], 3)
            row["likeliest"] = round(max(p["home"], p["draw"], p["away"]), 3)
        results.append(row)
    ids = {m["id"] for m in done if m["gw"] == gw}
    perf = []
    for pid, rows in histories.items():
        el = elements.get(int(pid))
        mine = [x for x in rows if x.get("fixture") in ids and x.get("minutes", 0) > 0]
        if not el or not mine:
            continue
        perf.append({"id": el["id"], "name": el["web_name"], "team_short": short.get(el["team"]),
                     "pos": pos_names[el["element_type"]],
                     "pts": sum(x.get("total_points", 0) for x in mine),
                     "g": sum(x.get("goals_scored", 0) for x in mine), "a": sum(x.get("assists", 0) for x in mine),
                     "xg": r(sum(f(x.get("expected_goals")) for x in mine)),
                     "xa": r(sum(f(x.get("expected_assists")) for x in mine)),
                     "min": sum(x.get("minutes", 0) for x in mine)})
    perf.sort(key=lambda x: (-x["pts"], -(x["xg"] + x["xa"])))
    return {"gw": gw, "results": results, "top": perf[:5]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    meta = build(os.path.join(args.out, "raw"), os.path.join(args.out, "build"),
                 log_dir=os.path.join(args.out, "log", "previews"))
    print(f"Built {meta['season']}: {meta['matches']} matches, {meta['players']} players, "
          f"next GW {meta['next_gw']}, {len(meta['warnings'])} warnings")


if __name__ == "__main__":
    sys.exit(main())
