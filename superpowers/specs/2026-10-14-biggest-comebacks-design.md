# Biggest Comebacks — Design

**Date:** 2026-10-14
**Status:** Approved in chat, pending spec review

## Goal

Add an all-time "Biggest Comebacks" record table to the site: the largest deficits overcome by the eventual winner, across every season with play-by-play (2007-08 onward). Prompted by Olympiacos winning at Valencia from 28 down (34-62, Q3 8:30) on 2026-10-13, which ties the largest comeback in the data.

**Success criteria**
- OLY @ PAM (2026-27 RS R5, game 45) shows as T-1 with 28, alongside Asseco Prokom Gdynia @ Siena (2012-13 RS R10, 28).
- The 2012 Final (OLY 62-61 CSK, down 19) and 2013 Final (OLY 100-88 MAD, down 17) appear in the postseason card. These cross-check the method against real history.
- New comebacks appear automatically on each pipeline run, with no manual steps.

## Placement

A new **Comebacks** tab on the existing All-Time Records page (`docs/records.html`), after Efficiency. There is no new page or nav link.

## Data: `calculate_comebacks.py`

**Input:** `data_cache/pbp_{s}.csv` for each `s` in `season_config.ALL_SEASONS`; a missing file is skipped with a warning.

**Per game** (grouped by `Season`, `Gamecode`):
1. Sort by `TRUE_NUMBEROFPLAY` when every row has it, else by `NUMBEROFPLAY`. Drop duplicate rows on (sort key, `PLAYTYPE`, `CODETEAM`).
2. Keep rows where `POINTS_A` or `POINTS_B` is present. Forward-fill each column, then fill the rest with 0 (a team that has not scored yet is on 0).
3. Skip the game if:
   - it has fewer than 30 scoring rows,
   - the final score is tied, or
   - either team's final score is under 45 (this catches corrupt games such as the 2012-13 TS game 192 with a "6-3" final).
4. Team codes and names come from the most common `CODETEAM` / `TEAM` on rows where that side's score increases. Names are kept as they appeared at the time.
5. Compute the winner's margin per row: `(A - B)` if A won, else `(B - A)`.
6. **Glitch guard:** a row's margin counts only if at least one neighbouring row (previous or next) is within 3 points of it. Rows that fail are treated as margin 0 for trough-finding, so a single bad score row can't create a phantom deficit.
7. `deficit` = `-min(confirmed margin)`, floored at 0. Record the score at that row (as `"trailing-leading"`, e.g. `"34-62"`), `PERIOD` and `MARKERTIME`.
8. `q4_deficit` is the same calculation restricted to rows with `PERIOD >= 4`. The neighbour check still uses the full sequence. It records its own score, quarter and clock.
9. `ot` = max `PERIOD` > 4. `home` = winner is side A (A is the home team in the API).

**Phase mapping for display:** RS "RS", TS "Top 16", PO "Playoffs", PI "Play-In", FF "Final Four".

**Ranking:** sort by deficit descending, then season descending, then gamecode descending (newest first among ties). Equal deficits share a rank, shown as "T-n" when tied.

**Output:** `docs/data/current/comebacks.json`
```json
{
  "generated": "2026-10-14",
  "seasons": [2007, 2026],
  "current_season": 2026,
  "games_scanned": 5055,
  "overall":        [ /* top 25 by deficit */ ],
  "fourth_quarter": [ /* top 25 by q4_deficit */ ],
  "postseason":     [ /* top 25 by deficit, phase in PO/PI/FF */ ]
}
```
Each entry:
```json
{
  "rank": 1, "tied": true,
  "season": 2026, "season_label": "2026-27", "phase": "RS", "round": 5, "gamecode": 45,
  "winner": "OLY", "winner_name": "Olympiacos Piraeus",
  "loser": "PAM",  "loser_name": "Valencia Basket",
  "home": false,
  "deficit": 28, "trailing": "34-62", "quarter": 3, "clock": "08:30",
  "final": "102-97", "ot": true,
  "has_replay": true
}
```
- In `fourth_quarter`, `deficit` / `trailing` / `quarter` / `clock` hold the Q4 values.
- `has_replay` is true when `docs/data/{season}/{gamecode}.json` exists.

**Pipeline:** add a step to `refresh_all.py` Phase 2 ("Biggest Comebacks", `calculate_comebacks.py`). It runs after Phase 1 so the current season's PBP is fresh. The CI commit step already stages `docs/data/`.

**Season rule:** no hardcoded years. Seasons come from `ALL_SEASONS` and labels from `season_label()`, as enforced by `tests/test_no_hardcoded_season.py`.

## Frontend: `docs/records.js` and `docs/records.html`

- Add `{ key: 'comebacks', label: 'Comebacks' }` to the tab list.
- Load `data/current/comebacks.json` lazily on the first click of the Comebacks tab and cache it. If it fails to load, show an inline error message in place of the grid.
- Hide the "Career minimum" filter row on this tab. Show a one-line legend instead: "Largest deficit the winner faced · 2007-08 onward".
- Use the existing three-card `.records-grid`:
  1. **Biggest Comebacks** (overall)
  2. **4th-Quarter Comebacks** (deficit faced in Q4 or OT)
  3. **Playoffs & Final Four** (postseason)
- Keep the existing top-10 / "Show top 25" behaviour and the gold, silver and bronze rank colours.
- Each row shows:
  - rank ("T-1" when tied)
  - matchup: `OLY @ PAM` for an away win, `OLY vs PAM` for a home win; full names go in the `title` attribute
  - a meta line: `2026-27 · RS R5` (postseason rows show the phase label, e.g. `2011-12 · Final Four`)
  - the deficit, large
  - a detail line: `trailed 34-62 · Q3 8:30` (`OT1` etc. for `quarter` > 4)
  - the final, with ` OT` when applicable
- The matchup links to `replay.html?season={season}&game={gamecode}` when `has_replay` is true.
- Rows whose `season` equals the file's `current_season` (written from `CURRENT_SEASON`) get a small "NEW" tag.
- Comeback rows use their own column set (# · Game · Deficit · Final), not the player columns.

## About page

Add a "Biggest Comebacks" methodology entry to `docs/about.html` covering:
- what is measured (the largest deficit the eventual winner faced at any point),
- the glitch guard and skipped games,
- that coverage starts in 2007-08,
- that the 4th-quarter card counts only deficits faced in Q4 or OT.

## Testing

`tests/test_comebacks.py` builds made-up PBP DataFrames and calls the per-game function directly:
- Basic comeback: the winner trails by 15, then wins, so the deficit is 15 with the correct trailing score, quarter and clock.
- Wire-to-wire winner: deficit 0.
- A team that has not scored yet (NaN on one side) counts as 0.
- One spiked score row (e.g. a +25 typo for one row) is ignored.
- The Q4 deficit only reflects rows with `PERIOD >= 4`.
- A game with a final under 45 is skipped (returns None).
- Ranking: tied deficits share a rank, are flagged `tied`, and are ordered newest first.

Plus an integration check after the build: run the script on real data and confirm the success criteria above.

## Out of scope

Blowouts, highest-scoring games and other game records. The tab layout leaves room for them later.
