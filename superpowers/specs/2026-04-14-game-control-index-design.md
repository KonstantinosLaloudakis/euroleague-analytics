# Game Control Index (GCI) — Design Spec

## Overview

A composite metric that captures *how* a team wins, not just *that* they won. Built from Win Probability trajectory analysis, the GCI produces per-game sub-metrics, team season profiles, auto-generated storylines, and season superlatives. Delivered as a new frontend page (`game-control.html`) with a narrative-first layout.

## Motivation

The project already answers "who wins?" and "who's the best player?" but not "how do teams win?" The GCI fills this gap with a completely novel metric — no public Euroleague analytics site (or NBA site) publishes a systematic game-control framework. It leverages the project's strongest unique asset: the WP model across 19 seasons of play-by-play data.

## Analytical Framework

### Per-Game Sub-Metrics

All metrics are derived from the WP replay data (`docs/data/{season}/{gamecode}.json`), which contains WP values at every play.

| Metric | Definition | Range |
|--------|-----------|-------|
| **Dominance Score** | Signed area between WP curve and 0.5 line, from home team's perspective. Computed as `mean(WP[i] - 0.5)` across all plays (equivalent to integral normalized by play count). | -0.5 to +0.5 |
| **Control Duration** | % of plays where the eventual winner held WP > 0.6 | 0% to 100% |
| **Drama Index** | Total variation of WP curve: `sum(abs(WP[i+1] - WP[i]))` for consecutive plays | 0 to ~8+ |
| **Comeback Magnitude** | For wins: `1.0 - min(winner_WP)`. For losses: 0 | 0 to 1.0 |
| **Crunch-Time Swing** | Net WP change per team in the final 5 minutes of game clock (Q4 from 5:00 to 0:00, plus overtime if applicable). Computed as `WP_final - WP_at_5min_mark`. | -1.0 to +1.0 |
| **Killer Instinct** | Net WP change during Q4 plays when leading (WP > 0.55 for home, < 0.45 for away). Sum of deltas, not average — captures total close-out pressure. Positive = extended lead. | -0.5 to +0.5 |

### Team Season Aggregates

| Aggregate | Derivation |
|-----------|-----------|
| **GCI Rating** | Weighted composite: Dominance (35%) + Control Duration (25%) + Crunch-Time Swing (20%) + Killer Instinct (20%). Z-normalized to 0-100 scale across the league. |
| **Win Quality Profile** | Histogram of Dominance Scores across wins, using 5 bins: [0-0.1) grind, [0.1-0.2) close, [0.2-0.3) solid, [0.3-0.4) comfortable, [0.4+) blowout. Shows whether a team is a blowout merchant or a grinder. |
| **Loss Profile** | Histogram of Dominance Scores across losses. Close losses vs. blowouts. |
| **Drama Rating** | Season-average Drama Index. |
| **Comeback Rating** | Frequency and average magnitude of comeback wins (wins where WP dropped below 20%). |
| **Home/Away Splits** | GCI components split by venue. |

### Auto-Generated Storylines

Each storyline is assigned to the league-leading team in a specific category:

| Storyline | Criteria |
|-----------|---------|
| **Dominant Force** | Highest GCI Rating |
| **Drama Magnets** | Highest average Drama Index |
| **Comeback Kings** | Most comeback wins from below 20% WP |
| **The Closers** | Highest Killer Instinct |
| **Fortress** | Largest home GCI vs. away GCI gap |

Each storyline includes a short auto-generated description text (1-2 sentences) based on the team's actual numbers.

### Season Superlatives

Three single-game awards:
- **Most Dominant Game** — Highest absolute Dominance Score
- **Most Dramatic Game** — Highest Drama Index
- **Biggest Comeback** — Highest Comeback Magnitude among wins

### Game of the Round

The game with the highest Drama Index in the most recent round is auto-selected as "Game of the Round."

## Data Pipeline

### New Script: `calculate_gci.py`

**Position in pipeline:** Phase 2 (Compute) of `refresh_all.py`, after `calculate_wpa.py`.

**Inputs:**
- `docs/data/2025/{gamecode}.json` — WP replay data per game (already exists)
- `mvp_game_results.json` — Game metadata (teams, scores, rounds, home/away)

**No new data fetching required.** All inputs already exist from the current pipeline.

**Computation steps:**

1. Load all WP replay files for the current season
2. For each game, compute the 6 per-game sub-metrics
3. For each team, aggregate into season profile
4. Compute GCI Rating (weighted composite, z-normalized to 0-100)
5. Assign storyline labels based on league leaders
6. Generate storyline description texts
7. Identify season superlatives and game of the round

**Output: `gci_ratings.json`**

