import json
import os
import sys
import unicodedata
import pandas as pd
from euroleague_api.player_stats import PlayerStats
from season_config import ALL_SEASONS

OUT_FULL  = os.path.join('docs', 'data', 'current', 'player_career_stats.json')
OUT_INDEX = os.path.join('docs', 'data', 'current', 'player_index.json')

SEASONS = ALL_SEASONS


def season_label(code):
    """'E2024' -> '2024-25'"""
    year = int(code[1:])
    return f"{year}-{str(year + 1)[-2:]}"


def normalize_name(name):
    """Uppercase + strip diacritics for robust name→code lookup across API endpoints."""
    nfkd = unicodedata.normalize('NFD', name.upper())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def pct_to_float(val):
    """Convert '52.1%' -> 52.1, or pass through if already numeric."""
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip('%')
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def attempt_weighted_pct(seasons, made_key, att_key):
    """True career shooting %: Σ(made×gp) / Σ(attempts×gp) × 100."""
    total_made = sum((s.get(made_key) or 0) * (s['gp'] or 0) for s in seasons if s.get('gp'))
    total_att  = sum((s.get(att_key)  or 0) * (s['gp'] or 0) for s in seasons if s.get('gp'))
    return round(total_made / total_att * 100, 1) if total_att > 0 else None


