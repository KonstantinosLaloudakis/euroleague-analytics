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
