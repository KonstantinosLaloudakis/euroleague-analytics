# Path to Title: Per-Team Championship Path Visualization

**Date:** 2026-04-18
**Status:** Approved

## Overview

A new section on `playoffs.html` that shows each playoff-eligible team's road to the championship. Hybrid UI: a grid comparing all teams side-by-side, plus an on-click detail view revealing a branching tree of possible future opponents per round.

## Goals

- Answer "who has the easiest/hardest path?" at a glance (grid view)
- Answer "what does team X need to do to win it all?" in depth (detail view)
- Work from day 1 of the playoffs (pre-playoff state renders purely from Monte Carlo)
- Tell the full story arc: completed rounds with actual results + remaining rounds with probabilities

## Architecture

Computation is server-side in `export_dashboard_data.py`. A new function `compute_path_to_title(playoff_results, matchup_probs, seeded_teams, n_sims=10000)` reuses the existing Monte Carlo machinery that powers `compute_championship_odds`. Results are precomputed once per refresh and stored in `dashboard.json` under a new key `path_to_title`.

**Rationale for server-side:** The frontend's existing client-side Monte Carlo reacts to user bracket picks; Path to Title must reflect the real state, not user picks. Server-side precomputation also caches the 10k-sim result rather than re-running per page interaction.

## Data Structure

New key in `dashboard.json`:

```json
"path_to_title": [
  {
    "team": "OLY",
    "status": "alive",
    "eliminated_at": null,
    "championship_odds": 27.3,
    "rounds": [
      {
        "round": "play_in",
        "status": "unreached",
        "reach_prob": 0.0
      },
      {
        "round": "qf",
        "status": "completed",
        "actual_opponent": "RED",
        "actual_result": "won",
        "series": [3, 1],
        "reach_prob": 100.0
      },
      {
        "round": "sf",
        "status": "upcoming",
        "reach_prob": 100.0,
        "win_prob": 62.4,
        "branches": [
          { "opponent": "MAD", "reach_prob_for_opp": 68.0, "win_prob_vs": 58.5 },
          { "opponent": "HTA", "reach_prob_for_opp": 22.0, "win_prob_vs": 71.3 },
          { "opponent": "ULK", "reach_prob_for_opp": 10.0, "win_prob_vs": 65.2 }
        ]
      },
      {
        "round": "final",
        "status": "upcoming",
        "reach_prob": 62.4,
        "win_prob": 54.1,
        "branches": [
          { "opponent": "PAM", "reach_prob_for_opp": 42.0, "win_prob_vs": 52.8 },
          { "opponent": "MAD", "reach_prob_for_opp": 18.0, "win_prob_vs": 55.4 },
          { "opponent": "ULK", "reach_prob_for_opp": 15.0, "win_prob_vs": 58.1 }
        ]
      }
    ]
  }
]
```

**Fields:**
- `status`: `alive` | `eliminated` | `champion`
- `eliminated_at`: `null` | `"play_in"` | `"qf"` | `"sf"` | `"final"`
- `rounds[].status`: `completed` | `in_progress` | `upcoming` | `unreached`
- `rounds[].reach_prob`: P(team reaches this round | current state), 0-100
- `rounds[].win_prob`: P(team wins this round | reaches it), aggregated across all possible opponents weighted by reach prob
- `rounds[].branches`: top 2-3 possible opponents, sorted by `reach_prob_for_opp` descending, truncated when cumulative reach ≥ 90% or after 3 entries
- Completed rounds: only `actual_opponent`, `actual_result`, `series`, `reach_prob=100` are set; `branches` omitted
- Unreached rounds (e.g., Play-In for seeds 1-6): only `reach_prob=0` set

## Computation

For each playoff-eligible team, run 10,000 Monte Carlo iterations from the current real state. For each simulation:

1. Advance the bracket to completion from the current `playoff_results` state (reusing the same simulation path as `compute_championship_odds`)
2. Record for this team:
   - Which round they exit (if not champion)
   - Which opponent they faced at each round they reached
   - Whether they won at each round

Aggregate across simulations:
- `reach_prob[round]` = fraction of sims where team reached that round
- For each round they reach, `branches` = opponent distribution weighted by P(opp reaches) × P(we beat opp from `matchup_probs`)
- `win_prob[round]` = weighted average of `win_prob_vs` across branches

For completed games, bypass Monte Carlo and populate from `playoff_results` directly.

## Frontend — Grid View (default)

New `<section id="path-to-title-section">` on `playoffs.html`, placed below the existing `#playoff-recaps-section`.

Layout: a compact table, one row per team, columns for each round plus championship odds:

| Status | Team | Play-In | QF | SF | Final | 🏆 | |
|--------|------|---------|-----|-----|-------|-----|------|
| 🟢 | Olympiacos | — | WON 3-1 | 62% | 54% | 27% | expand |
| 🟢 | Valencia | — | 2-1 | 48% | 41% | 18% | expand |
| 🟢 | Hapoel | WON vs PAN | 72% | 39% | 26% | 10% | expand |
| ⚪ | Zalgiris | LOST vs PAN | — | — | — | 0% | — |

