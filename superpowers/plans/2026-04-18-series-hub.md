# Series Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated `series.html` page that drills into each of the 7 playoff series (4 QFs + 2 SFs + Final), showing series hero, game-by-game timeline, regular-season H2H, and recap cards.

**Architecture:** Server-side aggregation in `export_dashboard_data.py` → new `"series"` key in `dashboard.json` → client-side rendering in new `docs/series.html` + `docs/series.js`. Per-series win probabilities piggyback on the existing Monte Carlo sim in `compute_championship_odds`. Slot-based URLs (`?id=qf1..qf4,sf1,sf2,final`) match existing `_bracket` indexing in `docs/playoffs.js`.

**Tech Stack:** Python 3 (pandas, stdlib), vanilla HTML/CSS/JS. No framework, no build step. Tests use AST extraction pattern (matches `test_path_to_title_play_in_states.py`).

**Spec:** [docs/superpowers/specs/2026-04-18-series-hub-design.md](../specs/2026-04-18-series-hub-design.md)

---

## File Structure

**Created:**
- `docs/series.html` — standalone page shell
- `docs/series.js` — URL parsing + rendering for all 4 sections
- `test_series_data.py` — unit tests for `compute_series_data`

**Modified:**
- `export_dashboard_data.py`:
  - `compute_championship_odds` — extended to also return per-series win probabilities
  - New `compute_series_data` function (nested inside `main()`)
  - `main()` — call `compute_series_data`, write `"series"` key to dashboard.json
- `docs/playoffs.js` — wrap bracket matchup lines and recap cards in `<a href="series.html?id=...">`
- `docs/style.css` — add series-specific classes (`.series-hero`, `.series-timeline`, `.series-game-box`, `.series-h2h-card`, `.series-prob-bar`)
- `docs/about.html` — paragraph about Series Hub under the Playoffs description

---

## Task 1: Extend Monte Carlo to return per-series win probabilities

**Goal:** Modify `compute_championship_odds` so each simulated bracket also records which team won each of the 7 series slots. Return a dict `{championship: {...}, series: {...}}` instead of bare championship odds.

**Files:**
- Modify: `export_dashboard_data.py:1423-1549` (the `compute_championship_odds` function)
- Modify: `export_dashboard_data.py:2090-2092`, `2145-2147` (call sites)
- Test: `test_series_data.py` (new)

- [ ] **Step 1: Write the failing test**

Create `test_series_data.py` at repo root:

```python
"""
Verifies compute_championship_odds returns per-series win probabilities
alongside championship odds. Extracts the nested function from
export_dashboard_data.py via AST.
"""
import ast
import os

_here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_here, 'export_dashboard_data.py'), 'r', encoding='utf-8') as f:
    src = f.read()

tree = ast.parse(src)
main_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
cco_fn = next(n for n in ast.walk(main_fn) if isinstance(n, ast.FunctionDef) and n.name == 'compute_championship_odds')

ns = {}
exec(ast.unparse(cco_fn), ns)
compute_championship_odds = ns['compute_championship_odds']

# 10 synthetic teams, higher seed favored
seeded = [{'team': f'T{i+1:02d}'} for i in range(10)]
SEEDS = [t['team'] for t in seeded]
matchup_probs = {}
for i, ta in enumerate(SEEDS):
    matchup_probs[ta] = {}
    for j, tb in enumerate(SEEDS):
        if i == j:
            continue
        p_ta = 0.65 if i < j else 0.35
        matchup_probs[ta][tb] = {'home': p_ta, 'away': p_ta - 0.1, 'neutral': p_ta - 0.05}

result = compute_championship_odds(None, matchup_probs, seeded, n_sims=2000)

assert isinstance(result, dict), f'expected dict, got {type(result)}'
assert 'championship' in result, f'missing championship key: {result.keys()}'
assert 'series' in result, f'missing series key: {result.keys()}'

champ = result['championship']
assert isinstance(champ, dict)
for code in SEEDS:
    assert code in champ, f'missing {code} in championship'
    assert 0 <= champ[code] <= 100

series = result['series']
expected_slots = {'qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final'}
assert set(series.keys()) == expected_slots, f'unexpected slots: {series.keys()}'

# Every slot should have probs summing to ~100 across the teams that could reach it
for slot, probs in series.items():
    total = sum(probs.values())
    assert 99.0 <= total <= 101.0, f'{slot} probs sum to {total}: {probs}'

# Seed 1 should win qf1 most of the time
assert series['qf1'].get('T01', 0) > series['qf1'].get('T08', 0), \
    f'qf1 higher seed should win more: {series["qf1"]}'

print('Task 1 assertions passed.')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: FAIL with `AssertionError: expected dict, got <class 'dict'>` or `missing championship key` (current return is flat `{team: odds}`).

- [ ] **Step 3: Modify `compute_championship_odds` to track per-series winners and return combined dict**

In `export_dashboard_data.py`, replace the function at lines 1423-1549 with the following. The key changes: add `series_counts` dict, record winners per slot in each sim, convert to percentages at the end, return `{'championship': ..., 'series': ...}`.

```python
    def compute_championship_odds(playoff_results, matchup_probs, seeded_teams, n_sims=50000):
        """
        Run Monte Carlo simulation of the remaining bracket from current state.

        Returns dict with:
          - 'championship': {team_code: championship_prob_pct}
          - 'series': {slot_id: {team_code: series_win_prob_pct}}

        Slot IDs: qf1..qf4 (1v8, 2v7, 3v6, 4v5), sf1 (w(qf1) vs w(qf4)),
        sf2 (w(qf2) vs w(qf3)), final.
        """
        import random
        random.seed(42)

        if len(seeded_teams) < 10:
            return {'championship': {}, 'series': {}}

        seed_codes = [t['team'] for t in seeded_teams[:10]]

        def _get_prob(team_a, team_b, venue):
            entry = (matchup_probs.get(team_a) or {}).get(team_b)
            if entry:
                return entry.get(venue, 0.5)
            return 0.5

        def _sim_game(team_a, team_b, venue):
            p = _get_prob(team_a, team_b, venue)
            return team_a if random.random() < p else team_b

        def _sim_series(higher, lower):
            home_pattern = [True, True, False, False, True]
            wins_h, wins_l = 0, 0
            for g in range(5):
                venue = 'home' if home_pattern[g] else 'away'
                winner = _sim_game(higher, lower, venue)
                if winner == higher:
                    wins_h += 1
                else:
                    wins_l += 1
                if wins_h >= 3 or wins_l >= 3:
                    break
            return higher if wins_h >= 3 else lower

        # Extract known results
        pi_a_winner = None
        pi_a_loser = None
        pi_b_winner = None
        pi_c_winner = None
        qf_winners = {'1v8': None, '2v7': None, '3v6': None, '4v5': None}
        qf_series_state = {}
        sf_winners = {'sf1': None, 'sf2': None}
        final_winner = None

        if playoff_results:
            pi = playoff_results.get('play_in', {})
            if pi.get('game_a') and pi['game_a'].get('winner'):
                pi_a_winner = pi['game_a']['winner']
                ga = pi['game_a']
                pi_a_loser = ga['away'] if ga['winner'] == ga['home'] else ga['home']
            if pi.get('game_b') and pi['game_b'].get('winner'):
                pi_b_winner = pi['game_b']['winner']
            if pi.get('game_c') and pi['game_c'].get('winner'):
                pi_c_winner = pi['game_c']['winner']

            qf_data = playoff_results.get('qf', {})
            for label in ['1v8', '2v7', '3v6', '4v5']:
                qf_entry = qf_data.get(label, {})
                if qf_entry.get('winner'):
                    qf_winners[label] = qf_entry['winner']
                elif qf_entry.get('series'):
                    qf_series_state[label] = (
                        qf_entry['series'][0], qf_entry['series'][1],
                        qf_entry.get('higher_seed'), qf_entry.get('lower_seed')
                    )

            sf_data = playoff_results.get('sf', {})
            if sf_data.get('sf1') and sf_data['sf1'].get('winner'):
                sf_winners['sf1'] = sf_data['sf1']['winner']
            if sf_data.get('sf2') and sf_data['sf2'].get('winner'):
                sf_winners['sf2'] = sf_data['sf2']['winner']

            final_data = playoff_results.get('final', {})
            if final_data.get('winner'):
                final_winner = final_data['winner']

        # Map from QF label (data-side) to slot ID (URL-side)
        qf_label_to_slot = {'1v8': 'qf1', '2v7': 'qf2', '3v6': 'qf3', '4v5': 'qf4'}

        counts = {code: 0 for code in seed_codes}
        series_counts = {slot: {} for slot in ('qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final')}

        for _ in range(n_sims):
            ga_w = pi_a_winner or _sim_game(seed_codes[6], seed_codes[7], 'home')
            ga_l = pi_a_loser or (seed_codes[7] if ga_w == seed_codes[6] else seed_codes[6])
            gb_w = pi_b_winner or _sim_game(seed_codes[8], seed_codes[9], 'home')
            gc_w = pi_c_winner or _sim_game(ga_l, gb_w, 'home')

            s7 = ga_w
            s8 = gc_w

            qf_pairs = {
                '1v8': (seed_codes[0], s8),
                '2v7': (seed_codes[1], s7),
                '3v6': (seed_codes[2], seed_codes[5]),
                '4v5': (seed_codes[3], seed_codes[4]),
            }

            qf_w = {}
            for label, (higher, lower) in qf_pairs.items():
                if qf_winners[label]:
                    qf_w[label] = qf_winners[label]
                elif label in qf_series_state:
                    h_wins, l_wins, h_seed, l_seed = qf_series_state[label]
                    while h_wins < 3 and l_wins < 3:
                        game_num = h_wins + l_wins
                        home_pattern = [True, True, False, False, True]
                        venue = 'home' if home_pattern[game_num] else 'away'
                        w = _sim_game(h_seed, l_seed, venue)
                        if w == h_seed:
                            h_wins += 1
                        else:
                            l_wins += 1
                    qf_w[label] = h_seed if h_wins >= 3 else l_seed
                else:
                    qf_w[label] = _sim_series(higher, lower)

                slot = qf_label_to_slot[label]
                series_counts[slot][qf_w[label]] = series_counts[slot].get(qf_w[label], 0) + 1

            sf1_w = sf_winners['sf1'] or _sim_game(qf_w['1v8'], qf_w['4v5'], 'neutral')
            sf2_w = sf_winners['sf2'] or _sim_game(qf_w['2v7'], qf_w['3v6'], 'neutral')
            series_counts['sf1'][sf1_w] = series_counts['sf1'].get(sf1_w, 0) + 1
            series_counts['sf2'][sf2_w] = series_counts['sf2'].get(sf2_w, 0) + 1

            champ = final_winner or _sim_game(sf1_w, sf2_w, 'neutral')
            series_counts['final'][champ] = series_counts['final'].get(champ, 0) + 1
            counts[champ] += 1

        championship_pcts = {code: round(count / n_sims * 100, 1) for code, count in counts.items()}
        series_pcts = {
            slot: {team: round(c / n_sims * 100, 1) for team, c in team_counts.items()}
            for slot, team_counts in series_counts.items()
        }

        return {'championship': championship_pcts, 'series': series_pcts}
