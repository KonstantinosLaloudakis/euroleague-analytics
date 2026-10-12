# Tale of the Tape & Series Momentum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new sections to Series Hub (`docs/series.html`) — Tale of the Tape (8-row stat comparison + 3 deterministic edges) and Series Momentum (series WP line chart with biggest-swing callout) — both fed by data precomputed in `dashboard.json`.

**Architecture:** Backend helpers in `export_dashboard_data.py` precompute box-score aggregations, paint-volume share, the series-WP DP, and the edges algorithm; results are embedded under each series entry's `tale_of_the_tape` and `momentum` keys. Frontend (`docs/series.js`) gains two new render functions called from the existing `renderSeries()` orchestrator. No new files.

**Tech Stack:** Python 3.12 (data pipeline), vanilla JS (frontend), Plotly.js (chart, loaded via CDN). Follows existing module-level helper pattern in `export_dashboard_data.py` and the section-render pattern in `series.js`.

**Spec:** `docs/superpowers/specs/2026-04-25-tale-of-the-tape-and-momentum-design.md`

---

## File Structure

| File | New / Modified | Responsibility |
|------|----------------|----------------|
| `export_dashboard_data.py` | Modified | Adds 5 module-level helpers (`compute_team_box_metrics`, `compute_team_paint_share`, `compute_remaining_series_wp`, `build_momentum`, `build_tale_of_the_tape`); wires them into the existing `compute_series_data()` builder. |
| `docs/series.html` | Modified | Adds Plotly CDN `<script>` tag and inline `<style>` for the two new sections. No new section markup — the JS template generates it. |
| `docs/series.js` | Modified | Adds `renderTaleOfTheTape()` and `renderMomentum()`; updates `renderSeries()` template to include two new `<section>` slots and calls. |
| `docs/about.html` | Modified | One-paragraph description of both features under the playoff section. |
| `inspect_tale_and_momentum.py` | New (root, ad-hoc) | Quick smoke check that prints `series.qf1.tale_of_the_tape` and `series.qf1.momentum` from the regenerated `dashboard.json`. Mirrors existing `inspect_*.py` pattern. |

All five new Python helpers go at **module level**, immediately above `def main()` (around line 890). They are called from inside the nested `compute_series_data()` (around line 2163).

---

## Task 1: Module-level helper — compute_team_box_metrics

**Why first:** Other helpers depend on its output (per-team pace, 3PT%, FT rate, bench share, opponents-allowed splits).

**Files:**
- Modify: `export_dashboard_data.py` — insert new function above `def main()` (around line 889)

- [ ] **Step 1: Add `compute_team_box_metrics` at module level**

Insert this function in `export_dashboard_data.py` immediately above the `def main():` line (currently line 890):

```python
def compute_team_box_metrics(all_game_stats, gamecode_to_teams):
    """
    Aggregate per-team season box-score metrics from raw box scores.

    Args:
        all_game_stats: list of game dicts from mvp_all_game_stats_2025.json
        gamecode_to_teams: dict[int, tuple[str, str]] mapping
            GameCode -> (local_team_code, road_team_code)

    Returns:
        dict[team_code] = {
            'pace': float,           # avg possessions per game
            'three_pct': float,      # 3PT% (0-100)
            'two_pct': float,        # 2PT% (0-100)
            'ft_rate': float,        # FTA / FGA
            'bench_share': float,    # bench points share (0-100)
            'opp_three_pct': float,  # opponents' 3PT% vs this team (0-100)
            'opp_two_pct': float,    # opponents' 2PT% vs this team (0-100)
            'games': int,
        }
    Skips playoff games (Gamecode > 380) and any game with no shot attempts logged.
    """
    from collections import defaultdict

    agg = defaultdict(lambda: {
        'fga': 0.0, 'fta': 0.0, 'oreb': 0.0, 'tov': 0.0,
        'fgm3': 0.0, 'fga3': 0.0, 'fgm2': 0.0, 'fga2': 0.0,
        'opp_fgm3': 0.0, 'opp_fga3': 0.0,
        'opp_fgm2': 0.0, 'opp_fga2': 0.0,
        'bench_pts': 0.0, 'total_pts': 0.0,
        'games': 0,
    })

    def _bench_points(players):
        if not isinstance(players, list):
            return 0.0
        total = 0.0
        for pl in players:
            stats = pl.get('stats') or {}
            if stats.get('startFive'):
                continue
            total += float(stats.get('points') or 0.0)
        return total

    for g in all_game_stats:
        gc = int(g.get('Gamecode') or g.get('GameCode') or 0)
        if gc <= 0 or gc > 380:
            continue
        teams = gamecode_to_teams.get(gc)
        if not teams:
            continue
        local_team, road_team = teams

        for side, opp_side, my_team in (
            ('local', 'road', local_team),
            ('road', 'local', road_team),
        ):
            fga = float(g.get(f'{side}.total.fieldGoalsAttemptedTotal') or 0)
            fta = float(g.get(f'{side}.total.freeThrowsAttempted') or 0)
            if fga + fta == 0:
                continue  # data missing

            t = agg[my_team]
            t['fga'] += fga
            t['fta'] += fta
            t['oreb'] += float(g.get(f'{side}.total.offensiveRebounds') or 0)
            t['tov'] += float(g.get(f'{side}.total.turnovers') or 0)
            t['fgm3'] += float(g.get(f'{side}.total.fieldGoalsMade3') or 0)
            t['fga3'] += float(g.get(f'{side}.total.fieldGoalsAttempted3') or 0)
            t['fgm2'] += float(g.get(f'{side}.total.fieldGoalsMade2') or 0)
            t['fga2'] += float(g.get(f'{side}.total.fieldGoalsAttempted2') or 0)
            t['opp_fgm3'] += float(g.get(f'{opp_side}.total.fieldGoalsMade3') or 0)
            t['opp_fga3'] += float(g.get(f'{opp_side}.total.fieldGoalsAttempted3') or 0)
            t['opp_fgm2'] += float(g.get(f'{opp_side}.total.fieldGoalsMade2') or 0)
            t['opp_fga2'] += float(g.get(f'{opp_side}.total.fieldGoalsAttempted2') or 0)
            t['total_pts'] += float(g.get(f'{side}.total.points') or 0)
            t['bench_pts'] += _bench_points(g.get(f'{side}.players'))
            t['games'] += 1

    out = {}
    for code, a in agg.items():
        if a['games'] == 0:
            continue
        poss = a['fga'] + 0.44 * a['fta'] - a['oreb'] + a['tov']
        out[code] = {
            'pace': round(poss / a['games'], 1),
            'three_pct': round((a['fgm3'] / a['fga3']) * 100, 1) if a['fga3'] > 0 else 0.0,
            'two_pct': round((a['fgm2'] / a['fga2']) * 100, 1) if a['fga2'] > 0 else 0.0,
            'ft_rate': round(a['fta'] / a['fga'], 3) if a['fga'] > 0 else 0.0,
            'bench_share': round((a['bench_pts'] / a['total_pts']) * 100, 1) if a['total_pts'] > 0 else 0.0,
            'opp_three_pct': round((a['opp_fgm3'] / a['opp_fga3']) * 100, 1) if a['opp_fga3'] > 0 else 0.0,
            'opp_two_pct': round((a['opp_fgm2'] / a['opp_fga2']) * 100, 1) if a['opp_fga2'] > 0 else 0.0,
            'games': a['games'],
        }
    return out
```

