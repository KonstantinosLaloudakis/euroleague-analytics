# Official Standings Order + Standings Race Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Season Hub standings table, the playoff bracket seeds and the Standings Race chart all use the official Euroleague order (wins, then head-to-head among tied teams, then head-to-head point difference, then overall point difference) — and the chart draws straight segments between rounds instead of overshooting splines.

**Architecture:** `export_dashboard_data.py` gets a pure `official_standings(game_results, schedule_rows)` that, for every round up to the latest played one, ranks all teams with the existing `simulate_monte_carlo._rank_with_h2h` tiebreaker (one "simulation" of the actual results). Each team object gains `position` (current official rank) and `rank_history` (rank after rounds 1..R); `teams` is sorted by `position`, so `seeded = teams[:10]` and every consumer of the export order follow the official table. Frontend: the standings table sorts by `position` by default, `playoffs.js` seeds by `position`, the chart plots `rank_history` with linear lines. Old dashboards without the fields keep today's behaviour.

**Tech Stack:** Python 3.12 + numpy + pytest; vanilla JS + Plotly.

**Spec:** Site audit 2026-10-12 finding #8 (Standings Race smoothed with 4 points, overshooting) plus what investigation found: ties in the chart are broken alphabetically and the table/bracket break ties by adjusted net rating, so the three disagree and none is official. User: "fix all of them, one at a time".

## Global Constraints

- Branch `fix/official-standings-order`.
- Tiebreak order = existing `_resolve_tie` in `simulate_monte_carlo.py` (do not change it): wins → H2H wins among tied → H2H point diff among tied → overall point diff.
- Ranking is by wins (as today and as in the season simulator); a game counts toward round R if its scheduled gameday ≤ R and it has been played.
- Round of a game = its `gameday` in `schedule_{S}.json` (regular-season rows only); team codes via `team_aliases.team_code(name)` with the row's `homecode`/`awaycode` as fallback.
- Never hardcode a season year. Keep line endings. `.venv/Scripts/python.exe`.
- Backward compatible: frontend falls back to the current logic when `position` / `rank_history` are absent (archived dashboards).

## Review Focus

1. Two teams level on wins: the H2H winner ranks higher even if its point difference is worse — `test_two_way_tie_uses_head_to_head`.
2. Three-way tie resolved by the mini-table — `test_three_way_tie_mini_table`.
3. A postponed game played later counts in its scheduled round's snapshot only once it has been played (snapshots are "as of now") — `test_postponed_game_counts_in_its_round`.
4. A team with no games played yet still appears and ranks below teams with wins — `test_team_without_games_is_ranked`.
5. Archived dashboards (no `position`) still render the table, bracket and chart — Task 2 Step 5.

---

### Task 1: `official_standings` in the export

**Files:**
- Modify: `export_dashboard_data.py` (new function above `def compute_championship_finals_history():`; use it where `teams` is sorted, ~line 1788)
- Create: `tests/test_official_standings.py`

**Interfaces — Produces:** `official_standings(game_results: list[dict], schedule_rows: list[dict]) -> tuple[list[str], dict[str, list[int]]]` — (team codes in current official order, {code: [rank after round 1, …, after latest played round]}); ranks 1-based. Team dict fields `position: int | None`, `rank_history: list[int]`.

- [ ] **Step 1: Branch** — `git checkout -b fix/official-standings-order`

- [ ] **Step 2: Failing tests** — create `tests/test_official_standings.py`:

