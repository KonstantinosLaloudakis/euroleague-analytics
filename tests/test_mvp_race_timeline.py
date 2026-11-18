"""MVP race timeline is built from the per-round mvp_rankings_{S}_R{N}.json snapshots."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import build_mvp_race  # noqa: E402


def _write(path, n, team='OLY'):
    rows = [{'MVP_Rank': i + 1, 'PlayerName': f'P{i}', 'TeamCode': team,
             'MVP_Score': 90.0 - i} for i in range(n)]
    path.write_text(json.dumps(rows))


def test_builds_top_n_per_round_in_round_order(tmp_path):
    _write(tmp_path / 'mvp_rankings_2026_R6.json', 12)
    _write(tmp_path / 'mvp_rankings_2026_R5.json', 3)
    race = build_mvp_race(2026, 12, top_n=10, root=str(tmp_path))
    assert [r['round'] for r in race] == [5] * 3 + [6] * 10
    assert race[0] == {'round': 5, 'player': 'P0', 'team': 'OLY', 'score': 90.0, 'rank': 1}


def test_ignores_future_rounds_other_seasons_and_empty_snapshots(tmp_path):
    _write(tmp_path / 'mvp_rankings_2026_R4.json', 0)      # before the 5-GP minimum
    _write(tmp_path / 'mvp_rankings_2026_R5.json', 2)
    _write(tmp_path / 'mvp_rankings_2026_R13.json', 2)     # ahead of the current round
    _write(tmp_path / 'mvp_rankings_2025_R30.json', 2)     # last season
    _write(tmp_path / 'mvp_rankings_2026.json', 2)         # unsuffixed
    race = build_mvp_race(2026, 12, root=str(tmp_path))
    assert {r['round'] for r in race} == {5}


def test_no_snapshots_gives_empty_list(tmp_path):
    assert build_mvp_race(2026, 12, root=str(tmp_path)) == []
