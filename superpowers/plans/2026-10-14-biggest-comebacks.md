# Biggest Comebacks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an all-time "Biggest Comebacks" tab to the All-Time Records page, ranking wins by the largest deficit the eventual winner overcame (2007-08 onward).

**Architecture:**
- A new pipeline script, `calculate_comebacks.py`, reads the cached play-by-play for every season. It computes each winner's worst confirmed deficit, overall and in Q4/OT only, and writes three ranked top-25 lists to `docs/data/current/comebacks.json`.
- `records.js` lazy-loads that file when the new Comebacks tab is first opened and renders it in the page's existing three-card grid.

**Tech Stack:** Python 3 and pandas (pipeline), pytest, vanilla JS and HTML (GitHub Pages, no build step).

**Spec:** `superpowers/specs/2026-10-14-biggest-comebacks-design.md`

## Global Constraints

- `calculate_comebacks.py` must contain no literal years matching `\b202[5-9]\b` anywhere outside `#` comments, docstrings included. `tests/test_no_hardcoded_season.py` scans every script named in `refresh_all.py`. Seasons come from `season_config.ALL_SEASONS` / `CURRENT_SEASON`, and labels from `season_config.season_label()`.
- Python on Windows: `.venv/Scripts/python.exe`. Tests: `.venv/Scripts/python.exe -m pytest tests/ -q`.
- Output file: `docs/data/current/comebacks.json`. Replay files: `docs/data/{season}/{gamecode}.json`.
- Glitch tolerance 3 points; skip games with < 30 scoring rows or any final under 45; top 25 per list.
- Ties: equal deficits share a rank, are flagged `tied`, and are ordered newest first (season desc, then gamecode desc).
- Frontend: vanilla JS, no new dependencies, reuse existing `style.css` variables (`--accent-gold`, `--accent-red`, `--accent-green`, `--accent-blue`).
- Plans and specs live in `superpowers/`, never under `docs/` (GitHub Pages publishes `docs/`).
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Older seasons have no `TRUE_NUMBEROFPLAY` column.** Ordering must fall back to `NUMBEROFPLAY` without crashing. Pinned by `test_falls_back_to_numberofplay` (Task 1).
2. **`Phase` / `Round` can be missing or non-numeric** (per-game API fetches, odd schedule gamedays). This must give `phase=None` / `round=None` rather than a crash, and the game must be left out of the postseason list. Pinned by `test_missing_phase_and_odd_round` (Task 1).
3. **`MARKERTIME` can be NaN at the trough row.** This must give `clock=None`, and the frontend renders an empty clock. Pinned by `test_missing_clock_is_none` (Task 1).
4. **A tie straddling the top-25 cutoff** must still be flagged `tied`, even though its partner was cut. Pinned by `test_tie_at_cutoff_still_flagged` (Task 1).
5. **A missing `comebacks.json`** (pipeline not yet run) must show an inline error on the Comebacks tab while the player tabs keep working. Pinned by the manual check in Task 3 Step 5.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `calculate_comebacks.py` | Per-game deficit analysis, ranking, JSON export |
| Create | `tests/test_comebacks.py` | Unit tests on made-up PBP |
| Modify | `refresh_all.py` (Phase 2, after the "GCI Ratings" step) | Run the script in the local pipeline |
| Modify | `.github/workflows/wp_replay_update.yml` (after "Preprocess WP JSON Data") | Run the script daily after the PBP and replay refresh |
| Create (generated) | `docs/data/current/comebacks.json` | Data consumed by the frontend |
| Modify | `docs/records.js` | Comebacks tab: lazy load and card rendering |
| Modify | `docs/records.html` | CSS for the comeback cards; meta description |
| Modify | `docs/about.html` (All-Time Records section, ~line 571) | Methodology entry |

---

### Task 1: `calculate_comebacks.py` core logic (TDD)

**Files:**
- Create: `calculate_comebacks.py`
- Test: `tests/test_comebacks.py`

