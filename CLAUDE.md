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
- **No model on the site (Josh, Nov 10).** The goals model runs in the background (build, frozen previews, accuracy,
  backtest) but the public site shows facts: who's playing, free odds, records, league position, xG comparisons.
  The deploy job publishes only `teams, players, matches, schedule, gameweek, meta` (not `fixtures.json` /
  `accuracy.json`, which hold model output). Don't add projections back without asking.
- Pages in `site/`, no build step:
  - `index.html` Matches: next two gameweeks (time, position, points, form, odds when published), last gameweek's
    results (goals and xG side by side, green = higher, red = lower, plus "xG says": how likely that result was from
    the chances, colored against the likeliest result so draws aren't always red), player of the week (FPL points).
  - `match.html?id=` head-to-head table (green = better of the two, red = worse), odds, key players, injuries, last 5.
  - `table.html` league table (Pos, Pts, GD first for phones) + xG / last 6 / home / away views, tap to sort.
  - `players.html` dense sortable table (FPL price, ownership, points, starts, G, A, xG, xA, min per xGI, DC, CS, xGC);
    the sorted column moves next to the name; green / red = top / bottom quarter of the list.
  - `compare.html?mode=teams|players&a=&b=` any two teams or players side by side.
- Shared helpers in `site/assets/common.js` (`MFC`: load, format, `tone`, `dot` club color dots, `team`, `us` odds,
  header, footer); styles in `style.css`.
- Odds: `scripts/odds.py` pulls football-data.co.uk `fixtures.csv` (free; upcoming round, updated a couple of times a
  week) → `raw/odds_fixtures.csv`; `build_data.schedule()` matches it to fixtures (date ±1 day, `model.team_key`),
  shows the bookmaker average as US odds plus the implied chance. No odds file = "Odds not out yet". No Odds API credits.
- Look (Josh, Nov 10): simple and easy to compare, inspired by stats tables he likes: dark header with a green rule,
  white tables on light grey, Archivo with tabular numbers. Mingus mark + "FC" tag. No Premier League logo / purple /
  fonts, no crests, kits or player photos (our own two-color club dots only).
- **Colors mean good / bad: green = better, white = okay, red = worse.** Form chips W green / D grey / L red, last 5.
- Every page carries the sources line and "For entertainment · 21+ · Gamble responsibly · 1-800-GAMBLER".
- Check every change at 390px and desktop: copy `site/` and the data branch's public `build/*.json` (as `data/`) into a
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

## Goals model v1 (`scripts/model.py`; Nov 10, 2026)
- Per match: blended goals = 85% xG + 15% goals. Team attack / defense = recency-weighted (15-match half-life) ratio to
  the league average for that venue, pulled toward a **prior** by 6 matches' worth of evidence. Prior = last season's
  end-of-season strength (`scripts/priors.json`, keyed by football-data team name via `model.team_key`); teams not in
  it (promoted) start at 0.75 attack / 1.25 defense.
- Projected goals: league home **goals** average x home attack x away defense (and the mirror). Scaling to actual goals
  stops a season where FPL xG runs above goals (2026-27) from inflating projections. Poisson + Dixon-Coles (rho -0.06).
- `model.fit(matches, priors)` is the one entry point (build and replay both use it).
- Players to watch: per-90 xG / xA steadied toward the position average (450 minutes' worth) x expected minutes
  (average of the team's last 4 matches x chance of playing) x the matchup (projected goals vs the team's
  average-opponent baseline, 0.5-2.0). Chance of at least one = 1 - e^(-expected).
- Expected points (luck table): Poisson on each match's xG totals. Rough; not shot-by-shot.
- **New season:** re-run the backtest with `--priors scripts/priors.json` after adding the finished season to
  `history.py`'s SEASONS, or every team starts as promoted.

## Backtest (`scripts/backtest.py`, `.github/workflows/history.yml`)
- `history.yml` (manual, or when `history.py` changes) downloads FPL seasons 2022-23 on (vaastav/Fantasy-Premier-League,
  team xG = sum of players') and football-data.co.uk `E0.csv` (closing odds) to the **`history`** branch. FPL xG starts
  at 2022-23 GW16; earlier matches are goals-only.
- Run: fetch the `history` branch (`hist/`) and the `data` branch (`build/`), then
  `python3 scripts/backtest.py --hist <hist> --current <data dir> --json reports/backtest.json --priors scripts/priors.json`.
  `reports/backtest.json` is committed (internal; not on the site).
- Market = closing prices, margin removed: Pinnacle, else Betfair Exchange (Pinnacle columns stop mid 2025-26), else
  average. Scored from GW4. v1 tuned on 2022-23 to 2025-26, 2026-27 held out.
- Nov 10 results (log loss, home / draw / away): v0 0.998, **v1 0.984**, closing odds **0.965**, base rate 1.075.
  v1 beat v0 every season; behind the odds in 4 of 5 (ahead in 2024-25). Mixing the model into the odds only helped in
  2024-25; a flat-stakes test swung +61 to -28 units by season. **No proven edge over bookmakers.** Over 2.5: about
  the baseline; the odds are better. Don't claim an edge publicly.

## Accuracy (`scripts/accuracy.py`, rebuilt every run into `build/accuracy.json`; internal, not deployed)
- **Replay:** every match from GW4 on, predicted only from earlier gameweeks with today's settings, vs a baseline
  that knows only earlier home / draw / away and over 2.5 rates. Nov 10 with v1 (70 matches): log loss 1.024 vs 1.095;
  over 2.5 about the baseline; goals 2.85 projected vs 2.69 actual (v0 was 2.94).
- **Live record:** each upcoming preview is written to `log/previews/<fixture>.json` on the data branch every run until
  kickoff, then never touched; graded once the result is in. This is the real record; the replay flatters the model.
- Live grading vs closing odds: later (the current season's odds file is on the `history` branch; refresh it by re-running
  `history.yml`).
