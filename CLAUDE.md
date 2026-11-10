# Mingus FC: notes for Claude

Mingus FC: Premier League research for Mingus Sports (name: Josh, Nov 10, 2026), owned by the soccer lead chat. Josh (joshwilliams332) merges PRs.
Team rules (honest records, responsible-gambling lines, our own brand, phone first, keep it cheap) are in the Mingus
Sports project: `claude/mingus-team-charter.md`. The plan is `claude/plans/premier-league.md`.

## How it runs
- Python 3.12, standard library only (no pip installs needed).
- `.github/workflows/build-data.yml`: tests, then `scripts/fpl.py` (fetch) and `scripts/build_data.py` (build),
  then commits `out/` to the **`data` branch** (main pushes, schedule, Run workflow) or **`data-preview`**
  (pull requests, so a PR can be checked before merging). Schedule: 11:17 and 23:41 UTC daily, 17:47 UTC Sat/Sun.
- Data branch layout: `raw/` (FPL bootstrap, fixtures, player histories, fetch.json) and `build/` (teams, players,
  matches, fixtures, meta). Generated: never hand-edit.
- The cloud sandbox can't reach FPL / Understat; check results by fetching the data branch.
- Work ships as branch, then PR, then Josh merges. Run `python3 -m unittest discover -s tests` before pushing.

## Site (GitHub Pages: https://joshwilliams332.github.io/soccer_analysis/)
- Static pages in `site/`, no build step: `index.html` (matches by gameweek), `match.html?id=` (preview),
  `table.html` (xG table: season / last 6 / home / away, tap to sort), `players.html` (per-90 xG / xA lists).
  Shared helpers (`MFC`: load, format, rank chips, header, footer) in `site/assets/common.js`; styles in `style.css`.
- The workflow's `deploy` job (not on PRs) copies the `data` branch `build/*.json` into `site/data/`, adds a
  commit-hash `?v=` to the shared files and deploys. Pages source must be "GitHub Actions". Never commit `site/data/`.
- Brand kit look: paper grid, ink, Lab Blue links, Pitch green only for the FC tag. Teams as names or abbreviations,
  no logos. Rank chips: top 5 blue, bottom 5 grey (sport colors never mean good / bad).
- Every page carries the sources line and "For entertainment · 21+ · Gamble responsibly · 1-800-GAMBLER";
  projections carry the dashed MINGUS ESTIMATE tag.
- Check every change at 390px and desktop: copy `site/` and the data branch's `build/*.json` (as `data/`) into a
  folder, `python3 -m http.server`, screenshot with Playwright (`/usr/bin/google-chrome`). Long team names get a
  smaller `long` class on phones.

## Data
- **FPL public API** (no key): player per-match minutes, goals, assists, xG, xA, xG conceded, defensive
  contributions, saves, cards; injury status, chance of playing, penalty / set-piece order; fixtures and scores.
  Team xG for a match = sum of its players' xG (includes penalties; there's no non-penalty xG in FPL).
  Player histories are re-fetched only when a match has finished since the last run or one is inside the 72-hour
  correction window (one request per player who has played, 0.15 s apart).
- **Understat** (shots, PPDA, shot maps) is planned but was on a maintenance page Nov 10, 2026.
- **FBref** has had no advanced stats since Jan 20, 2026. Don't use it for xG.
- Public numbers OK with sources credited (Josh, Nov 10): show our own derived numbers, credit FPL / Understat,
  never copy another site's tables, names or design.
- Brand: Mingus Sports kit (project `claude/brand-kit.md`). Soccer color Pitch #4C9A1E (small text #3B7A14).

## Goals model v0 (`scripts/model.py`, untested against odds)
- Per match: blended goals = 70% xG + 30% goals. Team attack / defense = recency-weighted (8-match half-life)
  ratio to the league average for that venue, pulled toward 1.0 by 6 matches' worth of evidence.
- Projected goals: league home average x home attack x away defense (and the mirror). Poisson scorelines with the
  Dixon-Coles low-score fix (rho -0.06): win / draw / loss, over 2.5, BTTS, clean sheets, top 5 scores.
- Players to watch: per-90 xG / xA steadied toward the position average (450 minutes' worth) x expected minutes
  (average of the team's last 4 matches x chance of playing) x the matchup (projected goals vs the team's
  average-opponent baseline, 0.5-2.0). Chance of at least one = 1 - e^(-expected).
- Expected points (luck table): Poisson on each match's xG totals. Rough; not shot-by-shot.
- Not proven: backtest against football-data.co.uk closing odds before any public claims. Label outputs as estimates.
