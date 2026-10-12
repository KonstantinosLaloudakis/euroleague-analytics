# Tale of the Tape & Series Momentum — Series Hub Additions

**Date:** 2026-04-25
**Status:** Spec
**Scope:** Two new sections inside `docs/series.html` (Series Hub).

## Goal

Extend Series Hub with two playoff-specific sections that ship before Play-In begins:

1. **Tale of the Tape** — a side-by-side stat comparison of the two teams in a series, plus a deterministic 3-row "Edges" panel surfacing the most distinctive matchup advantages.
2. **Series Momentum** — a line chart showing how series win probability has shifted after each completed game, with a "biggest swing" callout.

Both features use only data already produced by the existing pipeline; no new fetch endpoints or external data sources.

## Non-goals

- Live in-game / per-possession updates (already covered by `replay.html`).
- Final Four MVP race (premature; revisit once SF teams are set).
- Series-wide combined shot chart, lineup matchup grids, or coach decision tracking.
- Animated transitions on the momentum chart between data refreshes.

## Architecture & placement

Both features become new `<section>` slots inside `docs/series.html`, immediately after the existing Hero section:

```
Hero (existing)
Tale of the Tape (NEW)
Momentum (NEW)
Timeline (existing)
H2H (existing)
Recaps (existing)
```

**Lifecycle rules:**

- **Tale of the Tape** renders whenever a series has both `high_seed.team` and `low_seed.team` populated. Stays visible after the series concludes (becomes a retrospective preview card).
- **Momentum** only renders when `wins.high + wins.low ≥ 1`. Hidden in pure-preview state to avoid a pointless flat line.

**Data flow:**

- All new data is precomputed in Python at export time and embedded in `dashboard.json` under each series entry: `series.<slot>.tale_of_the_tape` and `series.<slot>.momentum`. No new files.
- Frontend (`series.js`) gets two new render functions: `renderTaleOfTheTape()` and `renderMomentum()`, called from the existing `renderSeries()` orchestrator.
- Python: `export_dashboard_data.py` gains two helpers, fed by existing team metrics, `playoff_matchup_probs`, and `playoff_results`.

## Tale of the Tape

### Visual layout

A `stat-card` containing 8 fixed stat rows in a diverging-bar pattern (mirrors the look used elsewhere via `chart_utils.py`), followed by an "Edges" panel with 3 short bullet lines. Team colors come from the existing `TEAM_COLORS` map.

### 8 stat rows (fixed order)

1. Pace (possessions per 40)
2. Adjusted offensive rating
3. Adjusted defensive rating
4. Adjusted net rating
5. 3PT %
6. Paint scoring %
7. FT rate
8. Bench points share

All values are read from the team metrics already serialized in `dashboard.json`. No new metric is computed for the table itself.

If a team is missing any one of these stats in `dashboard.json`, the row is skipped (no "n/a" placeholders).

### Edges panel — deterministic algorithm

A scoring rule generates candidate edges, then picks the top 3 by score with one constraint and one forced inclusion.

**Candidate types and scoring:**

| Type | Score | Inclusion rule |
|------|-------|----------------|
| Net rating gap | `abs(adj_net_high − adj_net_low)` | Always considered |
| 3PT shooting matchup | `abs(3PT%_team − 3PT%_allowed_opp)` × 100 | Always considered |
| Paint shooting matchup | `abs(paint%_team − paint%_allowed_opp)` × 100 | Always considered |
| Pace mismatch | `abs(pace_high − pace_low)` | Considered only if gap ≥ 3.0 poss/40 |
| Bench depth gap | `abs(bench_share_high − bench_share_low)` × 100 | Considered only if gap ≥ 5pp |
| Recent form | `abs(last5_wins_high − last5_wins_low)` | Considered only if gap ≥ 2 |
| RS head-to-head | n/a (forced) | Forced into top 3 if `rs_h2h` has at least 1 entry |

**Selection rules:**

