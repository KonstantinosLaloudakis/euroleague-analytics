# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Euroleague basketball analytics suite covering 20 seasons (2007–2026). Python backend computes advanced metrics from the Euroleague API, exports JSON, and a vanilla JS frontend (GitHub Pages) renders interactive dashboards.

## Commands

```bash
# Run the full pipeline (fetch data → compute metrics → visualize → export)
python refresh_all.py

# Common flags
python refresh_all.py --no-fetch       # Skip API fetch, recompute from cached data
python refresh_all.py --viz-only       # Only regenerate visualizations + export
python refresh_all.py --skip-wp-train  # Reuse existing WP model (saves ~5 min)
python refresh_all.py --with-animations # Include GIF generation (slow)
python refresh_all.py --commit         # Auto-stage and commit round-suffixed outputs

# Run a single script
.venv/Scripts/python.exe calculate_rapm.py   # Windows
python3 calculate_rapm.py                     # macOS/Linux
```

Tests: `.venv/Scripts/python.exe -m pytest tests/ -q`. No linter is configured. Ad-hoc validation scripts: `inspect_*.py`, `check_*.py`, `debug_*.py`.

## Architecture

### Data Pipeline (refresh_all.py orchestrates all phases)

```
Phase 1: Fetch     → fetch_schedule.py, fetch_mvp_data_v2.py, fetch_pbp.py, fetch_shot_data.py, fetch_lineups.py, parse_mvp_data.py, generate_clutch_data.py
Phase 2: Compute   → train_wp_model, calculate_{adjusted_ratings,mvp_scores,tpm,wir,wpa,elo,rapm}, simulate_monte_carlo
Phase 3: Visualize → visualize_*.py, mvp_oracle.py, oracle_accuracy_tracker.py, export_dashboard_data.py
Phase 4: Animate   → visualize_standings_race.py (optional)
Phase 5: Git       → auto-commit round-suffixed files (optional)
```

### Season

`season_config.py` holds `CURRENT_SEASON` (default 2026, override with env `EUROLEAGUE_SEASON`), plus `ALL_SEASONS`, `COMPLETED_SEASONS`, `season_label()`, `season_code()`. Scripts never hardcode a year (enforced by `tests/test_no_hardcoded_season.py`).

- `fetch_schedule.py` runs first and writes `schedule_{S}.json` / `official_schedule_{S}.xml`; `fetch_pbp.py`, `fetch_shot_data.py`, `fetch_lineups.py` use `incremental_fetch.py` to fetch only played games not yet cached (`--rebuild` deletes a cache to refetch, e.g. a game cached mid-game). `fetch_lineups.py` writes `data_cache/pbp_lineups_{S}.csv` and `games_{S}.csv`.
- `chart_utils.ratings_path(base)` returns the current-round ratings file or None; scripts skip rather than read last season's unsuffixed files (export uses `load_with_fallback(..., strict=True)`).
- Early season: metrics with minimum-games thresholds (MVP ≥5 GP, TPM/WIR ≥10 GP, GCI needs WP replay data) skip gracefully and fill in as rounds accumulate.
- `archive/{year}/` holds that season's round outputs; `docs/data/archive/{year}/dashboard.json` is its final dashboard, shown (with a banner) on series/title-race pages until the new playoffs start.

**Annual season rollover:**
1. Bump `CURRENT_SEASON` in `season_config.py`.
2. Move root `*_R[0-9]*.*` and `oracle_forecast_round_*` files to `archive/{prev}/`.
3. Copy `docs/data/current/dashboard.json` to `docs/data/archive/{prev}/dashboard.json`.
4. Check new teams in `team_aliases.py`, `docs/constants.js`, and the Python color dicts.
5. Switch the `refresh_data.yml` cron back to Wed–Sat (`'0 1 * * 3,4,5,6'`).

### Round Suffixing

Outputs are tagged with the current round (e.g., `adjusted_ratings_R34.json`, `gravity_map_OLY_R34.png`). The suffix is derived from `max(GP)` in `mvp_standings_derived.json` and passed via `EUROLEAGUE_ROUND_SUFFIX` env var.

### Frontend (docs/)

Static site deployed via GitHub Pages from the `docs/` folder.

- Python scripts export to `docs/data/current/dashboard.json` (main data source for all pages)
- Per-game WP replay data lives in `docs/data/{season}/{gamecode}.json`
- Each page is a standalone HTML file with inline `<style>` and a dedicated JS file
- Charts use Plotly.js (loaded via CDN on pages that need it) or inline SVG
- Shared styles in `docs/style.css`, no build step or bundler

**Pages:** index.html (Season Hub), team.html, players.html, h2h.html, recap.html, shots.html, network.html (Playmaking), replay.html, playoffs.html, mvp.html, about.html

### Key Data Files

- `mvp_standings_derived.json` — Current season standings, source of truth for round number
- `mvp_all_game_stats_{season}.json` — Per-player per-game box scores
- `data_cache/games_{season}.csv` — Game results with scores
- `data_cache/pbp_lineups_{season}.csv` — Play-by-play with 5-man lineup arrays
- `docs/data/current/dashboard.json` — Aggregated export consumed by the frontend

### Team Code Conventions

20 teams in the current season. Team codes (3-letter, e.g. OLY, PAN, BAR) are used everywhere. `TEAM_NAMES` and `TEAM_COLORS` live only in `docs/constants.js` (plus season helpers `dashboardSeason`, `seasonLabel`, `playoffsStarted`, `loadPlayoffDashboard`). Schedule team-name variants map to codes in `team_aliases.py` (`team_code()`); add new variants there when a club renames. Some teams have changed codes across seasons (e.g., Panathinaikos: PAN/PAM).

## Key Patterns

- **chart_utils.py** provides shared plotting helpers (logo overlays, diverging bar charts, color themes). Import from here when creating new visualizations.
- **export_dashboard_data.py** is the bridge between Python and the frontend. Any new metric must be added here to appear on the dashboard.
- **euroleague_api** package is the sole data source. It provides game stats, play-by-play, and shot data endpoints.
- **Sparse matrix approach** in calculate_rapm.py: lil_matrix → csr_matrix with +1/-1 player indicators for ridge regression.
- **Two-pass informed prior** in RAPM: Pass 1 (low alpha=100) generates noisy targets, box-score model predicts RAPM, Pass 2 uses predictions as regularization center.
- **Windows development**: The venv Python is at `.venv/Scripts/python.exe`. Use forward slashes and Unix shell syntax (bash on Windows).

## CI/CD

Two GitHub Actions workflows:
- `refresh_data.yml` — Runs Wed–Sat 01:00 UTC: full pipeline + auto-commit
- `wp_replay_update.yml` — Daily 03:00 UTC: fetches all-seasons PBP, preprocesses WP replay data
