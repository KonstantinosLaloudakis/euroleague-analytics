"""Fetch current-season PBP-with-lineups and game metadata into data_cache/.

Outputs (consumed by calculate_rapm.py and calculate_lineups.py):
  data_cache/pbp_lineups_{season}.csv  - PBP rows with Lineup_{TEAMCODE} columns
  data_cache/games_{season}.csv        - game metadata (gamenumber, homecode, ...)
"""
import os
import sys

import pandas as pd
from euroleague_api import play_by_play_data
from euroleague_api.game_metadata import GameMetadata

from incremental_fetch import fetch_missing_games, played_gamecodes
from season_config import CURRENT_SEASON

CACHE_DIR = 'data_cache'


def _team_for(lineup_col, df):
    names = set()
    for lineup in df[lineup_col].dropna():
        names.update(lineup)
    owners = df.loc[df['PLAYER'].isin(names), 'CODETEAM'].dropna()
    return owners.mode().iloc[0] if not owners.empty else None


def to_team_lineup_columns(df):
    """Rename Lineup_A/Lineup_B to Lineup_{TEAMCODE}.

    euroleague_api 0.1 labels lineups A/B and leaves IsHomeTeam empty, so
    each side's team is the CODETEAM most often attached to its players.
    """
    df = df.copy()
    if 'Lineup_A' in df.columns and 'Lineup_B' in df.columns:
        rename = {}
        for col in ('Lineup_A', 'Lineup_B'):
            team = _team_for(col, df)
            if team and f'Lineup_{team}' not in rename.values():
                rename[col] = f'Lineup_{team}'
            else:
                gc = df['Gamecode'].iloc[0] if 'Gamecode' in df.columns and len(df) else '?'
                print(f"  WARNING: game {gc}: could not resolve a unique team for {col} "
                      f"(got {team!r}); leaving it unrenamed")
        df = df.rename(columns=rename)
    if 'Gamecode' in df.columns and 'GameCode' not in df.columns:
        df['GameCode'] = df['Gamecode']
    return df


def fetch_lineups(season=CURRENT_SEASON):
    pbp = play_by_play_data.PlayByPlay()
    path = os.path.join(CACHE_DIR, f'pbp_lineups_{season}.csv')
    gamecodes = played_gamecodes(f'schedule_{season}.json')
    print(f"Lineups {season}: {len(gamecodes)} played games in schedule")

    def fetch_one(gc):
        g = pbp.get_game_pbp_data_lineups(season, gc)
        return to_team_lineup_columns(g) if g is not None and not g.empty else g

    os.makedirs(CACHE_DIR, exist_ok=True)
    df, _failed = fetch_missing_games(path, gamecodes, fetch_one)
    print(f"{path}: {df['Gamecode'].nunique() if not df.empty else 0} games")
    return df


def normalize_games_metadata(df):
    """Add the gamenumber/homecode/awaycode columns calculate_rapm.py reads.

    GameMetadata (0.1.0) returns Gamecode, CodeTeamA (home), CodeTeamB (away).
    """
    df = df.copy()
    if 'gamenumber' not in df.columns and 'Gamecode' in df.columns:
        df['gamenumber'] = df['Gamecode']
    if 'homecode' not in df.columns and 'CodeTeamA' in df.columns:
        df['homecode'] = df['CodeTeamA']
    if 'awaycode' not in df.columns and 'CodeTeamB' in df.columns:
        df['awaycode'] = df['CodeTeamB']
    return df


def fetch_games_metadata(season=CURRENT_SEASON):
    path = os.path.join(CACHE_DIR, f'games_{season}.csv')
    df = GameMetadata().get_game_metadata_single_season(season)
    df = normalize_games_metadata(df)
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"{path}: {len(df)} games")
    return df


if __name__ == '__main__':
    n_played = len(played_gamecodes(f'schedule_{CURRENT_SEASON}.json'))
    if not n_played:
        print("No played games yet; nothing to fetch.")
        sys.exit(0)
    lineups = fetch_lineups()
    games = fetch_games_metadata()
    # exit 1 only if games were played but nothing could be cached
    sys.exit(1 if lineups.empty or games.empty else 0)