1. If `rs_h2h` has any entries, an H2H edge is forced into the panel and is always rendered last (slot 3).
2. Among the remaining (non-H2H) candidates, drop the lower-scoring of {3PT, Paint} so at most one shooting-matchup edge survives.
3. Sort the surviving candidates by score descending. Tie-breaker: candidate-type priority order (Net → 3PT → Paint → Pace → Bench → Form).
4. Take the top 2 (or top 3 if no H2H qualified) and place them in slots 1–2 (or 1–3). If H2H qualified, append it as slot 3.

**Edge text format (one short sentence each, no LLM):**

- Net: `"OLY: +9.0 net rating advantage"`
- 3PT: `"OLY: 38% from 3 vs MCO defending 36% — slim edge OLY"`
- Paint: `"MCO: 47% in the paint vs OLY allowing 44%"`
- Pace: `"MCO plays 3.2 more possessions per 40 — pace edge MCO"`
- Bench: `"OLY: bench scores 31% vs MCO 24% — depth edge OLY"`
- Form: `"OLY: 4-1 last 5 vs MCO 2-3 — form edge OLY"`
- H2H: `"Split RS series 1-1; MCO took the Athens game"` (or `"OLY swept RS series 2-0"`)

### Data shape in `dashboard.json`

```json
"tale_of_the_tape": {
  "rows": [
    {"metric": "pace",        "high": 78.2,  "low": 80.1,  "label": "Pace (poss/40)"},
    {"metric": "adj_off",     "high": 117.4, "low": 113.8, "label": "Adj. Offense"},
    {"metric": "adj_def",     "high": 103.1, "low": 108.5, "label": "Adj. Defense", "lower_is_better": true},
    {"metric": "adj_net",     "high": 14.3,  "low": 5.3,   "label": "Adj. Net"},
    {"metric": "three_pct",   "high": 37.2,  "low": 35.8,  "label": "3PT %"},
    {"metric": "paint_pct",   "high": 47.1,  "low": 43.9,  "label": "Paint %"},
    {"metric": "ft_rate",     "high": 0.28,  "low": 0.24,  "label": "FT Rate"},
    {"metric": "bench_share", "high": 31.1,  "low": 28.4,  "label": "Bench %"}
  ],
  "edges": [
    {"text": "OLY: +9.0 net rating advantage",                    "favor": "high", "type": "net"},
    {"text": "OLY: 38% from 3 vs MCO defending 36% — slim edge",  "favor": "high", "type": "three_pct"},
    {"text": "Split RS series 1-1; MCO took the Athens game",     "favor": null,   "type": "h2h"}
  ]
}
```

`favor` ∈ `{"high", "low", null}` and is used by the frontend to color the bullet's leading dot with the team color.

`lower_is_better` flag on a row tells the diverging-bar renderer to invert the visual "winner" without changing the numeric values shown.

## Series Momentum

### Visual layout

Plotly line chart, two lines (high seed and low seed), x-axis = discrete checkpoints (`Pre-series`, `After G1`, `After G2`, …), y-axis = series win probability (0–100%). Markers on each point. Below the chart, a single-line "Biggest swing" callout.

### Computing checkpoints

For each checkpoint, recompute series WP from scratch using:

- Current series score at that point (`wins.high`, `wins.low`).
- Remaining games' home/away pattern, sliced from `home_pattern`.
- Existing `playoff_matchup_probs` for per-game home/away/neutral WP.
- The same best-of-N DP that lives in `playoffs.js` (`seriesProbHCA`), ported to Python as `compute_remaining_series_wp()`. ~30 lines, identical logic.

After G1 the function knows: "score is 1-0, three games left in pattern [low, low, high]" and rolls forward.

The Final round is single game, neutral venue: only Pre-series + After G1 checkpoints; biggest-swing logic still works (defaults to that single delta).

### Biggest-swing callout

After computing the array of `(checkpoint_label, series_wp_high)` pairs, find the consecutive pair with the largest absolute delta in `series_wp_high`. The callout names the game and magnitude:

> Biggest swing: G2 — MCO win shifted series WP +24%

