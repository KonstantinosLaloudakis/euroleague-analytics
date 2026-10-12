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
