# Calibrated Season Odds + What-If Playoffs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Top 4 / Top 6 / Top 10 odds honest (calibrated) and stop the Playoff Simulator presenting round-N standings as final playoff seeds.

**Architecture:** `simulate_monte_carlo.py` replaces its per-game formula (raw adj-net + Elo + triple-counted home court fed into the in-game WP model, with no uncertainty about team strength) with a Bayesian team-strength model: game margin = HCA + s_home − s_away + N(0, σ²), prior s ~ N(preseason Elo prior, τ²). Each simulation draws one strength vector from the posterior, so early-season uncertainty propagates into the standings. `export_dashboard_data.py` only produces championship odds / path to title / series data / the "Pre-Playoff" history baseline once every regular-season game is played, and exports a `regular_season_complete` flag; `docs/playoffs.js` uses it to label the bracket "If the season ended today".

**Tech Stack:** Python 3.12, numpy, pandas, pytest; vanilla JS + Plotly frontend (no build step).

**Spec:** The audit in this session (findings #1 and #2) plus the user's choice "What-if mode": keep the interactive bracket, label it "If the season ended today", hide Path to Title until the regular season ends, backend stops producing championship odds / path-to-title / series data / Pre-Playoff baseline until then.

**Evidence the design rests on** (scratch backtest, 7 round-robin seasons 2016–2024, checkpoints R4/8/12/20, ~1,450 Top-4/6/10 predictions):

| predicted bin | current model: actual | calibrated prototype: actual |
|---|---|---|
| 0–2% (avg 0.3%) | 2.3% | 0.8% |
| 2–10% (avg 5.3%) | 11.2% | 5.4% |
| 70–90% (avg 80.7%) | 65.7% | 80.4% |
| 98–100% (avg 99.6%) | 97.2% | 98.9% |

Pooled log loss 0.3908 (current) vs 0.3775 (prototype). Historical regression: rest-of-season margin ≈ 0.36 × first-4-games margin (0.49 after 8, 0.63 after 12) — i.e. ~7.5 pseudo-games of shrinkage, which is what σ=12, τ=4.5 gives (σ²/τ² = 7.1). Mean home margin 3.8 pts, home win% 62.6% (3,895 games 2007–2025).

## Global Constraints

- Work on branch `fix/calibrated-odds-whatif-playoffs` (main is the default branch; CI auto-commits there).
- Never hardcode a season year in pipeline scripts — use `season_config` (`tests/test_no_hardcoded_season.py`).
- Windows venv: run Python as `.venv/Scripts/python.exe`; tests: `.venv/Scripts/python.exe -m pytest tests/ -q`.
- `monte_carlo_results{suffix}.json` schema must stay identical (keys `Team, Top4_Pct, Top6_Pct, Top10_Pct, Sort_Metric, Avg_Wins, Current_Wins, Win_Distribution, Seed_Distribution`) — five `visualize_*.py` scripts and the export read it.
- Model constants: `SIGMA_GAME = 12.0`, `TAU_STRENGTH = 4.5`, `HCA_PTS = 3.0`, `ELO_PER_POINT = 25.0` (change only via Task 2's backtest).
- Always update `docs/about.html` when behaviour shown on the site changes.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A team in the schedule with zero games played** (round 1 partially played, or a postponed game) must be simulated from its prior, not crash with `KeyError` — test `test_team_with_no_games_is_simulated` in Task 1.
2. **Zero games played at all** (pre-season run) — `run_monte_carlo` must still write output from priors alone — test `test_simulate_season_with_no_played_games` in Task 1.
3. **Home-heavy starts** (PAN played its first 4 games at home) must not inflate strength — test `test_posterior_removes_home_court` in Task 1.
4. **An old dashboard without `regular_season_complete`** (e.g. the archive) must keep today's playoff-page behaviour — the JS treats a missing flag as complete (Task 4, Step 3 code).
5. **A stale mid-season "Pre-Playoff" entry already in `docs/data/current/dashboard.json`** must be dropped, not carried forward — Task 3, Step 4 code + Task 5 verification.

---

### Task 1: Bayesian strength model in the season simulator

**Files:**
- Modify: `simulate_monte_carlo.py` (add constants + `posterior_strength` + `simulate_season`; rewrite the body of `run_monte_carlo` sections 1b–3)
- Create: `tests/test_monte_carlo.py`

**Interfaces:**
- Consumes: existing `_rank_with_h2h(sim_wins, sim_pd, sim_h2h_wins, sim_h2h_pd, num_teams, num_simulations)` in `simulate_monte_carlo.py`; `calculate_elo._load_prior_season_elos(current_season) -> dict[str, float]` and `calculate_elo.STARTING_ELO`.
- Produces (used by Task 2):
  - `posterior_strength(num_teams: int, games: list[tuple[int, int, float]], prior_mean: array-like, sigma=SIGMA_GAME, tau=TAU_STRENGTH, hca=HCA_PTS) -> tuple[np.ndarray (n,), np.ndarray (n, n)]` — `games` items are `(home_idx, away_idx, home_margin)`.
  - `simulate_season(num_teams: int, played: list[tuple[int, int, int, int]], remaining: list[tuple[int, int]], prior_mean, num_simulations: int, rng: np.random.Generator, sigma=SIGMA_GAME, tau=TAU_STRENGTH, hca=HCA_PTS) -> tuple[np.ndarray (sims, n) int ranks 0-based, np.ndarray (sims, n) wins]` — `played` items are `(home_idx, away_idx, home_pts, away_pts)`.
  - Module constants `SIGMA_GAME, TAU_STRENGTH, HCA_PTS, ELO_PER_POINT`.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b fix/calibrated-odds-whatif-playoffs
```

- [ ] **Step 2: Write the failing tests** — create `tests/test_monte_carlo.py`:

```python
"""Season simulator: Bayesian team strength + calibrated standings odds."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simulate_monte_carlo import (HCA_PTS, TAU_STRENGTH, posterior_strength,
                                  simulate_season)


def _round_robin(n):
    """Double round-robin [(home, away), ...] in round order (circle method):
    the first k*n/2 games are exactly k rounds, every team playing once per round."""
    teams = list(range(n))
    rounds = []
    for r in range(n - 1):
        pairs = [(teams[i], teams[n - 1 - i]) for i in range(n // 2)]
        if r % 2:
            pairs = [(a, h) for h, a in pairs]
        rounds.append(pairs)
        teams = [teams[0], teams[-1]] + teams[1:-1]
    second_half = [[(a, h) for h, a in rd] for rd in rounds]
    return [g for rd in rounds + second_half for g in rd]


def test_posterior_without_games_is_prior():
    prior = np.array([2.0, -1.0, 0.0])
    mean, cov = posterior_strength(3, [], prior)
    np.testing.assert_allclose(mean, prior)
    np.testing.assert_allclose(np.sqrt(np.diag(cov)), TAU_STRENGTH)


def test_posterior_shrinks_hot_start():
    # Team 0 wins 4 neutral-ish games by +20 (2 home, 2 away) against average teams
    games = [(0, 1, 20 + HCA_PTS), (2, 0, -20 + HCA_PTS),
             (0, 3, 20 + HCA_PTS), (4, 0, -20 + HCA_PTS)]
    mean, _ = posterior_strength(5, games, np.zeros(5))
    assert 4.0 < mean[0] < 12.0          # history says ~36% of a 4-game margin persists


def test_posterior_removes_home_court():
    # Team 0 plays 4 home games, each won by exactly the home-court edge
    games = [(0, k, HCA_PTS) for k in (1, 2, 3, 4)]
    mean, _ = posterior_strength(5, games, np.zeros(5))
    assert abs(mean[0]) < 0.5


def test_posterior_recovers_strengths_with_many_games():
    rng = np.random.default_rng(1)
    n = 12
    true = rng.normal(0, 5, n)
    games = []
    for _ in range(3):
        for h, a in _round_robin(n):
            games.append((h, a, HCA_PTS + true[h] - true[a] + rng.normal(0, 12)))
    mean, _ = posterior_strength(n, games, np.zeros(n))
    assert np.corrcoef(mean, true)[0, 1] > 0.9


def _odds(ranks):
    return {c: (ranks < c).mean(axis=0) for c in (4, 6, 10)}


def test_simulate_season_invariants():
    n = 20
    fixtures = _round_robin(n)
    played = [(h, a, 80, 75) for h, a in fixtures[:40]]
    ranks, wins = simulate_season(n, played, fixtures[40:], np.zeros(n), 2000,
                                  np.random.default_rng(4))
    odds = _odds(ranks)
    assert abs(odds[4].sum() - 4) < 1e-9
    assert abs(odds[6].sum() - 6) < 1e-9
    assert abs(odds[10].sum() - 10) < 1e-9
    assert np.all(odds[4] <= odds[6]) and np.all(odds[6] <= odds[10])
    assert np.allclose(wins.sum(axis=1), len(fixtures))   # every game has one winner


def test_four_game_hot_start_is_not_a_lock():
    """Regression for the R4 2026-27 bug: 4-0 by +20 showed 99.4% Top 4."""
    n = 20
    fixtures = _round_robin(n)
    rounds, rest = fixtures[:40], fixtures[40:]
    played = []
    for h, a in rounds:
        if h == 0:
            played.append((h, a, 95, 75))
        elif a == 0:
            played.append((h, a, 75, 95))
        else:
            played.append((h, a, 80, 78))
    ranks, _ = simulate_season(n, played, rest, np.zeros(n), 4000,
                               np.random.default_rng(5))
    odds = _odds(ranks)
    assert odds[4][0] < 0.95
    assert odds[10].min() > 0.03          # nobody is dead after 4 rounds


def test_simulate_season_with_no_played_games():
    n = 6
    fixtures = _round_robin(n)
    ranks, wins = simulate_season(n, [], fixtures, np.zeros(n), 500,
                                  np.random.default_rng(6))
    assert ranks.shape == (500, n) and wins.shape == (500, n)


def test_team_with_no_games_is_simulated():
    n = 4
    played = [(0, 1, 80, 70)]                 # teams 2 and 3 have not played yet
    remaining = [(2, 3), (3, 0), (1, 2)]
    ranks, wins = simulate_season(n, played, remaining, np.zeros(n), 500,
                                  np.random.default_rng(7))
    assert wins[:, 2].max() >= 1 and wins[:, 3].max() >= 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_monte_carlo.py -q`
Expected: FAIL — `ImportError: cannot import name 'HCA_PTS' from 'simulate_monte_carlo'`.

- [ ] **Step 4: Add the model to `simulate_monte_carlo.py`**

Replace the import block at the top of the file:

```python
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import json
import os

from season_config import CURRENT_SEASON
from wp_model_utils import predict_wp
```

with:

```python
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import json
import os

from season_config import CURRENT_SEASON


# ── Team-strength model ──────────────────────────────────────────────
# margin(home) = HCA + s_home - s_away + N(0, SIGMA_GAME²), s ~ N(prior, TAU²).
# Backtested on 2016-2024 (backtest_monte_carlo.py): σ²/τ² ≈ 7 pseudo-games of
# shrinkage matches how much of an early-season margin actually persists.
SIGMA_GAME = 12.0     # residual sd of a single game's margin (pts)
TAU_STRENGTH = 4.5    # sd of true team strength around its preseason prior (pts/game)
HCA_PTS = 3.0         # home-court advantage (pts)
ELO_PER_POINT = 25.0  # Elo points per point of margin, for the preseason prior


def posterior_strength(num_teams, games, prior_mean,
                       sigma=SIGMA_GAME, tau=TAU_STRENGTH, hca=HCA_PTS):
    """Posterior mean and covariance of team strengths (pts/game vs average).

    games: iterable of (home_idx, away_idx, home_margin). Opponent strength and
    venue are both accounted for, so a home-heavy or soft early schedule does
    not inflate a team's rating.
    """
    prior_mean = np.asarray(prior_mean, dtype=float)
    precision = np.eye(num_teams) / tau ** 2
    b = prior_mean / tau ** 2
    for h, a, margin in games:
        x = np.zeros(num_teams)
        x[h], x[a] = 1.0, -1.0
        precision += np.outer(x, x) / sigma ** 2
        b = b + x * (margin - hca) / sigma ** 2
    cov = np.linalg.inv(precision)
    cov = (cov + cov.T) / 2   # exact symmetry for multivariate_normal
    return cov @ b, cov


def simulate_season(num_teams, played, remaining, prior_mean, num_simulations, rng,
                    sigma=SIGMA_GAME, tau=TAU_STRENGTH, hca=HCA_PTS):
    """Simulate the rest of the regular season.

    played:    list of (home_idx, away_idx, home_pts, away_pts)
    remaining: list of (home_idx, away_idx)
    Each simulation draws one strength vector from the posterior, so the
    uncertainty about how good a team really is carries through all of its
    remaining games. Returns (team_ranks, sim_wins), both (sims, teams).
    """
    base_wins = np.zeros(num_teams)
    base_pd = np.zeros(num_teams)
    base_h2h_wins = np.zeros((num_teams, num_teams))
    base_h2h_pd = np.zeros((num_teams, num_teams))
    for h, a, hp, ap in played:
        m = hp - ap
        winner, loser = (h, a) if m > 0 else (a, h)
        base_wins[winner] += 1
        base_h2h_wins[winner, loser] += 1
        base_pd[h] += m
        base_pd[a] -= m
        base_h2h_pd[h, a] += m
        base_h2h_pd[a, h] -= m

    mean, cov = posterior_strength(num_teams, [(h, a, hp - ap) for h, a, hp, ap in played],
                                   prior_mean, sigma, tau, hca)
    strengths = rng.multivariate_normal(mean, cov, size=num_simulations)

    sim_wins = np.tile(base_wins, (num_simulations, 1))
    sim_pd = np.tile(base_pd, (num_simulations, 1))
    sim_h2h_wins = np.tile(base_h2h_wins, (num_simulations, 1, 1))
    sim_h2h_pd = np.tile(base_h2h_pd, (num_simulations, 1, 1))

    for h, a in remaining:
        margins = rng.normal(strengths[:, h] - strengths[:, a] + hca, sigma)
        home_wins = (margins > 0).astype(int)
        away_wins = 1 - home_wins
        sim_wins[:, h] += home_wins
        sim_wins[:, a] += away_wins
        sim_pd[:, h] += margins
        sim_pd[:, a] -= margins
        sim_h2h_wins[:, h, a] += home_wins
        sim_h2h_wins[:, a, h] += away_wins
        sim_h2h_pd[:, h, a] += margins
        sim_h2h_pd[:, a, h] -= margins

    team_ranks = _rank_with_h2h(sim_wins, sim_pd, sim_h2h_wins, sim_h2h_pd,
                                num_teams, num_simulations)
    return team_ranks, sim_wins
```

Place this block right after the imports (before `# ── Euroleague tiebreaker helpers`). `_rank_with_h2h` is defined later in the module; that is fine because it is only looked up when `simulate_season` runs.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_monte_carlo.py -q`
Expected: 8 passed.

- [ ] **Step 6: Rewire `run_monte_carlo` to use the model**

Replace the whole `run_monte_carlo` function (from `def run_monte_carlo(num_simulations=10000):` through the line `    # 4. Rank and Aggregate` block's `team_ranks = _rank_with_h2h(...)` call — i.e. everything before `    results = {}`) with:

```python
def run_monte_carlo(num_simulations=10000):
    print("--- 🏀 Euroleague Monte Carlo Playoff Matrix 🏀 ---")
    print(f"Running {num_simulations} simulations of the remaining season...")

    from team_aliases import NAME_TO_CODE as name_to_code
    from calculate_elo import STARTING_ELO, _load_prior_season_elos

    # 1. Schedule: the regular season's fixtures define teams and gamecodes
    try:
        items = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml').getroot().findall('item')
    except Exception as e:
        print(f"Error loading schedule: {e}")
        return
    fixtures = []  # (gamecode, home, away, xml_played)
    for item in items:
        gc_text = item.find('gamecode').text
        gc = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
        h = name_to_code.get(item.find('hometeam').text, "UNK")
        a = name_to_code.get(item.find('awayteam').text, "UNK")
        played_el = item.find('played')
        xml_played = played_el is not None and (played_el.text or '').lower() == 'true'
        if h != "UNK" and a != "UNK":
            fixtures.append((gc, h, a, xml_played))
    team_list = sorted({t for _, h, a, _ in fixtures for t in (h, a)})
    team_to_idx = {t: i for i, t in enumerate(team_list)}
    num_teams = len(team_list)
    rs_codes = {gc for gc, _, _, _ in fixtures}

    # 2. Results: regular-season games only (gamecodes that are in the RS schedule)
    game_scores = {}
    if os.path.exists('mvp_game_results.json'):
        df = pd.read_json('mvp_game_results.json')
        if len(df):
            df = df[(df['LocalScore'] > 0) & (df['RoadScore'] > 0) & (df['GameCode'].isin(rs_codes))]
            for _, row in df.iterrows():
                game_scores[int(row['GameCode'])] = (row['LocalTeam'], row['RoadTeam'],
                                                 int(row['LocalScore']), int(row['RoadScore']))
    played = [(team_to_idx[h], team_to_idx[a], hp, ap)
              for h, a, hp, ap in game_scores.values() if h in team_to_idx and a in team_to_idx]
    # A game counts as played if we have its score, or the XML says so (stale-XML guard
    # is the score check; an XML-played game without a score is skipped, not simulated)
    remaining = [(team_to_idx[h], team_to_idx[a]) for gc, h, a, xml_played in fixtures
                 if gc not in game_scores and not xml_played]
    print(f"Loaded {num_teams} teams, {len(played)} played games, "
          f"{len(remaining)} unplayed games to simulate.")

    # 3. Preseason prior: last season's Elo with regression to the mean
    prior_elos = _load_prior_season_elos(CURRENT_SEASON)
    prior_mean = np.array([(prior_elos.get(t, STARTING_ELO) - STARTING_ELO) / ELO_PER_POINT
                           for t in team_list])

    # 4. Simulate. Seed from the round number so each round is reproducible.
    _suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    _round_num = int(_suffix.replace('_R', '')) if _suffix else None
    rng = np.random.default_rng(_round_num)  # None = truly random each run
    team_ranks, sim_wins = simulate_season(num_teams, played, remaining, prior_mean,
                                           num_simulations, rng)
    base_wins = np.zeros(num_teams)
    for h, a, hp, ap in played:
        base_wins[h if hp > ap else a] += 1
    print("Aggregating ranks...")
```

Leave everything from `    results = {}` (the aggregation loop) to the end of the file unchanged — it uses `team_list`, `team_ranks`, `sim_wins`, `base_wins`, `num_teams`, `num_simulations`, which the new code defines with the same names and shapes. Also delete the now-unused import `from wp_model_utils import predict_wp` if it is still present.

- [ ] **Step 7: Run the full test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass (including `test_no_hardcoded_season.py`).

- [ ] **Step 8: Smoke-run the real pipeline step**

Run: `EUROLEAGUE_ROUND_SUFFIX=_R4 .venv/Scripts/python.exe simulate_monte_carlo.py`
Expected: prints `Loaded 20 teams, 40 played games, 340 unplayed games to simulate.`, then a table where no team shows Top 4 above ~90% (prototype gave PAN 85.7 / 93.4 / 98.8), and writes `monte_carlo_results_R4.json`. Check: `.venv/Scripts/python.exe -c "import json; d=json.load(open('monte_carlo_results_R4.json')); print(round(sum(x['Top4_Pct'] for x in d)), round(sum(x['Top6_Pct'] for x in d)), round(sum(x['Top10_Pct'] for x in d)), sorted(d[0].keys()))"` → `400 600 1000` (±1 for rounding) and the 9 schema keys.

- [ ] **Step 9: Commit**

```bash
git add simulate_monte_carlo.py tests/test_monte_carlo.py monte_carlo_results_R4.json
git commit -m "fix: calibrated season odds — Bayesian team strength in Monte Carlo

Early-season ratings were taken as true strength, home court was counted
three times and each game was drawn independently, so after 4 rounds the
top four showed 89-99% Top-4 odds. Strengths now come from a venue- and
opponent-adjusted Bayesian posterior (preseason Elo prior) and each
simulation draws one strength vector from it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Historical backtest that validates the production model

**Files:**
- Create: `backtest_monte_carlo.py` (repo root, alongside `backtest_matchup_calibration.py`; not a pipeline script)

**Interfaces:**
- Consumes: `simulate_season`, `ELO_PER_POINT` from `simulate_monte_carlo`; `_load_prior_season_elos`, `STARTING_ELO` from `calculate_elo`; `COMPLETED_SEASONS` from `season_config`; `data_cache/pbp_{season}.csv`, `data_cache/game_elos.json`.
- Produces: a printed report + exit code 0 when the acceptance criteria hold, 1 otherwise.

- [ ] **Step 1: Write the script**

```python
"""Backtest the season Monte Carlo (Top 4 / 6 / 10 odds) on completed seasons.

For each round-robin season with complete play-by-play, rebuild the table at
checkpoint rounds, simulate the rest with the production model, and score the
probabilities against the real final standings. Exit code 1 if the model is
miscalibrated. Run: .venv/Scripts/python.exe backtest_monte_carlo.py
"""
import json
import sys

import numpy as np
import pandas as pd

from calculate_elo import STARTING_ELO, _load_prior_season_elos
from season_config import COMPLETED_SEASONS
from simulate_monte_carlo import ELO_PER_POINT, simulate_season

FIRST_ROUND_ROBIN = 2016   # single-table regular season from 2016-17 on
CHECKPOINTS = (4, 8, 12, 20)
CUTOFFS = (4, 6, 10)
N_SIMS = 4000
BINS = [0, .02, .1, .3, .5, .7, .9, .98, 1.001]


def load_games(season, game_meta):
    """[(round, home, away, home_pts, away_pts)] for the regular season."""
    pbp = pd.read_csv(f'data_cache/pbp_{season}.csv', low_memory=False,
                      usecols=['Phase', 'Round', 'Gamecode', 'POINTS_A', 'POINTS_B'])
    pbp = pbp[pbp.Phase == 'RS']
    g = pbp.groupby('Gamecode').agg(rnd=('Round', 'first'), a=('POINTS_A', 'max'),
                                    b=('POINTS_B', 'max')).reset_index()
    games = []
    for _, r in g.iterrows():
        meta = game_meta.get(f'{season}_{int(r.Gamecode)}')
        if meta and r.a == r.a and r.b == r.b:
            games.append((int(r.rnd), meta['home'], meta['away'], int(r.a), int(r.b)))
    return games


def final_ranks(n, played):
    ranks, _ = simulate_season(n, played, [], np.zeros(n), 1, np.random.default_rng(0))
    return ranks[0]


def score(p, t):
    q = np.clip(p, 1e-3, 1 - 1e-3)
    return float(np.mean(-(t * np.log(q) + (1 - t) * np.log(1 - q))))


def main():
    game_meta = json.load(open('data_cache/game_elos.json'))
    P, T = [], []
    for season in COMPLETED_SEASONS:
        if season < FIRST_ROUND_ROBIN:
            continue
        games = load_games(season, game_meta)
        teams = sorted({t for _, h, a, _, _ in games for t in (h, a)})
        n = len(teams)
        if len(games) < 0.98 * n * (n - 1):   # cancelled / withdrawals / incomplete cache
            print(f'{season}: skipped ({len(games)} of {n * (n - 1)} games)')
            continue
        idx = {t: i for i, t in enumerate(teams)}
        allg = [(r, idx[h], idx[a], hp, ap) for r, h, a, hp, ap in games]
        truth = final_ranks(n, [(h, a, hp, ap) for _, h, a, hp, ap in allg])
        prior_elos = _load_prior_season_elos(season)
        prior = np.array([(prior_elos.get(t, STARTING_ELO) - STARTING_ELO) / ELO_PER_POINT
                          for t in teams])
        for R in CHECKPOINTS:
            played = [(h, a, hp, ap) for r, h, a, hp, ap in allg if r <= R]
            remaining = [(h, a) for r, h, a, _, _ in allg if r > R]
            ranks, _ = simulate_season(n, played, remaining, prior, N_SIMS,
                                       np.random.default_rng(season * 100 + R))
            for c in CUTOFFS:
                P.extend((ranks < c).mean(axis=0))
                T.extend((truth < c).astype(float))
        print(f'{season}: {n} teams, {len(games)} games done')

    P, T = np.array(P), np.array(T)
    ll = score(P, T)
    extreme = (P >= .95) | (P <= .05)
    wrong = ((P >= .95) & (T == 0)) | ((P <= .05) & (T == 1))
    print(f'\nPredictions: {len(P)}  log loss {ll:.4f}  '
          f'wrong at extremes {wrong.sum()}/{extreme.sum()}')
    ok = ll <= 0.385 and wrong.sum() <= 0.03 * max(extreme.sum(), 1)
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = (P >= lo) & (P < hi)
        if not m.sum():
            continue
        gap = abs(P[m].mean() - T[m].mean())
        flag = '' if (m.sum() < 50 or gap <= 0.05) else '  <-- miscalibrated'
        ok = ok and not flag
        print(f'  {lo:.2f}-{min(hi, 1):.2f}: predicted {P[m].mean():.3f}  '
              f'actual {T[m].mean():.3f}  (n={m.sum()}){flag}')
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 2: Run it**

Run: `.venv/Scripts/python.exe backtest_monte_carlo.py` (takes a few minutes; run with a 10-minute timeout)
Expected: seasons 2016, 2017, 2018, 2020, 2022, 2023, 2024 processed (2019, 2021, 2025 skipped), log loss ≤ 0.385 (prototype: 0.3775; old model: 0.3908), no bin flagged, `PASS`, exit 0.

- [ ] **Step 3: If it prints FAIL — bounded tuning, then stop**

Only if Step 2 fails: try the 6 combinations `TAU_STRENGTH ∈ {3.5, 4.5, 5.5}` × `HCA_PTS ∈ {3.0, 3.5}` by editing the constants in `simulate_monte_carlo.py`, re-running the backtest each time. Keep the combination with the lowest log loss that passes. If none passes, stop and report the full output for each combination to the controller — do not change the model structure.

- [ ] **Step 4: Commit**

```bash
git add backtest_monte_carlo.py simulate_monte_carlo.py
git commit -m "test: backtest season Monte Carlo calibration on 2016-2024

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Export — no playoff forecasts until the regular season is complete

**Files:**
- Modify: `export_dashboard_data.py` (new module-level helper near `load_with_fallback` at line ~58; gating in `main()` playoff block at lines ~3328–3345; output dict at ~3364)
- Create: `tests/test_playoff_gating.py`

**Interfaces:**
- Produces: `regular_season_complete(schedule_rows: list[dict] | None) -> bool`; dashboard key `regular_season_complete: bool` (consumed by Task 4).

- [ ] **Step 1: Write the failing test** — create `tests/test_playoff_gating.py`:

```python
"""Playoff forecasts are only exported once the regular season is complete."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import regular_season_complete


def _rows(played_flags, extra=()):
    rows = [{'round': 'RS', 'played': p} for p in played_flags]
    return rows + list(extra)


def test_incomplete_regular_season():
    assert not regular_season_complete(_rows(['true'] * 40 + ['false'] * 340))


def test_complete_regular_season():
    assert regular_season_complete(_rows(['true'] * 380))


def test_unplayed_playoff_rows_do_not_block():
    assert regular_season_complete(_rows(['true'] * 380, [{'round': 'PO', 'played': 'false'}]))


def test_missing_or_empty_schedule_is_not_complete():
    assert not regular_season_complete(None)
    assert not regular_season_complete([])


def test_played_flag_case_and_bool():
    assert regular_season_complete(_rows(['True', True, 'TRUE']))
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_playoff_gating.py -q`
Expected: FAIL — `ImportError: cannot import name 'regular_season_complete'`.

- [ ] **Step 3: Add the helper** — insert directly above `def load_with_fallback(` in `export_dashboard_data.py`:

```python
def regular_season_complete(schedule_rows):
    """True once every regular-season game in the schedule has been played.
    Playoff forecasts (championship odds, path to title, series) are only
    meaningful once the seeds are final."""
    rs = [r for r in (schedule_rows or []) if r.get('round') == 'RS']
    return bool(rs) and all(str(r.get('played', '')).lower() == 'true' for r in rs)


```

- [ ] **Step 4: Gate the pre-playoff branch in `main()`**

(a) Directly above the line `    game_results_raw = load_json('mvp_game_results.json')` (just before `if game_results_raw and len(teams) >= 10:`), add:

```python
    rs_complete = regular_season_complete(load_json(f'schedule_{S}.json'))
```

(b) In the `else:` branch commented `# Pre-playoff: compute baseline odds if not done yet`, directly after its `try: ... except Exception: pass` that loads `championship_odds_history` from the previous dashboard, add:

```python
            if not rs_complete:
                # Seeds aren't final: no championship odds, path to title or
                # series yet, and drop any stale mid-season "Pre-Playoff" baseline.
                championship_odds_history = []
                print("  Regular season in progress — playoff forecasts skipped "
                      "(bracket stays a what-if)")
```

(c) In the same branch change

```python
            if playoff_matchup_probs and len(teams) >= 10:
                seeded = teams[:10]
```

to

```python
            if rs_complete and playoff_matchup_probs and len(teams) >= 10:
                seeded = teams[:10]
```

`playoff_matchup_probs` itself stays unconditional — the what-if bracket needs it.

(d) In the `output = {` dict, after `'season_label': season_label(),` add:

```python
        'regular_season_complete': rs_complete,
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add export_dashboard_data.py tests/test_playoff_gating.py
git commit -m "fix: only export playoff forecasts once the regular season is complete

At round 4 the export seeded the current top 10 as final playoff seeds,
publishing championship odds, a 100% QF path for the leader and a frozen
'Pre-Playoff' baseline. Adds a regular_season_complete dashboard flag.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Playoff Simulator what-if mode + About page

**Files:**
- Modify: `docs/playoffs.html:905-934` (header subtitle id, what-if banner slot, MC chart heading/description ids)
- Modify: `docs/playoffs.js` (data load block ~lines 175–227)
- Modify: `docs/about.html:289` (Playoffs bullet) and `docs/about.html:433-444` (Monte Carlo Simulation entry)

**Interfaces:**
- Consumes: dashboard `regular_season_complete` (Task 3). Missing flag ⇒ treat as `true` (archived/older dashboards).

- [ ] **Step 1: HTML hooks** — in `docs/playoffs.html`:

Change
```html
        <p class="subtitle">Build your bracket — click a team to advance, click a winner to undo. Probabilities update in real-time.</p>
```
to
```html
        <p class="subtitle" id="playoffs-subtitle">Build your bracket — click a team to advance, click a winner to undo. Probabilities update in real-time.</p>
```

Insert, as the first child inside `<main>` (before `<div class="stat-card">` that holds the bracket):
```html
        <div id="whatif-banner" class="season-banner" style="display:none"></div>
```

Change
```html
            <h3>Championship Odds (10,000-run Monte Carlo)</h3>
            <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:1rem">
                Simulates the full playoff bracket 10,000 times using adjusted ratings, Elo, and ML win probability.
            </p>
```
to
```html
            <h3 id="mc-heading">Championship Odds (10,000-run Monte Carlo)</h3>
            <p id="mc-desc" style="font-size:0.78rem;color:var(--text-muted);margin-bottom:1rem">
                Simulates the full playoff bracket 10,000 times using adjusted ratings, Elo, and ML win probability.
            </p>
```

- [ ] **Step 2: Verify the hooks are unique**

Run: `grep -c 'id="whatif-banner"\|id="mc-heading"\|id="mc-desc"\|id="playoffs-subtitle"' docs/playoffs.html`
Expected: `4`.

- [ ] **Step 3: JS what-if mode** — in `docs/playoffs.js`, directly after the line `        if (_ph) _ph.textContent = \`${seasonLabel(_dashSeason)} Euroleague Playoffs\`;` add:

```javascript
        // Before the regular season ends the seeds are just today's table:
        // label everything as a what-if, not a forecast. Older dashboards
        // have no flag — treat them as complete.
        const whatIf = data.regular_season_complete === false && !_realResults;
        if (whatIf) {
            if (_ph) _ph.textContent = `${seasonLabel(_dashSeason)} Playoffs — If the Season Ended Today`;
            const sub = document.getElementById('playoffs-subtitle');
            if (sub) sub.textContent = 'What-if bracket seeded from the current standings. Click a team to advance, click a winner to undo.';
            const banner = document.getElementById('whatif-banner');
            if (banner) {
                banner.innerHTML = `Regular season in progress (Round ${data.round || '?'}). Seeds below are today's standings, ` +
                    `not a forecast — for projected finishes see the <a href="index.html">Top 4 / 6 / 10 odds on the Season Hub</a>. ` +
                    `Championship odds and Path to Title appear once the regular season ends.`;
                banner.style.display = '';
            }
            const mh = document.getElementById('mc-heading');
            if (mh) mh.textContent = 'What-If Championship Odds (if the season ended today)';
            const md = document.getElementById('mc-desc');
            if (md) md.textContent = 'Plays this what-if bracket 10,000 times from the current standings. Not a title forecast — the seeds will change.';
        }
```

No other JS changes: with the Task 3 export, `championship_odds` is `{}` (so `runMonteCarlo` falls back to the client-side simulation of the what-if bracket), `championship_odds_history` is `[]` (tracker stays hidden, it needs ≥2 entries) and `path_to_title` is `[]` (section stays hidden).

- [ ] **Step 4: About page** — in `docs/about.html`:

In the `Playoffs` bullet (line ~289), after `Share your bracket via URL.` append:
```html
 Until the regular season is complete the bracket is a labelled "if the season ended today" what-if seeded from the current standings; championship odds and Path to Title are published only once the seeds are final.
```

Replace the Monte Carlo Simulation paragraph text (lines ~436–444, from `Simulates the remainder of the season` to `power the interactive bracket simulator.`) with:
```html
                    Simulates the remainder of the season 10,000 times to generate probability distributions for final standings.
                    Each team's strength (points per game vs an average team) is estimated with a Bayesian model:
                    every game's margin is treated as home-court advantage (3 pts) plus the strength difference plus noise
                    (sd 12 pts), starting from a preseason prior based on last season's Elo. The fit adjusts for opponent and venue,
                    and early results are shrunk toward the prior — historically only about a third of a team's margin over its
                    first four games carries over to the rest of the season. Each simulation first draws a plausible strength for
                    every team, then plays out all remaining games, so uncertainty about how good a team really is flows into the odds.
                    Teams are ranked using official Euroleague tiebreaker rules: head-to-head record among tied teams,
                    then head-to-head point differential, then overall point differential.
                    Outputs playoff probabilities (Top 4, Top 6, Top 10), projected win totals,
                    and seed distributions for every team. Backtested on the 2016–2024 regular seasons for calibration
                    (when it says 80%, it happens about 80% of the time).
```

- [ ] **Step 5: Commit**

```bash
git add docs/playoffs.html docs/playoffs.js docs/about.html
git commit -m "feat: label the playoff bracket as a what-if until the regular season ends

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Regenerate current outputs and verify end-to-end

**Files:**
- Modify (generated): `monte_carlo_results_R4.json`, `docs/data/current/dashboard.json`, plus any `*_R4.*` the export/visualize scripts rewrite.

- [ ] **Step 1: Regenerate**

Run:
```bash
EUROLEAGUE_ROUND_SUFFIX=_R4 .venv/Scripts/python.exe simulate_monte_carlo.py
EUROLEAGUE_ROUND_SUFFIX=_R4 .venv/Scripts/python.exe export_dashboard_data.py
```
Expected: export prints `Regular season in progress — playoff forecasts skipped (bracket stays a what-if)`.

- [ ] **Step 2: Verify the dashboard data**

Run:
```bash
.venv/Scripts/python.exe -c "
import json
d=json.load(open('docs/data/current/dashboard.json',encoding='utf-8'))
T=d['teams']
print('rs_complete', d['regular_season_complete'])
print('champ', d['championship_odds'], 'hist', d['championship_odds_history'], 'ptt', d['path_to_title'], 'series', d['series'])
print('matchup teams', len(d['playoff_matchup_probs']))
print('sums', round(sum(t['top4_pct'] for t in T)), round(sum(t['top6_pct'] for t in T)), round(sum(t['top10_pct'] for t in T)))
print('max top4', max(t['top4_pct'] for t in T), 'min top10', min(t['top10_pct'] for t in T))
"
```
Expected: `rs_complete False`; `champ {} hist [] ptt [] series {}`; `matchup teams 10`; sums `400 600 1000` (±1); max top4 < 95; min top10 > 3.

- [ ] **Step 3: Verify in a browser**

Run `.venv/Scripts/python.exe -m http.server 8765 --directory docs` in the background, then open with Playwright:
- `http://localhost:8765/playoffs.html` — heading reads "2026-27 Playoffs — If the Season Ended Today", the banner is visible, the odds card reads "What-If Championship Odds", Path to Title and Championship Odds Tracker are not shown, the bracket is still clickable, no console errors.
- `http://localhost:8765/index.html` — standings table shows the new Top 4/6/10 odds, no console errors.
- `http://localhost:8765/series.html` and `title-race.html` — still show the 2025-26 archive with its banner.
- `http://localhost:8765/about.html` — new Monte Carlo text present.
Stop the server afterwards.

- [ ] **Step 4: Full test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add monte_carlo_results_R4.json docs/data/current/dashboard.json
git status --short   # add any other regenerated *_R4.* outputs shown as modified
git commit -m "chore: regenerate R4 odds and dashboard with calibrated model

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
