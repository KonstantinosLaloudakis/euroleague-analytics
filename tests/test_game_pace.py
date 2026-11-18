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


@pytest.mark.parametrize('minute, ot', [(45, 1), (50, 2), (55, 3)])
def test_overtime_count_from_last_minute_inside_period(minute, ot):
    r = gp.analyze_clean(_cg(BASE + ev('B', 'TO', period=5), minute=minute))
    assert (r['ot'], r['minutes']) == (ot, 40 + 5 * ot)


def test_overtime_without_minute_counts_begin_period_rows():
    r = gp.analyze_clean(_cg(BASE + ev('A', 'BP', period=5, n=2)))
    assert (r['ot'], r['minutes']) == (2, 50)


def _g(season, phase, gc, home, away, hp, ap, pace, rnd=1):
    return {'season': season, 'phase': phase, 'round': rnd, 'gamecode': gc,
            'home': home, 'away': away, 'home_pts': hp, 'away_pts': ap,
            'home_poss': pace, 'away_poss': pace, 'poss': pace,
            'minutes': 40, 'ot': 0, 'pace40': pace}


# League 72: AAA 73 (+1), BBB 72 (0), CCC 71 (-1)
TRIO = [_g(2020, 'RS', 1, 'AAA', 'BBB', 80, 70, 74),
        _g(2020, 'RS', 2, 'AAA', 'CCC', 75, 70, 72),
        _g(2020, 'TS', 3, 'BBB', 'CCC', 70, 60, 70, rnd=2)]


def test_league_pace_uses_regular_season_only():
    rows = gp.league_by_season(TRIO + [_g(2020, 'PO', 4, 'AAA', 'BBB', 60, 55, 60)])
    assert len(rows) == 1
    r = rows[0]
    assert (r['season'], r['season_label'], r['games'], r['last_round']) == (2020, '2020-21', 3, 2)
    assert r['pace'] == pytest.approx(72.0)
    assert r['pts_per_game'] == pytest.approx(425 / 6, abs=0.01)
    assert r['ortg'] == pytest.approx(100 * 425 / 432, abs=0.01)


def test_league_last_round_is_none_when_no_rounds():
    rows = gp.league_by_season([_g(2020, 'RS', 1, 'AAA', 'BBB', 80, 70, 74, rnd=None)])
    assert rows[0]['last_round'] is None


def test_team_seasons_rank_relative_and_adjusted():
    t = {r['team']: r for r in gp.team_seasons(TRIO)}
    assert [t[c]['pace'] for c in ('AAA', 'BBB', 'CCC')] == pytest.approx([73, 72, 71])
    assert [t[c]['pace_rel'] for c in ('AAA', 'BBB', 'CCC')] == pytest.approx([1, 0, -1])
    assert [t[c]['adj_rel'] for c in ('AAA', 'BBB', 'CCC')] == pytest.approx([1.5, 0, -1.5])
    assert [t[c]['rank'] for c in ('AAA', 'BBB', 'CCC')] == [1, 2, 3]
    assert [t[c]['adj_rank'] for c in ('AAA', 'BBB', 'CCC')] == [1, 2, 3]
    assert (t['AAA']['gp'], t['AAA']['wins'], t['CCC']['wins'], t['AAA']['teams']) == (2, 2, 0, 3)
    assert t['AAA']['ortg'] == pytest.approx(100 * 155 / 146, abs=0.01)
    assert t['AAA']['net'] == pytest.approx(100 * (155 - 140) / 146, abs=0.01)


def test_champion_wins_highest_final_four_gamecode():
    ff = [_g(2020, 'FF', 300, 'AAA', 'BBB', 80, 70, 70),
          _g(2020, 'FF', 301, 'CCC', 'DDD', 60, 70, 70),
          _g(2020, 'FF', 302, 'AAA', 'CCC', 70, 75, 70)]
    assert gp.champions(ff) == {2020: 'CCC'}
    t = {r['team']: r for r in gp.team_seasons(TRIO + ff)}
    assert (t['CCC']['champion'], t['AAA']['champion']) == (True, False)
    assert 'DDD' not in t                     # Final Four games are not regular season


def test_playoffs_only_for_seasons_that_have_them():
    games = TRIO + [_g(2020, 'PO', 4, 'AAA', 'BBB', 60, 55, 60),
                    _g(2019, 'RS', 1, 'AAA', 'BBB', 70, 60, 71)]
    assert gp.playoff_vs_regular(games) == [
        {'season': 2020, 'season_label': '2020-21', 'regular': 72.0, 'playoffs': 60.0, 'diff': -12.0}]


def test_extremes_sorted_both_ways():
    ex = gp.extremes(TRIO, n=2)
    assert [g['pace40'] for g in ex['slowest']] == [70, 72]
    assert [g['pace40'] for g in ex['fastest']] == [74, 72]


def test_build_output_shape(tmp_path):
    out = gp.build_output(TRIO, 2020, replay_dir=str(tmp_path), generated='2026-11-18')
    assert set(out) == {'generated', 'current_season', 'league', 'teams', 'playoffs', 'extremes'}
    assert (out['generated'], out['current_season']) == ('2026-11-18', 2020)
    first = out['extremes']['slowest'][0]
    assert (first['season_label'], first['has_replay']) == ('2020-21', False)