- [ ] **Step 2: Validate via import**

Run:

```bash
.venv/Scripts/python.exe -c "
import json
from export_dashboard_data import compute_team_box_metrics
gs = json.load(open('mvp_all_game_stats_2025.json', encoding='utf-8'))
gr = json.load(open('mvp_game_results.json', encoding='utf-8'))
gc2t = {int(r['GameCode']): (r['LocalTeam'], r['RoadTeam']) for r in gr}
m = compute_team_box_metrics(gs, gc2t)
print('teams covered:', len(m))
for k in ('OLY', 'PAN', 'MAD', 'BAR'):
    if k in m:
        v = m[k]
        print(f'{k}: pace={v[\"pace\"]} 3p%={v[\"three_pct\"]} 2p%={v[\"two_pct\"]} ftrate={v[\"ft_rate\"]} bench={v[\"bench_share\"]}% games={v[\"games\"]}')
"
```

Expected: `teams covered: 20`. Each team's pace ≈ 70–80, three_pct ≈ 32–40, two_pct ≈ 50–58, ft_rate ≈ 0.18–0.32, bench_share ≈ 25–40, games close to 38.

If `teams covered` < 20 or any field shows 0.0 broadly, the gamecode mapping is wrong — verify `mvp_game_results.json` is up to date and the GameCode field name matches.

- [ ] **Step 3: Commit**

```bash
git add export_dashboard_data.py
git commit -m "$(cat <<'EOF'
feat: compute_team_box_metrics helper

Aggregates pace, 3PT%, 2PT%, FT rate, bench share, and
opponents-allowed splits per team from raw box scores.
Used by upcoming Tale of the Tape feature.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Module-level helper — compute_team_paint_share

**Files:**
- Modify: `export_dashboard_data.py` — insert immediately below `compute_team_box_metrics`

- [ ] **Step 1: Add `compute_team_paint_share` at module level**

Add immediately below `compute_team_box_metrics`:

```python
def compute_team_paint_share(shot_stats):
    """
    Compute per-team paint shot volume share from shot_stats data.

    Paint zones: A (At Rim), B (Left Paint), C (Right Paint).
    paint_share = (paint attempts) / (total attempts) * 100.

    Args:
        shot_stats: dict loaded from docs/data/current/shot_stats.json

    Returns:
        dict[team_code] -> float (0-100)
    """
    out = {}
    teams = (shot_stats or {}).get('teams') or {}
    paint_zones = ('A', 'B', 'C')
    for code, zones in teams.items():
        if not isinstance(zones, dict):
            continue
        paint_att = sum(float((zones.get(z) or {}).get('attempts') or 0) for z in paint_zones)
        total_att = sum(float((zones.get(z) or {}).get('attempts') or 0) for z in zones.keys())
        if total_att <= 0:
            continue
        out[code] = round((paint_att / total_att) * 100, 1)
    return out
```

- [ ] **Step 2: Validate**

```bash
.venv/Scripts/python.exe -c "
import json
from export_dashboard_data import compute_team_paint_share
ss = json.load(open('docs/data/current/shot_stats.json', encoding='utf-8'))
m = compute_team_paint_share(ss)
print('teams covered:', len(m))
for k in ('OLY', 'PAN', 'MAD', 'BAR'):
    if k in m:
        print(f'{k} paint share: {m[k]}%')
"
```

Expected: 20 teams covered. Each paint share ≈ 35–55%.

- [ ] **Step 3: Commit**

```bash
git add export_dashboard_data.py
git commit -m "$(cat <<'EOF'
feat: compute_team_paint_share helper

Per-team paint shot volume share derived from shot_stats zones
A/B/C. Used by upcoming Tale of the Tape feature.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Module-level helper — compute_remaining_series_wp

**Why:** Python port of the JS `seriesProbHCA` DP from `playoffs.js`. Powers the Momentum checkpoints. Backend and frontend must produce identical numbers.

**Files:**
- Modify: `export_dashboard_data.py` — insert below `compute_team_paint_share`

- [ ] **Step 1: Add `compute_remaining_series_wp` at module level**

```python
def compute_remaining_series_wp(matchup_probs, high_team, low_team,
                                wins_high, wins_low,
                                home_pattern=('high', 'high', 'low', 'low', 'high'),
                                target_wins=3, elo_high=None, elo_low=None,
                                elo_hca=50.0):
    """
    Compute series win probability for the higher seed given the current
    series score and remaining games. Best-of-N DP, identical to the JS
    `seriesProbHCA` in playoffs.js.

    Args:
        matchup_probs: dict[high_team][low_team] = {'home','away','neutral'}
            with floats in [0,1]. May be missing.
        high_team, low_team: 3-letter team codes.
        wins_high, wins_low: current series score (ints).
        home_pattern: tuple of 'high' | 'low' for each game number 1..N.
            'neutral' is also allowed (used for the Final).
        target_wins: wins needed to clinch (3 for best-of-5, 1 for single-game).
        elo_high, elo_low: optional Elo ratings for fallback when matchup_probs
            is missing for the pair.
        elo_hca: Elo home-court advantage in points.

    Returns:
        float in [0,1] — probability the higher seed wins the series.
    """
    if wins_high >= target_wins:
        return 1.0
    if wins_low >= target_wins:
        return 0.0

    pair_fwd = (matchup_probs.get(high_team) or {}).get(low_team) or {}

    def _elo_wp(neutral=False):
        if elo_high is None or elo_low is None:
            return 0.5
        hca = 0.0 if neutral else elo_hca
        return 1.0 / (1.0 + 10.0 ** ((elo_low - elo_high - hca) / 400.0))

    def _per_game_p(slot):
        if slot == 'high':
            return pair_fwd.get('home', _elo_wp(neutral=False))
        if slot == 'low':
            return pair_fwd.get('away', _elo_wp(neutral=False))
        return pair_fwd.get('neutral', _elo_wp(neutral=True))

    games_played = wins_high + wins_low
    remaining = list(home_pattern)[games_played:]
    if not remaining:
        return 1.0 if wins_high > wins_low else 0.0

    states = {(wins_high, wins_low): 1.0}
    prob_high = 0.0

    for slot in remaining:
        p = _per_game_p(slot)
        nxt = {}
        for (a, b), prob in states.items():
            # higher seed wins this game
            a1 = a + 1
            if a1 >= target_wins:
                prob_high += prob * p
            else:
                key = (a1, b)
                nxt[key] = nxt.get(key, 0.0) + prob * p
            # lower seed wins this game
            b1 = b + 1
            if b1 < target_wins:
                key = (a, b1)
                nxt[key] = nxt.get(key, 0.0) + prob * (1.0 - p)
            # else: low clinches — no contribution to prob_high
        states = nxt
        if not states:
            break

    return prob_high
```

- [ ] **Step 2: Validate against the JS implementation**

The function should match `seriesProbHCA` in `docs/playoffs.js` for identical inputs. Pick a known QF: OLY (1) vs MCO (8) at 0-0.

```bash
.venv/Scripts/python.exe -c "
import json
from export_dashboard_data import compute_remaining_series_wp
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
mp = d['playoff_matchup_probs']
qf1 = d['series']['qf1']
hi = qf1['high_seed']['team']
lo = qf1['low_seed']['team']
expected = qf1['series_win_prob']['high']  # already-computed value from playoff_results
got = compute_remaining_series_wp(mp, hi, lo, 0, 0)
print(f'qf1 {hi} vs {lo}: expected {expected}%, got {round(got*100, 1)}%')
assert abs(round(got*100, 1) - expected) < 1.5, 'series WP mismatch'
print('OK')
"
```

