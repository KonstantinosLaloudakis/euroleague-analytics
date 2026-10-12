# All-Time Records Page — Design Spec
**Date:** 2026-05-07
**Status:** Approved

## Overview

Add a `records.html` page showing all-time Euroleague records across 19 seasons (2007–08 to 2025–26). Two columns per stat category: Career Leaders (accumulated totals for counting stats) on the left, Best Single-Season performances (per-game averages) on the right. Data comes entirely from the existing `player_career_stats.json` — no new Python work required.

---

## Architecture

### New files
- `docs/records.html` — page shell, nav, inline CSS
- `docs/records.js` — all computation and rendering logic

### Data source
`docs/data/current/player_career_stats.json` (already exported by `fetch_player_career_stats.py`). Loaded once on page visit, all ranking computation happens client-side.

### No backend changes
The existing JSON has per-player, per-season stats. Career totals and single-season rankings are derived entirely in JavaScript.

### Navigation
"All-Time Records" nav link added to all 15 HTML pages (the existing 14 + `records.html` itself). Positioned between "Game Replay" and "Playoffs" in the nav. `records.html` marks it `active`.

---

## Data Computation

### Career totals (left column)
Counting stats are **accumulated totals**, not averages:

```
career_points  = Σ (season.ppg × season.gp)  for all seasons of a player
career_assists = Σ (season.apg × season.gp)
career_rebounds = Σ (season.rpg × season.gp)
career_steals  = Σ (season.spg × season.gp)
```

PIR and shooting percentages use the existing **GP-weighted career average** already stored in `player.career.pir`, `player.career.fg2_pct`, etc.

### Single-season records (right column)
Scan every `season` entry across all players, find the top N by the relevant per-game stat. Each record entry stores: `player_name`, `player_code`, `season` (label), `team_code`, `gp`, `stat_value`.

### Minimum thresholds
- **Career leaders**: minimum 100 GP (excludes very short careers). User-adjustable via dropdown (50 / 100 / 200 / No minimum).
- **Single-season records**: minimum 15 GP in that specific season (excludes anomalies).

### Computation timing
All rankings are computed once on page load (after JSON fetch) and cached in module-level arrays. Tab switches are instant re-renders from cached data.

---

## Frontend: `records.html` + `records.js`

### Page structure

```
<nav> — site nav with "All-Time Records" active
<header> — "🏆 All-Time Records" + subtitle (19 seasons · 1,148 players)
<div.cat-tabs> — 5 category tab buttons
<div.filter-row> — Min GP dropdown + legend note
<div.records-grid> — two-column grid
  <div.record-card> — Career Leaders table
  <div.record-card> — Best Single Season table
```

### The 5 tabs

| Tab | Career Leaders (left) | Single-Season Records (right) |
|-----|-----------------------|-------------------------------|
| Scoring | Total career points | Best season PPG |
| Playmaking | Total career assists | Best season APG |
| Rebounding | Total career rebounds | Best season RPG |
| Defense | Total career steals | Best season SPG |
| Efficiency | Career avg PIR (weighted) | Best season PIR |

### Table columns

**Career Leaders table:**
`# | Player (links to career page) | Seasons | GP | Total / Avg`

**Single-Season table:**
`# | Player · Season (links to career page) | Team | GP | Stat`

### Display
- Top 10 shown by default
- "Show top 25 ↓" expander below each table — rows 11–25 are rendered into the DOM but hidden (`display:none`); clicking the expander toggles their visibility in-place. No lazy fetch.
- Rank badges: gold (#1), silver (#2), bronze (#3), plain text for 4–25
- Career totals highlighted gold, single-season values highlighted green (matching career page colour scheme)
- Player names are `<a href="player.html?code=XXX">` links

### Responsive
On mobile (< 640px), the two-column grid stacks to one column (career first, single-season below).

---

## Navigation

Add to every HTML file in `docs/`:
```html
<a href="records.html" class="nav-link">All-Time Records</a>
```
Positioned after `replay.html` and before `playoffs.html`.

In `records.html` itself, that link gets `class="nav-link active"`.

---

## About Page

Add a brief "All-Time Records" entry to `docs/about.html` noting: data from `player_career_stats.json`, career totals computed as `Σ(per_game × GP)`, minimum GP thresholds, and that all 19 seasons are included.

---

## What's Not In Scope

- Team all-time records (player records only)
- Era filters (e.g., "post-2015 only")
- Eurocup or other competition records
- Exporting/sharing a specific record
- Animated reveals or trophy icons per record
