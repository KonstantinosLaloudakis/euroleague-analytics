"""
True Plus-Minus (TPM) Calculator — Current Season Only
Measures the actual point differential when a player is on the floor,
normalized per 40 minutes, ignoring traditional box score stats.
"""

import json
import pandas as pd
import numpy as np
import os

from season_config import CURRENT_SEASON, season_label

def calculate_tpm():
    with open(f'mvp_all_game_stats_{CURRENT_SEASON}.json', 'r') as f:
        games = json.load(f)
        
    # Load opponent quality adjustments for more advanced TPM later if needed
    adj_net = {}
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'adjusted_ratings{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'adjusted_ratings.json'
    if os.path.exists(in_file):
        with open(in_file, 'r') as f:
            for e in json.load(f):
                adj_net[e['Team']] = e['Adj_Net']
                
    player_data = {}

    for game in games:
        # Skip playoff/play-in games (GameCode > 380) — TPM is a regular-season stat
        gc = game.get('Gamecode', 0)
        if isinstance(gc, float):
            gc = int(gc)
        if gc > 380:
            continue
        for is_local, team_key in [(True, 'local.players'), (False, 'road.players')]:
            players = game.get(team_key, [])
            for p_entry in players:
                stats = p_entry.get('stats', {})
                info = p_entry.get('player', {})
                p_code = info.get('person', {}).get('code')
                
                if not p_code:
                    continue
                    
                p_name = info.get('person', {}).get('name')
                t_code = info.get('club', {}).get('code', 'UNKNOWN')
                
                if p_code not in player_data:
                    player_data[p_code] = {
                        'name': p_name,
                        'team': t_code,
                        'GP': 0,
                        'mins': 0.0,
                        'raw_pm': 0,  # Raw Plus-Minus
                    }
                
                pd_entry = player_data[p_code]
                
                # Parse minutes
                time_played = stats.get('timePlayed', 0.0)
                if not time_played or time_played == 0:
                     continue # DNP
                     
                pd_entry['GP'] += 1
                pd_entry['mins'] += float(time_played) / 60.0
                
                # Raw Plus-Minus 
                pm = stats.get('plusMinus', 0.0)
                pd_entry['raw_pm'] += pm

    # Convert to DataFrame
    rows = []
    for code, d in player_data.items():
        if d['GP'] >= 10 and d['mins'] >= 10: 
            avg_mins = d['mins'] / d['GP']
            if avg_mins >= 10.0: # Minimum 10 minutes per game
                # TPM calculation: Plus-Minus per 40 minutes
                tpm_40 = (d['raw_pm'] / d['mins']) * 40
                
                rows.append({
                    'player.code': code,
                    'player.name': d['name'],
                    'player.team.code': d['team'],
                    'gamesPlayed': d['GP'],
                    'mins_played': avg_mins,
                    'Total_PM': d['raw_pm'],
                    'TPM_40': tpm_40
                })
                
    df = pd.DataFrame(rows)
    print(f"Processed {len(df)} players with >10 GP and >10 MPG")
    if df.empty:
        print(f"No players meet the minimum-games threshold yet - skipping TPM.")
        return
    
    # Sort and rank
    df = df.sort_values('TPM_40', ascending=False).reset_index(drop=True)
    df['TPM_Rank'] = df.index + 1
    
    # === PRINT RESULTS ===
    print(f"\n{'='*75}")
    print(f"  TRUE PLUS-MINUS (TPM) per 40 mins — Euroleague {season_label()}")
    print(f"{'='*75}")
    print(f"  {'Rank':<4} {'Player':<25} {'Team':<5} {'TPM/40':>8} {'Total PM':>8}")
    print(f"  {'-'*65}")
    
    for _, row in df.head(20).iterrows():
        print(f"  {row['TPM_Rank']:<4} {row['player.name']:<25} {row['player.team.code']:<5} "
              f"{row['TPM_40']:>8.1f} {row['Total_PM']:>8.0f}")
              
    # Look at worst TPM
    print(f"\n  --- WORST TPM (Team bleeds points when they play) ---")
    worst = df.tail(5)
    for _, row in worst.iterrows():
         print(f"  {row['TPM_Rank']:<4} {row['player.name']:<25} ({row['player.team.code']}) | TPM/40: {row['TPM_40']:.1f}")

    # Save results
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'tpm_ratings{round_suffix}.json'
    df.to_json(outfile, orient='records', indent=4)
    print(f"\n  Saved full rankings to {outfile}")


if __name__ == '__main__':
    calculate_tpm()