Expected: prints something like `qf1 OLY vs MCO: expected 60.7%, got 60.7%` and `OK`.

A small (<1.5pp) tolerance is allowed because the existing `series_win_prob` in `dashboard.json` may use a slightly different DP; if the gap is larger, inspect the JS source to align.

- [ ] **Step 3: Commit**

```bash
git add export_dashboard_data.py
git commit -m "$(cat <<'EOF'
feat: compute_remaining_series_wp helper

Python port of seriesProbHCA from playoffs.js. Powers the
upcoming Series Momentum checkpoints. Best-of-N DP with home
pattern; falls back to Elo when matchup_probs are missing.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: build_momentum + wire into compute_series_data

**Files:**
- Modify: `export_dashboard_data.py` — add `build_momentum` at module level; wire it into `compute_series_data`'s per-slot result dict

- [ ] **Step 1: Add `build_momentum` at module level**

Place below `compute_remaining_series_wp`:

```python
def build_momentum(series_entry, matchup_probs, teams_by_code):
    """
    Build the Series Momentum checkpoint sequence + biggest-swing callout.

    Reads the entry's wins, completed games, home_pattern, and high/low seeds.
    Recomputes series WP from scratch at each checkpoint (Pre-series, After G1,
    After G2, ...). Returns None when no games have been played.

    Args:
        series_entry: dict produced by compute_series_data() for one slot.
        matchup_probs: dict[high][low] = {home, away, neutral}.
        teams_by_code: dict[code] -> team object from dashboard 'teams' list,
            used for Elo fallback.

    Returns:
        {
          'checkpoints': [{'label': 'Pre-series', 'high_wp': ..., 'low_wp': ...}, ...],
          'biggest_swing': {
              'from_label': str, 'to_label': str, 'game_num': int,
              'delta_pct': float, 'shifted_to': 'high'|'low',
              'winner_team': str
          }
        }
        or None if no games completed yet.
    """
    high = (series_entry.get('high_seed') or {}).get('team')
    low = (series_entry.get('low_seed') or {}).get('team')
    if not high or not low:
        return None

    games = series_entry.get('games') or []
    completed = [g for g in games if g.get('status') == 'completed']
    if not completed:
        return None

    fmt = series_entry.get('format') or 'best_of_5'
    target_wins = 1 if fmt == 'single_game' else 3
    home_pattern = tuple(series_entry.get('home_pattern')
                        or ('high', 'high', 'low', 'low', 'high'))

    elo_high = (teams_by_code.get(high) or {}).get('elo')
    elo_low = (teams_by_code.get(low) or {}).get('elo')

    def _wp(wins_h, wins_l):
        return compute_remaining_series_wp(
            matchup_probs, high, low, wins_h, wins_l,
            home_pattern=home_pattern, target_wins=target_wins,
            elo_high=elo_high, elo_low=elo_low,
        )

    # Pre-series checkpoint
    p0 = _wp(0, 0)
    checkpoints = [{
        'label': 'Pre-series',
        'high_wp': round(p0 * 100, 1),
        'low_wp': round((1 - p0) * 100, 1),
    }]

    wins_h, wins_l = 0, 0
    completed_sorted = sorted(completed, key=lambda g: g.get('game_num') or 0)
    for g in completed_sorted:
        winner = g.get('winner')
        if winner == high:
            wins_h += 1
        elif winner == low:
            wins_l += 1
        else:
            continue  # skip games with unknown winner
        p = _wp(wins_h, wins_l)
        checkpoints.append({
            'label': f'After G{g.get("game_num")}',
            'high_wp': round(p * 100, 1),
            'low_wp': round((1 - p) * 100, 1),
        })

    if len(checkpoints) < 2:
        return None  # nothing actually played that we could attribute

    # Biggest swing = consecutive checkpoint pair with largest |delta_high|
    biggest = None
    for i in range(1, len(checkpoints)):
        prev = checkpoints[i - 1]
        cur = checkpoints[i]
        delta = cur['high_wp'] - prev['high_wp']
        if biggest is None or abs(delta) > abs(biggest['delta']):
            biggest = {
                'i': i, 'delta': delta,
                'from_label': prev['label'], 'to_label': cur['label'],
            }

    # Resolve biggest swing -> game_num, winner
    swing_game = completed_sorted[biggest['i'] - 1]
    delta_pct = round(biggest['delta'], 1)
    shifted_to = 'high' if delta_pct > 0 else 'low'
    return {
        'checkpoints': checkpoints,
        'biggest_swing': {
            'from_label': biggest['from_label'],
            'to_label': biggest['to_label'],
            'game_num': swing_game.get('game_num'),
            'delta_pct': abs(delta_pct),
            'shifted_to': shifted_to,
            'winner_team': swing_game.get('winner'),
        },
    }
```

- [ ] **Step 2: Wire `build_momentum` into `compute_series_data`**

In `export_dashboard_data.py`, find the per-slot `result[slot_id] = {...}` block inside `compute_series_data` (currently around line 2416–2430). The existing dict ends with `'rs_h2h': _rs_h2h(high_code, low_code),`.

Find the function signature for `compute_series_data` (line 2163):

```python
def compute_series_data(playoff_results, matchup_probs, seeded_teams, series_win_probs, games_df):
```

Add a new parameter `teams_by_code` so the helper has access to Elo for the fallback. Change the signature to:

```python
def compute_series_data(playoff_results, matchup_probs, seeded_teams,
                        series_win_probs, games_df, teams_by_code):
```

In the result dict (currently line 2416), add a `'momentum'` key after `'rs_h2h'`:

```python
            result[slot_id] = {
                'id': slot_id,
                'round': defn['round'],
                'label': defn['label'],
                'format': fmt,
                'home_pattern': home_pattern,
                'high_seed': high,
                'low_seed': low,
                'status': status,
                'wins': {'high': wins_h, 'low': wins_l},
                'winner': winner,
                'series_win_prob': _build_prob_pair(slot_id, high_code, low_code),
                'games': games,
                'rs_h2h': _rs_h2h(high_code, low_code),
            }
            result[slot_id]['momentum'] = build_momentum(
                result[slot_id], matchup_probs, teams_by_code,
            )
```

Update the two call sites that invoke `compute_series_data`. Find them at lines 2531 and 2574 (`series_data = compute_series_data(...)`). Both must now pass `teams_by_code`. The `teams` list is already built inside `main()` — locate the variable holding it (search for `'teams': teams_data` or similar in the final output dict). Build a lookup dict and pass it:

```python
            teams_by_code = {t['team']: t for t in teams_data}
            series_data = compute_series_data(
                playoff_results_data, playoff_matchup_probs, seeded_teams,
                series_win_probs, games_df, teams_by_code,
            )
```

(Apply the same change to the second call site.)

- [ ] **Step 3: Smoke run a partial pipeline**

```bash
.venv/Scripts/python.exe export_dashboard_data.py
```

Expected: completes without traceback. If it errors on `teams_data` not being defined, confirm the variable name matches the list of team dicts in `main()` and update the lookup line accordingly.

- [ ] **Step 4: Validate output**

```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
for slot in ['qf1', 'sf1', 'final']:
    s = d['series'][slot]
    m = s.get('momentum')
    print(f'{slot} ({s[\"high_seed\"][\"team\"] if s[\"high_seed\"] else \"?\"} vs {s[\"low_seed\"][\"team\"] if s[\"low_seed\"] else \"?\"}): wins={s[\"wins\"]} momentum={m}')