**Interfaces:**
- Produces:
  - `analyze_game(g: pd.DataFrame) -> dict | None`. One game's PBP rows go in. It returns a record with the keys:
    - `season, phase, round, gamecode`
    - `winner, winner_name, loser, loser_name, home`
    - `deficit, trailing, quarter, clock`
    - `q4` (a dict with `deficit, trailing, quarter, clock`)
    - `final, ot`

    It returns `None` if the game is unusable. `trailing` is `"{winner_pts}-{loser_pts}"` at the worst moment, or `None` when the deficit is 0.
  - `rank_entries(records: list[dict], limit: int = TOP_N) -> list[dict]` keeps records with `deficit > 0`, sorted, and returns new dicts with `rank` and `tied` added.
  - `build_output(records: list[dict], current_season: int, replay_dir: str = REPLAY_DIR, generated: str | None = None) -> dict` returns the full JSON payload.
  - `load_records(seasons=ALL_SEASONS, cache_dir=CACHE_DIR) -> list[dict]`
  - `main()`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comebacks.py`:

```python
"""Tests for calculate_comebacks.py (made-up play-by-play)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import calculate_comebacks as cb


def game(legs, season=2015, gamecode=7, phase='RS', rnd=3, true_numbers=True):
    """Build a PBP DataFrame. legs: (side, baskets, points_each, period, clock).

    Side 'A' is the home team (code HOM), 'B' the away team (code AWY).
    A non-scoring 'Begin Period' row comes first, as in the real feed.
    """
    rows = [{'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
             'NUMBEROFPLAY': 0, 'TRUE_NUMBEROFPLAY': 0, 'CODETEAM': np.nan,
             'TEAM': np.nan, 'PLAYTYPE': 'BP', 'POINTS_A': np.nan, 'POINTS_B': np.nan,
             'PERIOD': 1, 'MARKERTIME': np.nan}]
    a = b = 0
    for side, n, pts, period, clock in legs:
        for _ in range(n):
            if side == 'A':
                a += pts
            else:
                b += pts
            code = 'HOM' if side == 'A' else 'AWY'
            rows.append({'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
                         'NUMBEROFPLAY': len(rows), 'TRUE_NUMBEROFPLAY': len(rows),
                         'CODETEAM': code, 'TEAM': f'{code} Club', 'PLAYTYPE': '2FGM',
                         'POINTS_A': a, 'POINTS_B': b, 'PERIOD': period, 'MARKERTIME': clock})
    df = pd.DataFrame(rows)
    if not true_numbers:
        df = df.drop(columns='TRUE_NUMBEROFPLAY')
    return df


# Away team trails 0-20 in Q1, wins 52-50.
BASIC = [('A', 10, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00'),
         ('A', 15, 2, 3, '05:00'), ('B', 1, 2, 4, '00:10')]


def test_basic_comeback():
    r = cb.analyze_game(game(BASIC))
    assert r['deficit'] == 20
    assert r['trailing'] == '0-20'
    assert (r['quarter'], r['clock']) == (1, '05:00')
    assert (r['winner'], r['winner_name'], r['loser'], r['loser_name']) == \
        ('AWY', 'AWY Club', 'HOM', 'HOM Club')
    assert r['home'] is False
    assert r['final'] == '52-50'
    assert r['ot'] is False
    assert (r['season'], r['phase'], r['round'], r['gamecode']) == (2015, 'RS', 3, 7)
    assert r['q4'] == {'deficit': 0, 'trailing': None, 'quarter': None, 'clock': None}


def test_wire_to_wire_winner_has_zero_deficit():
    r = cb.analyze_game(game([('A', 30, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00')]))
    assert r['deficit'] == 0
    assert r['trailing'] is None
    assert r['winner'] == 'HOM' and r['home'] is True


def test_unscored_side_counts_as_zero():
    df = game(BASIC)
    df.loc[df['POINTS_B'] == 0, 'POINTS_B'] = np.nan
    r = cb.analyze_game(df)
    assert r['deficit'] == 20
    assert r['trailing'] == '0-20'


def test_single_row_score_spike_is_ignored():
    df = game(BASIC)
    # row 30 is mid-way through B's run (A=20, B=40); a typo puts A at 80
    df.loc[30, 'POINTS_A'] = 80
    r = cb.analyze_game(df)
    assert r['deficit'] == 20


def test_fourth_quarter_deficit_only_uses_q4_and_ot():
    legs = [('A', 10, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00'),
            ('A', 18, 2, 4, '03:00'), ('B', 4, 2, 4, '00:30')]
    r = cb.analyze_game(game(legs))
    assert r['final'] == '58-56'
    assert r['deficit'] == 20
    assert r['q4'] == {'deficit': 6, 'trailing': '50-56', 'quarter': 4, 'clock': '03:00'}


def test_overtime_flag():
    legs = BASIC[:3] + [('B', 1, 2, 5, '00:10')]
    assert cb.analyze_game(game(legs))['ot'] is True


def test_final_under_45_is_skipped():
    assert cb.analyze_game(game([('A', 20, 1, 1, '05:00'), ('B', 15, 2, 2, '05:00')])) is None


def test_too_few_scoring_rows_is_skipped():
    assert cb.analyze_game(game([('A', 15, 4, 1, '05:00'), ('B', 10, 5, 2, '05:00')])) is None


def test_tied_final_is_skipped():
    assert cb.analyze_game(game([('A', 25, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00')])) is None


def test_falls_back_to_numberofplay():
    r = cb.analyze_game(game(BASIC, true_numbers=False))
    assert r['deficit'] == 20


def test_missing_phase_and_odd_round():
    r = cb.analyze_game(game(BASIC, phase=None, rnd='Final'))
    assert r['phase'] is None
    assert r['round'] is None
    assert r['deficit'] == 20


def test_missing_clock_is_none():
    legs = [('A', 10, 2, 1, np.nan)] + BASIC[1:]
    r = cb.analyze_game(game(legs))
    assert r['deficit'] == 20
    assert r['clock'] is None


def _rec(deficit, season, gamecode, phase='RS', q4_deficit=0):
    return {'season': season, 'phase': phase, 'round': 3, 'gamecode': gamecode,
            'winner': 'AWY', 'winner_name': 'AWY Club', 'loser': 'HOM', 'loser_name': 'HOM Club',
            'home': False, 'deficit': deficit, 'trailing': f'0-{deficit}', 'quarter': 2,
            'clock': '05:00',
            'q4': {'deficit': q4_deficit,
                   'trailing': f'1-{q4_deficit + 1}' if q4_deficit else None,
                   'quarter': 4 if q4_deficit else None,
                   'clock': '02:00' if q4_deficit else None},
            'final': '80-78', 'ot': False}


def test_rank_entries_ties_share_rank_newest_first():
    recs = [_rec(27, 2019, 5), _rec(28, 2012, 113), _rec(28, 2016, 45), _rec(0, 2010, 1)]
    out = cb.rank_entries(recs)
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == \
        [(45, 1, True), (113, 1, True), (5, 3, False)]
    assert 'rank' not in recs[0]          # inputs are not mutated


def test_tie_at_cutoff_still_flagged():
    recs = [_rec(28, 2012, 1), _rec(28, 2013, 2), _rec(28, 2014, 3), _rec(27, 2015, 4)]
    out = cb.rank_entries(recs, limit=2)
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == [(3, 1, True), (2, 1, True)]


def test_build_output(tmp_path):
    os.makedirs(tmp_path / '2015')
    (tmp_path / '2015' / '113.json').write_text('{}')
    recs = [_rec(20, 2015, 113, q4_deficit=8), _rec(15, 2016, 9, phase='FF'),
            _rec(10, 2017, 4, phase='PO', q4_deficit=12)]
    out = cb.build_output(recs, current_season=2017, replay_dir=str(tmp_path),
                          generated='2000-01-01')
    assert out['generated'] == '2000-01-01'
    assert out['seasons'] == [2015, 2017]
    assert out['current_season'] == 2017
    assert out['games_scanned'] == 3
    assert [r['gamecode'] for r in out['overall']] == [113, 9, 4]
    assert out['overall'][0]['has_replay'] is True
    assert out['overall'][1]['has_replay'] is False
    assert out['overall'][0]['season_label'] == '2015-16'
    assert 'q4' not in out['overall'][0]
    q4 = out['fourth_quarter']
    assert [r['gamecode'] for r in q4] == [4, 113]
    assert (q4[0]['deficit'], q4[0]['trailing'], q4[0]['quarter']) == (12, '1-13', 4)
    assert [r['gamecode'] for r in out['postseason']] == [9, 4]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_comebacks.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'calculate_comebacks'`.

- [ ] **Step 3: Write the implementation**

Create `calculate_comebacks.py`:

```python
"""
Biggest Comebacks: the largest deficits overcome by the eventual winner.