```python
"""Official Euroleague standings order after each round."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import official_standings


def _sched(rows):
    """rows: (gamecode, gameday, home, away) → schedule_{S}.json-like dicts."""
    return [{'round': 'RS', 'gamecode': f'E2099_{gc}', 'gameday': str(gd),
             'hometeam': h, 'homecode': h, 'awayteam': a, 'awaycode': a}
            for gc, gd, h, a in rows]


def _res(rows):
    """rows: (gamecode, home, away, home_pts, away_pts)."""
    return [{'GameCode': gc, 'LocalTeam': h, 'RoadTeam': a,
             'LocalScore': hp, 'RoadScore': ap} for gc, h, a, hp, ap in rows]


def test_two_way_tie_uses_head_to_head():
    sched = _sched([(1, 1, 'AAA', 'BBB'), (2, 1, 'CCC', 'DDD'),
                    (3, 2, 'AAA', 'CCC'), (4, 2, 'BBB', 'DDD')])
    # AAA beats BBB by 1; BBB thrashes DDD, AAA loses big to CCC → both 1-1,
    # BBB has the better point difference but AAA won the head-to-head.
    res = _res([(1, 'AAA', 'BBB', 71, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 60, 90), (4, 'BBB', 'DDD', 100, 60)])
    order, hist = official_standings(res, sched)
    assert order.index('AAA') < order.index('BBB')
    assert len(hist['AAA']) == 2


def test_three_way_tie_mini_table():
    # Round robin among AAA, BBB, CCC where each wins once → mini-table tied 1-1,
    # resolved by H2H point difference: AAA +10-2=+8, BBB -10+10=0, CCC -10+2=-8.
    sched = _sched([(1, 1, 'AAA', 'BBB'), (2, 2, 'BBB', 'CCC'), (3, 3, 'CCC', 'AAA')])
    res = _res([(1, 'AAA', 'BBB', 80, 70), (2, 'BBB', 'CCC', 80, 70), (3, 'CCC', 'AAA', 72, 70)])
    order, _ = official_standings(res, sched)
    assert order == ['AAA', 'BBB', 'CCC']


def test_rank_history_is_a_permutation_each_round():
    sched = _sched([(1, 1, 'AAA', 'BBB'), (2, 1, 'CCC', 'DDD'), (3, 2, 'AAA', 'CCC'), (4, 2, 'BBB', 'DDD')])
    res = _res([(1, 'AAA', 'BBB', 80, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 80, 70), (4, 'BBB', 'DDD', 80, 70)])
    order, hist = official_standings(res, sched)
    for r in range(2):
        assert sorted(h[r] for h in hist.values()) == [1, 2, 3, 4]
    assert [hist[t][-1] for t in order] == [1, 2, 3, 4]


def test_postponed_game_counts_in_its_round():
    # Round-1 game 2 was postponed and played after round 2; snapshots are "as of now".
    sched = _sched([(1, 1, 'AAA', 'BBB'), (2, 1, 'CCC', 'DDD'), (3, 2, 'AAA', 'CCC'), (4, 2, 'BBB', 'DDD')])
    res = _res([(1, 'AAA', 'BBB', 80, 70), (3, 'AAA', 'CCC', 80, 70),
                (4, 'BBB', 'DDD', 80, 70), (2, 'CCC', 'DDD', 90, 70)])
    _, hist = official_standings(res, sched)
    # after round 1: AAA and CCC both 1-0 (CCC's postponed win counts in round 1)
    assert {hist['AAA'][0], hist['CCC'][0]} == {1, 2}


def test_team_without_games_is_ranked():
    sched = _sched([(1, 1, 'AAA', 'BBB'), (2, 2, 'CCC', 'AAA')])   # CCC hasn't played yet
    res = _res([(1, 'AAA', 'BBB', 80, 70)])
    order, hist = official_standings(res, sched)
    assert set(order) == {'AAA', 'BBB', 'CCC'}
    assert order[0] == 'AAA'
    assert hist['CCC'][0] in (2, 3)


def test_no_games_played():
    order, hist = official_standings([], _sched([(1, 1, 'AAA', 'BBB')]))
    assert sorted(order) == ['AAA', 'BBB'] and hist == {'AAA': [], 'BBB': []}
```

- [ ] **Step 3: Run to verify they fail** — `.venv/Scripts/python.exe -m pytest tests/test_official_standings.py -q` → ImportError.

- [ ] **Step 4: Implement** — insert above `def compute_championship_finals_history():` (the module already imports `os`, `json`, `pandas as pd`; add `import numpy as np` at the top imports if absent):

