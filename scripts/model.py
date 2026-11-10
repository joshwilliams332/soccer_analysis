"""Goals model v0 (untested against odds; not for public claims yet).

Team strengths come from every finished match, newest weighted most:
  attack  = goals-ish created per game vs the league average for that venue
  defense = goals-ish allowed per game vs the league average for that venue (above 1 = leaky)
"goals-ish" blends xG (70%) with actual goals (30%), and each team is pulled toward average (1.0) by
PRIOR_GAMES matches' worth of evidence so early-season numbers stay sane.

Projected goals: home = league home average x home attack x away defense, and the mirror for the away side.
Scorelines: independent Poisson with the Dixon-Coles fix for 0-0, 1-0, 0-1 and 1-1.
"""
import math

XG_WEIGHT = 0.7
HALF_LIFE = 8        # matches; a match 8 games ago counts half
PRIOR_GAMES = 6      # pull toward league average worth this many matches
RHO = -0.06          # Dixon-Coles low-score correction (typical Premier League value)
MAX_GOALS = 10


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


def league_averages(matches):
    """matches: finished, each {home, away, hg, ag, hxg, axg}. Returns blended goals per game by venue."""
    if not matches:
        return {"home": 1.5, "away": 1.2}
    h = sum(blend(m["hxg"], m["hg"]) for m in matches) / len(matches)
    a = sum(blend(m["axg"], m["ag"]) for m in matches) / len(matches)
    return {"home": h, "away": a}


def team_strengths(matches, half_life=HALF_LIFE, prior_games=PRIOR_GAMES):
    """matches sorted oldest first. Returns ({team: {att, def, n}}, league averages)."""
    avg = league_averages(matches)
    games = {}
    for m in matches:
        hf, af = blend(m["hxg"], m["hg"]), blend(m["axg"], m["ag"])
        games.setdefault(m["home"], []).append((hf / avg["home"], af / avg["away"]))
        games.setdefault(m["away"], []).append((af / avg["away"], hf / avg["home"]))
    out = {}
    for team, rows in games.items():
        n = len(rows)
        w = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
        sw = sum(w)
        att = (sum(wi * r[0] for wi, r in zip(w, rows)) + prior_games) / (sw + prior_games)
        dfn = (sum(wi * r[1] for wi, r in zip(w, rows)) + prior_games) / (sw + prior_games)
        out[team] = {"att": att, "def": dfn, "n": n}
    return out, avg


def project(home, away, strengths, avg):
    sh = strengths.get(home, {"att": 1.0, "def": 1.0})
    sa = strengths.get(away, {"att": 1.0, "def": 1.0})
    return avg["home"] * sh["att"] * sa["def"], avg["away"] * sa["att"] * sh["def"]


def chance_at_least_one(expected):
    return 1 - math.exp(-max(expected, 0.0))
