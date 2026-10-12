# Player Career Pages — Design Spec
**Date:** 2026-05-07
**Status:** Approved

## Overview

Add a `player.html` page that gives every player who has ever appeared in Euroleague a dedicated career profile — season-by-season traditional stats across all 19 seasons, a PIR trend chart, and headline current-season stats. This is the core "Basketball Reference for Euroleague" experience: look up anyone, any era.

---

## Data Pipeline

### New script: `fetch_player_career_stats.py`

Calls the `euroleague_api` `PlayerStats` class:

```python
from euroleague_api.player_stats import PlayerStats
ps = PlayerStats()
df = ps.get_player_stats_all_seasons("traditional", statistic_mode="PerGame")
```

Groups by player code, sorts seasons newest-first, and writes `docs/data/current/player_career_stats.json`.

### Output JSON shape

```json
{
  "index": [
    { "code": "P000123", "name": "Nikola Mirotić", "current_team": "BAR", "seasons": 11 }
  ],
  "players": {
    "P000123": {
      "name": "Nikola Mirotić",
      "nationality": "Montenegro",
      "position": "C-F",
      "seasons": [
        {
          "season": "2024-25",
          "season_code": "E2024",
          "team_code": "BAR",
          "team_name": "FC Barcelona",
          "gp": 34,
          "ppg": 19.4, "rpg": 6.2, "apg": 1.8,
          "spg": 0.9,  "bpg": 0.6, "tpg": 1.4,
          "fg_pct": 52.1, "fg3_pct": 38.4, "ft_pct": 82.3,
          "pir": 18.2
        }
      ],
      "career": {
        "gp": 312, "ppg": 17.6, "rpg": 5.8, "apg": 1.6,
        "fg_pct": 51.2, "fg3_pct": 37.1, "ft_pct": 81.0,
        "pir": 16.4,
        "final_fours": 3, "championships": 1
      }
    }
  }
}
```

Seasons are sorted newest-first. Career totals are weighted averages (by GP) for per-game rates, true totals for counting stats (GP). `final_fours` and `championships` are derived from the existing `playoff_results` data in `dashboard.json`, cross-referenced by player code for the seasons they played.

### Integration

- `fetch_player_career_stats.py` runs as part of **Phase 1** (fetch) in `refresh_all.py`, after existing fetch scripts.
- Output file is separate from `dashboard.json` to avoid bloating it — fetched on demand only when a user visits `player.html`.
- Cached: historical seasons don't change, so the script can skip re-fetching seasons already present in the JSON (compare against stored season codes).

---

## Frontend: `player.html`

**URL scheme:** `player.html?code=P000123`

Single page, loads `player_career_stats.json` once on visit, looks up the player by code.

### Sections (top to bottom)

#### 1. Site nav — search bar added (player.html only for v1)
A search input is added to the nav on `player.html`. On input, it fetches the `index` array from `player_career_stats.json` (lazy, cached after first load), filters by name, and shows a dropdown of matches. Clicking a result navigates to `player.html?code=XXX`. Expanding the search to all pages is out of scope for v1.

#### 2. Breadcrumb
`Players › [Position group] › [Player Name]`

#### 3. Hero Card
- **Left:** Avatar circle with player initials, name, nationality + position + birth year, tag chips (current team, `N seasons · YYYY–YYYY`, Final Four count, championship count).
- **Right:** 4-stat grid showing current season: PPG (highlighted gold), RPG, APG, PIR (highlighted green). Labeled "2024–25 season" above the grid.
- Background: dark blue gradient matching existing dashboard aesthetic.

#### 4. PIR Trend Chart
- Bar chart, one bar per season, x-axis = season label, y-axis = PIR.
- Three bar colors: standard (past), peak (career-high season, violet), current (sky blue).
- Peak label shown top-right: "Peak: 21.4 (2022-23)".
- Rendered with inline SVG (no Plotly dependency needed for a simple bar chart — keeps page light).

#### 5. Career Stats Table
Tabbed into four views:

| Tab | Columns |
|-----|---------|
| Scoring | GP · PPG · RPG · APG · SPG · BPG · TPG · PIR |
| Shooting | GP · FG% · 3P% · FT% · PPG |
| Rebounding | GP · RPG · OREB · DREB · BPG |
| All Stats | All columns combined |

- One row per season, newest-first. Current season row has a subtle blue tint.
- Season column is a link (future: links to that season's page).
- **Career totals row** pinned at bottom, always visible regardless of active tab.
- Column headers are sortable (click to sort ascending/descending).

### Discovery / Navigation
Player names become `<a href="player.html?code=XXX">` links in these existing pages:
1. `players.html` — leaderboard rows
2. `team.html` — top contributors section
3. `recap.html` — box score player names

The search bar in the nav is the primary path for finding players from past seasons not visible in those lists.

---

## About Page

Add a "Player Career Pages" section to `about.html` describing the data source (`PlayerStats` API, all seasons), stat definitions (PIR, FG%, etc.), and RAPM availability note (current season only, shown in hero card).

---

## What's Not In Scope

- Player photos (API doesn't expose them reliably)
- RAPM in the career table (only available for current season; shown in hero card instead)
- Eurocup / other competition stats (Euroleague only, matching the rest of the site)
- Player comparison on this page (that's a future feature)
- Per-game game log (too granular for v1)