"
```

Expected: For series with no completed games, `momentum=None`. For any in-progress or completed series (currently none, but qf1 once Play-In ends), `momentum` is a dict with `checkpoints` (length ≥ 2) and `biggest_swing`.

- [ ] **Step 5: Commit**

```bash
git add export_dashboard_data.py
git commit -m "$(cat <<'EOF'
feat: build_momentum + wire into series builder

Embeds per-series momentum data (checkpoints + biggest-swing
callout) under each Series Hub entry. Hidden when no games
have completed.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: build_tale_of_the_tape rows + wire in

**Files:**
- Modify: `export_dashboard_data.py` — add `build_tale_of_the_tape` at module level (rows only, edges in next task); wire into `compute_series_data`

- [ ] **Step 1: Add `build_tale_of_the_tape` at module level (rows only)**

Place below `build_momentum`:

```python
def build_tale_of_the_tape(high_team, low_team, teams_by_code,
                            box_metrics, paint_share, rs_h2h):
    """
    Build the Tale of the Tape data block for a series.

    8 fixed stat rows in this order:
        1. Pace          (poss/40)         from box_metrics
        2. Adj. Offense                    from teams_by_code (adj_off)
        3. Adj. Defense                    from teams_by_code (adj_def, lower better)
        4. Adj. Net                        from teams_by_code (adj_net)
        5. 3PT %                           from box_metrics
        6. Paint %                         from paint_share
        7. FT Rate                         from box_metrics
        8. Bench %                         from box_metrics

    Rows where either team is missing the stat are skipped (no n/a placeholders).

    Args:
        high_team, low_team: 3-letter codes. Either may be None
            (returns None in that case).
        teams_by_code: dict from dashboard 'teams' list keyed by code.
        box_metrics: output of compute_team_box_metrics().
        paint_share: output of compute_team_paint_share().
        rs_h2h: list of regular-season meetings (already computed by
            compute_series_data._rs_h2h).

    Returns:
        {'rows': [...], 'edges': []} or None if either team is missing.

    Edges field is intentionally empty in this task; it is populated by
    the build_tale_of_the_tape_edges call wired in Task 6.
    """
    if not high_team or not low_team:
        return None

    th = teams_by_code.get(high_team) or {}
    tl = teams_by_code.get(low_team) or {}
    bh = box_metrics.get(high_team) or {}
    bl = box_metrics.get(low_team) or {}

    row_specs = [
        ('pace',        'Pace (poss/40)', bh.get('pace'),                 bl.get('pace'),                 False),
        ('adj_off',     'Adj. Offense',   th.get('adj_off'),              tl.get('adj_off'),              False),
        ('adj_def',     'Adj. Defense',   th.get('adj_def'),              tl.get('adj_def'),              True),
        ('adj_net',     'Adj. Net',       th.get('adj_net'),              tl.get('adj_net'),              False),
        ('three_pct',   '3PT %',          bh.get('three_pct'),            bl.get('three_pct'),            False),
        ('paint_pct',   'Paint %',        paint_share.get(high_team),     paint_share.get(low_team),      False),
        ('ft_rate',     'FT Rate',        bh.get('ft_rate'),              bl.get('ft_rate'),              False),
        ('bench_share', 'Bench %',        bh.get('bench_share'),          bl.get('bench_share'),          False),
    ]

    rows = []
    for metric, label, hv, lv, lower_is_better in row_specs:
        if hv is None or lv is None:
            continue
        row = {
            'metric': metric, 'label': label,
            'high': round(float(hv), 3 if metric == 'ft_rate' else 1),
            'low':  round(float(lv), 3 if metric == 'ft_rate' else 1),
        }
        if lower_is_better:
            row['lower_is_better'] = True
        rows.append(row)

    return {'rows': rows, 'edges': []}
```

- [ ] **Step 2: Wire into `compute_series_data`**

`compute_series_data` needs three new arguments: `box_metrics`, `paint_share`, `teams_by_code` (already added in Task 4 step 2). Update the signature:

```python
def compute_series_data(playoff_results, matchup_probs, seeded_teams,
                        series_win_probs, games_df, teams_by_code,
                        box_metrics, paint_share):
```

Inside the per-slot loop, after the `momentum` line added in Task 4, add:

```python
            result[slot_id]['tale_of_the_tape'] = build_tale_of_the_tape(
                high_code, low_code, teams_by_code,
                box_metrics, paint_share, result[slot_id]['rs_h2h'],
            )
```

Update both call sites of `compute_series_data` (lines 2531 and 2574) to pass `box_metrics` and `paint_share`. Build them once near the top of `main()` (or just before the first call site):

```python
            all_game_stats = load_json('mvp_all_game_stats_2025.json') or []
            gamecode_to_teams = {
                int(r['GameCode']): (r['LocalTeam'], r['RoadTeam'])
                for r in (load_json('mvp_game_results.json') or [])
            }
            box_metrics = compute_team_box_metrics(all_game_stats, gamecode_to_teams)
            shot_stats_for_paint = load_json('docs/data/current/shot_stats.json') or {}
            paint_share = compute_team_paint_share(shot_stats_for_paint)
```

Place this block before the first `series_data = compute_series_data(...)` call (around line 2531). If `mvp_all_game_stats_2025.json` is loaded elsewhere in `main()`, reuse that variable instead.

Update both call sites:

```python
            series_data = compute_series_data(
                playoff_results_data, playoff_matchup_probs, seeded_teams,
                series_win_probs, games_df, teams_by_code,
                box_metrics, paint_share,
            )
```

- [ ] **Step 3: Run pipeline and validate**

```bash
.venv/Scripts/python.exe export_dashboard_data.py
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
qf1 = d['series']['qf1']
tot = qf1.get('tale_of_the_tape')
print('qf1 high:', qf1['high_seed'], 'low:', qf1['low_seed'])
print('rows:', len(tot['rows']) if tot else 0)
for r in (tot or {}).get('rows', []):
    print(' ', r)
print('edges (should be empty for now):', (tot or {}).get('edges'))
"
```

Expected: 8 rows printed with sane values. `edges: []`.

- [ ] **Step 4: Commit**

```bash
git add export_dashboard_data.py
git commit -m "$(cat <<'EOF'
feat: build_tale_of_the_tape rows + wire into series builder

Embeds 8-row stat comparison under each Series Hub entry.
Edges panel scaffolded but populated in next commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Edges algorithm

**Why:** Implements the deterministic Edges panel logic from the spec (Net / 3PT / Paint / Pace / Bench / Form / forced H2H), with shooting de-duplication and tie-break ordering.

**Files:**
- Modify: `export_dashboard_data.py` — extend `build_tale_of_the_tape` to populate the `edges` array

- [ ] **Step 1: Replace `return {'rows': rows, 'edges': []}` with the edges algorithm**

In `build_tale_of_the_tape`, replace the final `return` statement with:

```python
    edges = _compute_edges(
        high_team, low_team, th, tl, bh, bl,
        paint_share, rs_h2h,
    )
    return {'rows': rows, 'edges': edges}
