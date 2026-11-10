# Mingus Soccer (working name): notes for Claude

Premier League research for Mingus Sports, owned by the soccer lead chat. Josh (joshwilliams332) merges PRs.
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

## Data
- **FPL public API** (no key): player per-match minutes, goals, assists, xG, xA, xG conceded, defensive
  contributions, saves, cards; injury status, chance of playing, penalty / set-piece order; fixtures and scores.
  Team xG for a match = sum of its players' xG (includes penalties; there's no non-penalty xG in FPL).
  Player histories are re-fetched only when a match has finished since the last run or one is inside the 72-hour
  correction window (one request per player who has played, 0.15 s apart).
- **Understat** (shots, PPDA, shot maps) is planned but was on a maintenance page Nov 10, 2026.
- **FBref** has had no advanced stats since Jan 20, 2026. Don't use it for xG.
- Show our own derived numbers; credit sources; never copy another site's tables, names or design.

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
