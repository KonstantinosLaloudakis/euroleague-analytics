"""
Lineup Net Ratings — All available seasons.
Computes offensive, defensive, and net rating per 100 possessions
for every 5-man lineup and 2-man pair that meets a minimum possession threshold.

Reads:  data_cache/pbp_lineups_{season}.csv  (all available seasons)
Writes: docs/data/current/lineups.json
"""

import os
import re
import json
import glob
from collections import defaultdict
from itertools import combinations

import pandas as pd

from lineup_utils import extract_stints, order_lineup_cols

CACHE_DIR    = "data_cache"
OUT_FILE     = os.path.join("docs", "data", "current", "lineups.json")
MIN_POSS_5   = 75
MIN_POSS_2   = 150


def load_home_map(season):
    """gamecode -> home team code from data_cache/games_{season}.csv ({} if absent)."""
    path = os.path.join(CACHE_DIR, f"games_{season}.csv")
    if not os.path.exists(path):
        return {}
    gdf = pd.read_csv(path)
    if 'gamenumber' not in gdf.columns or 'homecode' not in gdf.columns:
        return {}
    return dict(zip(gdf['gamenumber'], gdf['homecode']))


def process_season(season):
    path = os.path.join(CACHE_DIR, f"pbp_lineups_{season}.csv")
    df = pd.read_csv(path, low_memory=False)
    print(f"  Season {season}: {len(df):,} rows, {df['Gamecode'].nunique()} games")
    home_map = load_home_map(season)

    fiveman = defaultdict(lambda: {'poss': 0.0, 'pts_for': 0.0, 'pts_against': 0.0, 'games': set()})
    pairs   = defaultdict(lambda: {'poss': 0.0, 'pts_for': 0.0, 'pts_against': 0.0, 'games': set()})

    for gc, game_df in df.groupby('Gamecode'):
        lineup_cols = [c for c in game_df.columns
                       if c.startswith('Lineup_') and game_df[c].notna().any()]
        if len(lineup_cols) != 2:
            continue

        # POINTS_A (home) team first - CSV column order is not home/away
        col_a, col_b = order_lineup_cols(game_df, lineup_cols, home_map.get(gc))
        stints = extract_stints(game_df, col_a, col_b)
        gamecode = int(gc)

        for s in stints:
            # ── 5-man: team A ──
            ka = (s['team_a'], s['lineup_a'])
            fiveman[ka]['poss']       += s['poss']
            fiveman[ka]['pts_for']    += s['pts_a']
            fiveman[ka]['pts_against']+= s['pts_b']
            fiveman[ka]['games'].add(gamecode)

            # ── 5-man: team B ──
            kb = (s['team_b'], s['lineup_b'])
            fiveman[kb]['poss']       += s['poss']
            fiveman[kb]['pts_for']    += s['pts_b']
            fiveman[kb]['pts_against']+= s['pts_a']
            fiveman[kb]['games'].add(gamecode)

            # ── Pairs: team A ──
            for pair in combinations(s['lineup_a'], 2):
                pk = (s['team_a'], tuple(sorted(pair)))
                pairs[pk]['poss']       += s['poss']
                pairs[pk]['pts_for']    += s['pts_a']
                pairs[pk]['pts_against']+= s['pts_b']
                pairs[pk]['games'].add(gamecode)

            # ── Pairs: team B ──
            for pair in combinations(s['lineup_b'], 2):
                pk = (s['team_b'], tuple(sorted(pair)))
                pairs[pk]['poss']       += s['poss']
                pairs[pk]['pts_for']    += s['pts_b']
                pairs[pk]['pts_against']+= s['pts_a']
                pairs[pk]['games'].add(gamecode)

    def to_records(agg, min_poss):
        records = []
        for (team, lineup), d in agg.items():
            # combined poss from extract_stints counts both teams' plays;
            # divide by 2 to get per-team possession estimate
            team_poss = d['poss'] / 2
            if team_poss < min_poss:
                continue
            ortg = d['pts_for']    / team_poss * 100
            drtg = d['pts_against']/ team_poss * 100
            records.append({
                'season': season,
                'team':   team,
                'players': list(lineup),
                'poss':   round(team_poss, 1),
                'ortg':   round(ortg, 1),
                'drtg':   round(drtg, 1),
                'netrtg': round(ortg - drtg, 1),
                'gp':     len(d['games']),
            })
        return records

    return to_records(fiveman, MIN_POSS_5), to_records(pairs, MIN_POSS_2)


def main():
    pattern = os.path.join(CACHE_DIR, "pbp_lineups_*.csv")
    files   = sorted(glob.glob(pattern))

    if not files:
        print(f"No pbp_lineups_*.csv files found in {CACHE_DIR}/")
        return

    all_fiveman, all_pairs, seasons = [], [], []

    for f in files:
        m = re.search(r'pbp_lineups_(\d{4})\.csv$', f)
        if not m:
            continue
        season = int(m.group(1))
        fiveman, pairs = process_season(season)
        all_fiveman.extend(fiveman)
        all_pairs.extend(pairs)
        seasons.append(season)
        print(f"    -> {len(fiveman)} lineups, {len(pairs)} pairs qualifying")

    out = {
        'seasons':  sorted(seasons),
        'fiveman':  all_fiveman,
        'pairs':    all_pairs,
    }

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w') as f:
        json.dump(out, f)

    print(f"\nDone: {len(all_fiveman)} lineups + {len(all_pairs)} pairs "
          f"across {len(seasons)} seasons -> {OUT_FILE}")


if __name__ == '__main__':
    main()
