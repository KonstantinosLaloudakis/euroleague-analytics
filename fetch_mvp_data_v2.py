import pandas as pd
import json
import os
import sys
import time
from euroleague_api import game_stats
import traceback
from incremental_fetch import played_gamecodes
from season_config import CURRENT_SEASON

def fetch_mvp_data_iterative():
    season = CURRENT_SEASON
    gst = game_stats.GameStats()
    
    all_game_stats = []
    
    # We don't know exactly how many games per round or how many rounds.
    # But usually 9 games per round.
    # Providing Round Number is enough for get_game_stats? 
    # inspect says `get_game_stats(season, game_code)`? 
    # Or `get_game_stats(season, round, ...)`?
    # check_mvp_stats.py used `get_game_stats(2025, 1)`. 
    # If I have to iterate game codes, I need to know the range.
    # 18 teams -> 9 games/round * 34 rounds = 306 games.
    # Play-in/Playoffs add more.
    # Let's try fetching game 1 to 300.
    
    print(f"Fetching games for season {season}...")
    
    # We can fetch in batches.
    # If we hit a 404/Empty, we stop?
    # Games are usually 1-indexed.
    
    # The API returns non-empty frames with no players for unplayed games, so
    # iterate only over games the schedule marks as played (Fetch Schedule runs first).
    schedule_path = f'schedule_{season}.json'
    if not os.path.exists(schedule_path):
        print(f"{schedule_path} not found - run fetch_schedule.py first")
        sys.exit(1)
    game_codes = played_gamecodes(schedule_path)
    if not game_codes:
        print("No games played yet.")
        return

    consecutive_errors = 0
    for game_code in game_codes:
        try:
            df = gst.get_game_stats(season, game_code)
            if df is None or df.empty:
                consecutive_errors += 1
                if consecutive_errors > 10:
                    print(f"Stopped at Game {game_code} (10 consecutive empty).")
                    break
                continue
            consecutive_errors = 0
            df['GameCode'] = game_code
            all_game_stats.append(df)
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors > 20:
                print(f"Stopped at Game {game_code} (20 consecutive errors).")
                break

    if not all_game_stats:
        print("No data fetched!")
        return

    full_df = pd.concat(all_game_stats, ignore_index=True)
    print(f"\nFetched {len(full_df)} rows of stats.")
    
    # Save raw
    full_df.to_json(f'mvp_all_game_stats_{season}.json', orient='records', indent=4)
    print(f"Saved mvp_all_game_stats_{season}.json")

if __name__ == "__main__":
    fetch_mvp_data_iterative()
