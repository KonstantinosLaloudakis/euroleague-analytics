"""Fetch per-game box scores for the current season into mvp_all_game_stats_{S}.json.

Incremental: games already in the JSON are kept as-is and only played games
that are missing are requested (with retry/backoff from incremental_fetch),
so a throttled run can never replace a good file with a partial one.
The JSON keeps the nested player lists, so it is never round-tripped via CSV.
"""
import json
import os
import sys
import time

from euroleague_api import game_stats

from incremental_fetch import fetch_with_retry, played_gamecodes
from season_config import CURRENT_SEASON


def _gamecode(record):
    gc = record.get('GameCode', record.get('Gamecode'))
    try:
        return int(gc)
    except (TypeError, ValueError):
        return None


def game_codes_in(records):
    return {gc for gc in map(_gamecode, records) if gc is not None}


def load_records(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"  WARNING: could not read {path} ({e}); starting from empty")
        return []
    return data if isinstance(data, list) else []


def _write_atomic(records, path):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=4)
    os.replace(tmp, path)


def _save(records, path, floor):
    """Write records unless that would leave fewer games than `floor`."""
    n = len(game_codes_in(records))
    if n < floor:
        print(f"  WARNING: refusing to write {n} games over existing {floor}")
        return False
    _write_atomic(records, path)
    return True


def update_game_stats(path, gamecodes, fetch_one, delay=0.5, max_retries=4,
                      sleep=time.sleep, flush_every=10):
    """Append box scores for games in `gamecodes` missing from the JSON at `path`.

    fetch_one(gc) returns a DataFrame (one row per game). Returns
    (records, failed gamecodes). The file never ends up with fewer games
    than it started with.
    """
    records = load_records(path)
    have = game_codes_in(records)
    floor = len(have)
    missing = [gc for gc in gamecodes if gc not in have]
    if missing:
        print(f"  {len(have)} games cached, fetching {len(missing)} new: "
              f"{missing[:10]}{'...' if len(missing) > 10 else ''}")

    failed, pending = [], 0
    for gc in missing:
        df = fetch_with_retry(fetch_one, gc, max_retries=max_retries, sleep=sleep)
        if df is None:
            failed.append(gc)
            continue
        df = df.copy()
        df['GameCode'] = gc
        records.extend(json.loads(df.to_json(orient='records')))
        pending += 1
        if pending >= flush_every:
            _save(records, path, floor)   # survive CI kill mid-backfill
            pending = 0
        sleep(delay)

    if pending:
        _save(records, path, floor)
    if failed:
        print(f"  WARNING: {len(failed)} games failed, will retry next run: {failed}")
    return records, failed


def main():
    season = CURRENT_SEASON
    schedule_path = f'schedule_{season}.json'
    if not os.path.exists(schedule_path):
        print(f"{schedule_path} not found - run fetch_schedule.py first")
        return 1
    # The API returns non-empty frames with no players for unplayed games, so
    # only request games the schedule marks as played (Fetch Schedule runs first).
    game_codes = played_gamecodes(schedule_path)
    if not game_codes:
        print("No games played yet.")
        return 0

    out_path = f'mvp_all_game_stats_{season}.json'
    print(f"Box scores {season}: {len(game_codes)} played games in schedule")
    gst = game_stats.GameStats()
    records, _failed = update_game_stats(
        out_path, game_codes, lambda gc: gst.get_game_stats(season, gc))
    print(f"{out_path}: {len(game_codes_in(records))} games")
    # exit 1 only if games were played but nothing could be cached
    return 1 if not records else 0


if __name__ == "__main__":
    sys.exit(main())
