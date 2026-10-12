# Series Hub: Dedicated Playoff Series Page

**Date:** 2026-04-18
**Status:** Approved

## Overview

A new standalone page `series.html` that drills into a single playoff series (best-of-5 in Euroleague). It tells the series story: who's playing, the current state, series win probabilities, game-by-game timeline, regular-season head-to-head, and recap cards for completed games. Scoped to the current season (2025) only for v1.

## Goals

- Give each playoff matchup its own narrative home (`playoffs.html` is a whole-bracket overview; Series Hub goes deep on one matchup)
- Work from day 0: a series with no games played yet shows pregame context (RS H2H + upcoming schedule + pregame WPs)
- Evolve as games are played: completed games flow into the timeline and the recap section
- Reuse existing data and components rather than building parallel infrastructure

## Architecture

Computation is server-side in `export_dashboard_data.py`. A new function `compute_series_data(playoff_results, matchup_probs, seeded_teams, mc_sim_per_series, games_df)` produces a per-slot dictionary written to `dashboard.json` under a new key `"series"`. Per-series win probabilities piggyback on the existing Monte Carlo sim in `compute_championship_odds` — that sim already iterates every series outcome; we extend it to tally per-series wins alongside championship wins.

Frontend is a new standalone page (`series.html` + `series.js`) matching the existing vanilla-JS pattern. No framework, no build step. The page reads `?id=qf1` from the URL, pulls the matching entry from `dashboard.json.series`, and renders four stacked sections.

Navigation: `playoffs.html` is modified so bracket matchup lines and recap cards wrap their contents in `<a href="series.html?id=...">`.

## URL Scheme

Slot-based: `series.html?id=<slot>`, where `<slot>` is one of:

- `qf1`, `qf2`, `qf3`, `qf4` — quarterfinals
- `sf1`, `sf2` — semifinals
- `final` — the championship series

Slot IDs are **stable** regardless of which teams are seeded — this lets us link into a future round (e.g., `sf1`) before its teams are determined, and the URL stays the same after the teams resolve.

Bracket convention (matches existing `_bracket` structure in `docs/playoffs.js` where `qfN` maps to `quarters[N-1]`, `sfN` to `semis[N-1]`):

- `qf1` = seed 1 vs seed 8
- `qf2` = seed 2 vs seed 7
- `qf3` = seed 3 vs seed 6
- `qf4` = seed 4 vs seed 5
- `sf1` = winner(qf1) vs winner(qf4)
- `sf2` = winner(qf2) vs winner(qf3)
- `final` = winner(sf1) vs winner(sf2)

Missing or invalid `?id=` falls back to a lightweight index that lists all 7 slots with their current state.

## Data Structure

New top-level key in `dashboard.json`:

```json
"series": {
  "qf1": {
    "id": "qf1",
    "round": "qf",
    "label": "Quarterfinal 1",
    "format": "best_of_5",
    "home_pattern": ["high", "high", "low", "low", "high"],

    "high_seed": { "team": "OLY", "seed": 1, "logo": "OLY.png" },
    "low_seed":  { "team": "MCO", "seed": 8, "logo": "MCO.png" },

    "status": "in_progress",
    "wins": { "high": 1, "low": 0 },
    "winner": null,

    "series_win_prob": { "high": 72.4, "low": 27.6 },

    "games": [
      {
        "game_num": 1,
        "status": "completed",
        "date": "2026-04-21",
        "home": "OLY",
        "away": "MCO",
        "home_score": 92,
        "away_score": 78,
        "winner": "OLY",
        "pregame_wp": { "home": 68.0, "away": 32.0 },
        "gamecode": 345
      },
      {
        "game_num": 2,
        "status": "upcoming",
        "date": "2026-04-23",
        "home": "OLY",
        "away": "MCO",
        "pregame_wp": { "home": 66.1, "away": 33.9 }
      }
    ],

    "rs_h2h": [
      {
        "round": 7,
        "home": "OLY",
        "away": "MCO",
        "home_score": 84,
        "away_score": 79,
        "winner": "OLY"
      },
      {
        "round": 22,
        "home": "MCO",
        "away": "OLY",
        "home_score": 91,
        "away_score": 88,
        "winner": "MCO"
      }
    ]
  },
  "qf2": { "...": "same shape" },
  "sf1":  { "...": "same shape (may have null seeds until QFs resolve)" },
  "final":{ "...": "same shape" }
}
```

**Field notes:**

- **Seven slots always present.** Unresolved slots have `high_seed: null` and/or `low_seed: null`.
- **`status`** is one of: `not_started` (0-0), `in_progress` (at least one game played, not decided), `completed` (winner determined).
- **`wins`** tracks current series score (high_seed's wins vs low_seed's wins).
- **`series_win_prob`** values sum to 100 (±0.1 tolerance for rounding). For a `completed` series, the winner's value is 100.0, loser 0.0.
- **`games`** is always length 5. Game 4 and Game 5 entries have `status: "upcoming"` unless a sweep occurs, in which case they have `status: "unnecessary"`.
- **`pregame_wp`** for upcoming games uses the existing `_matchup_prob` function (same formula as everywhere else: adj_net 0.75 + elo 0.25 + dampened HCA).
- **`rs_h2h`** length is 0 (no RS meetings), 1 (one meeting — rare but possible with schedule gaps), or 2 (standard Euroleague — each team hosts once).
- **`gamecode`** links into `replay.html?season=2025&gamecode=<n>` for completed games.

