import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from incremental_fetch import played_gamecodes, fetch_missing_games


def test_played_gamecodes(tmp_path):
    p = tmp_path / 'schedule.json'
    p.write_text(json.dumps([
        {'gamecode': 'E2026_3', 'played': 'true'},
        {'gamecode': 'E2026_1', 'played': 'true'},
        {'gamecode': 'E2026_2', 'played': 'false'},
    ]))
    assert played_gamecodes(str(p)) == [1, 3]


def test_only_missing_games_fetched(tmp_path):
    cache = tmp_path / 'c.csv'
    pd.DataFrame({'Gamecode': [1, 1], 'x': [0, 0]}).to_csv(cache, index=False)
    calls = []

    def fetch_one(gc):
        calls.append(gc)
        return pd.DataFrame({'Gamecode': [gc], 'x': [gc]})

    df, failed = fetch_missing_games(str(cache), [1, 2, 3], fetch_one, sleep=lambda s: None)
    assert calls == [2, 3]
    assert failed == []
    assert sorted(df['Gamecode'].unique()) == [1, 2, 3]
    assert sorted(pd.read_csv(cache)['Gamecode'].unique()) == [1, 2, 3]


def test_empty_response_is_retried_then_reported(tmp_path):
    attempts = {'n': 0}

    def flaky(gc):
        attempts['n'] += 1
        if gc == 2:
            return pd.DataFrame()          # what euroleague_api returns on 429
        return pd.DataFrame({'Gamecode': [gc]})

    df, failed = fetch_missing_games(str(tmp_path / 'c.csv'), [1, 2], flaky,
                                     max_retries=3, sleep=lambda s: None)
    assert failed == [2]
    assert attempts['n'] == 1 + (1 + 3)
    assert list(df['Gamecode']) == [1]


def test_exception_then_success(tmp_path):
    state = {'n': 0}

    def fetch_one(gc):
        state['n'] += 1
        if state['n'] == 1:
            raise RuntimeError('429')
        return pd.DataFrame({'Gamecode': [gc]})

    df, failed = fetch_missing_games(str(tmp_path / 'c.csv'), [5], fetch_one, sleep=lambda s: None)
    assert failed == [] and list(df['Gamecode']) == [5]


def test_nothing_missing_no_write(tmp_path):
    df, failed = fetch_missing_games(str(tmp_path / 'none.csv'), [], lambda gc: None, sleep=lambda s: None)
    assert df.empty and failed == [] and not (tmp_path / 'none.csv').exists()


def test_flushes_every_10_games_survives_interrupt(tmp_path):
    import pytest
    cache = tmp_path / 'c.csv'
    n = {'n': 0}

    def fetch_one(gc):
        n['n'] += 1
        if n['n'] == 12:
            raise KeyboardInterrupt()
        return pd.DataFrame({'Gamecode': [gc]})

    with pytest.raises(KeyboardInterrupt):
        fetch_missing_games(str(cache), list(range(1, 21)), fetch_one, sleep=lambda s: None)
    assert sorted(pd.read_csv(cache)['Gamecode']) == list(range(1, 11))
    assert not (tmp_path / 'c.csv.tmp').exists()