```

- [ ] **Step 4: Update the two call sites in `main()` to unpack the new return shape**

In `export_dashboard_data.py`, around line 2090:

```python
            # Compute current championship odds
            mc_result = compute_championship_odds(
                playoff_results_data, playoff_matchup_probs, seeded
            )
            championship_odds = mc_result['championship']
            series_win_probs = mc_result['series']
```

And around line 2145 (pre-playoff branch):

```python
                if not championship_odds_history:
                    mc_result = compute_championship_odds(
                        None, playoff_matchup_probs, seeded
                    )
                    championship_odds = mc_result['championship']
                    series_win_probs = mc_result['series']
```

Before the `if playoff_results_data:` block (around line 2081), add a default:

```python
    series_win_probs = {}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: PASS — prints `Task 1 assertions passed.`

- [ ] **Step 6: Smoke-test the pipeline still runs**

Run: `EUROLEAGUE_ROUND_SUFFIX=_R38 .venv/Scripts/python.exe export_dashboard_data.py`
Expected: Runs to completion, no exceptions. Output mentions "Championship odds computed for N contending teams".

- [ ] **Step 7: Commit**

```bash
git add export_dashboard_data.py test_series_data.py
git commit -m "feat: extend MC sim to track per-series win probabilities

compute_championship_odds now returns a dict with both championship odds
and per-series win probabilities for the 7 playoff slots (qf1..qf4, sf1,
sf2, final). Needed for the upcoming Series Hub page. No functional
change to championship odds; only the return shape changed.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Scaffold `compute_series_data` — seeds and slot structure

**Goal:** Add a new nested function `compute_series_data` inside `main()` that builds the 7 slot entries with id, round, label, format, home_pattern, high_seed, and low_seed. Low seeds may be null if unresolved (e.g., sf1 before QFs done). No state/games/h2h yet.

**Files:**
- Modify: `export_dashboard_data.py` (add new function just after `build_playoff_recaps`, before the `# ── Build output ──` block near line 2073)
- Test: `test_series_data.py`

- [ ] **Step 1: Write the failing test**

Append to `test_series_data.py`:

```python
# ── Task 2: compute_series_data scaffolding ────────────────────────────────
csd_fn = next(n for n in ast.walk(main_fn) if isinstance(n, ast.FunctionDef) and n.name == 'compute_series_data')
ns2 = {}
exec(ast.unparse(csd_fn), ns2)
compute_series_data = ns2['compute_series_data']

# Empty series_win_probs dict (not yet wired) - we test slot structure first
import pandas as pd
empty_games_df = pd.DataFrame(columns=['round', 'homecode', 'awaycode', 'homescore', 'awayscore', 'played'])

# --- Pre-playoff state ---
result = compute_series_data(None, matchup_probs, seeded, {}, empty_games_df)
assert isinstance(result, dict)
assert set(result.keys()) == {'qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final'}

qf1 = result['qf1']
assert qf1['id'] == 'qf1'
assert qf1['round'] == 'qf'
assert qf1['label'] == 'Quarterfinal 1'
assert qf1['format'] == 'best_of_5'
assert qf1['home_pattern'] == ['high', 'high', 'low', 'low', 'high']
assert qf1['high_seed'] == {'team': 'T01', 'seed': 1}
assert qf1['low_seed'] == {'team': 'T08', 'seed': 8}

qf2 = result['qf2']
assert qf2['high_seed'] == {'team': 'T02', 'seed': 2}
assert qf2['low_seed'] == {'team': 'T07', 'seed': 7}

qf3 = result['qf3']
assert qf3['high_seed'] == {'team': 'T03', 'seed': 3}
assert qf3['low_seed'] == {'team': 'T06', 'seed': 6}

qf4 = result['qf4']
assert qf4['high_seed'] == {'team': 'T04', 'seed': 4}
assert qf4['low_seed'] == {'team': 'T05', 'seed': 5}

# SF/Final slots start unresolved pre-playoff
sf1 = result['sf1']
assert sf1['id'] == 'sf1'
assert sf1['round'] == 'sf'
assert sf1['high_seed'] is None and sf1['low_seed'] is None

finals = result['final']
assert finals['round'] == 'final'
assert finals['high_seed'] is None and finals['low_seed'] is None

print('Task 2 assertions passed.')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: FAIL with `StopIteration` (function `compute_series_data` not yet defined).

- [ ] **Step 3: Add the `compute_series_data` function**

In `export_dashboard_data.py`, find the line `# ── Build output ─────────────────────────────────────────────────────────` around line 2073. Insert the following function just above it (after `build_playoff_recaps`):

```python
    def compute_series_data(playoff_results, matchup_probs, seeded_teams, series_win_probs, games_df):
        """
        Build per-series entries for Series Hub pages.

        Returns dict keyed by slot_id (qf1..qf4, sf1, sf2, final). Each entry has
        id, round, label, format, home_pattern, high_seed, low_seed, status, wins,
        winner, series_win_prob, games[], rs_h2h[].

        Seeds resolve left-to-right: QFs populate from initial seeding; SFs/Final
        populate once prerequisite series are decided. Unresolved sides remain null.
        """
        if len(seeded_teams) < 10:
            return {}

        seed_codes = [t['team'] for t in seeded_teams[:10]]

        def _seed_obj(code, seed_num):
            if not code:
                return None
            return {'team': code, 'seed': seed_num}

        # Pull resolved winners from playoff_results (safe if None)
        qf_winners = {'1v8': None, '2v7': None, '3v6': None, '4v5': None}
        sf_winners = {'sf1': None, 'sf2': None}
        final_winner = None
        pi_a_winner = None
        pi_c_winner = None
        if playoff_results:
            for label in qf_winners:
                entry = (playoff_results.get('qf') or {}).get(label) or {}
                if entry.get('winner'):
                    qf_winners[label] = entry['winner']
            sf_data = playoff_results.get('sf') or {}
            if sf_data.get('sf1') and sf_data['sf1'].get('winner'):
                sf_winners['sf1'] = sf_data['sf1']['winner']
            if sf_data.get('sf2') and sf_data['sf2'].get('winner'):
                sf_winners['sf2'] = sf_data['sf2']['winner']
            final_data = playoff_results.get('final') or {}
            if final_data.get('winner'):
                final_winner = final_data['winner']
            pi = playoff_results.get('play_in') or {}
            if pi.get('game_a') and pi['game_a'].get('winner'):
                pi_a_winner = pi['game_a']['winner']
            if pi.get('game_c') and pi['game_c'].get('winner'):
                pi_c_winner = pi['game_c']['winner']

        # QF seedings: 1v8, 2v7, 3v6, 4v5 — resolve 7/8 seeds from play-in if known
        seed_7_team = pi_a_winner or seed_codes[6]
        seed_8_team = pi_c_winner
        # If Game C hasn't happened but we can trivially deduce (no play-in needed in this season?)
        # Leave seed_8_team as None if Game C isn't decided yet.

        qf_seeding = {
            'qf1': (_seed_obj(seed_codes[0], 1), _seed_obj(seed_8_team, 8)),
            'qf2': (_seed_obj(seed_codes[1], 2), _seed_obj(seed_7_team, 7)),
            'qf3': (_seed_obj(seed_codes[2], 3), _seed_obj(seed_codes[5], 6)),
            'qf4': (_seed_obj(seed_codes[3], 4), _seed_obj(seed_codes[4], 5)),
        }

        # SF seedings: winners of QFs — null until QFs resolve
        sf1_high = _seed_obj(qf_winners['1v8'], None) if qf_winners['1v8'] else None
        sf1_low = _seed_obj(qf_winners['4v5'], None) if qf_winners['4v5'] else None
        sf2_high = _seed_obj(qf_winners['2v7'], None) if qf_winners['2v7'] else None
        sf2_low = _seed_obj(qf_winners['3v6'], None) if qf_winners['3v6'] else None
        final_high = _seed_obj(sf_winners['sf1'], None) if sf_winners['sf1'] else None
        final_low = _seed_obj(sf_winners['sf2'], None) if sf_winners['sf2'] else None

        slot_defs = {
            'qf1':   {'round': 'qf',    'label': 'Quarterfinal 1', 'seeds': qf_seeding['qf1']},
            'qf2':   {'round': 'qf',    'label': 'Quarterfinal 2', 'seeds': qf_seeding['qf2']},
            'qf3':   {'round': 'qf',    'label': 'Quarterfinal 3', 'seeds': qf_seeding['qf3']},
            'qf4':   {'round': 'qf',    'label': 'Quarterfinal 4', 'seeds': qf_seeding['qf4']},
            'sf1':   {'round': 'sf',    'label': 'Semifinal 1',    'seeds': (sf1_high, sf1_low)},
            'sf2':   {'round': 'sf',    'label': 'Semifinal 2',    'seeds': (sf2_high, sf2_low)},
            'final': {'round': 'final', 'label': 'Final',          'seeds': (final_high, final_low)},
        }

        result = {}
        for slot_id, defn in slot_defs.items():
            high, low = defn['seeds']
            result[slot_id] = {
                'id': slot_id,
                'round': defn['round'],
                'label': defn['label'],
                'format': 'best_of_5',
                'home_pattern': ['high', 'high', 'low', 'low', 'high'],
                'high_seed': high,
                'low_seed': low,
                'status': 'not_started',
                'wins': {'high': 0, 'low': 0},
                'winner': None,
                'series_win_prob': {'high': 0.0, 'low': 0.0},
                'games': [],
                'rs_h2h': [],
            }

        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: PASS — prints both `Task 1 assertions passed.` and `Task 2 assertions passed.`

- [ ] **Step 5: Commit**

```bash
git add export_dashboard_data.py test_series_data.py
git commit -m "feat: scaffold compute_series_data with slot seeding

