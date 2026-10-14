"""Tests for game_highs.py (single-game player lines from play-by-play)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import game_highs as gh
import pbp_games as pg
from tests.pbp_fixtures import build, ev, filler

P1, P2 = 'P000001', 'P000002'


def _player_game():
    """HOM beats AWY 55-48. P1 (HOM) has a full line built from every play type."""
    def p1(pt, n=1):
        return ev('A', pt, 4, player=P1, name='ONE, A', n=n)
    events = (filler(20, 20, period=2)                       # 40-40, anonymous
              + p1('3FGM', 3) + p1('DUNK') + p1('LAYUPMD') + p1('FTM', 2)   # +15 -> 55
              + p1('FTA') + p1('2FGAB') + p1('LAYUPATT') + p1('3FGA')       # 4 misses
              + p1('D', 2) + p1('O')
              + p1('AS ', 4)                                 # trailing space, as in the feed
              + p1('ST') + p1('FV') + p1('RV', 2)
              + p1('TO', 2) + p1('AG') + p1('CM') + p1('OF')
              + ev('B', '2FGM', 4, player=P2, name='TWO, B', n=4)          # AWY -> 48
              + ev('B', 'D', 4))                             # team rebound: no player
    return pg.clean_game(build(events))


def _lines():
    return {l['player']: l for l in gh.analyze_clean(_player_game())}


def test_counting_rules_including_old_play_types():
    # PIR = 15 pts + 11 (D2 O1 AS4 ST1 FV1 RV2) - 4 misses - 3 (TO2 AG1) - 2 fouls = 17
    assert _lines()['000001']['line'] == \
        {'points': 15, 'rebounds': 3, 'assists': 4, 'threes': 3, 'pir': 17}


def test_team_opponent_home_won_and_final():
    lines = _lines()
    p1, p2 = lines['000001'], lines['000002']
    assert (p1['team'], p1['opp'], p1['home'], p1['won'], p1['final']) == \
        ('HOM', 'AWY', True, True, '55-48')
    assert (p2['team'], p2['opp'], p2['home'], p2['won'], p2['final']) == \
        ('AWY', 'HOM', False, False, '48-55')
    assert p2['line'] == {'points': 8, 'rebounds': 0, 'assists': 0, 'threes': 0, 'pir': 8}
    assert (p1['player_name'], p1['season'], p1['gamecode'], p1['phase'], p1['ot']) == \
        ('ONE, A', 2015, 7, 'RS', False)


def test_events_without_a_player_are_not_lines():
    assert set(_lines()) == {'000001', '000002'}


def _line(player, season, gamecode, points, rebounds=0, assists=0, threes=0, pir=0):
    return {'season': season, 'phase': 'RS', 'round': 3, 'gamecode': gamecode,
            'player': player, 'player_name': player, 'team': 'HOM', 'opp': 'AWY',
            'home': True, 'won': True, 'final': '80-70', 'ot': False,
            'line': {'points': points, 'rebounds': rebounds, 'assists': assists,
                     'threes': threes, 'pir': pir}}


def test_build_output_ranks_each_stat(tmp_path):
    lines = [_line('a', 2015, 1, 40, rebounds=5, pir=30),
             _line('b', 2016, 2, 40, rebounds=12, threes=8, pir=41),
             _line('c', 2017, 3, 20, assists=15, pir=25)]
    out = gh.build_output(lines, current_season=2017, games_scanned=3,
                          replay_dir=str(tmp_path), generated='2000-01-01')
    assert (out['generated'], out['seasons'], out['current_season'], out['games_scanned']) == \
        ('2000-01-01', [2015, 2017], 2017, 3)
    assert [(r['player'], r['value'], r['rank'], r['tied']) for r in out['points']] == \
        [('b', 40, 1, True), ('a', 40, 1, True), ('c', 20, 3, False)]
    assert [r['player'] for r in out['rebounds']] == ['b', 'a']
    assert [r['player'] for r in out['assists']] == ['c']
    assert [r['player'] for r in out['threes']] == ['b']
    assert [r['player'] for r in out['pir']] == ['b', 'a', 'c']
    top = out['points'][0]
    assert (top['season_label'], top['has_replay'], top['line']['rebounds']) == ('2016-17', False, 12)