**Styling:**
- Sorted by `championship_odds` descending; eliminated teams drop to bottom, `opacity: 0.5`
- Status dot: green (alive), gray (eliminated), gold (champion)
- Completed cells: "WON 3-1" green, "LOST 1-3" red
- In-progress cells: series score (e.g., "2-1") with pulse animation via CSS `@keyframes`
- Upcoming cells: % with color-coded heatmap (red ≤ 20%, amber 20-50%, green ≥ 50%)
- Pre-playoffs state: all rounds show probabilities; no "actual" cells
- Clicking an alive team's row toggles the detail view inline
- Only one team can be expanded at a time

**Teams shown:** All 10 playoff-eligible teams (6 seeded + 4 play-in). Non-playoff teams are not shown.

## Frontend — Detail View (click to expand)

Inline expansion directly below the clicked row reveals a horizontal SVG tree:

```
        [OLY logo]
              │
              ▼
   QF: WON 3-1 vs RED ✓  (completed, green)
              │
              ▼
     SF (62% to win)
         ┌────┼────┐
         │    │    │
       MAD  HTA  ULK
       68%  22%  10%   (P opp reaches SF)
       58%  71%  65%   (P we win vs them)
         │    │    │
         └────┼────┘
              ▼
   Final (54% to win)
              │
              ▼
           🏆 27%
```

**Rules:**
- Completed rounds: single locked branch showing actual opponent + result
- Upcoming rounds: top 2-3 opponents as branches (from `rounds[].branches`)
- Each branch shows: opponent code, reach probability, win probability vs them
- Root node shows team logo; leaf shows 🏆 with championship odds
- Eliminated teams: no expand option from grid (their full story fits in the grid row)
- Implementation: inline SVG, not Plotly. Reuses patterns from existing bracket SVG code in `playoffs.js`
- Auto-sizes (~300-400px tall, full section width)
- Only one team expanded at a time

## Backend Changes

### export_dashboard_data.py

New function:
- `compute_path_to_title(playoff_results, matchup_probs, seeded_teams, n_sims=10000)` — returns the `path_to_title` array

Integrated into the existing playoff tracking block alongside `compute_championship_odds` and `build_playoff_recaps`. Output written to `dashboard.json` under the `path_to_title` key.

### Edge Cases

- **No playoff teams yet** (regular season in progress): function returns `[]`, frontend hides the section
- **Pre-playoff state** (playoff teams known but no games played): all rounds computed purely from Monte Carlo
- **After play-in**: losers marked `eliminated_at: "play_in"`, winners continue
- **During a QF series**: Monte Carlo conditions on partial series state (already supported by `compute_championship_odds`)
- **Champion crowned**: `status: "champion"` for winner; all others `eliminated`

## Frontend Changes

### playoffs.html

- Add `<section id="path-to-title-section">` below `#playoff-recaps-section` (hidden by default)
- Add CSS for the grid table, status indicators, heatmap cells, and the expanded detail SVG

### playoffs.js

New functions:
- `renderPathToTitle(data)` — top-level render, populates the grid table, wires up row click handlers
- `renderPathDetailTree(team, container)` — renders the SVG tree for the expanded row
- `pathRoundCell(team, round)` — returns the HTML for a single round's grid cell
- `onPathRowClick(teamCode)` — toggles expansion, manages single-row-open state

Called from `init()` right after `renderPlayoffRecaps(data.playoff_recaps || [])`.

## Testing

- **Server-side**: unit test `compute_path_to_title` against a mocked playoff state with known outcomes — verify branch probabilities are within expected Monte Carlo tolerance (±2% for 10k sims)
- **Sanity check**: sum of `reach_prob_for_opp` within each round's branches is close to 100% (small noise acceptable; branches may be truncated at 3 entries)
- **Frontend**: manual verification via Playwright — load playoffs.html, scroll to Path to Title section, expand a team row, verify tree renders with correct branches, resize to mobile width
- **Pre-playoff test**: with today's data (no games played), verify grid renders with 10 teams, all rounds showing probabilities only
- **Mock playoff test**: manually edit `playoff_results` to simulate a post-QF state, re-export, verify eliminated teams appear grayed at bottom, winners' paths compress correctly

## Page Layout (playoffs.html) — After

Top-to-bottom order:

1. Bracket (existing, with live results)
2. Championship Odds Tracker chart (existing)
3. Playoff Recap Cards (existing)
4. **Path to Title** (new)

## Out of Scope

- Animations between states (e.g., teams sliding to "eliminated" section when they lose) — static render each refresh
- Historical path-to-title comparisons across seasons
- Editable "what if" detail view (clicking a branch to see the downstream path) — Path to Title reflects real state only; the existing interactive bracket already serves this purpose
- Mobile-specific redesign beyond responsive CSS (grid collapses to stacked cards on narrow widths)
