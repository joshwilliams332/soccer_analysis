"""Goals model v1 (Nov 10, 2026; backtested 2022-23 to 2026-27, see scripts/backtest.py).

Team strengths come from every finished match, newest weighted most:
  attack  = goals-ish created per game vs the league average for that venue
  defense = goals-ish allowed per game vs the league average for that venue (above 1 = leaky)
"goals-ish" blends xG (85%) with actual goals (15%). Each team is pulled toward its prior (last season's end-of-season
strength, promoted teams 0.75 attack / 1.25 defense) by PRIOR_GAMES matches' worth of evidence.

Projected goals: home = league home GOALS average x home attack x away defense, and the mirror for the away side
(scaled to actual goals, so a season where xG runs above goals doesn't inflate projections).
Scorelines: independent Poisson with the Dixon-Coles fix for 0-0, 1-0, 0-1 and 1-1.

v0 -> v1 (log loss, home / draw / away, lower is better): all seasons 0.998 -> 0.984; 2026-27 held out 1.050 -> 1.024.
Closing bookmaker prices: 0.965. The model is better than a base-rate baseline but not better than the market.
"""
import json
import math
import os

VERSION = "v1"
XG_WEIGHT = 0.85
HALF_LIFE = 15       # matches; a match 15 games ago counts half
PRIOR_GAMES = 6      # pull toward the prior worth this many matches
RHO = -0.06          # Dixon-Coles low-score correction
PROMOTED = (0.75, 1.25)  # prior attack / defense for teams not in last season's Premier League
MAX_GOALS = 10
PRIORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "priors.json")

# Team names differ between FPL and football-data.co.uk; everything is keyed by the football-data name.
ALIAS = {"Man Utd": "Man United", "Spurs": "Tottenham", "Sheffield Utd": "Sheffield United",
         "Coventry City": "Coventry", "Hull City": "Hull", "Ipswich Town": "Ipswich", "Nottingham Forest": "Nott'm Forest",
         "Wolverhampton": "Wolves", "Leicester City": "Leicester", "Leeds United": "Leeds"}


def team_key(name):
    return ALIAS.get(name, name)


def blend(xg, goals, w=XG_WEIGHT):
    if xg is None:
        return float(goals)
    return w * xg + (1 - w) * goals


def poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def tau(x, y, lh, la, rho):
    if x == 0 and y == 0:
        return 1 - lh * la * rho
    if x == 0 and y == 1:
        return 1 + lh * rho
    if x == 1 and y == 0:
        return 1 + la * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def score_grid(lh, la, rho=RHO, max_goals=MAX_GOALS):
    grid = [[poisson(x, lh) * poisson(y, la) * tau(x, y, lh, la, rho) for y in range(max_goals + 1)]
            for x in range(max_goals + 1)]
    total = sum(map(sum, grid))
    return [[p / total for p in row] for row in grid]


def match_probs(lh, la, rho=RHO, top=5):
    g = score_grid(lh, la, rho)
    n = len(g)
    cells = [(x, y, g[x][y]) for x in range(n) for y in range(n)]
    home = sum(p for x, y, p in cells if x > y)
    draw = sum(p for x, y, p in cells if x == y)
    away = sum(p for x, y, p in cells if x < y)
    return {
        "home": home, "draw": draw, "away": away,
        "over_2_5": sum(p for x, y, p in cells if x + y >= 3),
        "btts": sum(p for x, y, p in cells if x > 0 and y > 0),
        "home_clean_sheet": sum(g[x][0] for x in range(n)),
        "away_clean_sheet": sum(g[0][y] for y in range(n)),
        "scores": [{"h": x, "a": y, "p": p} for x, y, p in sorted(cells, key=lambda c: -c[2])[:top]],
    }


def expected_points(xg_for, xg_against):
    """Points a side 'earned' from the chances in one match (rough: Poisson on match xG totals)."""
    m = match_probs(max(xg_for, 0.01), max(xg_against, 0.01), rho=0.0, top=0)
    return 3 * m["home"] + m["draw"]


def league_averages(matches, xg_weight=XG_WEIGHT):
    """matches: finished, each {home, away, hg, ag, hxg, axg}. Returns blended goals per game by venue."""
    if not matches:
        return {"home": 1.5, "away": 1.2}
    h = sum(blend(m["hxg"], m["hg"], xg_weight) for m in matches) / len(matches)
    a = sum(blend(m["axg"], m["ag"], xg_weight) for m in matches) / len(matches)
    return {"home": h, "away": a}


def team_strengths(matches, half_life=HALF_LIFE, prior_games=PRIOR_GAMES, xg_weight=XG_WEIGHT, priors=None):
    """matches sorted oldest first. Returns ({team: {att, def, n}}, league averages).

    priors: optional {team: {"att", "def"}} to pull toward instead of 1.0 (e.g. last season, regressed).
    """
    avg = league_averages(matches, xg_weight)
    games = {}
    for m in matches:
        hf, af = blend(m["hxg"], m["hg"], xg_weight), blend(m["axg"], m["ag"], xg_weight)
        games.setdefault(m["home"], []).append((hf / avg["home"], af / avg["away"]))
        games.setdefault(m["away"], []).append((af / avg["away"], hf / avg["home"]))
    out = {}
    for team in set(games) | set(priors or {}):
        rows = games.get(team, [])
        p = (priors or {}).get(team, {"att": 1.0, "def": 1.0})
        n = len(rows)
        w = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
        sw = sum(w)
        att = (sum(wi * r[0] for wi, r in zip(w, rows)) + prior_games * p["att"]) / (sw + prior_games)
        dfn = (sum(wi * r[1] for wi, r in zip(w, rows)) + prior_games * p["def"]) / (sw + prior_games)
        out[team] = {"att": att, "def": dfn, "n": n}
    return out, avg


def goal_averages(matches):
    """Actual goals per game by venue (the scale projections should land on)."""
    if not matches:
        return {"home": 1.5, "away": 1.2}
    return {"home": sum(m["hg"] for m in matches) / len(matches),
            "away": sum(m["ag"] for m in matches) / len(matches)}


def load_priors(names, path=PRIORS_FILE):
    """{team_id: {"att", "def"}} from last season's end strengths; teams not found count as promoted."""
    try:
        with open(path, encoding="utf-8") as fh:
            teams = json.load(fh)["teams"]
    except FileNotFoundError:
        return None
    out = {}
    for tid, name in names.items():
        v = teams.get(team_key(name))
        out[tid] = dict(v) if v else {"att": PROMOTED[0], "def": PROMOTED[1]}
    return out


def fit(matches, priors=None):
    """v1: strengths from blended xG with priors, projections scaled to actual goals per game."""
    strengths, _ = team_strengths(matches, priors=priors)
    return strengths, goal_averages(matches)


def project(home, away, strengths, avg):
    sh = strengths.get(home, {"att": 1.0, "def": 1.0})
    sa = strengths.get(away, {"att": 1.0, "def": 1.0})
    return avg["home"] * sh["att"] * sa["def"], avg["away"] * sa["att"] * sh["def"]


def chance_at_least_one(expected):
    return 1 - math.exp(-max(expected, 0.0))
