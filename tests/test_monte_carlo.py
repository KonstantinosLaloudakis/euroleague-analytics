"""Season simulator: Bayesian team strength + calibrated standings odds."""
import os
import sys

import numpy as np
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simulate_monte_carlo import (HCA_PTS, TAU_STRENGTH, load_rs_fixtures,
                                  posterior_strength, simulate_season)


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


def _item(gc, rnd, home, away, played="false"):
    r = f"<round>{rnd}</round>" if rnd is not None else ""
    return (f"<item><gamecode>{gc}</gamecode>{r}<hometeam>{home}</hometeam>"
            f"<awayteam>{away}</awayteam><played>{played}</played></item>")


def _items(*xml_items):
    return ET.fromstring("<root>" + "".join(xml_items) + "</root>").findall('item')


def test_load_rs_fixtures_excludes_playoff_games():
    names = {"Alpha": "ALP", "Beta": "BET", "Gamma": "GAM"}
    items = _items(
        _item("E2026_1", "RS", "Alpha", "Beta", "true"),
        _item("E2026_2", "RS", "Beta", "Gamma"),
        _item("E2026_301", "PO", "Alpha", "Gamma", "true"),
        _item("E2026_385", None, "Alpha", "Beta"),
    )
    fixtures, unmapped = load_rs_fixtures(items, names)
    assert fixtures == [(1, "ALP", "BET", True), (2, "BET", "GAM", False)]
    assert unmapped == []


def test_load_rs_fixtures_missing_round_falls_back_to_gamecode():
    names = {"Alpha": "ALP", "Beta": "BET"}
    items = _items(_item("E2026_380", None, "Alpha", "Beta"),
                   _item("E2026_381", None, "Beta", "Alpha"))
    fixtures, _ = load_rs_fixtures(items, names)
    assert [f[0] for f in fixtures] == [380]


def test_load_rs_fixtures_reports_unmapped_names():
    names = {"Alpha": "ALP", "Beta": "BET"}
    items = _items(_item("E2026_1", "RS", "Alpha", "Beta"),
                   _item("E2026_2", "RS", "Alpha", "Mystery FC"))
    fixtures, unmapped = load_rs_fixtures(items, names)
    assert [f[0] for f in fixtures] == [1]
    assert unmapped == ["Mystery FC"]
