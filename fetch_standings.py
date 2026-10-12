"""Fetch the official Euroleague standings after every played regular-season round.

Rounds 1..R are fetched, where R is the highest `gameday` among played
regular-season games in `schedule_{S}.json` (run fetch_schedule.py first).
Writes `standings_{S}.json` at the repo root, next to `schedule_{S}.json`:

    {"season": S, "rounds": {"1": [{"code", "position", "wins", "losses",
                                    "points_diff", "points_for"}, ...], ...}}

export_dashboard_data.py takes the table order and the Standings Race ranks
from this file. A round whose API call fails keeps its previously cached entry.
"""
import json
import os

from season_config import CURRENT_SEASON


def get_round_standings(season, rnd):
    """Official standings DataFrame after round `rnd` (Euroleague API)."""
    from euroleague_api.standings import Standings
    return Standings().get_standings(season, rnd)


def last_played_round(schedule_rows):
    """Highest regular-season gameday with a played game (0 if none)."""
    rounds = [int(row.get('gameday') or 0) for row in schedule_rows or []
              if str(row.get('round', '')).upper() == 'RS'
              and str(row.get('played', '')).lower() == 'true']
    return max(rounds, default=0)


def parse_standings(df):
    """API DataFrame → list of row dicts sorted by position."""
    rows = [{
        'code': str(r['club.code']),
        'position': int(r['position']),
        'wins': int(r['gamesWon']),
        'losses': int(r['gamesLost']),
        'points_diff': int(str(r['pointsDifference']).replace('+', '')),
        'points_for': int(r['pointsFor']),
    } for _, r in df.iterrows()]
    return sorted(rows, key=lambda r: r['position'])


def _load(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def main():
    season = CURRENT_SEASON
    schedule = _load(f'schedule_{season}.json')
    last_round = last_played_round(schedule)
    if not schedule or last_round == 0:
        print(f"No played regular-season rounds in schedule_{season}.json; skipping standings fetch.")
        return 0

    out_path = f'standings_{season}.json'
    cached = (_load(out_path) or {}).get('rounds', {})
    rounds = {}
    for rnd in range(1, last_round + 1):
        try:
            rounds[str(rnd)] = parse_standings(get_round_standings(season, rnd))
        except Exception as e:
            print(f"  [WARN] Standings for round {rnd} failed ({e}); keeping cached entry.")
            if str(rnd) in cached:
                rounds[str(rnd)] = cached[str(rnd)]

    tmp_path = out_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump({'season': season, 'rounds': rounds}, f, indent=2)
    os.replace(tmp_path, out_path)
    print(f"Saved official standings for {len(rounds)} round(s) to {out_path}")
    return 0


if __name__ == '__main__':
    main()