Introduces the 7 playoff slot entries (qf1..qf4, sf1, sf2, final) with
high/low seed resolution. QFs populate from initial seeding; SFs/Final
remain unresolved until prerequisites decide. State, games, and H2H
fields are stubbed and filled in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: `compute_series_data` — series state, wins, games array

**Goal:** Populate `status`, `wins`, `winner`, `games` (5-length array with completed games, upcoming dates, and pregame WPs) per slot. Handles sweep (unnecessary games). Wires in `series_win_probs`.

**Files:**
- Modify: `export_dashboard_data.py` — the `compute_series_data` function
- Test: `test_series_data.py`

- [ ] **Step 1: Write the failing test**

Append to `test_series_data.py`:

```python
# ── Task 3: state + games ──────────────────────────────────────────────────

# Build a playoff_results with QF1 at 2-1 in favor of T01 (3 completed games)
# and qf2 swept 3-0 by T02
pr_state = {
    'play_in': {'game_a': None, 'game_b': None, 'game_c': None},
    'qf': {
        '1v8': {
            'higher_seed': 'T01', 'lower_seed': 'T08',
            'series': [2, 1],
            'winner': None,
            'games': [
                {'game_num': 1, 'date': '2026-04-21', 'home': 'T01', 'away': 'T08',
                 'home_score': 90, 'away_score': 75, 'winner': 'T01', 'gamecode': 401},
                {'game_num': 2, 'date': '2026-04-23', 'home': 'T01', 'away': 'T08',
                 'home_score': 80, 'away_score': 88, 'winner': 'T08', 'gamecode': 402},
                {'game_num': 3, 'date': '2026-04-26', 'home': 'T08', 'away': 'T01',
                 'home_score': 70, 'away_score': 85, 'winner': 'T01', 'gamecode': 403},
            ],
        },
        '2v7': {
            'higher_seed': 'T02', 'lower_seed': 'T07',
            'series': [3, 0],
            'winner': 'T02',
            'games': [
                {'game_num': 1, 'date': '2026-04-21', 'home': 'T02', 'away': 'T07',
                 'home_score': 95, 'away_score': 78, 'winner': 'T02', 'gamecode': 404},
                {'game_num': 2, 'date': '2026-04-23', 'home': 'T02', 'away': 'T07',
                 'home_score': 88, 'away_score': 85, 'winner': 'T02', 'gamecode': 405},
                {'game_num': 3, 'date': '2026-04-26', 'home': 'T07', 'away': 'T02',
                 'home_score': 79, 'away_score': 82, 'winner': 'T02', 'gamecode': 406},
            ],
        },
        '3v6': {'higher_seed': 'T03', 'lower_seed': 'T06', 'series': [0, 0], 'winner': None, 'games': []},
        '4v5': {'higher_seed': 'T04', 'lower_seed': 'T05', 'series': [0, 0], 'winner': None, 'games': []},
    },
    'sf': {'sf1': None, 'sf2': None},
    'final': {},
}

# Synthetic series_win_probs
swp = {
    'qf1': {'T01': 72.0, 'T08': 28.0},
    'qf2': {'T02': 100.0},   # completed
    'qf3': {'T03': 60.0, 'T06': 40.0},
    'qf4': {'T04': 55.0, 'T05': 45.0},
    'sf1': {'T01': 40.0, 'T04': 30.0, 'T05': 20.0, 'T08': 10.0},
    'sf2': {'T02': 50.0, 'T03': 30.0, 'T06': 20.0},
    'final': {'T01': 25.0, 'T02': 30.0, 'T03': 15.0, 'T04': 12.0, 'T05': 8.0, 'T06': 5.0, 'T08': 5.0},
}

result = compute_series_data(pr_state, matchup_probs, seeded, swp, empty_games_df)

# qf1: in progress, 2-1
qf1 = result['qf1']
assert qf1['status'] == 'in_progress', qf1['status']
assert qf1['wins'] == {'high': 2, 'low': 1}, qf1['wins']
assert qf1['winner'] is None
assert qf1['series_win_prob'] == {'high': 72.0, 'low': 28.0}, qf1['series_win_prob']

# 5 game entries total
assert len(qf1['games']) == 5
g1 = qf1['games'][0]
assert g1['status'] == 'completed'
assert g1['home'] == 'T01' and g1['away'] == 'T08'
assert g1['home_score'] == 90 and g1['away_score'] == 75
assert g1['winner'] == 'T01'
assert g1['gamecode'] == 401

g4 = qf1['games'][3]
assert g4['status'] == 'upcoming', g4['status']
assert g4['game_num'] == 4
assert g4['home'] == 'T08'   # home_pattern[3] = 'low' = T08
assert g4['away'] == 'T01'
assert 'pregame_wp' in g4
assert 'home' in g4['pregame_wp'] and 'away' in g4['pregame_wp']

# qf2: sweep, winner set, status completed
qf2 = result['qf2']
assert qf2['status'] == 'completed'
assert qf2['winner'] == 'T02'
assert qf2['wins'] == {'high': 3, 'low': 0}
assert qf2['series_win_prob'] == {'high': 100.0, 'low': 0.0}

# qf2 games: 3 completed, G4/G5 marked unnecessary (sweep)
assert len(qf2['games']) == 5
assert qf2['games'][3]['status'] == 'unnecessary'
assert qf2['games'][4]['status'] == 'unnecessary'

# qf3: not_started, all 5 upcoming
qf3 = result['qf3']
assert qf3['status'] == 'not_started'
assert qf3['winner'] is None
assert all(g['status'] == 'upcoming' for g in qf3['games'])

print('Task 3 assertions passed.')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: FAIL — qf1.status is still 'not_started' and games is empty.

- [ ] **Step 3: Extend `compute_series_data` with state + games logic**

In `export_dashboard_data.py`, find `compute_series_data`. Replace the final loop (the one that builds `result[slot_id]`) with the following richer version, and add the helper functions above it. The rest of the function (slot_defs setup) stays the same.

```python
        # --- Helpers for state + games ---
        qf_label_for_slot = {'qf1': '1v8', 'qf2': '2v7', 'qf3': '3v6', 'qf4': '4v5'}

        def _build_prob_pair(slot_id, high_code, low_code):
            sp = series_win_probs.get(slot_id, {}) if series_win_probs else {}
            h = round(sp.get(high_code, 0.0), 1) if high_code else 0.0
            l = round(sp.get(low_code, 0.0), 1) if low_code else 0.0
            return {'high': h, 'low': l}

        def _schedule_home(game_num, high_code, low_code):
            """Venue per home_pattern: G1/G2/G5 = high, G3/G4 = low."""
            pattern = ['high', 'high', 'low', 'low', 'high']
            side = pattern[game_num - 1]
            if side == 'high':
                return high_code, low_code
            return low_code, high_code

        def _build_games(completed_games, high_code, low_code, wins_h, wins_l, status):
            """Build the 5-entry games array from known completed games + schedule."""
            games = []
            completed_by_num = {g.get('game_num', idx + 1): g for idx, g in enumerate(completed_games)}
            sweep_or_done = status == 'completed'
            games_played = wins_h + wins_l

            for game_num in range(1, 6):
                gc = completed_by_num.get(game_num)
                if gc:
                    games.append({
                        'game_num': game_num,
                        'status': 'completed',
                        'date': gc.get('date', ''),
                        'home': gc.get('home'),
                        'away': gc.get('away'),
                        'home_score': gc.get('home_score'),
                        'away_score': gc.get('away_score'),
                        'winner': gc.get('winner'),
                        'gamecode': gc.get('gamecode'),
                    })
                    continue

                # Unnecessary if series already decided
                if sweep_or_done and game_num > games_played:
                    games.append({
                        'game_num': game_num,
                        'status': 'unnecessary',
                        'home': None,
                        'away': None,
                    })
                    continue

                # Upcoming: compute venue + pregame WP
                if not high_code or not low_code:
                    games.append({
                        'game_num': game_num,
                        'status': 'upcoming',
                        'home': None,
                        'away': None,
                    })
                    continue

                home_code, away_code = _schedule_home(game_num, high_code, low_code)
                venue = 'home'
                home_prob_entry = (matchup_probs.get(home_code) or {}).get(away_code) or {}
                p_home = home_prob_entry.get(venue, 0.5)
                games.append({
                    'game_num': game_num,
                    'status': 'upcoming',
                    'home': home_code,
                    'away': away_code,
                    'pregame_wp': {
                        'home': round(p_home * 100, 1),
                        'away': round((1 - p_home) * 100, 1),
                    },
                })

            return games

        result = {}
        for slot_id, defn in slot_defs.items():
            high, low = defn['seeds']
            high_code = high['team'] if high else None
            low_code = low['team'] if low else None

            # State from playoff_results
            wins_h, wins_l = 0, 0
            winner = None
            status = 'not_started'
            completed_games = []

            if slot_id.startswith('qf') and playoff_results:
                qf_label = qf_label_for_slot[slot_id]
                qf_entry = (playoff_results.get('qf') or {}).get(qf_label) or {}
                series = qf_entry.get('series') or [0, 0]
                wins_h, wins_l = series[0], series[1]
                winner = qf_entry.get('winner')
                completed_games = qf_entry.get('games') or []
            elif slot_id in ('sf1', 'sf2') and playoff_results:
                sf_entry = (playoff_results.get('sf') or {}).get(slot_id) or {}
                if sf_entry.get('winner'):
                    # SF winners are single-game in Euroleague's current format
                    winner = sf_entry['winner']
                    if winner == high_code:
                        wins_h = 1
                    else:
                        wins_l = 1
                    completed_games = [sf_entry] if sf_entry else []
            elif slot_id == 'final' and playoff_results:
                final_entry = (playoff_results.get('final') or {}).get('game') or {}
                final_winner_code = (playoff_results.get('final') or {}).get('winner')
                if final_winner_code:
                    winner = final_winner_code
                    if winner == high_code:
                        wins_h = 1
                    else:
                        wins_l = 1
                    completed_games = [final_entry] if final_entry else []

            if winner:
                status = 'completed'
            elif wins_h > 0 or wins_l > 0:
                status = 'in_progress'

            games = _build_games(completed_games, high_code, low_code, wins_h, wins_l, status)

            result[slot_id] = {
                'id': slot_id,
                'round': defn['round'],
                'label': defn['label'],
                'format': 'best_of_5',
                'home_pattern': ['high', 'high', 'low', 'low', 'high'],
                'high_seed': high,
                'low_seed': low,
                'status': status,
                'wins': {'high': wins_h, 'low': wins_l},
                'winner': winner,
                'series_win_prob': _build_prob_pair(slot_id, high_code, low_code),
                'games': games,
                'rs_h2h': [],
            }

        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: PASS — all 3 task assertion blocks.

