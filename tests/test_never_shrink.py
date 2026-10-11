"""Fetchers only add games: a throttled run never shrinks a cache (no network)."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from incremental_fetch import fetch_with_retry
from fetch_mvp_data_v2 import update_game_stats, game_codes_in
from fetch_lineups import fetch_games_metadata
import fetch_lineups

NO_SLEEP = lambda s: None


# ── shared retry helper ──────────────────────────────────────────────────

def test_retry_returns_first_non_empty():
    calls = []

    def fetch_one(gc):
        calls.append(gc)
        return pd.DataFrame() if len(calls) < 3 else pd.DataFrame({'x': [gc]})

    sleeps = []
    out = fetch_with_retry(fetch_one, 5, max_retries=4, sleep=sleeps.append)
    assert list(out['x']) == [5]
    assert len(calls) == 3
    assert sleeps == [4, 8]


def test_retry_gives_up_with_none():
    calls = []

    def boom(gc):
        calls.append(gc)
        raise RuntimeError('429')

    sleeps = []
    assert fetch_with_retry(boom, 1, max_retries=2, sleep=sleeps.append) is None
    assert len(calls) == 3
    assert sleeps == [4, 8]


# ── box scores JSON (fetch_mvp_data_v2) ──────────────────────────────────

def _game(gc):
    return pd.DataFrame([{'Season': 2026, 'Gamecode': gc,
                          'local.players': [{'player': {'person': {'name': f'P{gc}'}}}]}])


def _write_existing(path, codes):
    recs = [{'Season': 2026, 'Gamecode': gc, 'GameCode': gc,
             'local.players': [{'player': {'person': {'name': f'OLD{gc}'}}}]} for gc in codes]
    path.write_text(json.dumps(recs))
    return recs


def test_box_scores_fetch_only_missing_and_keep_nested(tmp_path):
    path = tmp_path / 'stats.json'
    _write_existing(path, [1, 2])
    calls = []

    def fetch_one(gc):
        calls.append(gc)
        return _game(gc)

    recs, failed = update_game_stats(str(path), [1, 2, 3, 4], fetch_one, sleep=NO_SLEEP)
    assert calls == [3, 4] and failed == []
    saved = json.loads(path.read_text())
    assert game_codes_in(saved) == {1, 2, 3, 4}
    # existing records untouched, nested player lists survive as lists
    assert saved[0]['local.players'][0]['player']['person']['name'] == 'OLD1'
    assert saved[-1]['local.players'][0]['player']['person']['name'] == 'P4'


def test_box_scores_never_shrink_when_api_throttled(tmp_path):
    path = tmp_path / 'stats.json'
    _write_existing(path, [1, 2, 3])
    before = path.read_text()

    recs, failed = update_game_stats(str(path), [1, 2, 3, 4, 5],
                                     lambda gc: pd.DataFrame(), max_retries=1,
                                     sleep=NO_SLEEP)
    assert failed == [4, 5]
    assert path.read_text() == before          # nothing new -> file not rewritten
    assert game_codes_in(recs) == {1, 2, 3}


def test_box_scores_no_existing_all_fail_writes_nothing(tmp_path):
    path = tmp_path / 'stats.json'
    recs, failed = update_game_stats(str(path), [1], lambda gc: None,
                                     max_retries=0, sleep=NO_SLEEP)
    assert recs == [] and failed == [1]
    assert not path.exists()


# ── games_{S}.csv metadata (fetch_lineups) ───────────────────────────────

class _FakeMeta:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    def get_game_metadata(self, season, gc):
        self.calls.append(gc)
        return self.behaviour(gc)


def _meta_frame(gc):
    return pd.DataFrame({'Season': [2026], 'Gamecode': [gc],
                         'CodeTeamA': ['RED'], 'CodeTeamB': ['ZAL']})


def _setup_cache(tmp_path, monkeypatch, codes):
    monkeypatch.setattr(fetch_lineups, 'CACHE_DIR', str(tmp_path))
    path = tmp_path / 'games_2026.csv'
    pd.DataFrame({'Gamecode': codes, 'gamenumber': codes,
                  'homecode': ['OLY'] * len(codes), 'awaycode': ['PAN'] * len(codes)}
                 ).to_csv(path, index=False)
    return path


def test_metadata_incremental(tmp_path, monkeypatch):
    path = _setup_cache(tmp_path, monkeypatch, [1, 2])
    meta = _FakeMeta(_meta_frame)
    df = fetch_games_metadata(2026, meta=meta, gamecodes=[1, 2, 3], sleep=NO_SLEEP)
    assert meta.calls == [3]
    saved = pd.read_csv(path)
    assert sorted(saved['Gamecode']) == [1, 2, 3]
    assert saved.loc[saved['Gamecode'] == 3, 'homecode'].iloc[0] == 'RED'
    assert len(df) == 3


def test_metadata_all_empty_keeps_existing(tmp_path, monkeypatch):
    path = _setup_cache(tmp_path, monkeypatch, [1, 2])
    before = path.read_text()
    meta = _FakeMeta(lambda gc: pd.DataFrame())
    df = fetch_games_metadata(2026, meta=meta, gamecodes=[1, 2, 3, 4], sleep=NO_SLEEP)
    assert path.read_text() == before
    assert len(df) == 2


def test_metadata_api_errors_keep_existing(tmp_path, monkeypatch):
    path = _setup_cache(tmp_path, monkeypatch, [1, 2, 3])
    before = path.read_text()

    def boom(gc):
        raise ConnectionError('down')

    df = fetch_games_metadata(2026, meta=_FakeMeta(boom), gamecodes=[1, 2, 3, 4], sleep=NO_SLEEP)
    assert path.read_text() == before
    assert len(df) == 3


def test_metadata_no_cache_all_empty_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_lineups, 'CACHE_DIR', str(tmp_path))
    df = fetch_games_metadata(2026, meta=_FakeMeta(lambda gc: None),
                              gamecodes=[1, 2], sleep=NO_SLEEP)
    assert df.empty
    assert not (tmp_path / 'games_2026.csv').exists()
