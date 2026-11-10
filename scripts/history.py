"""Download past Premier League seasons for backtesting (runs in GitHub Actions).

For each season writes <out>/hist/<season>/:
  matches.json  one row per finished match: id, gw, kickoff, home / away (names), goals, team xG (sum of players' FPL xG)
  odds.csv      football-data.co.uk results + bookmaker odds (incl. closing prices), unchanged

Sources (free, public):
  FPL history:  github.com/vaastav/Fantasy-Premier-League (player xG per match since 2022-23)
  Odds:         football-data.co.uk/mmz4281/<yyyy>/E0.csv
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

FPL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/{path}"
ODDS = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"
SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]
UA = "Mozilla/5.0 (compatible; MingusFC/0.1; +https://github.com/joshwilliams332/soccer_analysis)"


def get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(3 * (attempt + 1))


def rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))))


def fpl_season(season):
    fx_raw = get(FPL.format(season=season, path="fixtures.csv"))
    teams_raw = get(FPL.format(season=season, path="teams.csv"))
    gw_raw = get(FPL.format(season=season, path="gws/merged_gw.csv"))
    if not (fx_raw and teams_raw and gw_raw):
        return None
    names = {int(t["id"]): t["name"] for t in rows(teams_raw)}
    xg = {}
    has_xg = False
    for r in rows(gw_raw):
        if "expected_goals" not in r or r.get("fixture") in (None, ""):
            continue
        has_xg = True
        side = "h" if str(r.get("was_home")).strip().lower() == "true" else "a"
        key = (int(r["fixture"]), side)
        try:
            xg[key] = xg.get(key, 0.0) + float(r["expected_goals"] or 0)
        except ValueError:
            pass
    if not has_xg:
        return None
    out = []
    for f in rows(fx_raw):
        if str(f.get("finished")).lower() != "true" or f.get("team_h_score") in ("", None):
            continue
        fid = int(f["id"])
        if (fid, "h") not in xg and (fid, "a") not in xg:
            continue
        out.append({
            "id": fid, "gw": int(float(f["event"])) if f.get("event") else None, "kickoff": f["kickoff_time"],
            "home": int(f["team_h"]), "away": int(f["team_a"]),
            "home_name": names[int(f["team_h"])], "away_name": names[int(f["team_a"])],
            "hg": int(float(f["team_h_score"])), "ag": int(float(f["team_a_score"])),
            "hxg": round(xg.get((fid, "h"), 0.0), 3), "axg": round(xg.get((fid, "a"), 0.0), 3),
        })
    out.sort(key=lambda m: m["kickoff"])
    return out


def odds_code(season):
    a, b = season.split("-")
    return a[2:] + b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--current", default="2026-27", help="also fetch this season's odds file")
    args = ap.parse_args()
    summary = {}
    for season in SEASONS + [args.current]:
        d = os.path.join(args.out, "hist", season)
        os.makedirs(d, exist_ok=True)
        info = {}
        if season != args.current:
            matches = fpl_season(season)
            if matches:
                with open(os.path.join(d, "matches.json"), "w", encoding="utf-8") as fh:
                    json.dump(matches, fh, separators=(",", ":"))
            info["fpl_matches"] = len(matches) if matches else 0
        raw = get(ODDS.format(code=odds_code(season)))
        if raw:
            with open(os.path.join(d, "odds.csv"), "wb") as fh:
                fh.write(raw)
        info["odds_rows"] = len(rows(raw)) if raw else 0
        summary[season] = info
        print(season, info)
    with open(os.path.join(args.out, "hist", "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    if not any(v.get("fpl_matches") for v in summary.values()):
        sys.exit("no FPL history downloaded")


if __name__ == "__main__":
    main()
