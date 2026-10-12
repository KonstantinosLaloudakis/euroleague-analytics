# Historical GCI Trends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute Game Control Index for all 18 completed Euroleague seasons (2007–2024), then display league-wide era trends and per-team style evolution on a new `gci-history.html` page that merges historical data with the live 2025 season.

**Architecture:** A new batch script (`calculate_gci_historical.py`) imports `compute_game_metrics()` from the existing `calculate_gci.py`, processes 4,656 historical games across 18 seasons, and writes `docs/gci_historical.json`. A new frontend page (`docs/gci-history.html` + `docs/gci-history.js`) loads this file alongside `dashboard.json` (for live 2025 data) and renders four sections: hero trend cards, team comparison tool, era breakdown, and all-time superlatives.

**Tech Stack:** Python 3 (json, os, statistics), Plotly.js (CDN), inline SVG sparklines, vanilla JS (no build step)

**Spec:** `docs/superpowers/specs/2026-04-14-historical-gci-trends-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `calculate_gci_historical.py` | Batch compute GCI for seasons 2007–2024, write `docs/gci_historical.json` |
| Create | `tests/test_gci_historical.py` | Tests for the historical compute script |
| Create | `docs/gci-history.html` | Page structure, inline CSS, loading/error states |
| Create | `docs/gci-history.js` | All frontend logic: data loading, merge, hero, comparison chart, eras, superlatives |
| Modify | `docs/about.html` | Add "Historical GCI Trends" subsection |
| Modify | All 12 `docs/*.html` files | Add "GCI History" nav link |

---

### Task 1: Extract importable core from `calculate_gci.py`

The historical script needs `compute_game_metrics()` from `calculate_gci.py`. Currently the module works fine for import — `compute_game_metrics` is a top-level function with no module-level side effects (the `main()` call is guarded by `if __name__ == '__main__'`). No changes to `calculate_gci.py` are needed.

**Files:**
- Create: `tests/test_gci_historical.py`

- [ ] **Step 1: Write a test that validates importing `compute_game_metrics` from `calculate_gci`**

```python
"""Tests for calculate_gci_historical.py"""
import pytest


def test_compute_game_metrics_import():
    """Verify we can import compute_game_metrics from the existing GCI module."""
    from calculate_gci import compute_game_metrics
    assert callable(compute_game_metrics)


def test_compute_game_metrics_basic():
    """Verify compute_game_metrics returns expected keys for a simple timeline."""
    from calculate_gci import compute_game_metrics

    # Minimal timeline: 5 plays, home team winning throughout
    timeline = [
        {'e': 0,   's': 2400, 'a': 2, 'b': 0, 'w': 0.55, 'p': 1, 'd': ''},
        {'e': 60,  's': 2340, 'a': 4, 'b': 2, 'w': 0.58, 'p': 1, 'd': ''},
        {'e': 120, 's': 2280, 'a': 6, 'b': 4, 'w': 0.56, 'p': 1, 'd': ''},
        {'e': 2300,'s': 100,  'a': 80,'b': 70,'w': 0.85, 'p': 4, 'd': ''},
        {'e': 2400,'s': 0,    'a': 82,'b': 72,'w': 1.0,  'p': 4, 'd': ''},
    ]
    result = compute_game_metrics(timeline, winner_is_home=True)
    assert result is not None
    expected_keys = {
        'dominance', 'control_home', 'control_away', 'drama',
        'comeback', 'crunch_home', 'crunch_away', 'killer_home', 'killer_away',
    }
    assert set(result.keys()) == expected_keys
    assert result['dominance'] > 0  # home dominated
    assert result['drama'] > 0


def test_compute_game_metrics_insufficient_data():
    """Verify compute_game_metrics returns None for too-short timelines."""
    from calculate_gci import compute_game_metrics
    assert compute_game_metrics([], True) is None
    assert compute_game_metrics([{'w': 0.5}], True) is None
    assert compute_game_metrics([{'w': 0.5}, {'w': 0.6}], True) is None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gci_historical.py -v`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_gci_historical.py
git commit -m "test: verify compute_game_metrics is importable from calculate_gci"
```

---

### Task 2: Build `calculate_gci_historical.py` — data loading and per-season GCI computation

**Files:**
- Create: `calculate_gci_historical.py`
- Modify: `tests/test_gci_historical.py`

- [ ] **Step 1: Write tests for historical data loading and per-season computation**

Add these tests to `tests/test_gci_historical.py`:

```python
import json
import os
import tempfile


def test_load_season_games_from_wp_files():
    """Verify we can derive game results from WP replay files."""
    from calculate_gci_historical import load_season_games

    # Create a temp directory with two fake WP replay files
    with tempfile.TemporaryDirectory() as tmpdir:
        game1 = {
            'ta': 'OLY', 'tb': 'BAR',
            'timeline': [
                {'e': 0, 's': 2400, 'a': 0, 'b': 0, 'w': 0.5, 'p': 1, 'd': ''},
                {'e': 60, 's': 2340, 'a': 2, 'b': 0, 'w': 0.55, 'p': 1, 'd': ''},
                {'e': 120, 's': 2280, 'a': 4, 'b': 2, 'w': 0.56, 'p': 1, 'd': ''},
                {'e': 2300, 's': 100, 'a': 80, 'b': 70, 'w': 0.9, 'p': 4, 'd': ''},
                {'e': 2400, 's': 0, 'a': 85, 'b': 72, 'w': 1.0, 'p': 4, 'd': ''},
            ]
        }
        game2 = {
            'ta': 'MAD', 'tb': 'TEL',
            'timeline': [
                {'e': 0, 's': 2400, 'a': 0, 'b': 0, 'w': 0.5, 'p': 1, 'd': ''},
                {'e': 60, 's': 2340, 'a': 0, 'b': 3, 'w': 0.42, 'p': 1, 'd': ''},
                {'e': 120, 's': 2280, 'a': 2, 'b': 5, 'w': 0.40, 'p': 1, 'd': ''},
                {'e': 2300, 's': 100, 'a': 68, 'b': 80, 'w': 0.05, 'p': 4, 'd': ''},
                {'e': 2400, 's': 0, 'a': 70, 'b': 82, 'w': 0.0, 'p': 4, 'd': ''},
            ]
        }
        with open(os.path.join(tmpdir, '1.json'), 'w') as f:
            json.dump(game1, f)
        with open(os.path.join(tmpdir, '2.json'), 'w') as f:
            json.dump(game2, f)

        games, timelines = load_season_games(tmpdir)

        assert len(games) == 2
        assert games['1']['home'] == 'OLY'
        assert games['1']['away'] == 'BAR'
        assert games['1']['home_score'] == 85
        assert games['1']['away_score'] == 72
        assert games['1']['winner'] == 'OLY'  # final WP=1.0 > 0.5
        assert games['2']['winner'] == 'TEL'  # final WP=0.0 < 0.5
        assert len(timelines) == 2


def test_compute_season_gci():
    """Verify per-season GCI computation produces expected structure."""
    from calculate_gci_historical import load_season_games, compute_season_gci

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create 4 games between 2 teams to get meaningful aggregates
        for i, (ta, tb, final_wp, ha, hb) in enumerate([
            ('AAA', 'BBB', 0.9, 80, 70),
            ('BBB', 'AAA', 0.3, 65, 75),
            ('AAA', 'BBB', 0.8, 78, 68),
            ('BBB', 'AAA', 0.4, 70, 72),
        ], start=1):
            game = {
                'ta': ta, 'tb': tb,
                'timeline': [
                    {'e': 0, 's': 2400, 'a': 0, 'b': 0, 'w': 0.5, 'p': 1, 'd': ''},
                    {'e': 60, 's': 2340, 'a': 2, 'b': 0, 'w': final_wp * 0.6, 'p': 1, 'd': ''},
                    {'e': 1200, 's': 1200, 'a': ha // 2, 'b': hb // 2, 'w': final_wp * 0.8, 'p': 2, 'd': ''},
                    {'e': 2300, 's': 100, 'a': ha - 2, 'b': hb - 2, 'w': final_wp * 0.95, 'p': 4, 'd': ''},
                    {'e': 2400, 's': 0, 'a': ha, 'b': hb, 'w': final_wp, 'p': 4, 'd': ''},
                ]
            }
            with open(os.path.join(tmpdir, f'{i}.json'), 'w') as f:
                json.dump(game, f)

        games, timelines = load_season_games(tmpdir)
        result = compute_season_gci(games, timelines)

        assert 'gci_ratings' in result
        assert 'team_profiles' in result
        assert 'game_metrics' in result
        assert 'AAA' in result['gci_ratings']
        assert 'BBB' in result['gci_ratings']
        # GCI ratings should be 0-100
        for team, gci in result['gci_ratings'].items():
            assert 0 <= gci <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gci_historical.py::test_load_season_games_from_wp_files tests/test_gci_historical.py::test_compute_season_gci -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'calculate_gci_historical'`

- [ ] **Step 3: Implement `calculate_gci_historical.py` — core functions**

```python
"""
Historical GCI Trends — Batch compute GCI for all completed Euroleague seasons.

Imports compute_game_metrics() from calculate_gci.py (no duplication).
Derives game results directly from WP replay files (no mvp_game_results.json needed).

Usage:
    python calculate_gci_historical.py
"""

import json
import os
import statistics

from calculate_gci import compute_game_metrics, aggregate_team_profiles, compute_gci_ratings


SEASONS = list(range(2007, 2025))  # 2007–2024 (completed seasons only)
WP_DATA_ROOT = os.path.join("docs", "data")
OUTPUT_PATH = os.path.join("docs", "gci_historical.json")


def load_season_games(season_dir):
    """
    Load all WP replay files from a season directory.
    Derives game results (teams, scores, winner) from the replay data itself.

    Returns:
        games: dict mapping gamecode -> {home, away, home_score, away_score, winner}
        timelines: dict mapping gamecode -> timeline list
    """
    games = {}
    timelines = {}

    for filename in os.listdir(season_dir):
        if not filename.endswith('.json'):
            continue
        gamecode = filename.replace('.json', '')
        filepath = os.path.join(season_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        if not isinstance(data, dict):
            continue

        timeline = data.get('timeline', [])
        ta = data.get('ta')
        tb = data.get('tb')

        if not timeline or not ta or not tb or len(timeline) < 3:
            continue

        last = timeline[-1]
        final_wp = last.get('w', 0.5)
        home_score = last.get('a', 0)
        away_score = last.get('b', 0)

        # Determine winner from final WP
        if final_wp > 0.5:
            winner = ta  # home won
        elif final_wp < 0.5:
            winner = tb  # away won
        else:
            # Tie in WP (extremely rare) — use score
            if home_score > away_score:
                winner = ta
            elif away_score > home_score:
                winner = tb
            else:
                continue  # skip truly ambiguous games

        games[gamecode] = {
            'home': ta,
            'away': tb,
            'home_score': int(home_score),
            'away_score': int(away_score),
            'winner': winner,
        }
        timelines[gamecode] = timeline

    return games, timelines


def compute_season_gci(games, timelines):
    """
    Compute full GCI for one season given pre-loaded games and timelines.

    Returns dict with keys: gci_ratings, components, team_profiles, game_metrics
    """
    game_metrics = {}
    for gc, game in games.items():
        timeline = timelines.get(gc)
        if not timeline:
            continue
        winner_is_home = (game['winner'] == game['home'])
        metrics = compute_game_metrics(timeline, winner_is_home)
        if metrics:
            game_metrics[gc] = metrics

    team_profiles = aggregate_team_profiles(games, game_metrics)
    gci_ratings, components, (mu, sigma) = compute_gci_ratings(team_profiles)

    return {
        'gci_ratings': gci_ratings,
        'components': components,
        'team_profiles': team_profiles,
        'game_metrics': game_metrics,
        'games': games,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gci_historical.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add calculate_gci_historical.py tests/test_gci_historical.py
git commit -m "feat: add calculate_gci_historical.py with data loading and per-season GCI"
```

---

### Task 3: Add cross-season aggregation and JSON output

**Files:**
- Modify: `calculate_gci_historical.py`
- Modify: `tests/test_gci_historical.py`

- [ ] **Step 1: Write tests for league trends, era breakdown, superlatives, and team trends**

Add to `tests/test_gci_historical.py`:

```python
def test_compute_league_trends():
    """Verify league-wide trend aggregation across seasons."""
    from calculate_gci_historical import compute_league_trends

    # Simulate 2 seasons of results
    season_results = {
        2007: {
            'gci_ratings': {'AAA': 70.0, 'BBB': 30.0},
            'components': {
                'AAA': {'dominance_avg': 0.15, 'control_pct': 0.6, 'crunch_swing_avg': 0.1, 'killer_instinct': 0.2},
                'BBB': {'dominance_avg': -0.05, 'control_pct': 0.3, 'crunch_swing_avg': -0.05, 'killer_instinct': -0.1},
            },
            'team_profiles': {
                'AAA': {'games': [{'drama': 2.5, 'comeback': 0.3, 'dominance': 0.15, 'control': 0.6, 'crunch': 0.1, 'killer': 0.2, 'is_win': True, 'is_home': True, 'gamecode': '1', 'opponent': 'BBB', 'home_score': 80, 'away_score': 70}],
                         'wins': [{'drama': 2.5, 'comeback': 0.3, 'dominance': 0.15, 'control': 0.6, 'crunch': 0.1, 'killer': 0.2, 'is_win': True, 'is_home': True, 'gamecode': '1', 'opponent': 'BBB', 'home_score': 80, 'away_score': 70}],
                         'losses': [], 'home_games': [], 'away_games': []},
                'BBB': {'games': [{'drama': 2.5, 'comeback': 0.0, 'dominance': -0.15, 'control': 0.3, 'crunch': -0.1, 'killer': -0.2, 'is_win': False, 'is_home': False, 'gamecode': '1', 'opponent': 'AAA', 'home_score': 80, 'away_score': 70}],
                         'wins': [], 'losses': [{'drama': 2.5}], 'home_games': [], 'away_games': []},
            },
            'game_metrics': {'1': {'drama': 2.5, 'dominance': 0.15, 'comeback': 0.3}},
            'games': {'1': {'home': 'AAA', 'away': 'BBB', 'home_score': 80, 'away_score': 70, 'winner': 'AAA'}},
        },
        2008: {
            'gci_ratings': {'AAA': 65.0, 'CCC': 35.0},
            'components': {
                'AAA': {'dominance_avg': 0.10, 'control_pct': 0.5, 'crunch_swing_avg': 0.08, 'killer_instinct': 0.15},
                'CCC': {'dominance_avg': -0.08, 'control_pct': 0.35, 'crunch_swing_avg': -0.03, 'killer_instinct': -0.05},
            },
            'team_profiles': {
                'AAA': {'games': [{'drama': 3.0, 'comeback': 0.85, 'dominance': 0.10, 'control': 0.5, 'crunch': 0.08, 'killer': 0.15, 'is_win': True, 'is_home': True, 'gamecode': '1', 'opponent': 'CCC', 'home_score': 75, 'away_score': 70}],
                         'wins': [{'drama': 3.0, 'comeback': 0.85, 'dominance': 0.10, 'control': 0.5, 'crunch': 0.08, 'killer': 0.15, 'is_win': True, 'is_home': True, 'gamecode': '1', 'opponent': 'CCC', 'home_score': 75, 'away_score': 70}],
                         'losses': [], 'home_games': [], 'away_games': []},
                'CCC': {'games': [{'drama': 3.0, 'comeback': 0.0, 'dominance': -0.10, 'control': 0.35, 'crunch': -0.08, 'killer': -0.15, 'is_win': False, 'is_home': False, 'gamecode': '1', 'opponent': 'AAA', 'home_score': 75, 'away_score': 70}],
                         'wins': [], 'losses': [{'drama': 3.0}], 'home_games': [], 'away_games': []},
            },
            'game_metrics': {'1': {'drama': 3.0, 'dominance': 0.10, 'comeback': 0.85}},
            'games': {'1': {'home': 'AAA', 'away': 'CCC', 'home_score': 75, 'away_score': 70, 'winner': 'AAA'}},
        },
    }

    trends = compute_league_trends(season_results)

    assert trends['seasons'] == [2007, 2008]
    assert len(trends['avg_drama']) == 2
    assert len(trends['comeback_count']) == 2
    assert len(trends['avg_gci_spread']) == 2
    assert trends['game_count'] == [1, 1]
    # 2008 has one comeback (0.85 > 0.80 threshold)
    assert trends['comeback_count'][1] == 1


def test_compute_team_trends():
    """Verify per-team trend arrays across seasons."""
    from calculate_gci_historical import compute_team_trends

    season_results = {
        2007: {
            'gci_ratings': {'AAA': 70.0, 'BBB': 30.0},
            'team_profiles': {
                'AAA': {'games': [{'drama': 2.5, 'dominance': 0.15, 'killer': 0.2, 'comeback': 0.3, 'is_win': True, 'is_home': True, 'gamecode': '1', 'opponent': 'BBB', 'home_score': 80, 'away_score': 70, 'control': 0.6, 'crunch': 0.1}],
                         'wins': [{'comeback': 0.3}], 'losses': [], 'home_games': [], 'away_games': []},
                'BBB': {'games': [{'drama': 2.5, 'dominance': -0.15, 'killer': -0.2, 'comeback': 0.0, 'is_win': False, 'is_home': False, 'gamecode': '1', 'opponent': 'AAA', 'home_score': 80, 'away_score': 70, 'control': 0.3, 'crunch': -0.1}],
                         'wins': [], 'losses': [], 'home_games': [], 'away_games': []},
            },
        },
        2008: {
            'gci_ratings': {'AAA': 65.0},
            'team_profiles': {
                'AAA': {'games': [{'drama': 3.0, 'dominance': 0.10, 'killer': 0.15, 'comeback': 0.85, 'is_win': True, 'is_home': True, 'gamecode': '1', 'opponent': 'CCC', 'home_score': 75, 'away_score': 70, 'control': 0.5, 'crunch': 0.08}],
                         'wins': [{'comeback': 0.85}], 'losses': [], 'home_games': [], 'away_games': []},
            },
        },
    }

    team_trends = compute_team_trends(season_results, min_seasons=1)

    assert 'AAA' in team_trends  # 2 seasons
    assert 'BBB' in team_trends  # 1 season (min_seasons=1 for test)
    assert team_trends['AAA']['seasons'] == [2007, 2008]
    assert team_trends['AAA']['gci'] == [70.0, 65.0]
    assert len(team_trends['AAA']['drama_avg']) == 2
    assert team_trends['AAA']['total_seasons'] == 2


def test_find_historical_superlatives():
    """Verify all-time superlative detection."""
    from calculate_gci_historical import find_historical_superlatives

    season_results = {
        2007: {
            'gci_ratings': {'AAA': 70.0, 'BBB': 30.0},
            'game_metrics': {
                '1': {'dominance': 0.35, 'drama': 5.5, 'comeback': 0.90,
                       'control_home': 0.7, 'control_away': 0.2,
                       'crunch_home': 0.1, 'crunch_away': -0.1,
                       'killer_home': 0.2, 'killer_away': -0.1},
            },
            'games': {
                '1': {'home': 'AAA', 'away': 'BBB', 'home_score': 95, 'away_score': 68, 'winner': 'AAA'},
            },
        },
        2008: {
            'gci_ratings': {'AAA': 95.0},
            'game_metrics': {
                '1': {'dominance': 0.20, 'drama': 3.0, 'comeback': 0.50,
                       'control_home': 0.5, 'control_away': 0.3,
                       'crunch_home': 0.05, 'crunch_away': -0.05,
                       'killer_home': 0.1, 'killer_away': -0.05},
            },
            'games': {
                '1': {'home': 'AAA', 'away': 'CCC', 'home_score': 80, 'away_score': 75, 'winner': 'AAA'},
            },
        },
    }

    superlatives = find_historical_superlatives(season_results)

    assert superlatives['most_dominant_season']['team'] == 'AAA'
    assert superlatives['most_dominant_season']['season'] == 2008
    assert superlatives['most_dominant_season']['gci'] == 95.0

    assert superlatives['most_dramatic_game']['season'] == 2007
    assert superlatives['most_dramatic_game']['drama'] == 5.5

    assert superlatives['most_dominant_game']['season'] == 2007
    assert abs(superlatives['most_dominant_game']['dominance']) == 0.35

    assert superlatives['biggest_comeback']['season'] == 2007
    assert superlatives['biggest_comeback']['comeback'] == 0.90
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gci_historical.py::test_compute_league_trends tests/test_gci_historical.py::test_compute_team_trends tests/test_gci_historical.py::test_find_historical_superlatives -v`
Expected: FAIL with `ImportError: cannot import name 'compute_league_trends'`

- [ ] **Step 3: Implement aggregation functions**

Add these functions to `calculate_gci_historical.py`:

```python
# Era definitions
ERAS = [
    {'name': 'Expansion Era', 'years': '2007–2015', 'seasons': list(range(2007, 2016))},
    {'name': 'Contraction Era', 'years': '2016–2019', 'seasons': list(range(2016, 2020))},
    {'name': 'Modern Era', 'years': '2020–2025', 'seasons': list(range(2020, 2025))},
]


def compute_league_trends(season_results):
    """
    Compute league-wide aggregates per season.

    Returns dict with parallel arrays keyed by season:
        seasons, avg_drama, comeback_count, avg_gci_spread, game_count
    """
    seasons = sorted(season_results.keys())
    avg_drama = []
    comeback_count = []
    avg_gci_spread = []
    game_count = []

    for season in seasons:
        sr = season_results[season]
        profiles = sr['team_profiles']

        # Average drama across all games in the season
        all_dramas = []
        all_comebacks = 0
        for team, profile in profiles.items():
            for g in profile['games']:
                all_dramas.append(g['drama'])
            for g in profile.get('wins', []):
                if g.get('comeback', 0) > 0.80:
                    all_comebacks += 1

        # Each game is counted twice (once per team), so divide drama list / 2 is fine
        # because mean doesn't change. Comebacks need halving since each game counted from both sides.
        avg_d = statistics.mean(all_dramas) if all_dramas else 0
        avg_drama.append(round(avg_d, 3))
        comeback_count.append(all_comebacks)  # only winners have comeback > 0

        # GCI spread: max - min
        ratings = sr['gci_ratings']
        if len(ratings) >= 2:
            spread = max(ratings.values()) - min(ratings.values())
        else:
            spread = 0
        avg_gci_spread.append(round(spread, 1))

        game_count.append(len(sr.get('game_metrics', {})))

    return {
        'seasons': seasons,
        'avg_drama': avg_drama,
        'comeback_count': comeback_count,
        'avg_gci_spread': avg_gci_spread,
        'game_count': game_count,
    }


def compute_team_trends(season_results, min_seasons=3):
    """
    Build per-team trend arrays across seasons.

    Only includes teams with >= min_seasons of data.
    """
    # Collect all teams and their per-season data
    team_data = {}
    for season in sorted(season_results.keys()):
        sr = season_results[season]
        ratings = sr['gci_ratings']
        profiles = sr['team_profiles']

        for team in ratings:
            if team not in team_data:
                team_data[team] = {
                    'seasons': [],
                    'gci': [],
                    'drama_avg': [],
                    'dominance_avg': [],
                    'killer_instinct': [],
                    'comeback_count': [],
                }
            games = profiles.get(team, {}).get('games', [])
            wins = profiles.get(team, {}).get('wins', [])
            team_data[team]['seasons'].append(season)
            team_data[team]['gci'].append(ratings[team])
            team_data[team]['drama_avg'].append(
                round(statistics.mean(g['drama'] for g in games), 3) if games else 0
            )
            team_data[team]['dominance_avg'].append(
                round(statistics.mean(g['dominance'] for g in games), 4) if games else 0
            )
            team_data[team]['killer_instinct'].append(
                round(statistics.mean(g['killer'] for g in games), 4) if games else 0
            )
            team_data[team]['comeback_count'].append(
                sum(1 for g in wins if g.get('comeback', 0) > 0.80)
            )

    # Filter to teams with enough seasons
    return {
        team: {**data, 'total_seasons': len(data['seasons'])}
        for team, data in team_data.items()
        if len(data['seasons']) >= min_seasons
    }


def compute_era_breakdowns(season_results):
    """Compute era-level aggregates."""
    eras_output = []
    for era in ERAS:
        era_seasons = [s for s in era['seasons'] if s in season_results]
        if not era_seasons:
            continue

        all_dramas = []
        total_comebacks = 0
        total_games = 0
        team_gci_sums = {}
        team_gci_counts = {}
        team_set = set()

        for season in era_seasons:
            sr = season_results[season]
            for team, profile in sr['team_profiles'].items():
                team_set.add(team)
                for g in profile['games']:
                    all_dramas.append(g['drama'])
                for g in profile.get('wins', []):
                    if g.get('comeback', 0) > 0.80:
                        total_comebacks += 1
            for team, gci in sr['gci_ratings'].items():
                team_gci_sums[team] = team_gci_sums.get(team, 0) + gci
                team_gci_counts[team] = team_gci_counts.get(team, 0) + 1
            total_games += len(sr.get('game_metrics', {}))

        # Standout team: highest average GCI across the era
        team_avg_gci = {
            t: team_gci_sums[t] / team_gci_counts[t]
            for t in team_gci_sums
        }
        standout = max(team_avg_gci, key=team_avg_gci.get) if team_avg_gci else None

        avg_drama = statistics.mean(all_dramas) if all_dramas else 0
        gci_values = list(team_avg_gci.values())
        gci_spread = max(gci_values) - min(gci_values) if len(gci_values) >= 2 else 0

        eras_output.append({
            'name': era['name'],
            'years': era['years'],
            'seasons': era_seasons,
            'team_count': len(team_set),
            'total_games': total_games,
            'avg_drama': round(avg_drama, 3),
            'avg_gci_spread': round(gci_spread, 1),
            'total_comebacks': total_comebacks,
            'standout_team': standout,
            'standout_reason': f"Highest average GCI across the era ({team_avg_gci.get(standout, 0):.1f})" if standout else "",
        })

    return eras_output


def find_historical_superlatives(season_results):
    """Find all-time records across all seasons."""
    most_dominant_season = None
    most_dramatic_game = None
    most_dominant_game = None
    biggest_comeback = None

    for season, sr in season_results.items():
        # Most dominant season: highest single-season GCI
        for team, gci in sr['gci_ratings'].items():
            if most_dominant_season is None or gci > most_dominant_season['gci']:
                most_dominant_season = {'team': team, 'season': season, 'gci': gci}

        # Game-level superlatives
        for gc, metrics in sr.get('game_metrics', {}).items():
            game = sr['games'][gc]
            entry = {
                'gamecode': gc,
                'season': season,
                'home': game['home'],
                'away': game['away'],
                'home_score': game['home_score'],
                'away_score': game['away_score'],
            }

            # Most dramatic game
            if most_dramatic_game is None or metrics['drama'] > most_dramatic_game['drama']:
                most_dramatic_game = {**entry, 'drama': metrics['drama']}

            # Most dominant game
            abs_dom = abs(metrics['dominance'])
            if most_dominant_game is None or abs_dom > abs(most_dominant_game['dominance']):
                most_dominant_game = {**entry, 'dominance': metrics['dominance']}

            # Biggest comeback (only for wins with meaningful comeback)
            if metrics.get('comeback', 0) > 0.5:
                if biggest_comeback is None or metrics['comeback'] > biggest_comeback['comeback']:
                    biggest_comeback = {**entry, 'comeback': metrics['comeback'], 'winner': game['winner']}

    return {
        'most_dominant_season': most_dominant_season,
        'most_dramatic_game': most_dramatic_game,
        'most_dominant_game': most_dominant_game,
        'biggest_comeback': biggest_comeback,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gci_historical.py -v`
Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add calculate_gci_historical.py tests/test_gci_historical.py
git commit -m "feat: add cross-season aggregation — league trends, team trends, eras, superlatives"
```

---

### Task 4: Add `main()` function and run the batch computation

**Files:**
- Modify: `calculate_gci_historical.py`

- [ ] **Step 1: Add the main function that orchestrates the full batch**

Add to the bottom of `calculate_gci_historical.py`:

```python
def build_season_leaderboards(season_results):
    """Build per-season GCI leaderboards for optional drill-down."""
    leaderboards = {}
    for season in sorted(season_results.keys()):
        sr = season_results[season]
        ratings = sr['gci_ratings']
        components = sr.get('components', {})
        profiles = sr.get('team_profiles', {})

        entries = []
        for team in sorted(ratings, key=ratings.get, reverse=True):
            games = profiles.get(team, {}).get('games', [])
            entries.append({
                'team': team,
                'gci': ratings[team],
                'dominance_avg': round(components.get(team, {}).get('dominance_avg', 0), 4),
                'drama_avg': round(statistics.mean(g['drama'] for g in games), 3) if games else 0,
            })
        leaderboards[str(season)] = entries

    return leaderboards


def main():
    print("\n=== Computing Historical GCI Trends ===")
    print(f"  Seasons: {SEASONS[0]}–{SEASONS[-1]} ({len(SEASONS)} seasons)")

    season_results = {}
    total_games = 0

    for season in SEASONS:
        season_dir = os.path.join(WP_DATA_ROOT, str(season))
        if not os.path.exists(season_dir):
            print(f"  {season}: directory not found, skipping")
            continue

        games, timelines = load_season_games(season_dir)
        if not games:
            print(f"  {season}: no valid games, skipping")
            continue

        result = compute_season_gci(games, timelines)
        season_results[season] = result
        n_games = len(result['game_metrics'])
        n_teams = len(result['gci_ratings'])
        total_games += n_games
        print(f"  {season}: {n_games} games, {n_teams} teams")

    print(f"\n  Total: {total_games} games across {len(season_results)} seasons")

    # Cross-season aggregation
    print("  Computing league trends...")
    league_trends = compute_league_trends(season_results)

    print("  Computing team trends...")
    team_trends = compute_team_trends(season_results, min_seasons=3)
    print(f"  {len(team_trends)} teams with 3+ seasons")

    print("  Computing era breakdowns...")
    eras = compute_era_breakdowns(season_results)

    print("  Finding historical superlatives...")
    superlatives = find_historical_superlatives(season_results)

    print("  Building season leaderboards...")
    leaderboards = build_season_leaderboards(season_results)

    # Build output
    output = {
        'generated': '2026-04-14',
        'seasons_computed': sorted(season_results.keys()),
        'total_games': total_games,
        'league_trends': league_trends,
        'eras': eras,
        'team_trends': team_trends,
        'season_leaderboards': leaderboards,
        'superlatives': superlatives,
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Output: {OUTPUT_PATH}")
    print(f"  File size: {os.path.getsize(OUTPUT_PATH) / 1024:.0f} KB")
    print("\n=== Historical GCI computation complete ===")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run the batch script**

Run: `.venv/Scripts/python.exe calculate_gci_historical.py`
Expected: Processes 18 seasons, ~4,656 games, outputs `docs/gci_historical.json`. Should take 15–60 seconds.

- [ ] **Step 3: Verify the output file is valid**

Run: `.venv/Scripts/python.exe -c "import json; d=json.load(open('docs/gci_historical.json','r',encoding='utf-8')); print('Seasons:', len(d['seasons_computed'])); print('Total games:', d['total_games']); print('Team trends:', len(d['team_trends'])); print('Eras:', len(d['eras'])); print('Superlatives:', list(d['superlatives'].keys()))"`
Expected: Seasons: 18, Total games: ~4656, Team trends: ~25+, Eras: 3, Superlatives: 4 keys

- [ ] **Step 4: Commit**

```bash
git add calculate_gci_historical.py docs/gci_historical.json
git commit -m "feat: add main() to historical GCI script and generate initial data"
```

---

### Task 5: Create `gci-history.html` page structure

**Files:**
- Create: `docs/gci-history.html`

- [ ] **Step 1: Create the full HTML page**

```html
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#0f1117">
    <title>GCI History — Euroleague Analytics</title>
    <meta name="description"
        content="19 seasons of Game Control Index trends. How Euroleague basketball has evolved from 2007 to 2025.">
    <meta property="og:title" content="GCI History — Euroleague Analytics">
    <meta property="og:description"
        content="19 seasons of Game Control Index trends across 5,000+ Euroleague games.">
    <meta property="og:image" content="og-image.png">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Outfit:wght@700;800&display=swap"
        rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <link rel="stylesheet" href="style.css">
    <style>
        /* Hero metric cards */
        .hero-metrics { display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:0.5rem; }
        @media(max-width:768px){.hero-metrics{grid-template-columns:1fr;}}
        .hero-card { background:var(--bg-secondary);border-radius:var(--radius);padding:1.2rem;text-align:center;border:1px solid var(--border); }
        .hero-label { font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--text-muted);margin-bottom:0.3rem; }
        .hero-number { font-family:'Outfit',sans-serif;font-size:2.8rem;font-weight:800;line-height:1.1; }
        .hero-sub { font-size:0.78rem;color:var(--text-secondary);margin-top:0.2rem; }
        .hero-sparkline { margin-top:0.6rem; }
        .hero-summary { text-align:center;font-size:0.85rem;color:var(--text-secondary);margin-top:0.5rem; }
        .hero-count { text-align:center;font-size:0.72rem;color:var(--text-muted);margin-top:0.2rem;letter-spacing:1px; }

        /* Team comparison */
        .team-pills { display:flex;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.75rem; }
        .team-pill { padding:0.3rem 0.7rem;border-radius:20px;font-size:0.72rem;font-weight:600;cursor:pointer;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-secondary);transition:var(--transition);user-select:none; }
        .team-pill:hover { border-color:#4b5563; }
        .team-pill.active { border-color:var(--accent-teal);background:rgba(78,205,196,0.1);color:var(--text-primary); }
        .team-pill.active .pill-dot { opacity:1; }
        .pill-dot { display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle;opacity:0.4; }
        .comparison-controls { display:flex;align-items:center;gap:1rem;margin-bottom:0.75rem;flex-wrap:wrap; }
        .metric-select { background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:0.35rem 0.7rem;font-size:0.78rem;font-family:'Inter',sans-serif; }
        .show-more-btn { font-size:0.72rem;color:var(--accent-teal);cursor:pointer;background:none;border:none;padding:0.3rem 0.5rem;font-family:'Inter',sans-serif; }
        .show-more-btn:hover { text-decoration:underline; }
        #comparison-chart { width:100%;height:400px; }

        /* Era cards */
        .era-grid { display:grid;grid-template-columns:repeat(3,1fr);gap:0.75rem; }
        @media(max-width:768px){.era-grid{grid-template-columns:1fr;}}
        .era-card { background:var(--bg-secondary);border-radius:var(--radius);padding:1rem;border:1px solid var(--border);border-top:3px solid var(--border); }
        .era-name { font-family:'Outfit',sans-serif;font-size:1rem;font-weight:700;color:var(--text-primary); }
        .era-years { font-size:0.72rem;color:var(--text-muted);margin-bottom:0.6rem; }
        .era-stats { display:flex;flex-direction:column;gap:0.35rem; }
        .era-stat { display:flex;justify-content:space-between;font-size:0.78rem; }
        .era-stat-label { color:var(--text-secondary); }
        .era-stat-value { color:var(--text-primary);font-weight:600; }
        .era-standout { margin-top:0.6rem;padding-top:0.5rem;border-top:1px solid var(--border);font-size:0.72rem;color:var(--text-secondary); }
        .era-standout strong { color:var(--accent-teal); }

        /* Superlatives */
        .superlative-grid { display:grid;grid-template-columns:repeat(2,1fr);gap:0.75rem; }
        @media(max-width:768px){.superlative-grid{grid-template-columns:1fr;}}
        .superlative-card { background:var(--bg-secondary);border-radius:var(--radius);padding:1rem;text-align:center;border:1px solid var(--border); }
        .superlative-icon { font-size:1.5rem;margin-bottom:0.3rem; }
        .superlative-label { font-size:0.6rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px; }
        .superlative-matchup { font-family:'Outfit',sans-serif;font-size:0.95rem;font-weight:700;color:var(--text-primary);margin:0.3rem 0; }
        .superlative-season { font-size:0.72rem;color:var(--text-muted); }

        /* Section labels (reuse from game-control) */
        .section-label { font-size:0.68rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:0.3rem; }
        .section-title { font-family:'Outfit',sans-serif;font-size:1.15rem;font-weight:700;color:var(--text-primary);margin-bottom:0.8rem; }
    </style>
</head>

<body>

    <nav class="site-nav">
        <span class="site-nav-brand">🏀 Euroleague Analytics</span>
        <a href="index.html" class="nav-link">Season Hub</a>
        <a href="team.html" class="nav-link">Team Deep-Dive</a>
        <a href="players.html" class="nav-link">Player Stats</a>
        <a href="h2h.html" class="nav-link">Head-to-Head</a>
        <a href="recap.html" class="nav-link">Game Recap</a>
        <a href="shots.html" class="nav-link">Shot Lab</a>
        <a href="network.html" class="nav-link">Playmaking</a>
        <a href="replay.html" class="nav-link">Game Replay</a>
        <a href="playoffs.html" class="nav-link">Playoffs</a>
        <a href="mvp.html" class="nav-link">MVP Race</a>
        <a href="game-control.html" class="nav-link">Game Control</a>
        <a href="gci-history.html" class="nav-link active">GCI History</a>
        <a href="about.html" class="nav-link">About</a>
    </nav>

    <header>
        <h1>GCI History</h1>
        <p class="subtitle">19 seasons of Game Control — how Euroleague basketball has evolved</p>
    </header>

    <main>
        <!-- Loading -->
        <div id="loading" class="stat-card" style="text-align:center;padding:3rem 1rem;">
            <span class="loading-spinner"></span> Loading historical GCI data...
        </div>

        <!-- Error -->
        <div id="load-error" class="hidden" style="text-align:center;padding:3rem 1rem;">
            <div style="font-size:3rem;margin-bottom:1rem;">&#9888;&#65039;</div>
            <p style="color:var(--text-muted);font-size:1rem;">
                Could not load historical GCI data. Run
                <code>python calculate_gci_historical.py</code> to generate it.
            </p>
        </div>

        <!-- Content -->
        <div id="content" class="hidden">

            <!-- Section 1: Hero -->
            <div class="stat-card">
                <div id="hero-metrics" class="hero-metrics"></div>
                <div id="hero-summary" class="hero-summary"></div>
                <div id="hero-count" class="hero-count"></div>
            </div>

            <!-- Section 2: Team Comparison -->
            <div class="stat-card">
                <p class="section-label">Compare across 19 seasons</p>
                <h3 class="section-title">Team Comparison</h3>
                <div class="comparison-controls">
                    <select id="metric-select" class="metric-select">
                        <option value="gci">GCI Rating</option>
                        <option value="drama_avg">Drama Index</option>
                        <option value="dominance_avg">Dominance Score</option>
                        <option value="killer_instinct">Killer Instinct</option>
                        <option value="comeback_count">Comebacks</option>
                    </select>
                    <button id="show-more-btn" class="show-more-btn">Show more teams</button>
                </div>
                <div id="team-pills" class="team-pills"></div>
                <div id="comparison-chart"></div>
            </div>

            <!-- Section 3: Era Breakdown -->
            <div class="stat-card">
                <p class="section-label">Three distinct eras</p>
                <h3 class="section-title">Era Breakdown</h3>
                <div id="era-cards" class="era-grid"></div>
            </div>

            <!-- Section 4: Historical Superlatives -->
            <div class="stat-card">
                <p class="section-label">All-time records</p>
                <h3 class="section-title">Historical Superlatives</h3>
                <div id="superlatives" class="superlative-grid"></div>
            </div>

        </div>
    </main>

    <footer class="site-footer">
        <div class="footer-links">
            <a href="about.html">About & Methodology</a>
            <span class="footer-sep">·</span>
            <a href="https://github.com/giasemidis/euroleague_api" target="_blank" rel="noopener">Data: Euroleague API</a>
            <span class="footer-sep">·</span>
            <a href="https://github.com/KonstantinosLaloudakis" target="_blank" rel="noopener">GitHub</a>
        </div>
        <div>19 seasons · 5,000+ games · Updated daily</div>
    </footer>

    <script src="constants.js"></script>
    <script src="gci-history.js"></script>
</body>

</html>
```

- [ ] **Step 2: Verify the file loads without errors**

Open `docs/gci-history.html` in a browser (via local server or directly). Should show the loading spinner — no JS errors in console since `gci-history.js` doesn't exist yet.

- [ ] **Step 3: Commit**

```bash
git add docs/gci-history.html
git commit -m "feat: add gci-history.html page structure with all 4 sections"
```

---

### Task 6: Build `gci-history.js` — data loading, merge, and hero section

**Files:**
- Create: `docs/gci-history.js`

- [ ] **Step 1: Implement data loading, 2025 merge, and hero rendering**

```javascript
/**
 * gci-history.js — Historical GCI Trends page
 * Hero trends, team comparison, era breakdown, all-time superlatives
 */
'use strict';

/* ── State ─────────────────────────────────────────────────────────────── */
let _hist = null;       // gci_historical.json data
let _dashboard = null;  // dashboard.json data
let _merged = null;     // merged historical + live 2025
let _activeTeams = new Set();
let _showAll = false;

/* Legacy teams: present all 19 seasons */
const LEGACY_TEAMS = ['OLY', 'BAR', 'MAD', 'PAN', 'TEL', 'IST', 'ULK', 'BAS', 'MIL', 'ZAL'];

/* ── Boot ──────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const [histResp, dashResp] = await Promise.all([
            fetchJSON('gci_historical.json'),
            fetchJSON('data/current/dashboard.json'),
        ]);
        _hist = histResp;
        _dashboard = dashResp;
        _merged = mergeWithLive(_hist, _dashboard);

        document.getElementById('loading').classList.add('hidden');
        document.getElementById('content').classList.remove('hidden');

        renderHero();
        renderTeamPills();
        renderComparisonChart();
        renderEras();
        renderSuperlatives();
    } catch (err) {
        console.error('Failed to load GCI history data:', err);
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('load-error').classList.remove('hidden');
    }
});

/* ── Merge historical + live 2025 ──────────────────────────────────────── */
function mergeWithLive(hist, dashboard) {
    const gc = dashboard.game_control;
    if (!gc) return hist;

    const merged = JSON.parse(JSON.stringify(hist));
    const liveSeason = 2025;

    // Add 2025 to league trends
    if (merged.league_trends && !merged.league_trends.seasons.includes(liveSeason)) {
        merged.league_trends.seasons.push(liveSeason);

        // Compute 2025 league averages from dashboard game_control
        const games2025 = gc.games || [];
        const avgDrama = games2025.length
            ? games2025.reduce((s, g) => s + g.drama, 0) / games2025.length
            : 0;
        merged.league_trends.avg_drama.push(Math.round(avgDrama * 1000) / 1000);

        const comebacks2025 = games2025.filter(g => g.comeback > 0.80).length;
        merged.league_trends.comeback_count.push(comebacks2025);

        const teams2025 = gc.teams || {};
        const gcis = Object.values(teams2025).map(t => t.gci);
        const spread = gcis.length >= 2 ? Math.max(...gcis) - Math.min(...gcis) : 0;
        merged.league_trends.avg_gci_spread.push(Math.round(spread * 10) / 10);
        merged.league_trends.game_count.push(games2025.length);
    }

    // Add 2025 to team trends
    if (merged.team_trends && gc.teams) {
        for (const [code, teamData] of Object.entries(gc.teams)) {
            if (merged.team_trends[code]) {
                const tt = merged.team_trends[code];
                if (!tt.seasons.includes(liveSeason)) {
                    tt.seasons.push(liveSeason);
                    tt.gci.push(teamData.gci);
                    tt.drama_avg.push(teamData.drama_avg);
                    tt.dominance_avg.push(teamData.dominance_avg);
                    tt.killer_instinct.push(teamData.killer_instinct);
                    tt.comeback_count.push(teamData.comeback_count);
                    tt.total_seasons += 1;
                }
            }
        }
    }

    // Update total counts
    merged.seasons_computed = [...(merged.seasons_computed || [])];
    if (!merged.seasons_computed.includes(liveSeason)) {
        merged.seasons_computed.push(liveSeason);
    }
    merged.total_games = (merged.total_games || 0) + (gc.games || []).length;

    return merged;
}

/* ── 1. Hero Section ───────────────────────────────────────────────────── */
function renderHero() {
    const trends = _merged.league_trends;
    if (!trends || trends.seasons.length < 2) return;

    const first = 0;
    const last = trends.seasons.length - 1;

    // Drama change
    const dramaFirst = trends.avg_drama[first];
    const dramaLast = trends.avg_drama[last];
    const dramaPct = dramaFirst > 0 ? Math.round((dramaLast - dramaFirst) / dramaFirst * 100) : 0;

    // Comeback change
    const cbFirst = trends.comeback_count[first] || 1;
    const cbLast = trends.comeback_count[last];
    const cbMulti = (cbLast / cbFirst).toFixed(1);

    // GCI spread change (negative = more competitive)
    const spreadFirst = trends.avg_gci_spread[first];
    const spreadLast = trends.avg_gci_spread[last];
    const spreadPct = spreadFirst > 0 ? Math.round((spreadLast - spreadFirst) / spreadFirst * 100) : 0;

    const cards = [
        {
            label: 'Avg Drama Index',
            number: `${dramaPct > 0 ? '+' : ''}${dramaPct}%`,
            color: '#e74c3c',
            sub: `${dramaFirst.toFixed(2)} → ${dramaLast.toFixed(2)}`,
            values: trends.avg_drama,
        },
        {
            label: 'Comebacks / Season',
            number: `${cbMulti}×`,
            color: '#f1c40f',
            sub: `${cbFirst} → ${cbLast} per season`,
            values: trends.comeback_count,
        },
        {
            label: 'GCI Spread (Top–Bottom)',
            number: `${spreadPct > 0 ? '+' : ''}${spreadPct}%`,
            color: '#2ecc71',
            sub: `${spreadFirst.toFixed(1)} → ${spreadLast.toFixed(1)}`,
            values: trends.avg_gci_spread,
        },
    ];

    document.getElementById('hero-metrics').innerHTML = cards.map(c => {
        const sparkline = buildSparklineSVG(c.values, c.color);
        return `<div class="hero-card">
            <div class="hero-label">${c.label}</div>
            <div class="hero-number" style="color:${c.color}">${c.number}</div>
            <div class="hero-sub">${c.sub}</div>
            <div class="hero-sparkline">${sparkline}</div>
            <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--text-muted);margin-top:2px;">
                <span>${trends.seasons[first]}</span><span>${trends.seasons[last]}</span>
            </div>
        </div>`;
    }).join('');

    document.getElementById('hero-summary').textContent =
        'The Euroleague has evolved — more drama, more comebacks, and tighter competition across 19 seasons.';
    document.getElementById('hero-count').textContent =
        `${_merged.seasons_computed.length} Seasons · ${_merged.total_games.toLocaleString()} Games · Every Play Analyzed`;
}

function buildSparklineSVG(values, color) {
    if (!values || values.length < 2) return '';
    const w = 200, h = 40;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const step = w / (values.length - 1);

    const points = values.map((v, i) =>
        `${(i * step).toFixed(1)},${(h - ((v - min) / range) * (h - 4) - 2).toFixed(1)}`
    ).join(' ');

    return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:${h}px;" preserveAspectRatio="none">
        <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
    </svg>`;
}
```

- [ ] **Step 2: Open the page in a browser and verify the hero renders**

Open `docs/gci-history.html` via a local server (`python -m http.server 8000 --directory docs`). Should show three metric cards with sparklines and real data. The remaining sections will be empty.

- [ ] **Step 3: Commit**

```bash
git add docs/gci-history.js
git commit -m "feat: add gci-history.js with data loading, merge, and hero section"
```

---

### Task 7: Build team comparison tool and era breakdown

**Files:**
- Modify: `docs/gci-history.js`

- [ ] **Step 1: Add team comparison chart functions**

Append to `docs/gci-history.js`:

```javascript
/* ── 2. Team Comparison ────────────────────────────────────────────────── */
function renderTeamPills() {
    const trends = _merged.team_trends || {};
    const container = document.getElementById('team-pills');

    // Determine which teams to show
    const legacySet = new Set(LEGACY_TEAMS);
    const allTeams = Object.keys(trends).sort((a, b) => {
        const na = TEAM_NAMES[a] || a;
        const nb = TEAM_NAMES[b] || b;
        return na.localeCompare(nb);
    });
    const displayTeams = _showAll ? allTeams : allTeams.filter(t => legacySet.has(t));

    // Default selection: top 3 GCI legacy teams from latest season
    if (_activeTeams.size === 0) {
        const latest = Math.max(...(_merged.league_trends?.seasons || [2025]));
        const withLatest = displayTeams
            .filter(t => trends[t]?.seasons?.includes(latest))
            .sort((a, b) => {
                const aIdx = trends[a].seasons.indexOf(latest);
                const bIdx = trends[b].seasons.indexOf(latest);
                return (trends[b].gci[bIdx] || 0) - (trends[a].gci[aIdx] || 0);
            });
        withLatest.slice(0, 3).forEach(t => _activeTeams.add(t));
    }

    container.innerHTML = displayTeams.map(code => {
        const name = TEAM_NAMES[code] || code;
        const color = getTeamColor(code);
        const active = _activeTeams.has(code) ? ' active' : '';
        return `<span class="team-pill${active}" data-team="${code}" onclick="toggleTeam('${code}')">
            <span class="pill-dot" style="background:${color}"></span>${name}
        </span>`;
    }).join('');

    // Show more button
    const btn = document.getElementById('show-more-btn');
    btn.textContent = _showAll ? 'Show fewer teams' : `Show more teams (${allTeams.length - displayTeams.length} more)`;
    btn.onclick = () => {
        _showAll = !_showAll;
        renderTeamPills();
    };
    if (allTeams.length <= displayTeams.length) btn.style.display = 'none';
}

function toggleTeam(code) {
    if (_activeTeams.has(code)) {
        if (_activeTeams.size > 1) _activeTeams.delete(code);
    } else {
        if (_activeTeams.size >= 5) return; // max 5
        _activeTeams.add(code);
    }
    renderTeamPills();
    renderComparisonChart();
}

function renderComparisonChart() {
    const trends = _merged.team_trends || {};
    const metric = document.getElementById('metric-select').value;
    const container = document.getElementById('comparison-chart');

    const traces = [];
    for (const code of _activeTeams) {
        const tt = trends[code];
        if (!tt) continue;
        const color = getTeamColor(code);
        const name = TEAM_NAMES[code] || code;
        const values = tt[metric] || tt.gci;

        // Build x labels as season strings
        const xLabels = tt.seasons.map(s => `${s}-${String(s + 1).slice(2)}`);

        traces.push({
            x: xLabels,
            y: values,
            mode: 'lines+markers',
            name: name,
            line: { color: color, width: 2.5 },
            marker: { size: 5, color: color },
            hovertemplate: `${name}<br>%{x}<br>${metric}: %{y:.2f}<extra></extra>`,
            connectgaps: false,
        });
    }

    const metricLabels = {
        gci: 'GCI Rating',
        drama_avg: 'Drama Index',
        dominance_avg: 'Dominance Score',
        killer_instinct: 'Killer Instinct',
        comeback_count: 'Comebacks',
    };

    const layout = Object.assign({}, PLOTLY_THEME, {
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, {
            title: 'Season',
            tickangle: -45,
            tickfont: { size: 10 },
        }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, {
            title: metricLabels[metric] || metric,
        }),
        margin: { t: 20, r: 20, b: 70, l: 55 },
        showlegend: true,
        legend: {
            orientation: 'h',
            y: -0.25,
            x: 0.5,
            xanchor: 'center',
            font: { size: 11, color: '#9ca3af' },
        },
    });

    Plotly.newPlot(container, traces, layout, PLOTLY_CONFIG);
}

// Wire up metric dropdown
document.getElementById('metric-select').addEventListener('change', renderComparisonChart);

/* ── 3. Era Breakdown ──────────────────────────────────────────────────── */
function renderEras() {
    const eras = _merged.eras || [];
    const container = document.getElementById('era-cards');

    const eraColors = ['#4ecdc4', '#f1c40f', '#e74c3c'];

    container.innerHTML = eras.map((era, i) => {
        const color = eraColors[i] || '#6b7280';
        const standoutName = TEAM_NAMES[era.standout_team] || era.standout_team;
        return `<div class="era-card" style="border-top-color:${color}">
            <div class="era-name">${era.name}</div>
            <div class="era-years">${era.years} · ${era.team_count} teams · ${era.total_games.toLocaleString()} games</div>
            <div class="era-stats">
                <div class="era-stat">
                    <span class="era-stat-label">Avg Drama</span>
                    <span class="era-stat-value">${era.avg_drama.toFixed(2)}</span>
                </div>
                <div class="era-stat">
                    <span class="era-stat-label">GCI Spread</span>
                    <span class="era-stat-value">${era.avg_gci_spread.toFixed(1)}</span>
                </div>
                <div class="era-stat">
                    <span class="era-stat-label">Comebacks</span>
                    <span class="era-stat-value">${era.total_comebacks}</span>
                </div>
            </div>
            <div class="era-standout">
                Standout: <strong>${standoutName}</strong> — ${era.standout_reason}
            </div>
        </div>`;
    }).join('');
}
```

- [ ] **Step 2: Verify team comparison and era breakdown render correctly**

Refresh the page in the browser. Should see:
- Team pills with the 10 legacy teams, 3 pre-selected
- Plotly line chart with team GCI trends across seasons
- Metric dropdown to switch between GCI/Drama/Dominance/Killer/Comebacks
- Three era cards with stats and standout teams

- [ ] **Step 3: Commit**

```bash
git add docs/gci-history.js
git commit -m "feat: add team comparison chart and era breakdown to GCI History"
```

---

### Task 8: Build historical superlatives section

**Files:**
- Modify: `docs/gci-history.js`

- [ ] **Step 1: Add superlatives rendering**

Append to `docs/gci-history.js`:

```javascript
/* ── 4. Historical Superlatives ────────────────────────────────────────── */
function renderSuperlatives() {
    const s = _merged.superlatives;
    const container = document.getElementById('superlatives');
    if (!s) {
        container.innerHTML = '<p style="color:var(--text-muted)">No superlatives available.</p>';
        return;
    }

    const cards = [
        {
            icon: '\u{1F3C6}',
            label: 'Most Dominant Season Ever',
            data: s.most_dominant_season,
            color: '#4ecdc4',
            render: d => {
                const name = TEAM_NAMES[d.team] || d.team;
                return `<div class="superlative-matchup">${name}</div>
                    <div style="color:#4ecdc4;font-size:1.2rem;font-weight:800;">GCI ${d.gci.toFixed(1)}</div>
                    <div class="superlative-season">${d.season}-${String(d.season + 1).slice(2)} Season</div>`;
            },
        },
        {
            icon: '\u26A1',
            label: 'Most Dramatic Game Ever',
            data: s.most_dramatic_game,
            color: '#ff6b6b',
            render: d => {
                const score = `${d.home_score} - ${d.away_score}`;
                const replayLink = `replay.html?season=${d.season}&game=${d.gamecode}`;
                return `<div class="superlative-matchup">${d.home} ${score} ${d.away}</div>
                    <div style="color:#ff6b6b;font-size:1rem;font-weight:700;">Drama: ${d.drama.toFixed(2)}</div>
                    <div class="superlative-season">${d.season}-${String(d.season + 1).slice(2)}</div>
                    <a href="${replayLink}" style="font-size:0.72rem;color:var(--accent-teal);margin-top:0.3rem;display:inline-block;">▶ Watch Replay</a>`;
            },
        },
        {
            icon: '\u21BB',
            label: 'Biggest Comeback Ever',
            data: s.biggest_comeback,
            color: '#ffd700',
            render: d => {
                const score = `${d.home_score} - ${d.away_score}`;
                const pct = ((1 - d.comeback) * 100).toFixed(0);
                const replayLink = `replay.html?season=${d.season}&game=${d.gamecode}`;
                return `<div class="superlative-matchup">${d.home} ${score} ${d.away}</div>
                    <div style="color:#ffd700;font-size:1rem;font-weight:700;">From ${pct}% WP</div>
                    <div class="superlative-season">${d.season}-${String(d.season + 1).slice(2)}</div>
                    <a href="${replayLink}" style="font-size:0.72rem;color:var(--accent-teal);margin-top:0.3rem;display:inline-block;">▶ Watch Replay</a>`;
            },
        },
        {
            icon: '\u2605',
            label: 'Most Dominant Game Ever',
            data: s.most_dominant_game,
            color: '#a855f7',
            render: d => {
                const score = `${d.home_score} - ${d.away_score}`;
                const replayLink = `replay.html?season=${d.season}&game=${d.gamecode}`;
                return `<div class="superlative-matchup">${d.home} ${score} ${d.away}</div>
                    <div style="color:#a855f7;font-size:1rem;font-weight:700;">Dominance: ${Math.abs(d.dominance).toFixed(2)}</div>
                    <div class="superlative-season">${d.season}-${String(d.season + 1).slice(2)}</div>
                    <a href="${replayLink}" style="font-size:0.72rem;color:var(--accent-teal);margin-top:0.3rem;display:inline-block;">▶ Watch Replay</a>`;
            },
        },
    ];

    container.innerHTML = cards.map(c => {
        if (!c.data) return '';
        return `<div class="superlative-card">
            <div class="superlative-icon" style="color:${c.color}">${c.icon}</div>
            <div class="superlative-label">${c.label}</div>
            ${c.render(c.data)}
        </div>`;
    }).join('');
}
```

- [ ] **Step 2: Verify superlatives render correctly**

Refresh the page. Should see four cards in a 2×2 grid with real all-time records, each with team names, scores, metric values, and "Watch Replay" links.

- [ ] **Step 3: Commit**

```bash
git add docs/gci-history.js
git commit -m "feat: add historical superlatives section to GCI History"
```

---

### Task 9: Add navigation link to all existing pages

**Files:**
- Modify: `docs/index.html`, `docs/team.html`, `docs/players.html`, `docs/h2h.html`, `docs/recap.html`, `docs/shots.html`, `docs/network.html`, `docs/replay.html`, `docs/playoffs.html`, `docs/mvp.html`, `docs/game-control.html`, `docs/about.html`

- [ ] **Step 1: Add "GCI History" nav link to all 12 existing pages**

In every file listed above, find the nav bar section and add the GCI History link after the Game Control link and before the About link. The exact edit in each file:

Find:
```html
        <a href="game-control.html" class="nav-link">Game Control</a>
        <a href="about.html" class="nav-link">About</a>
```

Replace with:
```html
        <a href="game-control.html" class="nav-link">Game Control</a>
        <a href="gci-history.html" class="nav-link">GCI History</a>
        <a href="about.html" class="nav-link">About</a>
```

Note: In `game-control.html`, the Game Control link has `class="nav-link active"` — keep it as-is, just add the GCI History link after it. In `about.html`, the About link has `class="nav-link active"` — keep it as-is too.

- [ ] **Step 2: Verify navigation works**

Open any existing page (e.g., `index.html`) and confirm the "GCI History" link appears in the nav bar and navigates to `gci-history.html`.

- [ ] **Step 3: Commit**

```bash
git add docs/index.html docs/team.html docs/players.html docs/h2h.html docs/recap.html docs/shots.html docs/network.html docs/replay.html docs/playoffs.html docs/mvp.html docs/game-control.html docs/about.html
git commit -m "feat: add GCI History link to navigation across all pages"
```

---

### Task 10: Update `about.html` with historical methodology

**Files:**
- Modify: `docs/about.html`

- [ ] **Step 1: Add "Historical GCI Trends" subsection**

In `docs/about.html`, find the closing `</ul>` and `</div>` of the "Game Control Metrics" section (after the GCI Rating list item, around line 500-501). Add a new paragraph after the closing `</ul>`:

Find (in the Game Control Metrics section):
```html
            </ul>
        </div>
```

Replace with:
```html
            </ul>
            <h4 style="margin-top:1.2rem;color:var(--text-primary);">Historical GCI Trends</h4>
            <p>
                The <a href="gci-history.html" style="color:var(--accent-teal);">GCI History</a> page extends
                the Game Control Index across all 19 Euroleague seasons (2007–2025), covering 5,000+ games.
                The same six sub-metrics and GCI Rating formula are applied to each historical season independently,
                with z-normalization computed within each season (so a GCI of 70 in 2007 means the same relative
                dominance as 70 in 2024).
            </p>
            <p>
                Teams are included in trend comparisons only if they have 3 or more seasons of data.
                The 10 "legacy" teams (Olympiacos, Barcelona, Real Madrid, Panathinaikos, Maccabi Tel Aviv,
                Anadolu Efes, Fenerbahce, Baskonia, EA7 Milano, Zalgiris) have been present in all 19 seasons.
                Era breakdowns use three periods: Expansion Era (2007–2015, 24 teams), Contraction Era (2016–2019,
                16 teams), and Modern Era (2020–2025, 18–20 teams).
            </p>
        </div>
```

Also update the page features list to mention GCI History. Find:
```html
                <li><span class="metric-name">Game Control</span> — How teams win, not just that they win. The Game Control Index (GCI) uses Win Probability trajectory analysis to measure dominance, drama, comeback resilience, crunch-time performance, and killer instinct for every game and team.</li>
```

Replace with:
```html
                <li><span class="metric-name">Game Control</span> — How teams win, not just that they win. The Game Control Index (GCI) uses Win Probability trajectory analysis to measure dominance, drama, comeback resilience, crunch-time performance, and killer instinct for every game and team.</li>
                <li><span class="metric-name">GCI History</span> — 19 seasons of Game Control trends (2007–2025). League-wide era analysis, team comparison tool, era breakdowns, and all-time superlatives across 5,000+ games.</li>
```

- [ ] **Step 2: Verify the about page renders correctly**

Open `docs/about.html` in a browser. The "Game Control Metrics" section should now have a "Historical GCI Trends" subsection at the bottom, and the page features list should include "GCI History".

- [ ] **Step 3: Commit**

```bash
git add docs/about.html
git commit -m "feat: add Historical GCI Trends methodology to about page"
```

---

## Self-Review

**Spec coverage check:**

| Spec Requirement | Task |
|-----------------|------|
| `calculate_gci_historical.py` batch script | Tasks 2–4 |
| Derives game results from WP files | Task 2 (load_season_games) |
| Imports compute_game_metrics from calculate_gci | Tasks 1–2 |
| gci_historical.json output | Task 4 (main) |
| Frontend merges historical + live 2025 | Task 6 (mergeWithLive) |
| Hero: 3 metric cards with sparklines | Task 6 (renderHero) |
| Team comparison: pills, Plotly line chart, metric dropdown | Task 7 (renderTeamPills, renderComparisonChart) |
| Legacy teams default, show-more toggle | Task 7 (renderTeamPills) |
| Era breakdown: 3 cards | Task 7 (renderEras) |
| Historical superlatives: 4 award cards | Task 8 (renderSuperlatives) |
| Superlative replay links | Task 8 |
| Navigation update: all 12 pages | Task 9 |
| About page methodology | Task 10 |

**Placeholder scan:** No TBDs, TODOs, or "add appropriate" phrases found.

**Type consistency:** `compute_game_metrics` returns same dict shape everywhere. `compute_season_gci` returns `{gci_ratings, components, team_profiles, game_metrics, games}` used consistently in Tasks 3–4. Frontend property names (`gci`, `drama_avg`, `dominance_avg`, `killer_instinct`, `comeback_count`) match between Python output and JS consumption.