```python
def official_standings(game_results, schedule_rows):
    """Official Euroleague order after every round: wins, then head-to-head
    among tied teams, then H2H point difference, then overall point difference
    (the season simulator's tiebreaker). A game counts toward round R when its
    scheduled gameday <= R and it has been played.
    Returns (codes in current order, {code: [rank after round 1..R]})."""
    from simulate_monte_carlo import _rank_with_h2h
    from team_aliases import team_code

    gc_round, codes = {}, set()
    for row in schedule_rows or []:
        if row.get('round') != 'RS':
            continue
        gc = int(str(row.get('gamecode', '0')).split('_')[-1])
        gc_round[gc] = int(row.get('gameday') or 0)
        for name_key, code_key in (('hometeam', 'homecode'), ('awayteam', 'awaycode')):
            code = team_code(row.get(name_key), default=row.get(code_key) or 'UNK')
            if code != 'UNK':
                codes.add(code)

    played = []
    for g in game_results or []:
        gc = int(g.get('GameCode') or 0)
        hs, as_ = int(g.get('LocalScore') or 0), int(g.get('RoadScore') or 0)
        if gc in gc_round and hs > 0 and as_ > 0:
            played.append((gc_round[gc], g['LocalTeam'], g['RoadTeam'], hs, as_))
            codes.update((g['LocalTeam'], g['RoadTeam']))

    codes = sorted(codes)
    idx = {t: i for i, t in enumerate(codes)}
    n = len(codes)
    history = {t: [] for t in codes}
    last_round = max((p[0] for p in played), default=0)
    for R in range(1, last_round + 1):
        w = np.zeros((1, n)); pdiff = np.zeros((1, n))
        hw = np.zeros((1, n, n)); hp = np.zeros((1, n, n))
        for rnd, h, a, hs, as_ in played:
            if rnd > R:
                continue
            i, j, m = idx[h], idx[a], hs - as_
            win, lose = (i, j) if m > 0 else (j, i)
            w[0, win] += 1
            hw[0, win, lose] += 1
            pdiff[0, i] += m; pdiff[0, j] -= m
            hp[0, i, j] += m; hp[0, j, i] -= m
        ranks = _rank_with_h2h(w, pdiff, hw, hp, n, 1)[0]
        for t in codes:
            history[t].append(int(ranks[idx[t]]) + 1)
    order = sorted(codes, key=lambda t: history[t][-1]) if last_round else codes
    return order, history


```

Check `team_aliases.team_code`'s real signature (`team_code(name, default="UNK")`) before relying on it.

- [ ] **Step 5: Run the tests** — all 6 pass. (`test_team_without_games_is_ranked` accepts rank 2 or 3 for CCC — BBB and CCC both have 0 wins; their order is whatever the tiebreaker yields.)

- [ ] **Step 6: Use it in `main()`** — replace

```python
    # Sort: wins desc, then adj_net desc
    teams.sort(key=lambda t: (-t['wins'], -t['adj_net']))
```

with

```python
    # Official Euroleague order (wins, H2H, H2H point diff, point diff), also
    # after every round for the Standings Race chart.
    standings_order, rank_history = official_standings(
        load_json('mvp_game_results.json'), load_json(f'schedule_{S}.json'))
    position = {code: i + 1 for i, code in enumerate(standings_order)}
    for t in teams:
        t['position'] = position.get(t['team'])
        t['rank_history'] = rank_history.get(t['team'], [])
    teams.sort(key=lambda t: (t['position'] is None, t['position'] or 0,
                              -t['wins'], -t['adj_net']))
```

Leave `# Already sorted by wins desc, adj_net desc` comments near `seeded = teams[:10]` updated to `# Already in official standings order`.

- [ ] **Step 7: Check on real data** — run:

