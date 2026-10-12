# Historical GCI Trends — Design Spec

## Overview

Extend the Game Control Index with a historical dimension: compute GCI for all 19 Euroleague seasons (2007–2025, 5,026 games), then present league-wide era trends and per-team style evolution on a new frontend page. The page leads with a punchy "how the league evolved" hero, offers an interactive team comparison tool, breaks down eras, and showcases all-time superlatives.

## Motivation

The current GCI page answers "how do teams win *this season*?" but not "how has winning style changed over 19 years?" or "was Real Madrid always dominant?" Historical trends are the natural next step — they leverage the project's unique asset (WP replay data across every Euroleague game since 2007) and create viral-friendly content ("Euroleague drama has increased 43% since 2007").

## Data Landscape

### WP Replay Coverage

| Seasons | Years | Teams/Season | Total Games |
|---------|-------|-------------|-------------|
| 9 | 2007–2015 | 24 | ~2,000 |
| 4 | 2016–2019 | 16–18 | ~1,030 |
| 6 | 2020–2025 | 18–20 | ~1,950 |
| **19** | **2007–2025** | — | **5,026** |

All replay files share the same structure: `{ta, tb, timeline: [{e, s, a, b, w, p, d}, ...]}`.

### Team Continuity

10 "legacy" teams have been present all 19 seasons with consistent team codes:

| Code | Team |
|------|------|
| OLY | Olympiacos |
| BAR | Barcelona |
| MAD | Real Madrid |
| PAN | Panathinaikos |
| TEL | Maccabi Tel Aviv |
| IST | Anadolu Efes |
| ULK | Fenerbahce |
| BAS | Baskonia |
| MIL | EA7 Milano |
| ZAL | Zalgiris |

Additional teams with 3+ seasons (~20 teams) are available for comparison. Teams with <3 seasons appear only in per-season data, not in trend lines.

**No team code aliases are needed.** Every code maps to exactly one franchise. PAM is Valencia Basket (separate from PAN/Panathinaikos). UNK is UNICS Kazan. All verified against the actual data.

### Key Constraint

`mvp_game_results.json` only covers the current season (2025). For historical seasons, game results (teams, scores, winner) are derived directly from WP replay files:
- `ta`/`tb` → home/away team codes
- Last timeline entry `a`/`b` → final scores
- Last timeline entry `w` → winner (>0.5 = home, <0.5 = away)

## Data Pipeline

### New Script: `calculate_gci_historical.py`

**Not part of `refresh_all.py`.** This is a one-time batch script, re-run only when a new season completes.

**Inputs:**
- `docs/data/{season}/{gamecode}.json` — WP replay files for seasons 2007–2024 (completed seasons only)

**Note:** The current season (2025) is excluded from the historical batch. Its GCI data comes from the live `dashboard.json` (computed by `calculate_gci.py` on every refresh). The frontend merges the two at render time.

**Computation steps:**

1. For each season (2007–2024):
   a. Scan all WP replay files in `docs/data/{season}/`
   b. Derive game results from each file (teams from `ta`/`tb`, scores from last timeline entry, winner from final WP)
   c. Compute 6 per-game sub-metrics using the same `compute_game_metrics()` logic as `calculate_gci.py`
   d. Aggregate into per-team season profiles
   e. Compute GCI ratings (z-normalized 0–100 within each season)
   f. Compute league-wide aggregates (avg Drama, avg Dominance spread, comeback count)

2. Compute cross-season data:
   a. Era breakdowns (Expansion 2007–2015, Contraction 2016–2019, Modern 2020–2025)
   b. Historical superlatives (all-time records across all 5,026 games)
   c. Per-team trend arrays (GCI per season for teams with 3+ seasons)

**Reuses core functions** from `calculate_gci.py` via import: `compute_game_metrics()` and the GCI weighting formula. Does NOT duplicate the metric computation logic.

**Output: `gci_historical.json`**

```json
{
  "generated": "2026-04-14",
  "seasons_computed": [2007, 2008, ..., 2024],
  "total_games": 5026,
  "league_trends": {
    "seasons": [2007, 2008, ..., 2025],
    "avg_drama": [2.1, 2.3, ...],
    "avg_dominance_spread": [0.18, 0.17, ...],
    "comeback_count": [3, 5, ...],
    "avg_gci_spread": [28.5, 26.1, ...],
    "game_count": [231, 188, ...]
  },
  "eras": [
    {
      "name": "Expansion Era",
      "years": "2007–2015",
      "seasons": [2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015],
      "avg_drama": 2.4,
      "avg_gci_spread": 27.3,
      "total_comebacks": 18,
      "standout_team": "CSK",
      "standout_reason": "Highest average GCI across the era (82.1)"
    }
  ],
  "team_trends": {
    "OLY": {
      "seasons": [2007, 2008, ..., 2025],
      "gci": [72.1, 68.5, ..., 87.3],
      "drama_avg": [2.1, 2.4, ...],
      "dominance_avg": [0.12, 0.08, ...],
      "killer_instinct": [0.15, 0.11, ...],
      "comeback_count": [1, 0, ...],
      "total_seasons": 19
    }
  },
  "season_leaderboards": {
    "2007": [
      {"team": "CSK", "gci": 88.2, "dominance_avg": 0.18, "drama_avg": 1.9},
      {"team": "OLY", "gci": 72.1, "dominance_avg": 0.12, "drama_avg": 2.1}
    ]
  },
  "superlatives": {
    "most_dominant_season": {
      "team": "CSK",
      "season": 2016,
      "gci": 94.2
    },
    "most_dramatic_game": {
      "gamecode": "123",
      "season": 2019,
      "home": "FEN",
      "away": "PAR",
      "home_score": 82,
      "away_score": 79,
      "drama": 6.82
    },
    "biggest_comeback": {
      "gamecode": "78",
      "season": 2022,
      "home": "RMA",
      "away": "BAR",
      "home_score": 84,
      "away_score": 88,
      "comeback": 0.95
    },
    "most_dominant_game": {
      "gamecode": "45",
      "season": 2014,
      "home": "OLY",
      "away": "BAR",
      "home_score": 95,
      "away_score": 68,
      "dominance": 0.48
    }
  }
}
```

