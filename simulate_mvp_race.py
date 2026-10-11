import pandas as pd
import json
import matplotlib.pyplot as plt
import seaborn as sns
import os

def simulate_mvp_race():
    # Load Data
    try:
        df_games = pd.read_json('mvp_parsed_games.json')
        with open('clutch_logs_2025.json', 'r') as f:
            clutch_logs = json.load(f)
        df_clutch_logs = pd.DataFrame(clutch_logs)
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    # Determine Rounds based on PLAYED games
    # Filter for games where at least one player scored (to avoid future empty games)
    played_games = df_games[df_games['PTS'] > 0]
    if played_games.empty:
        max_played_gc = 0
    else:
        max_played_gc = played_games['GameCode'].max()
        
    games_per_round = 9 
    
    # Calculate max round
    # User confirms only 28 rounds played. Hard cap at 28 to avoid future schedule noise.
    max_round = min((max_played_gc // games_per_round) + 1, 28)
    
    print(f"Max Played GameCode: {max_played_gc}. Max Round (Capped): {max_round}")

    output_dir = 'mvp_race_images'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Clean up old images to avoid confusion
    for f in os.listdir(output_dir):
        os.remove(os.path.join(output_dir, f))

    print(f"Starting simulation for {max_round} rounds...")

    for round_num in range(1, max_round + 1):
        end_game_code = round_num * games_per_round
        
        # Filter Data
        current_games = df_games[df_games['GameCode'] <= end_game_code].copy()
        if current_games.empty: continue
        
        # Check if this round has been played (games have scores)
        # Note: current_games includes all updates. 
        # But we only want to plot if the round is actually complete or started.
        # If we are at Round 29 and no games have scores, skip.
        # REMOVED: The break caused issues with partial/skipped rounds. 
        # Since we capped max_round at 28, we trust the loop.
        # if current_games[current_games['GameCode'] > (round_num - 1) * games_per_round]['PTS'].sum() == 0:
        #    print(f"Round {round_num} appears unplayed. Stopping.")
        #    break
        
        current_clutch = pd.DataFrame()
        if not df_clutch_logs.empty:
             current_clutch = df_clutch_logs[df_clutch_logs['GameCode'] <= end_game_code].copy()

        # 1. Calculate Standings (local to this point)
        # We need Game Results from current_games
        # df_games doesn't have game results directly in row... wait.
        # Parse_data script calculated standings from derived results.
        # We need to re-derive results from player stats? No.
        # mvp_parsed_games.json has Player stats. 
        # We need Scores to determine Winner.
        # Score is sum of PTS for each team in a GameCode.
        
        game_scores = current_games.groupby(['GameCode', 'TeamCode'])['PTS'].sum().reset_index()
        # Pivot to find winner
        # This is tricky because we have 2 rows per game (Team A, Team B). 
        # But we don't know who played whom easily without the original schedule.
        # Actually, `mvp_parsed_games.json` doesn't have "Opponent". 
        # It has "TeamCode".
        # If we group by GameCode, we should have 2 teams.
        
        standings = {}
        
        games_list = game_scores['GameCode'].unique()
        for g in games_list:
            matchup = game_scores[game_scores['GameCode'] == g]
            if len(matchup) < 2: continue
            
            t1 = matchup.iloc[0]
            t2 = matchup.iloc[1]
            
            winner = t1['TeamCode'] if t1['PTS'] > t2['PTS'] else t2['TeamCode']
            loser = t1['TeamCode'] if t1['PTS'] < t2['PTS'] else t2['TeamCode']
            
            standings[winner] = standings.get(winner, {'W':0, 'GP':0})
            standings[loser] = standings.get(loser, {'W':0, 'GP':0})
            
            standings[winner]['W'] += 1
            standings[winner]['GP'] += 1
            standings[loser]['GP'] += 1

        # Calculate Win Pct
        team_win_pct = {}
        for t, stats in standings.items():
            team_win_pct[t] = stats['W'] / stats['GP'] if stats['GP'] > 0 else 0
            
        # Rank Bonus
        sorted_standings = sorted(team_win_pct.items(), key=lambda x: x[1], reverse=True)
        rank_map = {k: i+1 for i, (k, v) in enumerate(sorted_standings)}
        
        def get_rank_bonus(team):
            rank = rank_map.get(team, 18)
            if rank <= 4: return 1.10
            if rank <= 8: return 1.05
            return 1.0

        # 2. Player Stats Calculation
        # Primary Team
        player_teams = current_games.groupby(['PlayerCode', 'PlayerName'])['TeamCode'].agg(lambda x: x.mode().iloc[0]).reset_index()
        player_teams.rename(columns={'TeamCode': 'PrimaryTeam'}, inplace=True)
        current_games = pd.merge(current_games, player_teams[['PlayerCode', 'PrimaryTeam']], on='PlayerCode', how='left')
        
        stats = current_games.groupby(['PlayerCode', 'PlayerName', 'PrimaryTeam']).agg({
            'GmSc': 'mean',
            'GameCode': 'count',
            'PTS': 'mean'
        }).reset_index()
        stats.rename(columns={'GameCode': 'GP', 'PrimaryTeam': 'TeamCode'}, inplace=True)
        
        # Filter GP (Min 50% of rounds? or just fixed 3-5?)
        # For early weeks (Round 1-5), min 1?
        min_gp = max(1, round_num // 2)
        stats = stats[stats['GP'] >= min_gp]
        
        # 3. Points Share
        team_points = current_games.groupby('TeamCode')['PTS'].sum().to_dict()
        stats['PointsShare'] = stats.apply(lambda x: (x['PTS']*x['GP']) / team_points.get(x['TeamCode'], 1), axis=1)
        
        # 4. Clutch
        if not current_clutch.empty:
            # Clean Player Names (Upper)
            current_clutch['PlayerUpper'] = current_clutch['Player'].str.upper().str.strip()
            stats['PlayerUpper'] = stats['PlayerName'].str.upper().str.strip()
            
            clutch_agg = current_clutch.groupby('PlayerUpper')['ClutchPoints'].sum().reset_index()
            merged = pd.merge(stats, clutch_agg, on='PlayerUpper', how='left')
            merged['ClutchPoints'].fillna(0, inplace=True)
        else:
             merged = stats.copy()
             merged['ClutchPoints'] = 0
             
        merged['ClutchPPG'] = merged['ClutchPoints'] / merged['GP']
        merged['TeamWinPct'] = merged['TeamCode'].map(team_win_pct).fillna(0)
        merged['RankBonus'] = merged['TeamCode'].apply(get_rank_bonus)

        # 5. Normalize & Score
        def normalize(series):
            if series.max() == series.min(): return 0
            return (series - series.min()) / (series.max() - series.min()) * 100

        merged['GmSc_Norm'] = normalize(merged['GmSc'])
        merged['Team_Norm'] = normalize(merged['TeamWinPct'])
        merged['Clutch_Norm'] = normalize(merged['ClutchPPG'])
        merged['Share_Norm'] = normalize(merged['PointsShare'])
        
        merged['MVP_Score'] = (
            (merged['GmSc_Norm'] * 0.60) + 
            (merged['Team_Norm'] * 0.20 * merged['RankBonus']) + 
            (merged['Clutch_Norm'] * 0.10) + 
            (merged['Share_Norm'] * 0.10)
        )
        
        merged.sort_values('MVP_Score', ascending=False, inplace=True)
        top_10 = merged.head(10).sort_values('MVP_Score', ascending=True)

        # 6. Plot
        plt.figure(figsize=(10, 6))
        
        team_colors = {
            'OLY': '#E2001A', # Red (Olympiacos)
            'ULK': '#002B5C', # Navy (Fenerbahce) - Changed from Yellow to avoid TEL clash
            'PAN': '#007F3D', # Green
            'MAD': '#6C3B2A', # Real Madrid (Purple/White? Used Brown? Changed to White/Blue?)
                              # Real is usually White/Purple/Gold. Let's use #6C3B2A... wait that's Brown?
                              # Let's use #413D3D (Gray/Black)? No. #645486 (Purple).
            'MAD': '#645486', # Purple
            'BAR': '#004D98', # Blue/Red
            'MCO': '#D4AF37', # Gold (Monaco) - Changed from Red to avoid OLY clash
            'ZAL': '#006233', # Green
            'DUB': '#000000', # Black?
            'BES': '#d9d9d9', # Besiktas (light grey)
            'IST': '#003366', # Navy (Efes)
            'HTA': '#000000', # Black?
            'PAR': '#000000', # Partizaan (Black)
            'RED': '#FFFFFF', # White (Crvena Zvezda) - Changed from Red to avoid OLY clash
            'TEL': '#F6C300', # Yellow (Maccabi)
            'BAS': '#B50031', # Red/Blue (Baskonia)
            'MUN': '#DC052D', # Red (Bayern)... Clash?
                              # Bayern is Red. Maybe #0066B2 (Bavarian Blue)?
            'MUN': '#0066B2', # Blue
            'VIR': '#000000', # Black (Virtus)
            'PAM': '#EB7622', # Orange (Valencia)
            'ASV': '#000000'  # Black (Asvel)
        }
        
        bars = plt.barh(top_10['PlayerName'], top_10['MVP_Score'], color='#ff7f0e', edgecolor='black')
        for bar, team in zip(bars, top_10['TeamCode']):
            bar.set_color(team_colors.get(team, '#888888'))
            bar.set_edgecolor('black') # Default edge
            
            # Special Hatching for Red Star (RED) to match Red/White stripes and avoid invisible white bar
            if team == 'RED':
                bar.set_facecolor('white')
                bar.set_edgecolor('#E2001A')
                bar.set_hatch('///')
            # Special Hatching for Baskonia (Blue/Red)? OR others?
            # Let's keep it simple for now to solve the specific complaint.
            
        plt.title(f'MVP Ladder - Week {round_num}', fontsize=16, fontweight='bold')
        plt.xlabel('MVP Score', fontsize=12)
        plt.xlim(0, 105)
        
        # Add labels
        for bar, score, name, team in zip(bars, top_10['MVP_Score'], top_10['PlayerName'], top_10['TeamCode']):
             plt.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2, 
                     f"{score:.1f} ({team})", va='center', fontsize=9)

        plt.tight_layout()
        filename = f"{output_dir}/mvp_week_{round_num:02d}.png"
        plt.savefig(filename, dpi=150)
        plt.close()
        
        print(f"Generated {filename}")

if __name__ == "__main__":
    simulate_mvp_race()
