# Playoff Tracker: Live Results, Championship Odds & Recap Cards

**Date:** 2026-04-17
**Status:** Approved

## Overview

Three interconnected features that transform the playoff bracket page from a pure simulator into a live playoff tracking experience. Actual game results flow in after each game day via the existing `refresh_all.py` pipeline, updating the bracket, championship odds, and generating recap cards automatically.

## Feature 1: Live Playoff Results in Bracket

### Behavior

- On page load, `playoffs.js` reads `playoff_results` from `dashboard.json` and auto-fills completed games
- Completed games are locked (non-clickable), showing actual scores and series status
- Unplayed games remain interactive for "what if" simulation
- Championship odds recalculate from the current real state as baseline
- "Reset" button clears user picks but keeps real results locked
- Series status badge on each matchup card (e.g. "OLY leads 2-1")

### Data Structure

New key in `dashboard.json`:

```json
"playoff_results": {
  "play_in": {
    "game_a": {
      "home": "ZAL",
      "away": "PAN",
      "home_score": 85,
      "away_score": 78,
      "winner": "ZAL",
      "date": "2026-04-22"
    },
    "game_b": {
      "home": "MCO",
      "away": "BAR",
      "home_score": null,
      "away_score": null,
      "winner": null
    },
    "game_c": null
  },
  "qf": {
    "1v8": {
      "games": [
        { "home": "OLY", "away": "TBD", "home_score": 92, "away_score": 80, "date": "2026-04-28" },
        { "home": "OLY", "away": "TBD", "home_score": 88, "away_score": 85, "date": "2026-04-30" }
      ],
      "series": [2, 0],
      "winner": null
    },
    "2v7": { "games": [], "series": [0, 0], "winner": null },
    "3v6": { "games": [], "series": [0, 0], "winner": null },
    "4v5": { "games": [], "series": [0, 0], "winner": null }
  },
  "sf": {
    "sf1": { "game": null, "winner": null },
    "sf2": { "game": null, "winner": null }
  },
  "final": {
    "game": null,
    "winner": null
  }
}
```

### Seeding and Matchup Resolution

- Play-in teams are determined by final regular season seeding (positions 7-10)
- Play-in results determine seeds 7 and 8 for quarterfinals
- Quarterfinal matchups: 1v8, 2v7, 3v6, 4v5 (best-of-5, 2-2-1 HCA)
- Final Four: SF1 = winner of 1v8 vs winner of 4v5, SF2 = winner of 2v7 vs winner of 3v6
- Final: winner of SF1 vs winner of SF2

### Frontend Changes (playoffs.js)

- New `applyRealResults(data)` function called on init, before user interaction
- Locked games get a distinct visual treatment (solid background, score displayed, no hover/click)
- Series progress bar or pill indicator (e.g. filled/empty dots for games won)
- When user resets bracket, real results remain — only user-picked future games clear

## Feature 2: Championship Odds Tracker

### Behavior

- Plotly line chart rendered on the playoffs page, below the bracket
- X-axis: game days, labeled with round context (e.g. "Play-In Day 1", "QF G1")
- Y-axis: championship probability (0-100%)
- One line per team, colored by `TEAM_COLORS`
- Hover tooltip shows exact %, team name, and what game(s) were played that day
- Eliminated teams' lines drop to 0% and gray out
- First data point is pre-playoff baseline odds from Monte Carlo simulation

### Data Structure

New key in `dashboard.json`:

```json
"championship_odds_history": [
  {
    "date": "2026-04-21",
    "label": "Pre-Playoff",
    "odds": {
      "OLY": 28.5,
      "PAM": 22.1,
      "ULK": 15.3,
      "MAD": 12.8,
      "HTA": 8.1,
      "ZAL": 5.2,
      "PAN": 3.8,
      "RED": 2.1,
      "MCO": 1.5,
      "BAR": 0.6
    }
  },
  {
    "date": "2026-04-22",
    "label": "Play-In Day 1",
    "odds": { "OLY": 28.5, "PAM": 22.1, "ZAL": 6.8, "PAN": 1.9 }
  }
]
```

### Computation

After each game day during playoffs:
1. Load current `playoff_results` (real games played so far)
2. Run the bracket Monte Carlo (10,000 iterations) from the current real state forward
3. For each remaining unplayed matchup, use `playoff_matchup_probs` to simulate outcomes
4. Record each surviving team's championship probability
5. Append the new snapshot to `championship_odds_history`