### Frontend Data Loading

The page loads two files and merges them client-side:
- `gci_historical.json` — seasons 2007–2024 (static, generated once)
- `data/current/dashboard.json` → `game_control` key — live 2025 data

The merge appends 2025's team GCI values to `team_trends`, adds 2025 to `league_trends` arrays, and includes 2025 games in superlative comparisons. This way the current season is always up-to-date without re-running the historical batch.

## Frontend Page: `gci-history.html`

### Page Structure

#### Section 1: Hero — "How the Euroleague Evolved"

Three metric cards side by side, each with:
- Metric label (uppercase, small)
- Big number showing the % change from 2007 to 2025
- Sparkline (inline SVG) showing the 19-season trend
- Color-coded: red for Drama, gold for Comebacks, green for Competitiveness

Metrics displayed:
1. **Average Drama Index** — % change from first to last season
2. **Comebacks per Season** — multiplier change (e.g., "2.1×")
3. **Dominance Spread** — % change in gap between top and bottom GCI (negative = more competitive)

Subtitle below: one-sentence summary tying the three trends together.

Subheader: "19 Seasons · 5,026 Games · Every Play Analyzed"

#### Section 2: Team Comparison Tool

**Team selector:** Pill buttons for the 10 legacy teams (shown by default). "Show more" toggle expands to all teams with 3+ seasons. Click to toggle teams on/off (2–5 teams active).

**Chart:** Plotly.js line chart. X-axis: season (2007–2025). Y-axis: selected metric. One colored line per selected team using team colors from `constants.js`. Hover tooltip shows exact value, team name, season label.

**Metric dropdown:** Switch Y-axis between GCI Rating, Drama Index, Dominance Score, Killer Instinct, Comeback Count. Default: GCI Rating.

Teams with gaps (seasons they weren't in the league) show broken lines — no interpolation across missing seasons.

#### Section 3: Era Breakdown

Three cards in a horizontal row:

| Card | Era | Seasons | Key Stats |
|------|-----|---------|-----------|
| 1 | Expansion Era | 2007–2015 (24 teams) | Avg drama, GCI spread, total comebacks, standout team |
| 2 | Contraction Era | 2016–2019 (16 teams) | Same stats | 
| 3 | Modern Era | 2020–2025 (18–20 teams) | Same stats |

Each card has:
- Era name and year range
- Number of teams and total games
- 3 key stats with values
- Standout team badge with one-line reason
- Subtle color accent per era

#### Section 4: Historical Superlatives

Four award cards (2×2 grid):
- **Most Dominant Season Ever** — Team, season, GCI rating
- **Most Dramatic Game Ever** — Teams, score, season/round, Drama Index
- **Biggest Comeback Ever** — Teams, score, season/round, Comeback Magnitude
- **Most Dominant Game Ever** — Teams, score, season/round, Dominance Score

Each card shows the key metric value prominently, with team names, final score, and season. Game-level superlatives link to the WP Replay page for that game.

### Technical Implementation

- Standalone HTML: `docs/gci-history.html`
- Dedicated JS: `docs/gci-history.js`
- Data: `docs/gci_historical.json` + `docs/data/current/dashboard.json`
- Charts: Plotly.js for the team comparison line chart
- Sparklines: Inline SVG (same approach as current GCI page)
- Team colors: Import from `constants.js`
- Dark theme, responsive, follows existing page patterns
- No build step

### Navigation

Add "GCI History" link to the nav bar across all existing pages, positioned after "Game Control" and before "About".

### About Page

Add a "Historical GCI Trends" subsection to the existing Game Control Index methodology section in `docs/about.html`. Explain: same metrics as current-season GCI, computed independently per season with within-season z-normalization, era definitions, and the 3-season minimum for trend lines.

## Scope Boundaries

**In scope:**
- `calculate_gci_historical.py` — new batch compute script
- `docs/gci-history.html` + `docs/gci-history.js` — new frontend page
- `docs/gci_historical.json` — output data file (committed to repo)
- `docs/about.html` — add historical methodology note
- Navigation update across all existing pages

**Out of scope:**
- Changes to `refresh_all.py` (historical script is run manually)
- Changes to `export_dashboard_data.py` (frontend reads `gci_historical.json` directly)
- Changes to the current-season GCI page (`game-control.html`)
- Per-player historical GCI
- Season-over-season delta analysis ("team X improved the most")
