import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from euroleague_api.play_by_play_data import PlayByPlay
import os
import time

import fetch_lineups
from season_config import CURRENT_SEASON

# --- Configuration ---
START_SEASON = CURRENT_SEASON
END_SEASON = CURRENT_SEASON
MIN_MINUTES_5MAN = 50
MIN_MINUTES_2MAN = 150
MIN_MINUTES_ANCHOR = 150
CACHE_DIR = "data_cache"

os.makedirs(CACHE_DIR, exist_ok=True)

def fetch_pbp_with_lineups(season):
    """Fetches PBP data with lineups for a season (delegates to fetch_lineups)."""
    return fetch_lineups.fetch_lineups(season)

def process_time_str(t_str):
    """Converts MM:SS string to seconds."""
    if not isinstance(t_str, str):
        return 0
    try:
        parts = t_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except:
        return 0

def analyze_lineups(df_season):
    """
    Analyzes Lineups (5-man), Dynamic Duos (2-man), and Anchors (On/Off).
    """
    # Verify columns
    stats_5man = {}
    stats_2man = {}
    stats_anchor = {}
    
    # Pre-process Time
    if 'MARKERTIME' in df_season.columns:
         df_season['Time'] = df_season['MARKERTIME']
         
    if 'Time' not in df_season.columns:
        print("Error: 'Time' (or MARKERTIME) column missing.")
        return {}, {}, {}
        
    df_season['Seconds'] = df_season['Time'].apply(process_time_str)
    
    # Group by Game
    games = df_season.groupby('GameCode')
    
    valid_games = 0
    
    for gcode, game_df in games:
        # Sort by Period and Time Descending
        game_df = game_df.sort_values(by=['PERIOD', 'Seconds'], ascending=[True, False]).copy()
        
        # Fill Points
        cols_map = {c.upper(): c for c in game_df.columns}
        p_a_col = cols_map.get('POINTS_A')
        p_b_col = cols_map.get('POINTS_B')
        
        if p_a_col: game_df['PA_Fill'] = game_df[p_a_col].ffill().fillna(0)
        else: game_df['PA_Fill'] = 0
        
        if p_b_col: game_df['PB_Fill'] = game_df[p_b_col].ffill().fillna(0)
        else: game_df['PB_Fill'] = 0

        # Build Player -> Team Map for validation
        valid_player_map = {}
        if 'PLAYER' in game_df.columns and 'CODETEAM' in game_df.columns:
            temp_map = game_df[['PLAYER', 'CODETEAM']].dropna().drop_duplicates()
            valid_player_map = dict(zip(temp_map['PLAYER'], temp_map['CODETEAM']))
        else:
            print(f"DEBUG: Missing columns for map. Found: {game_df.columns}")
            
        # Whitelist for Euroleague 2025 Teams
        EL_TEAMS_2025 = {
            'ber', 'ist', 'mco', 'bas', 'red', 'mil', 'bar', 'mun', 'ulk', 'asv', 
            'tel', 'oly', 'pan', 'prs', 'par', 'mad', 'vir', 'zal'
        }
        EL_TEAMS_SET = {t.upper() for t in EL_TEAMS_2025}
        
        # Explicit Blacklist for known data ghosts
        GHOST_PLAYERS = {
            "KURUCS, RODIONS", "SIMMONS, KOBI" 
        }
        
        # Determine Teams based on lineup columns
        all_lineup_cols = [c for c in game_df.columns if 'Lineup_' in c]
        lineup_cols = [c for c in all_lineup_cols if game_df[c].notna().any()]
        
        if len(lineup_cols) != 2:
            continue
            
        team_a_code = lineup_cols[0].replace('Lineup_', '')
        team_b_code = lineup_cols[1].replace('Lineup_', '')
        
        # FILTER: Strict Euroleague Only
        if START_SEASON >= 2025:
             if team_a_code not in EL_TEAMS_SET or team_b_code not in EL_TEAMS_SET:
                 continue
                 
        if gcode % 10 == 0:
            print(f"Processing game {gcode}: {team_a_code} vs {team_b_code}")
            
        # DATA INTEGRITY CHECK
        # DATA INTEGRITY CHECK
        # Ensure scores are numeric and handle NaNs
        game_df['PA_Fill'] = pd.to_numeric(game_df['PA_Fill'], errors='coerce').fillna(0)
        game_df['PB_Fill'] = pd.to_numeric(game_df['PB_Fill'], errors='coerce').fillna(0)
        
        # Enforce monotonicity to prevent score dipping (0 -> 90 -> 0)
        game_df['PA_Fill'] = game_df['PA_Fill'].cummax()
        game_df['PB_Fill'] = game_df['PB_Fill'].cummax()
        
        max_pa = game_df['PA_Fill'].max()
        max_pb = game_df['PB_Fill'].max()
        
        if max_pa > 250 or max_pb > 250 or max_pa < 10 or max_pb < 10:
            print(f"Skipping Game {gcode} due to score anomaly: {max_pa}-{max_pb}")
            continue
            
        # 2. Check for NaN saturation (already filled, but check raw)
        if game_df[lineup_cols[0]].isna().mean() > 0.5:
             print(f"Skipping Game {gcode} due to missing lineup data.")
             continue
        def is_valid_lineup(players, expected_team_code):
            if len(players) != 5: return False
            for p in players:
                p_clean = p.strip()
                if p_clean in valid_player_map:
                    if valid_player_map[p_clean] != expected_team_code:
                        return False
            return True

        # Build Roster for this game for Anchor analysis
        roster_a = set()
        roster_b = set()
        
        def extract_players(val):
            if isinstance(val, list): return val
            if isinstance(val, str):
                try:
                    import ast
                    p_list = ast.literal_eval(val)
                    # Filter ghosts
                    return [p for p in p_list if p not in GHOST_PLAYERS]
                except:
                    return []
            return []
            
        for val in game_df[lineup_cols[0]].unique():
            ps = extract_players(val)
            if is_valid_lineup(ps, team_a_code):
                roster_a.update(ps)
        for val in game_df[lineup_cols[1]].unique():
            ps = extract_players(val)
            if is_valid_lineup(ps, team_b_code):
                roster_b.update(ps)
            
        # Helper to update stats
        def update_stats_dict(players, duration, pf, pa, stats_dict, fga=0, fta=0, orb=0, tov=0):
            if not players: return
            if isinstance(players, list):
                players = tuple(sorted(players))
            
            if players not in stats_dict:
                stats_dict[players] = {
                    'Minutes': 0, 'PF': 0, 'PA': 0,
                    'FGA': 0, 'FTA': 0, 'ORB': 0, 'TOV': 0
                }
            
            stats_dict[players]['Minutes'] += duration / 60
            stats_dict[players]['PF'] += pf
            stats_dict[players]['PA'] += pa
            stats_dict[players]['FGA'] += fga
            stats_dict[players]['FTA'] += fta
            stats_dict[players]['ORB'] += orb
            stats_dict[players]['TOV'] += tov
            
        def update_anchor_stats(on_players, off_players, duration, pf, pa, stats_dict, fga=0, fta=0, orb=0, tov=0):
            # Update ON players
            for p in on_players:
                if p not in stats_dict:
                    stats_dict[p] = {
                        'On_Min': 0, 'On_PF': 0, 'On_PA': 0,
                        'Off_Min': 0, 'Off_PF': 0, 'Off_PA': 0
                    }
                stats_dict[p]['On_Min'] += (duration / 60)
                stats_dict[p]['On_PF'] += pf
                stats_dict[p]['On_PA'] += pa
                
            # Update OFF players
            for p in off_players:
                if p not in stats_dict:
                    stats_dict[p] = {
                        'On_Min': 0, 'On_PF': 0, 'On_PA': 0,
                        'Off_Min': 0, 'Off_PF': 0, 'Off_PA': 0
                    }
                stats_dict[p]['Off_Min'] += (duration / 60)
                stats_dict[p]['Off_PF'] += pf
                stats_dict[p]['Off_PA'] += pa

        # Global score tracker for game
        current_score_a = 0
        current_score_b = 0
        
        for period in sorted(game_df['PERIOD'].unique()):
            period_df = game_df[game_df['PERIOD'] == period]
            prev_time = 600 if period <= 4 else 300
            
            from itertools import combinations

            def get_lineup(row, col_name):
                return sorted(extract_players(row.get(col_name)))

            for idx, row in period_df.iterrows():
                curr_time = row['Seconds']
                duration = prev_time - curr_time
                if duration < 0: duration = 0
                    
                new_score_a = row['PA_Fill']
                new_score_b = row['PB_Fill']
                score_diff_a = max(0, new_score_a - current_score_a)
                score_diff_b = max(0, new_score_b - current_score_b)
                current_score_a = new_score_a
                current_score_b = new_score_b
                
                lineup_a_list = get_lineup(row, f'Lineup_{team_a_code}')
                lineup_b_list = get_lineup(row, f'Lineup_{team_b_code}')
                
                valid_a = is_valid_lineup(lineup_a_list, team_a_code)
                valid_b = is_valid_lineup(lineup_b_list, team_b_code)
                lineup_a = tuple(sorted(lineup_a_list))
                lineup_b = tuple(sorted(lineup_b_list))
                
                # Parse Play Type for Possessions
                play_type = row['PLAYTYPE'].strip() if isinstance(row['PLAYTYPE'], str) else ''
                code_team = row['CODETEAM'].strip() if isinstance(row['CODETEAM'], str) else ''
                
                fga_a, fta_a, orb_a, tov_a = 0, 0, 0, 0
                fga_b, fta_b, orb_b, tov_b = 0, 0, 0, 0
                
                is_fga = play_type in ['2FGM', '2FGA', '3FGM', '3FGA']
                is_fta = play_type in ['FTM', 'FTA']
                is_orb = play_type == 'O'
                is_tov = play_type in ['TO', 'BP', 'OF']
                
                if code_team == team_a_code:
                     if is_fga: fga_a = 1
                     elif is_fta: fta_a = 1
                     elif is_orb: orb_a = 1
                     elif is_tov: tov_a = 1
                elif code_team == team_b_code:
                     if is_fga: fga_b = 1
                     elif is_fta: fta_b = 1
                     elif is_orb: orb_b = 1
                     elif is_tov: tov_b = 1
                
                # Update Stats
                if score_diff_a > 0:
                    if valid_a: update_stats_dict(lineup_a, duration, score_diff_a, 0, stats_5man, fga_a, fta_a, orb_a, tov_a)
                    if valid_b: update_stats_dict(lineup_b, duration, 0, score_diff_a, stats_5man, fga_b, fta_b, orb_b, tov_b)
                    
                    if valid_a:
                        for pair in combinations(lineup_a, 2):
                             update_stats_dict(tuple(sorted(pair)), duration, score_diff_a, 0, stats_2man, fga_a, fta_a, orb_a, tov_a)
                    if valid_b:
                        for pair in combinations(lineup_b, 2):
                             update_stats_dict(tuple(sorted(pair)), duration, 0, score_diff_a, stats_2man, fga_b, fta_b, orb_b, tov_b)
                             
                    if valid_a:
                        off_a = list(roster_a - set(lineup_a))
                        update_anchor_stats(lineup_a, off_a, duration, score_diff_a, 0, stats_anchor, fga_a, fta_a, orb_a, tov_a)
                    if valid_b:
                        off_b = list(roster_b - set(lineup_b))
                        update_anchor_stats(lineup_b, off_b, duration, 0, score_diff_a, stats_anchor, fga_b, fta_b, orb_b, tov_b)

                elif score_diff_b > 0:
                    if valid_b: update_stats_dict(lineup_b, duration, score_diff_b, 0, stats_5man, fga_b, fta_b, orb_b, tov_b)
                    if valid_a: update_stats_dict(lineup_a, duration, 0, score_diff_b, stats_5man, fga_a, fta_a, orb_a, tov_a)
                    
                    if valid_b:
                        for pair in combinations(lineup_b, 2):
                             update_stats_dict(tuple(sorted(pair)), duration, score_diff_b, 0, stats_2man, fga_b, fta_b, orb_b, tov_b)
                    if valid_a:
                        for pair in combinations(lineup_a, 2):
                             update_stats_dict(tuple(sorted(pair)), duration, 0, score_diff_b, stats_2man, fga_a, fta_a, orb_a, tov_a)
                             
                    if valid_b:
                        off_b = list(roster_b - set(lineup_b))
                        update_anchor_stats(lineup_b, off_b, duration, score_diff_b, 0, stats_anchor, fga_b, fta_b, orb_b, tov_b)
                    if valid_a:
                        off_a = list(roster_a - set(lineup_a))
                        update_anchor_stats(lineup_a, off_a, duration, 0, score_diff_b, stats_anchor, fga_a, fta_a, orb_a, tov_a)
                else:
                    if valid_a: update_stats_dict(lineup_a, duration, 0, 0, stats_5man, fga_a, fta_a, orb_a, tov_a)
                    if valid_b: update_stats_dict(lineup_b, duration, 0, 0, stats_5man, fga_b, fta_b, orb_b, tov_b)
                    
                    if valid_a:
                        for pair in combinations(lineup_a, 2):
                            update_stats_dict(tuple(sorted(pair)), duration, 0, 0, stats_2man, fga_a, fta_a, orb_a, tov_a)
                    if valid_b:
                        for pair in combinations(lineup_b, 2):
                            update_stats_dict(tuple(sorted(pair)), duration, 0, 0, stats_2man, fga_b, fta_b, orb_b, tov_b)
                            
                    if valid_a:
                        off_a = list(roster_a - set(lineup_a))
                        update_anchor_stats(lineup_a, off_a, duration, 0, 0, stats_anchor, fga_a, fta_a, orb_a, tov_a)
                    if valid_b:
                        off_b = list(roster_b - set(lineup_b))
                        update_anchor_stats(lineup_b, off_b, duration, 0, 0, stats_anchor, fga_b, fta_b, orb_b, tov_b)

                prev_time = curr_time
        
        valid_games += 1
        if valid_games % 10 == 0:
            print(f"Processed {valid_games} games...")
            
    print("Analysis Complete.")
    return stats_5man, stats_2man, stats_anchor