## Monte Carlo Integration

`compute_championship_odds` currently simulates the bracket 50,000 times (seeded RNG) and tallies championship wins per team. We extend its per-sim state tracking:

```python
# Inside the sim loop, after each series resolves:
series_wins_counter[slot_id][winning_team] += 1
```

After the loop, convert to percentages:

```python
series_win_prob[slot_id][team] = 100 * series_wins_counter[slot_id][team] / n_sims
```

These values get passed into `compute_series_data` and placed in each slot's `series_win_prob` field.

**State-aware:** Because the sim starts from the actual `playoff_results` state, `series_win_prob` naturally reflects current series state (e.g., down 0-1 teams have lower series win%).

## Page Layout

Four stacked sections (in order):

### Section 1 — Series Hero

- Team logos and names with seeds
- Current series score (e.g., "OLY leads 1-0")
- Best-of-5 label and home pattern
- Horizontal probability bar: high vs low series win %
- For completed series: shows the winner prominently, WP bar collapses to "Series complete"

### Section 2 — Game-by-Game Timeline

- Horizontal strip of 5 game boxes (G1–G5)
- Each box shows: game number, date, home/away venue indicator, score (if completed) or pregame WP (if upcoming)
- Completed boxes link to `replay.html?season=2025&gamecode=<n>`
- G4/G5 labeled "if necessary" when unresolved; hidden entirely on a sweep
- Scrolls horizontally on mobile

### Section 3 — Regular-Season H2H

- Two side-by-side mini game cards (one per RS meeting)
- Each card: round number, venue, final score, winner indicator
- Summary line below: "Season split: X-Y · Combined scoring margin: TEAM +Z"
- Fallback copy when no RS meetings exist: "No regular-season meetings"
- Stacks vertically on mobile

### Section 4 — Game Recaps

- Reuses the existing recap-card component from `playoffs.js`
- One card per completed game, stacked vertically
- Hidden entirely before Game 1 completes

## Navigation

**Into `series.html`:**

- `playoffs.html` bracket lines: wrap each matchup line in `<a href="series.html?id=qf1">`
- `playoffs.html` recap cards: wrap each card in `<a href="series.html?id=qf1">`
- Entry points must be added for all 7 slots

**Out of `series.html`:**

- Breadcrumb at top: "← Back to Playoffs" → `playoffs.html`
- Team logos/names in hero → `team.html?team=<code>`
- Completed game boxes in timeline → `replay.html?season=2025&gamecode=<n>`

Players link-out (section 6 from brainstorming) is deferred — users can reach `players.html` from the main nav.

## Edge Cases

| Situation | Behavior |
|---|---|
| Invalid `?id=` (e.g., `?id=qf9`) | "Series not found" message with back link |
| Missing `?id=` param | Index page listing all 7 slots with current state |
| Both teams TBD (e.g., `sf1` before QFs done) | Placeholder hero: "Winner of QF1 vs Winner of QF4 · Series begins once QFs complete" |
| One team resolved, one TBD | Show resolved team on its side, "Opponent: Winner of QF2" on the other |
| Sweep (series ends 3-0) | Hide G4 and G5 boxes entirely (no "if necessary" labels) |
| No RS H2H | Section 3 renders "No regular-season meetings" |
| Empty `playoff_results` (pre-season) | All 7 slots render with TBD placeholders; series_win_prob comes from MC sim using seeded teams only |

## Styling

- Extend `docs/style.css` with a handful of series-specific classes (`.series-hero`, `.series-timeline`, `.series-game-box`, `.series-h2h-card`)
- Reuse existing color variables and team colors
- No Plotly required — all visuals are HTML/CSS (the WP bar is a styled div, the timeline is flexbox)

## Testing

### Unit (Python)

- `test_series_data.py` — exercises `compute_series_data` across multiple series states:
  - `not_started` (0-0, no games)
  - `in_progress` (1-0, 2-1)
  - `completed` (3-0 sweep, 3-2)
  - Unresolved slot (`sf1` with `qf1`/`qf2` both pending)
  - No RS H2H
- Extraction pattern matches `test_path_to_title_play_in_states.py`: AST-unparse the nested function from `export_dashboard_data.py` for isolated testing

### Manual (browser)

- Load `series.html?id=qf1` through each state by editing a local fixture `dashboard.json`
- Verify bracket-line and recap-card clicks land on the right slot
- Check responsive behavior at mobile width

### Visual regression

- Take a Playwright screenshot of `series.html?id=qf1` in one canonical state (e.g., 1-0 series)
- Store in repo alongside other playoff screenshots (e.g., `series_hub_qf1.png`)

## Out of Scope (deferred to v2)

- Conditional "what if" win% tree (section 4 in brainstorm)
- Key player spotlight with trend arrows (section 6)
- Shot chart comparison (section 7)
- Lineup usage (section 8)
- Historical playoff series (2007–2024) — current season only for v1
- Per-series notification / alert on schedule changes
- Social share image per series

## Documentation

Update `docs/about.html` — add a paragraph under the Playoffs description explaining that each bracket line and recap card clicks into a dedicated Series Hub page with game-by-game timeline, RS H2H, and recaps.
