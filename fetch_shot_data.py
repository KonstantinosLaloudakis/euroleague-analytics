import argparse
import os
import shutil
import sys

from euroleague_api import shot_data

from incremental_fetch import fetch_missing_games, played_gamecodes
from season_config import CURRENT_SEASON


def fetch_and_cache_shot_data(season=CURRENT_SEASON):
    # Save both in data folder and in root to ensure compatibility with all scripts
    file_path_data = f'data/shot_data_{season}_{season}.csv'
    file_path_root = f'shot_data_{season}_{season}.csv'

    if '--rebuild' in sys.argv:
        for p in (file_path_data, file_path_root):
            if os.path.exists(p):
                os.remove(p)
    os.makedirs('data', exist_ok=True)
    # Seed the data/ cache from the root copy if only that exists
    if not os.path.exists(file_path_data) and os.path.exists(file_path_root):
        shutil.copyfile(file_path_root, file_path_data)

    shots = shot_data.ShotData()
    gamecodes = played_gamecodes(f'schedule_{season}.json')
    print(f"Shot data {season}: {len(gamecodes)} played games in schedule")
    df, failed = fetch_missing_games(
        file_path_data, gamecodes, lambda gc: shots.get_game_shot_data(season, gc))

    if os.path.exists(file_path_data):
        shutil.copyfile(file_path_data, file_path_root)
    print(f"{file_path_data}: {len(df)} shots, {df['Gamecode'].nunique() if not df.empty else 0} games")
    return df, failed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch Euroleague shot data')
    parser.add_argument('--season', type=int, default=CURRENT_SEASON,
                        help=f'Season year to fetch (default: {CURRENT_SEASON})')
    parser.add_argument('--force', action='store_true', help='No-op (kept for compatibility)')
    parser.add_argument('--rebuild', action='store_true', help='Discard cache and re-fetch everything')
    args = parser.parse_args()
    df, failed = fetch_and_cache_shot_data(season=args.season)
    sys.exit(1 if df.empty else 0)