def save_results(stats_5man, stats_2man, stats_anchor, season):
    import json
    
    # Helper to format for JSON
    def format_lineup_stats(stats_dict, min_minutes=0, label_key='Lineup', mode='40'):
        results = []
        for key, vals in stats_dict.items():
            mins = vals['Minutes']
            if mins < min_minutes: continue
            
            pf = vals['PF']
            pa = vals['PA']
            diff = pf - pa
            
            # Possessions
            fga = vals.get('FGA', 0)
            fta = vals.get('FTA', 0)
            orb = vals.get('ORB', 0)
            tov = vals.get('TOV', 0)
            poss = fga + 0.44 * fta - orb + tov
            
            if mode == '100':
                basis = poss
                factor = 100
            else:
                basis = mins
                factor = 40
                
            if basis > 0:
                off_rating = (pf / basis) * factor
                def_rating = (pa / basis) * factor
                net_rating = off_rating - def_rating
            else:
                off_rating, def_rating, net_rating = 0, 0, 0
            
            # Key is tuple
            key_str = ", ".join(key)
            
            results.append({
                label_key: key_str,
                'Minutes': round(mins, 2),
                'Possessions': round(poss, 1),
                'PF': pf, 'PA': pa, 'PlusMinus': diff,
                'OffRating': round(off_rating, 2),
                'DefRating': round(def_rating, 2),
                'NetRating': round(net_rating, 2),
                'StatMode': f"Per {factor} { 'Poss' if mode=='100' else 'Min' }"
            })
            
        return sorted(results, key=lambda x: x['NetRating'], reverse=True)

    def format_anchor_stats(stats_dict, min_minutes=0):
        results = []
        for player, vals in stats_dict.items():
            on_min = vals['On_Min']
            if on_min < min_minutes: continue
            
            # Default to Per 40 for Anchor
            on_net = ((vals['On_PF'] - vals['On_PA']) / on_min) * 40 if on_min > 0 else 0
            off_min = vals['Off_Min']
            off_net = ((vals['Off_PF'] - vals['Off_PA']) / off_min) * 40 if off_min > 0 else 0
            
            results.append({
                'Player': player,
                'On_Minutes': round(on_min, 2),
                'Off_Minutes': round(off_min, 2),
                'On_NetRating': round(on_net, 2),
                'Off_NetRating': round(off_net, 2),
                'AnchorScore': round(on_net - off_net, 2)
            })
            
        return sorted(results, key=lambda x: x['AnchorScore'], reverse=True)

    # Save 5-man (Per 40)
    res_5man_40 = format_lineup_stats(stats_5man, MIN_MINUTES_5MAN, 'Lineup', '40')
    with open(f"lineup_stats_5man_{season}.json", "w", encoding='utf-8') as f:
        json.dump(res_5man_40, f, indent=4)

    # Save 5-man (Per 100)
    res_5man_100 = format_lineup_stats(stats_5man, MIN_MINUTES_5MAN, 'Lineup', '100')
    with open(f"lineup_stats_5man_100_{season}.json", "w", encoding='utf-8') as f:
        json.dump(res_5man_100, f, indent=4)
        
    # Save 2-man (Per 40)
    res_2man_40 = format_lineup_stats(stats_2man, MIN_MINUTES_2MAN, 'Duo', '40')
    with open(f"lineup_stats_2man_{season}.json", "w", encoding='utf-8') as f:
        json.dump(res_2man_40, f, indent=4)

    # Save 2-man (Per 100)
    res_2man_100 = format_lineup_stats(stats_2man, MIN_MINUTES_2MAN, 'Duo', '100')
    with open(f"lineup_stats_2man_100_{season}.json", "w", encoding='utf-8') as f:
        json.dump(res_2man_100, f, indent=4)

    # Save Anchor (Per 40)
    res_anchor = format_anchor_stats(stats_anchor, MIN_MINUTES_ANCHOR)
    with open(f"lineup_stats_anchor_{season}.json", "w", encoding='utf-8') as f:
        json.dump(res_anchor, f, indent=4)
        
    print(f"Results saved for {season}.")
    return res_5man_40, res_5man_100, res_2man_40, res_2man_100