```

- [ ] **Step 2: Add `_compute_edges` helper at module level (above `build_tale_of_the_tape`)**

```python
def _compute_edges(high_team, low_team, th, tl, bh, bl, paint_share, rs_h2h):
    """
    Deterministic Edges panel. Returns a list of up to 3 edge dicts:
        {'text': str, 'favor': 'high' | 'low' | None, 'type': str}

    Algorithm (matches spec):
      - Generate candidates: net, three_pct, paint_pct, pace, bench, form.
      - Drop the lower-scoring of {three_pct, paint_pct} so at most one
        shooting edge survives.
      - Sort surviving by score desc; tie-break by priority order.
      - Take top 2 (or top 3 if no H2H qualifies).
      - Append H2H as slot 3 if rs_h2h has at least 1 entry.
    """
    PRIORITY = ['net', 'three_pct', 'paint_pct', 'pace', 'bench', 'form']
    cands = []  # each: {'type','score','favor','text'}

    def _last5_wins(team_obj):
        last5 = team_obj.get('last5') or []
        return sum(1 for x in last5 if x == 'W')

    # 1. Net rating gap (always considered)
    net_h = th.get('adj_net')
    net_l = tl.get('adj_net')
    if net_h is not None and net_l is not None:
        gap = abs(net_h - net_l)
        favor = 'high' if net_h >= net_l else 'low'
        team = high_team if favor == 'high' else low_team
        diff = abs(round(net_h - net_l, 1))
        cands.append({
            'type': 'net', 'score': gap, 'favor': favor,
            'text': f'{team}: +{diff:g} net rating advantage',
        })

    # 2. 3PT shooting matchup: team's 3PT% vs opp 3PT% allowed
    th_3 = bh.get('three_pct')
    tl_3 = bl.get('three_pct')
    th_opp3 = bh.get('opp_three_pct')
    tl_opp3 = bl.get('opp_three_pct')
    if None not in (th_3, tl_3, th_opp3, tl_opp3):
        # Each team's expected edge from 3 vs the OTHER team's perimeter D
        h_edge = th_3 - tl_opp3   # high shoots vs low's defense
        l_edge = tl_3 - th_opp3   # low shoots vs high's defense
        # Pick the larger absolute team edge as the candidate
        if abs(h_edge) >= abs(l_edge):
            score = abs(h_edge)
            favor = 'high' if h_edge >= 0 else 'low'
            text = (f'{high_team}: {th_3:.0f}% from 3 vs {low_team} defending '
                    f'{tl_opp3:.0f}% — '
                    + ('edge ' + (high_team if favor == 'high' else low_team)))
        else:
            score = abs(l_edge)
            favor = 'low' if l_edge >= 0 else 'high'
            text = (f'{low_team}: {tl_3:.0f}% from 3 vs {high_team} defending '
                    f'{th_opp3:.0f}% — '
                    + ('edge ' + (low_team if favor == 'low' else high_team)))
        cands.append({'type': 'three_pct', 'score': score, 'favor': favor, 'text': text})

    # 3. Paint shooting matchup: 2PT% as proxy (higher is better; also opp 2PT% lower is better D)
    th_2 = bh.get('two_pct')
    tl_2 = bl.get('two_pct')
    th_opp2 = bh.get('opp_two_pct')
    tl_opp2 = bl.get('opp_two_pct')
    if None not in (th_2, tl_2, th_opp2, tl_opp2):
        h_edge = th_2 - tl_opp2   # high inside vs low's interior D
        l_edge = tl_2 - th_opp2
        if abs(h_edge) >= abs(l_edge):
            score = abs(h_edge)
            favor = 'high' if h_edge >= 0 else 'low'
            text = (f'{high_team}: {th_2:.0f}% on 2s vs {low_team} allowing '
                    f'{tl_opp2:.0f}% — '
                    + ('paint edge ' + (high_team if favor == 'high' else low_team)))
        else:
            score = abs(l_edge)
            favor = 'low' if l_edge >= 0 else 'high'
            text = (f'{low_team}: {tl_2:.0f}% on 2s vs {high_team} allowing '
                    f'{th_opp2:.0f}% — '
                    + ('paint edge ' + (low_team if favor == 'low' else high_team)))
        cands.append({'type': 'paint_pct', 'score': score, 'favor': favor, 'text': text})

    # 4. Pace mismatch (gap >= 3.0)
    pace_h = bh.get('pace')
    pace_l = bl.get('pace')
    if pace_h is not None and pace_l is not None:
        gap = abs(pace_h - pace_l)
        if gap >= 3.0:
            favor = 'high' if pace_h > pace_l else 'low'
            faster = high_team if favor == 'high' else low_team
            cands.append({
                'type': 'pace', 'score': gap, 'favor': favor,
                'text': f'{faster} plays {gap:.1f} more possessions per 40 — pace edge {faster}',
            })

    # 5. Bench depth (gap >= 5pp)
    bs_h = bh.get('bench_share')
    bs_l = bl.get('bench_share')
    if bs_h is not None and bs_l is not None:
        gap = abs(bs_h - bs_l)
        if gap >= 5.0:
            favor = 'high' if bs_h > bs_l else 'low'
            deeper = high_team if favor == 'high' else low_team
            cands.append({
                'type': 'bench', 'score': gap, 'favor': favor,
                'text': f'{deeper}: bench scores {(bs_h if favor == "high" else bs_l):.0f}% vs '
                        f'{(bs_l if favor == "high" else bs_h):.0f}% — depth edge {deeper}',
            })

    # 6. Recent form (last5 W differential >= 2)
    f_h = _last5_wins(th)
    f_l = _last5_wins(tl)
    gap = abs(f_h - f_l)
    if gap >= 2 and (th.get('last5') or tl.get('last5')):
        favor = 'high' if f_h > f_l else 'low'
        team = high_team if favor == 'high' else low_team
        cands.append({
            'type': 'form', 'score': float(gap), 'favor': favor,
            'text': f'{team}: {f_h}-{5-f_h} last 5 vs {high_team if favor == "low" else low_team} '
                    f'{f_l}-{5-f_l} — form edge {team}',
        })

    # De-duplicate shooting edges: keep the higher-scoring of {three_pct, paint_pct}
    shooting = [c for c in cands if c['type'] in ('three_pct', 'paint_pct')]
    if len(shooting) > 1:
        keep = max(shooting, key=lambda c: c['score'])
        cands = [c for c in cands if c['type'] not in ('three_pct', 'paint_pct')] + [keep]

    # Sort by score desc, tie-break by PRIORITY order
    cands.sort(key=lambda c: (-c['score'], PRIORITY.index(c['type'])))

    # H2H is forced into slot 3 if any meetings exist
    h2h_edge = None
    if rs_h2h:
        wins_h = sum(1 for m in rs_h2h if m.get('winner') == high_team)
        wins_l = sum(1 for m in rs_h2h if m.get('winner') == low_team)
        if wins_h == len(rs_h2h) and wins_l == 0:
            text = f'{high_team} swept RS series {wins_h}-0'
            favor = 'high'
        elif wins_l == len(rs_h2h) and wins_h == 0:
            text = f'{low_team} swept RS series {wins_l}-0'
            favor = 'low'
        else:
            text = f'Split RS series {wins_h}-{wins_l}'
            favor = None
        h2h_edge = {'type': 'h2h', 'text': text, 'favor': favor}

    take = 2 if h2h_edge else 3
    edges = cands[:take]
    if h2h_edge:
        edges.append(h2h_edge)

    # Strip score before returning (frontend doesn't need it)
    return [{'text': e['text'], 'favor': e['favor'], 'type': e['type']} for e in edges]