```bash
.venv/Scripts/python.exe -c "
import json, export_dashboard_data as e
o, h = e.official_standings(e.load_json('mvp_game_results.json'), e.load_json(f'schedule_{e.S}.json'))
print(len(o), o); print({t: h[t] for t in o[:6]})
"
```
Expected: 20 codes; each history has 4 entries; the 4-0 teams (PAN, PAM) first two, the 3-1 teams (ULK, OLY, PAR) next.

- [ ] **Step 8: Full suite + commit** — `.venv/Scripts/python.exe -m pytest tests/ -q`; `git add export_dashboard_data.py tests/test_official_standings.py && git commit -m "feat: official Euroleague standings order (H2H tiebreak) per round in the export"`.

---

### Task 2: Frontend uses the official order

**Files:** `docs/season.js` (standings table default sort ~line 12/164; `renderStandingsTimeline` ~line 854), `docs/playoffs.js` (~line 176)

- [ ] **Step 1: Standings table** — in `docs/season.js`, the table's default sort is `let sortState = { col: 'wins', asc: false };`. In `renderStandings(teams)` (before the first render), if every team has a numeric `position`, set `sortState = { col: 'position', asc: true }` (only on first render — don't override a user's later click). Keep `wins` as the fallback when `position` is missing. The `#` column must show the row's position in the current sort as today.

- [ ] **Step 2: Standings Race chart** — in `renderStandingsTimeline(teams)`:
  - If every team has a non-empty `rank_history` of equal length, use it: `maxRound = rank_history.length`, `ranks[i][team] = rank_history[i]`. Otherwise keep the existing computation (fallback for old dashboards).
  - Update the comment `// Compute rank at each round (1 = best, ties broken by team name …)` to say the export provides official ranks and this is the fallback.
  - Change `line: { color, width: 2.5, shape: 'spline' }` to `line: { color, width: 2.5, shape: 'linear' }`.
  - Make the x axis show every round as an integer tick: set `xaxis.dtick = 1` and `xaxis.tick0 = 1` in the layout (merge with the existing xaxis object).
  - Hover text keeps "Round r: Rank #n · Record w-l".

- [ ] **Step 3: Playoff seeds** — in `docs/playoffs.js` change

```javascript
        _teams = (data.teams || []).sort((a, b) =>
            b.wins - a.wins || b.adj_net - a.adj_net
        );
```

to

```javascript
        // Official standings order from the export; fall back for old dashboards.
        _teams = (data.teams || []).sort((a, b) =>
            (a.position != null && b.position != null)
                ? a.position - b.position
                : (b.wins - a.wins || b.adj_net - a.adj_net)
        );
```

- [ ] **Step 4:** grep `docs/*.js` for other places that rank teams by `wins` then `adj_net` to derive a *standings position or seed* (not a stat sort), e.g. `season.js:364`; list them in the report and switch any that represent the standings order to `position` with the same fallback. Leave stat-specific sorts alone.

- [ ] **Step 5:** `node --check docs/season.js docs/playoffs.js`. Commit: `fix: standings table, bracket seeds and Standings Race use the official order; straight lines`.

---

### Task 3: Regenerate + verify

- [ ] **Step 1:** `EUROLEAGUE_ROUND_SUFFIX=_R4 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe export_dashboard_data.py`
- [ ] **Step 2:** In `docs/data/current/dashboard.json`: every team has `position` 1..20 (unique) and a 4-entry `rank_history`; `teams` is in `position` order; the last `rank_history` entry equals `position`.
- [ ] **Step 3:** Browser (serve docs on 8765): index.html standings table order equals `position`; the Standings Race chart has straight segments, integer round ticks 1–4, and its round-4 ranks equal the table positions for the visible teams (read via `document.getElementById('standings-timeline').data`); playoffs.html bracket seeds 1–10 equal `position` 1–10; no new console errors. Also load `docs/data/archive/2025/dashboard.json`-backed pages (series.html, title-race.html) to confirm nothing broke.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/ -q`; commit regenerated `docs/data/current/*.json`: `chore: regenerate dashboard with official standings order`.