This runs as part of the existing `export_dashboard_data.py` pipeline.

### Frontend Changes

- New `renderChampionshipOdds(history)` function in `playoffs.js`
- New `<div id="championship-odds">` container in `playoffs.html`
- Chart sizing: full-width, ~400px height
- Legend positioned inline or below, showing team badge + current %

## Feature 3: Playoff Recap Cards

### Phase 1 (Ship First)

Compact card per completed playoff game showing:
- **Score** and date
- **Series status** (e.g. "Series tied 1-1")
- **Pre-game win probability** for the winner
- **Upset badge** when the lower-probability team wins (pre-game prob < 40%)
- **Championship odds delta** for both teams (e.g. "OLY: 28.5% -> 31.2% (+2.7%)")

Cards displayed in reverse chronological order on the playoffs page, in a dedicated section below the championship odds chart.

### Phase 2 (Add Later)

- Top performers: points and PIR from box score data
- WPA leaders for the game from play-by-play data
- Key momentum swings / largest lead changes

### Data Structure

New key in `dashboard.json`:

```json
"playoff_recaps": [
  {
    "date": "2026-04-22",
    "round": "play_in",
    "label": "Play-In Game A",
    "home": "ZAL",
    "away": "PAN",
    "home_score": 85,
    "away_score": 78,
    "winner": "ZAL",
    "pre_game_win_prob": 57.0,
    "is_upset": false,
    "series": [1, 0],
    "series_label": "ZAL leads 1-0",
    "championship_odds_before": { "ZAL": 5.2, "PAN": 3.8 },
    "championship_odds_after": { "ZAL": 6.8, "PAN": 1.9 }
  }
]
```

### Frontend Changes

- New `renderPlayoffRecaps(recaps)` function in `playoffs.js`
- New `<div id="playoff-recaps">` container in `playoffs.html`
- Card design: dark card with team colors on left/right borders, score prominently centered, odds shift below
- Upset cards get a highlighted border or badge

## Backend Changes

### export_dashboard_data.py

New functions:

- `detect_playoff_phase()` — Determine if we're in play-in, QF, SF, or final. Playoff games are identified by GameCode > 380 (regular season = 38 rounds x 10 games = 380). The Euroleague API serves them with the same endpoints. Phase is inferred from the number and participants of completed playoff games
- `build_playoff_results(games)` — Map fetched game data to the `playoff_results` structure, matching games to the correct bracket slot by teams and round
- `compute_championship_odds(playoff_results, matchup_probs)` — Run 10,000 Monte Carlo iterations from current bracket state, return per-team championship probability
- `build_playoff_recaps(playoff_results, odds_before, odds_after)` — Generate recap card data for each completed game, including upset detection and odds deltas
- `append_odds_history(history, new_snapshot)` — Add today's championship odds to the history array

All integrated into the existing export flow, gated by whether playoff games exist in the data.

### refresh_all.py

- Skip regular-season-only visualizations during playoffs (remaining SOS, schedule grid, clutch matchups, seed distribution) — these are already handled by the 0-remaining-games guards
- The CI schedule (GitHub Actions) needs manual update from Wed-Sat to match playoff game days

### simulate_monte_carlo.py

- No changes needed for regular season simulation (it already handles 0 remaining games)
- The championship odds Monte Carlo is a separate computation in `export_dashboard_data.py` that operates on the bracket level, not the regular season level

## Page Layout (playoffs.html)

Top-to-bottom order on the playoffs page:

1. **Bracket** (existing, enhanced with real results)
2. **Championship Odds Tracker** (new chart)
3. **Playoff Recap Cards** (new section, reverse chronological)

## Data Flow

```
Game day ends
  -> CI triggers refresh_all.py
    -> fetch_mvp_data_v2.py fetches new game results (including playoff games)
    -> export_dashboard_data.py:
      1. Detects playoff games in results
      2. Builds playoff_results structure
      3. Runs championship Monte Carlo from current state
      4. Generates recap cards with odds deltas
      5. Appends to championship_odds_history
      6. Writes everything to dashboard.json
  -> Frontend loads updated dashboard.json
    -> Bracket shows real results locked + simulator for remaining
    -> Championship odds chart updates with new data point
    -> New recap cards appear for latest games
```

## Out of Scope

- Live in-game updates (we process after game day, not during games)
- Phase 2 recap card enhancements (WPA, player stats) — deferred
- Historical playoff comparisons across seasons
- Playoff-specific oracle predictions (regular season oracle is sufficient context)
