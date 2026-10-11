import pandas as pd
import json
import numpy as np
import os
from season_config import CURRENT_SEASON


def z_normalize(series, clip=3.0):
    """
    Z-score normalization clipped at ±clip, then scaled to 0-100.
    More robust than min-max: a single outlier won't compress everyone else.
    """
    std = series.std()
    if std == 0:
        return pd.Series(50.0, index=series.index)
    z = (series - series.mean()) / std
    return (z.clip(-clip, clip) + clip) / (2 * clip) * 100


def calculate_mvp_scores():
    # 1. Load Data
    try:
        df_games = pd.read_json('mvp_parsed_games.json')
        with open('mvp_standings_derived.json', 'r') as f:
            standings = json.load(f)
        with open(f'clutch_stats_{CURRENT_SEASON}_{CURRENT_SEASON}.json', 'r') as f:
            clutch_data = json.load(f)
            df_clutch = pd.DataFrame(clutch_data.get(str(CURRENT_SEASON), []))
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    print(f"Loaded {len(df_games)} player-games.")

    # Determine primary team per player (mode across all games — handles mid-season transfers)
    primary_team = (
        df_games.groupby(['PlayerCode', 'PlayerName'])['TeamCode']
        .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else 'UNKNOWN')
        .rename('PrimaryTeam')
        .reset_index()
    )
    df_games = pd.merge(df_games, primary_team[['PlayerCode', 'PrimaryTeam']], on='PlayerCode', how='left')

    # 2. Per-player season aggregates — PIR as primary metric (official Euroleague stat)
    player_stats = (
        df_games.groupby(['PlayerCode', 'PlayerName', 'PrimaryTeam'])
        .agg(
            GP      = ('GameCode', 'count'),
            AvgPIR  = ('PIR',      'mean'),
            StdPIR  = ('PIR',      'std'),
            AvgGmSc = ('GmSc',     'mean'),
            AvgPTS  = ('PTS',      'mean'),
        )
        .reset_index()
        .rename(columns={'PrimaryTeam': 'TeamCode'})
    )
    player_stats['StdPIR'] = player_stats['StdPIR'].fillna(0)

    # Minimum sample filter
    player_stats = player_stats[player_stats['GP'] >= 5].copy()

    # 3. Consistency — inverse coefficient of variation
    #    Higher = more reliable night-to-night performer
    player_stats['CV'] = player_stats['StdPIR'] / player_stats['AvgPIR'].clip(lower=0.1)
    player_stats['Consistency'] = 1.0 / (1.0 + player_stats['CV'])

    # 4. Team strength — continuous function of win% (no discrete step function)
    standings_map = {k: v['WinPct'] for k, v in standings.items()}
    player_stats['TeamWinPct'] = player_stats['TeamCode'].map(standings_map).fillna(0)

    # 5. WPA — Win Probability Added (season cumulative, from wpa_ratings.json)
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    wpa_file = f'wpa_ratings{round_suffix}.json'
    if not os.path.exists(wpa_file):
        wpa_file = 'wpa_ratings.json'

    wpa_lookup = {}
    if os.path.exists(wpa_file):
        with open(wpa_file) as f:
            wpa_data = json.load(f)
        for entry in wpa_data:
            wpa_lookup[entry['Player'].upper().strip()] = entry.get('Action_WPA', 0.0)
        print(f"Loaded WPA for {len(wpa_lookup)} players.")
    else:
        print("Warning: wpa_ratings.json not found — WPA factor set to 0.")

    player_stats['PlayerUpper'] = player_stats['PlayerName'].str.upper().str.strip()
    player_stats['WPA'] = player_stats['PlayerUpper'].map(wpa_lookup).fillna(0)

    # 6. Clutch True Shooting efficiency
    #    ClutchTS% = ClutchPTS / (2 * (ClutchFGA + 0.44 * ClutchFTA))
    #    Multiplied by per-game clutch scoring to blend volume + efficiency
    df_clutch['PlayerUpper'] = df_clutch['Player'].str.upper().str.strip()
    merged = pd.merge(
        player_stats,
        df_clutch[['PlayerUpper', 'ClutchPoints', 'ClutchFGM', 'ClutchFGA', 'ClutchFTM', 'ClutchFTA']],
        on='PlayerUpper', how='left'
    )
    for col in ['ClutchPoints', 'ClutchFGM', 'ClutchFGA', 'ClutchFTM', 'ClutchFTA']:
        merged[col] = merged[col].fillna(0)

    merged['ClutchPPG'] = merged['ClutchPoints'] / merged['GP']
    denom = 2 * (merged['ClutchFGA'] + 0.44 * merged['ClutchFTA'])
    merged['ClutchTS'] = np.where(denom > 0, merged['ClutchPoints'] / denom, 0.0).clip(0, 1)
    # ClutchEff = per-game clutch output weighted by shooting efficiency
    merged['ClutchEff'] = merged['ClutchPPG'] * merged['ClutchTS']

    # 7. Normalize all components with z-score (robust to outliers)
    merged['PIR_Norm']     = z_normalize(merged['AvgPIR'])
    merged['WPA_Norm']     = z_normalize(merged['WPA'])
    merged['Team_Norm']    = z_normalize(merged['TeamWinPct'])
    merged['Clutch_Norm']  = z_normalize(merged['ClutchEff'])
    merged['Consist_Norm'] = z_normalize(merged['Consistency'])

    # 8. Final MVP Score
    #   PIR        45% — official Euroleague performance metric
    #   WPA        25% — actual causal impact on winning outcomes
    #   Team       15% — credit for playing on a winning team
    #   Clutch     10% — performance in high-leverage moments (volume × TS%)
    #   Consistency 5% — reliability bonus for consistent contributors
    merged['MVP_Score'] = (
        merged['PIR_Norm']     * 0.45 +
        merged['WPA_Norm']     * 0.25 +
        merged['Team_Norm']    * 0.15 +
        merged['Clutch_Norm']  * 0.10 +
        merged['Consist_Norm'] * 0.05
    )

    merged.sort_values('MVP_Score', ascending=False, inplace=True)
    merged['MVP_Rank'] = range(1, len(merged) + 1)

    # Print leaderboard
    print(f"\n{'='*75}")
    print(f"  MVP LADDER — TOP 20")
    print(f"{'='*75}")
    print(f"  {'#':<4} {'Player':<25} {'Tm':<5} {'Score':>6} {'AvgPIR':>7} {'WPA':>8} {'WinPct':>7} {'Clutch':>7}")
    print(f"  {'-'*70}")
    for _, row in merged.head(20).iterrows():
        print(
            f"  {int(row['MVP_Rank']):<4} {row['PlayerName']:<25} {row['TeamCode']:<5}"
            f" {row['MVP_Score']:>6.1f} {row['AvgPIR']:>7.1f} {row['WPA']:>8.1f}"
            f" {row['TeamWinPct']:>7.1%} {row['ClutchEff']:>7.2f}"
        )

    # Save
    final_cols = [
        'MVP_Rank', 'PlayerName', 'TeamCode', 'MVP_Score',
        'AvgPIR', 'AvgGmSc', 'WPA', 'TeamWinPct', 'ClutchPoints', 'ClutchEff', 'Consistency', 'GP'
    ]
    outfile = f'mvp_rankings_{CURRENT_SEASON}{round_suffix}.json'
    merged[final_cols].to_json(outfile, orient='records', indent=4)
    print(f"\nSaved {outfile}")


if __name__ == "__main__":
    calculate_mvp_scores()