def plot_scatter(data, title, filename, label_key, mode='40'):
    if not data: return
    
    df = pd.DataFrame(data)
    
    # Helper for short names
    def shorten_names(name_str):
        if not isinstance(name_str, str): return str(name_str)
        parts = name_str.split(',')
        surnames = [parts[i].strip().title() for i in range(0, len(parts), 2)]
        return ", ".join(surnames)
        
    df['ShortLabel'] = df[label_key].apply(shorten_names)
    
    plt.figure(figsize=(14, 10))
    
    # Plot OffRating vs DefRating
    sns.scatterplot(
        data=df, 
        x='OffRating', 
        y='DefRating', 
        size='Minutes', 
        sizes=(100, 1000), 
        alpha=0.7, 
        legend=False
    )
    
    # Invert Y axis
    plt.gca().invert_yaxis()
    
    # Add Avg Lines
    avg_off = df['OffRating'].mean()
    avg_def = df['DefRating'].mean()
    plt.axvline(avg_off, color='gray', linestyle='--', alpha=0.5)
    plt.axhline(avg_def, color='gray', linestyle='--', alpha=0.5)
    
    # Label Quadrants
    plt.text(df['OffRating'].max(), df['DefRating'].min(), 'ELITE', ha='right', va='top', fontsize=12, color='green', weight='bold')
    
    top_performers = df.head(10)
    
    from adjustText import adjust_text
    texts = []
    
    for i, row in top_performers.iterrows():
        texts.append(plt.text(row['OffRating'], row['DefRating'], row['ShortLabel'], fontsize=9, weight='bold'))
        
    if texts:
        adjust_text(texts, arrowprops=dict(arrowstyle='-', color='gray', alpha=0.5))

    suffix = " (Per 40 Min)" if mode == '40' else " (Per 100 Poss)"
    plt.title(title + f" - Off vs Def Rating {suffix}")
    plt.xlabel(f"Offensive Rating {suffix}")
    plt.ylabel(f"Defensive Rating {suffix} [Inverted]")
    
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
    print(f"Saved plot {filename}")

def main():
    seasons = range(START_SEASON, END_SEASON + 1)
    
    for season in seasons:
        df = fetch_pbp_with_lineups(season)
        if df.empty: continue
        
        # Get Raw Stats
        stats_5man, stats_2man, stats_anchor = analyze_lineups(df)
        
        # Save and Format (returns lists of dicts)
        s5_40, s5_100, s2_40, s2_100 = save_results(stats_5man, stats_2man, stats_anchor, season)
        
        # Plot Per 40
        plot_scatter(s5_40[:50], f"Death Lineups {season}", f"death_lineups_{season}.png", "Lineup", '40')
        plot_scatter(s2_40[:50], f"Dynamic Duos {season}", f"dynamic_duos_{season}.png", "Duo", '40')
        
        # Plot Per 100
        plot_scatter(s5_100[:50], f"Death Lineups {season}", f"death_lineups_100_{season}.png", "Lineup", '100')
        plot_scatter(s2_100[:50], f"Dynamic Duos {season}", f"dynamic_duos_100_{season}.png", "Duo", '100')

if __name__ == "__main__":
    main()