```

- [ ] **Step 3: Run pipeline and inspect edges**

```bash
.venv/Scripts/python.exe export_dashboard_data.py
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
for slot in ('qf1', 'qf2', 'qf3', 'qf4'):
    s = d['series'][slot]
    if not s['high_seed']: continue
    tot = s.get('tale_of_the_tape') or {}
    print(f'\n=== {slot}: {s[\"high_seed\"][\"team\"]} vs {s[\"low_seed\"][\"team\"]} ===')
    for e in tot.get('edges', []):
        print(f'  ▸ [{e[\"type\"]:8s}] favor={e[\"favor\"]} :: {e[\"text\"]}')
"
```

Expected: each QF prints 2 or 3 edges. If `rs_h2h` is non-empty, the last edge is type=h2h. Numbers in edge text should match the 8 stat rows.

- [ ] **Step 4: Commit**

```bash
git add export_dashboard_data.py
git commit -m "$(cat <<'EOF'
feat: deterministic Edges algorithm for Tale of the Tape

Generates 3 edges per series (Net + best of {3PT, Paint} + best of
{Pace, Bench, Form}, with H2H forced into slot 3 if RS meetings exist).
Tie-break by candidate priority order.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: series.html — Plotly CDN + inline styles

**Files:**
- Modify: `docs/series.html` — add Plotly CDN, add inline `<style>` block before existing `<link rel="stylesheet" href="style.css">`

- [ ] **Step 1: Add Plotly CDN inside `<head>`**

In `docs/series.html`, locate the existing line (line 16):

```html
    <link rel="stylesheet" href="style.css">
```

Immediately after it, add:

```html
    <script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
```

(Same version as `playoffs.html` for consistency.)

- [ ] **Step 2: Add inline `<style>` for the new sections**

Immediately after the new `<script>` tag, add:

```html
    <style>
        /* ── Tale of the Tape ───────────────────────────────────── */
        .tot-rows {
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
            margin-top: 1rem;
        }

        .tot-row {
            display: grid;
            grid-template-columns: 70px 1fr 70px;
            align-items: center;
            gap: 0.6rem;
        }

        .tot-row-label {
            text-align: center;
            font-family: 'Outfit', sans-serif;
            font-size: 0.7rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.2rem;
        }

        .tot-bar-wrap {
            display: flex;
            height: 24px;
            background: var(--bg-secondary);
            border-radius: 4px;
            overflow: hidden;
        }

        .tot-bar-half {
            display: flex;
            align-items: center;
            font-family: 'Outfit', sans-serif;
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--text-primary);
            padding: 0 0.5rem;
            transition: width 0.3s ease;
        }

        .tot-bar-half.high {
            justify-content: flex-end;
            border-radius: 4px 0 0 4px;
        }

        .tot-bar-half.low {
            justify-content: flex-start;
            border-radius: 0 4px 4px 0;
        }

        .tot-bar-half.dim {
            opacity: 0.45;
        }

        .tot-value {
            font-family: 'Outfit', sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--text-primary);
            text-align: center;
        }

        .tot-value.high { text-align: right; }
        .tot-value.low { text-align: left; }
        .tot-value.dim { color: var(--text-muted); font-weight: 600; }

        /* ── Edges panel ────────────────────────────────────────── */
        .tot-edges {
            margin-top: 1.25rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }

        .tot-edges-title {
            font-family: 'Outfit', sans-serif;
            font-size: 0.72rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .tot-edge {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            font-size: 0.85rem;
            color: var(--text-primary);
        }

        .tot-edge-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--text-muted);
            flex-shrink: 0;
        }

        /* ── Momentum chart ─────────────────────────────────────── */
        #series-momentum .momentum-callout {
            margin-top: 0.75rem;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        #series-momentum .momentum-callout strong {
            color: var(--text-primary);
        }

        @media (max-width: 600px) {
            .tot-row { grid-template-columns: 56px 1fr 56px; gap: 0.35rem; }
            .tot-value { font-size: 0.75rem; }
            .tot-bar-half { font-size: 0.68rem; padding: 0 0.35rem; }
        }
    </style>
```

- [ ] **Step 3: Smoke-load the page**

Open `docs/series.html?id=qf1` in a local browser (using whatever local-serving approach the user prefers — e.g. `python -m http.server 8000` from the `docs/` directory). Confirm the existing Hero / Timeline / H2H / Recaps still render unchanged. New sections will appear empty until JS is wired in Tasks 8–9.

- [ ] **Step 4: Commit**

```bash
git add docs/series.html
git commit -m "$(cat <<'EOF'
feat: series.html — Plotly CDN + styles for new sections

Prep work for Tale of the Tape and Series Momentum sections.
Adds Plotly script tag (matches playoffs.html version) and the
inline styles consumed by the upcoming JS render functions.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: series.js — renderTaleOfTheTape

**Files:**
- Modify: `docs/series.js` — add `renderTaleOfTheTape`, register in `renderSeries`

- [ ] **Step 1: Add a `<section id="series-tale">` slot to the `renderSeries` template**

Locate `renderSeries` (currently around line 59):

```js
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

Update to:

```js
function renderSeries(root, entry, dashboard) {
  root.innerHTML = `
    <section id="series-hero" class="series-section"></section>
    <section id="series-tale" class="series-section"></section>
    <section id="series-momentum" class="series-section"></section>
    <section id="series-timeline" class="series-section"></section>
    <section id="series-h2h" class="series-section"></section>
    <section id="series-recaps" class="series-section"></section>
  `;
  renderHero(document.getElementById('series-hero'), entry);
  renderTaleOfTheTape(document.getElementById('series-tale'), entry);
  renderMomentum(document.getElementById('series-momentum'), entry);
  renderTimeline(document.getElementById('series-timeline'), entry);
  renderH2H(document.getElementById('series-h2h'), entry);
  renderRecaps(document.getElementById('series-recaps'), entry, dashboard);
}
```

- [ ] **Step 2: Add `renderTaleOfTheTape` near the bottom of `series.js`**

Add this function (placement: above the existing `main()` invocation if there is one, or at the end of the file):

