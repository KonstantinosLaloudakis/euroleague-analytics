"""Tests for game_pace.py (possessions per game and per 40 minutes)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import game_pace as gp
import pbp_games as pg
from tests.pbp_fixtures import build, ev

# HOM: 30 made 2s, 10 missed 2s, 10 FTA, 4 OREB, 6 TO -> 40 + 4.4 - 4 + 6 = 46.4
# AWY: 25 made 2s (last one in Q4), 5 missed 3s, 2 TO  -> 30 + 2 = 32
BASE = (ev('A', '2FGM', n=30) + ev('A', '2FGA', n=10) + ev('A', 'FTA', n=10)
        + ev('A', 'O', n=4) + ev('A', 'TO', n=6)
        + ev('B', '2FGM', n=24) + ev('B', '3FGA', n=5) + ev('B', 'TO', n=2)
        + ev('B', '2FGM', period=4))


def _cg(events, minute=None):
    df = build(events)
    if minute is not None:
        df['MINUTE'] = minute
    return pg.clean_game(df)


def test_possessions_formula():
    r = gp.analyze_clean(_cg(BASE))
    assert (r['home'], r['away'], r['home_pts'], r['away_pts']) == ('HOM', 'AWY', 60, 50)
    assert r['home_poss'] == pytest.approx(46.4)
    assert r['away_poss'] == pytest.approx(32.0)
    assert r['poss'] == pytest.approx(39.2)
    assert (r['minutes'], r['ot']) == (40, 0)
    assert r['pace40'] == pytest.approx(39.2)


def test_old_shot_codes_count_as_attempts():
    old = (ev('A', 'LAYUPMD', n=20) + ev('A', 'DUNK', n=10) + ev('A', 'LAYUPATT', n=10)
           + BASE[40:])   # BASE minus HOM's 30 2FGM + 10 2FGA
    assert gp.analyze_clean(_cg(old))['home_poss'] == pytest.approx(46.4)


def test_four_overtimes_scale_by_sixty_minutes():
    r = gp.analyze_clean(_cg(BASE + ev('B', 'TO', period=5), minute=61))
    assert (r['ot'], r['minutes']) == (4, 60)
    assert r['poss'] == pytest.approx(39.7)
    assert r['pace40'] == pytest.approx(39.7 * 40 / 60)


def test_overtime_without_minute_column_counts_one():
    r = gp.analyze_clean(_cg(BASE + ev('B', 'TO', period=5)))
    assert (r['ot'], r['minutes']) == (1, 45)
