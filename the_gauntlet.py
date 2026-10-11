import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import time
from euroleague_api.EuroLeagueData import EuroLeagueData
from euroleague_api.boxscore_data import BoxScoreData

# --- Configuration ---
START_SEASON = 2024
END_SEASON = 2025
SEASONS = range(START_SEASON, END_SEASON + 1)
CACHE_DIR = "data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Team name mapping for consistent display
TEAM_NAME_OVERRIDES = {
    "PAN": "Panathinaikos",
    "OLY": "Olympiacos",
    "RMB": "Real Madrid",
    "BAR": "Barcelona",
    "FBB": "Fenerbahce",
    "MCO": "Monaco",
    "TEL": "Maccabi", # Old code for Maccabi
    "MTA": "Maccabi",
    "EFS": "Anadolu Efes",
    "IST": "Anadolu Efes", # frequent changes
    "PAR": "Partizan",
    "CZV": "Crvena Zvezda",
    "RED": "Crvena Zvezda", # recent change
    "ZAL": "Zalgiris",
    "MIL": "Armani Milan",
    "EA7": "Armani Milan", # sponsored
    "VIR": "Virtus Bologna",
    "BAS": "Baskonia",
    "VAL": "Valencia",
    "BAY": "Bayern Munich",
    "MUN": "Bayern Munich", # alt code
    "BER": "ALBA Berlin",
    "ASV": "ASVEL",
    "PRS": "Paris",
    "DUB": "Dubai BC",
    "BES": "Besiktas",
    "MAD": "Real Madrid",
    "ULK": "Fenerbahce",
    "HTA": "Hapoel Tel Aviv",
    "PAM": "Valencia",
}

def get_full_team_name(code):
    return TEAM_NAME_OVERRIDES.get(code, code)

