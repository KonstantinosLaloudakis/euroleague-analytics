"""Lineup columns are oriented by home team, not by CSV column order."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from lineup_utils import infer_team_a, order_lineup_cols, extract_stints
import calculate_lineups

HOME = ['H1', 'H2', 'H3', 'H4', 'H5']
AWAY = ['A1', 'A2', 'A3', 'A4', 'A5']


def _game(gc=5):
    """HOM (home, POINTS_A) beats AWY 6-2; AWY's column comes first."""
    rows = [  # CODETEAM, PLAYTYPE, POINTS_A, POINTS_B
        ('HOM', 'JB', None, None),
        ('HOM', '2FGM', 2, None),
        ('AWY', '2FGA', None, None),
        ('HOM', '2FGM', 4, None),
        ('AWY', '2FGM', None, 2),
        ('HOM', '2FGM', 6, 2),
        ('AWY', 'TO', None, None),
    ]
    return pd.DataFrame({
        'Gamecode': gc,
        'NUMBEROFPLAY': range(len(rows)),
        'CODETEAM': [r[0] for r in rows],
        'PLAYER': None,
        'PLAYTYPE': [r[1] for r in rows],
        'POINTS_A': [r[2] for r in rows],
        'POINTS_B': [r[3] for r in rows],
        'Lineup_AWY': [str(AWAY)] * len(rows),   # away column appears first
        'Lineup_HOM': [str(HOME)] * len(rows),
    })


def test_infer_team_a_from_scoring():
    assert infer_team_a(_game(), ['AWY', 'HOM']) == 'HOM'


def test_order_uses_home_code_then_inference():
    g = _game()
    cols = ['Lineup_AWY', 'Lineup_HOM']
    assert order_lineup_cols(g, cols, 'HOM') == ('Lineup_HOM', 'Lineup_AWY')
    assert order_lineup_cols(g, cols, None) == ('Lineup_HOM', 'Lineup_AWY')
    assert order_lineup_cols(g, cols, 'XXX') == ('Lineup_HOM', 'Lineup_AWY')


def test_stints_credit_points_to_the_right_team():
    g = _game()
    col_a, col_b = order_lineup_cols(g, ['Lineup_AWY', 'Lineup_HOM'], 'HOM')
    (s,) = extract_stints(g, col_a, col_b)
    assert s['team_a'] == 'HOM' and s['lineup_a'] == tuple(HOME)
    assert (s['pts_a'], s['pts_b']) == (6, 2)


def test_lineups_net_rating_sign(tmp_path, monkeypatch):
    monkeypatch.setattr(calculate_lineups, 'CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(calculate_lineups, 'MIN_POSS_5', 0)
    monkeypatch.setattr(calculate_lineups, 'MIN_POSS_2', 0)
    _game().to_csv(tmp_path / 'pbp_lineups_2026.csv', index=False)
    fiveman, _pairs = calculate_lineups.process_season(2026)
    net = {r['team']: r['netrtg'] for r in fiveman}
    assert net['HOM'] > 0 > net['AWY']