```json
{
  "season": "2025",
  "round": 37,
  "teams": {
    "OLY": {
      "gci": 87.3,
      "dominance_avg": 0.42,
      "control_pct": 0.71,
      "crunch_swing_avg": 0.18,
      "killer_instinct": 0.85,
      "drama_avg": 2.14,
      "comeback_rating": 0.35,
      "comeback_count": 1,
      "home_gci": 91.2,
      "away_gci": 73.4,
      "storyline": "Dominant Force",
      "storyline_text": "Controlled 71% of game time on average. 8 wins with WP never below 60%.",
      "win_quality_hist": [2, 4, 8, 7, 3],
      "loss_quality_hist": [1, 2, 1, 0, 0]
    }
  },
  "games": [
    {
      "gamecode": "123",
      "round": 37,
      "home": "FEN",
      "away": "PAR",
      "home_score": 82,
      "away_score": 79,
      "dominance": -0.12,
      "drama": 4.82,
      "comeback": 0.87,
      "control_duration": 0.38,
      "crunch_home": 0.22,
      "crunch_away": -0.22,
      "killer_home": 0.14,
      "killer_away": -0.08
    }
  ],
  "game_of_round": {
    "gamecode": "123",
    "round": 37,
    "home": "FEN",
    "away": "PAR",
    "home_score": 82,
    "away_score": 79,
    "drama": 4.82,
    "label": "Game of the Round"
  },
  "storylines": [
    {"label": "Dominant Force", "team": "OLY", "text": "Controlled 71% of game time..."},
    {"label": "Drama Magnets", "team": "FEN", "text": "Highest drama index in the league..."},
    {"label": "Comeback Kings", "team": "BAR", "text": "3 wins from below 15% WP..."},
    {"label": "The Closers", "team": "RMA", "text": "Highest killer instinct..."},
    {"label": "Fortress", "team": "PAN", "text": "Home GCI 18 points above away..."}
  ],
  "superlatives": {
    "most_dominant": {"gamecode": "045", "home": "OLY", "away": "BAR", "home_score": 95, "away_score": 68, "dominance": 0.94, "round": 14},
    "most_dramatic": {"gamecode": "123", "home": "FEN", "away": "PAR", "home_score": 82, "away_score": 79, "drama": 4.82, "round": 37},
    "biggest_comeback": {"gamecode": "078", "home": "RMA", "away": "BAR", "home_score": 84, "away_score": 88, "comeback": 0.92, "round": 22}
  }
}
```

### Integration with `export_dashboard_data.py`

- Add GCI fields to each team object in `dashboard.json`: `gci`, `drama_avg`, `comeback_count`, `home_gci`, `away_gci`
- Add new top-level `game_control` key containing: `storylines`, `game_of_round`, `superlatives`, `games` array

### Integration with `refresh_all.py`

- Add `calculate_gci` call in Phase 2, after `calculate_wpa`
- No new CLI flags needed

## Frontend Page: `game-control.html`

### Page Structure (top to bottom)

1. **Header** — Title "Game Control Index", subtitle "How teams win, not just that they win", round indicator
2. **Storyline Hero Cards** — Horizontally scrollable cards, one per storyline. Each card: label, team name, description text, key metric badges. Color-coded borders (teal for Dominant, red for Drama, gold for Comeback, green for Closers).
3. **Game of the Round** — Featured game card with: team scores, mini WP curve (inline SVG), metric tags (Drama, Comeback, Crunch Swing), link to WP Replay page.
4. **Control vs. Drama Scatter** — Plotly.js scatter plot. X-axis: GCI Rating, Y-axis: Drama Index. Quadrant labels: "Dramatic & Dominant", "Quiet & Dominant", "Dramatic & Inconsistent", "Quiet & Inconsistent". Team dots use team colors. Click a dot to scroll to team deep-dive.
5. **GCI Leaderboard** — Sortable table with columns: Rank, Team, GCI, Dominance, Control%, Drama, Crunch, Killer, Comebacks. Click headers to sort. Click row to scroll to team deep-dive.
6. **Team Deep-Dive** — Team selector pills (20 teams). Expands to show:
   - Radar chart (6 sub-metrics) built with inline SVG
   - Win Quality histogram (Plotly bar chart)
   - Game-by-game log with Dominance Score per game (W/L colored)
   - Home vs. Away GCI comparison bar
7. **Season Superlatives** — Three award cards: Most Dominant Game, Most Dramatic Game, Biggest Comeback. Each with score, key metric, round number.

### Technical Implementation

- Standalone HTML file: `docs/game-control.html`
- Dedicated JS file: `docs/game-control.js`
- Data source: `docs/data/current/dashboard.json` (game_control key)
- Charts: Plotly.js for scatter and histograms, inline SVG for radar and mini WP curve
- Follows existing patterns: dark theme, team color constants from shared JS, no build step
- Navigation: add to the nav bar across all 11 existing pages

### About Page

Update `docs/about.html` to include a Game Control Index methodology section explaining the metric definitions, weights, and interpretation.

## Scope Boundaries

**In scope:**
- `calculate_gci.py` — new compute script
- `export_dashboard_data.py` — add GCI data to dashboard.json
- `refresh_all.py` — add GCI to pipeline
- `docs/game-control.html` + `docs/game-control.js` — new frontend page
- `docs/about.html` — add methodology section
- Navigation update across all existing pages
- Current season (2025) only for initial launch

**Out of scope (future work):**
- Historical 19-season GCI analysis and trends
- Per-player GCI contributions
- GCI-based game predictions
- GCI integration into the Team Deep-Dive page (team.html)
