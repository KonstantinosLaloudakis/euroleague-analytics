# Game Records Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the comebacks scan into a one-pass Game Records engine that also publishes single-game player highs and game-winners as two new tabs on the All-Time Records page.

**Architecture:**
- `pbp_games.py` owns the play-by-play cleaning steps (sort, coercion, skip rules, team detection) and the shared ranking and JSON helpers.
- Three analyzers each take a cleaned game: `calculate_comebacks.py` (refactored, output byte-identical), `game_highs.py` and `game_winners.py`.
- `calculate_game_records.py` iterates every game once and writes three JSON files.
- `docs/records.js` lazy-loads each file into its own tab.

**Tech Stack:** Python 3 + pandas, pytest, vanilla JS/HTML (GitHub Pages, no build step).

**Spec:** `superpowers/specs/2026-10-14-game-records-engine-design.md`

## Global Constraints

- No literal years matching `\b202[5-9]\b` outside `#` comments (docstrings included) in `pbp_games.py`, `calculate_comebacks.py`, `game_highs.py`, `game_winners.py` or `calculate_game_records.py`. Seasons come from `season_config`.
- Python is `.venv/Scripts/python.exe` (Windows, Git Bash). Tests: `.venv/Scripts/python.exe -m pytest tests/ -q`, and test output must be pristine (no warnings).
- Clean-game rules: ≥ 30 scoring rows; max scoring `PERIOD` ≥ 4; final not tied; both finals ≥ 45. Glitch tolerance 3. Top-N = 25.
- Game-winner: made field goal (`2FGM`, `3FGM`, `DUNK`, `LAYUPMD`) by the winner, `PERIOD` ≥ 4, `seconds_left` ≤ 10, giving the lead for good, and the score jump must equal the shot value. Buzzer-beater means `seconds_left` ≤ 1.
- Output files: `docs/data/current/comebacks.json` (byte-identical to today's after the refactor), `docs/data/current/game_highs.json`, `docs/data/current/game_winners.json`. Replays: `docs/data/{season}/{gamecode}.json`.
- Ties share a rank and are flagged `tied`. Order is newest first (season desc, gamecode desc). Ties are counted before the top-N cut.
- Frontend: vanilla JS, no new dependencies, existing `style.css` variables only.
- Plans and specs live in `superpowers/`, never under `docs/`.
- Work on branch `feat/game-records`. Every commit message ends with a `Co-Authored-By:` trailer naming the model that wrote it, e.g. `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Events without a player.** Team rebounds and team turnovers (`PLAYER_ID` NaN) must not create a player line or crash. Pinned by `test_events_without_a_player_are_not_lines` (Task 2).
2. **`PLAYTYPE` values with trailing spaces** (`'AS '`, seen in the real feed) must still count. Pinned by the `'AS '` events in `test_counting_rules_including_old_play_types` (Task 2) and `test_pid_strip_and_playtype_strip` (Task 1).
3. **An unparseable clock on the go-ahead row** (`'ND'`, NaN) must skip the game, not crash. Pinned by `test_unparseable_clock_is_skipped` (Task 3).
4. **A game-winner by a shooter with no `PLAYER_ID`** must appear in the lists but not in the leaderboard. Pinned by `test_build_output_lists_and_leaders` (Task 3, the `None` player).
5. **A missing season file** must print a warning and skip that season, so the other seasons still process. Pinned by `test_iter_games_reads_cache_and_skips_missing_season` (Task 1).

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `pbp_games.py` | `CleanGame`, `clean_game`, `iter_games`, `rank_by`, `finish_rows`, `season_span`, `keep_generated_date`, `write_json_if_changed`, `mode_value`, `int_or_none` |
| Modify | `calculate_comebacks.py` | Becomes an analyzer on top of `pbp_games` (`analyze_game`, `analyze_clean`, `rank_entries`, `build_output`). Its `main()` is removed in Task 4 |
| Create | `game_highs.py` | Per-player single-game lines → `game_highs.json` |
| Create | `game_winners.py` | Go-ahead-for-good late field goals → `game_winners.json` |
| Create | `calculate_game_records.py` | One-pass entry point writing all three JSON files |
| Create | `tests/pbp_fixtures.py` | Made-up PBP builders (`game`, `BASIC`, `ev`, `build`, `filler`) |
| Create | `tests/test_pbp_games.py`, `tests/test_game_highs.py`, `tests/test_game_winners.py`, `tests/test_game_records.py` | Unit tests |
| Modify | `tests/test_comebacks.py` | Imports the fixtures; the `keep_generated_date` test uses the shared helper |
| Modify | `tests/test_no_hardcoded_season.py` | Always scans the new modules |
| Modify | `refresh_all.py`, `.github/workflows/wp_replay_update.yml` | Run `calculate_game_records.py` instead of `calculate_comebacks.py` |
| Modify | `docs/records.js`, `docs/records.html`, `docs/about.html` | Game Highs and Game-Winners tabs, shared lazy loader, methodology |

---

### Task 1: `pbp_games.py` shared cleaner and comebacks refactor

**Files:**
- Create: `pbp_games.py`, `tests/pbp_fixtures.py`, `tests/test_pbp_games.py`
- Modify: `calculate_comebacks.py` (full rewrite below), `tests/test_comebacks.py`

**Interfaces:**
- Produces (used by Tasks 2–4):
  - `pbp_games.CleanGame`, a dataclass with these fields:
    - `season: int, phase: str|None, round: int|None, gamecode: int`
    - `rows: DataFrame` (all rows, sorted, with added `PT` and `PID` columns)
    - `sc: DataFrame` (scoring rows, index reset)
    - `a: list[int], b: list[int], periods: list[int], clocks: list`
    - `final_a: int, final_b: int, a_won: bool`
    - `code_a, name_a, code_b, name_b`
    - `ot: bool`
  - `clean_game(g) -> CleanGame | None`
  - `iter_games(seasons=ALL_SEASONS, cache_dir=CACHE_DIR)`, a generator
  - `rank_by(records, key, limit=TOP_N) -> list[dict]`
  - `finish_rows(rows, replay_dir=REPLAY_DIR) -> rows`
  - `season_span(records) -> [first, last] | []`
  - `keep_generated_date(old, new, content_keys) -> new`
  - `write_json_if_changed(path, out, content_keys) -> out`
  - `mode_value(series)`, `int_or_none(v)`
  - Constants: `CACHE_DIR, REPLAY_DIR, TOP_N, MIN_SCORING_ROWS, MIN_FINAL, LAST_REGULATION_PERIOD, GLITCH_TOL`
  - `calculate_comebacks.analyze_clean(cg) -> dict`, `calculate_comebacks.build_output(records, current_season, replay_dir=REPLAY_DIR, generated=None)`, and the constants `calculate_comebacks.OUT_PATH` and `calculate_comebacks.CONTENT_KEYS`
  - `tests/pbp_fixtures.py`: `game(legs, ...)`, `BASIC`, `ev(side, pt, period=1, clock='05:00', player=None, name=None, n=1)`, `build(events, season=2015, gamecode=7, phase='RS', rnd=3)`, `filler(a_baskets, b_baskets, period=2)`

- [ ] **Step 1: Save the current comebacks output for the byte-identical check**

```bash
SP=C:/Users/klalo/AppData/Local/Temp/claude/c--Users-klalo-PycharmProjects-pythonProject/85a4f455-7e38-4931-9536-a78ced663cf8/scratchpad
cp docs/data/current/comebacks.json "$SP/comebacks.before.json"
```

- [ ] **Step 2: Create `tests/pbp_fixtures.py`**

```python
"""Made-up play-by-play builders shared by the game-records tests."""
import numpy as np
import pandas as pd

TEAM = {'A': 'HOM', 'B': 'AWY'}
SHOT_POINTS = {'2FGM': 2, 'DUNK': 2, 'LAYUPMD': 2, '3FGM': 3, 'FTM': 1}


def _begin_row(season, phase, rnd, gamecode):
    return {'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
            'NUMBEROFPLAY': 0, 'TRUE_NUMBEROFPLAY': 0, 'CODETEAM': np.nan,
            'TEAM': np.nan, 'PLAYTYPE': 'BP', 'POINTS_A': np.nan, 'POINTS_B': np.nan,
            'PERIOD': 1, 'MARKERTIME': np.nan}


def game(legs, season=2015, gamecode=7, phase='RS', rnd=3, true_numbers=True):
    """Build a PBP DataFrame. legs: (side, baskets, points_each, period, clock).

    Side 'A' is the home team (code HOM), 'B' the away team (code AWY).
    A non-scoring 'Begin Period' row comes first, as in the real feed.
    """
    rows = [_begin_row(season, phase, rnd, gamecode)]
    a = b = 0
    for side, n, pts, period, clock in legs:
        for _ in range(n):
            if side == 'A':
                a += pts
            else:
                b += pts
            code = TEAM[side]
            rows.append({'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
                         'NUMBEROFPLAY': len(rows), 'TRUE_NUMBEROFPLAY': len(rows),
                         'CODETEAM': code, 'TEAM': f'{code} Club', 'PLAYTYPE': '2FGM',
                         'POINTS_A': a, 'POINTS_B': b, 'PERIOD': period, 'MARKERTIME': clock})
    df = pd.DataFrame(rows)
    if not true_numbers:
        df = df.drop(columns='TRUE_NUMBEROFPLAY')
    return df


# Away team trails 0-20 in Q1, wins 52-50 (last basket: Q4 0:10, breaking a 50-50 tie).
BASIC = [('A', 10, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00'),
         ('A', 15, 2, 3, '05:00'), ('B', 1, 2, 4, '00:10')]


def ev(side, pt, period=1, clock='05:00', player=None, name=None, n=1):
    """n identical event specs for build(). Scoring play types add their points."""
    return [(side, pt, period, clock, player, name)] * n


def build(events, season=2015, gamecode=7, phase='RS', rnd=3):
    """Build PBP from ev() specs. Scoring rows carry POINTS_A/B; other events
    leave them NaN, as in the real feed."""
    first = _begin_row(season, phase, rnd, gamecode)
    first.update({'PLAYER_ID': np.nan, 'PLAYER': np.nan})
    rows = [first]
    a = b = 0
    for side, pt, period, clock, player, name in events:
        pts = SHOT_POINTS.get(pt.strip(), 0)
        if side == 'A':
            a += pts
        else:
            b += pts
        code = TEAM[side]
        rows.append({'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
                     'NUMBEROFPLAY': len(rows), 'TRUE_NUMBEROFPLAY': len(rows),
                     'CODETEAM': code, 'TEAM': f'{code} Club', 'PLAYTYPE': pt,
                     'PLAYER_ID': np.nan if player is None else player,
                     'PLAYER': np.nan if name is None else name,
                     'POINTS_A': a if pts else np.nan, 'POINTS_B': b if pts else np.nan,
                     'PERIOD': period, 'MARKERTIME': clock})
    return pd.DataFrame(rows)


def filler(a_baskets, b_baskets, period=2):
    """Anonymous 2FGM baskets: all of A's first, then all of B's."""
    return ev('A', '2FGM', period, n=a_baskets) + ev('B', '2FGM', period, n=b_baskets)
```

- [ ] **Step 3: Write the failing tests in `tests/test_pbp_games.py`**

```python
"""Tests for pbp_games.py (shared play-by-play cleaning and helpers)."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pbp_games as pg
from tests.pbp_fixtures import BASIC, build, ev, filler, game


def test_clean_game_basic_fields():
    cg = pg.clean_game(game(BASIC))
    assert (cg.season, cg.phase, cg.round, cg.gamecode) == (2015, 'RS', 3, 7)
    assert (cg.final_a, cg.final_b, cg.a_won) == (50, 52, False)
    assert (cg.code_a, cg.name_a, cg.code_b, cg.name_b) == ('HOM', 'HOM Club', 'AWY', 'AWY Club')
    assert cg.ot is False
    assert len(cg.sc) == 51 and cg.periods[-1] == 4 and cg.clocks[-1] == '00:10'
    assert len(cg.rows) == 52          # includes the non-scoring Begin Period row


def test_tied_final_is_none():
    assert pg.clean_game(game([('A', 25, 2, 1, '05:00'), ('B', 25, 2, 4, '05:00')])) is None


def test_pid_strip_and_playtype_strip():
    events = (filler(25, 26, period=4)
              + ev('A', 'AS ', 4, player='P012774', name='DOE, JOHN')
              + ev('B', 'D', 4, player=' PABC ', name='ROE, RICH'))
    cg = pg.clean_game(build(events))
    assert '012774' in cg.rows['PID'].tolist()
    assert 'ABC' in cg.rows['PID'].tolist()
    assert cg.rows['PID'].isna().sum() == 52   # Begin Period row + 51 anonymous baskets
    assert 'AS' in cg.rows['PT'].tolist()


def test_scores_and_periods_given_as_strings_are_coerced():
    df = game(BASIC).astype({'POINTS_A': object, 'PERIOD': object})
    df['POINTS_A'] = df['POINTS_A'].map(lambda v: v if pd.isna(v) else str(int(v)))
    df['PERIOD'] = df['PERIOD'].astype(str)
    cg = pg.clean_game(df)
    assert (cg.final_a, cg.final_b) == (50, 52)


def _r(value, season, gamecode):
    return {'value': value, 'season': season, 'gamecode': gamecode}


def test_rank_by_ties_cutoff_and_zero_filter():
    recs = [_r(5, 2010, 1), _r(7, 2011, 2), _r(7, 2012, 3), _r(0, 2013, 4), _r(6, 2014, 5)]
    out = pg.rank_by(recs, 'value', limit=2)
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == [(3, 1, True), (2, 1, True)]
    out = pg.rank_by(recs, 'value')
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == \
        [(3, 1, True), (2, 1, True), (5, 3, False), (1, 4, False)]
    assert 'rank' not in recs[0]


def test_finish_rows_and_season_span(tmp_path):
    os.makedirs(tmp_path / '2015')
    (tmp_path / '2015' / '7.json').write_text('{}')
    rows = pg.finish_rows([_r(1, 2015, 7), _r(1, 2016, 8)], str(tmp_path))
    assert [(r['season_label'], r['has_replay']) for r in rows] == \
        [('2015-16', True), ('2016-17', False)]
    assert pg.season_span(rows) == [2015, 2016]
    assert pg.season_span([]) == []


def test_write_json_if_changed_keeps_date_only_when_content_same(tmp_path):
    path = str(tmp_path / 'out' / 'x.json')
    pg.write_json_if_changed(path, {'generated': '2000-01-01', 'v': 1}, ('v',))
    kept = pg.write_json_if_changed(path, {'generated': '2001-01-01', 'v': 1}, ('v',))
    assert kept['generated'] == '2000-01-01'
    changed = pg.write_json_if_changed(path, {'generated': '2002-01-01', 'v': 2}, ('v',))
    assert changed['generated'] == '2002-01-01'
    with open(path, encoding='utf-8') as f:
        assert json.load(f)['generated'] == '2002-01-01'


def test_iter_games_reads_cache_and_skips_missing_season(tmp_path, capsys):
    pd.concat([game(BASIC, gamecode=7), game(BASIC, gamecode=8)]).to_csv(
        tmp_path / 'pbp_2015.csv', index=False)
    games = list(pg.iter_games([2015, 2016], cache_dir=str(tmp_path)))
    assert [g.gamecode for g in games] == [7, 8]
    assert 'pbp_2016.csv missing' in capsys.readouterr().out
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pbp_games.py -q`
Expected: `ModuleNotFoundError: No module named 'pbp_games'`.

- [ ] **Step 5: Create `pbp_games.py`**

```python
"""
Shared play-by-play cleaning for the game-records engine.

clean_game() turns one game's raw PBP rows into a CleanGame (sorted rows,
numeric scores, team codes, final score) or None when the log is unusable.
iter_games() yields a CleanGame for every usable cached game. The ranking,
row-finishing and JSON-writing helpers are shared by every record board.
"""
import json
import os
from collections import Counter
from dataclasses import dataclass

import pandas as pd

from season_config import ALL_SEASONS, season_label

CACHE_DIR = 'data_cache'
REPLAY_DIR = os.path.join('docs', 'data')
TOP_N = 25
MIN_SCORING_ROWS = 30        # fewer scoring plays than this = truncated game
MIN_FINAL = 45               # a final under this is a data error, not a score
LAST_REGULATION_PERIOD = 4   # a log ending earlier is an incomplete game
GLITCH_TOL = 3               # one play moves the margin by at most 3 points


@dataclass
class CleanGame:
    season: int
    phase: object            # str | None
    round: object            # int | None
    gamecode: int
    rows: pd.DataFrame       # every row, sorted, with PT and PID columns
    sc: pd.DataFrame         # scoring rows only, index reset
    a: list
    b: list
    periods: list
    clocks: list
    final_a: int
    final_b: int
    a_won: bool
    code_a: object
    name_a: object
    code_b: object
    name_b: object
    ot: bool


def mode_value(series):
    m = series.dropna().astype(str).str.strip().mode()
    return m.iloc[0] if not m.empty else None


def int_or_none(v):
    try:
        return None if pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def _pid(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s[1:] if s.startswith('P') else s


def clean_game(g):
    """One game's raw PBP rows -> CleanGame, or None if the game is unusable."""
    key = ('TRUE_NUMBEROFPLAY'
           if 'TRUE_NUMBEROFPLAY' in g and g['TRUE_NUMBEROFPLAY'].notna().all()
           else 'NUMBEROFPLAY')
    g = g.drop_duplicates([key, 'PLAYTYPE', 'CODETEAM']).copy()
    for col in ('POINTS_A', 'POINTS_B', 'PERIOD'):
        g[col] = pd.to_numeric(g[col], errors='coerce')
    g['PT'] = g['PLAYTYPE'].astype(str).str.strip()
    g['PID'] = g['PLAYER_ID'].map(_pid) if 'PLAYER_ID' in g else None
    g = g.sort_values(['PERIOD', key], kind='stable')
    sc = g[g['POINTS_A'].notna() | g['POINTS_B'].notna()].reset_index(drop=True)
    if len(sc) < MIN_SCORING_ROWS:
        return None
    if sc['PERIOD'].max() < LAST_REGULATION_PERIOD:
        return None
    a = sc['POINTS_A'].ffill().fillna(0).astype(int).tolist()
    b = sc['POINTS_B'].ffill().fillna(0).astype(int).tolist()
    fa, fb = a[-1], b[-1]
    if fa == fb or min(fa, fb) < MIN_FINAL:
        return None

    a_up = pd.Series([a[0]] + [a[i] - a[i - 1] for i in range(1, len(a))]) > 0
    b_up = pd.Series([b[0]] + [b[i] - b[i - 1] for i in range(1, len(b))]) > 0

    first = g.iloc[0]
    phase = first.get('Phase')
    return CleanGame(
        season=int(first['Season']),
        phase=None if pd.isna(phase) else str(phase).strip(),
        round=int_or_none(first.get('Round')),
        gamecode=int(first['Gamecode']),
        rows=g.reset_index(drop=True),
        sc=sc,
        a=a, b=b,
        periods=sc['PERIOD'].fillna(0).astype(int).tolist(),
        clocks=sc['MARKERTIME'].tolist(),
        final_a=fa, final_b=fb, a_won=fa > fb,
        code_a=mode_value(sc.loc[a_up, 'CODETEAM']), name_a=mode_value(sc.loc[a_up, 'TEAM']),
        code_b=mode_value(sc.loc[b_up, 'CODETEAM']), name_b=mode_value(sc.loc[b_up, 'TEAM']),
        ot=bool(g['PERIOD'].max() > LAST_REGULATION_PERIOD),
    )


def iter_games(seasons=ALL_SEASONS, cache_dir=CACHE_DIR):
    """Yield a CleanGame for every usable game in data_cache/pbp_{season}.csv."""
    for s in seasons:
        path = os.path.join(cache_dir, f'pbp_{s}.csv')
        if not os.path.exists(path):
            print(f'  [WARN] {path} missing, skipping {season_label(s)}')
            continue
        df = pd.read_csv(path, low_memory=False)
        for _, g in df.groupby('Gamecode', sort=False):
            cg = clean_game(g)
            if cg is not None:
                yield cg


def rank_by(records, key, limit=TOP_N):
    """Top `limit` records with key > 0 (ties: newest first), each with rank and tied flag."""
    rows = sorted((r for r in records if r[key] > 0),
                  key=lambda r: (-r[key], -r['season'], -r['gamecode']))
    counts = Counter(r[key] for r in rows)   # before the cut, so cutoff ties count
    out, rank = [], 0
    for i, r in enumerate(rows[:limit]):
        if i == 0 or r[key] != rows[i - 1][key]:
            rank = i + 1
        out.append({'rank': rank, 'tied': counts[r[key]] > 1, **r})
    return out


def finish_rows(rows, replay_dir=REPLAY_DIR):
    """Add season_label and has_replay to each row (in place) and return them."""
    for r in rows:
        r['season_label'] = season_label(r['season'])
        r['has_replay'] = os.path.exists(
            os.path.join(replay_dir, str(r['season']), f"{r['gamecode']}.json"))
    return rows


def season_span(records):
    seasons = sorted({r['season'] for r in records})
    return [seasons[0], seasons[-1]] if seasons else []


def keep_generated_date(old, new, content_keys):
    """Reuse the old `generated` date when nothing but the date would change."""
    if old and all(old.get(k) == new.get(k) for k in content_keys):
        new['generated'] = old['generated']
    return new


def write_json_if_changed(path, out, content_keys):
    """Write `out` to `path`, keeping the old generated date if the content is unchanged."""
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                keep_generated_date(json.load(f), out, content_keys)
        except (OSError, ValueError, KeyError):
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pbp_games.py -q`
Expected: `8 passed`, no warnings.

- [ ] **Step 7: Rewrite `calculate_comebacks.py` on top of `pbp_games`**

Replace the whole file with:

```python
"""
Biggest Comebacks: the largest deficits overcome by the eventual winner.

analyze_clean() takes a pbp_games.CleanGame and returns the winner's worst
confirmed deficit, overall and in Q4/OT only. build_output() ranks three
lists for docs/data/current/comebacks.json: overall, fourth_quarter and
postseason (Playoffs, Play-In, Final Four).
"""
import os
from datetime import date

import pandas as pd

from pbp_games import (GLITCH_TOL, LAST_REGULATION_PERIOD, REPLAY_DIR, TOP_N, clean_game,
                       finish_rows, iter_games, rank_by, season_span, write_json_if_changed)
from season_config import CURRENT_SEASON

OUT_PATH = os.path.join('docs', 'data', 'current', 'comebacks.json')
POSTSEASON = {'PO', 'PI', 'FF'}
NO_DEFICIT = {'deficit': 0, 'trailing': None, 'quarter': None, 'clock': None}
CONTENT_KEYS = ('overall', 'fourth_quarter', 'postseason', 'games_scanned', 'current_season')


def _confirmed_margins(margins):
    """Zero out margins no neighbouring play agrees with (single-row score typos)."""
    out = []
    for i, m in enumerate(margins):
        nbrs = margins[max(i - 1, 0):i] + margins[i + 1:i + 2]
        out.append(m if any(abs(m - x) <= GLITCH_TOL for x in nbrs) else 0)
    return out


def analyze_game(g):
    """One game's raw PBP rows -> comeback record, or None if the game is unusable."""
    cg = clean_game(g)
    return None if cg is None else analyze_clean(cg)


def analyze_clean(cg):
    """CleanGame -> comeback record (worst confirmed deficit overall and in Q4/OT)."""
    w_pts, l_pts = (cg.a, cg.b) if cg.a_won else (cg.b, cg.a)
    conf = _confirmed_margins([w - l for w, l in zip(w_pts, l_pts)])

    def worst(indices):
        if not indices:
            return dict(NO_DEFICIT)
        i = min(indices, key=lambda j: (conf[j], j))
        if conf[i] >= 0:
            return dict(NO_DEFICIT)
        clk = cg.clocks[i]
        return {'deficit': -conf[i], 'trailing': f'{w_pts[i]}-{l_pts[i]}',
                'quarter': cg.periods[i], 'clock': None if pd.isna(clk) else str(clk)}

    return {
        'season': cg.season,
        'phase': cg.phase,
        'round': cg.round,
        'gamecode': cg.gamecode,
        'winner': cg.code_a if cg.a_won else cg.code_b,
        'winner_name': cg.name_a if cg.a_won else cg.name_b,
        'loser': cg.code_b if cg.a_won else cg.code_a,
        'loser_name': cg.name_b if cg.a_won else cg.name_a,
        'home': cg.a_won,
        **worst(list(range(len(conf)))),
        'q4': worst([i for i, p in enumerate(cg.periods) if p >= LAST_REGULATION_PERIOD]),
        'final': f'{max(cg.final_a, cg.final_b)}-{min(cg.final_a, cg.final_b)}',
        'ot': cg.ot,
    }


def rank_entries(records, limit=TOP_N):
    """Top `limit` by deficit (ties: newest first), each with rank and tied flag."""
    return rank_by(records, 'deficit', limit)


def _without_q4(r):
    return {k: v for k, v in r.items() if k != 'q4'}


def _with_q4(r):
    return {**_without_q4(r), **r['q4']}


def build_output(records, current_season, replay_dir=REPLAY_DIR, generated=None):
    return {
        'generated': generated or date.today().isoformat(),
        'seasons': season_span(records),
        'current_season': current_season,
        'games_scanned': len(records),
        'overall': finish_rows(rank_entries([_without_q4(r) for r in records]), replay_dir),
        'fourth_quarter': finish_rows(rank_entries([_with_q4(r) for r in records]), replay_dir),
        'postseason': finish_rows(rank_entries(
            [_without_q4(r) for r in records if r['phase'] in POSTSEASON]), replay_dir),
    }


def main():
    out = build_output([analyze_clean(cg) for cg in iter_games()], CURRENT_SEASON)
    write_json_if_changed(OUT_PATH, out, CONTENT_KEYS)
    print(f"Comebacks: {out['games_scanned']} games scanned -> {OUT_PATH}")
    if out['overall']:
        top = out['overall'][0]
        print(f"  Biggest: {top['winner']} over {top['loser']} "
              f"({top['season_label']}) from {top['deficit']} down")


if __name__ == '__main__':
    main()
```

(`main()` here is temporary. Task 4 removes it once `calculate_game_records.py` exists.)

- [ ] **Step 8: Point `tests/test_comebacks.py` at the shared fixtures and helper**

In `tests/test_comebacks.py`:
1. Delete the local `game(...)` function and the `BASIC = [...]` block (with its comment). After `import calculate_comebacks as cb`, add:
   ```python
   import pbp_games as pg
   from tests.pbp_fixtures import BASIC, game
   ```
2. In `test_keep_generated_date_only_when_content_unchanged`, change the two `cb.keep_generated_date(old, same)` / `cb.keep_generated_date(old, diff)` calls to `pg.keep_generated_date(old, same, cb.CONTENT_KEYS)` / `pg.keep_generated_date(old, diff, cb.CONTENT_KEYS)`.

Leave every other test exactly as it is.

- [ ] **Step 9: Run all the comeback and pbp_games tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_comebacks.py tests/test_pbp_games.py -q`
Expected: `26 passed` (18 + 8), no warnings.

- [ ] **Step 10: Byte-identical check on real data**

```bash
.venv/Scripts/python.exe calculate_comebacks.py
cmp docs/data/current/comebacks.json "$SP/comebacks.before.json" && echo IDENTICAL
git status --short docs/data/current/comebacks.json
```
Expected: `IDENTICAL`, and `git status` shows no change to the file. If the files differ, the refactor changed behaviour: fix the code, not the expectation.

- [ ] **Step 11: Full suite and commit**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q` (all pass, no warnings).

```bash
git add pbp_games.py calculate_comebacks.py tests/pbp_fixtures.py tests/test_pbp_games.py tests/test_comebacks.py
git commit -m "refactor: shared pbp_games cleaner; comebacks becomes an analyzer

Co-Authored-By: <your model> <noreply@anthropic.com>"
```

---

### Task 2: `game_highs.py`, single-game player lines

**Files:**
- Create: `game_highs.py`, `tests/test_game_highs.py`

**Interfaces:**
- Consumes: `pbp_games.CleanGame`, `clean_game`, `rank_by`, `finish_rows`, `season_span`, `mode_value`, `REPLAY_DIR`; `tests.pbp_fixtures.build/ev/filler`.
- Produces:
  - `game_highs.analyze_clean(cg) -> list[dict]`. Each line has the keys:
    - `season, phase, round, gamecode`
    - `player, player_name, team, opp, home, won, final, ot`
    - `line: {points, rebounds, assists, threes, pir}`
  - `game_highs.build_output(lines, current_season, games_scanned, replay_dir=REPLAY_DIR, generated=None) -> dict` with the keys:
    - `generated, seasons, current_season, games_scanned`
    - one list per stat, `points, rebounds, assists, threes, pir`, whose entries are the line fields plus `value, rank, tied, season_label, has_replay`
  - Constants: `game_highs.OUT_PATH`, `game_highs.CONTENT_KEYS`, `game_highs.STATS`.

- [ ] **Step 1: Write the failing tests in `tests/test_game_highs.py`**

```python
"""Tests for game_highs.py (single-game player lines from play-by-play)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import game_highs as gh
import pbp_games as pg
from tests.pbp_fixtures import build, ev, filler

P1, P2 = 'P000001', 'P000002'


def _player_game():
    """HOM beats AWY 55-48. P1 (HOM) has a full line built from every play type."""
    def p1(pt, n=1):
        return ev('A', pt, 4, player=P1, name='ONE, A', n=n)
    events = (filler(20, 20, period=2)                       # 40-40, anonymous
              + p1('3FGM', 3) + p1('DUNK') + p1('LAYUPMD') + p1('FTM', 2)   # +15 -> 55
              + p1('FTA') + p1('2FGAB') + p1('LAYUPATT') + p1('3FGA')       # 4 misses
              + p1('D', 2) + p1('O')
              + p1('AS ', 4)                                 # trailing space, as in the feed
              + p1('ST') + p1('FV') + p1('RV', 2)
              + p1('TO', 2) + p1('AG') + p1('CM') + p1('OF')
              + ev('B', '2FGM', 4, player=P2, name='TWO, B', n=4)          # AWY -> 48
              + ev('B', 'D', 4))                             # team rebound: no player
    return pg.clean_game(build(events))


def _lines():
    return {l['player']: l for l in gh.analyze_clean(_player_game())}


def test_counting_rules_including_old_play_types():
    # PIR = 15 pts + 11 (D2 O1 AS4 ST1 FV1 RV2) - 4 misses - 3 (TO2 AG1) - 2 fouls = 17
    assert _lines()['000001']['line'] == \
        {'points': 15, 'rebounds': 3, 'assists': 4, 'threes': 3, 'pir': 17}


def test_team_opponent_home_won_and_final():
    lines = _lines()
    p1, p2 = lines['000001'], lines['000002']
    assert (p1['team'], p1['opp'], p1['home'], p1['won'], p1['final']) == \
        ('HOM', 'AWY', True, True, '55-48')
    assert (p2['team'], p2['opp'], p2['home'], p2['won'], p2['final']) == \
        ('AWY', 'HOM', False, False, '48-55')
    assert p2['line'] == {'points': 8, 'rebounds': 0, 'assists': 0, 'threes': 0, 'pir': 8}
    assert (p1['player_name'], p1['season'], p1['gamecode'], p1['phase'], p1['ot']) == \
        ('ONE, A', 2015, 7, 'RS', False)


def test_events_without_a_player_are_not_lines():
    assert set(_lines()) == {'000001', '000002'}


def _line(player, season, gamecode, points, rebounds=0, assists=0, threes=0, pir=0):
    return {'season': season, 'phase': 'RS', 'round': 3, 'gamecode': gamecode,
            'player': player, 'player_name': player, 'team': 'HOM', 'opp': 'AWY',
            'home': True, 'won': True, 'final': '80-70', 'ot': False,
            'line': {'points': points, 'rebounds': rebounds, 'assists': assists,
                     'threes': threes, 'pir': pir}}


def test_build_output_ranks_each_stat(tmp_path):
    lines = [_line('a', 2015, 1, 40, rebounds=5, pir=30),
             _line('b', 2016, 2, 40, rebounds=12, threes=8, pir=41),
             _line('c', 2017, 3, 20, assists=15, pir=25)]
    out = gh.build_output(lines, current_season=2017, games_scanned=3,
                          replay_dir=str(tmp_path), generated='2000-01-01')
    assert (out['generated'], out['seasons'], out['current_season'], out['games_scanned']) == \
        ('2000-01-01', [2015, 2017], 2017, 3)
    assert [(r['player'], r['value'], r['rank'], r['tied']) for r in out['points']] == \
        [('b', 40, 1, True), ('a', 40, 1, True), ('c', 20, 3, False)]
    assert [r['player'] for r in out['rebounds']] == ['b', 'a']
    assert [r['player'] for r in out['assists']] == ['c']
    assert [r['player'] for r in out['threes']] == ['b']
    assert [r['player'] for r in out['pir']] == ['b', 'a', 'c']
    top = out['points'][0]
    assert (top['season_label'], top['has_replay'], top['line']['rebounds']) == ('2016-17', False, 12)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_game_highs.py -q`
Expected: `ModuleNotFoundError: No module named 'game_highs'`.

- [ ] **Step 3: Create `game_highs.py`**

```python
"""
Game Highs: single-game player records rebuilt from play-by-play.

analyze_clean() turns a pbp_games.CleanGame into one stat line per player
(points, rebounds, assists, threes, PIR). build_output() ranks the top
lines per stat for docs/data/current/game_highs.json. Older logs record
made dunks/layups and blocked or missed layup attempts as separate play
types; they are counted like the modern ones.
"""
import os
from datetime import date

from pbp_games import REPLAY_DIR, finish_rows, mode_value, rank_by, season_span

OUT_PATH = os.path.join('docs', 'data', 'current', 'game_highs.json')
STATS = ('points', 'rebounds', 'assists', 'threes', 'pir')
CONTENT_KEYS = STATS + ('games_scanned', 'current_season')

SHOT_POINTS = {'2FGM': 2, 'DUNK': 2, 'LAYUPMD': 2, '3FGM': 3, 'FTM': 1}
REBOUNDS = {'D', 'O'}
PIR_PLUS = {'D', 'O', 'AS', 'ST', 'FV', 'RV'}          # rebounds, assists, steals, blocks, fouls drawn
MISSES = {'2FGA', '3FGA', 'FTA', '2FGAB', '3FGAB', 'LAYUPATT'}
FOULS = {'CM', 'OF', 'CMT', 'CMU', 'CMD', 'CMTI', 'C', 'B'}
PIR_MINUS = MISSES | FOULS | {'TO', 'AG'}             # + turnovers, shots blocked


def stat_line(play_types):
    """Play-type codes for one player in one game -> stat line."""
    points = sum(SHOT_POINTS.get(t, 0) for t in play_types)
    return {
        'points': points,
        'rebounds': sum(t in REBOUNDS for t in play_types),
        'assists': sum(t == 'AS' for t in play_types),
        'threes': sum(t == '3FGM' for t in play_types),
        'pir': (points + sum(t in PIR_PLUS for t in play_types)
                - sum(t in PIR_MINUS for t in play_types)),
    }


def analyze_clean(cg):
    """CleanGame -> one line per player with at least one event in the game."""
    rows = cg.rows[cg.rows['PID'].notna()]
    lines = []
    for pid, pr in rows.groupby('PID', sort=False):
        team = mode_value(pr['CODETEAM'])
        if team == cg.code_a:
            home, opp = True, cg.code_b
        elif team == cg.code_b:
            home, opp = False, cg.code_a
        else:
            continue
        team_pts, opp_pts = (cg.final_a, cg.final_b) if home else (cg.final_b, cg.final_a)
        lines.append({
            'season': cg.season, 'phase': cg.phase, 'round': cg.round, 'gamecode': cg.gamecode,
            'player': pid,
            'player_name': mode_value(pr['PLAYER']) if 'PLAYER' in pr else None,
            'team': team, 'opp': opp, 'home': home, 'won': home == cg.a_won,
            'final': f'{team_pts}-{opp_pts}', 'ot': cg.ot,
            'line': stat_line(pr['PT'].tolist()),
        })
    return lines


def build_output(lines, current_season, games_scanned, replay_dir=REPLAY_DIR, generated=None):
    out = {
        'generated': generated or date.today().isoformat(),
        'seasons': season_span(lines),
        'current_season': current_season,
        'games_scanned': games_scanned,
    }
    for stat in STATS:
        flat = [{**l, 'value': l['line'][stat]} for l in lines]
        out[stat] = finish_rows(rank_by(flat, 'value'), replay_dir)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_game_highs.py -q`
Expected: `4 passed`, no warnings.

- [ ] **Step 5: Real-data check against the official box scores**

```bash
.venv/Scripts/python.exe -c "
import json
from pbp_games import iter_games
import game_highs as gh
for s in (2024, 2025):
    pbp, games = {}, set()
    for cg in iter_games([s]):
        games.add(cg.gamecode)
        for l in gh.analyze_clean(cg):
            pbp[(cg.gamecode, l['player'].lstrip('0'))] = l['line']
    off = json.load(open(f'mvp_all_game_stats_{s}.json', encoding='utf-8'))
    n, skipped = 0, 0
    ok = dict.fromkeys(gh.STATS, 0)
    for g in off:
        if g['Gamecode'] not in games:
            skipped += 1
            continue
        for side in ('local', 'road'):
            for p in g.get(f'{side}.players', []):
                st = p['stats']
                key = (g['Gamecode'], p['player']['person']['code'].lstrip('0'))
                want = {'points': st['points'], 'rebounds': st['totalRebounds'],
                        'assists': st['assistances'], 'threes': st['fieldGoalsMade3'],
                        'pir': st['valuation']}
                if key not in pbp and not any(want.values()):
                    continue
                n += 1
                got = pbp.get(key, {})
                for k in ok:
                    ok[k] += got.get(k, 0) == want[k]
    rates = {k: round(ok[k] / n, 5) for k in ok}
    print(s, 'player-games', n, 'official games not in pbp', skipped, rates)
    assert all(rates[k] >= 0.999 for k in ('points', 'rebounds', 'assists', 'threes')), rates
    assert rates['pir'] >= 0.995, rates
print('OK')
"
```
Expected: two lines with rates ≥ 0.999 (PIR ≥ 0.995), then `OK`.

- [ ] **Step 6: Full suite and commit**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q` (all pass, no warnings).

```bash
git add game_highs.py tests/test_game_highs.py
git commit -m "feat: single-game player highs rebuilt from play-by-play

Co-Authored-By: <your model> <noreply@anthropic.com>"
```

---

### Task 3: `game_winners.py`, late go-ahead-for-good field goals

**Files:**
- Create: `game_winners.py`, `tests/test_game_winners.py`

**Interfaces:**
- Consumes: `pbp_games.CleanGame`, `clean_game`, `finish_rows`, `season_span`, `LAST_REGULATION_PERIOD`, `REPLAY_DIR`, `TOP_N`; `season_config.season_label`; `tests.pbp_fixtures.build/ev/filler`.
- Produces:
  - `game_winners.analyze_clean(cg) -> dict | None`. The record has the keys:
    - `season, phase, round, gamecode`
    - `player, player_name, team, opp, home`
    - `quarter, clock, seconds_left, points, shot`
    - `before, after, final, ot, buzzer`
  - `game_winners.leaders(records, limit=TOP_N) -> list[dict]`
  - `game_winners.build_output(records, current_season, games_scanned, replay_dir=REPLAY_DIR, generated=None) -> dict` with the keys `generated, seasons, current_season, games_scanned, window_seconds, all, buzzer_beaters, leaders`
  - Constants: `game_winners.OUT_PATH`, `CONTENT_KEYS`, `WINDOW_SECONDS = 10`, `BUZZER_SECONDS = 1`.

- [ ] **Step 1: Write the failing tests in `tests/test_game_winners.py`**

```python
"""Tests for game_winners.py (late go-ahead-for-good field goals)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import game_winners as gw
import pbp_games as pg
from tests.pbp_fixtures import build, ev, filler

SHOOTER = 'P000009'


def _shot(pt='3FGM', clock='00:01', period=4, before=(), after=()):
    """50-50 in Q4 (anonymous filler), then AWY's shot, plus optional extra events."""
    events = (filler(25, 25, period=4) + list(before)
              + ev('B', pt, period, clock, player=SHOOTER, name='SHOOTER, S') + list(after))
    return pg.clean_game(build(events))


def test_buzzer_three_that_takes_the_lead_for_good():
    r = gw.analyze_clean(_shot())
    assert (r['player'], r['player_name'], r['team'], r['opp'], r['home']) == \
        ('000009', 'SHOOTER, S', 'AWY', 'HOM', False)
    assert (r['quarter'], r['clock'], r['seconds_left'], r['points'], r['shot']) == \
        (4, '00:01', 1, 3, '3PT')
    assert (r['before'], r['after'], r['final'], r['ot'], r['buzzer']) == \
        ('50-50', '53-50', '53-50', False, True)
    assert (r['season'], r['phase'], r['round'], r['gamecode']) == (2015, 'RS', 3, 7)


def test_dunk_inside_window_is_not_a_buzzer_beater():
    r = gw.analyze_clean(_shot(pt='DUNK', clock='00:05'))
    assert (r['shot'], r['points'], r['after'], r['buzzer']) == ('Dunk', 2, '52-50', False)


def test_go_ahead_outside_window_is_skipped():
    assert gw.analyze_clean(_shot(clock='00:15')) is None


def test_go_ahead_free_throw_is_skipped():
    assert gw.analyze_clean(_shot(pt='FTM', clock='00:02')) is None


def test_unparseable_clock_is_skipped():
    assert gw.analyze_clean(_shot(clock='ND')) is None
    assert gw.analyze_clean(_shot(clock=float('nan'))) is None


def test_lead_tied_late_then_won_in_overtime():
    events = (filler(25, 25, period=4)
              + ev('B', '2FGM', 4, '00:05', player=SHOOTER, name='SHOOTER, S')   # 50-52
              + ev('A', '2FGM', 4, '00:01')                                       # 52-52
              + ev('B', '3FGM', 5, '00:03', player='P000010', name='OT, HERO'))    # 52-55
    r = gw.analyze_clean(pg.clean_game(build(events)))
    assert (r['player'], r['quarter'], r['ot'], r['before'], r['after']) == \
        ('000010', 5, True, '52-52', '55-52')
    late_ot = events[:-1] + ev('B', '3FGM', 5, '02:00', player='P000010', name='OT, HERO')
    assert gw.analyze_clean(pg.clean_game(build(late_ot))) is None


def test_third_quarter_go_ahead_is_skipped():
    events = (filler(25, 25, period=3)
              + ev('B', '2FGM', 3, '00:01', player=SHOOTER, name='SHOOTER, S')    # 50-52
              + ev('B', '2FGM', 4, '05:00') + ev('A', '2FGM', 4, '04:00'))         # 52-54
    assert gw.analyze_clean(pg.clean_game(build(events))) is None


def test_score_jump_not_matching_shot_value_is_skipped():
    df = build(filler(25, 25, period=4)
               + ev('B', '3FGM', 4, '00:01', player=SHOOTER, name='SHOOTER, S'))
    df.loc[df.index[-1], 'POINTS_B'] = 55          # a 3-pointer cannot add 5
    assert gw.analyze_clean(pg.clean_game(df)) is None


def test_wire_to_wire_winner_has_no_game_winner():
    events = ev('A', '2FGM', 4, n=25) + ev('B', '2FGM', 4, n=24)     # HOM leads throughout
    assert gw.analyze_clean(pg.clean_game(build(events))) is None


def _gw(player, season, gamecode, buzzer=False):
    return {'season': season, 'phase': 'RS', 'round': 3, 'gamecode': gamecode,
            'player': player, 'player_name': player, 'team': 'AWY', 'opp': 'HOM',
            'home': False, 'quarter': 4, 'clock': '00:01' if buzzer else '00:08',
            'seconds_left': 1 if buzzer else 8, 'points': 3, 'shot': '3PT',
            'before': '50-50', 'after': '53-50', 'final': '53-50', 'ot': False,
            'buzzer': buzzer}


def test_build_output_lists_and_leaders(tmp_path):
    recs = [_gw('a', 2015, 4), _gw('b', 2016, 9, buzzer=True), _gw('a', 2017, 2, buzzer=True),
            _gw('c', 2017, 5), _gw(None, 2014, 1)]
    out = gw.build_output(recs, current_season=2017, games_scanned=100,
                          replay_dir=str(tmp_path), generated='2000-01-01')
    assert (out['generated'], out['games_scanned'], out['window_seconds'], out['seasons']) == \
        ('2000-01-01', 100, 10, [2014, 2017])
    assert [(r['season'], r['gamecode']) for r in out['all']] == \
        [(2017, 5), (2017, 2), (2016, 9), (2015, 4), (2014, 1)]
    assert [(r['season'], r['gamecode']) for r in out['buzzer_beaters']] == [(2017, 2), (2016, 9)]
    assert (out['all'][0]['season_label'], out['all'][0]['has_replay']) == ('2017-18', False)
    assert [(l['player'], l['count'], l['buzzer_count'], l['rank'], l['tied'],
             l['last_season_label']) for l in out['leaders']] == \
        [('a', 2, 1, 1, False, '2017-18'), ('b', 1, 1, 2, True, '2016-17'),
         ('c', 1, 0, 2, True, '2017-18')]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_game_winners.py -q`
Expected: `ModuleNotFoundError: No module named 'game_winners'`.

- [ ] **Step 3: Create `game_winners.py`**

```python
"""
Game-Winners: made field goals in the last seconds of the 4th quarter or
overtime that gave the eventual winner the lead for good.

analyze_clean() finds the play after which the winner never trailed or
was tied again, and keeps it if it is a made field goal by the winner
inside WINDOW_SECONDS of a 4th-quarter/OT clock whose score jump matches
the shot value. build_output() writes every game-winner (newest first),
the buzzer-beaters and a career leaderboard to
docs/data/current/game_winners.json.
"""
import os
from collections import Counter
from datetime import date

import pandas as pd

from pbp_games import (LAST_REGULATION_PERIOD, REPLAY_DIR, TOP_N, finish_rows,
                       season_span)
from season_config import season_label

OUT_PATH = os.path.join('docs', 'data', 'current', 'game_winners.json')
CONTENT_KEYS = ('all', 'leaders', 'games_scanned', 'current_season')
WINDOW_SECONDS = 10
BUZZER_SECONDS = 1
SHOT_LABEL = {'3FGM': '3PT', '2FGM': '2PT', 'DUNK': 'Dunk', 'LAYUPMD': 'Layup'}


def _seconds(clock):
    """'mm:ss' -> seconds left, or None if the clock is missing/unparseable."""
    try:
        mm, ss = str(clock).split(':')
        return int(mm) * 60 + int(ss)
    except ValueError:
        return None


def analyze_clean(cg):
    """CleanGame -> game-winner record, or None if the game had none."""
    w, l = (cg.a, cg.b) if cg.a_won else (cg.b, cg.a)
    not_ahead = [i for i in range(len(w)) if w[i] - l[i] <= 0]
    if not not_ahead:
        return None
    j = not_ahead[-1] + 1
    if j >= len(w):
        return None
    row = cg.sc.iloc[j]
    pt = row['PT']
    winner, loser = (cg.code_a, cg.code_b) if cg.a_won else (cg.code_b, cg.code_a)
    if pt not in SHOT_LABEL or str(row['CODETEAM']).strip() != winner:
        return None
    if cg.periods[j] < LAST_REGULATION_PERIOD:
        return None
    secs = _seconds(cg.clocks[j])
    if secs is None or secs > WINDOW_SECONDS:
        return None
    value = 3 if pt == '3FGM' else 2
    if w[j] - w[j - 1] != value or l[j] != l[j - 1]:
        return None
    name = row['PLAYER'] if 'PLAYER' in row.index else None
    pid = row['PID']
    return {
        'season': cg.season, 'phase': cg.phase, 'round': cg.round, 'gamecode': cg.gamecode,
        'player': None if pd.isna(pid) else pid,   # never NaN: it must serialise as JSON null
        'player_name': None if pd.isna(name) else str(name).strip(),
        'team': winner, 'opp': loser, 'home': cg.a_won,
        'quarter': cg.periods[j], 'clock': str(cg.clocks[j]), 'seconds_left': secs,
        'points': value, 'shot': SHOT_LABEL[pt],
        'before': f'{w[j - 1]}-{l[j - 1]}', 'after': f'{w[j]}-{l[j]}',
        'final': f'{w[-1]}-{l[-1]}', 'ot': cg.ot,
        'buzzer': secs <= BUZZER_SECONDS,
    }


def _newest_first(records):
    return sorted(records, key=lambda r: (-r['season'], -r['gamecode']))


def leaders(records, limit=TOP_N):
    """Career game-winner counts per player (shooters without an id are skipped)."""
    by_player = {}
    for r in records:
        if r['player'] is None:
            continue
        e = by_player.setdefault(r['player'], {
            'player': r['player'], 'player_name': r['player_name'],
            'count': 0, 'buzzer_count': 0, 'last_season': r['season']})
        e['count'] += 1
        e['buzzer_count'] += int(r['buzzer'])
        e['last_season'] = max(e['last_season'], r['season'])
    rows = sorted(by_player.values(),
                  key=lambda e: (-e['count'], -e['buzzer_count'], -e['last_season']))
    counts = Counter(e['count'] for e in rows)
    out, rank = [], 0
    for i, e in enumerate(rows[:limit]):
        if i == 0 or e['count'] != rows[i - 1]['count']:
            rank = i + 1
        out.append({'rank': rank, 'tied': counts[e['count']] > 1, **e,
                    'last_season_label': season_label(e['last_season'])})
    return out


def build_output(records, current_season, games_scanned, replay_dir=REPLAY_DIR, generated=None):
    all_rows = finish_rows([dict(r) for r in _newest_first(records)], replay_dir)
    return {
        'generated': generated or date.today().isoformat(),
        'seasons': season_span(records),
        'current_season': current_season,
        'games_scanned': games_scanned,
        'window_seconds': WINDOW_SECONDS,
        'all': all_rows,
        'buzzer_beaters': [r for r in all_rows if r['buzzer']],
        'leaders': leaders(records),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_game_winners.py -q`
Expected: `10 passed`, no warnings.

- [ ] **Step 5: Real-data spot check on the current season**

```bash
.venv/Scripts/python.exe -c "
from pbp_games import iter_games
from season_config import CURRENT_SEASON
import game_winners as gw
recs = [r for r in (gw.analyze_clean(cg) for cg in iter_games([CURRENT_SEASON])) if r]
print([(r['gamecode'], r['player_name'], r['shot'], r['quarter'], r['clock'], r['buzzer']) for r in recs])
r = [r for r in recs if r['gamecode'] == 44][0]
assert (r['player_name'], r['shot'], r['quarter'], r['buzzer']) == ('ROBINSON, JUSTIN', '3PT', 4, True), r
print('OK')
"
```
Expected: the list printed, then `OK`.

- [ ] **Step 6: Full suite and commit**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q` (all pass, no warnings).

```bash
git add game_winners.py tests/test_game_winners.py
git commit -m "feat: game-winners (late go-ahead-for-good field goals)

Co-Authored-By: <your model> <noreply@anthropic.com>"
```

---

### Task 4: `calculate_game_records.py`, pipeline wiring and real data

**Files:**
- Create: `calculate_game_records.py`, `tests/test_game_records.py`
- Modify: `calculate_comebacks.py` (remove `main()` and the `__main__` block, plus imports that become unused), `refresh_all.py:178-181`, `.github/workflows/wp_replay_update.yml:40-43`, `tests/test_no_hardcoded_season.py:12-14` and `:32-33`
- Generated: `docs/data/current/game_highs.json`, `docs/data/current/game_winners.json` (`comebacks.json` must not change)

**Interfaces:**
- Consumes: `pbp_games.iter_games`, `write_json_if_changed`; `calculate_comebacks.analyze_clean/build_output/OUT_PATH/CONTENT_KEYS`; `game_highs.analyze_clean/build_output/OUT_PATH/CONTENT_KEYS`; `game_winners.analyze_clean/build_output/OUT_PATH/CONTENT_KEYS`.
- Produces:
  - `calculate_game_records.collect(games) -> (comebacks: list, lines: list, winners: list)`
  - `main()`
  - The three JSON files, whose schemas Task 5 consumes:
    - **game_highs.json:** keys `generated, seasons, current_season, games_scanned, points, rebounds, assists, threes, pir`. Each entry has `rank, tied, value, season, phase, round, gamecode, player, player_name, team, opp, home, won, final, ot, line{points,rebounds,assists,threes,pir}, season_label, has_replay`.
    - **game_winners.json:** keys `generated, seasons, current_season, games_scanned, window_seconds, all, buzzer_beaters, leaders`.
      - Shot entries have `season, phase, round, gamecode, player, player_name, team, opp, home, quarter, clock, seconds_left, points, shot, before, after, final, ot, buzzer, season_label, has_replay`.
      - Leader entries have `rank, tied, player, player_name, count, buzzer_count, last_season, last_season_label`.

- [ ] **Step 1: Write the failing test in `tests/test_game_records.py`**

```python
"""Tests for calculate_game_records.py (one pass, every analyzer)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import calculate_game_records as gr
import pbp_games as pg
from tests.pbp_fixtures import BASIC, build, ev, filler, game


def test_collect_runs_every_analyzer_once_per_game():
    g1 = pg.clean_game(game(BASIC))          # no player ids; ends with AWY's 50-50 tie-breaker at 0:10
    g2 = pg.clean_game(build(filler(25, 25, period=4)
                             + ev('B', '3FGM', 4, '00:01', player='P000009', name='SHOOTER, S'),
                             gamecode=8))
    comebacks, lines, winners = gr.collect([g1, g2])
    assert [c['gamecode'] for c in comebacks] == [7, 8]
    assert [l['player'] for l in lines] == ['000009']
    assert [w['gamecode'] for w in winners] == [7, 8]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_game_records.py -q`
Expected: `ModuleNotFoundError: No module named 'calculate_game_records'`.

- [ ] **Step 3: Create `calculate_game_records.py`**

```python
"""
Game Records engine: one pass over every cached play-by-play game.

Each usable game (pbp_games.iter_games) goes through the comebacks, game
highs and game-winners analyzers, and the three record boards are written
to docs/data/current/: comebacks.json, game_highs.json, game_winners.json.
"""
import calculate_comebacks as comebacks
import game_highs
import game_winners
from pbp_games import iter_games, write_json_if_changed
from season_config import CURRENT_SEASON


def collect(games):
    """Run every analyzer on each CleanGame -> (comebacks, highs lines, game-winners)."""
    cbs, lines, winners = [], [], []
    for cg in games:
        cbs.append(comebacks.analyze_clean(cg))
        lines.extend(game_highs.analyze_clean(cg))
        r = game_winners.analyze_clean(cg)
        if r:
            winners.append(r)
    return cbs, lines, winners


def main():
    cbs, lines, winners = collect(iter_games())
    n = len(cbs)
    outputs = [
        (comebacks.OUT_PATH, comebacks.build_output(cbs, CURRENT_SEASON), comebacks.CONTENT_KEYS),
        (game_highs.OUT_PATH, game_highs.build_output(lines, CURRENT_SEASON, n),
         game_highs.CONTENT_KEYS),
        (game_winners.OUT_PATH, game_winners.build_output(winners, CURRENT_SEASON, n),
         game_winners.CONTENT_KEYS),
    ]
    for path, out, keys in outputs:
        write_json_if_changed(path, out, keys)
    print(f'Game records: {n} games scanned')
    highs, gws = outputs[1][1], outputs[2][1]
    if highs['points']:
        top = highs['points'][0]
        print(f"  Top scoring game: {top['player_name']} {top['value']} "
              f"({top['team']} vs {top['opp']}, {top['season_label']})")
    print(f"  Game-winners: {len(gws['all'])} ({len(gws['buzzer_beaters'])} buzzer-beaters)")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_game_records.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Remove the temporary entry point from `calculate_comebacks.py`**

Delete `def main(): ...` and the `if __name__ == '__main__': main()` block. Remove `iter_games`, `write_json_if_changed` and `CURRENT_SEASON` from the imports, since they are now unused. Keep `OUT_PATH` and `CONTENT_KEYS`; the engine uses them.

- [ ] **Step 6: Rewire the pipeline**

In `refresh_all.py`, replace

```python
        results.append(('Biggest Comebacks', run_step(
            'Computing all-time biggest comebacks from play-by-play',
            'calculate_comebacks.py'
        )))
```

with

```python
        results.append(('Game Records', run_step(
            'Computing all-time game records (comebacks, game highs, game-winners)',
            'calculate_game_records.py'
        )))
```

In `.github/workflows/wp_replay_update.yml`, replace

```yaml
    - name: Compute Biggest Comebacks
      continue-on-error: true
      run: |
        python calculate_comebacks.py
```

with

```yaml
    - name: Compute Game Records
      continue-on-error: true
      run: |
        python calculate_game_records.py
```

- [ ] **Step 7: Extend the season-guard test**

In `tests/test_no_hardcoded_season.py`, change the always-scanned set in `_pipeline_scripts()` to:

```python
    names |= {'refresh_all.py', 'fetch_all_seasons.py', 'incremental_fetch.py',
              'preprocess_wp_data.py', 'calculate_gci_historical.py',
              'fetch_lineups.py', 'generate_clutch_data.py',
              'pbp_games.py', 'calculate_comebacks.py', 'game_highs.py', 'game_winners.py'}
```

and the tuple in `test_guarded_scripts_are_scanned()` to:

```python
    for name in ('preprocess_wp_data.py', 'calculate_gci_historical.py',
                 'fetch_lineups.py', 'generate_clutch_data.py', 'fetch_all_seasons.py',
                 'pbp_games.py', 'calculate_comebacks.py', 'game_highs.py',
                 'game_winners.py', 'calculate_game_records.py'):
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_no_hardcoded_season.py -q`
Expected: PASS.

- [ ] **Step 8: Generate the real files and verify**

```bash
SP=C:/Users/klalo/AppData/Local/Temp/claude/c--Users-klalo-PycharmProjects-pythonProject/85a4f455-7e38-4931-9536-a78ced663cf8/scratchpad
cp docs/data/current/comebacks.json "$SP/comebacks.before4.json"
.venv/Scripts/python.exe calculate_game_records.py
cmp docs/data/current/comebacks.json "$SP/comebacks.before4.json" && echo COMEBACKS IDENTICAL
.venv/Scripts/python.exe -c "
import json
h = json.load(open('docs/data/current/game_highs.json', encoding='utf-8'))
w = json.load(open('docs/data/current/game_winners.json', encoding='utf-8'))
c = json.load(open('docs/data/current/comebacks.json', encoding='utf-8'))
assert h['games_scanned'] == w['games_scanned'] == c['games_scanned'], (h['games_scanned'], w['games_scanned'], c['games_scanned'])
for k in ('points', 'rebounds', 'assists', 'threes', 'pir'):
    assert len(h[k]) == 25, k
    print(k, [(r['player_name'], r['value'], r['season_label']) for r in h[k][:3]])
assert 150 <= len(w['all']) <= 220, len(w['all'])
r = [r for r in w['all'] if r['season'] == w['current_season'] and r['gamecode'] == 44][0]
assert (r['player_name'], r['shot'], r['quarter'], r['buzzer']) == ('ROBINSON, JUSTIN', '3PT', 4, True)
print('game-winners', len(w['all']), 'buzzer', len(w['buzzer_beaters']), 'leaders top', [(l['player_name'], l['count']) for l in w['leaders'][:3]])
print('OK')
"
```
Expected: `COMEBACKS IDENTICAL`, the top-3 lines per stat, the game-winner counts, then `OK`. Record the printed output in your report.

- [ ] **Step 9: Full suite and commits (code, then data)**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q` (all pass, no warnings).

```bash
git add calculate_game_records.py tests/test_game_records.py calculate_comebacks.py refresh_all.py .github/workflows/wp_replay_update.yml tests/test_no_hardcoded_season.py
git commit -m "feat: one-pass game records engine wired into refresh and daily workflow

Co-Authored-By: <your model> <noreply@anthropic.com>"
git add docs/data/current/game_highs.json docs/data/current/game_winners.json
git status --short
git commit -m "data: generate game_highs.json and game_winners.json

Co-Authored-By: <your model> <noreply@anthropic.com>"
```
`git status --short` must show nothing else modified. If anything else shows (in particular `comebacks.json`), stop and report it.

---

### Task 5: Game Highs and Game-Winners tabs, and About methodology

**Files:**
- Modify: `docs/records.js` (header constants, `TABS`, the lazy branch of `renderPage`, the tab click handler, and everything from `// ── Comebacks tab` to the end of the file)
- Modify: `docs/records.html` (CSS after the `.cb-new` rule; `<meta name="description">`)
- Modify: `docs/about.html` (All-Time Records section)

**Interfaces:**
- Consumes: the three JSON schemas listed in Task 4's Interfaces, plus `comebacks.json` (unchanged).
- Produces: UI only.

- [ ] **Step 1: Header constants and `TABS` in `docs/records.js`**

Replace the line `const COMEBACKS_URL = 'data/current/comebacks.json';` with:

```js
const LAZY_URLS     = {
    comebacks: 'data/current/comebacks.json',
    highs:     'data/current/game_highs.json',
    winners:   'data/current/game_winners.json',
};
```

Replace the line `let _comebacks   = null; // comebacks.json, loaded on first Comebacks tab click` with:

```js
let _lazy        = {};   // tab key -> JSON (or {error:true}), loaded on first tab click
```

In `TABS`, after `{ key: 'comebacks',  label: 'Comebacks' },` add:

```js
    { key: 'highs',      label: 'Game Highs' },
    { key: 'winners',    label: 'Game-Winners' },
```

- [ ] **Step 2: The lazy branch and click handler in `renderPage()`**

Replace

```js
    if (_activeTab === 'comebacks') {
        content.innerHTML = `<div class="cat-tabs">${tabButtons}</div>${renderComebacks()}`;
    } else {
```

with

```js
    const lazyRender = { comebacks: renderComebacks, highs: renderHighs, winners: renderWinners }[_activeTab];
    if (lazyRender) {
        content.innerHTML = `<div class="cat-tabs">${tabButtons}</div>${lazyRender(_lazy[_activeTab])}`;
    } else {
```

Replace

```js
        btn.addEventListener('click', async () => {
            if (btn.dataset.tab === 'comebacks' && !_comebacks) await loadComebacks();
            _activeTab = btn.dataset.tab;
            renderPage();
        });
```

with

```js
        btn.addEventListener('click', async () => {
            const key = btn.dataset.tab;
            if (LAZY_URLS[key] && !_lazy[key]) _lazy[key] = await loadJson(LAZY_URLS[key]);
            _activeTab = key;
            renderPage();
        });
```

- [ ] **Step 3: Replace everything from `// ── Comebacks tab` to the end of `docs/records.js`**

```js
// ── Lazy-loaded game-record tabs ───────────────────────────────────────────────
async function loadJson(url) {
    try {
        const r = await fetch(url);
        if (!r.ok) throw new Error(r.status);
        return await r.json();
    } catch {
        return { error: true };
    }
}

function errorMsg(what)     { return `<p class="error-msg">Could not load ${what} data. Run the data pipeline first.</p>`; }
function legend(html)       { return `<div class="filter-row"><span class="filter-legend">${html}</span></div>`; }
function sinceLabel(d)      { return d.seasons && d.seasons.length ? seasonLbl(d.seasons[0]) : ''; }
function rankCls(r)         { return r.rank === 1 ? 'rank-1' : r.rank === 2 ? 'rank-2' : r.rank === 3 ? 'rank-3' : ''; }
function rowCls(r, i)       { return [r.rank ? rankCls(r) : '', i >= TOP_INITIAL ? 'hidden' : ''].filter(Boolean).join(' '); }
function rankCell(r)        { return `<td class="${rankCls(r)}">${r.tied ? 'T-' : ''}${r.rank}</td>`; }
function newTag(season, cur){ return season === cur ? '<span class="cb-new">NEW</span>' : ''; }
function emptyRow(cols)     { return `<tr><td colspan="${cols}" class="p-meta">No qualifying games yet</td></tr>`; }

function replayLink(r, label, title) {
    return r.has_replay
        ? `<a href="replay.html?season=${r.season}&game=${r.gamecode}" title="${title} · open replay">${label}</a>`
        : `<span title="${title}">${label}</span>`;
}

function playerLink(r) {
    const name = esc(r.player_name || r.player || '—');
    return r.player ? `<a href="player.html?code=${encodeURIComponent(r.player)}">${name}</a>` : name;
}

function showMoreBtn(n, all) {
    if (n <= TOP_INITIAL) return '';
    return `<button class="show-more-btn">${all ? `Show all ${n}` : `Show top ${Math.min(n, TOP_EXTENDED)}`} ↓</button>`;
}

function cardShell(title, sub, titleCls, tableCls, thead, trows, showMore) {
    return `
    <div class="record-card">
      <div class="record-card-header">
        <span class="rch-title ${titleCls}">${title}</span>
        <span class="rch-sub">${sub}</span>
      </div>
      <table class="lb-table ${tableCls}">
        <thead>${thead}</thead>
        <tbody>${trows}</tbody>
      </table>
      ${showMore}
    </div>`;
}

// ── Comebacks tab ──────────────────────────────────────────────────────────────
function renderComebacks(d) {
    if (d.error) return errorMsg('comeback');
    return legend(`Largest deficit the eventual winner faced &nbsp;·&nbsp; ${d.games_scanned.toLocaleString()} games since ${sinceLabel(d)} &nbsp;·&nbsp; click a game for its replay`) + `
    <div class="records-grid">
      ${renderComebackCard(d.overall,        'Biggest Comebacks',     'Any point in the game',         'comeback', d.current_season)}
      ${renderComebackCard(d.fourth_quarter, '4th-Quarter Comebacks', 'Deficit faced in Q4 or OT',     'q4',       d.current_season)}
      ${renderComebackCard(d.postseason,     'Playoffs & Final Four', 'Playoffs, Play-In, Final Four', 'post',     d.current_season)}
    </div>`;
}

function renderComebackCard(rows, title, sub, titleCls, current) {
    const trows = rows.length ? rows.map((r, i) => {
        const sep  = r.home ? 'vs' : '@';
        const game = replayLink(r, `${r.winner} ${sep} ${r.loser}`, esc(`${r.winner_name} ${sep} ${r.loser_name}`));
        const meta = [r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        return `<tr class="${rowCls(r, i)}">
          ${rankCell(r)}
          <td>
            <span class="p-name">${game}${newTag(r.season, current)}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td class="val-deficit">${r.deficit}
            <span class="p-meta">trailed ${r.trailing} · ${periodLabel(r.quarter)} ${clockLabel(r.clock)}</span>
          </td>
          <td>${r.final}${r.ot ? ' OT' : ''}</td>
        </tr>`;
    }).join('') : emptyRow(4);
    return cardShell(title, sub, titleCls, 'cb-table',
        '<tr><th>#</th><th>Game</th><th>Deficit</th><th>Final</th></tr>', trows, showMoreBtn(rows.length, false));
}

// ── Game Highs tab ─────────────────────────────────────────────────────────────
const HIGH_CARDS = [
    { key: 'points',   title: 'Points',   unit: 'PTS', cls: 'career' },
    { key: 'rebounds', title: 'Rebounds', unit: 'REB', cls: 'avg' },
    { key: 'assists',  title: 'Assists',  unit: 'AST', cls: 'season' },
    { key: 'threes',   title: 'Threes',   unit: '3PM', cls: 'q4' },
    { key: 'pir',      title: 'PIR',      unit: 'PIR', cls: 'post' },
];

function renderHighs(d) {
    if (d.error) return errorMsg('game-high');
    return legend(`Single-game bests rebuilt from play-by-play &nbsp;·&nbsp; ${d.games_scanned.toLocaleString()} games since ${sinceLabel(d)} &nbsp;·&nbsp; click a game for its replay`) +
        `<div class="records-grid">${HIGH_CARDS.map(c => renderHighCard(d[c.key] || [], c, d.current_season)).join('')}</div>`;
}

function lineSummary(line, key) {
    const parts = [`${line.points} PTS`, `${line.rebounds} REB`, `${line.assists} AST`];
    if (key === 'threes') parts.push(`${line.threes} 3PM`);
    parts.push(`${line.pir} PIR`);
    return parts.join(' · ');
}

function renderHighCard(rows, c, current) {
    const trows = rows.length ? rows.map((r, i) => {
        const sep  = r.home ? 'vs' : '@';
        const game = replayLink(r, `${sep} ${r.opp}`, esc(`${r.team} ${sep} ${r.opp}`));
        const meta = [r.team, r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        return `<tr class="${rowCls(r, i)}">
          ${rankCell(r)}
          <td>
            <span class="p-name">${playerLink(r)}${newTag(r.season, current)}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td>
            <span class="p-name">${game}</span>
            <span class="p-meta">${r.won ? 'W' : 'L'} ${r.final}${r.ot ? ' OT' : ''}</span>
          </td>
          <td class="val-deficit">${r.value}
            <span class="p-meta">${lineSummary(r.line, c.key)}</span>
          </td>
        </tr>`;
    }).join('') : emptyRow(4);
    return cardShell(c.title, 'Single game', c.cls, 'gr-table',
        `<tr><th>#</th><th>Player</th><th>Game</th><th>${c.unit}</th></tr>`, trows, showMoreBtn(rows.length, false));
}

// ── Game-Winners tab ───────────────────────────────────────────────────────────
function renderWinners(d) {
    if (d.error) return errorMsg('game-winner');
    return legend(`Made field goals in the last ${d.window_seconds} seconds of the 4th quarter or OT that gave the winner the lead for good &nbsp;·&nbsp; ${d.all.length} since ${sinceLabel(d)}`) + `
    <div class="records-grid">
      ${renderShotCard(d.all,            'All Game-Winners', 'Newest first',  'comeback', d.current_season)}
      ${renderShotCard(d.buzzer_beaters, 'Buzzer-Beaters',   '0:01 or less',  'q4',       d.current_season)}
      ${renderLeadersCard(d.leaders)}
    </div>`;
}

function renderShotCard(rows, title, sub, titleCls, current) {
    const trows = rows.length ? rows.map((r, i) => {
        const sep    = r.home ? 'vs' : '@';
        const game   = replayLink(r, `${r.team} ${sep} ${r.opp}`, esc(`${r.team} ${sep} ${r.opp}`));
        const meta   = [game, r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        const buzzer = r.buzzer ? '<span class="gw-buzzer">BUZZER</span>' : '';
        return `<tr class="${rowCls(r, i)}">
          <td>
            <span class="p-name">${playerLink(r)}${newTag(r.season, current)}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td>
            <span class="p-name">${r.shot} · ${periodLabel(r.quarter)} ${clockLabel(r.clock)}${buzzer}</span>
            <span class="p-meta">go-ahead ${r.after} · final ${r.final}${r.ot ? ' OT' : ''}</span>
          </td>
        </tr>`;
    }).join('') : emptyRow(2);
    return cardShell(title, sub, titleCls, 'gw-table',
        '<tr><th>Shooter</th><th>Shot</th></tr>', trows, showMoreBtn(rows.length, true));
}

function renderLeadersCard(rows) {
    const trows = rows.length ? rows.map((r, i) => `<tr class="${rowCls(r, i)}">
          ${rankCell(r)}
          <td>
            <span class="p-name">${playerLink(r)}</span>
            <span class="p-meta">last ${r.last_season_label}</span>
          </td>
          <td class="val-deficit">${r.count}</td>
          <td>${r.buzzer_count}</td>
        </tr>`).join('') : emptyRow(4);
    return cardShell('Most Game-Winners', 'Career', 'post', 'gr-table',
        '<tr><th>#</th><th>Player</th><th>GW</th><th>Buzzer</th></tr>', trows, showMoreBtn(rows.length, false));
}

function seasonLbl(s)   { return `${s}-${String(s + 1).slice(-2)}`; }
function periodLabel(q) { return q == null ? '' : q <= 4 ? `Q${q}` : `OT${q - 4}`; }
function clockLabel(c)  { return c ? String(c).replace(/^0(?=\d:)/, '') : ''; }
function esc(s)         { return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }
function stageLabel(r) {
    const name = PHASE_LABEL[r.phase] || r.phase || '';
    return (r.phase === 'RS' || r.phase === 'TS') && r.round != null ? `${name} R${r.round}` : name;
}
```

- [ ] **Step 4: CSS and meta description in `docs/records.html`**

Directly after the closing `}` of the `.cb-new { ... }` rule, add:

```css
    .gr-table thead th:nth-child(1) { width: 36px; }
    .gr-table td:nth-child(1) { white-space: nowrap; }
    .gr-table .p-name { white-space: nowrap; }
    .gr-table .val-deficit .p-meta { white-space: normal; }
    .gw-table thead th:nth-child(1), .gw-table td:nth-child(1) { text-align: left; width: auto; font-weight: 400; font-size: 12px; }
    .gw-table thead th:nth-child(2), .gw-table td:nth-child(2) { text-align: right; }
    .gw-table .p-name { white-space: nowrap; }
    .gw-buzzer {
      display: inline-block; margin-left: 6px; padding: 0 4px; border: 1px solid currentColor;
      border-radius: 4px; font-size: 9px; font-weight: 700; color: var(--accent-red); vertical-align: 1px;
    }
```

Change the meta description content to:
`Euroleague all-time career leaders, single-season records, biggest comebacks, single-game highs and game-winners across 20 seasons.`

- [ ] **Step 5: About page entries in `docs/about.html`**

In the "Biggest Comebacks" paragraph, change `<code style="color:var(--accent-blue)">calculate_comebacks.py</code>` to `<code style="color:var(--accent-blue)">calculate_game_records.py</code>`. Then, directly after the `</p>` that ends "…listed newest first." (the second Biggest Comebacks paragraph), add:

```html
            <h4 style="margin-top:1.2rem;color:var(--text-primary);">Game Highs</h4>
            <p>
                The Game Highs tab ranks the best single-game lines for points, rebounds, assists, threes and PIR. Box scores are rebuilt per player from the play-by-play log of every game since 2007–08 (<code style="color:var(--accent-blue)">calculate_game_records.py</code> → <code style="color:var(--accent-blue)">game_highs.json</code>, refreshed daily), including older logs that record made dunks and layups and blocked or missed layup attempts as separate play types. PIR = points + rebounds + assists + steals + blocks + fouls drawn − missed shots − turnovers − shots blocked − fouls committed. For 2024–25 and 2025–26 the rebuilt lines match the official box scores for more than 99.9% of player-games. Equal values share a rank (T-1) and are listed newest first.
            </p>
            <h4 style="margin-top:1.2rem;color:var(--text-primary);">Game-Winners</h4>
            <p>
                A game-winner is a made field goal in the last 10 seconds of the 4th quarter or overtime that gave the eventual winner the lead for good (<code style="color:var(--accent-blue)">game_winners.json</code>). Free throws are not counted. Shots with 0:01 or less on the clock are marked as buzzer-beaters; the play-by-play clock has one-second resolution. The career leaderboard counts each player's game-winners and buzzer-beaters.
            </p>
            <p>
                Coverage: the Comebacks, Game Highs and Game-Winners boards only include games with a play-by-play log. A few 2012–13 and 2018–19 games are missing from the source, and a game whose log ends before the 4th quarter is skipped.
            </p>
```

- [ ] **Step 6: Syntax check and Node smoke test**

Run: `node --check docs/records.js` (no output).

Write a throwaway smoke test **outside the repo** at `C:/Users/klalo/AppData/Local/Temp/claude/c--Users-klalo-PycharmProjects-pythonProject/85a4f455-7e38-4931-9536-a78ced663cf8/scratchpad/records_smoke2.js`. Don't commit it. It should:
1. Use `vm.createContext` with a stub `document` (`addEventListener` no-op; `getElementById` returns an object whose `innerHTML` setter is captured; `querySelectorAll` returns `[]`), then run `docs/records.js` in that context.
2. Load the three real JSON files from `docs/data/current/`, then assert the rendered HTML for each tab:
   - `renderComebacks(cb)` contains `T-1`, `OLY @ PAM`, `cb-new`, `trailed 34-62 · Q3 8:30`.
   - `renderHighs(h)` contains five `record-card` occurrences, `player.html?code=`, `PTS ·`, `Show top 25`, and the name of `h.points[0].player_name`.
   - `renderWinners(w)` contains `ROBINSON, JUSTIN`, `gw-buzzer`, `Show all`, `Most Game-Winners`, and `replay.html?season=`.
3. For each of the three, assert `renderX({error:true})` contains `Could not load`.
4. Stub `fetch` to reject, then assert `await loadJson('x')` deep-equals `{error:true}`.
5. Set `_rankings = computeRankings({players:{}}, 100)`, `_activeTab='scoring'`, call `renderPage()`, and assert the captured HTML contains `min-gp-select`, `Game Highs` and `Game-Winners`.
6. Set `_lazy = {highs: h}`, `_activeTab='highs'`, call `renderPage()`, and assert the captured HTML has no `min-gp-select`.

Run it with `node` and paste the output into your report. List the manual browser checks for the user:
- each new tab renders
- "T-" ranks don't wrap
- "Show all N" expands the full game-winner list
- player links open career pages
- the replay links open the game
- at about 400px wide, the cards stack with no horizontal scroll

- [ ] **Step 7: Commit**

```bash
git add docs/records.js docs/records.html docs/about.html
git commit -m "feat: Game Highs and Game-Winners tabs on All-Time Records + about methodology

Co-Authored-By: <your model> <noreply@anthropic.com>"
```
