"""search_index.json builder for the nav search box."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fetch_player_career_stats import build_search_index

SCHEDULE = [
    {'homecode': 'OLY', 'hometeam': 'OLYMPIACOS PIRAEUS'},
    {'homecode': 'PAN', 'hometeam': 'PANATHINAIKOS AKTOR ATHENS'},
    {'homecode': 'OLY', 'hometeam': 'OLYMPIACOS PIRAEUS'},
]


def _p(name, *seasons):
    return {'name': name, 'seasons': [{'season_code': c, 'team_code': t} for c, t in seasons]}


def test_player_entry_fields():
    players = {'003469': _p('VEZENKOV, SASHA', ('E2026', 'OLY'), ('E2015', 'BAR'), ('E2016', 'BAR'))}
    out = build_search_index(players, SCHEDULE, 2026)
    assert out['players'] == [
        {'c': '003469', 'n': 'VEZENKOV, SASHA', 't': 'OLY', 'f': 2015, 'l': 2026, 's': 3}
    ]


def test_transfer_code_joined_with_slash():
    players = {'X': _p('DOE, JOHN', ('E2026', 'OLY;PAR'), ('E2025', 'PAR'))}
    assert build_search_index(players, SCHEDULE, 2026)['players'][0]['t'] == 'OLY/PAR'


def test_teams_come_from_schedule_without_transfer_codes():
    players = {'X': _p('DOE, JOHN', ('E2026', 'VIR;IST'))}
    out = build_search_index(players, SCHEDULE, 2026)
    assert out['teams'] == [
        {'c': 'OLY', 'n': 'OLYMPIACOS PIRAEUS'},
        {'c': 'PAN', 'n': 'PANATHINAIKOS AKTOR ATHENS'},
    ]
    assert all(';' not in t['c'] for t in out['teams'])


def test_works_before_any_games():
    players = {'X': _p('DOE, JOHN', ('E2025', 'BAR'))}
    out = build_search_index(players, SCHEDULE, 2026)
    assert out['season'] == 2026
    assert len(out['teams']) == 2


def test_skips_players_without_seasons():
    players = {'X': _p('NOBODY'), 'Y': _p('DOE, JOHN', ('E2026', 'OLY'))}
    out = build_search_index(players, SCHEDULE, 2026)
    assert [p['c'] for p in out['players']] == ['Y']
