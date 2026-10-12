# Season 2026-27 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Point the whole analytics pipeline, CI and frontend at the 2026-27 Euroleague season through one season setting, while preserving 2025-26 as a completed, archived season.

**Architecture:** A new `season_config.py` becomes the single source of truth (`CURRENT_SEASON = 2026`, overridable with `EUROLEAGUE_SEASON`). Every pipeline script imports it instead of hardcoding `2025`. Current-season fetches become incremental per game (only played games not yet cached, throttled, with 429 backoff), and CI persists those caches with `actions/cache`. `export_dashboard_data.py` writes `season` / `season_label` into `dashboard.json`, and the frontend reads the season from there instead of hardcoding it.

**Tech Stack:** Python 3.11, pandas, `euroleague_api` 0.1.0, pytest (already in `.venv`), vanilla JS + Plotly (GitHub Pages from `docs/`), GitHub Actions.

**Spec:** No separate spec doc. The requirements come from the 2026-10-12 audit conversation and are restated here:
1. The pipeline must process 2026-27 (API has ≥79 games played as of 2026-10-12).
2. The year must live in one place.
3. CI "Refresh Analytics Data" must stop failing with HTTP 429. It has failed daily since 2026-09-22 because it refetches whole seasons every run.
4. The new team Beşiktaş (`BES`, API name "Besiktas Istanbul") needs names/colors. Monaco (`MCO`) is no longer in the league.
5. 2025-26 stays visible as history (records, GCI history, replays, championship finals, last playoffs).

## Global Constraints

- Python scripts run from repo root. Locally: `.venv/Scripts/python.exe <script>`; in CI: `python <script>`.
- Tests: `.venv/Scripts/python.exe -m pytest tests/ -q`. Tests live in `tests/`, insert the repo root on `sys.path` like `tests/test_gci_historical.py` does.
- The season comes only from `season_config`. No new literal `2025`/`2026` in any pipeline script except: comments describing history, the `train_wp_model.py` validation split (Task 7), and the `2026` default inside `season_config.py`.
- Keep existing output file *naming patterns* (`mvp_all_game_stats_{season}.json`, `shot_data_{s}_{s}.csv`, `pbp_{s}.csv`, `official_schedule_{s}.xml`, `mvp_rankings_{s}{suffix}.json`, `data_cache/pbp_lineups_{s}.csv`, `data_cache/games_{s}.csv`). Only the year becomes a variable.
- Commit messages: conventional style used in repo (`feat:`, `fix:`, `chore:`), ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never push. The user pushes.
- Do not touch the git stash `pre-pull local edits (...)`.
- Per user preference: any user-facing feature change must also update `docs/about.html` (Task 11 owns this).

## Review Focus

1. **Stale 2025 artifacts read as 2026 data.** Root-level `*_R{n}.*` and `oracle_forecast_round_*.json` files from 2025 would be picked up by `find_latest_oracle_forecast()` (export) and the `os.listdir('.')` scan in `oracle_accuracy_tracker.py`, so 2026 accuracy gets computed against 2025 predictions. *Expected:* after Task 2, no root file matches those patterns before the first 2026 run. Pinned by `tests/test_season_archive.py`.
2. **Championship-finals history treating an in-progress season as finished.** `export_dashboard_data.py` takes the highest gamecode in `docs/data/{season}/` as "the final". For 2026 that's a regular-season game. *Expected:* only `COMPLETED_SEASONS` are scanned. Pinned in Task 9.
3. **GCI history mislabeling the live season.** `docs/gci-history.js` `merge2025()` pushes the current dashboard's data as season `2025`. *Expected:* 2025 comes from `gci_historical.json` (regenerated over completed seasons) and the live season is merged under `dashboard.season`. Pinned in Task 11 browser check + Task 7 regeneration.
4. **Throttled/empty API responses mistaken for "no data".** `euroleague_api` logs 429s as "Didn't find gamecode" and returns an empty frame. *Expected:* a played game that returns empty is retried with backoff, and any game still failing is reported and left for the next run. Pinned by `tests/test_incremental_fetch.py`.
5. **Lineup column format change.** `euroleague_api` 0.1.0 returns `Lineup_A`/`Lineup_B` with `IsHomeTeam=None`, but RAPM/lineups expect `Lineup_{TEAMCODE}`. *Expected:* columns renamed by matching lineup player names to `CODETEAM`. Pinned by `tests/test_fetch_lineups.py`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `season_config.py` | Create | `FIRST_SEASON`, `CURRENT_SEASON`, `ALL_SEASONS`, `COMPLETED_SEASONS`, `season_label()`, `season_code()` |
| `incremental_fetch.py` | Create | `played_gamecodes()`, `fetch_missing_games()`: per-game cache fill with throttle + backoff |
| `fetch_lineups.py` | Create | Incremental `data_cache/pbp_lineups_{S}.csv` + `data_cache/games_{S}.csv`; `to_team_lineup_columns()` adapter |
| `generate_clutch_data.py` | Create (replaces `generate_clutch_data_2025.py`) | Clutch stats for current season from local PBP → `clutch_stats_{S}_{S}.json` |
| `archive/2025/` | Create | 2025-26 round-suffixed outputs + oracle forecasts (moved, not deleted) |
| `docs/data/archive/2025/dashboard.json` | Create | Frozen final 2025-26 dashboard |
| `tests/test_season_config.py`, `tests/test_incremental_fetch.py`, `tests/test_fetch_lineups.py`, `tests/test_season_archive.py`, `tests/test_no_hardcoded_season.py` | Create | Tests |
| ~30 pipeline scripts, `refresh_all.py`, `clutchStats.py`, `calculate_gci_historical.py` | Modify | Use `season_config` |
| `docs/constants.js`, `docs/*.js`, several `docs/*.html` | Modify | BES, season from dashboard, archive fallback |
| `.github/workflows/refresh_data.yml` | Modify | Wed–Sat cron, `actions/cache` for fetch caches |
| `CLAUDE.md` | Modify | Document season config + new steps; fix stale team-mapping note |

---

### Task 1: `season_config.py`

**Files:**
- Create: `season_config.py`
- Test: `tests/test_season_config.py`

**Interfaces:**
- Produces: `FIRST_SEASON: int = 2007`, `CURRENT_SEASON: int`, `ALL_SEASONS: list[int]` (2007..CURRENT inclusive), `COMPLETED_SEASONS: list[int]` (2007..CURRENT-1), `season_label(season: int | None = None) -> str` (`2026 → "2026-27"`), `season_code(season: int | None = None) -> str` (`2026 → "E2026"`).

