"""fetch_standings.py: official standings per played regular-season round."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import fetch_standings
from season_config import CURRENT_SEASON


def _write_schedule(tmp_path, played_rounds, total_rounds=3):
    rows = []
    for gd in range(1, total_rounds + 1):
        rows.append({'gameday': str(gd), 'round': 'RS', 'gamecode': f'E_{gd}',
                     'homecode': 'AAA', 'awaycode': 'BBB',
                     'played': 'True' if gd <= played_rounds else 'false'})
    rows.append({'gameday': '99', 'round': 'PO', 'gamecode': 'E_99',
                 'homecode': 'AAA', 'awaycode': 'BBB', 'played': 'true'})
    (tmp_path / f'schedule_{CURRENT_SEASON}.json').write_text(json.dumps(rows), encoding='utf-8')


def _df(rnd):
    # BBB ahead of AAA in odd rounds, AAA ahead in even ones; rows deliberately unsorted.
    first, second = ('BBB', 'AAA') if rnd % 2 else ('AAA', 'BBB')
    return pd.DataFrame([
        {'position': '2', 'gamesWon': '0', 'gamesLost': str(rnd), 'pointsDifference': '-3',
         'pointsFor': '150', 'club.code': second},
        {'position': '1', 'gamesWon': str(rnd), 'gamesLost': '0', 'pointsDifference': '+12',
         'pointsFor': '160', 'club.code': first},
    ])


def _out(tmp_path):
    return tmp_path / f'standings_{CURRENT_SEASON}.json'


def test_writes_rounds_with_parsed_ints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_schedule(tmp_path, played_rounds=2)
    calls = []
    monkeypatch.setattr(fetch_standings, 'get_round_standings',
                        lambda season, rnd: calls.append((season, rnd)) or _df(rnd))
    assert fetch_standings.main() == 0
    data = json.loads(_out(tmp_path).read_text(encoding='utf-8'))
    assert calls == [(CURRENT_SEASON, 1), (CURRENT_SEASON, 2)]
    assert data['season'] == CURRENT_SEASON
    assert sorted(data['rounds']) == ['1', '2']
    assert data['rounds']['1'] == [
        {'code': 'BBB', 'position': 1, 'wins': 1, 'losses': 0, 'points_diff': 12, 'points_for': 160},
        {'code': 'AAA', 'position': 2, 'wins': 0, 'losses': 1, 'points_diff': -3, 'points_for': 150},
    ]
    assert [r['code'] for r in data['rounds']['2']] == ['AAA', 'BBB']


def test_failing_round_keeps_cached_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_schedule(tmp_path, played_rounds=2)
    cached = [{'code': 'ZZZ', 'position': 1, 'wins': 9, 'losses': 9,
               'points_diff': 0, 'points_for': 1}]
    _out(tmp_path).write_text(json.dumps({'season': CURRENT_SEASON, 'rounds': {'2': cached}}),
                              encoding='utf-8')

    def fake(season, rnd):
        if rnd == 2:
            raise RuntimeError('API down')
        return _df(rnd)

    monkeypatch.setattr(fetch_standings, 'get_round_standings', fake)
    assert fetch_standings.main() == 0
    data = json.loads(_out(tmp_path).read_text(encoding='utf-8'))
    assert data['rounds']['2'] == cached
    assert data['rounds']['1'][0]['code'] == 'BBB'


def test_no_schedule_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_standings, 'get_round_standings',
                        lambda season, rnd: (_ for _ in ()).throw(AssertionError('no call')))
    assert fetch_standings.main() == 0
    assert not _out(tmp_path).exists()


def test_no_played_round_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_schedule(tmp_path, played_rounds=0)
    monkeypatch.setattr(fetch_standings, 'get_round_standings',
                        lambda season, rnd: (_ for _ in ()).throw(AssertionError('no call')))
    assert fetch_standings.main() == 0
    assert not _out(tmp_path).exists()
