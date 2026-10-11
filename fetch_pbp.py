import os
import sys

from euroleague_api import play_by_play_data

from incremental_fetch import fetch_missing_games, played_gamecodes
from season_config import CURRENT_SEASON


def fetch_and_cache_pbp(season=CURRENT_SEASON):
    file_path = f'pbp_{season}.csv'
    if '--rebuild' in sys.argv and os.path.exists(file_path):
        os.remove(file_path)
    pbp = play_by_play_data.PlayByPlay()
    gamecodes = played_gamecodes(f'schedule_{season}.json')
    print(f"Play-by-play {season}: {len(gamecodes)} played games in schedule")
    df, failed = fetch_missing_games(
        file_path, gamecodes, lambda gc: pbp.get_game_play_by_play_data(season, gc))
    print(f"{file_path}: {len(df)} events, {df['Gamecode'].nunique() if not df.empty else 0} games")
    return df, failed


if __name__ == '__main__':
    df, failed = fetch_and_cache_pbp()
    sys.exit(1 if df.empty else 0)