- [ ] **Step 1: Write the failing test** `tests/test_season_config.py`

```python
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import season_config


def test_defaults_to_2026(monkeypatch):
    monkeypatch.delenv('EUROLEAGUE_SEASON', raising=False)
    cfg = importlib.reload(season_config)
    assert cfg.CURRENT_SEASON == 2026
    assert cfg.ALL_SEASONS[0] == 2007 and cfg.ALL_SEASONS[-1] == 2026
    assert cfg.COMPLETED_SEASONS[-1] == 2025
    assert len(cfg.ALL_SEASONS) == 20


def test_env_override(monkeypatch):
    monkeypatch.setenv('EUROLEAGUE_SEASON', '2027')
    cfg = importlib.reload(season_config)
    assert cfg.CURRENT_SEASON == 2027
    assert cfg.COMPLETED_SEASONS[-1] == 2026
    monkeypatch.delenv('EUROLEAGUE_SEASON')
    importlib.reload(season_config)


def test_labels():
    assert season_config.season_label(2026) == '2026-27'
    assert season_config.season_label(2009) == '2009-10'
    assert season_config.season_label(2099) == '2099-00'
    assert season_config.season_code(2026) == 'E2026'
    assert season_config.season_label() == season_config.season_label(season_config.CURRENT_SEASON)
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: season_config`)

Run: `.venv/Scripts/python.exe -m pytest tests/test_season_config.py -q`

- [ ] **Step 3: Implement** `season_config.py`

```python
"""Single source of truth for which Euroleague season the pipeline processes.

Bump CURRENT_SEASON each autumn when the new season tips off, or set the
EUROLEAGUE_SEASON env var for a one-off run against another season.
Seasons are identified by their start year (2026 = 2026-27).
"""
import os

FIRST_SEASON = 2007
CURRENT_SEASON = int(os.environ.get('EUROLEAGUE_SEASON', '2026'))

ALL_SEASONS = list(range(FIRST_SEASON, CURRENT_SEASON + 1))
COMPLETED_SEASONS = list(range(FIRST_SEASON, CURRENT_SEASON))


def season_label(season=None):
    """2026 -> '2026-27'"""
    s = CURRENT_SEASON if season is None else season
    return f"{s}-{str(s + 1)[-2:]}"


def season_code(season=None):
    """2026 -> 'E2026' (API season code)"""
    s = CURRENT_SEASON if season is None else season
    return f"E{s}"
```

- [ ] **Step 4: Run, expect PASS** (3 passed)
- [ ] **Step 5: Commit** `feat: add season_config as single source of truth for current season`

---

### Task 2: Archive 2025-26 outputs

Move 2025 season artifacts out of the repo root so 2026 runs can't read them, and freeze the final 2025-26 dashboard.

**Files:**
- Move: every root file matching `*_R[0-9]*.json`, `*_R[0-9]*.png`, `oracle_forecast_round_*.json`, `oracle_forecast_round_*.png` → `archive/2025/` (use `git mv` for tracked files, plain `mv` for untracked)
- Create: `docs/data/archive/2025/dashboard.json` (copy of current `docs/data/current/dashboard.json`, which is the final 2025-26 state, round 38 + playoffs)
- Test: `tests/test_season_archive.py`

**Interfaces:**
- Produces: `docs/data/archive/2025/dashboard.json` (consumed by Task 11 frontend fallback).

- [ ] **Step 1: Write the failing test** `tests/test_season_archive.py`

```python
import glob
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _root_glob(pattern):
    return glob.glob(os.path.join(ROOT, pattern))


def test_no_stale_round_files_in_root():
    # Round-suffixed outputs at root must belong to the current season only.
    # Right after archiving there are none; the 2026 pipeline recreates them.
    import season_config
    marker = os.path.join(ROOT, 'archive', str(season_config.CURRENT_SEASON - 1))
    assert os.path.isdir(marker), 'previous season archive folder missing'
    for f in _root_glob('oracle_forecast_round_*.json'):
        # any forecast present must be newer than the archive move
        assert os.path.getmtime(f) > os.path.getmtime(marker), f'stale forecast {f}'


def test_final_2025_dashboard_archived():
    path = os.path.join(ROOT, 'docs', 'data', 'archive', '2025', 'dashboard.json')
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
    assert d['round'] == 38
    assert d.get('series'), 'archived dashboard should contain 2025-26 playoff series'
```

(`sys.path` insert as in Task 1 test so `import season_config` works.)

- [ ] **Step 2: Run, expect FAIL** (archive folder missing)
- [ ] **Step 3: Move files**

```bash
mkdir -p archive/2025 docs/data/archive/2025
cp docs/data/current/dashboard.json docs/data/archive/2025/dashboard.json
for f in *_R[0-9]*.json *_R[0-9]*.png oracle_forecast_round_*.json oracle_forecast_round_*.png; do
  [ -e "$f" ] || continue
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then git mv "$f" archive/2025/; else mv "$f" archive/2025/; fi
done
ls *_R[0-9]* oracle_forecast_round_* 2>/dev/null | wc -l   # expect 0
```

Before moving, run `grep -rlE "_R[0-9]+\.(png|json)|oracle_forecast_round" docs/ --include=*.html --include=*.js`. Expected: nothing (verified 2026-10-12). If something appears, stop and report.

- [ ] **Step 4: Run test, expect PASS**
- [ ] **Step 5: Commit** `chore: archive 2025-26 round outputs and final dashboard`

---

### Task 3: Incremental per-game fetching (PBP + shots)

**Files:**
- Create: `incremental_fetch.py`
- Modify: `fetch_pbp.py` (whole file), `fetch_shot_data.py` (whole fetch function + argparse default)
- Test: `tests/test_incremental_fetch.py`

**Interfaces:**
- Consumes: `season_config.CURRENT_SEASON`; `schedule_{S}.json` written by `fetch_schedule.py` (Task 5). Rows have `gamecode` like `"E2026_7"` and `played` as string `"true"`/`"false"`.
- Produces:
  - `played_gamecodes(schedule_path: str) -> list[int]`
  - `fetch_missing_games(cache_path: str, gamecodes: list[int], fetch_one: Callable[[int], pd.DataFrame], gamecode_col: str = 'Gamecode', delay: float = 0.5, max_retries: int = 4, sleep: Callable = time.sleep) -> tuple[pd.DataFrame, list[int]]` returns (full cached frame, gamecodes that still failed).

