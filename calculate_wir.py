"""
Weighted Impact Rating (WIR) Calculator — Current Season Only
Replaces Euroleague's flawed PIR metric with an efficiency-adjusted, 
per-minute normalized impact score. Uses local game-by-game data.
"""

import json
import pandas as pd
import numpy as np

from season_config import CURRENT_SEASON, season_label

def calculate_wir():
    with open(f'mvp_all_game_stats_{CURRENT_SEASON}.json', 'r') as f:
        games = json.load(f)
        
    player_data = {}

    for game in games:
        # Skip playoff/play-in games (GameCode > 380) — WIR is a regular-season stat
        gc = game.get('Gamecode', 0)
        if isinstance(gc, float):
            gc = int(gc)
        if gc > 380:
            continue
        for team_key in ['local.players', 'road.players']:
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
                        'pts': 0, 'ast': 0, 'orb': 0, 'drb': 0, 'trb': 0,
                        'stl': 0, 'blk': 0, 'tov': 0,
                        'fga': 0, 'fgm': 0, 'fta': 0, 'ftm': 0,
                        'pir': 0
                    }
                
                pd_entry = player_data[p_code]
                
                # Parse minutes
                time_played = stats.get('timePlayed', 0.0)
                if not time_played or time_played == 0:
                    continue # DNP
                    
                pd_entry['GP'] += 1
                pd_entry['mins'] += float(time_played) / 60.0
                pd_entry['pts'] += stats.get('points', 0)
                pd_entry['ast'] += stats.get('assistances', 0)
                pd_entry['orb'] += stats.get('offensiveRebounds', 0)
                pd_entry['drb'] += stats.get('defensiveRebounds', 0)
                pd_entry['trb'] += stats.get('totalRebounds', 0)
                pd_entry['stl'] += stats.get('steals', 0)
                pd_entry['blk'] += stats.get('blocksFavour', 0)
                pd_entry['tov'] += stats.get('turnovers', 0)
                pd_entry['pir'] += stats.get('valuation', 0)
                
                pd_entry['fga'] += stats.get('fieldGoalsAttemptedTotal', 0)
                pd_entry['fgm'] += stats.get('fieldGoalsMadeTotal', 0)
                pd_entry['fta'] += stats.get('freeThrowsAttempted', 0)
                pd_entry['ftm'] += stats.get('freeThrowsMade', 0)

    # Convert to DataFrame
    rows = []
    for code, d in player_data.items():
        if d['GP'] >= 10 and d['mins'] >= 10: # Minimum 10 games, 10 minutes total (will filter more later)
            avg_mins = d['mins'] / d['GP']
            if avg_mins >= 10.0: # Minimum 10 minutes per game
                rows.append({
                    'player.code': code,
                    'player.name': d['name'],
                    'player.team.code': d['team'],
                    'player.team.name': d['team'],
                    'gamesPlayed': d['GP'],
                    'mins_played': avg_mins,
                    'pointsScored': d['pts'] / d['GP'],
                    'assists': d['ast'] / d['GP'],
                    'offensiveRebounds': d['orb'] / d['GP'],
                    'defensiveRebounds': d['drb'] / d['GP'],
                    'totalRebounds': d['trb'] / d['GP'],
                    'steals': d['stl'] / d['GP'],
                    'blocks': d['blk'] / d['GP'],
                    'turnovers': d['tov'] / d['GP'],
                    'fga': d['fga'] / d['GP'],
                    'fgm': d['fgm'] / d['GP'],
                    'fta': d['fta'] / d['GP'],
                    'ftm': d['ftm'] / d['GP'],
                    'pir': d['pir'] / d['GP']
                })
                
    df = pd.DataFrame(rows)
    print(f"Processed {len(df)} players with >10 GP and >10 MPG")
    if df.empty:
        print("No players meet the minimum-games threshold yet - skipping WIR.")
        return
    
    fg_miss = df['fga'] - df['fgm']
    ft_miss = df['fta'] - df['ftm']
    
    # WIR Formula (Efficiency-weighted)
    df['WIR'] = (
        (df['pointsScored'] * 0.8) + 
        (df['assists'] * 1.5) + 
        (df['offensiveRebounds'] * 1.2) + 
        (df['defensiveRebounds'] * 0.4) + 
        (df['steals'] * 1.8) + 
        (df['blocks'] * 1.2) - 
        (df['turnovers'] * 1.5) - 
        (fg_miss * 0.5) - 
        (ft_miss * 0.5)
    )
    
    # Per 40 minutes normalization
    df['WIR_40'] = (df['WIR'] / df['mins_played']) * 40
    df['PIR_40'] = (df['pir'] / df['mins_played']) * 40
    
    # Calculate True Shooting Percentage for context
    ts_att = df['fga'] + 0.44 * df['fta']
    df['TS%'] = np.where(ts_att > 0, (df['pointsScored'] / (2 * ts_att)) * 100, 0)
    
    # Sort and rank
    df = df.sort_values('WIR_40', ascending=False).reset_index(drop=True)
    df['WIR_Rank'] = df.index + 1
    
    df_pir_sorted = df.sort_values('PIR_40', ascending=False).reset_index(drop=True)
    pir_ranks = {row['player.code']: idx + 1 for idx, row in df_pir_sorted.iterrows()}
    df['PIR_Rank'] = df['player.code'].map(pir_ranks)
    df['Rank_Diff'] = df['PIR_Rank'] - df['WIR_Rank']  # Positive = WIR rates them higher than PIR
    
    # === PRINT RESULTS ===
    print(f"\n{'='*90}")
    print(f"  WEIGHTED IMPACT RATING (WIR) vs PIR per 40 mins — Euroleague {season_label()}")
    print(f"{'='*90}")
    print(f"  {'Rank':<4} {'Player':<20} {'Team':<5} {'WIR/40':>8} {'PIR/40':>8} {'TS%':>6}  {'PIR Rank':>8}  {'Diff':>6}")
    print(f"  {'-'*76}")
    
    for _, row in df.head(15).iterrows():
        diff_str = f"+{row['Rank_Diff']}" if row['Rank_Diff'] > 0 else str(row['Rank_Diff'])
        print(f"  {row['WIR_Rank']:<4} {row['player.name']:<20} {row['player.team.code']:<5} "
              f"{row['WIR_40']:>8.1f} {row['PIR_40']:>8.1f} {row['TS%']:>5.1f}%  #{int(row['PIR_Rank']):<7} {diff_str:>6}")
    
    print(f"\n  --- BIGGEST RISERS (Overlooked by PIR, loved by WIR) ---")
    risers = df.sort_values('Rank_Diff', ascending=False).head(5)
    for _, row in risers.iterrows():
        print(f"  {row['player.name']:<20} ({row['player.team.code']}) | WIR Rank: #{int(row['WIR_Rank'])} | PIR Rank: #{int(row['PIR_Rank'])} | WIR/40: {row['WIR_40']:.1f}")

    print(f"\n  --- BIGGEST FALLERS (Overrated by PIR volume/inefficiency) ---")
    fallers = df.sort_values('Rank_Diff', ascending=True).head(5)
    for _, row in fallers.iterrows():
        print(f"  {row['player.name']:<20} ({row['player.team.code']}) | WIR Rank: #{int(row['WIR_Rank'])} | PIR Rank: #{int(row['PIR_Rank'])} | WIR/40: {row['WIR_40']:.1f}")
        
    # Save results
    cols_to_save = ['player.code', 'player.name', 'player.team.name', 'player.team.code', 'gamesPlayed', 'mins_played', 
                    'pointsScored', 'assists', 'totalRebounds', 'TS%', 
                    'pir', 'PIR_40', 'WIR', 'WIR_40', 'WIR_Rank', 'PIR_Rank', 'Rank_Diff']
    
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'wir_ratings{round_suffix}.json'
    df[cols_to_save].to_json(outfile, orient='records', indent=4)
    print(f"\n  Saved full rankings to {outfile}")


if __name__ == '__main__':
    calculate_wir()