Reads cached play-by-play for every season in season_config.ALL_SEASONS
(data_cache/pbp_{season}.csv) and writes docs/data/current/comebacks.json
with three ranked lists: overall, fourth_quarter (deficit faced in Q4/OT)
and postseason (Playoffs, Play-In, Final Four).
"""
import json
import os
from collections import Counter
from datetime import date

import pandas as pd

from season_config import ALL_SEASONS, CURRENT_SEASON, season_label

CACHE_DIR = 'data_cache'
OUT_PATH = os.path.join('docs', 'data', 'current', 'comebacks.json')
REPLAY_DIR = os.path.join('docs', 'data')
TOP_N = 25
MIN_SCORING_ROWS = 30   # fewer scoring plays than this = truncated game
MIN_FINAL = 45          # a final under this is a data error, not a score
GLITCH_TOL = 3          # one play moves the margin by at most 3 points
POSTSEASON = {'PO', 'PI', 'FF'}
NO_DEFICIT = {'deficit': 0, 'trailing': None, 'quarter': None, 'clock': None}


def _confirmed_margins(margins):
    """Zero out margins no neighbouring play agrees with (single-row score typos)."""
    out = []
    for i, m in enumerate(margins):
        nbrs = margins[max(i - 1, 0):i] + margins[i + 1:i + 2]
        out.append(m if any(abs(m - x) <= GLITCH_TOL for x in nbrs) else 0)
    return out


def _mode(series):
    m = series.dropna().astype(str).str.strip().mode()
    return m.iloc[0] if not m.empty else None


def _int_or_none(v):
    try:
        return None if pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def analyze_game(g):
    """One game's PBP rows -> comeback record, or None if the game is unusable."""
    key = ('TRUE_NUMBEROFPLAY'
           if 'TRUE_NUMBEROFPLAY' in g and g['TRUE_NUMBEROFPLAY'].notna().all()
           else 'NUMBEROFPLAY')
    g = g.drop_duplicates([key, 'PLAYTYPE', 'CODETEAM']).sort_values(key, kind='stable')
    sc = g[g['POINTS_A'].notna() | g['POINTS_B'].notna()].reset_index(drop=True)
    if len(sc) < MIN_SCORING_ROWS:
        return None
    a = sc['POINTS_A'].ffill().fillna(0).astype(int).tolist()
    b = sc['POINTS_B'].ffill().fillna(0).astype(int).tolist()
    fa, fb = a[-1], b[-1]
    if fa == fb or min(fa, fb) < MIN_FINAL:
        return None

    a_up = pd.Series([a[0]] + [a[i] - a[i - 1] for i in range(1, len(a))]) > 0
    b_up = pd.Series([b[0]] + [b[i] - b[i - 1] for i in range(1, len(b))]) > 0
    code_a, name_a = _mode(sc.loc[a_up, 'CODETEAM']), _mode(sc.loc[a_up, 'TEAM'])
    code_b, name_b = _mode(sc.loc[b_up, 'CODETEAM']), _mode(sc.loc[b_up, 'TEAM'])

    a_won = fa > fb
    w_pts, l_pts = (a, b) if a_won else (b, a)
    conf = _confirmed_margins([w - l for w, l in zip(w_pts, l_pts)])
    periods = sc['PERIOD'].fillna(0).astype(int).tolist()
    clocks = sc['MARKERTIME'].tolist()

    def worst(indices):
        if not indices:
            return dict(NO_DEFICIT)
        i = min(indices, key=lambda j: (conf[j], j))
        if conf[i] >= 0:
            return dict(NO_DEFICIT)
        clk = clocks[i]
        return {'deficit': -conf[i], 'trailing': f'{w_pts[i]}-{l_pts[i]}',
                'quarter': periods[i], 'clock': None if pd.isna(clk) else str(clk)}

    first = g.iloc[0]
    phase = first.get('Phase')
    return {
        'season': int(first['Season']),
        'phase': None if pd.isna(phase) else str(phase).strip(),
        'round': _int_or_none(first.get('Round')),
        'gamecode': int(first['Gamecode']),
        'winner': code_a if a_won else code_b,
        'winner_name': name_a if a_won else name_b,
        'loser': code_b if a_won else code_a,
        'loser_name': name_b if a_won else name_a,
        'home': a_won,
        **worst(list(range(len(conf)))),
        'q4': worst([i for i, p in enumerate(periods) if p >= 4]),
        'final': f'{max(fa, fb)}-{min(fa, fb)}',
        'ot': bool(g['PERIOD'].max() > 4),
    }


