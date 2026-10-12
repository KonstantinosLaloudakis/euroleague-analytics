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
