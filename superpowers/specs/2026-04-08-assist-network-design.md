# Assist/Playmaking Network — Design Spec

## Overview

A new standalone page (`network.html`) that visualizes assist relationships within each Euroleague team using an interactive chord diagram. Accompanied by league-wide leaderboard tables for top assist combos and top individual playmakers.

**Data source:** 11,036 assist events in `data_cache/pbp_2025.csv`, linked to made shots via consecutive `NUMBEROFPLAY` entries (83.5% linkable).

## Decisions

| Question | Decision |
|----------|----------|
| Where does it live? | New standalone page (`network.html` + `network.js`) |
| Granularity | Team-scoped network + league-wide leader tables |
| Visualization | Chord diagram (pure inline SVG, no libraries) |
| Tooltip detail | Rich: count, 2PT/3PT split, per-game rate, % of passer's assists, % of scorer's baskets |
| League tables | Two tables: top assist combos + top individual playmakers |

## Page Structure

### 1. Team Selector

20 team chips in a grid (same pattern as `team.html`). Default: first team alphabetically. URL param `?team=OLY` for deep linking. Clicking a chip re-renders the chord diagram for that team.

### 2. Chord Diagram (Centerpiece)

- **Technology:** Pure inline SVG, built in JS (same approach as radar charts in `mvp.js` and paint court in `shots.js`)
- **Size:** ~500px diameter, centered
- **Players shown:** Top 8 per team by assist involvement (assists given + assists received). Players outside the top 8 are excluded entirely (no "Others" bucket — bench players with minimal assists add visual noise).
- **Arc segments:** Each player gets an arc on the outer ring, sized proportionally to their total assist involvement (given + received)
- **Ribbons:** Connect passer arc to scorer arc. Width proportional to assist count for that pair. Color derived from passer's segment.
- **Hover — player arc:** Highlight only that player's ribbons; fade all others to ~10% opacity. Show player name and total stats in a label.
- **Hover — ribbon:** Show rich tooltip with:
  - Assist count
  - Shot type split (2PT / 3PT)
  - Per-game frequency
  - % of passer's total assists
  - % of scorer's assisted baskets
- **Click — player arc:** Pin the highlight and populate the player detail card below.
- **Color scheme:** Each player's segment gets a unique shade derived from the team color using HSL rotation (e.g., base team hue ± offsets for each player). This keeps the diagram visually cohesive while distinguishing players.

### 3. Player Detail Card

Appears below the chord diagram when a player arc is clicked. Contains:

- Player name + team badge
- **Assists given:** Total, per game, unique teammates fed
- **Top 5 targets:** Who they feed most (name, count, shot type split)
- **Assists received:** Total assisted baskets
- **Top 5 feeders:** Who feeds them most (name, count)

### 4. League-Wide Tables

Two tables side by side below the diagram (stack vertically on mobile).

**Table A — Top 20 Assist Combos:**

| # | Passer | Scorer | Team | AST | 2PT | 3PT | /Game |
|---|--------|--------|------|-----|-----|-----|-------|

Sorted by total assists descending. Clicking a row navigates to that team's chord diagram with the passer highlighted.

**Table B — Top 20 Playmakers:**

| # | Player | Team | AST | /Game | Teammates Fed | Top Target |
|---|--------|------|-----|-------|---------------|------------|

Sorted by total assists descending.

## Backend: `build_assist_network()`

New function in `export_dashboard_data.py`.

### Algorithm

1. Load `data_cache/pbp_2025.csv`
2. Sort by `Gamecode`, `NUMBEROFPLAY`
3. For each row where `PLAYTYPE == 'AS'`:
   - Look at the previous row (same `Gamecode`, `NUMBEROFPLAY - 1`)
   - If previous row is `2FGM` or `3FGM`: link assist
     - Passer: current row's `PLAYER_ID`, `PLAYER`, `CODETEAM`
     - Scorer: previous row's `PLAYER_ID`, `PLAYER`, `CODETEAM`
     - Shot type: previous row's `PLAYTYPE`
   - Skip if previous row isn't a made field goal (unlinked assist)
