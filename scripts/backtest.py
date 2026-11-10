"""Backtest the goals model on past seasons and against closing bookmaker odds.

Each match is predicted only from matches that kicked off earlier (same season), optionally starting from last
season's team strengths pulled toward average. Scores, lower is better:
  Brier / log loss for home / draw / away, Brier / log loss for over 2.5, mean projected vs actual goals.
Compared with:
  base    how often home / draw / away and overs happened earlier that season (the minimum bar)
  market  closing bookmaker prices with the margin removed: Pinnacle close, else Betfair Exchange close, else the
          market average close (football-data.co.uk)

Usage: python scripts/backtest.py --hist <dir with hist/> [--current <data dir with build/>] [--grid]
"""
import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model  # noqa: E402

SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]
SCORE_FROM_GW = 4

V0 = {"xg_weight": 0.7, "half_life": 8, "prior_games": 6, "rho": -0.06, "scale": "blend", "carry": 0.0,
      "promoted": (1.0, 1.0)}
# v1 (Nov 10, 2026): tuned on 2022-23 to 2025-26, checked on 2026-27 (held out).
V1 = {"xg_weight": model.XG_WEIGHT, "half_life": model.HALF_LIFE, "prior_games": model.PRIOR_GAMES,
      "rho": model.RHO, "scale": "goals", "carry": 1.0, "promoted": model.PROMOTED}

norm = model.team_key


