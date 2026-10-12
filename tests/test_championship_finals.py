"""Championship finals history: correct final game and lead-change counting."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import championship_final_gamecode, game_flow


def _write_pbp(tmp_path, season, rows):
    lines = ['Season,Phase,Round,Gamecode,POINTS_A,POINTS_B']
    lines += [f'{season},{ph},1,{gc},,' for ph, gc in rows]
    (tmp_path / f'pbp_{season}.csv').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def test_final_gamecode_picks_highest_ff(tmp_path):
    _write_pbp(tmp_path, 2018, [('RS', 240), ('PO', 256), ('FF', 257), ('FF', 258), ('FF', 259), ('FF', 260)])
    assert championship_final_gamecode(2018, str(tmp_path)) == 260


def test_final_gamecode_none_without_final_four(tmp_path):
    # 2019-20 was cancelled: regular season only
    _write_pbp(tmp_path, 2019, [('RS', 1), ('RS', 252)])
    assert championship_final_gamecode(2019, str(tmp_path)) is None


def test_final_gamecode_missing_pbp_returns_none(tmp_path):
    assert championship_final_gamecode(2011, str(tmp_path)) is None


def test_game_flow_wire_to_wire():
    assert game_flow([(2, 0), (4, 0), (4, 3), (6, 3)]) == (0, 0)


def test_game_flow_counts_switches_not_first_lead():
    # A leads, B leads, A leads → 2 changes; one tie after a lead
    assert game_flow([(2, 0), (2, 2), (2, 3), (5, 3)]) == (2, 1)


def test_game_flow_dedupes_repeated_scores():
    # 4-4 appears in two consecutive entries → one tie
    assert game_flow([(2, 0), (2, 2), (4, 2), (4, 4), (4, 4), (4, 6)]) == (1, 2)


def test_game_flow_ignores_opening_zero_zero():
    assert game_flow([(0, 0), (0, 2), (3, 2)]) == (1, 0)