- [ ] **Step 5: Commit**

```bash
git add export_dashboard_data.py test_series_data.py
git commit -m "feat: populate series state, wins, and games in compute_series_data

Series slots now carry status (not_started/in_progress/completed), wins
(high vs low), winner, and a 5-entry games array. Completed games are
pulled from playoff_results; upcoming games get pregame WP from
matchup_probs using the standard 2-2-1 home_pattern. Sweep handling
marks unplayed games as 'unnecessary'.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: `compute_series_data` — regular-season H2H

**Goal:** Populate `rs_h2h` per slot by filtering `games_df` to regular-season games between the two seeded teams. Handle 0/1/2 meetings.

**Files:**
- Modify: `export_dashboard_data.py` — the `compute_series_data` function (add H2H section)
- Test: `test_series_data.py`

- [ ] **Step 1: Write the failing test**

Append to `test_series_data.py`:

```python
# ── Task 4: RS H2H ─────────────────────────────────────────────────────────

# Build a synthetic games_df with 2 RS meetings between T01 and T08
rs_games = pd.DataFrame([
    {'round': 'RS', 'homecode': 'T01', 'awaycode': 'T08', 'homescore': 84,
     'awayscore': 79, 'played': True, 'gameday': 7},
    {'round': 'RS', 'homecode': 'T08', 'awaycode': 'T01', 'homescore': 91,
     'awayscore': 88, 'played': True, 'gameday': 22},
    {'round': 'RS', 'homecode': 'T02', 'awaycode': 'T07', 'homescore': 80,
     'awayscore': 75, 'played': True, 'gameday': 10},
    # T03/T06 have no RS meetings
])

result = compute_series_data(None, matchup_probs, seeded, {}, rs_games)

qf1 = result['qf1']
assert len(qf1['rs_h2h']) == 2, f'expected 2 rs_h2h, got {len(qf1["rs_h2h"])}'
m0 = qf1['rs_h2h'][0]
assert m0['home'] == 'T01' and m0['away'] == 'T08'
assert m0['home_score'] == 84 and m0['away_score'] == 79
assert m0['winner'] == 'T01'
assert m0['round'] == 7

m1 = qf1['rs_h2h'][1]
assert m1['home'] == 'T08' and m1['away'] == 'T01'
assert m1['winner'] == 'T08'
assert m1['round'] == 22

# qf2: 1 meeting
qf2 = result['qf2']
assert len(qf2['rs_h2h']) == 1
assert qf2['rs_h2h'][0]['winner'] == 'T02'

# qf3: 0 meetings
qf3 = result['qf3']
assert qf3['rs_h2h'] == []

# SF/Final slots (unresolved seeds): no H2H
assert result['sf1']['rs_h2h'] == []

print('Task 4 assertions passed.')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: FAIL — `rs_h2h` is currently always `[]`.

- [ ] **Step 3: Add H2H lookup inside `compute_series_data`**

In `export_dashboard_data.py`, inside `compute_series_data`, locate the final `result[slot_id] = { ... 'rs_h2h': [] }` block. Add a helper function above the main loop:

```python
        def _rs_h2h(team_a, team_b):
            if not team_a or not team_b or games_df is None or len(games_df) == 0:
                return []
            df = games_df[
                (games_df['round'] == 'RS') &
                (games_df['played'] == True) &
                (
                    ((games_df['homecode'] == team_a) & (games_df['awaycode'] == team_b)) |
                    ((games_df['homecode'] == team_b) & (games_df['awaycode'] == team_a))
                )
            ]
            meetings = []
            for _, row in df.iterrows():
                home = row['homecode']
                away = row['awaycode']
                hs = int(row['homescore']) if row['homescore'] else 0
                aws = int(row['awayscore']) if row['awayscore'] else 0
                winner = home if hs > aws else away
                meetings.append({
                    'round': int(row.get('gameday') or 0),
                    'home': home,
                    'away': away,
                    'home_score': hs,
                    'away_score': aws,
                    'winner': winner,
                })
            meetings.sort(key=lambda m: m['round'])
            return meetings
```

Then in the final loop, replace `'rs_h2h': []` with:

```python
                'rs_h2h': _rs_h2h(high_code, low_code),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe test_series_data.py`
Expected: PASS — all 4 task blocks.

- [ ] **Step 5: Commit**

```bash
git add export_dashboard_data.py test_series_data.py
git commit -m "feat: add regular-season H2H lookup to compute_series_data

Each series slot now pulls RS meetings between its two teams from
games_df. Supports 0, 1, or 2 meetings. Sorted by round.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Wire `compute_series_data` into `main()` and write to `dashboard.json`

**Goal:** Call `compute_series_data` from the playoff-tracking block in `main()`, pass in `series_win_probs` from Task 1, and emit a `"series"` key in `dashboard.json`.

**Files:**
- Modify: `export_dashboard_data.py` — `main()` body near line 2120 (after `path_to_title` assignment), and the final output dict assembly

- [ ] **Step 1: Locate the output dict assembly**

Run: `grep -n "'path_to_title'" export_dashboard_data.py`
Expected: shows the line where `path_to_title` is added to the output dict, around line 2230.

- [ ] **Step 2: Load games_df once in main() (if not already available)**

In `export_dashboard_data.py`, search for `games_2025.csv` or `games_df` already being loaded. Run:

`grep -n "games_.*\.csv\|games_df" export_dashboard_data.py | head -10`

If a `games_df` is already loaded in `main()`, note its variable name and skip to Step 3. Otherwise, add this loader near the top of `main()`, after the initial prints and before the playoff-tracking block (around line 2076):

```python
    # Load raw RS games for Series Hub H2H lookups
    games_df = None
    try:
        games_csv = os.path.join('data_cache', 'games_2025.csv')
        if os.path.exists(games_csv):
            games_df = pd.read_csv(games_csv)
    except Exception as e:
        print(f"  [WARN] Could not load games_2025.csv for Series Hub: {e}")
```

- [ ] **Step 3: Call `compute_series_data` after `path_to_title` is computed**

In `export_dashboard_data.py`, find the block ending with `path_to_title = compute_path_to_title(...)` near line 2126. After that call, add:

```python
            # Build Series Hub data
            series_data = compute_series_data(
                playoff_results_data, playoff_matchup_probs, seeded,
                series_win_probs, games_df,
            )
```

Also add a default `series_data = {}` at the top of the playoff-tracking block alongside the other defaults (near line 2081):

```python
    series_data = {}
```

For the pre-playoff branch (around line 2145-2148), after `mc_result = compute_championship_odds(None, ...)` add:

```python
                if playoff_matchup_probs and len(teams) >= 10:
                    series_data = compute_series_data(
                        None, playoff_matchup_probs, seeded, series_win_probs, games_df,
                    )
```

(Place this inside the existing `if playoff_matchup_probs and len(teams) >= 10:` block.)

- [ ] **Step 4: Add `"series"` to the output dict**

Find the final output dict assembly. Run: `grep -n "'path_to_title': path_to_title\|dashboard\[.path_to_title.\]\|output\[.path_to_title.\]" export_dashboard_data.py`

Add the line:

```python
        'series': series_data,