def num(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def devig(prices):
    if any(p is None for p in prices):
        return None
    inv = [1 / p for p in prices]
    s = sum(inv)
    return [x / s for x in inv]


def load_odds(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if not r.get("HomeTeam"):
                continue
            d = datetime.strptime(r["Date"], "%d/%m/%Y" if len(r["Date"]) == 10 else "%d/%m/%y").date()
            x12 = None
            for pre in ("PSC", "BFEC", "AvgC"):
                x12 = devig([num(r.get(pre + k)) for k in "HDA"])
                if x12:
                    src = pre
                    break
            ou = None
            for pre in ("PC", "BFEC", "AvgC"):
                ou = devig([num(r.get(f"{pre}>2.5")), num(r.get(f"{pre}<2.5"))])
                if ou:
                    break
            out[(d.isoformat(), norm(r["HomeTeam"]), norm(r["AwayTeam"]))] = {
                "x12": x12, "x12_src": src if x12 else None, "over": ou[0] if ou else None}
    return out


def attach_odds(matches, odds):
    hit = 0
    for m in matches:
        day = m["kickoff"][:10]
        key = (day, norm(m["home_name"]), norm(m["away_name"]))
        o = odds.get(key)
        if not o:  # late UK kickoffs can fall on the next UTC day, or vice versa
            for k, v in odds.items():
                if k[1:] == key[1:] and abs((datetime.fromisoformat(k[0]) - datetime.fromisoformat(day)).days) <= 1:
                    o = v
                    break
        m["mkt"] = o
        hit += bool(o)
    return hit


def season_end_strengths(matches, params):
    s, _ = model.team_strengths(matches, params["half_life"], 0.0001, params["xg_weight"])
    return {t: {"att": v["att"], "def": v["def"]} for t, v in s.items()}


def run_season(matches, params, prev_end=None, prev_names=None):
    """Yield one scored row per match (from SCORE_FROM_GW) with model, base and market probabilities."""
    priors = None
    if prev_end and params["carry"] > 0:
        c = params["carry"]
        priors = {}
        name_of = {}
        for m in matches:
            name_of[m["home"]] = norm(m["home_name"])
            name_of[m["away"]] = norm(m["away_name"])
        by_name = {prev_names[t]: v for t, v in prev_end.items()}
        pa, pd = params["promoted"]
        for tid, nm in name_of.items():
            v = by_name.get(nm, {"att": pa, "def": pd})
            priors[tid] = {"att": 1 + c * (v["att"] - 1), "def": 1 + c * (v["def"] - 1)}
    rows = []
    cache = {}
    for i, m in enumerate(matches):
        if (m.get("gw") or 0) < SCORE_FROM_GW:
            continue
        prior = [x for x in matches[:i] if x["kickoff"] < m["kickoff"]]
        key = len(prior)
        if key not in cache:
            s, avg = model.team_strengths(prior, params["half_life"], params["prior_games"], params["xg_weight"], priors)
            if params["scale"] == "goals":
                avg = model.goal_averages(prior)
            cache[key] = (s, avg)
        s, avg = cache[key]
        lh, la = model.project(m["home"], m["away"], s, avg)
        p = model.match_probs(lh, la, rho=params["rho"], top=0)
        n = len(prior)
        bh = sum(x["hg"] > x["ag"] for x in prior) / n
        bd = sum(x["hg"] == x["ag"] for x in prior) / n
        bo = sum(x["hg"] + x["ag"] >= 3 for x in prior) / n
        r = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
        rows.append({"p": [p["home"], p["draw"], p["away"]], "b": [bh, bd, 1 - bh - bd], "o": p["over_2_5"], "bo": bo,
                     "mk": m["mkt"]["x12"] if m.get("mkt") else None,
                     "mo": m["mkt"]["over"] if m.get("mkt") else None,
                     "r": r, "over": int(m["hg"] + m["ag"] >= 3), "gp": lh + la, "g": m["hg"] + m["ag"]})
    return rows


def brier(p, r):
    return sum((pi - (i == r)) ** 2 for i, pi in enumerate(p))


def ll(p, r):
    return -math.log(max(p[r], 1e-9))


def score(rows, with_market=True):
    n = len(rows)
    if not n:
        return {}
    out = {
        "n": n,
        "brier": sum(brier(x["p"], x["r"]) for x in rows) / n,
        "ll": sum(ll(x["p"], x["r"]) for x in rows) / n,
        "base_brier": sum(brier(x["b"], x["r"]) for x in rows) / n,
        "base_ll": sum(ll(x["b"], x["r"]) for x in rows) / n,
        "o_brier": sum((x["o"] - x["over"]) ** 2 for x in rows) / n,
        "o_ll": sum(-math.log(max(x["o"] if x["over"] else 1 - x["o"], 1e-9)) for x in rows) / n,
        "base_o_brier": sum((x["bo"] - x["over"]) ** 2 for x in rows) / n,
        "goals_pred": sum(x["gp"] for x in rows) / n,
        "goals": sum(x["g"] for x in rows) / n,
    }
    if with_market:
        mk = [x for x in rows if x["mk"]]
        if mk:
            k = len(mk)
            out.update({
                "mk_n": k,
                "mk_brier": sum(brier(x["mk"], x["r"]) for x in mk) / k,
                "mk_ll": sum(ll(x["mk"], x["r"]) for x in mk) / k,
                "model_brier_on_mk": sum(brier(x["p"], x["r"]) for x in mk) / k,
                "model_ll_on_mk": sum(ll(x["p"], x["r"]) for x in mk) / k,
            })
        mo = [x for x in rows if x["mo"]]
        if mo:
            k = len(mo)
            out.update({
                "mo_n": k,
                "mo_brier": sum((x["mo"] - x["over"]) ** 2 for x in mo) / k,
                "model_o_brier_on_mo": sum((x["o"] - x["over"]) ** 2 for x in mo) / k,
            })
    return out


def load_seasons(hist_dir, current_dir=None):
    seasons = []
    for s in SEASONS:
        p = os.path.join(hist_dir, s, "matches.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                ms = json.load(fh)
            for m in ms:  # FPL only started publishing xG at 2022-23 gameweek 16: treat 0-0 xG as missing
                if not m["hxg"] and not m["axg"]:
                    m["hxg"] = m["axg"] = None
            attach_odds(ms, load_odds(os.path.join(hist_dir, s, "odds.csv")))
            seasons.append((s, ms))
    if current_dir:
        with open(os.path.join(current_dir, "build", "matches.json"), encoding="utf-8") as fh:
            ms = json.load(fh)
        with open(os.path.join(current_dir, "build", "teams.json"), encoding="utf-8") as fh:
            names = {t["id"]: t["name"] for t in json.load(fh)}
        for m in ms:
            m["home_name"], m["away_name"] = names[m["home"]], names[m["away"]]
        attach_odds(ms, load_odds(os.path.join(hist_dir, "2026-27", "odds.csv")))
        seasons.append(("2026-27", ms))
    return seasons


def evaluate(seasons, params):
    per, all_rows = {}, []
    prev_end = prev_names = None
    for name, ms in seasons:
        rows = run_season(ms, params, prev_end, prev_names)
        per[name] = score(rows)
        all_rows += rows
        prev_end = season_end_strengths(ms, params)
        prev_names = {}
        for m in ms:
            prev_names[m["home"]] = norm(m["home_name"])
            prev_names[m["away"]] = norm(m["away_name"])
    return per, score(all_rows)


def fmt(sc):
    s = (f"n={sc['n']:4d}  1X2 Brier {sc['brier']:.4f} (base {sc['base_brier']:.4f}"
         + (f", market {sc['mk_brier']:.4f} on {sc['mk_n']}" if "mk_brier" in sc else "") + ")"
         + f"  LL {sc['ll']:.4f}" + (f" (mkt {sc['mk_ll']:.4f})" if "mk_ll" in sc else "")
         + f"  O2.5 Brier {sc['o_brier']:.4f} (base {sc['base_o_brier']:.4f}"
         + (f", mkt {sc['mo_brier']:.4f}" if "mo_brier" in sc else "") + ")"
         + f"  goals {sc['goals_pred']:.2f} vs {sc['goals']:.2f}")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", required=True, help="folder containing <season>/matches.json and odds.csv")
    ap.add_argument("--current", help="data folder with build/matches.json and build/teams.json (this season)")
    ap.add_argument("--json", help="write the summary the Model page shows here")
    ap.add_argument("--priors", help="write last season's end strengths (v1 priors for the current season) here")
    args = ap.parse_args()
    seasons = load_seasons(args.hist, args.current)
    summary = {}
    for label, params in (("v0", V0), ("v1", V1)):
        per, tot = evaluate(seasons, params)
        print(label)
        for k, v in per.items():
            print(" ", k, fmt(v))
        print("  ALL    ", fmt(tot))
        summary[label] = {"per_season": {k: rounded(v) for k, v in per.items()}, "all": rounded(tot)}
    if args.json:
        summary["note"] = ("Each match predicted only from earlier matches. Market = closing prices with the margin "
                           "removed (Pinnacle, else Betfair Exchange, else market average; football-data.co.uk). "
                           "v1 settings were tuned on 2022-23 to 2025-26; 2026-27 was held out.")
        summary["held_out"] = "2026-27"
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=1)
    if args.priors:
        last_name, last = [s for s in seasons if s[0] in SEASONS][-1]
        end = season_end_strengths(last, V1)
        names = {}
        for m in last:
            names[m["home"]] = norm(m["home_name"])
            names[m["away"]] = norm(m["away_name"])
        with open(args.priors, "w", encoding="utf-8") as fh:
            json.dump({"from_season": last_name, "teams": {names[t]: {"att": round(v["att"], 4), "def": round(v["def"], 4)}
                                                           for t, v in sorted(end.items(), key=lambda kv: names[kv[0]])}},
                      fh, indent=1)


def rounded(d):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


if __name__ == "__main__":
    main()
