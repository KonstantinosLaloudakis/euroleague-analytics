import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fetch_lineups import to_team_lineup_columns


def _game():
    a = ['A1', 'A2', 'A3', 'A4', 'A5']
    b = ['B1', 'B2', 'B3', 'B4', 'B5']
    return pd.DataFrame({
        'Gamecode': [7, 7, 7, 7],
        'CODETEAM': ['RED', 'PAR', 'RED', None],
        'PLAYER':   ['A1', 'B2', 'A3', None],
        'IsHomeTeam': [None] * 4,
        'Lineup_A': [a, a, a, a],
        'Lineup_B': [b, b, b, b],
    })


def test_renames_by_player_membership():
    out = to_team_lineup_columns(_game())
    assert 'Lineup_RED' in out.columns and 'Lineup_PAR' in out.columns
    assert 'Lineup_A' not in out.columns and 'Lineup_B' not in out.columns
    assert out['Lineup_RED'].iloc[0][0] == 'A1'
    assert list(out['GameCode']) == [7, 7, 7, 7]


def test_swapped_sides():
    df = _game()
    df['CODETEAM'] = ['PAR', 'RED', 'PAR', None]   # A players belong to PAR now
    out = to_team_lineup_columns(df)
    assert out['Lineup_PAR'].iloc[0][0] == 'A1'


def test_old_format_passthrough():
    df = pd.DataFrame({'Gamecode': [1], 'Lineup_IST': [['x']]})
    out = to_team_lineup_columns(df)
    assert 'Lineup_IST' in out.columns


def test_same_team_for_both_sides_does_not_duplicate_columns(capsys):
    df = _game()
    df['CODETEAM'] = ['RED', 'RED', 'RED', None]   # B2 also attributed to RED
    out = to_team_lineup_columns(df)
    assert not out.columns.duplicated().any()
    assert 'Lineup_RED' in out.columns
    assert 'Lineup_B' in out.columns   # ambiguous side left unrenamed
    assert 'WARNING' in capsys.readouterr().out


def test_unresolvable_side_left_unrenamed():
    df = _game()
    df['CODETEAM'] = [None] * 4
    out = to_team_lineup_columns(df)
    assert 'Lineup_A' in out.columns and 'Lineup_B' in out.columns


def test_normalize_games_metadata():
    from fetch_lineups import normalize_games_metadata
    df = pd.DataFrame({'Gamecode': [5], 'CodeTeamA': ['PAN'], 'CodeTeamB': ['PRS']})
    out = normalize_games_metadata(df)
    assert out['gamenumber'].iloc[0] == 5 and out['homecode'].iloc[0] == 'PAN'
    assert out['awaycode'].iloc[0] == 'PRS'
