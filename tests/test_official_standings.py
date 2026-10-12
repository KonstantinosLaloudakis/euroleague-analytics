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


def _api_round(codes, records=None):
    """codes in position order → API standings rows."""
    records = records or {}
    return [{'code': c, 'position': i + 1, 'wins': records.get(c, (0, 0))[0],
             'losses': records.get(c, (0, 0))[1], 'points_diff': 0, 'points_for': 0}
            for i, c in enumerate(codes)]


SCHED4 = [(1, 1, 'AAA', 'BBB'), (2, 1, 'CCC', 'DDD'), (3, 2, 'AAA', 'CCC'), (4, 2, 'BBB', 'DDD')]


def test_fallback_ranks_by_point_diff_not_head_to_head():
    sched = _sched(SCHED4)
    # AAA beats BBB by 1; BBB thrashes DDD, AAA loses big to CCC → both 1-1,
    # AAA won the head-to-head but BBB has the better point difference.
    res = _res([(1, 'AAA', 'BBB', 71, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 60, 90), (4, 'BBB', 'DDD', 100, 60)])
    order, hist, recs, _ = official_standings(res, sched)
    assert order.index('BBB') < order.index('AAA')
    assert len(hist['AAA']) == 2
    assert recs['AAA'] == [[1, 0], [1, 1]] and recs['BBB'] == [[0, 1], [1, 1]]


def test_fallback_points_for_breaks_point_diff_tie():
    # Every team 1-1 with the same point difference (0) → points scored decides.
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 90, 80), (2, 'CCC', 'DDD', 60, 70),
                (3, 'AAA', 'CCC', 60, 70), (4, 'BBB', 'DDD', 90, 80)])
    # points for: AAA 150, BBB 170, CCC 130, DDD 150; AAA/DDD level → code asc
    order, hist, _, _ = official_standings(res, sched)
    assert order == ['BBB', 'AAA', 'DDD', 'CCC']
    assert [hist[t][-1] for t in order] == [1, 2, 3, 4]


def test_rank_history_is_a_permutation_each_round():
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 80, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 80, 70), (4, 'BBB', 'DDD', 80, 70)])
    order, hist, _, _ = official_standings(res, sched)
    for r in range(2):
        assert sorted(h[r] for h in hist.values()) == [1, 2, 3, 4]
    assert [hist[t][-1] for t in order] == [1, 2, 3, 4]


def test_postponed_game_counts_in_its_round():
    # Round-1 game 2 was postponed and played after round 2; snapshots are "as of now".
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 80, 70), (3, 'AAA', 'CCC', 80, 70),
                (4, 'BBB', 'DDD', 80, 70), (2, 'CCC', 'DDD', 90, 70)])
    _, hist, _, _ = official_standings(res, sched)
    # after round 1: AAA and CCC both 1-0 (CCC's postponed win counts in round 1)
    assert {hist['AAA'][0], hist['CCC'][0]} == {1, 2}


def test_team_without_games_is_ranked():
    sched = _sched([(1, 1, 'AAA', 'BBB'), (2, 2, 'CCC', 'AAA')])   # CCC hasn't played yet
    res = _res([(1, 'AAA', 'BBB', 80, 70)])
    order, hist, recs, _ = official_standings(res, sched)
    assert set(order) == {'AAA', 'BBB', 'CCC'}
    assert order[0] == 'AAA'
    assert hist['CCC'][0] in (2, 3)
    assert recs['CCC'] == [[0, 0]]


def test_no_games_played():
    order, hist, recs, _ = official_standings([], _sched([(1, 1, 'AAA', 'BBB')]))
    assert sorted(order) == ['AAA', 'BBB'] and hist == {'AAA': [], 'BBB': []}
    assert recs == {'AAA': [], 'BBB': []}


def test_api_standings_are_used():
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 80, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 80, 70), (4, 'BBB', 'DDD', 80, 70)])
    fallback_order, _, _, _ = official_standings(res, sched)
    api = {'season': 2099, 'rounds': {
        '1': _api_round(['DDD', 'CCC', 'BBB', 'AAA'],
                        {'DDD': (5, 6), 'CCC': (4, 4), 'BBB': (3, 2), 'AAA': (1, 2)}),
        '2': _api_round(['DDD', 'BBB', 'AAA', 'CCC'],
                        {'DDD': (7, 0), 'BBB': (6, 1), 'AAA': (5, 2), 'CCC': (4, 3)}),
    }}
    order, hist, recs, _ = official_standings(res, sched, api)
    assert order == ['DDD', 'BBB', 'AAA', 'CCC'] != fallback_order
    assert hist == {'DDD': [1, 1], 'CCC': [2, 4], 'BBB': [3, 2], 'AAA': [4, 3]}
    assert recs['DDD'] == [[5, 6], [7, 0]] and recs['CCC'] == [[4, 4], [4, 3]]


def test_api_round_missing_is_computed():
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 80, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 80, 70), (4, 'BBB', 'DDD', 80, 70)])
    _, fb_hist, fb_recs, _ = official_standings(res, sched)
    api = {'rounds': {'2': _api_round(['DDD', 'BBB', 'AAA', 'CCC'])}}
    order, hist, recs, _ = official_standings(res, sched, api)
    assert order == ['DDD', 'BBB', 'AAA', 'CCC']
    assert {t: h[0] for t, h in hist.items()} == {t: h[0] for t, h in fb_hist.items()}
    assert {t: r[0] for t, r in recs.items()} == {t: r[0] for t, r in fb_recs.items()}
    assert hist['DDD'][1] == 1


def test_api_missing_team_falls_back():
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 80, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 80, 70), (4, 'BBB', 'DDD', 80, 70)])
    expected = official_standings(res, sched)
    api = {'rounds': {'1': _api_round(['CCC', 'BBB', 'AAA']),
                      '2': _api_round(['CCC', 'BBB', 'AAA'])}}   # DDD missing
    assert official_standings(res, sched, api) == expected


def test_used_api_flag():
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 80, 70)])
    assert official_standings(res, sched)[3] is False
    api = {'rounds': {'1': _api_round(['DDD', 'CCC', 'BBB', 'AAA'])}}
    assert official_standings(res, sched, api)[3] is True
    partial = {'rounds': {'1': _api_round(['CCC', 'BBB', 'AAA'])}}
    assert official_standings(res, sched, partial)[3] is False


def test_latest_from_api_false_when_api_is_a_round_behind():
    sched = _sched(SCHED4)
    res = _res([(1, 'AAA', 'BBB', 80, 70), (2, 'CCC', 'DDD', 80, 70),
                (3, 'AAA', 'CCC', 80, 70), (4, 'BBB', 'DDD', 80, 70)])
    api = {'rounds': {'1': _api_round(['DDD', 'CCC', 'BBB', 'AAA'])}}
    order, hist, _, latest_from_api = official_standings(res, sched, api)
    assert latest_from_api is False
    assert len(hist['AAA']) == 2
    assert sorted(h[1] for h in hist.values()) == [1, 2, 3, 4]