```

In the same dict, right after the line adding `path_to_title`.

- [ ] **Step 5: Regenerate dashboard.json and verify `"series"` key is present**

Run:
```bash
EUROLEAGUE_ROUND_SUFFIX=_R38 .venv/Scripts/python.exe export_dashboard_data.py
```
Expected: finishes without errors.

Run:
```bash
python -c "import json; d=json.load(open('docs/data/current/dashboard.json', encoding='utf-8')); print(list(d.keys())); print('series keys:', list(d.get('series', {}).keys()))"
```
Expected: top-level keys include `'series'`. Series keys include all 7 slots: `['qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final']`.

- [ ] **Step 6: Verify one slot's structure end-to-end**

Run:
```bash
python -c "
import json
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
import pprint
pprint.pprint(d['series']['qf1'])
"
```
Expected: Shows id, round, label, format, home_pattern, high_seed (seed 1 team), low_seed (seed 8 team or null if play-in not done), status='not_started' (pre-playoff), wins {high:0, low:0}, winner=null, series_win_prob with non-zero values, games array of length 5 with 'upcoming' status, rs_h2h with 0-2 entries.

- [ ] **Step 7: Commit**

```bash
git add export_dashboard_data.py
git commit -m "feat: wire compute_series_data into dashboard.json output

Series Hub data is now emitted under dashboard.json['series'], keyed by
slot id (qf1..qf4, sf1, sf2, final). Consumers: upcoming series.html
page and potentially playoffs.html for hover previews.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Create `series.html` + `series.js` skeleton with URL parsing, data fetch, and error states

**Goal:** A standalone page that reads `?id=<slot>` from the URL, fetches `dashboard.json`, renders 4 empty section containers (filled in later tasks), and handles invalid/missing `?id=`.

**Files:**
- Create: `docs/series.html`
- Create: `docs/series.js`

Before starting, inspect the existing pattern in `docs/playoffs.html` to match header/nav/style-link conventions:

```bash
head -40 docs/playoffs.html
```

- [ ] **Step 1: Create `docs/series.html`**

Write to `docs/series.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Series Hub · Euroleague Analytics</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <nav class="top-nav">
    <a href="index.html">Season</a>
    <a href="playoffs.html">Playoffs</a>
    <a href="team.html">Teams</a>
    <a href="players.html">Players</a>
    <a href="h2h.html">H2H</a>
    <a href="mvp.html">MVP</a>
    <a href="shots.html">Shots</a>
    <a href="replay.html">Replay</a>
    <a href="about.html">About</a>
  </nav>

  <main class="series-page">
    <a class="back-link" href="playoffs.html">← Back to Playoffs</a>
    <div id="series-root">Loading…</div>
  </main>

  <script src="series.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `docs/series.js` with URL parsing, fetch, and error handling**

Write to `docs/series.js`:

```javascript
// Series Hub renderer — reads ?id=<slot> from URL and renders series data from dashboard.json.

const VALID_SLOTS = ['qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final'];

function getSlotId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('id');
}

function renderError(root, msg) {
  root.innerHTML = `<div class="series-error"><h1>Series not found</h1><p>${msg}</p></div>`;
}

function renderIndex(root, series) {
  const items = VALID_SLOTS.map(id => {
    const s = series[id] || {};
    const teams = s.high_seed && s.low_seed
      ? `${s.high_seed.team} vs ${s.low_seed.team}`
      : 'TBD';
    return `<li><a href="series.html?id=${id}">${s.label || id} — ${teams}</a></li>`;
  }).join('');
  root.innerHTML = `<h1>All series</h1><ul class="series-index">${items}</ul>`;
}

async function main() {
  const root = document.getElementById('series-root');
  const slotId = getSlotId();

  let dashboard;
  try {
    const res = await fetch('data/current/dashboard.json');
    dashboard = await res.json();
  } catch (err) {
    renderError(root, 'Could not load dashboard data.');
    return;
  }

  const series = dashboard.series || {};
  if (!slotId) {
    renderIndex(root, series);
    return;
  }
  if (!VALID_SLOTS.includes(slotId)) {
    renderError(root, `Invalid series id: "${slotId}". Valid ids: ${VALID_SLOTS.join(', ')}.`);
    return;
  }

  const entry = series[slotId];
  if (!entry) {
    renderError(root, `No data available for "${slotId}".`);
    return;
  }

  renderSeries(root, entry);
}

function renderSeries(root, entry) {
  // Placeholders for Tasks 7-10
  root.innerHTML = `
    <section id="series-hero" class="series-section"></section>
    <section id="series-timeline" class="series-section"></section>
    <section id="series-h2h" class="series-section"></section>
    <section id="series-recaps" class="series-section"></section>
  `;
  // Temporary: show raw JSON so we can sanity-check data flow
  document.getElementById('series-hero').innerText = `Loaded ${entry.label}`;
}

main();
```

- [ ] **Step 3: Manual smoke test**

Start a local server from the repo root:
```bash
python -m http.server 8000 --directory docs
```

Open in browser:
- `http://localhost:8000/series.html?id=qf1` — Expected: "Loaded Quarterfinal 1"
- `http://localhost:8000/series.html?id=bogus` — Expected: "Series not found · Invalid series id…"
- `http://localhost:8000/series.html` — Expected: index listing all 7 slots with their current teams or TBD

Stop the server with Ctrl-C.

- [ ] **Step 4: Commit**

```bash
git add docs/series.html docs/series.js
git commit -m "feat: add series.html skeleton with URL routing and error states

New standalone page series.html?id=<slot> loads dashboard.json and
dispatches to the correct series entry. Invalid/missing ids fall back
to an error message or index listing. Section containers are empty
placeholders to be filled in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Render Section 1 — Series Hero

**Goal:** Render the top banner: team logos, names, seeds, current series score, best-of-5 label, home pattern, and a horizontal WP bar. Handles `not_started`, `in_progress`, `completed`, and TBD-seed states.

**Files:**
- Modify: `docs/series.js` — replace placeholder `renderSeries` body

First, inspect the existing `TEAM_NAMES` map in `docs/season.js` or `docs/players.js` to verify import path for team full names:

```bash
grep -n "TEAM_NAMES\s*=" docs/season.js docs/players.js docs/playoffs.js | head -5
```

- [ ] **Step 1: Add a `TEAM_NAMES` reference inside `series.js`**

If `season.js` exports `TEAM_NAMES` globally via a `<script>` tag inclusion, include it. Otherwise define inline. Add this near the top of `docs/series.js` (after `VALID_SLOTS`):

```javascript
const TEAM_NAMES = {
  BER: 'ALBA Berlin', IST: 'Anadolu Efes', MCO: 'AS Monaco', BAS: 'Baskonia',
  RED: 'Crvena Zvezda', MIL: 'EA7 Milan', BAR: 'FC Barcelona', MUN: 'Bayern Munich',
  ULK: 'Fenerbahce', ASV: 'ASVEL', TEL: 'Maccabi Tel Aviv', OLY: 'Olympiacos',
  PAN: 'Panathinaikos', PAR: 'Partizan', PRS: 'Paris Basketball', MAD: 'Real Madrid',
  PAM: 'Valencia Basket', VIR: 'Virtus Bologna', ZAL: 'Zalgiris', DUB: 'Dubai Basketball',
  HTA: 'Hapoel Tel Aviv',
};

function teamName(code) { return TEAM_NAMES[code] || code; }
function logoUrl(code) { return `logos/${code}.png`; }
```

- [ ] **Step 2: Replace `renderSeries` with hero-only rendering**

In `docs/series.js`, replace the entire `renderSeries` function with:

```javascript
function renderSeries(root, entry) {
  root.innerHTML = `
    <section id="series-hero" class="series-section"></section>
    <section id="series-timeline" class="series-section"></section>
    <section id="series-h2h" class="series-section"></section>
    <section id="series-recaps" class="series-section"></section>
  `;
  renderHero(document.getElementById('series-hero'), entry);
}

function renderHero(container, entry) {
  const { high_seed, low_seed, wins, status, winner, series_win_prob, label, format } = entry;

  const seedLabel = (s) => {
    if (!s) return 'TBD';
    const seedSuffix = s.seed != null ? ` (${s.seed})` : '';
    return `<img class="series-logo" src="${logoUrl(s.team)}" alt="${s.team}" onerror="this.style.display='none'"><span>${teamName(s.team)}${seedSuffix}</span>`;
  };

  const scoreLine = () => {
    if (status === 'not_started') return 'Best-of-5 · Series not started';
    if (status === 'completed') return `Series complete · Winner: ${teamName(winner)}`;
    const leaderCode = wins.high > wins.low ? (high_seed && high_seed.team) : (low_seed && low_seed.team);
    return `Series: ${Math.max(wins.high, wins.low)}-${Math.min(wins.high, wins.low)} ${leaderCode || ''}`.trim();
  };

  const fmtLine = () => {
    if (format === 'best_of_5') return 'Best-of-5 · 2-2-1 home pattern';
    return format;
  };

  const probBar = () => {
    if (status === 'completed') return '';
    const h = series_win_prob.high || 0;
    const l = series_win_prob.low || 0;
    const highTeam = high_seed ? high_seed.team : 'HIGH';
    const lowTeam = low_seed ? low_seed.team : 'LOW';
    return `
      <div class="series-prob-bar">
        <div class="series-prob-fill series-prob-high" style="width: ${h}%"></div>
        <div class="series-prob-fill series-prob-low" style="width: ${l}%"></div>
      </div>
      <div class="series-prob-labels">
        <span>${highTeam} ${h.toFixed(1)}%</span>
        <span>${lowTeam} ${l.toFixed(1)}%</span>
      </div>
    `;
  };

  container.innerHTML = `
    <div class="series-hero">
      <h1 class="series-title">${label}</h1>
      <div class="series-teams">
        <div class="series-team series-team-high">${seedLabel(high_seed)}</div>
        <div class="series-vs">vs</div>
        <div class="series-team series-team-low">${seedLabel(low_seed)}</div>
      </div>
      <div class="series-state">${scoreLine()}</div>
      <div class="series-format">${fmtLine()}</div>
      ${probBar()}
    </div>
  `;
}
```

- [ ] **Step 3: Manual smoke test**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/series.html?id=qf1`. Expected: hero shows both teams (or TBD for low seed if play-in pending), series state line, best-of-5 format, and a horizontal probability bar split between high/low seed.

