"""Tests for pbp_games.py (shared play-by-play cleaning and helpers)."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pbp_games as pg
from tests.pbp_fixtures import BASIC, build, ev, filler, game


def test_clean_game_basic_fields():
    cg = pg.clean_game(game(BASIC))
    assert (cg.season, cg.phase, cg.round, cg.gamecode) == (2015, 'RS', 3, 7)
    assert (cg.final_a, cg.final_b, cg.a_won) == (50, 52, False)
    assert (cg.code_a, cg.name_a, cg.code_b, cg.name_b) == ('HOM', 'HOM Club', 'AWY', 'AWY Club')
    assert cg.ot is False
    assert len(cg.sc) == 51 and cg.periods[-1] == 4 and cg.clocks[-1] == '00:10'
    assert len(cg.rows) == 52          # includes the non-scoring Begin Period row


def test_tied_final_is_none():
    assert pg.clean_game(game([('A', 25, 2, 1, '05:00'), ('B', 25, 2, 4, '05:00')])) is None


def test_pid_strip_and_playtype_strip():
    events = (filler(25, 26, period=4)
              + ev('A', 'AS ', 4, player='P012774', name='DOE, JOHN')
              + ev('B', 'D', 4, player=' PABC ', name='ROE, RICH'))
    cg = pg.clean_game(build(events))
    assert '012774' in cg.rows['PID'].tolist()
    assert 'ABC' in cg.rows['PID'].tolist()
    assert cg.rows['PID'].isna().sum() == 52   # Begin Period row + 51 anonymous baskets
    assert 'AS' in cg.rows['PT'].tolist()


def test_scores_and_periods_given_as_strings_are_coerced():
    df = game(BASIC).astype({'POINTS_A': object, 'PERIOD': object})
    df['POINTS_A'] = df['POINTS_A'].map(lambda v: v if pd.isna(v) else str(int(v)))
    df['PERIOD'] = df['PERIOD'].astype(str)
    cg = pg.clean_game(df)
    assert (cg.final_a, cg.final_b) == (50, 52)


def _with_stale_row_after_eg(with_eg):
    events = filler(25, 26, period=4) + (ev('A', 'EG', 4, '00:00') if with_eg else [])
    df = build(events)
    stale = df[df['POINTS_A'].notna()].iloc[-3].copy()      # an earlier score, logged last
    stale['NUMBEROFPLAY'] = stale['TRUE_NUMBEROFPLAY'] = len(df)
    return pd.concat([df, stale.to_frame().T], ignore_index=True), len(df)


def test_stale_correction_row_after_end_game_does_not_set_final():
    df, stale_key = _with_stale_row_after_eg(True)
    cg = pg.clean_game(df)
    assert (cg.final_a, cg.final_b, cg.a_won) == (25 * 2, 26 * 2, False)
    assert len(cg.sc) == 51
    assert stale_key in cg.rows['TRUE_NUMBEROFPLAY'].tolist()   # late row stays in rows


def test_stale_row_without_end_game_still_sets_final():
    df, _ = _with_stale_row_after_eg(False)
    cg = pg.clean_game(df)
    assert (cg.final_a, cg.final_b) != (50, 52)


def _with_late_logged_row(clock, pa, pb, last_clock='00:05'):
    """filler 50-52, a 3-pointer at last_clock (53-52), then a row logged after it
    (higher play number) with the given clock/score, then an End Game row."""
    df = build(filler(25, 26, period=4) + ev('A', '3FGM', 4, last_clock))
    late = df.iloc[-1].copy()
    late['NUMBEROFPLAY'] = late['TRUE_NUMBEROFPLAY'] = len(df)
    late['MARKERTIME'], late['POINTS_A'], late['POINTS_B'] = clock, pa, pb
    end = df.iloc[0].copy()
    end['NUMBEROFPLAY'] = end['TRUE_NUMBEROFPLAY'] = len(df) + 1
    end['PLAYTYPE'], end['PERIOD'] = 'EG', 4
    return pd.concat([df, late.to_frame().T, end.to_frame().T], ignore_index=True), len(df)


def test_stale_row_before_eg_is_dropped():
    df, stale_key = _with_late_logged_row('00:33', 50, 52)
    cg = pg.clean_game(df)
    assert (cg.final_a, cg.final_b, cg.a_won) == (53, 52, True)
    assert len(cg.sc) == 52 and cg.clocks[-1] == '00:05'
    assert len(cg.a) == len(cg.b) == len(cg.periods) == len(cg.clocks) == 52
    assert stale_key in cg.rows['TRUE_NUMBEROFPLAY'].tolist()   # still counted in rows


def test_out_of_order_row_with_consistent_score_is_kept():
    df, _ = _with_late_logged_row('00:33', 53, 52)       # more time left, no regression
    cg = pg.clean_game(df)
    assert (cg.final_a, cg.final_b) == (53, 52)
    assert len(cg.sc) == 53


def test_minute_resolution_clocks_are_not_dropped():
    df, _ = _with_late_logged_row('01:00', 50, 52, last_clock='01:00')
    cg = pg.clean_game(df)
    assert (cg.final_a, cg.final_b) == (50, 52)           # equal clocks: not provably stale
    assert len(cg.sc) == 53


def _r(value, season, gamecode):
    return {'value': value, 'season': season, 'gamecode': gamecode}


def test_rank_by_ties_cutoff_and_zero_filter():
    recs = [_r(5, 2010, 1), _r(7, 2011, 2), _r(7, 2012, 3), _r(0, 2013, 4), _r(6, 2014, 5)]
    out = pg.rank_by(recs, 'value', limit=2)
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == [(3, 1, True), (2, 1, True)]
    out = pg.rank_by(recs, 'value')
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == \
        [(3, 1, True), (2, 1, True), (5, 3, False), (1, 4, False)]
    assert 'rank' not in recs[0]


def test_finish_rows_and_season_span(tmp_path):
    os.makedirs(tmp_path / '2015')
    (tmp_path / '2015' / '7.json').write_text('{}')
    rows = pg.finish_rows([_r(1, 2015, 7), _r(1, 2016, 8)], str(tmp_path))
    assert [(r['season_label'], r['has_replay']) for r in rows] == \
        [('2015-16', True), ('2016-17', False)]
    assert pg.season_span(rows) == [2015, 2016]
    assert pg.season_span([]) == []


def test_write_json_if_changed_keeps_date_only_when_content_same(tmp_path):
    path = str(tmp_path / 'out' / 'x.json')
    pg.write_json_if_changed(path, {'generated': '2000-01-01', 'v': 1}, ('v',))
    kept = pg.write_json_if_changed(path, {'generated': '2001-01-01', 'v': 1}, ('v',))
    assert kept['generated'] == '2000-01-01'
    changed = pg.write_json_if_changed(path, {'generated': '2002-01-01', 'v': 2}, ('v',))
    assert changed['generated'] == '2002-01-01'
    with open(path, encoding='utf-8') as f:
        assert json.load(f)['generated'] == '2002-01-01'


def test_iter_games_reads_cache_and_skips_missing_season(tmp_path, capsys):
    pd.concat([game(BASIC, gamecode=7), game(BASIC, gamecode=8)]).to_csv(
        tmp_path / 'pbp_2015.csv', index=False)
    games = list(pg.iter_games([2015, 2016], cache_dir=str(tmp_path)))
    assert [g.gamecode for g in games] == [7, 8]
    assert 'pbp_2016.csv missing' in capsys.readouterr().out
