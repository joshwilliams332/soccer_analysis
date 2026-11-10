"""How good are the projections? Two honest checks, rebuilt every run.

replay: every match from gameweek REPLAY_FROM on, predicted only from earlier gameweeks with today's model settings.
live:   previews frozen before kickoff (log/previews/<id>.json, never edited after kickoff) graded once played.

Scores (lower is better): Brier and log loss for win / draw / loss, Brier for over 2.5. Each is compared with a
baseline that knows only how often home wins / draws / away wins and overs have happened in earlier matches.
"""
import json
import math
import os

import model

REPLAY_FROM = 4


def result(hg, ag):
    return 0 if hg > ag else 1 if hg == ag else 2


def brier(p, r):
    return sum((pi - (1 if i == r else 0)) ** 2 for i, pi in enumerate(p))


def logloss(p, r):
    return -math.log(max(p[r], 1e-9))


def base_rates(prior):
    n = len(prior)
    if not n:
        return (0.45, 0.25, 0.30), 0.5
    h = sum(m["hg"] > m["ag"] for m in prior) / n
    d = sum(m["hg"] == m["ag"] for m in prior) / n
    over = sum(m["hg"] + m["ag"] >= 3 for m in prior) / n
    return (h, d, 1 - h - d), over


def summarize(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    avg = lambda f: sum(f(x) for x in rows) / n  # noqa: E731
    fav = [x for x in rows if max(x["p"][0], x["p"][2]) > 0.5]
    return {
        "n": n,
        "brier": round(avg(lambda x: brier(x["p"], x["r"])), 3),
        "brier_base": round(avg(lambda x: brier(x["b"], x["r"])), 3),
        "logloss": round(avg(lambda x: logloss(x["p"], x["r"])), 3),
        "logloss_base": round(avg(lambda x: logloss(x["b"], x["r"])), 3),
        "over_brier": round(avg(lambda x: (x["o"] - x["over"]) ** 2), 3),
        "over_brier_base": round(avg(lambda x: (x["ob"] - x["over"]) ** 2), 3),
        "over_rate": round(avg(lambda x: x["over"]), 3),
        "over_pred": round(avg(lambda x: x["o"]), 3),
        "goals_pred": round(avg(lambda x: x["g_pred"]), 2),
        "goals_actual": round(avg(lambda x: x["g"]), 2),
        "fav_n": len(fav),
        "fav_won": sum((x["p"][0] > 0.5 and x["r"] == 0) or (x["p"][2] > 0.5 and x["r"] == 2) for x in fav),
        "fav_pred": round(sum(max(x["p"][0], x["p"][2]) for x in fav) / len(fav), 3) if fav else None,
    }


def replay(matches):
    """matches: finished, sorted by kickoff, each {gw, home, away, hg, ag, hxg, axg}."""
    rows = []
    for m in matches:
        if (m.get("gw") or 0) < REPLAY_FROM:
            continue
        prior = [x for x in matches if (x.get("gw") or 0) < m["gw"]]
        s, avg = model.team_strengths(prior)
        lh, la = model.project(m["home"], m["away"], s, avg)
        p = model.match_probs(lh, la, top=0)
        b, ob = base_rates(prior)
        rows.append({"p": (p["home"], p["draw"], p["away"]), "b": b, "o": p["over_2_5"], "ob": ob,
                     "r": result(m["hg"], m["ag"]), "over": m["hg"] + m["ag"] >= 3,
                     "g_pred": lh + la, "g": m["hg"] + m["ag"]})
    return summarize(rows)


def snapshot(log_dir, upcoming, now_iso, version):
    """Save each upcoming preview; files are only rewritten before kickoff, so the last pre-kickoff one stays."""
    os.makedirs(log_dir, exist_ok=True)
    for fx in upcoming:
        if not fx.get("kickoff") or fx["kickoff"] <= now_iso:
            continue
        keep = {k: fx[k] for k in ("id", "gw", "kickoff", "home", "away", "home_short", "away_short", "proj", "probs")}
        keep.update({"saved": now_iso, "model": version})
        with open(os.path.join(log_dir, f"{fx['id']}.json"), "w", encoding="utf-8") as fh:
            json.dump(keep, fh, separators=(",", ":"))


def grade_live(log_dir, matches):
    by_id = {m["id"]: m for m in matches}
    rows, graded = [], []
    if not os.path.isdir(log_dir):
        return summarize(rows), graded
    for name in sorted(os.listdir(log_dir)):
        with open(os.path.join(log_dir, name), encoding="utf-8") as fh:
            snap = json.load(fh)
        m = by_id.get(snap["id"])
        if not m:
            continue
        prior = [x for x in matches if x["kickoff"] < snap["kickoff"]]
        b, ob = base_rates(prior)
        pr = snap["probs"]
        rows.append({"p": (pr["home"], pr["draw"], pr["away"]), "b": b, "o": pr["over_2_5"], "ob": ob,
                     "r": result(m["hg"], m["ag"]), "over": m["hg"] + m["ag"] >= 3,
                     "g_pred": snap["proj"]["home"] + snap["proj"]["away"], "g": m["hg"] + m["ag"]})
        graded.append({"id": m["id"], "gw": m["gw"], "home_short": snap["home_short"], "away_short": snap["away_short"],
                       "proj": snap["proj"], "probs": pr, "hg": m["hg"], "ag": m["ag"]})
    return summarize(rows), graded