def rank_entries(records, limit=TOP_N):
    """Top `limit` by deficit (ties: newest first), each with rank and tied flag."""
    rows = sorted((r for r in records if r['deficit'] > 0),
                  key=lambda r: (-r['deficit'], -r['season'], -r['gamecode']))
    counts = Counter(r['deficit'] for r in rows)   # before the cut, so cutoff ties count
    out, rank = [], 0
    for i, r in enumerate(rows[:limit]):
        if i == 0 or r['deficit'] != rows[i - 1]['deficit']:
            rank = i + 1
        out.append({'rank': rank, 'tied': counts[r['deficit']] > 1, **r})
    return out


def _without_q4(r):
    return {k: v for k, v in r.items() if k != 'q4'}


def _with_q4(r):
    return {**_without_q4(r), **r['q4']}


def build_output(records, current_season, replay_dir=REPLAY_DIR, generated=None):
    def finish(rows):
        for r in rows:
            r['season_label'] = season_label(r['season'])
            r['has_replay'] = os.path.exists(
                os.path.join(replay_dir, str(r['season']), f"{r['gamecode']}.json"))
        return rows

    seasons = sorted({r['season'] for r in records})
    return {
        'generated': generated or date.today().isoformat(),
        'seasons': [seasons[0], seasons[-1]] if seasons else [],
        'current_season': current_season,
        'games_scanned': len(records),
        'overall': finish(rank_entries([_without_q4(r) for r in records])),
        'fourth_quarter': finish(rank_entries([_with_q4(r) for r in records])),
        'postseason': finish(rank_entries(
            [_without_q4(r) for r in records if r['phase'] in POSTSEASON])),
    }


