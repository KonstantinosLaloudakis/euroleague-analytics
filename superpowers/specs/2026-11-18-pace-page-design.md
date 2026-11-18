# Pace Page — Design

**Date:** 2026-11-18
**Status:** Agreed in conversation; prototype analysis published as a private artifact.

## Why

Commentators quote "70–71 possessions" to describe a slow team. Across 20 seasons of
play-by-play that number used to be the league average: pace sat between 69.6 and 71.7
for 15 seasons (2007-08 to 2021-22), then rose five seasons in a row to 75.1 in
2026-27. No site publishes this history for the Euroleague, which fits the
"Basketball Reference for Euroleague" positioning.

## What it shows

A new page, `docs/pace.html` ("Pace", in the **Teams** nav group):

1. **Headline cards**: league pace this season with change vs last season; how many
   seasons in a row pace has risen and from what; the slowest team this season.
2. **League pace by season**, 2007-08 to now (line), with the band of the pre-climb
   seasons shaded.
3. **Every team this season**: pace this season vs last season (dumbbell), with a
   toggle between **raw** pace and **opponent-adjusted** pace. Adjusted pace is how
   much faster or slower a team's games run than its opponents' usual pace; it
   corrects early-season schedule bias (e.g. Panathinaikos 2026-27: raw rank 14th of
   20, adjusted 6th-slowest).
4. **Regular season vs playoffs** per season (paired dots). Playoff series were slower
   in 17 of 18 seasons.
5. **Pace vs winning**: every completed team-season, pace relative to league vs net
   rating, champions highlighted.
6. **Slowest and fastest games** since 2007 (table, replay link where one exists).

And on the **Team Deep-Dive** page: a "Pace" card with the team's pace by season
against the league average, plus this season's raw and adjusted rank.

`docs/about.html` gets a "Pace & Possessions" section and a Dashboard Pages entry.

Out of scope: seconds per possession (offence vs defence tempo); the
underdog-by-game-pace and who-sets-the-pace analyses from the prototype; changing the
existing matchup-card pace in `export_dashboard_data.compute_team_box_metrics`.

## Definitions

- Possessions per team = FGA + 0.44 × FTA − OREB + TOV. FGA counts `2FGM 2FGA 2FGAB
  3FGM 3FGA 3FGAB LAYUPMD LAYUPATT DUNK` (the last three are 2008-09 to 2014-15 codes);
  FTA counts `FTM FTA`; OREB is `O`; TOV is `TO`.
- Game possessions = mean of both teams' counts. Pace = game possessions × 40 / minutes.
- Minutes = 40 + 5 × overtimes. The feed labels every overtime `PERIOD 5`; the overtime
  count comes from the `MINUTE` column (OT1 ends at 46, OT2 at 51, …):
  `round((max MINUTE − 41) / 5)`, at least 1.
- "Regular season" = phases `RS` and `TS` (Top 16). "Playoffs" = phase `PO` only (not
  Final Four, not play-in).
- League pace = mean game pace over regular-season games. Team pace = mean pace of the
  team's regular-season games. `pace_rel` = team pace − league pace.
- Adjusted pace (`adj_rel`) = mean over the team's games of
  (game pace − league pace − opponent's `pace_rel`).
- Ratings per 100 possessions use game possessions: ORtg = 100 × points / possessions.
- Champion = winner of the season's highest-gamecode `FF` game (same rule as
  `export_dashboard_data.championship_final_gamecode`).

## Data

Computed in the existing one-pass game-records engine (`calculate_game_records.py`
over `pbp_games.iter_games()`), written to `docs/data/current/pace.json`. CI already
commits `docs/data/`.
