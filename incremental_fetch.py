"""Per-game incremental fetching for the current season.

Re-downloading a whole season every night got CI throttled (HTTP 429), so
fetchers only request played games that are not cached yet, pause between
calls, and back off when the API returns nothing for a game that was played
(euroleague_api turns 429s into empty frames).
"""
import json
import os
import time

import pandas as pd


def played_gamecodes(schedule_path):
    """Gamecodes (int) of played games from a schedule_{season}.json file."""
    with open(schedule_path, encoding='utf-8') as f:
        rows = json.load(f)
    codes = {int(str(r['gamecode']).split('_')[-1])
             for r in rows if str(r.get('played', '')).lower() == 'true'}
    return sorted(codes)


def _write_atomic(df, cache_path):
    tmp = cache_path + '.tmp'
    df.to_csv(tmp, index=False)
    os.replace(tmp, cache_path)


def fetch_missing_games(cache_path, gamecodes, fetch_one, gamecode_col='Gamecode',
                        delay=0.5, max_retries=4, sleep=time.sleep, flush_every=10):
    """Fetch games in `gamecodes` that aren't in the CSV at `cache_path`.

    Returns (full DataFrame, list of gamecodes that still failed).
    """
    existing = pd.DataFrame()
    if os.path.exists(cache_path):
        existing = pd.read_csv(cache_path, low_memory=False)
    have = set()
    if not existing.empty and gamecode_col in existing.columns:
        have = set(existing[gamecode_col].dropna().astype(int))

    missing = [gc for gc in gamecodes if gc not in have]
    if missing:
        print(f"  {len(have)} games cached, fetching {len(missing)} new: {missing[:10]}{'...' if len(missing) > 10 else ''}")

    new_frames, failed = [], []
    for gc in missing:
        df = None
        for attempt in range(1 + max_retries):
            try:
                df = fetch_one(gc)
            except Exception as e:
                print(f"    game {gc}: {type(e).__name__}: {e}")
                df = None
            if df is not None and not df.empty:
                break
            if attempt < max_retries:
                sleep(4 * 2 ** attempt)   # 4, 8, 16, 32s
        if df is None or df.empty:
            failed.append(gc)
            continue
        if gamecode_col not in df.columns:
            df[gamecode_col] = gc
        new_frames.append(df)
        if len(new_frames) >= flush_every:
            existing = pd.concat([existing, *new_frames], ignore_index=True)
            new_frames = []
            _write_atomic(existing, cache_path)   # survive CI kill mid-backfill
        sleep(delay)

    if new_frames:
        existing = pd.concat([existing, *new_frames], ignore_index=True)
        _write_atomic(existing, cache_path)
    if failed:
        print(f"  WARNING: {len(failed)} games failed, will retry next run: {failed}")
    return existing, failed
