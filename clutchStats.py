import pandas as pd
from euroleague_api import play_by_play_data
import json

def get_seconds_from_time(time_str):
    """Converts MM:SS time string to total seconds."""
    try:
        minutes, seconds = map(int, str(time_str).split(':'))
        return minutes * 60 + seconds
    except (ValueError, AttributeError):
        return 0

def analyze_clutch_stats(start_season=2023, end_season=2024, full_df=None,
                         output_path='clutch_stats_multiple_seasons.json'):
    """Compute clutch stats per season. Pass full_df (play-by-play) to skip the API fetch."""
    if full_df is None:
        pbp = play_by_play_data.PlayByPlay()

        print(f"Fetching play-by-play data for seasons {start_season}-{end_season}...")
        try:
            # Use bulk fetch method
            full_df = pbp.get_game_play_by_play_data_range_seasons(start_season, end_season)
        except Exception as e:
            print(f"Error fetching data: {e}")
            return

    if full_df.empty:
        print("No data fetched.")
        return

    print(f"Total rows fetched: {len(full_df)}")
    
    # Ensure correct sorting for forward fill: Gamecode -> Period -> Time (desc) or PlayNumber
    if 'NUMBEROFPLAY' in full_df.columns:
        full_df = full_df.sort_values(['Gamecode', 'NUMBEROFPLAY'])
    else:
        # Fallback: assume loosely sorted or sort by Period/Time
        # Note: Time string sort might be wrong ("10:00" vs "2:00"). 
        # But usually API returns chronological.
        pass

    # Forward fill scores for each game to handle NaNs in non-scoring plays
    if 'POINTS_A' in full_df.columns and 'POINTS_B' in full_df.columns:
        full_df['POINTS_A'] = pd.to_numeric(full_df['POINTS_A'], errors='coerce')
        full_df['POINTS_B'] = pd.to_numeric(full_df['POINTS_B'], errors='coerce')
        
        full_df['POINTS_A'] = full_df.groupby('Gamecode')['POINTS_A'].ffill().fillna(0)
        full_df['POINTS_B'] = full_df.groupby('Gamecode')['POINTS_B'].ffill().fillna(0)
    else:
        print("Score columns not found!")
        return
    
    # 1. Filter for Clutch Moments
    if 'MARKERTIME' in full_df.columns:
         full_df['SecondsRemaining'] = full_df['MARKERTIME'].apply(get_seconds_from_time)
    else:
        print("MARKERTIME column not found!")
        return

    if 'PERIOD' in full_df.columns:
        full_df['PERIOD'] = pd.to_numeric(full_df['PERIOD'], errors='coerce')
        clutch_df = full_df[full_df['PERIOD'] >= 4].copy()
    else:
        print("PERIOD column not found!")
        return

    # Calculate Pre-Play Margin to determine if the situation was clutch BEFORE the event
    # Shift scores to get the state at the start of the play
    full_df['Prev_POINTS_A'] = full_df.groupby('Gamecode')['POINTS_A'].shift(1).fillna(0)
    full_df['Prev_POINTS_B'] = full_df.groupby('Gamecode')['POINTS_B'].shift(1).fillna(0)
    
    full_df['PrePlayMargin'] = abs(full_df['Prev_POINTS_A'] - full_df['Prev_POINTS_B'])
    
    # 1. Filter for Clutch Moments (Time)
    if 'MARKERTIME' in full_df.columns:
         full_df['SecondsRemaining'] = full_df['MARKERTIME'].apply(get_seconds_from_time)
    else:
        print("MARKERTIME column not found!")
        return

    if 'PERIOD' in full_df.columns:
        full_df['PERIOD'] = pd.to_numeric(full_df['PERIOD'], errors='coerce')
        clutch_df = full_df[full_df['PERIOD'] >= 4].copy()
    else:
        print("PERIOD column not found!")
        return

    # Filter Time <= 5 mins (300 seconds)
    clutch_df = clutch_df[clutch_df['SecondsRemaining'] <= 300]
    
    # Filter Clutch Score <= 5 using Pre-Play Margin
    # "Clutch" means the score *was* <= 5 when the play started.
    clutch_df = clutch_df[clutch_df['PrePlayMargin'] <= 5]
    
    # Also calculate current margin just for reference or debugging
    clutch_df['ScoreMargin'] = abs(clutch_df['POINTS_A'] - clutch_df['POINTS_B'])
        
    print(f"Found {len(clutch_df)} clutch plays.")
    
    # Calculate Stats per Season per Player
    results_by_season = {}
    
    # We need to process each season separately to find "Best of Season X"
    for season in range(start_season, end_season + 1):
        season_clutch_df = clutch_df[clutch_df['Season'] == season]
        
        player_stats = {}
        
        for index, row in season_clutch_df.iterrows():
            play_type = row.get('PLAYTYPE', '')
            player_name = row.get('PLAYER', 'Unknown')
            team_code = row.get('CODETEAM', '')

            if not player_name or pd.isna(player_name):
                continue
                
            if player_name not in player_stats:
                player_stats[player_name] = {
                    'Player': player_name,
                    'Team': team_code,
                    'Season': season,
                    'ClutchPoints': 0,
                    'ClutchFGM': 0,
                    'ClutchFGA': 0,
                    'ClutchFTM': 0,
                    'ClutchFTA': 0,
                    'Clutch3PM': 0,
                    'ClutchFoulsDrawn': 0, 
                    'ClutchTurnovers': 0
                }
                
            stats = player_stats[player_name]
            
            if play_type == '2FGM':
                stats['ClutchPoints'] += 2
                stats['ClutchFGM'] += 1
                stats['ClutchFGA'] += 1
            elif play_type == '2FGA':
                stats['ClutchFGA'] += 1
            elif play_type == '3FGM':
                stats['ClutchPoints'] += 3
                stats['ClutchFGM'] += 1
                stats['ClutchFGA'] += 1
                stats['Clutch3PM'] += 1
            elif play_type == '3FGA':
                stats['ClutchFGA'] += 1
            elif play_type == 'FTM':
                stats['ClutchPoints'] += 1
                stats['ClutchFTM'] += 1
                stats['ClutchFTA'] += 1
            elif play_type == 'FTA': # Missed FT
                 stats['ClutchFTA'] += 1
            elif play_type == 'TO':
                stats['ClutchTurnovers'] += 1
            elif play_type == 'RV':
                stats['ClutchFoulsDrawn'] += 1
        
        # Format Results for Season
        season_results = []
        for p_name, stats in player_stats.items():
            if stats['ClutchPoints'] == 0 and stats['ClutchFGA'] == 0:
                continue
                
            # FG%
            if stats['ClutchFGA'] > 0:
                stats['FG%'] = f"{(stats['ClutchFGM'] / stats['ClutchFGA']) * 100:.1f}%"
            else:
                stats['FG%'] = "N/A"
                
            # FT%
            if stats['ClutchFTA'] > 0:
                stats['FT%'] = f"{(stats['ClutchFTM'] / stats['ClutchFTA']) * 100:.1f}%"
            else:
                stats['FT%'] = "N/A"

            season_results.append(stats)
            
        # Sort and Store
        season_results.sort(key=lambda x: x['ClutchPoints'], reverse=True)
        results_by_season[season] = season_results

    # Save to JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results_by_season, f, indent=4, ensure_ascii=False)
        
    print(f"Saved results to {output_path}")
    
    for season, data in results_by_season.items():
        print(f"\nTop 5 Clutch Scorers Season {season}:")
        for i in range(min(5, len(data))):
            print(f"{i+1}. {data[i]['Player']} ({data[i]['Team']}) - {data[i]['ClutchPoints']} pts")

if __name__ == "__main__":
    # Example: Analyze 2023 and 2024
    analyze_clutch_stats(2023, 2024)