```js
function _formatTotValue(metric, value) {
  if (value == null || isNaN(value)) return '—';
  if (metric === 'ft_rate') return Number(value).toFixed(2);
  if (metric === 'pace') return Number(value).toFixed(1);
  return Number(value).toFixed(1);
}

function _suffixForMetric(metric) {
  if (metric === 'pace') return '';
  if (metric === 'ft_rate') return '';
  if (['three_pct', 'paint_pct', 'bench_share'].includes(metric)) return '%';
  return '';
}

function renderTaleOfTheTape(container, entry) {
  if (!container) return;
  const tot = entry && entry.tale_of_the_tape;
  if (!tot || !Array.isArray(tot.rows) || tot.rows.length === 0) {
    container.innerHTML = '';
    return;
  }

  const high = entry.high_seed && entry.high_seed.team;
  const low = entry.low_seed && entry.low_seed.team;
  const colorH = teamColor(high);
  const colorL = teamColor(low);

  const rowsHtml = tot.rows.map(r => {
    const lowerBetter = !!r.lower_is_better;
    // "Winner" (visually emphasized) is the side with the better stat.
    const hWins = lowerBetter ? r.high <= r.low : r.high >= r.low;
    const lWins = !hWins;

    // Bar widths: proportional split, floor at 15% so the loser is still visible.
    const total = (Number(r.high) || 0) + (Number(r.low) || 0);
    let hPct = 50, lPct = 50;
    if (total > 0) {
      hPct = Math.max(15, Math.min(85, Math.round((r.high / total) * 100)));
      lPct = 100 - hPct;
    }

    return `
      <div class="tot-row-block">
        <div class="tot-row-label">${r.label}</div>
        <div class="tot-row">
          <div class="tot-value high ${lWins ? 'dim' : ''}">${_formatTotValue(r.metric, r.high)}${_suffixForMetric(r.metric)}</div>
          <div class="tot-bar-wrap">
            <div class="tot-bar-half high ${lWins ? 'dim' : ''}"
                 style="width:${hPct}%; background:${colorH || 'var(--accent-blue)'}"></div>
            <div class="tot-bar-half low ${hWins ? 'dim' : ''}"
                 style="width:${lPct}%; background:${colorL || 'var(--accent-red)'}"></div>
          </div>
          <div class="tot-value low ${hWins ? 'dim' : ''}">${_formatTotValue(r.metric, r.low)}${_suffixForMetric(r.metric)}</div>
        </div>
      </div>
    `;
  }).join('');

  const edgesHtml = (tot.edges || []).map(e => {
    let dotColor = 'var(--text-muted)';
    if (e.favor === 'high') dotColor = colorH || 'var(--accent-blue)';
    if (e.favor === 'low') dotColor = colorL || 'var(--accent-red)';
    return `
      <div class="tot-edge">
        <span class="tot-edge-dot" style="background:${dotColor}"></span>
        <span>${e.text}</span>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    <div class="stat-card">
      <h3>Tale of the Tape</h3>
      <div class="tot-rows">${rowsHtml}</div>
      ${edgesHtml ? `
        <div class="tot-edges">
          <div class="tot-edges-title">Edges</div>
          ${edgesHtml}
        </div>` : ''}
    </div>
  `;
}
```

- [ ] **Step 3: Visual smoke check**

Reload `docs/series.html?id=qf1` in the browser. Expect:
- "Tale of the Tape" heading.
- 8 rows with horizontal split bars and team values on either side.
- "Edges" subsection underneath listing 2 or 3 short bullet lines with colored dots.
- Page does not crash on `qf3` (likely `awaiting_teams` until Play-In ends) — the section just renders empty.

If a row's value is missing for one team, that single row should be silently skipped. If both `high_seed` and `low_seed` are null (Final before SF resolved), the entire section should render empty without error.

- [ ] **Step 4: Commit**

