"""Mathematical clinch / elimination for Top 4/6/10 (ties never decide)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import clinch_status


def _teams(n, wins, remaining):
    codes = [f'T{i:02d}' for i in range(n)]
    return dict(zip(codes, wins)), dict(zip(codes, remaining))


def test_nothing_decided_early():
    w, r = _teams(20, [4, 4] + [2] * 18, [34] * 20)
    s = clinch_status(w, r)
    assert not any(s[t]['clinched'][k] or s[t]['eliminated'][k] for t in s for k in ('4', '6', '10'))


def test_clinched_when_fewer_than_n_can_catch_up():
    # T00 has 30 wins; only 3 others can still reach 30 → clinched top 4 (and 6, 10)
    w, r = _teams(20, [30, 28, 28, 28] + [20] * 16, [2, 2, 2, 2] + [2] * 16)
    s = clinch_status(w, r)
    assert s['T00']['clinched'] == {'4': True, '6': True, '10': True}


def test_tie_possible_is_not_clinched():
    # 4 others can reach exactly T00's wins → not clinched top 4
    w, r = _teams(20, [30, 28, 28, 28, 28] + [10] * 15, [0, 2, 2, 2, 2] + [0] * 15)
    s = clinch_status(w, r)
    assert s['T00']['clinched']['4'] is False
    assert s['T00']['clinched']['6'] is True


def test_eliminated_when_n_teams_already_above_max():
    # T19 max = 12; 10 teams already have more than 12 → eliminated from top 10
    w, r = _teams(20, [20] * 10 + [10] * 9 + [10], [0] * 19 + [2])
    s = clinch_status(w, r)
    assert s['T19']['eliminated']['10'] is True
    assert s['T19']['eliminated']['4'] is True


def test_equal_to_max_is_not_eliminated():
    # 10 teams have exactly T19's max → not eliminated (tiebreak could favour T19)
    w, r = _teams(20, [12] * 10 + [5] * 9 + [10], [0] * 19 + [2])
    s = clinch_status(w, r)
    assert s['T19']['eliminated']['10'] is False


from export_dashboard_data import remaining_games, final_status_from_positions


def _sched_rows(pairs):
    return [{'round': 'RS', 'hometeam': h, 'awayteam': a, 'homecode': h, 'awaycode': a,
             'played': 'true'} for h, a in pairs]


def test_remaining_basic():
    rows = _sched_rows([('AAA', 'BBB')] * 19 + [('BBB', 'AAA')] * 19)
    assert remaining_games({'AAA': (4, 0), 'BBB': (0, 4)}, rows) == {'AAA': 34, 'BBB': 34}


def test_remaining_counts_unfetched_game_as_remaining():
    # schedule says 2 games played, but W-L only includes 1 -> the other still counts as remaining
    rows = _sched_rows([('AAA', 'BBB'), ('BBB', 'AAA')])
    assert remaining_games({'AAA': (1, 0), 'BBB': (0, 1)}, rows) == {'AAA': 1, 'BBB': 1}
    assert remaining_games({'AAA': (0, 0), 'BBB': (0, 0)}, rows) == {'AAA': 2, 'BBB': 2}


def test_remaining_none_when_team_missing_from_schedule():
    rows = _sched_rows([('AAA', 'BBB')])
    assert remaining_games({'AAA': (0, 0), 'BBB': (0, 0), 'CCC': (0, 0)}, rows) is None
    assert remaining_games({'AAA': (0, 0)}, []) is None


def test_final_status_from_positions():
    pos = {f'T{i:02d}': i + 1 for i in range(20)}
    s = final_status_from_positions(pos)
    assert s['T00']['clinched'] == {'4': True, '6': True, '10': True}
    assert s['T00']['eliminated'] == {'4': False, '6': False, '10': False}
    assert s['T04']['clinched'] == {'4': False, '6': True, '10': True}
    assert s['T04']['eliminated'] == {'4': True, '6': False, '10': False}
    assert s['T19']['eliminated'] == {'4': True, '6': True, '10': True}