Also check `http://localhost:8000/series.html?id=sf1` — Expected: both teams show as TBD.

Stop server.

- [ ] **Step 4: Commit**

```bash
git add docs/series.js
git commit -m "feat: render Section 1 series hero in series.js

Hero shows team logos, seeds, current series score, format line, and a
horizontal probability bar. Handles not_started, in_progress, completed,
and TBD-seed states.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Render Section 2 — Game-by-Game Timeline

**Goal:** Render a horizontal strip of 5 game boxes. Completed games show score + winner + link to `replay.html`. Upcoming games show date + venue icon + pregame WP. Unnecessary (sweep) games are hidden entirely.

**Files:**
- Modify: `docs/series.js` — add `renderTimeline`

- [ ] **Step 1: Add `renderTimeline` and call it from `renderSeries`**

In `docs/series.js`, update `renderSeries` to call `renderTimeline`:

```javascript
function renderSeries(root, entry) {
  root.innerHTML = `
    <section id="series-hero" class="series-section"></section>
    <section id="series-timeline" class="series-section"></section>
    <section id="series-h2h" class="series-section"></section>
    <section id="series-recaps" class="series-section"></section>
  `;
  renderHero(document.getElementById('series-hero'), entry);
  renderTimeline(document.getElementById('series-timeline'), entry);
}
```

Then add `renderTimeline` below `renderHero`:

```javascript
function renderTimeline(container, entry) {
  const games = entry.games || [];
  const boxes = games
    .filter(g => g.status !== 'unnecessary')
    .map(g => renderGameBox(g))
    .join('');

  container.innerHTML = `
    <h2 class="series-section-title">Game-by-game</h2>
    <div class="series-timeline">${boxes}</div>
  `;
}

function renderGameBox(g) {
  const num = `G${g.game_num}`;
  if (g.status === 'completed') {
    const winnerCls = g.winner === g.home ? 'home-win' : 'away-win';
    const link = g.gamecode
      ? `replay.html?season=2025&gamecode=${g.gamecode}`
      : null;
    const inner = `
      <div class="series-game-num">${num}</div>
      <div class="series-game-score ${winnerCls}">
        <span class="${g.winner === g.home ? 'winner' : ''}">${g.home} ${g.home_score}</span>
        <span class="${g.winner === g.away ? 'winner' : ''}">${g.away} ${g.away_score}</span>
      </div>
      <div class="series-game-date">${formatDate(g.date)}</div>
      <div class="series-game-status">Final</div>
    `;
    return link
      ? `<a class="series-game-box completed" href="${link}">${inner}</a>`
      : `<div class="series-game-box completed">${inner}</div>`;
  }

  // upcoming
  const homeWp = (g.pregame_wp && g.pregame_wp.home) || null;
  const awayWp = (g.pregame_wp && g.pregame_wp.away) || null;
  const venue = g.home ? `@ ${g.home}` : '';
  return `
    <div class="series-game-box upcoming">
      <div class="series-game-num">${num}</div>
      <div class="series-game-venue">${venue}</div>
      <div class="series-game-date">${formatDate(g.date) || 'TBD'}</div>
      ${homeWp != null ? `<div class="series-game-wp">${g.home} ${homeWp.toFixed(0)}% / ${g.away} ${awayWp.toFixed(0)}%</div>` : ''}
    </div>
  `;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
```

- [ ] **Step 2: Manual smoke test**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/series.html?id=qf1`. Expected: 5 game boxes in a horizontal strip, each with game number, date, and (for upcoming) pregame WP %.

Stop server.

- [ ] **Step 3: Commit**

```bash
git add docs/series.js
git commit -m "feat: render Section 2 game-by-game timeline

Horizontal strip of up to 5 game boxes. Completed games show score
plus a click-through to replay.html. Upcoming games show date, venue,
and pregame win probability. Unnecessary (sweep) games are hidden.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Render Section 3 — Regular-Season H2H

**Goal:** Render up to 2 RS meeting cards side by side, plus a summary line with season split and combined margin. Fallback message if no meetings.

**Files:**
- Modify: `docs/series.js` — add `renderH2H`

- [ ] **Step 1: Wire `renderH2H` into `renderSeries` and add the function**

In `docs/series.js`, extend `renderSeries`:

```javascript
function renderSeries(root, entry) {
  root.innerHTML = `
    <section id="series-hero" class="series-section"></section>
    <section id="series-timeline" class="series-section"></section>
    <section id="series-h2h" class="series-section"></section>
    <section id="series-recaps" class="series-section"></section>
  `;
  renderHero(document.getElementById('series-hero'), entry);
  renderTimeline(document.getElementById('series-timeline'), entry);
  renderH2H(document.getElementById('series-h2h'), entry);
}
```

Add `renderH2H` below `renderTimeline`:

```javascript
function renderH2H(container, entry) {
  const meetings = entry.rs_h2h || [];
  const highTeam = entry.high_seed && entry.high_seed.team;
  const lowTeam = entry.low_seed && entry.low_seed.team;

  if (!highTeam || !lowTeam) {
    container.innerHTML = `
      <h2 class="series-section-title">Regular-season H2H</h2>
      <p class="series-empty">Waiting for both teams to be determined.</p>
    `;
    return;
  }

  if (meetings.length === 0) {
    container.innerHTML = `
      <h2 class="series-section-title">Regular-season H2H</h2>
      <p class="series-empty">No regular-season meetings.</p>
    `;
    return;
  }

  const cards = meetings.map(m => {
    const hostedBy = `${m.home} home`;
    return `
      <div class="series-h2h-card">
        <div class="series-h2h-round">Round ${m.round} · ${hostedBy}</div>
        <div class="series-h2h-score">
          <span class="${m.winner === m.home ? 'winner' : ''}">${m.home} ${m.home_score}</span>
          <span> – </span>
          <span class="${m.winner === m.away ? 'winner' : ''}">${m.away} ${m.away_score}</span>
        </div>
      </div>
    `;
  }).join('');

  // Summary line
  let highWins = 0, lowWins = 0, highPts = 0, lowPts = 0;
  meetings.forEach(m => {
    const highIsHome = m.home === highTeam;
    const hs = highIsHome ? m.home_score : m.away_score;
    const ls = highIsHome ? m.away_score : m.home_score;
    highPts += hs;
    lowPts += ls;
    if (m.winner === highTeam) highWins += 1;
    else lowWins += 1;
  });
  const margin = highPts - lowPts;
  const marginLeader = margin > 0 ? highTeam : (margin < 0 ? lowTeam : 'even');
  const marginStr = margin === 0 ? 'Combined margin: even' : `Combined margin: ${marginLeader} +${Math.abs(margin)}`;

  container.innerHTML = `
    <h2 class="series-section-title">Regular-season H2H</h2>
    <div class="series-h2h-cards">${cards}</div>
    <div class="series-h2h-summary">Season split: ${highTeam} ${highWins}-${lowWins} ${lowTeam} · ${marginStr}</div>
  `;
}
```

- [ ] **Step 2: Manual smoke test**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/series.html?id=qf1`. Expected: two H2H cards (or one/zero depending on real 2025 schedule) + a season-split summary line.

Stop server.

- [ ] **Step 3: Commit**

```bash
git add docs/series.js
git commit -m "feat: render Section 3 regular-season H2H

Shows up to two RS meeting cards with scores and a summary line of
the season split and combined margin. Graceful fallback for 0 meetings
or unresolved teams.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: Render Section 4 — Game Recaps (reuse playoffs.js component)

**Goal:** For each completed game in this series, render a recap card matching the style on `playoffs.html`. Hidden entirely if no games completed.

**Files:**
- Modify: `docs/series.js` — add `renderRecaps`

First, inspect the recap card markup used on `playoffs.html`:

```bash
grep -n "recap\|playoff_recaps" docs/playoffs.js | head -10
```

- [ ] **Step 1: Identify the matching recaps from `dashboard.playoff_recaps`**

The existing `playoff_recaps` array in `dashboard.json` already contains recap entries with home/away/winner/scores/round labels/etc. For Series Hub, we filter that array to recaps whose teams match this series' pair.

In `docs/series.js`, update `main()` to pass the full dashboard to `renderSeries`:

```javascript
async function main() {
  const root = document.getElementById('series-root');
  const slotId = getSlotId();

  let dashboard;
  try {
    const res = await fetch('data/current/dashboard.json');
    dashboard = await res.json();
  } catch (err) {
    renderError(root, 'Could not load dashboard data.');
    return;
  }

  const series = dashboard.series || {};
  if (!slotId) {
    renderIndex(root, series);
    return;
  }
  if (!VALID_SLOTS.includes(slotId)) {
    renderError(root, `Invalid series id: "${slotId}". Valid ids: ${VALID_SLOTS.join(', ')}.`);
    return;
  }

  const entry = series[slotId];
  if (!entry) {
    renderError(root, `No data available for "${slotId}".`);
    return;
  }

  renderSeries(root, entry, dashboard);
}
```

And update `renderSeries` signature:

```javascript
function renderSeries(root, entry, dashboard) {
  root.innerHTML = `
    <section id="series-hero" class="series-section"></section>
    <section id="series-timeline" class="series-section"></section>
    <section id="series-h2h" class="series-section"></section>
    <section id="series-recaps" class="series-section"></section>
  `;
  renderHero(document.getElementById('series-hero'), entry);
  renderTimeline(document.getElementById('series-timeline'), entry);
  renderH2H(document.getElementById('series-h2h'), entry);
  renderRecaps(document.getElementById('series-recaps'), entry, dashboard);
}
```

- [ ] **Step 2: Add `renderRecaps` function**

Append to `docs/series.js`:

```javascript
function renderRecaps(container, entry, dashboard) {
  const highTeam = entry.high_seed && entry.high_seed.team;
  const lowTeam = entry.low_seed && entry.low_seed.team;
  if (!highTeam || !lowTeam) {
    container.innerHTML = '';
    return;
  }

  const allRecaps = dashboard.playoff_recaps || [];
  const pair = new Set([highTeam, lowTeam]);
  const matching = allRecaps.filter(r =>
    pair.has(r.home) && pair.has(r.away)
  );

  if (matching.length === 0) {
    container.innerHTML = '';
    return;
  }

  const cards = matching.map(r => renderRecapCard(r)).join('');
  container.innerHTML = `
    <h2 class="series-section-title">Game recaps</h2>
    <div class="series-recaps">${cards}</div>
  `;
}

function renderRecapCard(r) {
  // Matches the visual shape of playoffs.html recap cards.
  const score = `${r.home} ${r.home_score} – ${r.away} ${r.away_score}`;
  const pre = r.pre_game_win_prob != null ? `Pre-game ${r.winner} win prob: ${r.pre_game_win_prob}%` : '';
  const upset = r.is_upset ? '<span class="recap-upset">Upset</span>' : '';
  const title = r.series_label || r.round || '';
  return `
    <div class="series-recap-card">
      <div class="recap-title">${title} ${upset}</div>
      <div class="recap-score ${r.winner === r.home ? 'home-win' : 'away-win'}">${score}</div>
      <div class="recap-pre">${pre}</div>
    </div>
  `;
}
```

- [ ] **Step 3: Manual smoke test**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/series.html?id=qf1`. Expected: If any QF1 games have been played, recap cards appear in Section 4. Otherwise the section is empty (no heading).

Stop server.

- [ ] **Step 4: Commit**

```bash
git add docs/series.js
git commit -m "feat: render Section 4 game recaps by filtering playoff_recaps

Reuses dashboard.playoff_recaps, filtering to the current series' team
pair. Each recap rendered as a simple card matching playoffs.html style.
Empty when no games have been played yet.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: Add series-specific styles to `docs/style.css`

**Goal:** Add the CSS classes used by series.js. Match the existing color palette and component style of `playoffs.html`.

**Files:**
- Modify: `docs/style.css` — append new rules at the end

First, inspect existing style patterns to match:
```bash
tail -80 docs/style.css
grep -n "recap\|bracket\|--accent\|--bg" docs/style.css | head -10
```

- [ ] **Step 1: Append Series Hub rules to `docs/style.css`**

Append to the end of `docs/style.css`:

```css
/* ── Series Hub ────────────────────────────────────────────────────────── */

.series-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 16px 64px;
}