4. Aggregate edges: group by (passer_id, scorer_id) → count, fg2_count, fg3_count
5. Aggregate per-player: total assists given, total assists received, games played
6. Build team-level structures: for each team, collect players + edges
7. Build league-wide tables: top 20 combos, top 20 playmakers
8. Compute per-game rates using each player's GP from `mvp_all_game_stats_2025.json`

### Output: `docs/data/current/assist_network.json`

```json
{
  "teams": {
    "OLY": {
      "players": [
        {
          "id": "P009126",
          "name": "SLOUKAS, KOSTAS",
          "ast_given": 142,
          "ast_received": 65,
          "gp": 34,
          "ast_per_game": 4.2,
          "unique_targets": 12
        }
      ],
      "edges": [
        {
          "from": "P009126",
          "to": "P005432",
          "count": 42,
          "fg2": 28,
          "fg3": 14
        }
      ]
    }
  },
  "top_combos": [
    {
      "passer": "SLOUKAS, KOSTAS",
      "passer_id": "P009126",
      "scorer": "VEZENKOV, SASHA",
      "scorer_id": "P005432",
      "team": "OLY",
      "count": 42,
      "fg2": 28,
      "fg3": 14,
      "per_game": 1.2
    }
  ],
  "top_playmakers": [
    {
      "player": "SLOUKAS, KOSTAS",
      "player_id": "P009126",
      "team": "OLY",
      "ast": 142,
      "per_game": 4.2,
      "unique_targets": 12,
      "top_target": "VEZENKOV, SASHA",
      "top_target_count": 42
    }
  ]
}
```

## Frontend: `network.html` + `network.js`

### HTML Structure

- Standard page shell (nav, header, footer) matching existing pages
- `<script src="constants.js">` before `<script src="network.js">`
- Team chip selector grid
- SVG container for chord diagram (id: `chord-svg`)
- Player detail card (id: `player-detail`, hidden by default)
- Two table containers side by side

### JS Architecture (`network.js`)

- `fetchJSON('data/current/assist_network.json')` on load
- `selectTeam(code)` — filters data, calls `renderChord()`
- `renderChord(teamData)` — builds the SVG chord diagram:
  - Compute arc angles per player (proportional to involvement)
  - Compute ribbon paths (quadratic bezier curves between arc midpoints)
  - Attach hover/click event listeners
- `highlightPlayer(playerId)` — fades non-connected ribbons, shows detail card
- `showTooltip(edge, pos)` — rich tooltip on ribbon hover
- `renderCombosTable(combos)` — league-wide top 20 combos
- `renderPlaymakersTable(playmakers)` — league-wide top 20 individuals
- URL param handling: `?team=XXX` on load, update on chip click

### SVG Chord Rendering

The chord diagram is built from scratch in SVG:

1. **Outer arcs:** `<path>` elements using SVG arc commands, one per player. Gap of 2-3 degrees between segments.
2. **Ribbons:** `<path>` elements using quadratic bezier curves. Start point on passer's arc, end point on scorer's arc, control point near center. Width at endpoints proportional to assist count relative to that player's segment.
3. **Labels:** `<text>` elements positioned outside each arc with player's formatted name.
4. **Interactions:** CSS transitions for opacity changes on hover. Event delegation on the SVG container.

### Styling

- Inline `<style>` in `network.html` for page-specific styles (same pattern as other pages)
- Dark theme matching existing pages
- Chord diagram: transparent background, team-colored segments
- Tables: reuse existing table styles from `style.css`
- Mobile: chord diagram scales down, tables stack vertically at 768px

### Nav Integration

Add "Playmaking" link to nav bar in all HTML pages, positioned after "Shot Lab".

## File Changes Summary

| File | Change |
|------|--------|
| `docs/network.html` | New file — page shell, styles, structure |
| `docs/network.js` | New file — data loading, chord rendering, tables |
| `export_dashboard_data.py` | Add `build_assist_network()` function + export call |
| `docs/*.html` (all 10 pages) | Add "Playmaking" nav link |
| `CLAUDE.md` | Update pages list |

## Not in Scope

- Player-scoped view (click player → see their full network across all opponents) — future addition
- Team comparison view (compare two teams' assist networks side by side)
- Historical/multi-season assist data
- Assist location data (where on the court the assist happened)
