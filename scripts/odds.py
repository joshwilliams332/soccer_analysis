"""Free pre-match odds for upcoming Premier League games (football-data.co.uk fixtures.csv).

football-data.co.uk publishes the coming round's fixtures with bookmaker odds, updated a couple of times a week.
Writes <out>/raw/odds_fixtures.csv (Premier League rows only). Never fails the build: no file = no odds shown.
"""
import argparse
import csv
import io
import os
import sys
import urllib.request

URL = "https://www.football-data.co.uk/fixtures.csv"
UA = "Mozilla/5.0 (compatible; MingusFC/0.1; +https://github.com/joshwilliams332/soccer_analysis)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    path = os.path.join(args.out, "raw", "odds_fixtures.csv")
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8-sig", errors="replace")
    except Exception as err:  # noqa: BLE001 - odds are optional
        print(f"odds: skipped ({err})")
        return 0
    reader = csv.DictReader(io.StringIO(text))
    rows = [r for r in reader if r.get("Div") == "E0"]
    if not rows:
        print("odds: no Premier League rows this week (kept the previous file)")
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=reader.fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"odds: {len(rows)} Premier League fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
