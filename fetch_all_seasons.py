"""
Fetch PBP data for all Euroleague seasons from 2007-08 to the current season.
Saves each season as data_cache/pbp_{year}.csv.

Completed seasons never change: they are fetched only if the cache file is
missing. The current season is fetched incrementally, one played game at a
time (schedule_{S}.json), so a throttled run only ever adds games and never
publishes a partial season over a complete one.
"""
import os
import shutil
import sys

from euroleague_api import play_by_play_data

from incremental_fetch import fetch_missing_games, played_gamecodes
from season_config import ALL_SEASONS, CURRENT_SEASON

CACHE_DIR = 'data_cache'


def schedule_lookup(schedule_rows):
    """gamecode -> (Phase, Round) from schedule rows (round='RS'/'PO'..., gameday=round no.)."""
    out = {}
    for r in schedule_rows:
        gc = int(str(r['gamecode']).split('_')[-1])
        gameday = str(r.get('gameday', ''))
        out[gc] = (r.get('round'), int(gameday) if gameday.isdigit() else gameday)
    return out


def with_phase_round(df, gc, lookup):
    """Per-game PBP lacks the Phase/Round columns the season-range call adds."""
    if df is None or df.empty or 'Round' in df.columns:
        return df
    phase, rnd = lookup.get(gc, (None, None))
    df = df.copy()
    df.insert(1, 'Phase', phase)
    df.insert(2, 'Round', rnd)
    return df


def _load_schedule(season):
    import json
    path = f'schedule_{season}.json'
    if not os.path.exists(path):
        # normally committed by the refresh workflow; fetch it if absent
        from fetch_schedule import fetch_and_cache_schedule
        fetch_and_cache_schedule(season)
    with open(path, encoding='utf-8') as f:
        return path, json.load(f)


def fetch_current_season(season, pbp, cache_dir=CACHE_DIR):
    cache_path = os.path.join(cache_dir, f'pbp_{season}.csv')
    schedule_path, rows = _load_schedule(season)
    gamecodes = played_gamecodes(schedule_path)
    lookup = schedule_lookup(rows)
    print(f"  [INCREMENTAL] Season {season}: {len(gamecodes)} played games in schedule")
    df, failed = fetch_missing_games(
        cache_path, gamecodes,
        lambda gc: with_phase_round(pbp.get_game_play_by_play_data(season, gc), gc, lookup))
    n = df['Gamecode'].nunique() if not df.empty else 0
    print(f"    {cache_path}: {n} games")
    return df, failed


def fetch_completed_season(year, pbp, cache_dir=CACHE_DIR):
    cache_path = os.path.join(cache_dir, f'pbp_{year}.csv')
    root_path = f'pbp_{year}.csv'  # some files might be in root from earlier
    if os.path.exists(cache_path):
        print(f"  [SKIP] {cache_path} already exists")
        return
    if os.path.exists(root_path):
        print(f"  [MOVE] {root_path} -> {cache_path}")
        shutil.move(root_path, cache_path)
        return
    print(f"  [FETCH] Season {year}-{str(year+1)[-2:]}...")
    try:
        df = pbp.get_game_play_by_play_data_range_seasons(year, year)
        if df is not None and len(df) > 0:
            df.to_csv(cache_path, index=False)
            print(f"    Saved {len(df)} events to {cache_path}")
        else:
            print(f"    WARNING: No data for season {year}")
    except Exception as e:
        print(f"    ERROR fetching season {year}: {e}")


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    pbp = play_by_play_data.PlayByPlay()
    for year in ALL_SEASONS:
        if year == CURRENT_SEASON:
            fetch_current_season(year, pbp)
        else:
            fetch_completed_season(year, pbp)
    print("\nDone! All seasons fetched.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
