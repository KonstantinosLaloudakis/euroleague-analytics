"""Backtest the season Monte Carlo (Top 4 / 6 / 10 odds) on completed seasons.

For each round-robin season with complete play-by-play, rebuild the table at
checkpoint rounds, simulate the rest with the production model, and score the
probabilities against the real final standings. Exit code 1 if the model is
miscalibrated. Run: .venv/Scripts/python.exe backtest_monte_carlo.py
"""
import json
import sys

import numpy as np
import pandas as pd

from calculate_elo import STARTING_ELO, _load_prior_season_elos
from season_config import COMPLETED_SEASONS
from simulate_monte_carlo import ELO_PER_POINT, simulate_season

FIRST_ROUND_ROBIN = 2016   # single-table regular season from 2016-17 on
CHECKPOINTS = (4, 8, 12, 20)
CUTOFFS = (4, 6, 10)
N_SIMS = 4000
BINS = [0, .02, .1, .3, .5, .7, .9, .98, 1.001]


def load_games(season, game_meta):
    """[(round, home, away, home_pts, away_pts)] for the regular season."""
    pbp = pd.read_csv(f'data_cache/pbp_{season}.csv', low_memory=False,
                      usecols=['Phase', 'Round', 'Gamecode', 'POINTS_A', 'POINTS_B'])
    pbp = pbp[pbp.Phase == 'RS']
    g = pbp.groupby('Gamecode').agg(rnd=('Round', 'first'), a=('POINTS_A', 'max'),
                                    b=('POINTS_B', 'max')).reset_index()
    games = []
    for _, r in g.iterrows():
        meta = game_meta.get(f'{season}_{int(r.Gamecode)}')
        if meta and r.a == r.a and r.b == r.b:
            games.append((int(r.rnd), meta['home'], meta['away'], int(r.a), int(r.b)))
    return games


def final_ranks(n, played):
    ranks, _ = simulate_season(n, played, [], np.zeros(n), 1, np.random.default_rng(0))
    return ranks[0]


def score(p, t):
    q = np.clip(p, 1e-3, 1 - 1e-3)
    return float(np.mean(-(t * np.log(q) + (1 - t) * np.log(1 - q))))


def main():
    game_meta = json.load(open('data_cache/game_elos.json'))
    P, T = [], []
    for season in COMPLETED_SEASONS:
        if season < FIRST_ROUND_ROBIN:
            continue
        games = load_games(season, game_meta)
        teams = sorted({t for _, h, a, _, _ in games for t in (h, a)})
        n = len(teams)
        if len(games) < 0.98 * n * (n - 1):   # cancelled / withdrawals / incomplete cache
            print(f'{season}: skipped ({len(games)} of {n * (n - 1)} games)')
            continue
        idx = {t: i for i, t in enumerate(teams)}
        allg = [(r, idx[h], idx[a], hp, ap) for r, h, a, hp, ap in games]
        truth = final_ranks(n, [(h, a, hp, ap) for _, h, a, hp, ap in allg])
        prior_elos = _load_prior_season_elos(season)
        prior = np.array([(prior_elos.get(t, STARTING_ELO) - STARTING_ELO) / ELO_PER_POINT
                          for t in teams])
        for R in CHECKPOINTS:
            played = [(h, a, hp, ap) for r, h, a, hp, ap in allg if r <= R]
            remaining = [(h, a) for r, h, a, _, _ in allg if r > R]
            ranks, _ = simulate_season(n, played, remaining, prior, N_SIMS,
                                       np.random.default_rng(season * 100 + R))
            for c in CUTOFFS:
                P.extend((ranks < c).mean(axis=0))
                T.extend((truth < c).astype(float))
        print(f'{season}: {n} teams, {len(games)} games done')

    P, T = np.array(P), np.array(T)
    ll = score(P, T)
    extreme = (P >= .95) | (P <= .05)
    wrong = ((P >= .95) & (T == 0)) | ((P <= .05) & (T == 1))
    print(f'\nPredictions: {len(P)}  log loss {ll:.4f}  '
          f'wrong at extremes {wrong.sum()}/{extreme.sum()}')
    ok = ll <= 0.385 and wrong.sum() <= 0.03 * max(extreme.sum(), 1)
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = (P >= lo) & (P < hi)
        if not m.sum():
            continue
        gap = abs(P[m].mean() - T[m].mean())
        flag = '' if (m.sum() < 50 or gap <= 0.05) else '  <-- miscalibrated'
        ok = ok and not flag
        print(f'  {lo:.2f}-{min(hi, 1):.2f}: predicted {P[m].mean():.3f}  '
              f'actual {T[m].mean():.3f}  (n={m.sum()}){flag}')
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