- [ ] **Step 1: Write failing tests** `tests/test_incremental_fetch.py`

```python
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from incremental_fetch import played_gamecodes, fetch_missing_games


def test_played_gamecodes(tmp_path):
    p = tmp_path / 'schedule.json'
    p.write_text(json.dumps([
        {'gamecode': 'E2026_3', 'played': 'true'},
        {'gamecode': 'E2026_1', 'played': 'true'},
        {'gamecode': 'E2026_2', 'played': 'false'},
    ]))
    assert played_gamecodes(str(p)) == [1, 3]


def test_only_missing_games_fetched(tmp_path):
    cache = tmp_path / 'c.csv'
    pd.DataFrame({'Gamecode': [1, 1], 'x': [0, 0]}).to_csv(cache, index=False)
    calls = []

    def fetch_one(gc):
        calls.append(gc)
        return pd.DataFrame({'Gamecode': [gc], 'x': [gc]})

    df, failed = fetch_missing_games(str(cache), [1, 2, 3], fetch_one, sleep=lambda s: None)
    assert calls == [2, 3]
    assert failed == []
    assert sorted(df['Gamecode'].unique()) == [1, 2, 3]
    assert sorted(pd.read_csv(cache)['Gamecode'].unique()) == [1, 2, 3]


def test_empty_response_is_retried_then_reported(tmp_path):
    attempts = {'n': 0}

    def flaky(gc):
        attempts['n'] += 1
        if gc == 2:
            return pd.DataFrame()          # what euroleague_api returns on 429
        return pd.DataFrame({'Gamecode': [gc]})

    df, failed = fetch_missing_games(str(tmp_path / 'c.csv'), [1, 2], flaky,
                                     max_retries=3, sleep=lambda s: None)
    assert failed == [2]
    assert attempts['n'] == 1 + 3
    assert list(df['Gamecode']) == [1]


def test_exception_then_success(tmp_path):
    state = {'n': 0}

    def fetch_one(gc):
        state['n'] += 1
        if state['n'] == 1:
            raise RuntimeError('429')
        return pd.DataFrame({'Gamecode': [gc]})

    df, failed = fetch_missing_games(str(tmp_path / 'c.csv'), [5], fetch_one, sleep=lambda s: None)
    assert failed == [] and list(df['Gamecode']) == [5]


def test_nothing_missing_no_write(tmp_path):
    df, failed = fetch_missing_games(str(tmp_path / 'none.csv'), [], lambda gc: None, sleep=lambda s: None)
    assert df.empty and failed == [] and not (tmp_path / 'none.csv').exists()
```

- [ ] **Step 2: Run, expect FAIL** (module missing)
- [ ] **Step 3: Implement** `incremental_fetch.py`

```python
"""Per-game incremental fetching for the current season.

Re-downloading a whole season every night got CI throttled (HTTP 429), so
fetchers only request played games that are not cached yet, pause between
calls, and back off when the API returns nothing for a game that was played
(euroleague_api turns 429s into empty frames).
"""
import json
import os
import time

import pandas as pd


def played_gamecodes(schedule_path):
    """Gamecodes (int) of played games from a schedule_{season}.json file."""
    with open(schedule_path, encoding='utf-8') as f:
        rows = json.load(f)
    codes = {int(str(r['gamecode']).split('_')[-1])
             for r in rows if str(r.get('played', '')).lower() == 'true'}
    return sorted(codes)


def fetch_missing_games(cache_path, gamecodes, fetch_one, gamecode_col='Gamecode',
                        delay=0.5, max_retries=4, sleep=time.sleep):
    """Fetch games in `gamecodes` that aren't in the CSV at `cache_path`.

    Returns (full DataFrame, list of gamecodes that still failed).
    """
    existing = pd.DataFrame()
    if os.path.exists(cache_path):
        existing = pd.read_csv(cache_path, low_memory=False)
    have = set()
    if not existing.empty and gamecode_col in existing.columns:
        have = set(existing[gamecode_col].dropna().astype(int))

    missing = [gc for gc in gamecodes if gc not in have]
    if missing:
        print(f"  {len(have)} games cached, fetching {len(missing)} new: {missing[:10]}{'...' if len(missing) > 10 else ''}")

    new_frames, failed = [], []
    for gc in missing:
        df = None
        for attempt in range(1 + max_retries):
            try:
                df = fetch_one(gc)
            except Exception as e:
                print(f"    game {gc}: {type(e).__name__}: {e}")
                df = None
            if df is not None and not df.empty:
                break
            if attempt < max_retries:
                sleep(4 * 2 ** attempt)   # 4, 8, 16, 32s
        if df is None or df.empty:
            failed.append(gc)
            continue
        if gamecode_col not in df.columns:
            df[gamecode_col] = gc
        new_frames.append(df)
        sleep(delay)

    if new_frames:
        existing = pd.concat([existing, *new_frames], ignore_index=True)
        existing.to_csv(cache_path, index=False)
    if failed:
        print(f"  ⚠️  {len(failed)} games failed, will retry next run: {failed}")
    return existing, failed
```

Note the retry count in the test: `max_retries=3` → 1 initial + 3 retries = 4 calls.

- [ ] **Step 4: Run, expect PASS** (5 passed)
- [ ] **Step 5: Rewrite `fetch_pbp.py`**

```python
import os
import sys

from euroleague_api import play_by_play_data

from incremental_fetch import fetch_missing_games, played_gamecodes
from season_config import CURRENT_SEASON


def fetch_and_cache_pbp(season=CURRENT_SEASON):
    file_path = f'pbp_{season}.csv'
    if '--rebuild' in sys.argv and os.path.exists(file_path):
        os.remove(file_path)
    pbp = play_by_play_data.PlayByPlay()
    gamecodes = played_gamecodes(f'schedule_{season}.json')
    print(f"Play-by-play {season}: {len(gamecodes)} played games in schedule")
    df, failed = fetch_missing_games(
        file_path, gamecodes, lambda gc: pbp.get_game_play_by_play_data(season, gc))
    print(f"{file_path}: {len(df)} events, {df['Gamecode'].nunique() if not df.empty else 0} games")
    return df, failed


if __name__ == '__main__':
    df, failed = fetch_and_cache_pbp()
    sys.exit(1 if df.empty else 0)
```

`--force` (still passed by `refresh_all.py`) is now a harmless no-op. `--rebuild` is the escape hatch.