.back-link {
  display: inline-block;
  color: #9fb7d9;
  text-decoration: none;
  margin-bottom: 16px;
  font-size: 14px;
}
.back-link:hover { color: #fff; }

.series-section {
  margin-bottom: 28px;
}

.series-section-title {
  font-size: 14px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #9fb7d9;
  margin: 0 0 12px;
}

/* Hero */
.series-hero {
  background: #1e3a5f;
  border: 1px solid #60a5fa;
  border-radius: 8px;
  padding: 24px;
}
.series-title {
  margin: 0 0 16px;
  font-size: 22px;
  color: #fff;
}
.series-teams {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.series-team { display: flex; align-items: center; gap: 8px; font-size: 18px; color: #fff; }
.series-logo { width: 32px; height: 32px; object-fit: contain; }
.series-vs { color: #9fb7d9; font-size: 14px; }
.series-state { font-size: 16px; color: #e8efff; margin-bottom: 4px; }
.series-format { font-size: 13px; color: #9fb7d9; margin-bottom: 16px; }

.series-prob-bar {
  display: flex;
  height: 18px;
  border-radius: 4px;
  overflow: hidden;
  background: #2a4a70;
}
.series-prob-fill { height: 100%; transition: width 0.3s ease; }
.series-prob-high { background: #60a5fa; }
.series-prob-low { background: #f59e0b; }
.series-prob-labels {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #e8efff;
  margin-top: 4px;
}

/* Timeline */
.series-timeline {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 8px;
}
.series-game-box {
  flex: 0 0 140px;
  background: #1e3a5f;
  border: 1px solid #3a5a80;
  border-radius: 6px;
  padding: 12px;
  color: #e8efff;
  text-decoration: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}
.series-game-box.completed { border-color: #60a5fa; }
.series-game-box.completed:hover { background: #2a4a70; }
.series-game-num { font-weight: 600; font-size: 14px; color: #fff; }
.series-game-score { display: flex; flex-direction: column; gap: 2px; }
.series-game-score .winner { font-weight: 700; color: #fff; }
.series-game-date { color: #9fb7d9; }
.series-game-status { color: #60a5fa; font-size: 11px; }
.series-game-wp { color: #f59e0b; font-size: 11px; }
.series-game-venue { color: #9fb7d9; font-size: 11px; }

/* H2H */
.series-h2h-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.series-h2h-card {
  background: #1e3a5f;
  border: 1px solid #3a5a80;
  border-radius: 6px;
  padding: 14px;
  color: #e8efff;
}
.series-h2h-round {
  color: #9fb7d9;
  font-size: 12px;
  margin-bottom: 6px;
}
.series-h2h-score { font-size: 16px; }
.series-h2h-score .winner { color: #60a5fa; font-weight: 600; }
.series-h2h-summary {
  margin-top: 10px;
  color: #9fb7d9;
  font-size: 13px;
}

/* Recaps */
.series-recaps { display: flex; flex-direction: column; gap: 10px; }
.series-recap-card {
  background: #1e3a5f;
  border: 1px solid #3a5a80;
  border-radius: 6px;
  padding: 14px;
  color: #e8efff;
}
.recap-title { font-size: 13px; color: #9fb7d9; margin-bottom: 6px; }
.recap-score { font-size: 16px; margin-bottom: 4px; }
.recap-pre { font-size: 12px; color: #9fb7d9; }
.recap-upset {
  background: #f59e0b;
  color: #0e1a2a;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  margin-left: 6px;
}

/* Fallbacks */
.series-empty { color: #9fb7d9; font-size: 14px; }
.series-error { text-align: center; padding: 40px 16px; }
.series-error h1 { color: #fff; }
.series-error p { color: #9fb7d9; }
.series-index { list-style: none; padding: 0; }
.series-index li { padding: 8px 0; border-bottom: 1px solid #2a4a70; }
.series-index a { color: #60a5fa; text-decoration: none; }
.series-index a:hover { color: #fff; }

/* Responsive */
@media (max-width: 640px) {
  .series-h2h-cards { grid-template-columns: 1fr; }
  .series-teams { flex-direction: column; align-items: flex-start; }
}
```

- [ ] **Step 2: Manual smoke test**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/series.html?id=qf1`. Expected: page now has proper visual layout — hero block with colored probability bar, timeline with clearly delineated boxes, H2H cards side-by-side, styled recap cards.

Resize to mobile width (375px). Expected: H2H cards stack, teams stack vertically in hero.

Stop server.

- [ ] **Step 3: Commit**

```bash
git add docs/style.css
git commit -m "style: add Series Hub CSS classes

Hero, timeline, H2H cards, recap cards, error/empty states. Matches
playoffs.html palette (blue on dark navy). Responsive collapse to
single-column at 640px.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: Wire navigation — `playoffs.js` bracket lines and recap cards

**Goal:** Clicking a bracket matchup line or a recap card on `playoffs.html` navigates to the corresponding series page. Use the slot-id convention (`qf1..qf4`, `sf1`, `sf2`, `final`).

**Files:**
- Modify: `docs/playoffs.js` — `renderMatchup` and recap-rendering functions

- [ ] **Step 1: Identify where matchups are rendered**

Run: `grep -n "renderMatchup\|data-idx.*\${idx}\|recap" docs/playoffs.js | head -20`

Expected: finds the matchup rendering near line 293 and recap rendering elsewhere.

- [ ] **Step 2: Read the relevant functions**

Read the existing implementations to understand how to wrap them without breaking user-bracket-pick behavior. Specifically, check `renderMatchup` (around line 285-295) and the recap-card rendering block.

- [ ] **Step 3: Build a slot-id helper**

Near the top of `docs/playoffs.js` (after any initial constants), add:

```javascript
// Map (round, idx) -> series slot id used by series.html
function _seriesSlotId(round, idx) {
  if (round === 'quarters') return `qf${idx + 1}`;
  if (round === 'semis') return `sf${idx + 1}`;
  if (round === 'final') return 'final';
  return null;   // play-in has no Series Hub entry
}
```

- [ ] **Step 4: Wrap the matchup block with a Series Hub link (non-breaking)**

In `docs/playoffs.js`, locate `renderMatchup` (near line 293). The current last line is roughly:

```javascript
return `<div class="matchup" data-round="${round}" data-idx="${idx}">${sideA}${sideB}${badgeHTML}</div>`;
```

Modify it to append a small link icon that doesn't interfere with the existing bracket-pick click handlers. Change the block to:

```javascript
function renderMatchup(round, idx, seriesLen, neutral) {
  // ... existing logic building sideA, sideB, badgeHTML stays the same ...

  const slotId = _seriesSlotId(round, idx);
  const hubLink = slotId
    ? `<a class="series-hub-link" href="series.html?id=${slotId}" title="Open Series Hub">→</a>`
    : '';

  return `<div class="matchup" data-round="${round}" data-idx="${idx}">${sideA}${sideB}${badgeHTML}${hubLink}</div>`;
}
```

(Do not wrap the whole matchup in a link — that would break the existing click-to-pick behavior.)

- [ ] **Step 5: Add style for `.series-hub-link`**

Append to `docs/style.css`:

```css
.series-hub-link {
  position: absolute;
  top: 4px;
  right: 6px;
  color: #9fb7d9;
  text-decoration: none;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: 3px;
  z-index: 2;
}
.series-hub-link:hover { color: #fff; background: #2a4a70; }
.matchup { position: relative; }
```

- [ ] **Step 6: Wrap recap cards in Series Hub links**

Run: `grep -n "recap\|playoff_recaps" docs/playoffs.js`

Locate the recap-card rendering block. Each recap has a `series_label` or round that identifies its slot. Extend with a link wrapper. Inside the recap rendering function (find by the grep), locate where each card is returned. Where the card's outer HTML is built, add a link wrapper:

First, extend `_seriesSlotId` (in playoffs.js) to accept a recap's round label:

```javascript
function _slotIdForRecapRound(recapRoundLabel) {
  // recap round labels like "Quarterfinal 1v8", "Semi-Final 1", "Final"
  if (!recapRoundLabel) return null;
  const s = recapRoundLabel.toLowerCase();
  if (s.includes('final') && !s.includes('semi') && !s.includes('quarter')) return 'final';
  if (s.includes('semi-final 1') || s.includes('sf1')) return 'sf1';
  if (s.includes('semi-final 2') || s.includes('sf2')) return 'sf2';
  if (s.includes('1v8')) return 'qf1';
  if (s.includes('2v7')) return 'qf2';
  if (s.includes('3v6')) return 'qf3';
  if (s.includes('4v5')) return 'qf4';
  return null;
}
```

Inspect the recap-render function (look for `recap.round`, `recap.series_label`, or similar) to understand which field holds the series label. Verify the label formats by running:

```bash
python -c "import json; d=json.load(open('docs/data/current/dashboard.json', encoding='utf-8')); [print(r.get('round'), '|', r.get('series_label')) for r in d.get('playoff_recaps', [])[:10]]"
```

Based on the output, adjust `_slotIdForRecapRound` as needed so every real recap returns a non-null slot.

Then wrap each recap card in the render function. Example pattern — find where the card HTML is returned (likely a string interpolation) and change it to:

```javascript
const hubSlot = _slotIdForRecapRound(recap.round || recap.series_label);
const wrappedCard = hubSlot
  ? `<a class="recap-card-link" href="series.html?id=${hubSlot}"><div class="recap-card">${cardInner}</div></a>`
  : `<div class="recap-card">${cardInner}</div>`;
return wrappedCard;
```

- [ ] **Step 7: Add link style to `docs/style.css`**

Append:

```css
.recap-card-link {
  text-decoration: none;
  color: inherit;
  display: block;
}
.recap-card-link .recap-card:hover {
  background: #2a4a70;
  cursor: pointer;
}
```

- [ ] **Step 8: Manual smoke test**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/playoffs.html`. Expected:
- Each bracket matchup has a small "→" arrow in the top-right corner. Clicking it opens `series.html?id=qfN` etc.
- Clicking the matchup body still does the existing bracket-pick behavior (does NOT navigate away).
- Each recap card is now clickable — clicking opens the correct Series Hub page.

Stop server.

- [ ] **Step 9: Commit**

```bash
git add docs/playoffs.js docs/style.css
git commit -m "feat: wire Series Hub links from bracket matchups and recap cards

Bracket matchup cells get a small arrow link to series.html?id=<slot>,
preserving existing click-to-pick behavior. Recap cards become
clickable wrappers to the corresponding series page. Slot id resolution
handled by helper functions in playoffs.js.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 13: Update `docs/about.html` with Series Hub description

**Goal:** Add a paragraph under the Playoffs description that explains Series Hub.

**Files:**
- Modify: `docs/about.html`

- [ ] **Step 1: Locate the Playoffs description block**

Run: `grep -n "Playoff\|playoffs" docs/about.html | head -10`

- [ ] **Step 2: Add Series Hub paragraph**

Read the existing Playoffs description block, then insert the following paragraph immediately after it (inside the same section):

```html
<p>Each bracket matchup and recap card now links into a dedicated <strong>Series Hub</strong> page. Every quarterfinal, semifinal, and final series has its own page showing the series hero (teams, seeds, current score, series win probability), a game-by-game timeline with pregame win probabilities for upcoming games, regular-season head-to-head results, and recap cards for every completed game.</p>
```

Use the Edit tool to insert this after the existing last paragraph of the Playoffs section.

- [ ] **Step 3: Manual verification**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/about.html`. Expected: new paragraph about Series Hub appears under the Playoffs description.

Stop server.

- [ ] **Step 4: Commit**

```bash
git add docs/about.html
git commit -m "docs: describe Series Hub in about page

Mentions the dedicated series.html page that Playoffs bracket cells and
recap cards now link into.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 14: Final integration and visual verification

**Goal:** Run the pipeline end-to-end, verify `dashboard.json` is well-formed, and screenshot all 7 slots for visual regression.

**Files:**
- None modified — verification only.

- [ ] **Step 1: Regenerate dashboard.json**

Run:
```bash
EUROLEAGUE_ROUND_SUFFIX=_R38 .venv/Scripts/python.exe export_dashboard_data.py
```
Expected: runs without errors, `docs/data/current/dashboard.json` is updated.

- [ ] **Step 2: Verify structure for all 7 slots**

Run:
```bash
python -c "
import json
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
s = d['series']
for slot in ['qf1','qf2','qf3','qf4','sf1','sf2','final']:
    e = s[slot]
    hs = e['high_seed']['team'] if e['high_seed'] else 'TBD'
    ls = e['low_seed']['team'] if e['low_seed'] else 'TBD'
    print(f'{slot}: {hs} vs {ls} · status={e[\"status\"]} · games={len(e[\"games\"])} · h2h={len(e[\"rs_h2h\"])}')"
```

Expected: all 7 slots print. QF slots show actual seed teams (TBD for seed 7/8 if play-in not done). SF/Final slots show TBD vs TBD. Each has 5 games entries and 0-2 h2h entries.

- [ ] **Step 3: Visual browser sweep**

Run:
```bash
python -m http.server 8000 --directory docs
```

Open each URL and eyeball for correctness:
- `http://localhost:8000/series.html` (index)
- `http://localhost:8000/series.html?id=qf1`
- `http://localhost:8000/series.html?id=qf2`
- `http://localhost:8000/series.html?id=qf3`
- `http://localhost:8000/series.html?id=qf4`
- `http://localhost:8000/series.html?id=sf1`
- `http://localhost:8000/series.html?id=sf2`
- `http://localhost:8000/series.html?id=final`
- `http://localhost:8000/series.html?id=bogus` (error page)
- `http://localhost:8000/playoffs.html` (verify bracket links + recap cards)

For each: no JS console errors, no missing sections, no layout breaks.

- [ ] **Step 4: Take screenshot for visual regression**

With the server running, use Playwright (already in repo per `.playwright-mcp/`) to capture one canonical screenshot:

```bash
npx playwright screenshot --viewport-size=1200,800 http://localhost:8000/series.html?id=qf1 series_hub_qf1.png
```

Expected: `series_hub_qf1.png` created at repo root. (If `npx` isn't available, skip this step and just verify by eye.)

Stop server.

- [ ] **Step 5: Run the full test suite**

Run:
```bash
.venv/Scripts/python.exe test_series_data.py
```
Expected: all 4 task assertion blocks pass.

Run:
```bash
.venv/Scripts/python.exe test_path_to_title_play_in_states.py
```
Expected: All 4 state assertions passed (the existing tests should still pass since we didn't change `compute_path_to_title`).

- [ ] **Step 6: Final commit**

```bash
git add series_hub_qf1.png 2>/dev/null || true
git commit -m "test: add Series Hub visual regression screenshot

Baseline screenshot of series.html?id=qf1 in current state. Used for
eyeball diffs when refactoring.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>" || echo "Nothing to commit (screenshot step was skipped)."
```

---

## Self-Review Checklist

Before handing off for execution, verify:

**Spec coverage:**
- ✅ 7 slots (qf1..qf4, sf1, sf2, final) — Task 1 (MC sim), Task 2 (structure)
- ✅ Slot-based URL (`?id=...`) — Task 6
- ✅ Section 1 Series Hero (logos, seeds, score, WP bar) — Task 7
- ✅ Section 2 Timeline (5 game boxes, completed/upcoming/unnecessary) — Task 8
- ✅ Section 3 RS H2H (2 cards + summary) — Task 4 (data), Task 9 (render)
- ✅ Section 4 Recap Cards (reuse playoffs.js) — Task 10
- ✅ Navigation wiring (bracket + recap cards) — Task 12
- ✅ Edge cases: invalid id, missing id, TBD slots, sweep, no H2H — Tasks 6, 7, 8, 9
- ✅ Monte Carlo integration for series_win_prob — Task 1
- ✅ Pregame WP via _matchup_prob — Task 3
- ✅ About page update — Task 13
- ✅ Styles — Task 11
- ✅ Tests — Tasks 1, 2, 3, 4

**No placeholders in plan:** every step has exact code or exact commands with expected output.

**Type consistency:** slot ids (`qf1..final`) are used uniformly across Python (`compute_championship_odds`, `compute_series_data`) and JS (`VALID_SLOTS`, `_seriesSlotId`). Field names (`high_seed`, `low_seed`, `wins`, `series_win_prob`, `games`, `rs_h2h`) are consistent between Python output and JS consumption.
