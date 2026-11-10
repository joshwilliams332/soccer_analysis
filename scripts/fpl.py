"""Fetch Premier League data from the free Fantasy Premier League API.

Writes to <out>/raw/:
  bootstrap.json  players (status, injury news, set-piece orders), teams, gameweeks
  fixtures.json   every fixture with scores
  histories.json  {player_id: [one row per match played]} with xG, xA, xG conceded, minutes...
  fetch.json      when it ran, how many players were fetched

Player histories (one request per player) are only re-fetched when a match has finished since the last run,
or a finished match is still inside the 72-hour correction window, so quiet days cost two requests.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://fantasy.premierleague.com/api/"
UA = "Mozilla/5.0 (compatible; MingusSoccer/0.1; +https://github.com/joshwilliams332/soccer_analysis)"
PAUSE = 0.15  # seconds between player requests, to stay gentle
CORRECTION_WINDOW = timedelta(hours=72)

KEEP = [
    "fixture", "opponent_team", "was_home", "kickoff_time", "round", "team_h_score", "team_a_score",
    "minutes", "starts", "goals_scored", "assists", "own_goals", "penalties_missed", "penalties_saved",
    "clean_sheets", "goals_conceded", "yellow_cards", "red_cards", "saves", "bonus", "bps",
    "clearances_blocks_interceptions", "recoveries", "tackles", "defensive_contribution",
    "expected_goals", "expected_assists", "expected_goal_involvements", "expected_goals_conceded",
    "total_points",
]


def get(path, retries=4):
    url = BASE + path
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            if attempt == retries - 1:
                raise RuntimeError(f"FPL request failed: {url}: {err}") from err
            time.sleep(3 * (attempt + 1))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def needs_refresh(fixtures, previous_fetch, now):
    """True if any match finished since the last fetch, or one is still in the correction window."""
    finished = [f for f in fixtures if f.get("finished")]
    ids = sorted(f["id"] for f in finished)
    if ids != previous_fetch.get("finished_ids"):
        return True
    for f in finished:
        k = parse_time(f.get("kickoff_time"))
        if k and now - k < CORRECTION_WINDOW:
            return True
    return False


def trim(row):
    return {k: row[k] for k in KEEP if k in row}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--full", action="store_true", help="re-fetch every player history")
    args = ap.parse_args()
    raw = os.path.join(args.out, "raw")
    now = datetime.now(timezone.utc)

    bootstrap = get("bootstrap-static/")
    fixtures = get("fixtures/")
    previous = load(os.path.join(raw, "fetch.json"), {})
    histories = load(os.path.join(raw, "histories.json"), {})

    refresh = args.full or not histories or needs_refresh(fixtures, previous, now)
    fetched = 0
    if refresh:
        players = [p for p in bootstrap["elements"] if p.get("minutes", 0) > 0]
        fresh = {}
        for p in players:
            summary = get(f"element-summary/{p['id']}/")
            fresh[str(p["id"])] = [trim(r) for r in summary.get("history", [])]
            fetched += 1
            time.sleep(PAUSE)
        histories = fresh

    save(os.path.join(raw, "bootstrap.json"), bootstrap)
    save(os.path.join(raw, "fixtures.json"), fixtures)
    save(os.path.join(raw, "histories.json"), histories)
    fetch = {
        "ran": now.isoformat(timespec="seconds"),
        "refreshed_histories": refresh,
        "players_fetched": fetched,
        "players_with_history": len(histories),
        "finished_ids": sorted(f["id"] for f in fixtures if f.get("finished")),
        "histories_from": now.isoformat(timespec="seconds") if refresh else previous.get("histories_from"),
    }
    save(os.path.join(raw, "fetch.json"), fetch)
    print(f"FPL: {len(bootstrap['elements'])} players, {len(fixtures)} fixtures, "
          f"histories {'refreshed' if refresh else 'kept'} ({fetched} fetched)")


if __name__ == "__main__":
    sys.exit(main())