class TheGauntlet:
    def __init__(self):
        self.api = EuroLeagueData()
        self.boxscore_api = BoxScoreData()

    def get_season_games(self, season):
        # ... (keep existing implementation) ...
        cache_file = os.path.join(CACHE_DIR, f"games_{season}.csv")
        
        if os.path.exists(cache_file):
            print(f"Loading cached games for {season}...")
            df = pd.read_csv(cache_file)
        else:
            print(f"Fetching games for {season} from API...")
            try:
                df = self.api.get_game_metadata_season(season)
                df.to_csv(cache_file, index=False)
                time.sleep(1) # Be nice to API
            except Exception as e:
                print(f"Error fetching season {season}: {e}")
                return pd.DataFrame()
        
        # Ensure played games only
        if 'played' in df.columns:
            df = df[df['played'] == True].copy()
            
        return df

    def get_advanced_game_data(self, season, game_df):
        """
        Fetches detailed boxscore data to calculate Possessions and Pace.
        Returns a DataFrame with advanced metrics per game.
        """
        cache_file = os.path.join(CACHE_DIR, f"games_advanced_{season}.csv")
        
        existing_df = pd.DataFrame()
        processed_gamecodes = set()
        
        if os.path.exists(cache_file):
            print(f"Loading cached ADVANCED stats for {season}...")
            try:
                existing_df = pd.read_csv(cache_file)
                if not existing_df.empty and 'gamecode' in existing_df.columns:
                    processed_gamecodes = set(existing_df['gamecode'].unique())
                    print(f"Found {len(processed_gamecodes)} games already processed completely.")
            except Exception as e:
                print(f"Error reading cache: {e}. Starting fresh.")
                existing_df = pd.DataFrame()

        # If we have all games, return immediately
        # Note: game_df has one row per game? No, typically one.
        # But advanced stats stores 2 rows per game (Home & Away)? 
        # My implementation stores 2 rows per game loop.
        # So processed_gamecodes check is enough.
        
        # Check if we need to fetch anything
        games_to_fetch = [g for g in game_df['gamecode'].unique() if g not in processed_gamecodes]
        
        if not games_to_fetch:
            print("All advanced data is cached.")
            return existing_df
        
        print(f"Fetching ADVANCED stats for {len(games_to_fetch)} remaining games...")
        
        # Load existing rows into list
        advanced_rows = existing_df.to_dict('records') if not existing_df.empty else []
        
        total_fetching = len(games_to_fetch)
        
        for i, gamecode in enumerate(games_to_fetch):
            # Find row in game_df for metadata
            metadata = game_df[game_df['gamecode'] == gamecode].iloc[0]
            r = metadata['gameday']
            home = metadata['homecode']
            away = metadata['awaycode']
            
            if i % 1 == 0: # Save after every game (to be safe)
                print(f"Processing game {i+1}/{total_fetching}...")
                if advanced_rows:
                    pd.DataFrame(advanced_rows).to_csv(cache_file, index=False)

            # Retry Logic
            max_retries = 5
            success = False
            
            for attempt in range(max_retries):
                try:
                    # Fetch boxscore
                    # API expects the numeric code (e.g. "1" from "E2024_1")
                    api_gamecode = str(gamecode).split('_')[-1]
                    df_box = self.boxscore_api.get_player_boxscore_stats_data(season, api_gamecode)
                    
                    if df_box.empty:
                         # Sometimes checking empty helps verify if we got bad data
                         raise ValueError("Empty DataFrame returned")

                    # Use 'Total' row for Team Totals (Points, FGA, etc.)
                    # 'Team' row only contains Team/Coach stats (like team rebounds/turnovers)
                    team_stats = df_box[df_box['Player_ID'] == 'Total']
                    
                    for team_code in [home, away]:
                        ts = team_stats[team_stats['Team'] == team_code]
                        if ts.empty: continue
                            
                        # Extract Metrics
                        fga2 = ts['FieldGoalsAttempted2'].values[0]
                        fga3 = ts['FieldGoalsAttempted3'].values[0]
                        fga = fga2 + fga3
                        fta = ts['FreeThrowsAttempted'].values[0]
                        orb = ts['OffensiveRebounds'].values[0]
                        tov = ts['Turnovers'].values[0]
                        points = ts['Points'].values[0]
                        
                        # Possessions Formula: 0.96 * (FGA + TOV + 0.44 * FTA - ORB)
                        poss = 0.96 * (fga + tov + 0.44 * fta - orb)
                        
                        # OffRtg = 100 * Points / Poss
                        off_rtg = 100 * (points / poss) if poss > 0 else 0
                        
                        # Bench Points calculation
                        team_players = df_box[df_box['Team'] == team_code]
                        starters = team_players[team_players['IsStarter'] == 1]
                        bench = team_players[(team_players['IsStarter'] == 0) & (team_players['Player_ID'] != 'Total')]
                        
                        bench_points = bench['Points'].sum()
                        starter_points = starters['Points'].sum()
                        
                        advanced_rows.append({
                            'season': season,
                            'round': r,
                            'gamecode': gamecode,
                            'team': team_code,
                            'opponent': away if team_code == home else home,
                            'location': 'Home' if team_code == home else 'Away',
                            'possessions': poss,
                            'off_rtg': off_rtg,
                            'points': points,
                            'bench_points': bench_points,
                            'starter_points': starter_points,
                            'pace': poss,  # Pace is approx possessions per 40m (game is 40m),
                            'fga': fga,
                            'fg3a': fga3, 
                            'fta': fta
                        })
                    
                    success = True
                    time.sleep(5) # 5s delay
                    break # Success, exit retry loop

                except Exception as e:
                    wait_time = 5 * (2 ** attempt) # Exponential backoff: 5, 10, 20, 40, 80
                    print(f"Error processing {gamecode} (Attempt {attempt+1}): {e}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
            
            if not success:
                print(f"Failed to fetch {gamecode} after retries. Skipping.")

        df_advanced = pd.DataFrame(advanced_rows)
        df_advanced.to_csv(cache_file, index=False)
        return df_advanced
        
    def generate_clutch_gene(self, df, season):
        """
        The Clutch Gene: Close Game Performance (<= 5 points).
        Uses basic game data, not advanced, but we can put it here.
        """
        # Filter close games
        # Row-based df has each game twice (once per team)? 
        # Actually df from process_season_data is game-based (one row per game).
        # Let's use that.
        
        close_games = []
        for _, row in df.iterrows():
            margin = abs(row['homescore'] - row['awayscore'])
            if margin <= 5:
                # Add for Home
                close_games.append({
                    'team': row['homecode'],
                    'win': 1 if row['homescore'] > row['awayscore'] else 0
                })
                # Add for Away
                close_games.append({
                    'team': row['awaycode'],
                    'win': 1 if row['awayscore'] > row['homescore'] else 0
                })
                
        df_close = pd.DataFrame(close_games)
        
        if df_close.empty:
            print("No close games found yet.")
            return

        stats = df_close.groupby('team').agg(
            games=('win', 'count'),
            wins=('win', 'sum')
        )
        stats['win_pct'] = (stats['wins'] / stats['games']) * 100
        
        plt.figure(figsize=(12, 10))
        
        plt.scatter(stats['games'], stats['win_pct'], s=150, alpha=0.8, c='crimson')
        
        for team in stats.index:
            plt.text(stats.loc[team, 'games']+0.1, stats.loc[team, 'win_pct'], team, fontsize=9, weight='bold')
            
        plt.title(f"THE CLUTCH GENE: Games Decided by ≤ 5 Pts ({season})", fontsize=20, weight='bold')
        plt.xlabel("Close Games Played (Experience)", fontsize=14)
        plt.ylabel("Win % in Close Games (Clutch Factor)", fontsize=14)
        
        plt.axhline(50, color='k', linestyle='--', alpha=0.5)
        
        plt.text(stats['games'].max(), 100, "ICE COLD KILLERS\n(High Volume, High Win%)", ha='right', va='top', color='green', weight='bold')
        plt.text(stats['games'].max(), 0, "HEARTBREAKERS\n(Always Close, Always Lose)", ha='right', va='bottom', color='red', weight='bold')
        
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"the_clutch_gene_{season}.png", dpi=300)
        plt.close()

    def generate_snipers_nest(self, df_adv, season):
        """
        Shooting Efficiency: TS% vs 3P Rate.
        Requires fga, fta, fg3a, points.
        """
        if 'fga' not in df_adv.columns:
            print("Sniper's Nest requires FGA/FTA data. Please re-fetch advanced stats.")
            return

        stats = df_adv.groupby('team')[['points', 'fga', 'fta', 'fg3a']].sum()
        
        # True Shooting % = Pts / (2 * (FGA + 0.44 * FTA))
        stats['ts_pct'] = 100 * stats['points'] / (2 * (stats['fga'] + 0.44 * stats['fta']))
        
        # 3P Attempt Rate = 3PA / FGA
        stats['3par'] = 100 * stats['fg3a'] / stats['fga']
        
        # PPG (for size)
        games_played = df_adv.groupby('team')['gamecode'].count()
        stats['ppg'] = stats['points'] / games_played
        
        plt.figure(figsize=(14, 10))
        
        x = stats['3par']
        y = stats['ts_pct']
        sizes = stats['ppg'] * 5 # Scale for bubble
        teams = [get_full_team_name(t) for t in stats.index]
        
        plt.scatter(x, y, s=sizes, alpha=0.6, c='dodgerblue', edgecolors='k')
        
        for i, team in enumerate(teams):
            plt.text(x[i], y[i], team, fontsize=8, ha='center', va='center', weight='bold')
            
        plt.title(f"THE SNIPER'S NEST: Shooting Efficiency ({season})", fontsize=20, weight='bold')
        plt.xlabel("3-Point Attempt Rate (% of Shots)", fontsize=14)
        plt.ylabel("True Shooting % (Efficiency)", fontsize=14)
        
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"the_snipers_nest_{season}.png", dpi=300)
        plt.close()


    def process_season_data(self, season):
        df = self.get_season_games(season)
        if df.empty:
            return None

        # Fetch Advanced Data
        df_adv = self.get_advanced_game_data(season, df)
        
        # Create lookups
        teams = set(df['homecode'].unique()) | set(df['awaycode'].unique())
        rounds = sorted(df['gameday'].unique())
        
        margins = {}
        opponents = {}
        
        # Simple margins from basic data
        for _, row in df.iterrows():
            round_num = row['gameday']
            margin = row['homescore'] - row['awayscore']
            margins[(row['homecode'], round_num)] = margin
            margins[(row['awaycode'], round_num)] = -margin
            opponents[(row['homecode'], round_num)] = row['awaycode']
            opponents[(row['awaycode'], round_num)] = row['homecode']

        return margins, opponents, sorted(list(teams)), rounds, df, df_adv

    def generate_heatmap(self, season):
        data = self.process_season_data(season)
        if not data: return
        margins, opponents, teams, rounds, df, df_adv = data

        # ... (Keep existing heatmap logic) ...
        # (Redraw heatmap logic here if strictly needed, or assume it exists)
        # For this edit, I'll focus on adding the NEW charts and updating the existing Fortress.
        
        # ... [Existing Heatmap Code Omitted for Brevity - assume unchanged] ...
        # Re-implementing visually for the user to ensure it works
        
        team_diffs = {team: sum(margins.get((team, r), 0) for r in rounds) for team in teams}
        sorted_teams = sorted(teams, key=lambda t: team_diffs[t], reverse=True)
        
        plot_data = []
        for team in sorted_teams:
            row = []
            for r in rounds:
                row.append(margins.get((team, r), np.nan))
            plot_data.append(row)
            
        df_plot = pd.DataFrame(plot_data, index=[get_full_team_name(t) for t in sorted_teams], columns=rounds)

        plt.figure(figsize=(20, 12))
        cmap = sns.diverging_palette(10, 130, as_cmap=True, center="light")
        sns.heatmap(df_plot, cmap=cmap, center=0, annot=True, fmt=".0f", cbar_kws={'label': 'Point Differential'}, linewidths=1, linecolor='white')
        plt.title(f"THE GAUNTLET: Margin of Victory ({season})", fontsize=20, weight='bold')
        plt.tight_layout()
        plt.savefig(f"the_gauntlet_{season}.png", dpi=300)
        plt.close()

        # Generate ALL New Charts
        self.generate_cumulative_diff_chart(teams, rounds, margins, season)
        self.generate_fortress_advanced(df_adv, season)
        self.generate_pace_maker(df_adv, season)
        self.generate_glass_cannon(df_adv, season)
        self.generate_bench_mob(df_adv, season)
        self.generate_heartbeat(df_adv, season)
        self.generate_momentum_meter(df_adv, season)
        self.generate_road_warriors(df_adv, season)
        self.generate_snipers_nest(df_adv, season)
        
        # Clutch Gene uses basic data (df)
        self.generate_clutch_gene(df, season)

    # ... (Keep generate_cumulative_diff_chart) ...
    def generate_cumulative_diff_chart(self, teams, rounds, margins, season):
        # (Same as before)
        plt.figure(figsize=(16, 10))
        final_diffs = []
        for team in teams:
            cum = 0
            hist = []
            for r in rounds:
                m = margins.get((team, r), 0)
                if pd.isna(m): m=0
                cum += m
                hist.append(cum)
            final_diffs.append((team, cum))
        
        final_diffs.sort(key=lambda x: x[1], reverse=True)
        top = {x[0] for x in final_diffs[:4]}
        bot = {x[0] for x in final_diffs[-2:]}
        
        for team in teams:
            cum = 0
            hist = []
            for r in rounds:
                m = margins.get((team, r), 0)
                if pd.isna(m): m=0
                cum += m
                hist.append(cum)
            
            name = get_full_team_name(team)
            if team in top:
                plt.plot(rounds, hist, linewidth=3, label=f"{name} ({int(hist[-1])})")
            elif team in bot:
                plt.plot(rounds, hist, linewidth=3, linestyle='--', label=f"{name} ({int(hist[-1])})")
            else:
                plt.plot(rounds, hist, color='grey', alpha=0.3, linewidth=1)
        
        plt.title(f"THE MOUNTAIN: Cumulative +/- ({season})", fontsize=20, weight='bold')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"the_mountain_{season}.png", dpi=300)
        plt.close()

    def generate_fortress_advanced(self, df_adv, season):
        """
        The Fortress: Net Rating (Home vs Away).
        """
        # Group by team and location
        grouped = df_adv.groupby(['team', 'location'])['off_rtg'].mean().unstack()
        # Allows us to get Avg OffRtg Home vs Away.
        # But we want Net Rating.
        # We need opponent OffRtg to subtract.
        
        # Let's aggregate defense too
        # DefRtg of Team A = OffRtg of Team B (Opponent) in that game
        # We can join df_adv with itself on gamecode + opponent?
        # Or simpler: The cache has 'team' and 'points'. 
        # DefRtg = 100 * OppPoints / OppPoss (which is ~TeamPoss)
        
        # Calculate DefRtg per row
        # Since we processed every team, we can find the opponent's stats in the same DF
        # merge on gamecode + team=opponent
        df_opp = df_adv[['gamecode', 'team', 'points', 'possessions']].rename(
            columns={'team': 'opponent', 'points': 'opp_points', 'possessions': 'opp_poss'}
        )
        joined = pd.merge(df_adv, df_opp, on=['gamecode', 'opponent'])
        
        joined['def_rtg'] = 100 * (joined['opp_points'] / joined['possessions'])
        joined['net_rtg'] = joined['off_rtg'] - joined['def_rtg']
        
        # Now pivot
        net_pivot = joined.groupby(['team', 'location'])['net_rtg'].mean().unstack()
        
        plt.figure(figsize=(12, 12))
        
        x_vals, y_vals, labels = [], [], []
        
        for team in net_pivot.index:
            home_net = net_pivot.loc[team, 'Home']
            away_net = net_pivot.loc[team, 'Away']
            
            if pd.isna(home_net) or pd.isna(away_net): continue
            
            x_vals.append(home_net)
            y_vals.append(away_net)
            labels.append(team)
            
            plt.scatter(home_net, away_net, s=150, alpha=0.8)
            plt.text(home_net+0.3, away_net+0.3, get_full_team_name(team), fontsize=9, weight='bold')

        # Formatting
        limit = max(max(abs(min(x_vals)), max(x_vals)), max(abs(min(y_vals)), max(y_vals))) + 3
        plt.xlim(-limit, limit)
        plt.ylim(-limit, limit)
        plt.axhline(0, color='k', linewidth=1)
        plt.axvline(0, color='k', linewidth=1)
        
        # Quadrants
        plt.text(limit-1, limit-1, "CONTENDERS\n(Net+ Everywhere)", ha='right', va='top', color='green', weight='bold')
        plt.text(-limit+1, -limit+1, "LOTTERY\n(Net- Everywhere)", ha='left', va='bottom', color='red', weight='bold')
        plt.text(limit-1, -limit+1, "HOME HEROES\n(Good Home, Bad Away)", ha='right', va='bottom', color='blue', weight='bold')
        plt.text(-limit+1, limit-1, "ROAD WARRIORS\n(Oddly better Away)", ha='left', va='top', color='orange', weight='bold')

        plt.title(f"THE FORTRESS: Net Rating Home vs Away ({season})", fontsize=20, weight='bold')
        plt.xlabel("Home Net Rating", fontsize=14)
        plt.ylabel("Away Net Rating", fontsize=14)
        plt.grid(True, linestyle='--', alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"the_fortress_{season}.png", dpi=300)
        plt.close()
        
    def generate_pace_maker(self, df_adv, season):
        """
        Pace vs Efficiency.
        """
        # Avg Pace and OffRtg
        stats = df_adv.groupby('team')[['pace', 'off_rtg']].mean()
        
        plt.figure(figsize=(14, 10))
        
        # Combo Chart: Bar for Pace, Line for OffRtg?
        # Bar Chart sorted by Pace
        stats = stats.sort_values('pace', ascending=False)
        
        ax1 = plt.gca()
        ax2 = ax1.twinx()
        
        teams = [get_full_team_name(t) for t in stats.index]
        x = range(len(teams))
        
        # Pace Bars
        ax1.bar(x, stats['pace'], alpha=0.6, color='skyblue', label='Pace')
        ax1.set_ylabel("Pace (Poss/40m)", color='tab:blue', fontsize=14)
        ax1.set_ylim(65, 80) # typical range
        
        # Efficiency Line
        ax2.plot(x, stats['off_rtg'], color='orange', marker='o', linewidth=3, label='Off Rating')
        ax2.set_ylabel("Offensive Rating", color='tab:orange', fontsize=14)
        
        plt.title(f"THE PACE MAKER: Speed vs. Efficiency ({season})", fontsize=20, weight='bold')
        ax1.set_xticks(x)
        ax1.set_xticklabels(teams, rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig(f"the_pace_maker_{season}.png", dpi=300)
        plt.close()

    def generate_glass_cannon(self, df_adv, season):
        """
        OffRtg vs DefRtg (Diverging Bar).
        """
        # Recalculate joined metrics
        df_opp = df_adv[['gamecode', 'team', 'points', 'possessions']].rename(
            columns={'team': 'opponent', 'points': 'opp_points', 'possessions': 'opp_poss'}
        )
        joined = pd.merge(df_adv, df_opp, on=['gamecode', 'opponent'])
        joined['def_rtg'] = 100 * (joined['opp_points'] / joined['possessions'])
        joined['net_rtg'] = joined['off_rtg'] - joined['def_rtg']
        
        stats = joined.groupby('team')[['off_rtg', 'def_rtg', 'net_rtg']].mean()
        stats = stats.sort_values('net_rtg', ascending=True) # Bottom to top
        
        plt.figure(figsize=(14, 12))
        
        teams = [get_full_team_name(t) for t in stats.index]
        y_pos = range(len(teams))
        
        # Create Diverging Bar
        # Center at league average? Or just back-to-back?
        # Let's do back to back 
        # Offense to right (Green), Defense to left (Red)
        
        plt.barh(y_pos, stats['off_rtg'], color='forestgreen', alpha=0.7, label='Offensive Rtg')
        plt.barh(y_pos, -stats['def_rtg'], color='firebrick', alpha=0.7, label='Defensive Rtg')
        
        plt.yticks(y_pos, teams, fontsize=12)
        plt.axvline(0, color='k')
        
        # Add values
        for i, val in enumerate(stats['off_rtg']):
            plt.text(val+1, i, f"{val:.1f}", va='center', color='green', fontweight='bold')
            
        for i, val in enumerate(stats['def_rtg']):
            plt.text(-val-8, i, f"{val:.1f}", va='center', color='firebrick', fontweight='bold')
            
        plt.title(f"THE GLASS CANNON: Offense vs Defense ({season})", fontsize=20, weight='bold')
        plt.xlabel("Rating (Pts/100)", fontsize=14)
        
        # Fix X axis labels to be positive on both sides
        # locs, _ = plt.xticks()
        # plt.xticks(locs, [str(abs(int(x))) for x in locs])
        
        plt.xlim(-130, 130)
        plt.tight_layout()
        plt.savefig(f"the_glass_cannon_{season}.png", dpi=300)
        plt.close()

    def generate_bench_mob(self, df_adv, season):
        """
        Stacked Bar: Starter vs Bench Points.
        """
        stats = df_adv.groupby('team')[['points', 'bench_points', 'starter_points']].mean()
        stats['bench_pct'] = stats['bench_points'] / stats['points']
        
        stats = stats.sort_values('bench_pct', ascending=True)
        
        plt.figure(figsize=(14, 12))
        teams = [get_full_team_name(t) for t in stats.index]
        
        # Stacked Bar
        p1 = plt.barh(teams, stats['starter_points'], color='navy', alpha=0.8, label='Starters')
        p2 = plt.barh(teams, stats['bench_points'], left=stats['starter_points'], color='gold', alpha=0.8, label='Bench')
        
        plt.legend()
        plt.title(f"THE BENCH MOB: Scoring Depth ({season})", fontsize=20, weight='bold')
        plt.xlabel("Points Per Game", fontsize=14)
        
        # Annotate percentages
        for i, (total, bench) in enumerate(zip(stats['points'], stats['bench_points'])):
            pct = (bench / total) * 100
            plt.text(total+1, i, f"{pct:.1f}% from Bench", va='center', fontsize=10)
            
        plt.tight_layout()
        plt.savefig(f"the_bench_mob_{season}.png", dpi=300)
        plt.close()

    def generate_heartbeat(self, df_adv, season):
        """
        The Heartbeat: Consistency Check (StdDev vs Mean Net Rating).
        """
        # Calculate Net Rating per game
        # We need opponent score for Net Rating.
        # We can compute it row-wise if we assume data is complete or just use OffRtg for now?
        # Better: use the 'points' and 'possessions' to find margins.
        # Actually, simpler: join like before.
        df_opp = df_adv[['gamecode', 'team', 'points', 'possessions']].rename(
            columns={'team': 'opponent', 'points': 'opp_points', 'possessions': 'opp_poss'}
        )
        joined = pd.merge(df_adv, df_opp, on=['gamecode', 'opponent'])
        joined['def_rtg'] = 100 * (joined['opp_points'] / joined['possessions'])
        joined['net_rtg'] = joined['off_rtg'] - joined['def_rtg']
        
        stats = joined.groupby('team')['net_rtg'].agg(['mean', 'std'])
        
        plt.figure(figsize=(12, 10))
        
        x = stats['mean']
        y = stats['std']
        teams = [get_full_team_name(t) for t in stats.index]
        
        plt.scatter(x, y, s=150, alpha=0.7, c='purple')
        
        for i, team in enumerate(teams):
            plt.text(x[i]+0.2, y[i], team, fontsize=9, weight='bold')
            
        plt.title(f"THE HEARTBEAT: Consistency Check ({season})", fontsize=20, weight='bold')
        plt.xlabel("Average Net Rating (Quality)", fontsize=14)
        plt.ylabel("Standard Deviation (Volatility)", fontsize=14)
        
        # Quadrants
        avg_std = y.mean()
        plt.axhline(avg_std, color='k', linestyle='--', alpha=0.5, label='Avg Volatility')
        plt.axvline(0, color='k', linestyle='-', alpha=0.5)
        
        plt.text(x.max(), y.min(), "STEADY GIANTS\n(Good & Consistent)", ha='right', va='bottom', color='green', weight='bold')
        plt.text(x.max(), y.max(), "WILDCARDS\n(Good but Chaos)", ha='right', va='top', color='orange', weight='bold')
        
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"the_heartbeat_{season}.png", dpi=300)
        plt.close()

    def generate_momentum_meter(self, df_adv, season):
        """
        Rolling 5-game Net Rating Trend.
        """
        # Need date or round order
        df_opp = df_adv[['gamecode', 'team', 'points', 'possessions']].rename(
            columns={'team': 'opponent', 'points': 'opp_points', 'possessions': 'opp_poss'}
        )
        joined = pd.merge(df_adv, df_opp, on=['gamecode', 'opponent'])
        joined['def_rtg'] = 100 * (joined['opp_points'] / joined['possessions'])
        joined['net_rtg'] = joined['off_rtg'] - joined['def_rtg']
        
        plt.figure(figsize=(16, 10))
        
        teams = joined['team'].unique()
        # Calculate Rolling Average per team
        final_medians = []
        
        for team in teams:
            team_data = joined[joined['team'] == team].sort_values('round')
            team_data['rolling_net'] = team_data['net_rtg'].rolling(window=5, min_periods=1).mean()
            
            final_val = team_data['rolling_net'].iloc[-1]
            final_medians.append((team, final_val))
            
            # Plot
            # Highlight top 4
            name = get_full_team_name(team)
            plt.plot(team_data['round'], team_data['rolling_net'], alpha=0.3, color='grey')
            
        # Re-plot top 4 and bottom 2 in color
        final_medians.sort(key=lambda x: x[1], reverse=True)
        
        top_teams = [x[0] for x in final_medians[:4]]
        bot_teams = [x[0] for x in final_medians[-2:]]
        
        # Color palette for top 4 (Green, Blue, Orange, Purple)
        top_colors = ['#2ca02c', '#1f77b4', '#ff7f0e', '#9467bd']
        # Color palette for bottom 2 (Red, Black)
        bot_colors = ['#d62728', 'black']
        
        for team in teams:
            if team in top_teams or team in bot_teams:
                team_data = joined[joined['team'] == team].sort_values('round')
                team_data['rolling_net'] = team_data['net_rtg'].rolling(window=5, min_periods=1).mean()
                
                name = get_full_team_name(team)
                
                if team in top_teams:
                    idx = top_teams.index(team)
                    color = top_colors[idx]
                    label = f"#{idx+1} {name}"
                elif team in bot_teams:
                    # Bottom 2
                    # bot_teams has [2nd_last, last] because of [-2:] slicing on sorted list
                    # Wait, final_medians is sorted DESCENDING.
                    # so [-2:] gives [2nd_Last, Last]
                    try:
                        idx = bot_teams.index(team) # 0 is 2nd last, 1 is last
                        color = bot_colors[idx]
                        rank_from_bot = 2 - idx 
                        label = f"Bot {rank_from_bot} {name}"
                    except:
                        color = 'red'
                        label = name
                    
                plt.plot(team_data['round'], team_data['rolling_net'], color=color, linewidth=3, label=label)
        
        plt.title(f"THE MOMENTUM METER: 5-Game Rolling Net Rating ({season})", fontsize=20, weight='bold')
        plt.xlabel("Round", fontsize=14)
        plt.ylabel("Rolling Net Rating", fontsize=14)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.axhline(0, color='k', linewidth=1)
        plt.tight_layout()
        plt.savefig(f"the_momentum_meter_{season}.png", dpi=300)
        plt.close()

    def generate_road_warriors(self, df_adv, season):
        """
        Home vs Away Net Rating Delta.
        """
        df_opp = df_adv[['gamecode', 'team', 'points', 'possessions']].rename(
            columns={'team': 'opponent', 'points': 'opp_points', 'possessions': 'opp_poss'}
        )
        joined = pd.merge(df_adv, df_opp, on=['gamecode', 'opponent'])
        joined['def_rtg'] = 100 * (joined['opp_points'] / joined['possessions'])
        joined['net_rtg'] = joined['off_rtg'] - joined['def_rtg']
        
        pivot = joined.groupby(['team', 'location'])['net_rtg'].mean().unstack()
        pivot['road_delta'] = pivot['Away'] - pivot['Home']
        
        pivot = pivot.sort_values('road_delta', ascending=False)
        
        plt.figure(figsize=(14, 12))
        teams = [get_full_team_name(t) for t in pivot.index]
        
        colors = ['green' if x > 0 else 'firebrick' for x in pivot['road_delta']]
        plt.barh(teams, pivot['road_delta'], color=colors, alpha=0.8)
        
        plt.title(f"ROAD WARRIORS: Home vs Away Performance Drop-off ({season})", fontsize=20, weight='bold')
        plt.xlabel("Net Rating Difference (Away - Home)", fontsize=14)
        plt.axvline(0, color='k')
        
        for i, val in enumerate(pivot['road_delta']):
            plt.text(val, i, f"{val:.1f}", va='center', fontweight='bold')
            
        plt.tight_layout()
        plt.savefig(f"the_road_warriors_{season}.png", dpi=300)
        plt.close()

if __name__ == "__main__":
    gauntlet = TheGauntlet()
    for season in SEASONS:
        gauntlet.generate_heatmap(season)
