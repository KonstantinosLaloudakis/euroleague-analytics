"""
Win Probability Added (WPA) Calculator — Current Season
Calculates the True Win Probability at every play-by-play event,
and assigns the delta (change) in WP to the player who made the play.

Uses the ML model from wp_model_utils if available, otherwise falls back
to the analytic formula.
"""

import pandas as pd
import numpy as np
import math

from season_config import CURRENT_SEASON, season_label
from wp_model_utils import predict_wp, get_elo_diff


def calc_wp(margin, seconds_remaining, elo_diff=0.0):
    """Wrapper for backward compatibility. Delegates to ML model or fallback."""
    return predict_wp(margin, seconds_remaining, elo_diff=elo_diff)

def get_seconds(time_str):
    try:
        m, s = map(int, str(time_str).split(':'))
        return m * 60 + s
    except:
        return 0

def calculate_action_wpa():
    print(f"Loading pbp_{CURRENT_SEASON}.csv...")
    df = pd.read_csv(f'pbp_{CURRENT_SEASON}.csv')
    
    # Sort chronologically
    df = df.sort_values(['Gamecode', 'NUMBEROFPLAY']).reset_index(drop=True)
    
    # Forward fill points
    df['POINTS_A'] = df.groupby('Gamecode')['POINTS_A'].ffill().fillna(0)
    df['POINTS_B'] = df.groupby('Gamecode')['POINTS_B'].ffill().fillna(0)
    
    # Calculate Seconds Remaining in the Game
    df['SecRemainingPeriod'] = df['MARKERTIME'].apply(get_seconds)
    
    def calc_game_seconds(row):
        period = row['PERIOD']
        sec_per = row['SecRemainingPeriod']
        if pd.isna(period):
            return 0
        if period <= 4:
            return (4 - period) * 600 + sec_per
        else:
            # Overtime
            ot_num = period - 4
            return max(0, (1 - ot_num) * 300 + sec_per)  # Simplification for 1st OT
            
    df['SecondsRemaining'] = df.apply(calc_game_seconds, axis=1)
    
    # Load per-game Elo diffs (season = first Season value in file)
    season = int(df['Season'].iloc[0]) if 'Season' in df.columns else CURRENT_SEASON
    elo_diff_map = {gc: get_elo_diff(season, gc) for gc in df['Gamecode'].unique()}
    df['EloDiff'] = df['Gamecode'].map(elo_diff_map).fillna(0.0)

    # Determine WP at each row
    df['Margin'] = df['POINTS_A'] - df['POINTS_B']
    df['WP_A'] = df.apply(
        lambda r: calc_wp(r['Margin'], r['SecondsRemaining'], elo_diff=r['EloDiff']), axis=1
    )
    
    # Calculate ΔWP
    # Shift within the game
    df['Prev_WP_A'] = df.groupby('Gamecode')['WP_A'].shift(1).fillna(0.5)
    df['Delta_WP_A'] = df['WP_A'] - df['Prev_WP_A']
    
    # Try to identify which Team Code is Local (Team A)
    # We can do this by looking at who scores POINTS_A
    local_team_codes = {}
    for g, group in df.groupby('Gamecode'):
        # Find first row where POINTS_A > 0 and the play changed POINTS_A
        scored_a = group[group['POINTS_A'] > group['POINTS_A'].shift(1).fillna(0)]
        if not scored_a.empty:
            local_team_codes[g] = scored_a.iloc[0]['CODETEAM']
            
    # Assign WPA
    player_wpa = {}
    
    for _, row in df.iterrows():
        player = row['PLAYER']
        team = row['CODETEAM']
        game = row['Gamecode']
        
        if pd.isna(player) or pd.isna(team):
            continue
            
        local_team = local_team_codes.get(game)
        
        # If team == local_team, this player's WPA is positive when Delta_WP_A is positive
        if team == local_team:
            wpa = row['Delta_WP_A']
        else:
            wpa = -row['Delta_WP_A']
            
        # Give WPA as a percentage point (-100 to 100)
        wpa_pct = wpa * 100
        
        if player not in player_wpa:
            player_wpa[player] = {'Team': team, 'Action_WPA': 0.0, 'Plays': 0}
            
        player_wpa[player]['Action_WPA'] += wpa_pct
        player_wpa[player]['Plays'] += 1
        
    res = []
    for p, d in player_wpa.items():
        if d['Plays'] > 50: # Filter for players with enough tracked actions
            res.append({
                'Player': p,
                'Team': d['Team'],
                'Action_WPA': d['Action_WPA'],
                'Plays': d['Plays']
            })
            
    res_df = pd.DataFrame(res).sort_values('Action_WPA', ascending=False).reset_index(drop=True)
    res_df['WPA_Rank'] = res_df.index + 1
    
    print(f"\n{'='*65}")
    print(f"  ACTION WIN PROBABILITY ADDED (WPA) — Euroleague {season_label()}")
    print(f"{'='*65}")
    print(f"  {'Rank':<4} {'Player':<25} {'Team':<5} {'Total WPA':>10}")
    print(f"  {'-'*55}")
    for _, row in res_df.head(20).iterrows():
        print(f"  {row['WPA_Rank']:<4} {row['Player']:<25} {row['Team']:<5} {row['Action_WPA']:>9.1f}%")
        
    # Save to JSON
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'wpa_ratings{round_suffix}.json'
    res_df.to_json(outfile, orient='records', indent=4)
    print(f"\nSaved Action WPA to {outfile}")

if __name__ == '__main__':
    calculate_action_wpa()