```bash
git add docs/series.js
git commit -m "$(cat <<'EOF'
feat: Series Hub renderTaleOfTheTape section

Renders 8 diverging-bar stat rows + Edges panel in series.html.
Wired into renderSeries between Hero and Timeline. Hides
gracefully when teams aren't set or data is missing.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: series.js — renderMomentum

**Files:**
- Modify: `docs/series.js` — add `renderMomentum` (the section slot was already added in Task 8)

- [ ] **Step 1: Add `renderMomentum` near `renderTaleOfTheTape`**

Insert immediately below `renderTaleOfTheTape`:

```js
function renderMomentum(container, entry) {
  if (!container) return;
  const m = entry && entry.momentum;
  if (!m || !Array.isArray(m.checkpoints) || m.checkpoints.length < 2) {
    container.innerHTML = '';
    return;
  }
  if (typeof Plotly === 'undefined') {
    container.innerHTML = '<div class="stat-card"><h3>Series Momentum</h3><p>Plotly failed to load.</p></div>';
    return;
  }

  const high = entry.high_seed && entry.high_seed.team;
  const low = entry.low_seed && entry.low_seed.team;
  const colorH = teamColor(high) || '#60a5fa';
  const colorL = teamColor(low) || '#f87171';

  container.innerHTML = `
    <div class="stat-card">
      <h3>Series Momentum</h3>
      <div id="momentum-chart" style="width:100%;height:280px"></div>
      ${_renderMomentumCallout(m.biggest_swing)}
    </div>
  `;

  const labels = m.checkpoints.map(c => c.label);
  const highVals = m.checkpoints.map(c => c.high_wp);
  const lowVals = m.checkpoints.map(c => c.low_wp);

  const traces = [
    {
      x: labels, y: highVals, mode: 'lines+markers',
      name: high || 'Higher seed',
      line: { color: colorH, width: 3 },
      marker: { size: 8, color: colorH },
    },
    {
      x: labels, y: lowVals, mode: 'lines+markers',
      name: low || 'Lower seed',
      line: { color: colorL, width: 3 },
      marker: { size: 8, color: colorL },
    },
  ];

  const layout = {
    margin: { l: 40, r: 16, t: 8, b: 36 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {
      family: 'Inter, sans-serif',
      color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary') || '#cbd5e1',
      size: 12,
    },
    xaxis: { gridcolor: 'rgba(255,255,255,0.06)', tickfont: { size: 11 } },
    yaxis: {
      title: { text: 'Series WP %', font: { size: 11 } },
      range: [0, 100], gridcolor: 'rgba(255,255,255,0.06)',
      ticksuffix: '%',
    },
    showlegend: true,
    legend: { orientation: 'h', y: -0.2, x: 0.5, xanchor: 'center' },
    hovermode: 'x unified',
  };

  Plotly.newPlot('momentum-chart', traces, layout, {
    displayModeBar: false, responsive: true,
  });
}

function _renderMomentumCallout(swing) {
  if (!swing) return '';
  const winner = swing.winner_team || (swing.shifted_to === 'high' ? 'higher seed' : 'lower seed');
  const sign = swing.shifted_to === 'high' ? '' : '';  // magnitude only; direction is in 'winner'
  return `
    <div class="momentum-callout">
      <strong>Biggest swing:</strong>
      G${swing.game_num} — ${winner} win shifted series WP ${sign}${swing.delta_pct}%
    </div>
  `;
}
```

- [ ] **Step 2: Visual smoke check**

Reload `docs/series.html?id=qf1`. Pre-Play-In, no series has any completed games, so the Momentum section should render empty (no card visible) — not throw an error.

To exercise the chart end-to-end before real games are played, temporarily fake a completed game:

```bash
.venv/Scripts/python.exe -c "
import json
p = 'docs/data/current/dashboard.json'
d = json.load(open(p, encoding='utf-8'))
qf = d['series']['qf1']
qf['games'][0] = {**qf['games'][0], 'status': 'completed', 'winner': qf['high_seed']['team'], 'home_score': 88, 'away_score': 79}
qf['wins'] = {'high': 1, 'low': 0}
qf['status'] = 'in_progress'
# Recompute momentum inline using the same logic as backend (cheaper: just hand-craft for the smoke test)
qf['momentum'] = {
    'checkpoints': [
        {'label': 'Pre-series', 'high_wp': qf['series_win_prob']['high'], 'low_wp': qf['series_win_prob']['low']},
        {'label': 'After G1',   'high_wp': min(99.0, qf['series_win_prob']['high'] + 14.0),
                                'low_wp':  max(1.0,  qf['series_win_prob']['low']  - 14.0)},
    ],
    'biggest_swing': {'from_label': 'Pre-series', 'to_label': 'After G1', 'game_num': 1,
                      'delta_pct': 14.0, 'shifted_to': 'high', 'winner_team': qf['high_seed']['team']}
}
json.dump(d, open(p, 'w', encoding='utf-8'), indent=2)
print('patched qf1 with fake G1 completion')
"
```

Reload the page; expect a 280px-tall Plotly chart with two lines (high seed climbing, low seed descending) and a "Biggest swing" callout.

**Roll back the fake patch** before continuing:

```bash
.venv/Scripts/python.exe export_dashboard_data.py
```

(This re-runs the export and overwrites the patched file with real data.)

- [ ] **Step 3: Commit**

```bash
git add docs/series.js
git commit -m "$(cat <<'EOF'
feat: Series Hub renderMomentum section

Plotly line chart of series WP at each checkpoint plus a
biggest-swing callout. Hidden until at least one game completes.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: about.html update + final smoke test

**Files:**
- Modify: `docs/about.html` — append to the playoff-features paragraph
- New (ad-hoc): `inspect_tale_and_momentum.py` — quick post-refresh validation script

- [ ] **Step 1: Add description to about.html**

Open `docs/about.html` and find the existing paragraph that lists playoff features (search for "Path to Title" or "Series Hub"). Append:

```html
<p>
  Each Series Hub page now opens with a <strong>Tale of the Tape</strong>:
  an 8-row stat comparison (pace, adjusted ratings, shooting splits, FT rate,
  bench share) and a deterministic <em>Edges</em> panel that surfaces the
  three sharpest matchup advantages — including head-to-head context from
  the regular season. Once a series begins, a <strong>Series Momentum</strong>
  chart tracks how series win probability shifts after each completed game,
  with a callout for the biggest swing.
</p>
```

Pick the appropriate sibling element to insert before/after based on the surrounding markup style.

- [ ] **Step 2: Create the inspect script**

Create `inspect_tale_and_momentum.py` at the repo root:

```python
"""
Quick sanity check for Tale of the Tape + Series Momentum data.
Run after `python refresh_all.py --no-fetch` to print a summary
of every series entry.
"""
import json

with open('docs/data/current/dashboard.json', encoding='utf-8') as f:
    d = json.load(f)

print(f"Round: {d.get('round')}")
print()

for slot in ('qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final'):
    s = d['series'].get(slot) or {}
    hi = (s.get('high_seed') or {}).get('team') or '?'
    lo = (s.get('low_seed') or {}).get('team') or '?'
    print(f"=== {slot}: {hi} vs {lo} ({s.get('status')}) ===")

    tot = s.get('tale_of_the_tape') or {}
    rows = tot.get('rows') or []
    print(f"  rows: {len(rows)}")
    for r in rows:
        better = ''
        if r.get('lower_is_better'):
            better = ' (lower better)'
        print(f"    {r['label']:<18s}  {r['high']:>7}  vs  {r['low']:<7}{better}")

    edges = tot.get('edges') or []
    print(f"  edges: {len(edges)}")
    for e in edges:
        print(f"    [{e['type']:<10s}] favor={str(e['favor']):<5s} {e['text']}")

    m = s.get('momentum')
    if m:
        cps = m.get('checkpoints') or []
        bs = m.get('biggest_swing') or {}
        print(f"  momentum: {len(cps)} checkpoints, biggest swing G{bs.get('game_num')} {bs.get('delta_pct')}% to {bs.get('shifted_to')}")
    else:
        print(f"  momentum: (none — no games played)")
    print()
```

- [ ] **Step 3: Run full refresh + inspect**

```bash
.venv/Scripts/python.exe refresh_all.py --no-fetch --skip-wp-train
.venv/Scripts/python.exe inspect_tale_and_momentum.py
```

Expected:
- `refresh_all.py` completes without traceback (skip-wp-train short-circuits the slow WP retraining).
- `inspect_tale_and_momentum.py` prints 7 series. Each QF prints 8 rows + 2-3 edges. Each series with no completed games shows `momentum: (none — no games played)`.

- [ ] **Step 4: Browser smoke test**

Serve `docs/` locally and open:

- `series.html?id=qf1` — Tale of the Tape renders with 8 rows + Edges panel; Momentum hidden.
- `series.html?id=qf3` (or any unfilled slot) — Tale of the Tape and Momentum both hidden; rest of page unchanged.
- `playoffs.html` — bracket page still works; click into a QF series; lands on the new-look Series Hub.

Verify on a narrow viewport (≤600px) that the diverging bars don't overflow.

- [ ] **Step 5: Commit**

```bash
git add docs/about.html inspect_tale_and_momentum.py
git commit -m "$(cat <<'EOF'
docs: about.html — describe Tale of the Tape & Momentum

Adds a paragraph under the playoff-features section. Also
adds inspect_tale_and_momentum.py as an ad-hoc smoke check
script following the existing inspect_*.py pattern.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Checklist (executed by plan author)

**Spec coverage:**
- 8 stat rows in fixed order — Task 5 (`row_specs`).
- Diverging-bar visual — Task 7 styles + Task 8 render.
- Edges algorithm with shooting de-dup, tie-break ordering, forced H2H — Task 6 (`_compute_edges`).
- Lifecycle: Tale of the Tape needs both seeds, Momentum needs ≥1 completed game — Task 5 / Task 4 early returns + Task 8 / Task 9 empty-render.
- Plotly line chart with markers, two lines, biggest-swing callout — Task 9.
- `compute_remaining_series_wp` mirrors `seriesProbHCA` — Task 3 with cross-check against existing `series_win_prob`.
- Edge cases (awaiting_teams, missing matchup_probs, single-game Final) — covered in Task 4 (target_wins=1 path), Task 5 (None returns), Task 8 / Task 9 empty renders.
- about.html paragraph — Task 10.

**Placeholder scan:** No "TBD"/"TODO"/"add validation"/"similar to Task N". Each step has either a code block or an exact command with expected output.

**Type / name consistency:**
- `compute_team_box_metrics` produces `pace, three_pct, two_pct, ft_rate, bench_share, opp_three_pct, opp_two_pct, games`. All consumers in Task 5 (`build_tale_of_the_tape` row_specs) and Task 6 (`_compute_edges`) reference these exact field names. ✓
- `compute_team_paint_share` returns `dict[code] -> float`. Task 5 indexes it as `paint_share.get(team)`. ✓
- `build_momentum` returns `{'checkpoints': [...], 'biggest_swing': {...}}` matching the spec data shape and consumed by `renderMomentum` field-for-field. ✓
- `renderTaleOfTheTape` and `renderMomentum` are referenced in `renderSeries` (Task 8 step 1) and defined in Tasks 8/9. ✓
- `_compute_edges` is added at module level above `build_tale_of_the_tape` (Task 6 step 2) and called from inside `build_tale_of_the_tape` (Task 6 step 1). ✓

**Notes for the executor:**
- The codebase has no test runner; validation is via inline `python -c` + the new `inspect_tale_and_momentum.py`.
- Path-to-Title-style branching trees are out of scope — this plan only adds the two sections in the spec.
- If the box-score validation in Task 1 step 2 shows missing teams, suspect: (a) `mvp_game_results.json` outdated, or (b) a team-code change not covered by `gamecode_to_teams`. Investigate before continuing.