def fetch_career_stats():
    force = '--force' in sys.argv
    if os.path.exists(OUT_FULL) and not force:
        print("player_career_stats.json exists — use --force to re-fetch")
        return

    print(f"Fetching per-season player traditional stats ({SEASONS[0]}-{SEASONS[-1]})…")
    ps = PlayerStats()

    frames = []
    for season_year in SEASONS:
        season_code = f"E{season_year}"
        print(f"  Fetching {season_label(season_code)}…", end=' ', flush=True)
        try:
            df = ps.get_player_stats_single_season(
                'traditional', season_year, statistic_mode='PerGame'
            )
            df['seasonCode'] = season_code
            frames.append(df)
            print(f"{len(df)} players")
        except Exception as e:
            print(f"ERROR: {e}")

    if not frames:
        print("No data fetched — aborting.")
        return

    df = pd.concat(frames, ignore_index=True)
    print(f"Total rows: {len(df)}")

    col_map = {
        'player.code':              'player_code',
        'player.name':              'player_name',
        'player.imageUrl':          'image_url',
        'player.team.code':         'team_code',
        'player.team.name':         'team_name',
        'gamesPlayed':              'gp',
        'pir':                      'pir',
        'pointsScored':             'ppg',
        'totalRebounds':            'rpg',
        'offensiveRebounds':        'oreb',
        'defensiveRebounds':        'dreb',
        'assists':                  'apg',
        'steals':                   'spg',
        'blocks':                   'bpg',
        'turnovers':                'tpg',
        'twoPointersMade':          'fg2_made',
        'twoPointersAttempted':     'fg2_att',
        'threePointersMade':        'fg3_made',
        'threePointersAttempted':   'fg3_att',
        'freeThrowsMade':           'ft_made',
        'freeThrowsAttempted':      'ft_att',
        'twoPointersPercentage':    'fg2_pct_raw',
        'threePointersPercentage':  'fg3_pct_raw',
        'freeThrowsPercentage':     'ft_pct_raw',
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    for raw_col, final_col in [('fg2_pct_raw', 'fg2_pct'),
                                ('fg3_pct_raw', 'fg3_pct'),
                                ('ft_pct_raw',  'ft_pct')]:
        if raw_col in df.columns:
            df[final_col] = df[raw_col].apply(pct_to_float)
            df.drop(columns=[raw_col], inplace=True)

    # Per-game display stats (rounded to 1 decimal for display)
    stat_cols = ['gp', 'ppg', 'rpg', 'oreb', 'dreb', 'apg',
                 'spg', 'bpg', 'tpg', 'fg2_pct', 'fg3_pct', 'ft_pct', 'pir']
    # Made/attempted stored per season for attempt-weighted career % computation
    made_att_cols = ['fg2_made', 'fg2_att', 'fg3_made', 'fg3_att', 'ft_made', 'ft_att']

    players_dict = {}
    index_list   = []
    name_to_code = {}
    name_collisions = set()

    for code, grp in df.groupby('player_code', sort=False):
        grp = grp.sort_values('seasonCode', ascending=False)
        row0 = grp.iloc[0]

        seasons = []
        for _, r in grp.iterrows():
            s = {
                'season':      season_label(r['seasonCode']),
                'season_code': r['seasonCode'],
                'team_code':   str(r.get('team_code', '')),
                'team_name':   str(r.get('team_name', '')),
            }
            for c in stat_cols:
                val = r.get(c)
                s[c] = round(float(val), 1) if pd.notna(val) else None
            for c in made_att_cols:
                val = r.get(c)
                s[c] = round(float(val), 2) if pd.notna(val) else None
            seasons.append(s)

        total_gp = sum(s['gp'] for s in seasons if s['gp'])

        # --- Career totals (fix 1): raw sums before rounding ---
        total_pts  = sum((s['ppg'] or 0) * (s['gp'] or 0) for s in seasons)
        total_ast  = sum((s['apg'] or 0) * (s['gp'] or 0) for s in seasons)
        total_reb  = sum((s['rpg'] or 0) * (s['gp'] or 0) for s in seasons)
        total_stl  = sum((s['spg'] or 0) * (s['gp'] or 0) for s in seasons)

        # --- Career averages (GP-weighted for rate stats) ---
        career = {'gp': total_gp,
                  'total_pts': round(total_pts, 1),
                  'total_ast': round(total_ast, 1),
                  'total_reb': round(total_reb, 1),
                  'total_stl': round(total_stl, 1)}

        for c in [c for c in stat_cols if c not in ('gp', 'fg2_pct', 'fg3_pct', 'ft_pct')]:
            vals = [(s[c], s['gp']) for s in seasons if s[c] is not None and s['gp']]
            career[c] = round(sum(v * g for v, g in vals) / sum(g for _, g in vals), 1) if vals else None

        # --- Career shooting %: attempt-weighted (fix 2) ---
        career['fg2_pct'] = attempt_weighted_pct(seasons, 'fg2_made', 'fg2_att')
        career['fg3_pct'] = attempt_weighted_pct(seasons, 'fg3_made', 'fg3_att')
        career['ft_pct']  = attempt_weighted_pct(seasons, 'ft_made',  'ft_att')

        name = str(row0.get('player_name', ''))
        raw_img = row0.get('image_url')
        image_url = str(raw_img) if raw_img and pd.notna(raw_img) else None
        players_dict[code] = {
            'name':        name,
            'image':       image_url,
            'position':    '',
            'nationality': '',
            'seasons':     seasons,
            'career':      career,
        }

        current_team = seasons[0]['team_code'] if seasons else ''
        index_list.append({
            'code':         code,
            'name':         name,
            'current_team': current_team,
            'seasons':      len(seasons),
        })

        # --- Name index: normalized key, collision detection (fixes 3 & 5) ---
        key = normalize_name(name)
        if key in name_to_code and name_to_code[key] != code:
            name_collisions.add(key)
        name_to_code[key] = code  # most recent iteration wins on collision

    if name_collisions:
        print(f"  Warning: {len(name_collisions)} name collision(s) in index: {name_collisions}")

    out = {
        'index':   sorted(index_list, key=lambda x: x['name']),
        'players': players_dict,
    }

    os.makedirs(os.path.dirname(OUT_FULL), exist_ok=True)
    with open(OUT_FULL, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f"Wrote {OUT_FULL} ({len(players_dict)} players)")

    with open(OUT_INDEX, 'w', encoding='utf-8') as f:
        json.dump(name_to_code, f, ensure_ascii=False, separators=(',', ':'))
    print(f"Wrote {OUT_INDEX} ({len(name_to_code)} entries)")


if __name__ == '__main__':
    fetch_career_stats()
