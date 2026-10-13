"""Tests for calculate_comebacks.py (made-up play-by-play)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import calculate_comebacks as cb


def game(legs, season=2015, gamecode=7, phase='RS', rnd=3, true_numbers=True):
    """Build a PBP DataFrame. legs: (side, baskets, points_each, period, clock).

    Side 'A' is the home team (code HOM), 'B' the away team (code AWY).
    A non-scoring 'Begin Period' row comes first, as in the real feed.
    """
    rows = [{'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
             'NUMBEROFPLAY': 0, 'TRUE_NUMBEROFPLAY': 0, 'CODETEAM': np.nan,
             'TEAM': np.nan, 'PLAYTYPE': 'BP', 'POINTS_A': np.nan, 'POINTS_B': np.nan,
             'PERIOD': 1, 'MARKERTIME': np.nan}]
    a = b = 0
    for side, n, pts, period, clock in legs:
        for _ in range(n):
            if side == 'A':
                a += pts
            else:
                b += pts
            code = 'HOM' if side == 'A' else 'AWY'
            rows.append({'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
                         'NUMBEROFPLAY': len(rows), 'TRUE_NUMBEROFPLAY': len(rows),
                         'CODETEAM': code, 'TEAM': f'{code} Club', 'PLAYTYPE': '2FGM',
                         'POINTS_A': a, 'POINTS_B': b, 'PERIOD': period, 'MARKERTIME': clock})
    df = pd.DataFrame(rows)
    if not true_numbers:
        df = df.drop(columns='TRUE_NUMBEROFPLAY')
    return df


# Away team trails 0-20 in Q1, wins 52-50.
BASIC = [('A', 10, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00'),
         ('A', 15, 2, 3, '05:00'), ('B', 1, 2, 4, '00:10')]


def test_basic_comeback():
    r = cb.analyze_game(game(BASIC))
    assert r['deficit'] == 20
    assert r['trailing'] == '0-20'
    assert (r['quarter'], r['clock']) == (1, '05:00')
    assert (r['winner'], r['winner_name'], r['loser'], r['loser_name']) == \
        ('AWY', 'AWY Club', 'HOM', 'HOM Club')
    assert r['home'] is False
    assert r['final'] == '52-50'
    assert r['ot'] is False
    assert (r['season'], r['phase'], r['round'], r['gamecode']) == (2015, 'RS', 3, 7)
    assert r['q4'] == {'deficit': 0, 'trailing': None, 'quarter': None, 'clock': None}


def test_wire_to_wire_winner_has_zero_deficit():
    r = cb.analyze_game(game([('A', 30, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00')]))
    assert r['deficit'] == 0
    assert r['trailing'] is None
    assert r['winner'] == 'HOM' and r['home'] is True


def test_unscored_side_counts_as_zero():
    df = game(BASIC)
    df.loc[df['POINTS_B'] == 0, 'POINTS_B'] = np.nan
    r = cb.analyze_game(df)
    assert r['deficit'] == 20
    assert r['trailing'] == '0-20'


def test_single_row_score_spike_is_ignored():
    df = game(BASIC)
    # row 30 is mid-way through B's run (A=20, B=40); a typo puts A at 80
    df.loc[30, 'POINTS_A'] = 80
    r = cb.analyze_game(df)
    assert r['deficit'] == 20


def test_fourth_quarter_deficit_only_uses_q4_and_ot():
    legs = [('A', 10, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00'),
            ('A', 18, 2, 4, '03:00'), ('B', 4, 2, 4, '00:30')]
    r = cb.analyze_game(game(legs))
    assert r['final'] == '58-56'
    assert r['deficit'] == 20
    assert r['q4'] == {'deficit': 6, 'trailing': '50-56', 'quarter': 4, 'clock': '03:00'}


def test_overtime_flag():
    legs = BASIC[:3] + [('B', 1, 2, 5, '00:10')]
    assert cb.analyze_game(game(legs))['ot'] is True


def test_final_under_45_is_skipped():
    assert cb.analyze_game(game([('A', 20, 1, 1, '05:00'), ('B', 15, 2, 2, '05:00')])) is None


def test_too_few_scoring_rows_is_skipped():
    assert cb.analyze_game(game([('A', 15, 4, 1, '05:00'), ('B', 10, 5, 2, '05:00')])) is None


def test_tied_final_is_skipped():
    assert cb.analyze_game(game([('A', 25, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00')])) is None


def test_falls_back_to_numberofplay():
    r = cb.analyze_game(game(BASIC, true_numbers=False))
    assert r['deficit'] == 20


def test_missing_phase_and_odd_round():
    r = cb.analyze_game(game(BASIC, phase=None, rnd='Final'))
    assert r['phase'] is None
    assert r['round'] is None
    assert r['deficit'] == 20


def test_missing_clock_is_none():
    legs = [('A', 10, 2, 1, np.nan)] + BASIC[1:]
    r = cb.analyze_game(game(legs))
    assert r['deficit'] == 20
    assert r['clock'] is None


def _rec(deficit, season, gamecode, phase='RS', q4_deficit=0):
    return {'season': season, 'phase': phase, 'round': 3, 'gamecode': gamecode,
            'winner': 'AWY', 'winner_name': 'AWY Club', 'loser': 'HOM', 'loser_name': 'HOM Club',
            'home': False, 'deficit': deficit, 'trailing': f'0-{deficit}', 'quarter': 2,
            'clock': '05:00',
            'q4': {'deficit': q4_deficit,
                   'trailing': f'1-{q4_deficit + 1}' if q4_deficit else None,
                   'quarter': 4 if q4_deficit else None,
                   'clock': '02:00' if q4_deficit else None},
            'final': '80-78', 'ot': False}


def test_rank_entries_ties_share_rank_newest_first():
    recs = [_rec(27, 2019, 5), _rec(28, 2012, 113), _rec(28, 2016, 45), _rec(0, 2010, 1)]
    out = cb.rank_entries(recs)
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == \
        [(45, 1, True), (113, 1, True), (5, 3, False)]
    assert 'rank' not in recs[0]          # inputs are not mutated


def test_tie_at_cutoff_still_flagged():
    recs = [_rec(28, 2012, 1), _rec(28, 2013, 2), _rec(28, 2014, 3), _rec(27, 2015, 4)]
    out = cb.rank_entries(recs, limit=2)
    assert [(r['gamecode'], r['rank'], r['tied']) for r in out] == [(3, 1, True), (2, 1, True)]


def test_build_output(tmp_path):
    os.makedirs(tmp_path / '2015')
    (tmp_path / '2015' / '113.json').write_text('{}')
    recs = [_rec(20, 2015, 113, q4_deficit=8), _rec(15, 2016, 9, phase='FF'),
            _rec(10, 2017, 4, phase='PO', q4_deficit=12)]
    out = cb.build_output(recs, current_season=2017, replay_dir=str(tmp_path),
                          generated='2000-01-01')
    assert out['generated'] == '2000-01-01'
    assert out['seasons'] == [2015, 2017]
    assert out['current_season'] == 2017
    assert out['games_scanned'] == 3
    assert [r['gamecode'] for r in out['overall']] == [113, 9, 4]
    assert out['overall'][0]['has_replay'] is True
    assert out['overall'][1]['has_replay'] is False
    assert out['overall'][0]['season_label'] == '2015-16'
    assert 'q4' not in out['overall'][0]
    q4 = out['fourth_quarter']
    assert [r['gamecode'] for r in q4] == [4, 113]
    assert (q4[0]['deficit'], q4[0]['trailing'], q4[0]['quarter']) == (12, '1-13', 4)
    assert [r['gamecode'] for r in out['postseason']] == [9, 4]
