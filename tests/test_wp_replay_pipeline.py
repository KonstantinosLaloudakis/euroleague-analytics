"""WP replay data: incremental current-season PBP and partial preprocessing."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import fetch_all_seasons
import preprocess_wp_data
from season_config import ALL_SEASONS


def test_schedule_lookup_and_phase_round():
    rows = [{'gamecode': 'E2026_7', 'round': 'RS', 'gameday': '3', 'played': 'true'},
            {'gamecode': 'E2026_390', 'round': 'PO', 'gameday': '41', 'played': 'true'}]
    lookup = fetch_all_seasons.schedule_lookup(rows)
    assert lookup == {7: ('RS', 3), 390: ('PO', 41)}
    df = pd.DataFrame({'Season': [2026], 'Gamecode': [390], 'PLAYTYPE': ['BP']})
    out = fetch_all_seasons.with_phase_round(df, 390, lookup)
    assert list(out.columns[:4]) == ['Season', 'Phase', 'Round', 'Gamecode']
    assert out['Round'].iloc[0] == 41 and out['Phase'].iloc[0] == 'PO'


def test_current_season_fetch_is_incremental(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'data_cache').mkdir()
    json.dump([{'gamecode': f'E2026_{g}', 'round': 'RS', 'gameday': '1', 'played': 'true'}
               for g in (1, 2)], open('schedule_2026.json', 'w'))
    pd.DataFrame({'Season': [2026], 'Phase': ['RS'], 'Round': [1], 'Gamecode': [1]}
                 ).to_csv('data_cache/pbp_2026.csv', index=False)

    class FakePBP:
        calls = []

        def get_game_play_by_play_data(self, season, gc):
            self.calls.append(gc)
            return pd.DataFrame({'Season': [season], 'Gamecode': [gc]})

    monkeypatch.setattr('incremental_fetch.time.sleep', lambda s: None)
    pbp = FakePBP()
    df, failed = fetch_all_seasons.fetch_current_season(2026, pbp, cache_dir='data_cache')
    assert pbp.calls == [2] and failed == []
    saved = pd.read_csv('data_cache/pbp_2026.csv')
    assert sorted(saved['Gamecode']) == [1, 2]
    assert saved.loc[saved['Gamecode'] == 2, 'Phase'].iloc[0] == 'RS'


def test_seasons_json_keeps_unprocessed_seasons(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = ALL_SEASONS[0]
    os.makedirs(f'docs/data/{old}')
    json.dump([{'gc': 1}, {'gc': 2}, {'gc': 3}], open(f'docs/data/{old}/games.json', 'w'))

    # reprocess only the latest season; its PBP cache is missing -> skipped
    preprocess_wp_data.main(['--seasons', str(ALL_SEASONS[-1])])
    seasons = json.load(open('docs/data/seasons.json'))
    assert seasons == [{'season': old, 'label': f'{old}-{str(old + 1)[-2:]}', 'count': 3}]


def test_seasons_arg_parsing():
    assert preprocess_wp_data.parse_args([]).seasons is None
    assert preprocess_wp_data.parse_args(['--seasons', '2025', '2026']).seasons == [2025, 2026]