If only one game has been played, that single transition is the swing by default.

### Data shape in `dashboard.json`

```json
"momentum": {
  "checkpoints": [
    {"label": "Pre-series", "high_wp": 60.7, "low_wp": 39.3},
    {"label": "After G1",   "high_wp": 75.4, "low_wp": 24.6},
    {"label": "After G2",   "high_wp": 51.2, "low_wp": 48.8}
  ],
  "biggest_swing": {
    "from_label": "After G1",
    "to_label": "After G2",
    "game_num": 2,
    "delta_pct": 24.2,
    "shifted_to": "low",
    "winner_team": "MCO"
  }
}
```

Absent (`null` or key missing) when `wins.high + wins.low == 0`.

## Files touched

| File | Change |
|------|--------|
| `export_dashboard_data.py` | Add `build_tale_of_the_tape()`, `build_momentum()`, helper `compute_remaining_series_wp()`. Wire both into the existing series-builder loop so each entry in `series.qf1`…`series.final` gets `tale_of_the_tape` and `momentum` keys. |
| `docs/series.html` | Add Plotly CDN `<script>` tag (currently absent on this page). Add two new `<section>` slots in the page skeleton. |
| `docs/series.js` | Add `renderTaleOfTheTape()` (~80 lines) and `renderMomentum()` (~60 lines); call them from `renderSeries()` after `renderHero()`. |
| `docs/series.html` (inline `<style>`) | New styles for tale-of-the-tape rows (diverging-bar pattern) and momentum container. Match existing `.stat-card` aesthetic. |
| `docs/about.html` | One-paragraph description of both features under the playoff section. |

No new files. No new data files. No changes to the refresh pipeline orchestration.

## Edge cases

1. **Series has no team yet** (e.g., `qf3` before Play-In ends — `awaiting_teams`). Both new sections check the same flag the Hero already uses and skip rendering. No half-populated cards.
2. **Series with no RS H2H entries.** Edges panel skips the forced-H2H rule and just takes top 3 by score.
3. **Final round = single game, neutral venue.** No best-of-N DP needed. Tale of the Tape still runs (uses `home_pattern` only for context). Momentum has only Pre-series + After G1; biggest-swing logic still works.
4. **Missing matchup_probs for a pair.** Mirror the existing JS fallback to Elo (`eloWinProb` in `playoffs.js`) in the Python helper so both sides produce identical numbers.
5. **Pace / shooting splits missing for some team.** Tale-of-the-Tape skips that row rather than rendering "n/a"; Edges panel skips affected candidate types.
6. **First playoff round of any season.** Currently R38, no playoff games yet. Tale of the Tape renders for QF1–QF4 once Play-In sets seeds 7/8; Momentum stays hidden until QF Game 1.
7. **Determinism of Edges picks.** Sort by score descending; tie-break by candidate priority order (Net → 3PT → Paint → Pace → Bench → Form). Same input → same edges on every refresh.

## Testing plan

No test runner is configured (per `CLAUDE.md`). Validation steps:

1. Run `python refresh_all.py --no-fetch` to regenerate `dashboard.json`.
2. Inspect `series.qf1.tale_of_the_tape` and `series.qf1.momentum` for sane values via a small inline Python script (utf-8 read of the JSON).
3. Open `docs/series.html?id=qf1` locally; verify both sections render and look right on mobile width.
4. Open `docs/series.html?id=qf3` (likely `awaiting_teams` until Play-In ends) — confirm sections gracefully hide.
5. Click through `playoffs.html` → Series Hub for each QF to confirm the existing entry path still works.

## YAGNI / explicit cuts

- No richer "Edges" copy variations beyond the templates above.
- No animations on chart updates.
- No per-game WP-curve sparklines under the momentum chart (the Series Hub timeline already links to `replay.html` per game).
- No leverage / pivot-moment panel (was option C in brainstorm; deferred).
- No preview card for Tale of the Tape on `playoffs.html` (deferred — trivial to add later if desired).