def load_records(seasons=ALL_SEASONS, cache_dir=CACHE_DIR):
    records = []
    for s in seasons:
        path = os.path.join(cache_dir, f'pbp_{s}.csv')
        if not os.path.exists(path):
            print(f'  [WARN] {path} missing, skipping {season_label(s)}')
            continue
        df = pd.read_csv(path, low_memory=False)
        for _, g in df.groupby('Gamecode', sort=False):
            r = analyze_game(g)
            if r:
                records.append(r)
    return records


def main():
    out = build_output(load_records(), CURRENT_SEASON)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"Comebacks: {out['games_scanned']} games scanned -> {OUT_PATH}")
    if out['overall']:
        top = out['overall'][0]
        print(f"  Biggest: {top['winner']} over {top['loser']} "
              f"({top['season_label']}) from {top['deficit']} down")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_comebacks.py -q`
Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add calculate_comebacks.py tests/test_comebacks.py
git commit -m "feat: compute biggest comebacks from play-by-play

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Pipeline wiring, data refresh and real-data verification

**Files:**
- Modify: `refresh_all.py` (Phase 2: insert after the `('GCI Ratings', run_step(...))` block, before `else:` / "Skipping compute engines")
- Modify: `.github/workflows/wp_replay_update.yml` (insert after the "Preprocess WP JSON Data (current season only)" step)
- Generated: `docs/data/current/comebacks.json`, plus refreshed `data_cache/pbp_{CURRENT}.csv`, `schedule_{CURRENT}.json`, `docs/data/{CURRENT}/*.json`

**Interfaces:**
- Consumes: `calculate_comebacks.py` CLI (`main()`), from Task 1.
- Produces: `docs/data/current/comebacks.json` with the keys `generated`, `seasons`, `current_season`, `games_scanned`, `overall`, `fourth_quarter`, `postseason`. Each list entry has:
  - `rank, tied`
  - `season, season_label, phase, round, gamecode`
  - `winner, winner_name, loser, loser_name, home`
  - `deficit, trailing, quarter, clock`
  - `final, ot, has_replay`

- [ ] **Step 1: Add the `refresh_all.py` step**

Directly after the existing block

```python
        results.append(('GCI Ratings', run_step(
            'Computing Game Control Index (GCI)',
            'calculate_gci.py'
        )))
```

insert:

```python
        results.append(('Biggest Comebacks', run_step(
            'Computing all-time biggest comebacks from play-by-play',
            'calculate_comebacks.py'
        )))
```

- [ ] **Step 2: Add the workflow step**

In `.github/workflows/wp_replay_update.yml`, directly after the step

```yaml
    - name: Preprocess WP JSON Data (current season only)
      run: |
        SEASON=$(python -c "import season_config as s; print(s.CURRENT_SEASON)")
        python preprocess_wp_data.py --seasons "$SEASON"
```

insert (same indentation):

```yaml
    - name: Compute Biggest Comebacks
      run: |
        python calculate_comebacks.py
```

The existing commit step already runs `git add docs/data/ data_cache/`.

- [ ] **Step 3: Run the season-guard test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_no_hardcoded_season.py -q`
Expected: PASS. `calculate_comebacks.py` is now scanned because `refresh_all.py` names it.

- [ ] **Step 4: Refresh the current season's play-by-play and replays**

The 2026-10-13 game (Valencia vs Olympiacos, gamecode 45) is not cached yet. Run, in order:

```bash
.venv/Scripts/python.exe fetch_schedule.py --force
.venv/Scripts/python.exe fetch_all_seasons.py
SEASON=$(.venv/Scripts/python.exe -c "import season_config as s; print(s.CURRENT_SEASON)")
.venv/Scripts/python.exe preprocess_wp_data.py --seasons "$SEASON"
```

Expected: `fetch_all_seasons.py` reports more games for the current season than before (it was 40), and `docs/data/$SEASON/45.json` exists.

- [ ] **Step 5: Generate the JSON**

Run: `.venv/Scripts/python.exe calculate_comebacks.py`
Expected: a line `Comebacks: ~5060 games scanned -> docs/data/current/comebacks.json` and `Biggest: OLY over PAM (2026-27) from 28 down`.

- [ ] **Step 6: Verify the success criteria on real data**

Run:

```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/comebacks.json', encoding='utf-8'))
o = d['overall']
print([(r['rank'], r['tied'], r['winner'], r['loser'], r['season_label'], r['deficit'], r['trailing'], r['has_replay']) for r in o[:4]])
assert (o[0]['winner'], o[0]['loser'], o[0]['gamecode'], o[0]['deficit'], o[0]['rank'], o[0]['tied']) == ('OLY', 'PAM', 45, 28, 1, True)
assert o[0]['trailing'] == '34-62' and o[0]['quarter'] == 3 and o[0]['ot'] is True
assert (o[1]['winner'], o[1]['loser'], o[1]['deficit'], o[1]['rank']) == ('SOP', 'SIE', 28, 1)
ps = {(r['season'], r['winner'], r['loser']) for r in d['postseason']}
assert (2011, 'OLY', 'CSK') in ps and (2012, 'OLY', 'MAD') in ps, ps
assert all(r['phase'] in ('PO', 'PI', 'FF') for r in d['postseason'])
assert all(r['quarter'] >= 4 for r in d['fourth_quarter'])
print('OK', d['games_scanned'], 'games; Q4 top:', d['fourth_quarter'][0]['winner'], d['fourth_quarter'][0]['deficit'])
"
```

Expected: ends with `OK ... games; Q4 top: ...` and raises no AssertionError. If the OLY assertion fails because game 45 is missing, Step 4 did not fetch it: check `schedule_{CURRENT}.json` marks it played.

- [ ] **Step 7: Run the full test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 8: Commit (two commits: code, then data)**

```bash
git add refresh_all.py .github/workflows/wp_replay_update.yml
git commit -m "feat: run biggest-comebacks step in refresh and daily replay workflows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Stage only these data paths: `data_cache/pbp_*.csv`, `schedule_*.json`, `official_schedule_*.xml`, `docs/data/<CURRENT>/`, `docs/data/seasons.json`, `docs/data/current/comebacks.json`. Leave anything else `git status` shows unstaged and report it.

```bash
git add docs/data/current/comebacks.json data_cache/ docs/data/seasons.json "docs/data/$SEASON/" "schedule_$SEASON.json" "official_schedule_$SEASON.xml"
git commit -m "data: fetch latest round PBP/replays and generate comebacks.json

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Comebacks tab on the Records page and About methodology

**Files:**
- Modify: `docs/records.js`
- Modify: `docs/records.html` (`<style>` block after the `.val-season` rule; `<meta name="description">`)
- Modify: `docs/about.html` (All-Time Records section, after the "Single-Season Records" `<p>`, ~line 583)

**Interfaces:**
- Consumes: `docs/data/current/comebacks.json`, from Task 2 (schema in Task 2's Interfaces).
- Produces: user-facing UI only.

- [ ] **Step 1: Add constants, state and the tab entry in `docs/records.js`**

After the line `const TOP_EXTENDED  = 25;` add:

```js
const COMEBACKS_URL = 'data/current/comebacks.json';
const PHASE_LABEL   = { RS: 'RS', TS: 'Top 16', PO: 'Playoffs', PI: 'Play-In', FF: 'Final Four' };
```

After the line `let _minGpCareer = 100;` add:

```js
let _comebacks   = null; // comebacks.json, loaded on first Comebacks tab click
```

In the `TABS` array, after the `efficiency` entry, add:

```js
    { key: 'comebacks',  label: 'Comebacks' },
```

- [ ] **Step 2: Replace `renderPage()` in `docs/records.js`**

Replace the whole `function renderPage() { ... }` (from `// ── Render full page` to just before `// ── Render one record card`) with:

```js
// ── Render full page ───────────────────────────────────────────────────────────
function renderPage() {
    const tabButtons = TABS.map(t =>
        `<button class="cat-tab${t.key === _activeTab ? ' active' : ''}" data-tab="${t.key}">${t.label}</button>`
    ).join('');
    const content = document.getElementById('records-content');

    if (_activeTab === 'comebacks') {
        content.innerHTML = `<div class="cat-tabs">${tabButtons}</div>${renderComebacks()}`;
    } else {
        const filterHtml = `
    <div class="filter-row">
      <span>Career minimum:</span>
      <select id="min-gp-select">
        <option value="50"${_minGpCareer ===  50 ? ' selected' : ''}>50 GP</option>
        <option value="100"${_minGpCareer === 100 ? ' selected' : ''}>100 GP</option>
        <option value="200"${_minGpCareer === 200 ? ' selected' : ''}>200 GP</option>
        <option value="0"${_minGpCareer ===   0 ? ' selected' : ''}>No minimum</option>
      </select>
      <span class="filter-legend">· Career totals = Σ(stat × GP) &nbsp;·&nbsp; Career averages = GP-weighted &nbsp;·&nbsp; Season min: ${MIN_GP_SEASON} GP</span>
    </div>`;

        const tab  = TABS.find(t => t.key === _activeTab);
        const data = _rankings[_activeTab];

        content.innerHTML = `
    <div class="cat-tabs">${tabButtons}</div>
    ${filterHtml}
    <div class="records-grid">
      ${renderCard(data.career, tab.careerLabel, tab.careerSub, 'career', tab.fmtC)}
      ${renderCard(data.avg,    tab.avgLabel,    tab.avgSub,    'avg',    tab.avgFmt)}
      ${renderCard(data.season, tab.seasonLabel, tab.seasonSub, 'season', tab.fmtS)}
    </div>`;

        document.getElementById('min-gp-select').addEventListener('change', e => {
            _minGpCareer = Number(e.target.value);
            _rankings = computeRankings(_data, _minGpCareer); // reuse cached _data, no re-fetch
            renderPage();
        });
    }

    document.querySelectorAll('.cat-tab').forEach(btn => {
        btn.addEventListener('click', async () => {
            _activeTab = btn.dataset.tab;
            if (_activeTab === 'comebacks' && !_comebacks) await loadComebacks();
            renderPage();
        });
    });

    document.querySelectorAll('.show-more-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.record-card').querySelectorAll('tr.hidden').forEach(tr => tr.classList.remove('hidden'));
            btn.remove();
        });
    });
}
```

- [ ] **Step 3: Append the comeback functions to the end of `docs/records.js`**

```js
// ── Comebacks tab ──────────────────────────────────────────────────────────────
async function loadComebacks() {
    try {
        const r = await fetch(COMEBACKS_URL);
        if (!r.ok) throw new Error(r.status);
        _comebacks = await r.json();
    } catch {
        _comebacks = { error: true };
    }
}

function renderComebacks() {
    if (_comebacks.error) {
        return '<p class="error-msg">Could not load comeback data. Run the data pipeline first.</p>';
    }
    const since = _comebacks.seasons.length ? seasonLbl(_comebacks.seasons[0]) : '';
    return `
    <div class="filter-row">
      <span class="filter-legend">Largest deficit the eventual winner faced &nbsp;·&nbsp; ${_comebacks.games_scanned.toLocaleString()} games since ${since} &nbsp;·&nbsp; click a game for its replay</span>
    </div>
    <div class="records-grid">
      ${renderComebackCard(_comebacks.overall,        'Biggest Comebacks',     'Any point in the game',         'comeback')}
      ${renderComebackCard(_comebacks.fourth_quarter, '4th-Quarter Comebacks', 'Deficit faced in Q4 or OT',     'q4')}
      ${renderComebackCard(_comebacks.postseason,     'Playoffs & Final Four', 'Playoffs, Play-In, Final Four', 'post')}
    </div>`;
}

function renderComebackCard(rows, title, sub, titleCls) {
    const rankCls = r => r.rank === 1 ? 'rank-1' : r.rank === 2 ? 'rank-2' : r.rank === 3 ? 'rank-3' : '';

    const trows = rows.length ? rows.map((r, i) => {
        const cls   = [rankCls(r), i >= TOP_INITIAL ? 'hidden' : ''].filter(Boolean).join(' ');
        const sep   = r.home ? 'vs' : '@';
        const full  = esc(`${r.winner_name} ${sep} ${r.loser_name}`);
        const label = `${r.winner} ${sep} ${r.loser}`;
        const game  = r.has_replay
            ? `<a href="replay.html?season=${r.season}&game=${r.gamecode}" title="${full} · open replay">${label}</a>`
            : `<span title="${full}">${label}</span>`;
        const isNew = r.season === _comebacks.current_season ? '<span class="cb-new">NEW</span>' : '';
        const meta  = [r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        return `<tr class="${cls}">
          <td class="${rankCls(r)}">${r.tied ? 'T-' : ''}${r.rank}</td>
          <td>
            <span class="p-name">${game}${isNew}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td class="val-deficit">${r.deficit}
            <span class="p-meta">trailed ${r.trailing} · ${periodLabel(r.quarter)} ${clockLabel(r.clock)}</span>
          </td>
          <td>${r.final}${r.ot ? ' OT' : ''}</td>
        </tr>`;
    }).join('') : '<tr><td colspan="4" class="p-meta">No qualifying games yet</td></tr>';

    const showMore = rows.length > TOP_INITIAL
        ? `<button class="show-more-btn">Show top ${Math.min(rows.length, TOP_EXTENDED)} ↓</button>`
        : '';

    return `
    <div class="record-card">
      <div class="record-card-header">
        <span class="rch-title ${titleCls}">${title}</span>
        <span class="rch-sub">${sub}</span>
      </div>
      <table class="lb-table">
        <thead><tr><th>#</th><th>Game</th><th>Deficit</th><th>Final</th></tr></thead>
        <tbody>${trows}</tbody>
      </table>
      ${showMore}
    </div>`;
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

- [ ] **Step 4: Add the CSS and update the meta description in `docs/records.html`**

Directly after the line `    .val-season { color: var(--accent-green); font-weight: 700; }` add:

```css
    .rch-title.comeback { color: var(--accent-gold); }
    .rch-title.q4       { color: var(--accent-red); }
    .rch-title.post     { color: var(--accent-green); }
    .val-deficit { color: var(--accent-gold); font-weight: 800; font-size: 15px; }
    .val-deficit .p-meta { font-weight: 400; white-space: nowrap; }
    .cb-new {
      display: inline-block; margin-left: 6px; padding: 0 4px; border: 1px solid currentColor;
      border-radius: 4px; font-size: 9px; font-weight: 700; color: var(--accent-green); vertical-align: 1px;
    }
```

Replace the meta description content with:
`Euroleague all-time career leaders, single-season records and biggest comebacks across 20 seasons.`

- [ ] **Step 5: Syntax check and manual browser check**

Run: `node --check docs/records.js`
Expected: no output (exit 0).

Then run `.venv/Scripts/python.exe -m http.server 8765 -d docs` in the background and open `http://localhost:8765/records.html`. Check each of the following:

- **Scoring tab** renders exactly as before, including the career-minimum filter.
- **Comebacks tab:**
  - three cards; Biggest Comebacks shows `T-1 OLY @ PAM` with a NEW tag, `2026-27 · RS R5`, deficit 28, `trailed 34-62 · Q3 8:30`, `102-97 OT`, and `T-1 SOP @ SIE` second
  - "Show top 25 ↓" expands
  - clicking `OLY @ PAM` opens `replay.html?season=2026&game=45` with the game loaded
  - the Playoffs card shows `2011-12 · Final Four` for OLY vs CSK
- **Missing-file check (Review Focus #5):** temporarily rename `docs/data/current/comebacks.json`, hard-reload, then:
  - the Comebacks tab shows "Could not load comeback data…"
  - switching back to Scoring still works

  Rename the file back afterwards.
- **Narrow window (~400px):** cards stack in one column with no horizontal page scroll.

If no browser tool is available, say so in the report and list these checks for the user to do.

- [ ] **Step 6: Add the About entry**

In `docs/about.html`, in the `<!-- ── All-Time Records ── -->` section, directly after the `<p>` that follows `<h4 ...>Single-Season Records</h4>` (the one ending "…injury-shortened appearances."), add:

```html
            <h4 style="margin-top:1.2rem;color:var(--text-primary);">Biggest Comebacks</h4>
            <p>
                The Comebacks tab ranks wins by the largest deficit the eventual winner faced at any point, rebuilt from every play-by-play log since 2007–08 (<code style="color:var(--accent-blue)">calculate_comebacks.py</code> → <code style="color:var(--accent-blue)">comebacks.json</code>, refreshed daily). The 4th-Quarter card counts only deficits faced in the 4th quarter or overtime; the Playoffs &amp; Final Four card covers Playoffs, Play-In and Final Four games. Click any game to open its win-probability replay.
            </p>
            <p>
                Play-by-play logs occasionally contain a mistyped score. Since no single play moves the margin by more than 3 points, a deficit only counts if a neighbouring play agrees with it to within 3, so one bad row cannot create a phantom lead. Games with fewer than 30 scoring plays or a final score under 45 are skipped as incomplete. Equal deficits share a rank (T-1) and are listed newest first.
            </p>
```

- [ ] **Step 7: Commit**

```bash
git add docs/records.js docs/records.html docs/about.html
git commit -m "feat: Comebacks tab on All-Time Records + about methodology

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