- [ ] **Step 6: Rewrite the fetch function in `fetch_shot_data.py`** using the same pattern: `season=CURRENT_SEASON` default, argparse `--season` default `CURRENT_SEASON`, fetch with `shots.get_game_shot_data(season, gc)` (`ShotData`), cache at `data/shot_data_{season}_{season}.csv`, then `shutil.copyfile` to root `shot_data_{season}_{season}.csv` (both paths are read downstream). Exit 1 only if the resulting frame is empty. Read the current file first and keep its import of `ShotData` and any column clean-up it does.
- [ ] **Step 7: Smoke test against the live API** (needs `schedule_2026.json`; if Task 5 isn't done yet, run `.venv/Scripts/python.exe fetch_schedule.py --season 2026 --force` first, it already accepts `--season`):

```bash
.venv/Scripts/python.exe fetch_pbp.py && .venv/Scripts/python.exe fetch_shot_data.py
.venv/Scripts/python.exe fetch_pbp.py   # second run: expect "0 new"/no fetch lines, fast
```

Expected: first run fetches all played 2026 games, and the second fetches nothing.
- [ ] **Step 8: Commit** `feat: incremental per-game fetching with 429 backoff for pbp and shots`

---

### Task 4: `fetch_lineups.py` (lineups + games metadata in the pipeline)

`data_cache/pbp_lineups_{S}.csv` (RAPM, lineups) and `data_cache/games_{S}.csv` (RAPM home map) were previously built by hand with `the_lineup_analyzer.py` / `the_gauntlet.py`. The lineup call in `the_lineup_analyzer.py` (`get_pbp_data_with_lineups`) no longer exists in `euroleague_api` 0.1.0.

**Files:**
- Create: `fetch_lineups.py`
- Modify: `the_lineup_analyzer.py:19-90` — replace `fetch_pbp_with_lineups` body with a call to `fetch_lineups.fetch_lineups(season)` so the old script keeps working
- Test: `tests/test_fetch_lineups.py`

**Interfaces:**
- Consumes: `incremental_fetch.fetch_missing_games`, `played_gamecodes`; `season_config.CURRENT_SEASON`.
- Produces: `to_team_lineup_columns(df: pd.DataFrame) -> pd.DataFrame`; `fetch_lineups(season: int) -> pd.DataFrame`; `fetch_games_metadata(season: int) -> pd.DataFrame`. Output CSV format must match the existing `data_cache/pbp_lineups_2025.csv`: one `Lineup_{TEAMCODE}` column per team (values are 5-name lists), plus `Gamecode` **and** `GameCode` columns.

API facts (verified 2026-10-12): `PlayByPlay().get_game_pbp_data_lineups(season, gamecode)` returns columns incl. `Gamecode, CODETEAM, PLAYER, IsHomeTeam, Lineup_A, Lineup_B`. `IsHomeTeam` is `None` on every row, so team assignment must come from matching names. Example game 2026/1: `Lineup_A = ['MOTLEY, JOHNATHAN', ...]`, `Lineup_B = ['WILLIAMS-GOSS, NIGEL', ...]`.

- [ ] **Step 1: Write failing test** `tests/test_fetch_lineups.py`

```python
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fetch_lineups import to_team_lineup_columns


def _game():
    a = ['A1', 'A2', 'A3', 'A4', 'A5']
    b = ['B1', 'B2', 'B3', 'B4', 'B5']
    return pd.DataFrame({
        'Gamecode': [7, 7, 7, 7],
        'CODETEAM': ['RED', 'PAR', 'RED', None],
        'PLAYER':   ['A1', 'B2', 'A3', None],
        'IsHomeTeam': [None] * 4,
        'Lineup_A': [a, a, a, a],
        'Lineup_B': [b, b, b, b],
    })


def test_renames_by_player_membership():
    out = to_team_lineup_columns(_game())
    assert 'Lineup_RED' in out.columns and 'Lineup_PAR' in out.columns
    assert 'Lineup_A' not in out.columns and 'Lineup_B' not in out.columns
    assert out['Lineup_RED'].iloc[0][0] == 'A1'
    assert list(out['GameCode']) == [7, 7, 7, 7]


def test_swapped_sides():
    df = _game()
    df['CODETEAM'] = ['PAR', 'RED', 'PAR', None]   # A players belong to PAR now
    out = to_team_lineup_columns(df)
    assert out['Lineup_PAR'].iloc[0][0] == 'A1'


def test_old_format_passthrough():
    df = pd.DataFrame({'Gamecode': [1], 'Lineup_IST': [['x']]})
    out = to_team_lineup_columns(df)
    assert 'Lineup_IST' in out.columns
```

- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** `fetch_lineups.py`

```python
"""Fetch current-season PBP-with-lineups and game metadata into data_cache/.

Outputs (consumed by calculate_rapm.py and calculate_lineups.py):
  data_cache/pbp_lineups_{season}.csv  — PBP rows with Lineup_{TEAMCODE} columns
  data_cache/games_{season}.csv        — game metadata (gamenumber, homecode, ...)
"""
import os
import sys

import pandas as pd
from euroleague_api import play_by_play_data
from euroleague_api.EuroLeagueData import EuroLeagueData

from incremental_fetch import fetch_missing_games, played_gamecodes
from season_config import CURRENT_SEASON

CACHE_DIR = 'data_cache'


def _team_for(lineup_col, df):
    names = set()
    for lineup in df[lineup_col].dropna():
        names.update(lineup)
    owners = df.loc[df['PLAYER'].isin(names), 'CODETEAM'].dropna()
    return owners.mode().iloc[0] if not owners.empty else None


def to_team_lineup_columns(df):
    """Rename Lineup_A/Lineup_B to Lineup_{TEAMCODE}.

    euroleague_api 0.1 labels lineups A/B and leaves IsHomeTeam empty, so
    each side's team is the CODETEAM most often attached to its players.
    """
    df = df.copy()
    if 'Lineup_A' in df.columns:
        rename = {}
        for col in ('Lineup_A', 'Lineup_B'):
            team = _team_for(col, df)
            if team:
                rename[col] = f'Lineup_{team}'
        df = df.rename(columns=rename)
    if 'Gamecode' in df.columns and 'GameCode' not in df.columns:
        df['GameCode'] = df['Gamecode']
    return df


def fetch_lineups(season=CURRENT_SEASON):
    pbp = play_by_play_data.PlayByPlay()
    path = os.path.join(CACHE_DIR, f'pbp_lineups_{season}.csv')
    gamecodes = played_gamecodes(f'schedule_{season}.json')

    def fetch_one(gc):
        g = pbp.get_game_pbp_data_lineups(season, gc)
        return to_team_lineup_columns(g) if g is not None and not g.empty else g

    df, _failed = fetch_missing_games(path, gamecodes, fetch_one)
    print(f"{path}: {df['Gamecode'].nunique() if not df.empty else 0} games")
    return df


def fetch_games_metadata(season=CURRENT_SEASON):
    path = os.path.join(CACHE_DIR, f'games_{season}.csv')
    df = EuroLeagueData().get_game_metadata_season(season)
    df.to_csv(path, index=False)
    print(f"{path}: {len(df)} games")
    return df


if __name__ == '__main__':
    os.makedirs(CACHE_DIR, exist_ok=True)
    lineups = fetch_lineups()
    games = fetch_games_metadata()
    sys.exit(1 if lineups.empty or games.empty else 0)
```

`get_game_metadata_season` is the call `the_gauntlet.py:66` used. Check it still exists in 0.1.0: `.venv/Scripts/python.exe -c "from euroleague_api.EuroLeagueData import EuroLeagueData as E; print(hasattr(E(),'get_game_metadata_season'))"`. If it doesn't, find the 0.1.0 equivalent with `dir()` and use that. The output must keep `gamenumber` and `homecode` columns, because `calculate_rapm.py:218` reads them. Rename to those names if needed.

- [ ] **Step 4: Run tests, expect PASS**
- [ ] **Step 5: Live check**: `.venv/Scripts/python.exe fetch_lineups.py`, then `.venv/Scripts/python.exe -c "import pandas as pd; d=pd.read_csv('data_cache/pbp_lineups_2026.csv',low_memory=False); print(d['Gamecode'].nunique(), sorted(c for c in d.columns if c.startswith('Lineup_')))"`. Expect ~20 `Lineup_XXX` columns (the 20 teams of 2026, incl. `Lineup_BES`), and no `Lineup_A`/`Lineup_B`.
- [ ] **Step 6:** Point `the_lineup_analyzer.py`'s `fetch_pbp_with_lineups(season)` at `fetch_lineups.fetch_lineups(season)` (keep the function name and signature), and set its `START_SEASON = END_SEASON = CURRENT_SEASON` from `season_config`.
- [ ] **Step 7: Commit** `feat: fetch lineups and game metadata in pipeline, adapt to Lineup_A/B format`

---

### Task 5: Fetch-phase parametrization + orchestrator wiring

**Files (modify; line numbers are pre-change):**

| File | Change |
|---|---|
| `fetch_schedule.py:21,50` | `def fetch_and_cache_schedule(season=CURRENT_SEASON)`, argparse default `CURRENT_SEASON`, help text `default: current season`. **Also** save the raw XML to `official_schedule_{season}.xml`. Fetch it with `requests.get('https://api-live.euroleague.net/v1/schedules', params={'seasonCode': season_code(season)}, timeout=30)`, write `r.text`, then parse the same text with `xmltodict` into the DataFrame instead of calling `Schedule.get_schedule` (one request instead of two; same columns: `pd.DataFrame(xmltodict.parse(r.text)['schedule']['item'])`). Retry up to 3× with 10s sleep on non-200. The XML is read by 8 downstream scripts. |
| `fetch_mvp_data_v2.py:8,68,69` | `season = CURRENT_SEASON`; output `f'mvp_all_game_stats_{season}.json'`. Delete the stale musing comments on lines 18-19. |
| `parse_mvp_data.py:5` | read `f'mvp_all_game_stats_{CURRENT_SEASON}.json'` |
| `fetch_player_career_stats.py:11-12,56` | `SEASONS = ALL_SEASONS`; drop the "bump upper bound" comment; print uses `SEASONS[0]`–`SEASONS[-1]` |
| `fetch_all_seasons.py:2,10` | `SEASONS = ALL_SEASONS`; docstring "from 2007-08 to the current season" |
| `refresh_all.py` | Phase 1 order: **Fetch Schedule first** (pbp/shots/lineups need `schedule_{S}.json`), then game stats, PBP, shots, **new** `('Fetch Lineups', 'fetch_lineups.py')`, career stats, parse. After `parse_mvp_data.py`, **new** `('Clutch Stats', 'generate_clutch_data.py')` (created in Task 6). Print `f"Season: {season_label()}"` under the banner. Set `os.environ.setdefault('EUROLEAGUE_SEASON', str(CURRENT_SEASON))` so child scripts agree. |

- [ ] **Step 1:** Make the edits above. In each script, `from season_config import CURRENT_SEASON` (plus `ALL_SEASONS`, `season_code`, `season_label` where needed).
- [ ] **Step 2:** `.venv/Scripts/python.exe fetch_schedule.py --force && head -c 300 official_schedule_2026.xml`. Expect the XML header and `<date>Sep 24, 2026</date>`-era items.
- [ ] **Step 3:** `.venv/Scripts/python.exe fetch_mvp_data_v2.py && .venv/Scripts/python.exe parse_mvp_data.py`, then check `mvp_standings_derived.json` has 20 teams incl. `BES` and max GP ≈ current round:

```bash
.venv/Scripts/python.exe -c "import json;d=json.load(open('mvp_standings_derived.json'));print(len(d),'BES' in d,max(t['GP'] for t in d.values()))"
```

- [ ] **Step 4: Commit** `feat: drive fetch phase from season_config, fetch schedule xml, wire new steps`

---

### Task 6: Clutch stats from local PBP

`calculate_mvp_scores.py` returns early (no MVP output at all) if `clutch_stats_{S}_{S}.json` is missing. The file was last regenerated by hand on 2026-02-18.

**Files:**
- Modify: `clutchStats.py:13-30,180` — signature `analyze_clutch_stats(start_season=2023, end_season=2024, full_df=None, output_path='clutch_stats_multiple_seasons.json')`. When `full_df` is given, skip the API fetch. Write to `output_path`. Default behaviour unchanged for other callers.
- Create: `generate_clutch_data.py`; delete `generate_clutch_data_2025.py` (`git rm`)
- Modify: `calculate_mvp_scores.py:25-27` → `f'clutch_stats_{CURRENT_SEASON}_{CURRENT_SEASON}.json'`, key `str(CURRENT_SEASON)`. Check how `analyze_clutch_stats` keys `results_by_season` (int vs str, which becomes str after JSON) and match it.

```python
"""Generate current-season clutch stats from the cached play-by-play CSV."""
import sys

import pandas as pd

from clutchStats import analyze_clutch_stats
from season_config import CURRENT_SEASON


def main():
    pbp_path = f'pbp_{CURRENT_SEASON}.csv'
    out_path = f'clutch_stats_{CURRENT_SEASON}_{CURRENT_SEASON}.json'
    df = pd.read_csv(pbp_path, low_memory=False)
    analyze_clutch_stats(CURRENT_SEASON, CURRENT_SEASON, full_df=df, output_path=out_path)
    print(f"Saved {out_path}")


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 1:** Implement. **Step 2:** `.venv/Scripts/python.exe generate_clutch_data.py`, then `.venv/Scripts/python.exe calculate_mvp_scores.py`. Expect `mvp_rankings_2026.json` (or with suffix) to be written, with players from 2026 teams.
- [ ] **Step 3: Regression**: `EUROLEAGUE_SEASON=2025 .venv/Scripts/python.exe generate_clutch_data.py` produces a `clutch_stats_2025_2025.json`. Diff its top-10 `ClutchPoints` against `git show HEAD:clutch_stats_2025_2025.json`. Values should be ≥ the committed (Feb) values (more games now) and in the same format. Then `git checkout clutch_stats_2025_2025.json` to restore.
- [ ] **Step 4: Commit** `feat: generate current-season clutch stats from local pbp in pipeline`

---

### Task 7: Compute scripts

**Files (modify; pre-change line numbers):**

| File | Change |
|---|---|
| `calculate_adjusted_ratings.py:2,54,276` | docstring "Euroleague (current season)"; `ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')` ×2 |
| `calculate_mvp_scores.py:149` | `f'mvp_rankings_{CURRENT_SEASON}{round_suffix}.json'` |
| `calculate_tpm.py:2,12,13,100,123` | rename `calculate_tpm_2025` → `calculate_tpm`; input `mvp_all_game_stats_{S}.json`; banner uses `season_label()` |
| `calculate_wir.py:2,11,12,139,172` | same pattern (`calculate_wir`) |
| `calculate_wpa.py:2,29,30,57,123` | `pbp_{S}.csv`; fallback season `CURRENT_SEASON`; banner `season_label()` |
| `calculate_elo.py:73-88` | replace env/glob detection with `current_season = CURRENT_SEASON` |
| `simulate_monte_carlo.py:249` | `official_schedule_{S}.xml` |
| `calculate_rapm.py:2,33,37-41,59` | `SEASON = CURRENT_SEASON`; replace hardcoded `EL_TEAMS` with the team codes in `mvp_standings_derived.json`: `EL_TEAMS = set(json.load(open('mvp_standings_derived.json', encoding='utf-8')).keys())`, computed inside the function that uses it, not at import; stats file `mvp_all_game_stats_{SEASON}.json` |
| `calculate_gci.py:16` | `SEASON = str(CURRENT_SEASON)` |
| `calculate_gci_historical.py:26` | `SEASONS = COMPLETED_SEASONS` (now includes 2025). Then **run it** to regenerate `docs/gci_historical.json` and confirm `tests/test_gci_historical.py` still passes. |
| `train_wp_model.py:4,324-327,397,466` | leave the split logic. Update the docstring to "every completed season's play-by-play". Not run in CI (`--skip-wp-train`). Do **not** retrain in this task. |

- [ ] **Step 1:** Make the edits. **Step 2:** Run each of `calculate_adjusted_ratings.py calculate_mvp_scores.py calculate_tpm.py calculate_wir.py calculate_wpa.py calculate_elo.py simulate_monte_carlo.py calculate_rapm.py calculate_lineups.py calculate_gci.py` with `EUROLEAGUE_ROUND_SUFFIX` set from the current max GP (e.g. `_R8`). Each must exit 0, and printed team lists must include `BES` and exclude `MCO`.
- [ ] **Step 3:** `.venv/Scripts/python.exe calculate_gci_historical.py && .venv/Scripts/python.exe -m pytest tests/test_gci_historical.py -q` → pass; `docs/gci_historical.json` `league_trends.seasons[-1] == 2025`.
- [ ] **Step 4: Commit** `feat: compute engines read season from season_config`

---

### Task 8: Visualization + oracle scripts

| File | Change |
|---|---|
| `visualize_mvp_ladder.py:9,11,67,81` | `mvp_rankings_{S}{suffix}.json` / fallback `mvp_rankings_{S}.json`; title `f'Euroleague {season_label()} MVP Ladder ({round_label})'`; output `mvp_ladder_{S}{suffix}.png` |
| `visualize_rapm.py:2,95` | `season_label()` in title |
| `visualize_tpm_wir.py:82`, `visualize_wpa.py:35` | `season_label()` in titles |
| `visualize_standings_race.py:92` | `f"EUROLEAGUE STANDINGS RACE {season_label()}"` |
| `visualize_remaining_sos.py:2` | docstring |
| `visualize_round_preview.py:52`, `visualize_schedule_grid.py:81`, `visualize_clutch_matchups.py:72`, `mvp_oracle.py:256`, `oracle_accuracy_tracker.py:107-108` | `official_schedule_{CURRENT_SEASON}.xml` |

- [ ] **Step 1:** Edits. **Step 2:** Run each Phase-3 script in `refresh_all.py`'s `viz_scripts` list except `export_dashboard_data.py`, with the round suffix env set. All exit 0. Open 2 PNGs (MVP ladder, schedule grid) with the Read tool and check the title says 2026-27 and BES is drawn with its logo.
- [ ] **Step 3: Commit** `feat: visualizations and oracle read season from season_config`

---

### Task 9: `export_dashboard_data.py`

**Interfaces:**
- Produces in `docs/data/current/dashboard.json`: `"season": 2026`, `"season_label": "2026-27"` (top level, next to `"round"`). Task 11 reads these.

| Lines (pre-change) | Change |
|---|---|
| 69, 73, 808, 2023 | `official_schedule_{S}.xml` |
| 123, 126, 216, 537, 793, 961, 3296, 3349 | `mvp_all_game_stats_{S}.json` |
| 440, 442 | `shot_data_{S}_{S}.csv` |
| 282 | `glob.glob('shot_data_*_*.csv')` picks an arbitrary season. Use `f'shot_data_{S}_{S}.csv'` explicitly. |
| 606 | `data_cache/pbp_{S}.csv` |
| 1491, 1498 | `for season in COMPLETED_SEASONS:` (**Review Focus #2**) |
| 1606 | fallback `mvp_rankings_{S}.json` |
| 3192, 3222 | comment + `schedule_{S}.json` |
| where `'round'` is set in the output dict | add `'season': CURRENT_SEASON, 'season_label': season_label()` |

- [ ] **Step 1:** Edits. Use `S = CURRENT_SEASON` imported at top.
- [ ] **Step 2:** Run `.venv/Scripts/python.exe export_dashboard_data.py` → exit 0. Verify:

```bash
.venv/Scripts/python.exe -c "
import json; d=json.load(open('docs/data/current/dashboard.json',encoding='utf-8'))
print(d['season'], d['season_label'], d['round'])
print('BES' in json.dumps(d['teams']))
print([s.get('season') for s in d['championship_finals_history']][-3:])"
```

Expected: `2026 2026-27 <8-ish>`, `True`, last finals season `2025` (no 2026 entry).
- [ ] **Step 3:** If any section crashes because 2026 has no playoff data yet, make that section emit its empty value (`[]`/`{}`) instead of raising. Keep the dashboard keys present.
- [ ] **Step 4: Commit** `feat: export current season to dashboard, finals history uses completed seasons only`

---

### Task 10: Team mappings (BES in, MCO historical)

- [ ] **Step 1:** `docs/constants.js`: add to current-season block `BES:'#d9d9d9'` (Beşiktaş black/white; light grey stays visible on the dark theme) and `BES:'Besiktas Istanbul'`. Move `MCO` (and `BER`, which is also absent from the 2026 API team list) into the "Historical" blocks. Change the block comments to `// Current season` / `// Historical` (no years).
- [ ] **Step 2:** Python team dicts. For every file listed by

```bash
grep -rlE "['\"]ZAL['\"]\s*:" --include=*.py . --exclude-dir=.venv --exclude-dir=.claude --exclude-dir=archive
```

that has a name/color dict containing `DUB` but not `BES`, add `'BES'` with the same name/color as above. Don't remove MCO from Python dicts, because historical scripts need it.
- [ ] **Step 3:** Confirm `docs/logos/BES.png` exists (it does) and that `chart_utils.py`'s logo loader resolves it: `.venv/Scripts/python.exe -c "import chart_utils, inspect; print([n for n in dir(chart_utils) if 'logo' in n.lower()])"`, then call the loader for `'BES'` and expect a non-None image.
- [ ] **Step 4: Commit** `feat: add Besiktas (BES) to team mappings, move MCO/BER to historical`

---

### Task 11: Frontend season awareness

**Files:** `docs/constants.js`, `docs/game-control.js:121`, `docs/playoffs.js:1224`, `docs/series.js:193,324`, `docs/player.js:3,224`, `docs/gci-history.js:44-120`, `docs/title-race.js`, `docs/playoffs.html:914`, `docs/title-race.html:8,10,154`, `docs/records.html:122`, `docs/replay.html:10,12,54`, `docs/about.html:250,292,526,536,569`, `docs/gci-history.html:10`, `docs/style.css`.

**Interfaces:**
- Consumes: `dashboard.season`, `dashboard.season_label` (Task 9); `docs/data/archive/2025/dashboard.json` (Task 2).
- Produces (in `constants.js`, global functions like `getTeamColor`):

```js
// Season of a dashboard.json payload (pre-2026 dashboards had no field → 2025).
function dashboardSeason(dash) { return (dash && dash.season) || 2025; }
function seasonLabel(s) { return `${s}-${String(s + 1).slice(-2)}`; }
function isEmptyData(v) {
    if (v == null) return true;
    if (Array.isArray(v)) return v.length === 0;
    if (typeof v === 'object') return Object.keys(v).length === 0;
    return false;
}
// Playoff-only pages show last season's final playoffs until the new ones start.
async function loadPlayoffDashboard() {
    const cur = await fetchJSON('data/current/dashboard.json');
    if (!isEmptyData(cur.series)) return { dash: cur, archived: false };
    const prev = dashboardSeason(cur) - 1;
    try {
        const old = await fetchJSON(`data/archive/${prev}/dashboard.json`);
        return { dash: old, archived: true, archivedSeason: prev, currentSeason: dashboardSeason(cur) };
    } catch (e) {
        return { dash: cur, archived: false };
    }
}
```

(`fetchJSON` already exists in `constants.js` or a shared file. Grep for it. If it's defined elsewhere, make sure `constants.js` is loaded after it on the pages that use `loadPlayoffDashboard`, or define these after `fetchJSON`.)

- [ ] **Step 1:** Add the helpers above.
- [ ] **Step 2: Replay links** (`game-control.js:121`, `playoffs.js:1224`, `series.js:193`): replace `season=2025` with `season=${dashboardSeason(<the dashboard object in scope>)}`. Store the season in a module variable when the dashboard loads if the object isn't in scope there.
- [ ] **Step 3: `player.js`**: `CURRENT_SEASON_CODE` becomes derived. Load `data/current/dashboard.json` alongside existing data (or take the max season code found in the career data if the page doesn't load the dashboard) and set `CURRENT_SEASON_CODE = 'E' + season`. Line 224: compute the count/range from the data (`new Set(seasons).size` seasons · `2007–<last>`).
- [ ] **Step 4: `gci-history.js`**: rename `merge2025` → `mergeCurrentSeason`, and use `const yr = dashboardSeason(dashboard)` everywhere 2025 is hardcoded in that function (lines 44-120, incl. Modern Era end). If `hist.league_trends.seasons` already contains `yr`, skip merging (guards double counting). **Review Focus #3.**
- [ ] **Step 5: Playoff-only pages** (`series.js`, `title-race.js`): load via `loadPlayoffDashboard()`. When `archived`, show a banner at the top of the main content: `Showing the ${seasonLabel(archivedSeason)} playoffs (final). The ${seasonLabel(currentSeason)} playoffs start in April.` Add `.season-banner` to `docs/style.css` using existing tokens (muted surface, small text, rounded, margin-bottom). Make `title-race.html:154` heading dynamic (`🏆 ${seasonLabel(...)} Championship Chase`) and the meta descriptions season-neutral ("through the Euroleague playoffs").
- [ ] **Step 6: `playoffs.js` / `playoffs.html`**: this page mixes regular-season projections (`playoff_matchup_probs`, `championship_odds`) with playoff results. Keep it on the current dashboard. Heading `2025 Euroleague Playoffs` → filled by JS with `${seasonLabel(dashboardSeason(dash))} Euroleague Playoffs`. For each section driven by `playoff_results` / `path_to_title` / `playoff_recaps` / `series`, make sure an empty value hides the section or shows its existing empty state rather than throwing. The championship-finals history section stays.
- [ ] **Step 7: Static copy:** `records.html:122` → `20 seasons · 2007–08 to 2026–27 · Euroleague only`; `replay.html` 3 spots → `to 2026-27`; `gci-history.html:10` → `20 seasons`… `to 2026`; `about.html`: `Seasons (2007-2026)`, `20 seasons`, `(2007–2026)`, Modern Era `(2020–2026, 18–20 teams)`, records `20 Euroleague seasons (2007–08 to 2026–27)`. Add one sentence to about.html's data/methodology section: *"Season-aware since 2026-27: the pipeline tracks the live season, and last season's final playoffs remain browsable until the new playoffs begin."* (user rule: always update about page). `series.js:324` Final Four venue comment: leave as-is (historical fact), but if the code uses the 2025 venue timezone for *upcoming* games, note it in the task report. 2027 F4 venue is out of scope.
- [ ] **Step 8:** Browser check via Task 13 harness (or do it here): serve `docs/` (`.venv/Scripts/python.exe -m http.server 8765 -d docs`) and load `index.html, team.html, players.html, player.html, h2h.html, recap.html, shots.html, network.html, replay.html, playoffs.html, series.html, title-race.html, mvp.html, gci-history.html, game-control.html, records.html, about.html`. Expect no console errors, 2026-27 labels where the season is named, the archive banner on series/title-race, and GCI history showing 2025 and 2026 as separate points.
- [ ] **Step 9: Commit** `feat: frontend reads season from dashboard, archived playoffs fallback, about page`

---

### Task 12: CI workflow + docs

**Files:** `.github/workflows/refresh_data.yml`, `CLAUDE.md`, test `tests/test_no_hardcoded_season.py`.

- [ ] **Step 1: Guard test** `tests/test_no_hardcoded_season.py`

```python
"""Pipeline scripts must take the season from season_config."""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), '..')
ALLOWED = {'season_config.py', 'train_wp_model.py'}   # train: historical split


def _pipeline_scripts():
    src = open(os.path.join(ROOT, 'refresh_all.py'), encoding='utf-8').read()
    names = set(re.findall(r"['\"]([a-z_0-9]+\.py)['\"]", src))
    names |= {'refresh_all.py', 'fetch_all_seasons.py', 'incremental_fetch.py'}
    return sorted(n for n in names if os.path.exists(os.path.join(ROOT, n)))


def test_no_literal_current_years():
    offenders = []
    for name in _pipeline_scripts():
        if name in ALLOWED:
            continue
        for i, line in enumerate(open(os.path.join(ROOT, name), encoding='utf-8'), 1):
            code = line.split('#', 1)[0]
            if re.search(r'\b202[5-9]\b', code):
                offenders.append(f'{name}:{i}: {line.strip()}')
    assert not offenders, '\n'.join(offenders)
```

Run it. Fix any offenders it finds (string literals inside docstrings count; reword them), until it passes.

- [ ] **Step 2: Workflow** `refresh_data.yml`:
  - cron → `'0 1 * * 3,4,5,6'` and keep the comment lines: `# Regular season: Wed-Sat 01:00 UTC (after Tue-Fri games)` / `# Playoffs: switch to '0 1 * * *'`.
  - After `Install dependencies`, add:

```yaml
    - name: Restore fetch caches
      uses: actions/cache@v4
      with:
        path: |
          pbp_*.csv
          shot_data_*.csv
          data/shot_data_*.csv
          data_cache/pbp_lineups_*.csv
        key: fetch-cache-${{ github.run_id }}
        restore-keys: fetch-cache-
```

  (`actions/cache` saves automatically in its post step, with a new key each run, and restores the latest via the prefix. Tracked files in those globs get overwritten by the cached copies, which is fine because the cache is a superset.)
- [ ] **Step 3: `CLAUDE.md`**: add a "Season" subsection under Architecture saying that `season_config.py` holds `CURRENT_SEASON`, that you bump it each autumn (or set `EUROLEAGUE_SEASON`), and that you move the previous season's root `*_R*` / `oracle_forecast_round_*` files to `archive/{year}/` and copy the final dashboard to `docs/data/archive/{year}/dashboard.json`. Fix "19 seasons (2007–2025)" → "20 seasons (2007–2026)". Replace the stale note that `TEAM_NAMES`/`TEAM_COLORS` live in `season.js` and `players.js`: they're in `docs/constants.js` only. Add `fetch_lineups.py` and `generate_clutch_data.py` to the Phase 1 line. Mention tests: `.venv/Scripts/python.exe -m pytest tests/ -q`.
- [ ] **Step 4:** Validate YAML: `.venv/Scripts/python.exe -c "import yaml,sys;yaml.safe_load(open('.github/workflows/refresh_data.yml'))"` (if `yaml` missing, `pip install pyyaml` into the venv, no requirements change).
- [ ] **Step 5: Commit** `ci: wed-sat schedule and persistent fetch caches; docs: season config`

---

### Task 13: End-to-end verification

- [ ] **Step 1:** `.venv/Scripts/python.exe -m pytest tests/ -q`, all pass.
- [ ] **Step 2:** `.venv/Scripts/python.exe refresh_all.py --skip-wp-train`. Expect the summary to show 0 failed. Record runtime. Run it a second time: the fetch phase should fetch ~0 new games and be much faster.
- [ ] **Step 3:** `git status`: new outputs are `_R{n}` for the current 2026 round. `archive/2025/` is untouched. `docs/data/current/dashboard.json` has `season: 2026`.
- [ ] **Step 4:** Browser smoke test (Playwright MCP tools or a scripted check) over every page listed in Task 11 Step 8. Collect console errors. Screenshot index.html, playoffs.html, series.html, gci-history.html and attach the observations to the report.
- [ ] **Step 5:** Commit generated outputs: `chore: first 2026-27 pipeline run (R{n})`.
- [ ] **Step 6:** Report to the user. Do **not** push. Report: pushing triggers Pages; the first CI run has no cache yet and will fetch all played games once, throttled.
