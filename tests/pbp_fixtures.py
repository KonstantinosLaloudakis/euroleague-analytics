"""Made-up play-by-play builders shared by the game-records tests."""
import numpy as np
import pandas as pd

TEAM = {'A': 'HOM', 'B': 'AWY'}
SHOT_POINTS = {'2FGM': 2, 'DUNK': 2, 'LAYUPMD': 2, '3FGM': 3, 'FTM': 1}


def _begin_row(season, phase, rnd, gamecode):
    return {'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
            'NUMBEROFPLAY': 0, 'TRUE_NUMBEROFPLAY': 0, 'CODETEAM': np.nan,
            'TEAM': np.nan, 'PLAYTYPE': 'BP', 'POINTS_A': np.nan, 'POINTS_B': np.nan,
            'PERIOD': 1, 'MARKERTIME': np.nan}


def game(legs, season=2015, gamecode=7, phase='RS', rnd=3, true_numbers=True):
    """Build a PBP DataFrame. legs: (side, baskets, points_each, period, clock).

    Side 'A' is the home team (code HOM), 'B' the away team (code AWY).
    A non-scoring 'Begin Period' row comes first, as in the real feed.
    """
    rows = [_begin_row(season, phase, rnd, gamecode)]
    a = b = 0
    for side, n, pts, period, clock in legs:
        for _ in range(n):
            if side == 'A':
                a += pts
            else:
                b += pts
            code = TEAM[side]
            rows.append({'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
                         'NUMBEROFPLAY': len(rows), 'TRUE_NUMBEROFPLAY': len(rows),
                         'CODETEAM': code, 'TEAM': f'{code} Club', 'PLAYTYPE': '2FGM',
                         'POINTS_A': a, 'POINTS_B': b, 'PERIOD': period, 'MARKERTIME': clock})
    df = pd.DataFrame(rows)
    if not true_numbers:
        df = df.drop(columns='TRUE_NUMBEROFPLAY')
    return df


# Away team trails 0-20 in Q1, wins 52-50 (last basket: Q4 0:10, breaking a 50-50 tie).
BASIC = [('A', 10, 2, 1, '05:00'), ('B', 25, 2, 2, '05:00'),
         ('A', 15, 2, 3, '05:00'), ('B', 1, 2, 4, '00:10')]


def ev(side, pt, period=1, clock='05:00', player=None, name=None, n=1):
    """n identical event specs for build(). Scoring play types add their points."""
    return [(side, pt, period, clock, player, name)] * n


def build(events, season=2015, gamecode=7, phase='RS', rnd=3):
    """Build PBP from ev() specs. Scoring rows carry POINTS_A/B; other events
    leave them NaN, as in the real feed."""
    first = _begin_row(season, phase, rnd, gamecode)
    first.update({'PLAYER_ID': np.nan, 'PLAYER': np.nan})
    rows = [first]
    a = b = 0
    for side, pt, period, clock, player, name in events:
        pts = SHOT_POINTS.get(pt.strip(), 0)
        if side == 'A':
            a += pts
        else:
            b += pts
        code = TEAM[side]
        rows.append({'Season': season, 'Phase': phase, 'Round': rnd, 'Gamecode': gamecode,
                     'NUMBEROFPLAY': len(rows), 'TRUE_NUMBEROFPLAY': len(rows),
                     'CODETEAM': code, 'TEAM': f'{code} Club', 'PLAYTYPE': pt,
                     'PLAYER_ID': np.nan if player is None else player,
                     'PLAYER': np.nan if name is None else name,
                     'POINTS_A': a if pts else np.nan, 'POINTS_B': b if pts else np.nan,
                     'PERIOD': period, 'MARKERTIME': clock})
    return pd.DataFrame(rows)


def filler(a_baskets, b_baskets, period=2):
    """Anonymous 2FGM baskets: all of A's first, then all of B's."""
    return ev('A', '2FGM', period, n=a_baskets) + ev('B', '2FGM', period, n=b_baskets)
