"""
Export all season analytics data to docs/data/current/dashboard.json
for the Season Hub web page.

Usage:
    python export_dashboard_data.py

Reads from root dir JSON files; writes to docs/data/current/dashboard.json
"""

import json
import os
import glob
import re
import numpy as np
import pandas as pd

from season_config import CURRENT_SEASON, COMPLETED_SEASONS, season_label

S = CURRENT_SEASON

# ── Team name mapping ────────────────────────────────────────────────────────
TEAM_NAMES = {
    'BER': 'ALBA Berlin',
    'IST': 'Anadolu Efes',
    'MCO': 'AS Monaco',
    'BAS': 'Baskonia',
    'RED': 'Crvena Zvezda',
    'MIL': 'EA7 Milan',
    'BAR': 'FC Barcelona',
    'MUN': 'Bayern Munich',
    'ULK': 'Fenerbahce',
    'ASV': 'ASVEL',
    'TEL': 'Maccabi Tel Aviv',
    'OLY': 'Olympiacos',
    'PAN': 'Panathinaikos',
    'PAR': 'Partizan',
    'PRS': 'Paris Basketball',
    'MAD': 'Real Madrid',
    'PAM': 'Valencia Basket',
    'VIR': 'Virtus Bologna',
    'ZAL': 'Zalgiris',
    'DUB': 'Dubai Basketball',
    'BES': 'Besiktas Istanbul',
    'HTA': 'Hapoel Tel Aviv',
}


def load_json(path):
    """Load JSON file, return None on failure."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  [WARN] Could not load {path}: {e}")
        return None


def regular_season_complete(schedule_rows):
    """True once every regular-season game in the schedule has been played.
    Playoff forecasts (championship odds, path to title, series) are only
    meaningful once the seeds are final."""
    rs = [r for r in (schedule_rows or []) if r.get('round') == 'RS']
    return bool(rs) and all(str(r.get('played', '')).lower() == 'true' for r in rs)


def load_with_fallback(suffix, base_name, fallback_name=None, strict=False):
    """Try loading base_name+suffix first, fall back to fallback_name or base_name.

    strict=True: with a round suffix, return None when this round's file is
    missing instead of falling back to a stale unsuffixed (previous-season) file.
    """
    if strict and not suffix:
        print(f"  [SKIP] {base_name}: no round suffix, cannot trust an unsuffixed file (strict)")
        return None
    if suffix:
        candidate = base_name.replace('.json', f'{suffix}.json')
        if strict and not os.path.exists(candidate):
            print(f"  [SKIP] {candidate} not found (no stale fallback)")
            return None
        data = load_json(candidate)
        if data is not None:
            print(f"  Loaded: {candidate}")
            return data
    fallback = fallback_name or base_name
    data = load_json(fallback)
    if data is not None:
        print(f"  Loaded: {fallback}")
    return data


def parse_schedule_dates():
    """Parse the current season official schedule XML → {(homecode, awaycode): {'date': ..., 'time': ...}}."""
    dates = {}
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(f'official_schedule_{S}.xml')
        for item in tree.getroot().iter('item'):
            home = (item.findtext('homecode') or '').strip()
            away = (item.findtext('awaycode') or '').strip()
            date = (item.findtext('date') or '').strip()
            time = (item.findtext('startime') or '').strip()
            if home and away and date:
                dates[(home, away)] = {'date': date, 'time': time}
    except Exception as e:
        print(f"  [WARN] Could not parse schedule XML: {e}")
    return dates


def find_latest_oracle_forecast():
    """Scan for oracle_forecast_round_*_ml.json or oracle_forecast_round_*.json,
    pick highest round number. Returns (path, round_num) or (None, None)."""
    best_round = -1
    best_path = None

    # Prefer ML variants
    for pattern in ['oracle_forecast_round_*_ml.json', 'oracle_forecast_round_*.json']:
        for fpath in glob.glob(pattern):
            m = re.search(r'oracle_forecast_round_(\d+)', fpath)
            if m:
                rnum = int(m.group(1))
                if rnum > best_round:
                    best_round = rnum
                    best_path = fpath

    if best_path:
        print(f"  Latest oracle forecast: {best_path} (Round {best_round})")
    return best_path, best_round


def find_latest_player_forecast(oracle_round):
    """Find player forecast for the same round as oracle."""
    if oracle_round and oracle_round > 0:
        # Try ML variant first
        candidates = [
            f'player_forecast_round_{oracle_round}_ml.json',
            f'player_forecast_round_{oracle_round}.json',
        ]
        for c in candidates:
            if os.path.exists(c):
                print(f"  Loaded player forecast: {c}")
                return load_json(c)
    return None


def build_player_stats(mvp_data, current_round=5):
    """Aggregate per-player season averages from mvp_all_game_stats for the current season."""
    from collections import defaultdict

    all_stats = load_json(f'mvp_all_game_stats_{S}.json')
    if not all_stats:
        return []

    # Build rankings lookup by player name
    rankings_lookup = {}
    if mvp_data:
        for row in mvp_data:
            rankings_lookup[row.get('PlayerName', '')] = row

    agg = defaultdict(lambda: {
        'name': '', 'team': '', 'position': '',
        'pts': [], 'reb': [], 'ast': [], 'stl': [], 'to_': [], 'blk': [],
        'pir': [], 'fg2m': 0, 'fg2a': 0, 'fg3m': 0, 'fg3a': 0,
        'ftm': 0, 'fta': 0,
    })

    for game in all_stats:
        for side in ('local.players', 'road.players'):
            for entry in game.get(side, []):
                p = entry.get('player', {})
                s = entry.get('stats', {})
                code = p.get('person', {}).get('code', '')
                name = p.get('person', {}).get('name', '')
                team = p.get('club', {}).get('code', '')
                pos = p.get('positionName', '')
                if not code or not name:
                    continue
                # Skip DNPs (no minutes and no stats)
                if s.get('timePlayed', 0) == 0 and s.get('points', 0) == 0 and s.get('valuation', 0) == 0:
                    continue
                d = agg[code]
                d['name'] = name
                d['team'] = team
                d['position'] = pos
                d['pts'].append(s.get('points', 0))
                d['reb'].append(s.get('totalRebounds', 0))
                d['ast'].append(s.get('assistances', 0))
                d['stl'].append(s.get('steals', 0))
                d['to_'].append(s.get('turnovers', 0))
                d['blk'].append(s.get('blocksFavour', 0))
                d['pir'].append(s.get('valuation', 0))
                d['fg2m'] += s.get('fieldGoalsMade2', 0)
                d['fg2a'] += s.get('fieldGoalsAttempted2', 0)
                d['fg3m'] += s.get('fieldGoalsMade3', 0)
                d['fg3a'] += s.get('fieldGoalsAttempted3', 0)
                d['ftm'] += s.get('freeThrowsMade', 0)
                d['fta'] += s.get('freeThrowsAttempted', 0)

    def avg(lst): return round(sum(lst) / len(lst), 1) if lst else 0.0

    result = []
    for code, d in agg.items():
        gp = len(d['pts'])
        if gp < min(5, max(1, current_round)):
            continue
        fgm = d['fg2m'] + d['fg3m']
        fga = d['fg2a'] + d['fg3a']
        rnk = rankings_lookup.get(d['name'], {})
        result.append({
            'code': code,
            'name': d['name'],
            'team': d['team'],
            'position': d['position'],
            'gp': gp,
            'avg_pts': avg(d['pts']),
            'avg_reb': avg(d['reb']),
            'avg_ast': avg(d['ast']),
            'avg_stl': avg(d['stl']),
            'avg_to': avg(d['to_']),
            'avg_blk': avg(d['blk']),
            'avg_pir': avg(d['pir']),
            'fg_pct': round(fgm / fga * 100, 1) if fga > 0 else 0.0,
            'fg3_pct': round(d['fg3m'] / d['fg3a'] * 100, 1) if d['fg3a'] > 0 else 0.0,
            'ft_pct': round(d['ftm'] / d['fta'] * 100, 1) if d['fta'] > 0 else 0.0,
            'mvp_score': round(rnk.get('MVP_Score', 0.0), 1),
            'mvp_rank': rnk.get('MVP_Rank', 0),
            'wpa': round(rnk.get('WPA', 0.0), 1),
            'consistency': round(rnk.get('Consistency', 0.0), 3),
            'clutch_eff': round(rnk.get('ClutchEff', 0.0), 3),
        })

    result.sort(key=lambda x: -x['avg_pir'])
    return result


def build_playoff_player_stats():
    """Aggregate per-player averages from playoff games only (Gamecode > 380)."""
    from collections import defaultdict

    all_stats = load_json(f'mvp_all_game_stats_{S}.json')
    if not all_stats:
        return []

    playoff_games = [g for g in all_stats if g.get('Gamecode', 0) > 380]
    if not playoff_games:
        return []

    agg = defaultdict(lambda: {
        'name': '', 'team': '',
        'pts': [], 'reb': [], 'ast': [], 'stl': [], 'blk': [], 'to_': [], 'pir': [],
    })

    for game in playoff_games:
        for side in ('local.players', 'road.players'):
            for entry in game.get(side, []):
                p = entry.get('player', {})
                s = entry.get('stats', {})
                code = p.get('person', {}).get('code', '')
                name = p.get('person', {}).get('name', '')
                team = p.get('club', {}).get('code', '')
                if not code or not name:
                    continue
                # Skip DNPs
                if s.get('timePlayed', 0) == 0 and s.get('points', 0) == 0 and s.get('valuation', 0) == 0:
                    continue
                d = agg[code]
                d['name'] = name
                d['team'] = team
                d['pts'].append(s.get('points', 0))
                d['reb'].append(s.get('totalRebounds', 0))
                d['ast'].append(s.get('assistances', 0))
                d['stl'].append(s.get('steals', 0))
                d['blk'].append(s.get('blocksFavour', 0))
                d['to_'].append(s.get('turnovers', 0))
                d['pir'].append(s.get('valuation', 0))

    def avg(lst): return round(sum(lst) / len(lst), 1) if lst else 0.0

    result = []
    for code, d in agg.items():
        gp = len(d['pts'])
        if gp < 1:
            continue
        result.append({
            'code': code,
            'name': d['name'],
            'team': d['team'],
            'gp': gp,
            'avg_pts': avg(d['pts']),
            'avg_reb': avg(d['reb']),
            'avg_ast': avg(d['ast']),
            'avg_stl': avg(d['stl']),
            'avg_blk': avg(d['blk']),
            'avg_to':  avg(d['to_']),
            'avg_pir': avg(d['pir']),
        })

    result.sort(key=lambda x: -x['avg_pir'])
    return result


# ── Shot stats aggregation ────────────────────────────────────────────────
def build_shot_stats():
    """Aggregate shot data by zone for league, team, and player breakdowns."""
    import csv
    shot_file = f'shot_data_{S}_{S}.csv'
    if not os.path.exists(shot_file):
        print(f"  {shot_file} not found — skipping shot stats.")
        return None
    print(f"\n--- Building shot stats from {shot_file} ---")

    from collections import defaultdict

    ZONES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    ZONE_NAMES = {
        'A': 'At Rim', 'B': 'Left Paint', 'C': 'Right Paint',
        'D': 'Left Mid', 'E': 'Right Mid', 'F': 'Left Extended',
        'G': 'Right Extended', 'H': 'Left 3PT', 'I': 'Right 3PT', 'J': 'Deep 3PT',
    }

    def new_zone(): return {'attempts': 0, 'makes': 0, 'pts': 0}

    league = {z: new_zone() for z in ZONES}
    teams = defaultdict(lambda: {z: new_zone() for z in ZONES})
    players = defaultdict(lambda: {'team': '', 'zones': {z: new_zone() for z in ZONES}, 'total_fga': 0})

    with open(shot_file, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            zone = row.get('ZONE', '').strip()
            if zone not in ZONES:
                continue
            action = row.get('ID_ACTION', '')
            if action == 'FTM':
                continue  # free throws don't have meaningful zone data
            team_code = row.get('TEAM', '')
            player = row.get('PLAYER', '')
            pts = int(row.get('POINTS', 0))
            made = action in ('2FGM', '3FGM')

            # League
            league[zone]['attempts'] += 1
            if made:
                league[zone]['makes'] += 1
                league[zone]['pts'] += pts

            # Team
            teams[team_code][zone]['attempts'] += 1
            if made:
                teams[team_code][zone]['makes'] += 1
                teams[team_code][zone]['pts'] += pts

            # Player
            players[player]['team'] = team_code
            players[player]['zones'][zone]['attempts'] += 1
            players[player]['total_fga'] += 1
            if made:
                players[player]['zones'][zone]['makes'] += 1
                players[player]['zones'][zone]['pts'] += pts

    def finalize(zone_dict):
        result = {}
        for z, d in zone_dict.items():
            att = d['attempts']
            if att == 0:
                continue
            result[z] = {
                'attempts': att,
                'makes': d['makes'],
                'fg_pct': round(d['makes'] / att * 100, 1),
                'pps': round(d['pts'] / att, 2),  # points per shot
            }
        return result

    # Filter players: min 50 FGA
    filtered_players = {}
    for name, pdata in players.items():
        if pdata['total_fga'] >= 50:
            filtered_players[name] = {
                'team': pdata['team'],
                'total_fga': pdata['total_fga'],
                'zones': finalize(pdata['zones']),
            }

    # ── Heatmap grid ─────────────────────────────────────────────────────────
    GRID_COLS, GRID_ROWS = 25, 25
    X_MIN, X_MAX = -740, 740
    Y_MIN, Y_MAX = -100, 1300
    cell_w = (X_MAX - X_MIN) / GRID_COLS
    cell_h = (Y_MAX - Y_MIN) / GRID_ROWS

    def new_grid():
        return [[{'att': 0, 'makes': 0} for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]

    league_grid = new_grid()
    team_grids = defaultdict(new_grid)

    with open(shot_file, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            action = row.get('ID_ACTION', '')
            if action not in ('2FGM', '2FGA', '3FGM', '3FGA'):
                continue
            try:
                x = int(row['COORD_X'])
                y = int(row['COORD_Y'])
            except (ValueError, KeyError):
                continue
            col = min(GRID_COLS - 1, max(0, int((x - X_MIN) / cell_w)))
            r   = min(GRID_ROWS - 1, max(0, int((y - Y_MIN) / cell_h)))
            made = 1 if action in ('2FGM', '3FGM') else 0
            team_code = row.get('TEAM', '')

            league_grid[r][col]['att'] += 1
            league_grid[r][col]['makes'] += made
            team_grids[team_code][r][col]['att'] += 1
            team_grids[team_code][r][col]['makes'] += made

    def grid_to_arrays(grid, min_att=3):
        """Convert grid to fg_pct and attempts 2D arrays with smoothing."""
        fg = []
        att = []
        for r in range(GRID_ROWS):
            fg_row = []
            att_row = []
            for c in range(GRID_COLS):
                cell = grid[r][c]
                if cell['att'] >= min_att:
                    fg_row.append(round(cell['makes'] / cell['att'] * 100, 1))
                    att_row.append(cell['att'])
                else:
                    fg_row.append(None)
                    att_row.append(0)
            fg.append(fg_row)
            att.append(att_row)
        return {'fg_pct': fg, 'attempts': att}

    grid_data = {
        'cols': GRID_COLS, 'rows': GRID_ROWS,
        'x_min': X_MIN, 'x_max': X_MAX,
        'y_min': Y_MIN, 'y_max': Y_MAX,
        'league': grid_to_arrays(league_grid, min_att=5),
        'teams': {code: grid_to_arrays(g, min_att=2) for code, g in team_grids.items()},
    }

    output = {
        'zone_names': ZONE_NAMES,
        'league': finalize(league),
        'teams': {code: finalize(zones) for code, zones in teams.items()},
        'players': filtered_players,
        'grid': grid_data,
    }

    total_shots = sum(d['attempts'] for d in league.values())
    print(f"  Total field goal attempts: {total_shots}")
    print(f"  Teams: {len(teams)}, Players (>=50 FGA): {len(filtered_players)}")
    print(f"  Heatmap grid: {GRID_COLS}x{GRID_ROWS} cells")
    return output


def build_paint_profiles():
    """Build paint finishing profiles: L/R/C breakdown for players and teams."""
    import csv
    import math
    shot_file = f'shot_data_{S}_{S}.csv'
    if not os.path.exists(shot_file):
        print(f"  shot_data_{S}_{S}.csv not found — skipping paint profiles.")
        return None

    # Accumulators: {key: {left_att, left_made, right_att, right_made, center_att, center_made}}
    from collections import defaultdict
    def new_profile():
        return {'left_att':0,'left_made':0,'right_att':0,'right_made':0,
                'center_att':0,'center_made':0,'fb_att':0,'sc_att':0}

    players = defaultdict(lambda: {'team':'', 'profile': new_profile()})
    teams = defaultdict(new_profile)
    league = new_profile()

    with open(shot_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            zone = (row.get('ZONE') or '').strip()
            if zone not in ('A', 'B', 'C'):
                continue
            action = (row.get('ID_ACTION') or '').strip()
            if action not in ('2FGM', '2FGA'):
                continue

            x = float(row.get('COORD_X', 0) or 0)
            made = action == '2FGM'
            fb = int(row.get('FASTBREAK', 0) or 0)
            sc = int(row.get('SECOND_CHANCE', 0) or 0)

            if x < -20:
                side = 'left'
            elif x > 20:
                side = 'right'
            else:
                side = 'center'

            team_code = (row.get('TEAM') or '').strip()
            player = (row.get('PLAYER') or '').strip()

            for target in [league, teams[team_code], players[player]['profile']]:
                target[f'{side}_att'] += 1
                if made:
                    target[f'{side}_made'] += 1
                if fb:
                    target['fb_att'] += 1
                if sc:
                    target['sc_att'] += 1

            players[player]['team'] = team_code

    def finalize_profile(p):
        total = p['left_att'] + p['right_att'] + p['center_att']
        if total == 0:
            return None
        made = p['left_made'] + p['right_made'] + p['center_made']
        left_fgp = round(p['left_made'] / p['left_att'] * 100, 1) if p['left_att'] > 0 else None
        right_fgp = round(p['right_made'] / p['right_att'] * 100, 1) if p['right_att'] > 0 else None
        center_fgp = round(p['center_made'] / p['center_att'] * 100, 1) if p['center_att'] > 0 else None
        left_pct = round(p['left_att'] / total * 100, 1)
        right_pct = round(p['right_att'] / total * 100, 1)
        return {
            'att': total,
            'made': made,
            'fg_pct': round(made / total * 100, 1),
            'left_att': p['left_att'], 'left_made': p['left_made'],
            'left_fgp': left_fgp, 'left_pct': left_pct,
            'right_att': p['right_att'], 'right_made': p['right_made'],
            'right_fgp': right_fgp, 'right_pct': right_pct,
            'center_att': p['center_att'], 'center_made': p['center_made'],
            'center_fgp': center_fgp,
        }

    # Players: min 30 paint attempts
    player_profiles = []
    for name, data in players.items():
        fp = finalize_profile(data['profile'])
        if fp and fp['att'] >= 30:
            fp['player'] = name
            fp['team'] = data['team']
            player_profiles.append(fp)
    player_profiles.sort(key=lambda x: x['att'], reverse=True)

    # Teams
    team_profiles = {}
    for code, prof in teams.items():
        fp = finalize_profile(prof)
        if fp:
            team_profiles[code] = fp

    # Team paint defense: opponent paint finishing
    team_defense = defaultdict(new_profile)
    with open(shot_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # We need opponent info — load game data for team mapping
    # Simpler approach: use game-level data
    # Load all game stats to map gamecodes to home/away teams
    all_stats = load_json(f'mvp_all_game_stats_{S}.json') or []
    game_teams = {}
    for g in all_stats:
        gc = g.get('Gamecode', g.get('GameCode'))
        lp = g.get('local.players') or []
        rp = g.get('road.players') or []
        if lp and rp:
            local = lp[0]['player']['club']['code']
            road = rp[0]['player']['club']['code']
            game_teams[gc] = {'local': local, 'road': road}

    with open(shot_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            zone = (row.get('ZONE') or '').strip()
            if zone not in ('A', 'B', 'C'):
                continue
            action = (row.get('ID_ACTION') or '').strip()
            if action not in ('2FGM', '2FGA'):
                continue

            x = float(row.get('COORD_X', 0) or 0)
            made = action == '2FGM'
            gc = int(row.get('Gamecode', 0) or 0)
            team_code = (row.get('TEAM') or '').strip()

            if x < -20:
                side = 'left'
            elif x > 20:
                side = 'right'
            else:
                side = 'center'

            # Find the defending team
            gt = game_teams.get(gc)
            if not gt:
                continue
            if team_code == gt['local']:
                defender = gt['road']
            elif team_code == gt['road']:
                defender = gt['local']
            else:
                continue

            target = team_defense[defender]
            target[f'{side}_att'] += 1
            if made:
                target[f'{side}_made'] += 1

    team_def_profiles = {}
    for code, prof in team_defense.items():
        fp = finalize_profile(prof)
        if fp:
            team_def_profiles[code] = fp

    output = {
        'league': finalize_profile(league),
        'players': player_profiles,
        'teams': team_profiles,
        'team_defense': team_def_profiles,
    }
    return output


def build_assist_network():
    """Build passer→scorer assist network from play-by-play data."""
    import csv
    from collections import defaultdict

    pbp_file = f'data_cache/pbp_{S}.csv'
    if not os.path.exists(pbp_file):
        print("  No PBP data found — skipping assist network.")
        return None

    print(f"\n--- Building assist network from {pbp_file} ---")

    # ── Phase 1: Read PBP, link assists to made field goals ──────────────────
    rows = []
    with open(pbp_file, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # Sort by Gamecode, NUMBEROFPLAY to ensure correct linking order
    rows.sort(key=lambda r: (r.get('Gamecode', ''), int(r.get('NUMBEROFPLAY', 0)) if r.get('NUMBEROFPLAY', '').isdigit() else 0))

    # Track GP per player (unique gamecodes where they appear)
    player_games = defaultdict(set)
    for row in rows:
        pid = row.get('PLAYER_ID', '').strip()
        gc = row.get('Gamecode', '').strip()
        if pid and gc:
            player_games[pid].add(gc)

    # Link assists: AS row follows a 2FGM/3FGM row with consecutive NUMBEROFPLAY
    edges_raw = []  # list of (passer_id, passer_name, scorer_id, scorer_name, team, shot_type, gamecode)
    for i, row in enumerate(rows):
        if row.get('PLAYTYPE') != 'AS':
            continue
        if i == 0:
            continue
        prev = rows[i - 1]
        if prev.get('Gamecode') != row.get('Gamecode'):
            continue
        if prev.get('PLAYTYPE') not in ('2FGM', '3FGM'):
            continue
        # Verify consecutive NUMBEROFPLAY
        try:
            nop_cur = int(row.get('NUMBEROFPLAY', 0))
            nop_prev = int(prev.get('NUMBEROFPLAY', 0))
        except (ValueError, TypeError):
            continue
        if nop_cur != nop_prev + 1:
            continue

        passer_id = row.get('PLAYER_ID', '').strip()
        passer_name = row.get('PLAYER', '').strip()
        scorer_id = prev.get('PLAYER_ID', '').strip()
        scorer_name = prev.get('PLAYER', '').strip()
        team = row.get('CODETEAM', '').strip()
        shot_type = prev.get('PLAYTYPE')  # '2FGM' or '3FGM'
        gamecode = row.get('Gamecode', '').strip()

        if passer_id and scorer_id and team:
            edges_raw.append((passer_id, passer_name, scorer_id, scorer_name, team, shot_type, gamecode))

    print(f"  Linked assists: {len(edges_raw)}")

    # ── Phase 2: Aggregate edges ─────────────────────────────────────────────
    # Edge key: (passer_id, scorer_id)
    edge_agg = defaultdict(lambda: {'count': 0, 'fg2': 0, 'fg3': 0, 'team': '', 'passer_name': '', 'scorer_name': ''})
    # Per-player totals
    player_ast_given = defaultdict(lambda: {'name': '', 'team': '', 'count': 0, 'targets': set()})
    player_ast_received = defaultdict(lambda: {'name': '', 'team': '', 'count': 0, 'feeders': set()})

    for passer_id, passer_name, scorer_id, scorer_name, team, shot_type, gamecode in edges_raw:
        key = (passer_id, scorer_id)
        e = edge_agg[key]
        e['count'] += 1
        e['team'] = team
        e['passer_name'] = passer_name
        e['scorer_name'] = scorer_name
        if shot_type == '2FGM':
            e['fg2'] += 1
        else:
            e['fg3'] += 1

        g = player_ast_given[passer_id]
        g['name'] = passer_name
        g['team'] = team
        g['count'] += 1
        g['targets'].add(scorer_id)

        r = player_ast_received[scorer_id]
        r['name'] = scorer_name
        r['team'] = team
        r['count'] += 1
        r['feeders'].add(passer_id)

    # ── Phase 3: Build per-team structures ───────────────────────────────────
    team_players = defaultdict(dict)  # team -> {player_id: {info}}
    team_edges = defaultdict(list)    # team -> [edge dicts]

    for (passer_id, scorer_id), e in edge_agg.items():
        team = e['team']
        team_edges[team].append({
            'from': passer_id,
            'to': scorer_id,
            'count': e['count'],
            'fg2': e['fg2'],
            'fg3': e['fg3'],
        })

        # Ensure both players exist in the team's player dict
        for pid, pname in [(passer_id, e['passer_name']), (scorer_id, e['scorer_name'])]:
            if pid not in team_players[team]:
                gp = len(player_games.get(pid, set()))
                ast_g = player_ast_given.get(pid, {}).get('count', 0)
                ast_r = player_ast_received.get(pid, {}).get('count', 0)
                targets = len(player_ast_given.get(pid, {}).get('targets', set()))
                team_players[team][pid] = {
                    'id': pid,
                    'name': pname,
                    'ast_given': ast_g,
                    'ast_received': ast_r,
                    'gp': gp,
                    'ast_per_game': round(ast_g / gp, 1) if gp > 0 else 0.0,
                    'unique_targets': targets,
                }

    # Assemble teams dict
    teams_out = {}
    for team_code in sorted(team_players.keys()):
        players_list = sorted(team_players[team_code].values(), key=lambda p: p['ast_given'] + p['ast_received'], reverse=True)
        teams_out[team_code] = {
            'players': players_list,
            'edges': team_edges[team_code],
        }

    # ── Phase 4: Build league-wide tables ────────────────────────────────────
    # Top 20 assist combos
    all_combos = []
    for (passer_id, scorer_id), e in edge_agg.items():
        passer_gp = len(player_games.get(passer_id, set()))
        all_combos.append({
            'passer': e['passer_name'],
            'passer_id': passer_id,
            'scorer': e['scorer_name'],
            'scorer_id': scorer_id,
            'team': e['team'],
            'count': e['count'],
            'fg2': e['fg2'],
            'fg3': e['fg3'],
            'per_game': round(e['count'] / passer_gp, 2) if passer_gp > 0 else 0.0,
        })
    all_combos.sort(key=lambda x: x['count'], reverse=True)
    top_combos = all_combos[:20]

    # Top 20 playmakers
    all_playmakers = []
    for pid, info in player_ast_given.items():
        if info['count'] < 5:
            continue  # skip very low-volume
        gp = len(player_games.get(pid, set()))
        # Find top target
        best_target = ''
        best_target_count = 0
        for (p_id, s_id), e in edge_agg.items():
            if p_id == pid and e['count'] > best_target_count:
                best_target_count = e['count']
                best_target = e['scorer_name']
        all_playmakers.append({
            'player': info['name'],
            'player_id': pid,
            'team': info['team'],
            'ast': info['count'],
            'per_game': round(info['count'] / gp, 1) if gp > 0 else 0.0,
            'unique_targets': len(info['targets']),
            'top_target': best_target,
            'top_target_count': best_target_count,
        })
    all_playmakers.sort(key=lambda x: x['ast'], reverse=True)
    top_playmakers = all_playmakers[:20]

    print(f"  Teams: {len(teams_out)}")
    print(f"  Total edges: {sum(len(t['edges']) for t in teams_out.values())}")
    print(f"  Top combo: {top_combos[0]['passer']} -> {top_combos[0]['scorer']} ({top_combos[0]['count']})" if top_combos else "  No combos")

    return {
        'teams': teams_out,
        'top_combos': top_combos,
        'top_playmakers': top_playmakers,
    }


def build_game_recaps():
    """Build per-round game recaps with box scores from game stats + backtest."""
    all_stats = load_json(f'mvp_all_game_stats_{S}.json')
    backtest = load_json('oracle_backtest_predictions.json')
    if not all_stats or not backtest:
        print("  Missing game stats or backtest — skipping game recaps.")
        return None

    # Build backtest lookup by GameCode
    bt_lookup = {}
    for g in backtest:
        bt_lookup[g['GameCode']] = g

    # Build schedule lookup by (homecode, awaycode) for game dates
    sched_lookup = {}
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(f'official_schedule_{S}.xml')
        for item in tree.getroot().iter('item'):
            home = (item.findtext('homecode') or '').strip()
            away = (item.findtext('awaycode') or '').strip()
            date = (item.findtext('date') or '').strip()
            time_ = (item.findtext('startime') or '').strip()
            if home and away:
                sched_lookup[(home, away)] = {'date': date, 'time': time_}
    except Exception:
        pass

    rounds = {}  # round_num -> [game, ...]

    for game in all_stats:
        gc = game.get('Gamecode', game.get('GameCode'))
        # Skip playoff/play-in games (GameCode > 380) — Game Recaps cover regular season only
        gc_int = int(gc) if isinstance(gc, (int, float)) else 0
        if gc_int > 380:
            continue
        bt = bt_lookup.get(gc)
        if not bt:
            continue  # skip games not in backtest (future/unplayed)

        local_players = game.get('local.players', [])
        road_players = game.get('road.players', [])
        if not local_players and not road_players:
            continue  # no box score data

        rnd = bt['Round']
        home_code = bt['Home']
        away_code = bt['Away']
        home_pts = game.get('local.total.points', 0) or 0
        away_pts = game.get('road.total.points', 0) or 0

        def fmt_time(secs):
            secs = int(secs or 0)
            return f"{secs // 60}:{secs % 60:02d}"

        def build_player_row(entry):
            p = entry.get('player', {})
            s = entry.get('stats', {})
            person = p.get('person', {})
            time_secs = s.get('timePlayed', 0) or 0
            pts = int(s.get('points', 0) or 0)
            fg2m = int(s.get('fieldGoalsMade2', 0) or 0)
            fg2a = int(s.get('fieldGoalsAttempted2', 0) or 0)
            fg3m = int(s.get('fieldGoalsMade3', 0) or 0)
            fg3a = int(s.get('fieldGoalsAttempted3', 0) or 0)
            ftm = int(s.get('freeThrowsMade', 0) or 0)
            fta = int(s.get('freeThrowsAttempted', 0) or 0)
            return {
                'name': person.get('name', ''),
                'starter': bool(s.get('startFive')),
                'min': fmt_time(time_secs),
                'pts': pts,
                'reb': int(s.get('totalRebounds', 0) or 0),
                'ast': int(s.get('assistances', 0) or 0),
                'stl': int(s.get('steals', 0) or 0),
                'to': int(s.get('turnovers', 0) or 0),
                'blk': int(s.get('blocksFavour', 0) or 0),
                'pir': int(s.get('valuation', 0) or 0),
                'pm': int(s.get('plusMinus', 0) or 0),
                'fg': f"{fg2m + fg3m}/{fg2a + fg3a}",
                'fg3': f"{fg3m}/{fg3a}",
                'ft': f"{ftm}/{fta}",
            }

        home_roster = [build_player_row(e) for e in local_players
                       if (e.get('stats', {}).get('timePlayed', 0) or 0) > 0
                       or e.get('stats', {}).get('startFive')]
        away_roster = [build_player_row(e) for e in road_players
                       if (e.get('stats', {}).get('timePlayed', 0) or 0) > 0
                       or e.get('stats', {}).get('startFive')]

        # Sort: starters first (by PIR desc), then bench (by PIR desc)
        for roster in (home_roster, away_roster):
            roster.sort(key=lambda x: (-x['starter'], -x['pir']))

        # Team totals
        def team_totals(prefix):
            return {
                'pts': int(game.get(f'{prefix}.total.points', 0) or 0),
                'reb': int(game.get(f'{prefix}.total.totalRebounds', 0) or 0),
                'ast': int(game.get(f'{prefix}.total.assistances', 0) or 0),
                'stl': int(game.get(f'{prefix}.total.steals', 0) or 0),
                'to': int(game.get(f'{prefix}.total.turnovers', 0) or 0),
                'blk': int(game.get(f'{prefix}.total.blocksFavour', 0) or 0),
                'fg2': f"{int(game.get(f'{prefix}.total.fieldGoalsMade2', 0) or 0)}/{int(game.get(f'{prefix}.total.fieldGoalsAttempted2', 0) or 0)}",
                'fg3': f"{int(game.get(f'{prefix}.total.fieldGoalsMade3', 0) or 0)}/{int(game.get(f'{prefix}.total.fieldGoalsAttempted3', 0) or 0)}",
                'ft': f"{int(game.get(f'{prefix}.total.freeThrowsMade', 0) or 0)}/{int(game.get(f'{prefix}.total.freeThrowsAttempted', 0) or 0)}",
                'pir': int(game.get(f'{prefix}.total.valuation', 0) or 0),
            }

        # Find top performer (highest PIR across both teams)
        all_players = home_roster + away_roster
        top = max(all_players, key=lambda x: x['pir']) if all_players else None

        # Game date/time from schedule
        sched = sched_lookup.get((home_code, away_code), {})

        game_obj = {
            'gameCode': gc,
            'home': home_code,
            'away': away_code,
            'homePts': int(home_pts),
            'awayPts': int(away_pts),
            'homeName': TEAM_NAMES.get(home_code, home_code),
            'awayName': TEAM_NAMES.get(away_code, away_code),
            'date': sched.get('date', ''),
            'time': sched.get('time', ''),
            'homeRoster': home_roster,
            'awayRoster': away_roster,
            'homeTotals': team_totals('local'),
            'awayTotals': team_totals('road'),
            'oracle': {
                'predictedWinner': bt.get('PredictedWinner', ''),
                'homeWinProb': bt.get('HomeWinProb', 50),
                'margin': bt.get('PredictedMargin', 0),
                'correct': bt.get('Correct', False),
            },
        }
        if top:
            game_obj['topPerformer'] = {
                'name': top['name'],
                'pts': top['pts'],
                'reb': top['reb'],
                'ast': top['ast'],
                'pir': top['pir'],
            }

        rounds.setdefault(rnd, []).append(game_obj)

    # Sort games within each round by gamecode
    for rnd in rounds:
        rounds[rnd].sort(key=lambda x: x['gameCode'])

    # Convert to sorted list of rounds
    from datetime import datetime, timezone
    output = {
        'rounds': {str(r): rounds[r] for r in sorted(rounds.keys())},
        'totalRounds': max(rounds.keys()) if rounds else 0,
        'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }

    print(f"  Game recaps: {sum(len(v) for v in rounds.values())} games across {len(rounds)} rounds")
    return output


def compute_team_box_metrics(all_game_stats, gamecode_to_teams):
    """
    Aggregate per-team season box-score metrics from raw box scores.

    Args:
        all_game_stats: list of game dicts from the current season mvp_all_game_stats file
        gamecode_to_teams: dict[int, tuple[str, str]] mapping
            GameCode -> (local_team_code, road_team_code)

    Returns:
        dict[team_code] = {
            'pace': float,           # avg possessions per game
            'three_pct': float,      # 3PT% (0-100)
            'two_pct': float,        # 2PT% (0-100)
            'ft_rate': float,        # FTA / FGA
            'bench_share': float,    # bench points share (0-100)
            'opp_three_pct': float,  # opponents' 3PT% vs this team (0-100)
            'opp_two_pct': float,    # opponents' 2PT% vs this team (0-100)
            'games': int,
        }
    Skips playoff games (Gamecode > 380) and any game with no shot attempts logged.
    """
    from collections import defaultdict

    agg = defaultdict(lambda: {
        'fga': 0.0, 'fta': 0.0, 'oreb': 0.0, 'tov': 0.0,
        'fgm3': 0.0, 'fga3': 0.0, 'fgm2': 0.0, 'fga2': 0.0,
        'opp_fgm3': 0.0, 'opp_fga3': 0.0,
        'opp_fgm2': 0.0, 'opp_fga2': 0.0,
        'bench_pts': 0.0, 'total_pts': 0.0,
        'games': 0,
    })

    def _bench_points(players):
        if not isinstance(players, list):
            return 0.0
        total = 0.0
        for pl in players:
            stats = pl.get('stats') or {}
            if stats.get('startFive'):
                continue
            total += float(stats.get('points') or 0.0)
        return total

    for g in all_game_stats:
        gc = int(g.get('Gamecode') or g.get('GameCode') or 0)
        if gc <= 0 or gc > 380:
            continue
        teams = gamecode_to_teams.get(gc)
        if not teams:
            continue
        local_team, road_team = teams

        for side, opp_side, my_team in (
            ('local', 'road', local_team),
            ('road', 'local', road_team),
        ):
            fga = float(g.get(f'{side}.total.fieldGoalsAttemptedTotal') or 0)
            fta = float(g.get(f'{side}.total.freeThrowsAttempted') or 0)
            if fga + fta == 0:
                continue  # data missing

            t = agg[my_team]
            t['fga'] += fga
            t['fta'] += fta
            t['oreb'] += float(g.get(f'{side}.total.offensiveRebounds') or 0)
            t['tov'] += float(g.get(f'{side}.total.turnovers') or 0)
            t['fgm3'] += float(g.get(f'{side}.total.fieldGoalsMade3') or 0)
            t['fga3'] += float(g.get(f'{side}.total.fieldGoalsAttempted3') or 0)
            t['fgm2'] += float(g.get(f'{side}.total.fieldGoalsMade2') or 0)
            t['fga2'] += float(g.get(f'{side}.total.fieldGoalsAttempted2') or 0)
            t['opp_fgm3'] += float(g.get(f'{opp_side}.total.fieldGoalsMade3') or 0)
            t['opp_fga3'] += float(g.get(f'{opp_side}.total.fieldGoalsAttempted3') or 0)
            t['opp_fgm2'] += float(g.get(f'{opp_side}.total.fieldGoalsMade2') or 0)
            t['opp_fga2'] += float(g.get(f'{opp_side}.total.fieldGoalsAttempted2') or 0)
            t['total_pts'] += float(g.get(f'{side}.total.points') or 0)
            t['bench_pts'] += _bench_points(g.get(f'{side}.players'))
            t['games'] += 1

    out = {}
    for code, a in agg.items():
        if a['games'] == 0:
            continue
        poss = a['fga'] + 0.44 * a['fta'] - a['oreb'] + a['tov']
        out[code] = {
            'pace': round(poss / a['games'], 1),
            'three_pct': round((a['fgm3'] / a['fga3']) * 100, 1) if a['fga3'] > 0 else 0.0,
            'two_pct': round((a['fgm2'] / a['fga2']) * 100, 1) if a['fga2'] > 0 else 0.0,
            'ft_rate': round(a['fta'] / a['fga'], 3) if a['fga'] > 0 else 0.0,
            'bench_share': round((a['bench_pts'] / a['total_pts']) * 100, 1) if a['total_pts'] > 0 else 0.0,
            'opp_three_pct': round((a['opp_fgm3'] / a['opp_fga3']) * 100, 1) if a['opp_fga3'] > 0 else 0.0,
            'opp_two_pct': round((a['opp_fgm2'] / a['opp_fga2']) * 100, 1) if a['opp_fga2'] > 0 else 0.0,
            'games': a['games'],
        }
    return out


def compute_team_paint_share(shot_stats):
    """
    Compute per-team paint shot volume share from shot_stats data.

    Paint zones: A (At Rim), B (Left Paint), C (Right Paint).
    paint_share = (paint attempts) / (total attempts) * 100.

    Args:
        shot_stats: dict loaded from docs/data/current/shot_stats.json

    Returns:
        dict[team_code] -> float (0-100)
    """
    out = {}
    teams = (shot_stats or {}).get('teams') or {}
    paint_zones = ('A', 'B', 'C')
    for code, zones in teams.items():
        if not isinstance(zones, dict):
            continue
        paint_att = sum(float((zones.get(z) or {}).get('attempts') or 0) for z in paint_zones)
        total_att = sum(float((zones.get(z) or {}).get('attempts') or 0) for z in zones.keys())
        if total_att <= 0:
            continue
        out[code] = round((paint_att / total_att) * 100, 1)
    return out


def compute_remaining_series_wp(matchup_probs, high_team, low_team,
                                wins_high, wins_low,
                                home_pattern=('high', 'high', 'low', 'low', 'high'),
                                target_wins=3, elo_high=None, elo_low=None,
                                elo_hca=50.0):
    """
    Compute series win probability for the higher seed given the current
    series score and remaining games. Best-of-N DP, identical to the JS
    `seriesProbHCA` in playoffs.js.

    Args:
        matchup_probs: dict[high_team][low_team] = {'home','away','neutral'}
            with floats in [0,1]. May be missing.
        high_team, low_team: 3-letter team codes.
        wins_high, wins_low: current series score (ints).
        home_pattern: tuple of 'high' | 'low' for each game number 1..N.
            'neutral' is also allowed (used for the Final).
        target_wins: wins needed to clinch (3 for best-of-5, 1 for single-game).
        elo_high, elo_low: optional Elo ratings for fallback when matchup_probs
            is missing for the pair.
        elo_hca: Elo home-court advantage in points.

    Returns:
        float in [0,1] — probability the higher seed wins the series.
    """
    if wins_high >= target_wins:
        return 1.0
    if wins_low >= target_wins:
        return 0.0

    pair_fwd = (matchup_probs.get(high_team) or {}).get(low_team) or {}

    def _elo_wp(neutral=False):
        if elo_high is None or elo_low is None:
            return 0.5
        hca = 0.0 if neutral else elo_hca
        return 1.0 / (1.0 + 10.0 ** ((elo_low - elo_high - hca) / 400.0))

    def _per_game_p(slot):
        if slot == 'high':
            return pair_fwd.get('home', _elo_wp(neutral=False))
        if slot == 'low':
            return pair_fwd.get('away', _elo_wp(neutral=False))
        return pair_fwd.get('neutral', _elo_wp(neutral=True))

    games_played = wins_high + wins_low
    remaining = list(home_pattern)[games_played:]
    if not remaining:
        return 1.0 if wins_high > wins_low else 0.0

    states = {(wins_high, wins_low): 1.0}
    prob_high = 0.0

    for slot in remaining:
        p = _per_game_p(slot)
        nxt = {}
        for (a, b), prob in states.items():
            # higher seed wins this game
            a1 = a + 1
            if a1 >= target_wins:
                prob_high += prob * p
            else:
                key = (a1, b)
                nxt[key] = nxt.get(key, 0.0) + prob * p
            # lower seed wins this game
            b1 = b + 1
            if b1 < target_wins:
                key = (a, b1)
                nxt[key] = nxt.get(key, 0.0) + prob * (1.0 - p)
            # else: low clinches — no contribution to prob_high
        states = nxt
        if not states:
            break

    return prob_high


def build_momentum(series_entry, matchup_probs, teams_by_code):
    """
    Build the Series Momentum checkpoint sequence + biggest-swing callout.

    Reads the entry's wins, completed games, home_pattern, and high/low seeds.
    Recomputes series WP from scratch at each checkpoint (Pre-series, After G1,
    After G2, ...). Returns None when no games have been played.

    Args:
        series_entry: dict produced by compute_series_data() for one slot.
        matchup_probs: dict[high][low] = {home, away, neutral}.
        teams_by_code: dict[code] -> team object from dashboard 'teams' list,
            used for Elo fallback.

    Returns:
        {
          'checkpoints': [{'label': 'Pre-series', 'high_wp': ..., 'low_wp': ...}, ...],
          'biggest_swing': {
              'from_label': str, 'to_label': str, 'game_num': int,
              'delta_pct': float, 'shifted_to': 'high'|'low',
              'winner_team': str
          }
        }
        or None if no games completed yet.
    """
    high = (series_entry.get('high_seed') or {}).get('team')
    low = (series_entry.get('low_seed') or {}).get('team')
    if not high or not low:
        return None

    games = series_entry.get('games') or []
    completed = [g for g in games if g.get('status') == 'completed']
    if not completed:
        return None

    fmt = series_entry.get('format') or 'best_of_5'
    target_wins = 1 if fmt == 'single_game' else 3
    home_pattern = tuple(series_entry.get('home_pattern')
                        or ('high', 'high', 'low', 'low', 'high'))

    elo_high = (teams_by_code.get(high) or {}).get('elo')
    elo_low = (teams_by_code.get(low) or {}).get('elo')

    def _wp(wins_h, wins_l):
        return compute_remaining_series_wp(
            matchup_probs, high, low, wins_h, wins_l,
            home_pattern=home_pattern, target_wins=target_wins,
            elo_high=elo_high, elo_low=elo_low,
        )

    # Pre-series checkpoint
    p0 = _wp(0, 0)
    checkpoints = [{
        'label': 'Pre-series',
        'high_wp': round(p0 * 100, 1),
        'low_wp': round((1 - p0) * 100, 1),
    }]

    wins_h, wins_l = 0, 0
    completed_sorted = sorted(completed, key=lambda g: g.get('game_num') or 0)
    for g in completed_sorted:
        winner = g.get('winner')
        if winner == high:
            wins_h += 1
        elif winner == low:
            wins_l += 1
        else:
            continue  # skip games with unknown winner
        p = _wp(wins_h, wins_l)
        checkpoints.append({
            'label': f'After G{g.get("game_num")}',
            'high_wp': round(p * 100, 1),
            'low_wp': round((1 - p) * 100, 1),
        })

    if len(checkpoints) < 2:
        return None  # nothing actually played that we could attribute

    # Biggest swing = consecutive checkpoint pair with largest |delta_high|
    biggest = None
    for i in range(1, len(checkpoints)):
        prev = checkpoints[i - 1]
        cur = checkpoints[i]
        delta = cur['high_wp'] - prev['high_wp']
        if biggest is None or abs(delta) > abs(biggest['delta']):
            biggest = {
                'i': i, 'delta': delta,
                'from_label': prev['label'], 'to_label': cur['label'],
            }

    # Resolve biggest swing -> game_num, winner
    swing_game = completed_sorted[biggest['i'] - 1]
    delta_pct = round(biggest['delta'], 1)
    shifted_to = 'high' if delta_pct > 0 else 'low'
    return {
        'checkpoints': checkpoints,
        'biggest_swing': {
            'from_label': biggest['from_label'],
            'to_label': biggest['to_label'],
            'game_num': swing_game.get('game_num'),
            'delta_pct': abs(delta_pct),
            'shifted_to': shifted_to,
            'winner_team': swing_game.get('winner'),
        },
    }


def _compute_edges(high_team, low_team, th, tl, bh, bl, paint_share, rs_h2h):
    """
    Deterministic Edges panel. Returns a list of up to 3 edge dicts:
        {'text': str, 'favor': 'high' | 'low' | None, 'type': str}

    Algorithm (matches spec):
      - Generate candidates: net, three_pct, paint_pct, pace, bench, form.
      - Drop the lower-scoring of {three_pct, paint_pct} so at most one
        shooting edge survives.
      - Sort surviving by score desc; tie-break by priority order.
      - Take top 2 (or top 3 if no H2H qualifies).
      - Append H2H as slot 3 if rs_h2h has at least 1 entry.
    """
    PRIORITY = ['net', 'three_pct', 'paint_pct', 'pace', 'bench', 'form']
    cands = []  # each: {'type','score','favor','text'}

    def _last5_wins(team_obj):
        last5 = team_obj.get('last5') or []
        return sum(1 for x in last5 if x == 'W')

    # 1. Net rating gap (always considered)
    net_h = th.get('adj_net')
    net_l = tl.get('adj_net')
    if net_h is not None and net_l is not None:
        gap = abs(net_h - net_l)
        favor = 'high' if net_h >= net_l else 'low'
        team = high_team if favor == 'high' else low_team
        diff = abs(round(net_h - net_l, 1))
        cands.append({
            'type': 'net', 'score': gap, 'favor': favor,
            'text': f'{team}: +{diff:g} net rating advantage',
        })

    # 2. 3PT shooting matchup: team's 3PT% vs opp 3PT% allowed
    th_3 = bh.get('three_pct')
    tl_3 = bl.get('three_pct')
    th_opp3 = bh.get('opp_three_pct')
    tl_opp3 = bl.get('opp_three_pct')
    if None not in (th_3, tl_3, th_opp3, tl_opp3):
        # Each team's expected edge from 3 vs the OTHER team's perimeter D
        h_edge = th_3 - tl_opp3   # high shoots vs low's defense
        l_edge = tl_3 - th_opp3   # low shoots vs high's defense
        # Pick the larger absolute team edge as the candidate
        if abs(h_edge) >= abs(l_edge):
            score = abs(h_edge)
            favor = 'high' if h_edge >= 0 else 'low'
            text = (f'{high_team}: {th_3:.0f}% from 3 vs {low_team} defending '
                    f'{tl_opp3:.0f}% — '
                    + ('edge ' + (high_team if favor == 'high' else low_team)))
        else:
            score = abs(l_edge)
            favor = 'low' if l_edge >= 0 else 'high'
            text = (f'{low_team}: {tl_3:.0f}% from 3 vs {high_team} defending '
                    f'{th_opp3:.0f}% — '
                    + ('edge ' + (low_team if favor == 'low' else high_team)))
        cands.append({'type': 'three_pct', 'score': score, 'favor': favor, 'text': text})

    # 3. Paint shooting matchup: 2PT% as proxy (higher is better; also opp 2PT% lower is better D)
    th_2 = bh.get('two_pct')
    tl_2 = bl.get('two_pct')
    th_opp2 = bh.get('opp_two_pct')
    tl_opp2 = bl.get('opp_two_pct')
    if None not in (th_2, tl_2, th_opp2, tl_opp2):
        h_edge = th_2 - tl_opp2   # high inside vs low's interior D
        l_edge = tl_2 - th_opp2
        if abs(h_edge) >= abs(l_edge):
            score = abs(h_edge)
            favor = 'high' if h_edge >= 0 else 'low'
            text = (f'{high_team}: {th_2:.0f}% on 2s vs {low_team} allowing '
                    f'{tl_opp2:.0f}% — '
                    + ('paint edge ' + (high_team if favor == 'high' else low_team)))
        else:
            score = abs(l_edge)
            favor = 'low' if l_edge >= 0 else 'high'
            text = (f'{low_team}: {tl_2:.0f}% on 2s vs {high_team} allowing '
                    f'{th_opp2:.0f}% — '
                    + ('paint edge ' + (low_team if favor == 'low' else high_team)))
        cands.append({'type': 'paint_pct', 'score': score, 'favor': favor, 'text': text})

    # 4. Pace mismatch (gap >= 3.0)
    pace_h = bh.get('pace')
    pace_l = bl.get('pace')
    if pace_h is not None and pace_l is not None:
        gap = abs(pace_h - pace_l)
        if gap >= 3.0:
            favor = 'high' if pace_h > pace_l else 'low'
            faster = high_team if favor == 'high' else low_team
            cands.append({
                'type': 'pace', 'score': gap, 'favor': favor,
                'text': f'{faster} plays {gap:.1f} more possessions per 40 — pace edge {faster}',
            })

    # 5. Bench depth (gap >= 5pp)
    bs_h = bh.get('bench_share')
    bs_l = bl.get('bench_share')
    if bs_h is not None and bs_l is not None:
        gap = abs(bs_h - bs_l)
        if gap >= 5.0:
            favor = 'high' if bs_h > bs_l else 'low'
            deeper = high_team if favor == 'high' else low_team
            cands.append({
                'type': 'bench', 'score': gap, 'favor': favor,
                'text': f'{deeper}: bench scores {(bs_h if favor == "high" else bs_l):.0f}% vs '
                        f'{(bs_l if favor == "high" else bs_h):.0f}% — depth edge {deeper}',
            })

    # 6. Recent form (last5 W differential >= 2)
    f_h = _last5_wins(th)
    f_l = _last5_wins(tl)
    gap = abs(f_h - f_l)
    if gap >= 2 and (th.get('last5') or tl.get('last5')):
        favor = 'high' if f_h > f_l else 'low'
        team = high_team if favor == 'high' else low_team
        opp_name = low_team if favor == 'high' else high_team
        f_team = f_h if favor == 'high' else f_l
        f_opp = f_l if favor == 'high' else f_h
        cands.append({
            'type': 'form', 'score': float(gap), 'favor': favor,
            'text': f'{team}: {f_team}-{5-f_team} last 5 vs {opp_name} '
                    f'{f_opp}-{5-f_opp} — form edge {team}',
        })

    # De-duplicate shooting edges: keep the higher-scoring of {three_pct, paint_pct}
    shooting = [c for c in cands if c['type'] in ('three_pct', 'paint_pct')]
    if len(shooting) > 1:
        keep = max(shooting, key=lambda c: c['score'])
        cands = [c for c in cands if c['type'] not in ('three_pct', 'paint_pct')] + [keep]

    # Sort by score desc, tie-break by PRIORITY order
    cands.sort(key=lambda c: (-c['score'], PRIORITY.index(c['type'])))

    # H2H is forced into slot 3 if any meetings exist
    h2h_edge = None
    if rs_h2h:
        wins_h = sum(1 for m in rs_h2h if m.get('winner') == high_team)
        wins_l = sum(1 for m in rs_h2h if m.get('winner') == low_team)
        if wins_h == len(rs_h2h) and wins_l == 0:
            text = f'{high_team} swept RS series {wins_h}-0'
            favor = 'high'
        elif wins_l == len(rs_h2h) and wins_h == 0:
            text = f'{low_team} swept RS series {wins_l}-0'
            favor = 'low'
        else:
            text = f'Split RS series {wins_h}-{wins_l}'
            favor = None
        h2h_edge = {'type': 'h2h', 'text': text, 'favor': favor}

    take = 2 if h2h_edge else 3
    edges = cands[:take]
    if h2h_edge:
        edges.append(h2h_edge)

    # Strip score before returning (frontend doesn't need it)
    return [{'text': e['text'], 'favor': e['favor'], 'type': e['type']} for e in edges]


def build_tale_of_the_tape(high_team, low_team, teams_by_code,
                            box_metrics, paint_share, rs_h2h):
    """
    Build the Tale of the Tape data block for a series.

    8 fixed stat rows in this order:
        1. Pace          (poss/40)         from box_metrics
        2. Adj. Offense                    from teams_by_code (adj_off)
        3. Adj. Defense                    from teams_by_code (adj_def, lower better)
        4. Adj. Net                        from teams_by_code (adj_net)
        5. 3PT %                           from box_metrics
        6. Paint %                         from paint_share
        7. FT Rate                         from box_metrics
        8. Bench %                         from box_metrics

    Rows where either team is missing the stat are skipped (no n/a placeholders).

    Args:
        high_team, low_team: 3-letter codes. Either may be None
            (returns None in that case).
        teams_by_code: dict from dashboard 'teams' list keyed by code.
        box_metrics: output of compute_team_box_metrics().
        paint_share: output of compute_team_paint_share().
        rs_h2h: list of regular-season meetings (already computed by
            compute_series_data._rs_h2h).

    Returns:
        {'rows': [...], 'edges': [...]} or None if either team is missing.
        Edges are computed via _compute_edges() and follow the rows.
    """
    if not high_team or not low_team:
        return None

    th = teams_by_code.get(high_team) or {}
    tl = teams_by_code.get(low_team) or {}
    bh = box_metrics.get(high_team) or {}
    bl = box_metrics.get(low_team) or {}

    row_specs = [
        ('pace',        'Pace (poss/40)', bh.get('pace'),                 bl.get('pace'),                 False),
        ('adj_off',     'Adj. Offense',   th.get('adj_off'),              tl.get('adj_off'),              False),
        ('adj_def',     'Adj. Defense',   th.get('adj_def'),              tl.get('adj_def'),              True),
        ('adj_net',     'Adj. Net',       th.get('adj_net'),              tl.get('adj_net'),              False),
        ('three_pct',   '3PT %',          bh.get('three_pct'),            bl.get('three_pct'),            False),
        ('paint_pct',   'Paint %',        paint_share.get(high_team),     paint_share.get(low_team),      False),
        ('ft_rate',     'FT Rate',        bh.get('ft_rate'),              bl.get('ft_rate'),              False),
        ('bench_share', 'Bench %',        bh.get('bench_share'),          bl.get('bench_share'),          False),
    ]

    rows = []
    for metric, label, hv, lv, lower_is_better in row_specs:
        if hv is None or lv is None:
            continue
        row = {
            'metric': metric, 'label': label,
            'high': round(float(hv), 3 if metric == 'ft_rate' else 1),
            'low':  round(float(lv), 3 if metric == 'ft_rate' else 1),
        }
        if lower_is_better:
            row['lower_is_better'] = True
        rows.append(row)

    edges = _compute_edges(
        high_team, low_team, th, tl, bh, bl,
        paint_share, rs_h2h,
    )
    return {'rows': rows, 'edges': edges}


def championship_final_gamecode(season, pbp_dir='data_cache'):
    """Gamecode of the season's championship final: the highest Final Four
    (Phase 'FF') gamecode in the play-by-play. None when the season had no
    Final Four (2019-20 was cancelled) or its pbp file is missing."""
    path = os.path.join(pbp_dir, f'pbp_{season}.csv')
    if not os.path.exists(path):
        return None
    pbp = pd.read_csv(path, usecols=['Phase', 'Gamecode'], low_memory=False)
    ff = pbp.loc[pbp['Phase'] == 'FF', 'Gamecode']
    return int(ff.max()) if len(ff) else None


def game_flow(plays):
    """(lead_changes, times_tied) for a sequence of (a, b) scores.
    A lead change is the leader switching sides (the first lead is not a
    change); a tie counts when the score becomes level after someone led.
    Consecutive identical scores are one moment."""
    lead_changes = times_tied = 0
    leader = 0          # +1 a leads, -1 b leads, 0 nobody has led yet
    prev = None
    for a, b in plays:
        if (a, b) == prev:
            continue
        prev = (a, b)
        if a == b:
            if leader != 0:
                times_tied += 1
            continue
        side = 1 if a > b else -1
        if leader != 0 and side != leader:
            lead_changes += 1
        leader = side
    return lead_changes, times_tied


def official_standings(game_results, schedule_rows, api_standings=None):
    """Euroleague standings order after every regular-season round.

    Positions come from the official Euroleague standings (Euroleague API,
    cached by fetch_standings.py in standings_{S}.json) when that file covers
    every team in the schedule; a round missing from it is computed with the
    fallback. The fallback approximates the in-season rule: wins, then overall
    point difference, then points scored (then team code). Head-to-head is not
    applied in-season. A game counts toward round R when its scheduled gameday
    <= R and it has been played.
    Returns (codes in current order, {code: [rank after round 1..R]},
    {code: [[wins, losses] after round 1..R]})."""
    from team_aliases import team_code

    gc_round, codes = {}, set()
    for row in schedule_rows or []:
        if row.get('round') != 'RS':
            continue
        gc = int(str(row.get('gamecode', '0')).split('_')[-1])
        gc_round[gc] = int(row.get('gameday') or 0)
        for name_key, code_key in (('hometeam', 'homecode'), ('awayteam', 'awaycode')):
            code = team_code(row.get(name_key), default=row.get(code_key) or 'UNK')
            if code != 'UNK':
                codes.add(code)
    sched_teams = len(codes)

    played = []
    for g in game_results or []:
        gc = int(g.get('GameCode') or 0)
        hs, as_ = int(g.get('LocalScore') or 0), int(g.get('RoadScore') or 0)
        if gc in gc_round and hs > 0 and as_ > 0:
            played.append((gc_round[gc], g['LocalTeam'], g['RoadTeam'], hs, as_))
            codes.update((g['LocalTeam'], g['RoadTeam']))

    codes = sorted(codes)
    if len(codes) != sched_teams:
        print(f"  [WARN] Standings: {len(codes)} team codes vs {sched_teams} "
              f"distinct teams in the regular-season schedule")

    def computed_round(R):
        w = {t: 0 for t in codes}; l = dict(w); pdiff = dict(w); pf = dict(w)
        for rnd, h, a, hs, as_ in played:
            if rnd > R:
                continue
            win, lose = (h, a) if hs > as_ else (a, h)
            w[win] += 1; l[lose] += 1
            pdiff[h] += hs - as_; pdiff[a] += as_ - hs
            pf[h] += hs; pf[a] += as_
        ranked = sorted(codes, key=lambda t: (-w[t], -pdiff[t], -pf[t], t))
        return {t: (i + 1, [w[t], l[t]]) for i, t in enumerate(ranked)}

    api_rounds = {}
    for key, rows in ((api_standings or {}).get('rounds') or {}).items():
        try:
            api_rounds[int(key)] = {r['code']: (int(r['position']), [int(r['wins']), int(r['losses'])])
                                    for r in rows}
        except (KeyError, TypeError, ValueError):
            continue
    use_api = bool(api_rounds) and set(codes) <= set(api_rounds[max(api_rounds)])

    # Rounds 1..R, R = latest played round (or latest API round if later);
    # a round the API file lacks is computed with the fallback rule.
    last_round = max((p[0] for p in played), default=0)
    if use_api:
        last_round = max(last_round, max(api_rounds))
    history = {t: [] for t in codes}
    records = {t: [] for t in codes}
    for R in range(1, last_round + 1):
        snap = api_rounds.get(R) if use_api else None
        if snap is None or not set(codes) <= set(snap):
            snap = computed_round(R)
        for t in codes:
            history[t].append(snap[t][0])
            records[t].append(snap[t][1])
    order = sorted(codes, key=lambda t: (history[t][-1], t)) if last_round else codes
    return order, history, records


def compute_championship_finals_history():
    """
    For each completed season (COMPLETED_SEASONS), load the championship final WP replay JSON
    (the season's highest Final Four gamecode, see championship_final_gamecode), compute lead changes / times
    tied / max deficit, and return a list sorted by lead_changes descending.
    """
    results = []
    replay_base = os.path.join('docs', 'data')

    for season in COMPLETED_SEASONS:
        season_dir = os.path.join(replay_base, str(season))
        if not os.path.isdir(season_dir):
            continue

        if not os.path.exists(os.path.join('data_cache', f'pbp_{season}.csv')):
            print(f'  [WARN] championship finals {season}: pbp file missing, skipping')
            continue
        final_gc = championship_final_gamecode(season)
        if final_gc is None:
            print(f'  [INFO] championship finals {season}: no Final Four in pbp, skipping')
            continue

        path = os.path.join(season_dir, f'{final_gc}.json')
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            print(f'  [WARN] championship finals: could not load {path}: {e}')
            continue

        ta = data.get('ta', '')
        tb = data.get('tb', '')
        timeline = data.get('timeline', [])

        # Extract only scoring plays (entries that have 'a' and 'b')
        plays = [(p['a'], p['b']) for p in timeline if 'a' in p and 'b' in p]
        if not plays:
            continue

        final_a, final_b = plays[-1]
        if final_a == final_b:
            print(f'  [WARN] championship finals {season}: game {final_gc} ended tied {final_a}-{final_b}, skipping')
            continue
        winner = ta if final_a > final_b else tb

        # ── Lead changes & times tied ────────────────────────────────────
        lead_changes, times_tied = game_flow(plays)

        # ── Max deficit overcome by winner ───────────────────────────────
        max_deficit = 0
        for a, b in plays:
            if winner == ta:
                deficit = b - a  # winner is ta; how far behind were they?
            else:
                deficit = a - b  # winner is tb
            if deficit > max_deficit:
                max_deficit = deficit

        results.append({
            'season': season,
            'gamecode': final_gc,
            'home': ta,
            'away': tb,
            'home_name': TEAM_NAMES.get(ta, ta),
            'away_name': TEAM_NAMES.get(tb, tb),
            'home_score': int(final_a),
            'away_score': int(final_b),
            'winner': winner,
            'lead_changes': lead_changes,
            'times_tied': times_tied,
            'max_deficit_overcome': max_deficit,
            'has_replay': True,
        })

    results.sort(key=lambda x: x['lead_changes'], reverse=True)
    print(f'  Championship finals history: {len(results)} seasons computed')
    return results


def main():
    print(f"\n=== Dashboard Export ===")
    if 'EUROLEAGUE_ROUND_SUFFIX' in os.environ:
        suffix = os.environ['EUROLEAGUE_ROUND_SUFFIX']
        print(f"Round suffix: '{suffix}' (from EUROLEAGUE_ROUND_SUFFIX)")
    else:
        # Auto-derive from max GP in standings so ad-hoc runs pick up the
        # latest round-suffixed files instead of silently falling back to
        # stale un-suffixed copies. Mirrors refresh_all.py's convention.
        suffix = ''
        try:
            with open('mvp_standings_derived.json', 'r') as f:
                _standings_for_suffix = json.load(f)
            _max_gp = max((t.get('GP', 0) for t in _standings_for_suffix.values()), default=0)
            if _max_gp > 0:
                suffix = f'_R{_max_gp}'
        except Exception as e:
            print(f"  [WARN] Could not auto-derive round suffix: {e}")
        print(f"Round suffix: '{suffix}' (auto-derived from mvp_standings_derived.json max GP)")

    # ── Load all source data ─────────────────────────────────────────────────
    adjusted = load_with_fallback(suffix, 'adjusted_ratings.json', strict=True)
    elo_data = load_with_fallback(suffix, 'elo_ratings.json', strict=True)
    mc_data = load_with_fallback(suffix, 'monte_carlo_results.json', strict=True)
    mvp_data = load_with_fallback(suffix, f'mvp_rankings_{S}.json', strict=True)
    standings_data = load_json('mvp_standings_derived.json')
    # Accuracy: try oracle_accuracy{suffix}.json first (no _ml infix), then ml variant, then bare
    # Accuracy is per season: strict (this round's file or nothing).
    accuracy_data = load_with_fallback(suffix, 'oracle_accuracy.json', strict=True)
    if accuracy_data is None:
        accuracy_data = load_with_fallback(suffix, 'oracle_accuracy_ml.json', strict=True)

    oracle_path, oracle_round = find_latest_oracle_forecast()
    oracle_data = load_json(oracle_path) if oracle_path else None

    # Load player forecast and attach it to oracle data
    player_forecasts = find_latest_player_forecast(oracle_round)
    if oracle_data and player_forecasts:
        oracle_data['player_forecasts'] = player_forecasts

    # Enrich oracle predictions with game dates from schedule XML
    schedule_dates = parse_schedule_dates()
    if oracle_data and schedule_dates:
        for pred in oracle_data.get('predictions', []):
            key = (pred.get('Local', ''), pred.get('Road', ''))
            info = schedule_dates.get(key, {})
            pred['Date'] = info.get('date', '')
            pred['Time'] = info.get('time', '')

    # ── Compute Last 5 / home-away records / round results from backtest ─────
    l5_lookup       = {}
    home_rec_lookup = {}   # team -> {'W': n, 'L': n}
    away_rec_lookup = {}
    round_results_lookup = {}  # team -> [{round, result, opp}]
    backtest_data = load_with_fallback(suffix, 'oracle_backtest_predictions.json', 'oracle_backtest_predictions.json')
    if backtest_data:
        from collections import defaultdict
        team_games      = defaultdict(list)   # (rnd, result, opp, is_home)
        home_rec        = defaultdict(lambda: {'W': 0, 'L': 0})
        away_rec        = defaultdict(lambda: {'W': 0, 'L': 0})
        for g in backtest_data:
            # Skip playoff/play-in games (GameCode > 380) — Last 5 and home/away
            # records must reflect regular-season performance only.
            gc = g.get('GameCode', 0)
            if isinstance(gc, float):
                gc = int(gc)
            if gc > 380:
                continue
            home, away, winner = g.get('Home'), g.get('Away'), g.get('ActualWinner')
            rnd = g.get('Round', 0)
            if home and away and winner:
                hw = 'W' if winner == home else 'L'
                aw = 'W' if winner == away else 'L'
                team_games[home].append((rnd, hw, away,  True))
                team_games[away].append((rnd, aw, home, False))
                home_rec[home][hw] += 1
                away_rec[away][aw] += 1
        for team, games in team_games.items():
            games.sort(key=lambda x: x[0])
            l5_lookup[team] = [r for _, r, _, _ in games[-5:]]
            home_rec_lookup[team] = dict(home_rec[team])
            away_rec_lookup[team] = dict(away_rec[team])
            round_results_lookup[team] = [
                {'round': rnd, 'result': res, 'opp': opp, 'home': is_home}
                for rnd, res, opp, is_home in games
            ]

    # ── Build Elo lookup ─────────────────────────────────────────────────────
    elo_lookup = {}
    if elo_data:
        for row in elo_data:
            elo_lookup[row['Team']] = row.get('Elo', 1500.0)

    # ── Build Monte Carlo lookup ─────────────────────────────────────────────
    mc_lookup = {}
    if mc_data:
        for row in mc_data:
            mc_lookup[row['Team']] = row

    # ── Build standings lookup ───────────────────────────────────────────────
    standings_lookup = {}
    if standings_data:
        for code, vals in standings_data.items():
            standings_lookup[code] = vals

    # ── Determine round number ───────────────────────────────────────────────
    # Derive from suffix, standings GP, or oracle round
    round_num = 0
    if suffix:
        m = re.search(r'R(\d+)', suffix)
        if m:
            round_num = int(m.group(1))
    if round_num == 0 and standings_data:
        gp_vals = [v.get('GP', 0) for v in standings_data.values()]
        if gp_vals:
            round_num = max(gp_vals)
    if round_num == 0 and oracle_round and oracle_round > 0:
        round_num = oracle_round - 1  # oracle predicts NEXT round

    print(f"  Determined round: {round_num}")

    # ── Build teams list ─────────────────────────────────────────────────────
    teams = []
    if adjusted:
        for row in adjusted:
            code = row['Team']
            mc = mc_lookup.get(code, {})
            sl = standings_lookup.get(code, {})
            wins = sl.get('W', sl.get('Wins', row.get('Wins', 0)))
            losses = sl.get('L', sl.get('Losses', row.get('Losses', 0)))
            gp = sl.get('GP', wins + losses)
            win_pct = round((wins / gp * 100) if gp > 0 else 0.0, 1)

            teams.append({
                'team': code,
                'name': TEAM_NAMES.get(code, code),
                'wins': wins,
                'losses': losses,
                'win_pct': win_pct,
                'adj_net': round(row.get('Adj_Net', 0.0), 2),
                'adj_off': round(row.get('Adj_Off', 0.0), 2),
                'adj_def': round(row.get('Adj_Def', 0.0), 2),
                'elo': round(elo_lookup.get(code, 1500.0), 1),
                'sos': round(row.get('SOS_WinPct', 0.0) * 100, 1),
                'remaining': row.get('Remaining_Games', 0),
                'top4_pct': mc.get('Top4_Pct', 0.0),
                'top6_pct': mc.get('Top6_Pct', 0.0),
                'top10_pct': mc.get('Top10_Pct', 0.0),
                'avg_wins': round(mc.get('Avg_Wins', wins), 1),
                'current_wins': mc.get('Current_Wins', wins),
                'last5': l5_lookup.get(code, []),
                'home_record': home_rec_lookup.get(code, {'W': 0, 'L': 0}),
                'away_record': away_rec_lookup.get(code, {'W': 0, 'L': 0}),
                'round_results': round_results_lookup.get(code, []),
                'remaining_sos': round(row.get('Remaining_SOS', 0.0), 1),
                'home_games': row.get('Home_Games', 0),
                'away_games': row.get('Away_Games', 0),
                'remaining_opponents': row.get('Remaining_Opponents', []),
                'win_distribution': mc.get('Win_Distribution', {}),
                'seed_distribution': mc.get('Seed_Distribution', {}),
            })

    # Official Euroleague order from the API (standings_{S}.json, written by
    # fetch_standings.py), also after every round for the Standings Race chart;
    # falls back to wins, point difference, points scored.
    standings_order, rank_history, record_history = official_standings(
        load_json('mvp_game_results.json'), load_json(f'schedule_{S}.json'),
        load_json(f'standings_{S}.json'))
    position = {code: i + 1 for i, code in enumerate(standings_order)}
    for t in teams:
        t['position'] = position.get(t['team'])
        t['rank_history'] = rank_history.get(t['team'], [])
        t['record_history'] = record_history.get(t['team'], [])
    teams.sort(key=lambda t: (t['position'] is None, t['position'] or 0,
                              -t['wins'], -t['adj_net']))

    # ── Build MVP list (top 15) with component breakdowns ─────────────────────
    mvp_list = []
    if mvp_data:
        for row in mvp_data[:15]:
            mvp_list.append({
                'rank': row.get('MVP_Rank', 0),
                'player': row.get('PlayerName', ''),
                'team': row.get('TeamCode', ''),
                'mvp_score': round(row.get('MVP_Score', 0.0), 2),
                'avg_pir': round(row.get('AvgPIR', 0.0), 2),
                'avg_gmsc': round(row.get('AvgGmSc', 0.0), 2),
                'wpa': round(row.get('WPA', 0.0), 1),
                'team_win_pct': round(row.get('TeamWinPct', 0.0) * 100, 1),
                'clutch_eff': round(row.get('ClutchEff', 0.0), 4),
                'clutch_pts': round(row.get('ClutchPoints', 0.0), 1),
                'consistency': round(row.get('Consistency', 0.0), 4),
                'gp': row.get('GP', 0),
            })

    # ── Build MVP race timeline ─────────────────────────────────────────────
    # mvp_race_timeline.json has no season marker or producer script; a file with
    # rounds beyond the current round is a previous season's and must not be shown.
    mvp_race = load_json('mvp_race_timeline.json') or []
    if mvp_race and max(r.get('round', 0) for r in mvp_race) > round_num:
        print("  [SKIP] mvp_race_timeline.json is ahead of the current round (stale) - emitting []")
        mvp_race = []
    if mvp_race:
        rounds_in_race = len(set(r['round'] for r in mvp_race))
        print(f"  MVP race timeline: {len(mvp_race)} data points across {rounds_in_race} rounds")

    # ── Build player stats leaderboard ───────────────────────────────────────
    player_stats = build_player_stats(mvp_data, round_num)
    print(f"  Player stats: {len(player_stats)} players")

    # ── Load RAPM ratings ────────────────────────────────────────────────────
    rapm_data = load_with_fallback(suffix, 'rapm_ratings.json', strict=True)
    if rapm_data:
        print(f"  RAPM ratings: {len(rapm_data)} players")
    else:
        rapm_data = []

    # ── Load WPA ratings (normalize keys) ──────────────────────────────────
    wpa_raw = load_with_fallback(suffix, 'wpa_ratings.json', strict=True)
    wpa_data = []
    if wpa_raw:
        for r in wpa_raw:
            wpa_data.append({
                'player': r.get('Player', ''),
                'team': r.get('Team', ''),
                'wpa': round(r.get('Action_WPA', 0.0), 2),
                'plays': r.get('Plays', 0),
                'rank': r.get('WPA_Rank', 0),
            })
        print(f"  WPA ratings: {len(wpa_data)} players")

    # ── Load TPM ratings (normalize keys) ──────────────────────────────────
    tpm_raw = load_with_fallback(suffix, 'tpm_ratings.json', strict=True)
    tpm_data = []
    if tpm_raw:
        for r in tpm_raw:
            tpm_data.append({
                'player': r.get('player.name', ''),
                'team': r.get('player.team.code', ''),
                'tpm_40': round(r.get('TPM_40', 0.0), 2),
                'total_pm': round(r.get('Total_PM', 0.0), 1),
                'gp': r.get('gamesPlayed', 0),
                'mpg': round(r.get('mins_played', 0.0), 1),
                'rank': r.get('TPM_Rank', 0),
            })
        print(f"  TPM ratings: {len(tpm_data)} players")

    # ── Load WIR ratings (normalize keys) ──────────────────────────────────
    wir_raw = load_with_fallback(suffix, 'wir_ratings.json', strict=True)
    wir_data = []
    if wir_raw:
        for r in wir_raw:
            wir_data.append({
                'player': r.get('player.name', ''),
                'team': r.get('player.team.code', ''),
                'wir_40': round(r.get('WIR_40', 0.0), 2),
                'pir_40': round(r.get('PIR_40', 0.0), 2),
                'wir_rank': r.get('WIR_Rank', 0),
                'pir_rank': r.get('PIR_Rank', 0),
                'rank_diff': r.get('Rank_Diff', 0),
                'gp': r.get('gamesPlayed', 0),
                'mpg': round(r.get('mins_played', 0.0), 1),
                'ts_pct': round(r.get('TS%', 0.0), 1),
            })
        print(f"  WIR ratings: {len(wir_data)} players")

    # ── Load GCI ratings ─────────────────────────────────────────────────
    gci_raw = load_with_fallback(suffix, 'gci_ratings.json', strict=True)
    gci_data = None
    if gci_raw:
        gci_data = {
            'teams': gci_raw.get('teams', {}),
            'games': gci_raw.get('games', []),
            'storylines': gci_raw.get('storylines', []),
            'game_of_round': gci_raw.get('game_of_round', {}),
            'superlatives': gci_raw.get('superlatives', {}),
        }
        # Also add GCI to each team object
        for team_obj in teams:
            code = team_obj['team']
            tgci = gci_raw.get('teams', {}).get(code, {})
            team_obj['gci'] = tgci.get('gci', 0.0)
            team_obj['drama_avg'] = round(tgci.get('drama_avg', 0.0), 2)
            team_obj['comeback_count'] = tgci.get('comeback_count', 0)
        print(f"  GCI ratings: {len(gci_raw.get('teams', {}))} teams")

    # ── Compute pairwise playoff matchup probabilities ────────────────────────
    playoff_matchup_probs = {}
    top10 = teams[:10]
    if len(top10) >= 10:
        try:
            import math
            from wp_model_utils import predict_wp

            # Postseason calibration: Platt scaling fit on 2022-2024 EuroLeague
            # playoff + Final Four games (n=71) by backtest_matchup_calibration.py.
            # Shrinks overconfident favorites — see backtest_reliability.png.
            platt_coef = None
            platt_intercept = None
            try:
                with open('calibration_correction.json') as _cf:
                    _platt = json.load(_cf)
                if _platt.get('method') == 'platt_sigmoid_on_logit':
                    platt_coef = float(_platt['coef'])
                    platt_intercept = float(_platt['intercept'])
                    print(f"  Loaded postseason calibration: coef={platt_coef:.3f} "
                          f"intercept={platt_intercept:.3f} (n_fit={_platt.get('n_fit')})")
            except FileNotFoundError:
                pass

            def _platt(p, apply_intercept=True):
                """Apply postseason calibration. The intercept was fit on
                home-team predictions so it captures home-team bias; on
                neutral courts we drop it to keep P(A>B)+P(B>A)=1."""
                if platt_coef is None:
                    return p
                p = min(max(p, 1e-6), 1 - 1e-6)
                z = platt_coef * math.log(p / (1 - p))
                if apply_intercept:
                    z += platt_intercept
                return 1.0 / (1.0 + math.exp(-z))

            # Load game results for HCA data (legacy oracle formula: 75% adjusted net / 25% Elo margin, blended HCA, ML win probability; independent of the season simulator)
            game_results = load_json('mvp_game_results.json')
            hca_global = 0.0
            home_net_map = {}   # team code → home net rating per game
            net_map = {}        # team code → overall net rating per game
            if game_results:
                gdf = pd.DataFrame(game_results)
                played = gdf[(gdf['LocalScore'] > 0) & (gdf['RoadScore'] > 0)]
                hca_global = (played['LocalScore'] - played['RoadScore']).mean()

                td = {}
                for _, row in played.iterrows():
                    loc, road = row['LocalTeam'], row['RoadTeam']
                    lp, rp = row['LocalScore'], row['RoadScore']
                    for t in (loc, road):
                        if t not in td:
                            td[t] = {'HP': 0, 'HA': 0, 'HG': 0, 'AP': 0, 'AA': 0, 'AG': 0}
                    td[loc]['HP'] += lp; td[loc]['HA'] += rp; td[loc]['HG'] += 1
                    td[road]['AP'] += rp; td[road]['AA'] += lp; td[road]['AG'] += 1
                for t, s in td.items():
                    gp = s['HG'] + s['AG']
                    net_map[t] = ((s['HP'] + s['AP']) - (s['HA'] + s['AA'])) / gp if gp > 0 else 0
                    home_net_map[t] = (s['HP'] - s['HA']) / s['HG'] if s['HG'] > 0 else 0

            def _matchup_prob(team_a, team_b, venue):
                """P(team_a wins) under given venue: 'home', 'away', 'neutral'.
                Raw wp_model output is passed through the postseason Platt
                correction when calibration_correction.json is available."""
                a_adj, b_adj = team_a['adj_net'], team_b['adj_net']
                a_elo, b_elo = team_a['elo'], team_b['elo']

                if venue == 'home':
                    # A is home — legacy oracle formula (see above), not the season simulator
                    elo_margin = (a_elo - b_elo + 50) / 25
                    margin_raw = (a_adj - b_adj) * 0.75 + elo_margin * 0.25
                    team_hca = home_net_map.get(team_a['team'], 0) - net_map.get(team_a['team'], 0)
                    blended_hca = (hca_global * 0.7 + team_hca * 0.3) * 0.5
                    pred_margin = margin_raw + blended_hca
                    raw = predict_wp(margin=pred_margin, seconds_remaining=2400, elo_diff=a_elo - b_elo)
                    return _platt(raw)

                elif venue == 'away':
                    # B is home — compute P(B wins) then invert
                    return 1.0 - _matchup_prob(team_b, team_a, 'home')

                else:  # neutral — average both perspectives to cancel is_home bias
                    elo_margin = (a_elo - b_elo) / 25
                    margin_raw = (a_adj - b_adj) * 0.75 + elo_margin * 0.25
                    p_a = predict_wp(margin=margin_raw, seconds_remaining=2400, elo_diff=a_elo - b_elo)
                    p_b = predict_wp(margin=-margin_raw, seconds_remaining=2400, elo_diff=b_elo - a_elo)
                    return _platt((p_a + (1.0 - p_b)) / 2.0, apply_intercept=False)

            for ta in top10:
                inner = {}
                for tb in top10:
                    if ta['team'] == tb['team']:
                        continue
                    inner[tb['team']] = {
                        'home':    round(_matchup_prob(ta, tb, 'home'), 4),
                        'away':    round(_matchup_prob(ta, tb, 'away'), 4),
                        'neutral': round(_matchup_prob(ta, tb, 'neutral'), 4),
                    }
                playoff_matchup_probs[ta['team']] = inner

            print(f"  Playoff matchup probs: {len(top10)} teams, {len(top10) * (len(top10) - 1)} pairs")

        except Exception as e:
            print(f"  Warning: Could not compute playoff matchup probs: {e}")

    # ── Playoff bracket helper functions ─────────────────────────────────────

    def _detect_playoff_label(playoff_results):
        """Generate a human-readable label for the current playoff phase."""
        if not playoff_results:
            return 'Pre-Playoff'

        final = playoff_results.get('final', {})
        if final.get('winner'):
            return 'Final'

        sf = playoff_results.get('sf', {})
        if sf.get('sf1') or sf.get('sf2'):
            return 'Final Four'

        qf = playoff_results.get('qf', {})
        qf_series_lengths = [len(q.get('games', [])) for q in qf.values()]
        if any(n > 0 for n in qf_series_lengths):
            qf_round = max(qf_series_lengths)
            return f'QF Round {qf_round}'

        pi = playoff_results.get('play_in', {})
        pi_count = sum(1 for k in ['game_a', 'game_b', 'game_c'] if pi.get(k) and pi[k].get('winner'))
        if pi_count > 0:
            return 'After Play-Ins'

        return 'Playoffs'

    def _format_game(g):
        """Format a playoff game dict for JSON output."""
        return {
            'gamecode': g.get('game_code'),
            'home': g['home'],
            'away': g['away'],
            'home_score': g['home_score'],
            'away_score': g['away_score'],
            'winner': g['winner'],
            'date': g.get('date', ''),
        }

    def build_playoff_results(game_results, seeded_teams):
        """
        Detect playoff games and build structured bracket results.

        Playoff games have GameCode > 380 in the Euroleague API.
        The schedule XML 'round' field distinguishes phases:
          PI = Play-In, QF = Quarterfinals, SF = Semi-Finals, F = Final

        Args:
            game_results: list of dicts with GameCode, LocalTeam, RoadTeam, LocalScore, RoadScore, Winner
            seeded_teams: list of top-10 team dicts sorted by seed (index 0 = seed 1)

        Returns:
            dict with play_in, qf, sf, final structure, or None if no playoff games exist
        """
        import xml.etree.ElementTree as ET

        # Build game code → round-type mapping from schedule XML
        gc_to_phase = {}
        gc_to_date = {}
        try:
            tree = ET.parse(f'official_schedule_{S}.xml')
            for item in tree.getroot().findall('item'):
                gc_el = item.find('gamecode')
                round_el = item.find('round')
                date_el = item.find('date')
                if gc_el is not None and gc_el.text:
                    gc_text = gc_el.text
                    gc_num = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
                    if round_el is not None and round_el.text:
                        gc_to_phase[gc_num] = round_el.text
                    if date_el is not None and date_el.text:
                        gc_to_date[gc_num] = date_el.text
        except Exception:
            pass

        def _infer_phase(gc):
            # Fallback when the cached schedule XML predates the playoff
            # schedule announcement. Euroleague's GameCode convention:
            # 381-383 = Play-In, 384-403 = QF (best-of-5, 4 series),
            # 404-405 = SF (Final Four), 406 = Final.
            if 381 <= gc <= 383:
                return 'PI'
            if 384 <= gc <= 403:
                return 'QF'
            if gc in (404, 405):
                return 'SF'
            if gc == 406:
                return 'F'
            return ''

        # Filter to playoff games with scores
        playoff_games = []
        for g in game_results:
            gc = g.get('GameCode', 0)
            if isinstance(gc, float):
                gc = int(gc)
            if gc > 380 and g.get('LocalScore', 0) > 0:
                phase = gc_to_phase.get(gc) or _infer_phase(gc)
                playoff_games.append({
                    'game_code': gc,
                    'home': g['LocalTeam'],
                    'away': g['RoadTeam'],
                    'home_score': int(g['LocalScore']),
                    'away_score': int(g['RoadScore']),
                    'winner': g['Winner'],
                    'phase': phase,
                    'date': gc_to_date.get(gc, ''),
                })

        if not playoff_games:
            return None

        # Sort by game code (chronological)
        playoff_games.sort(key=lambda x: x['game_code'])

        # Build seed lookup
        seed_codes = [t['team'] for t in seeded_teams[:10]]

        # --- Play-In ---
        pi_games = [g for g in playoff_games if g['phase'] == 'PI']
        play_in = {
            'game_a': None,
            'game_b': None,
            'game_c': None,
        }

        s7, s8, s9, s10 = (seed_codes[6] if len(seed_codes) > 6 else None,
                            seed_codes[7] if len(seed_codes) > 7 else None,
                            seed_codes[8] if len(seed_codes) > 8 else None,
                            seed_codes[9] if len(seed_codes) > 9 else None)

        for g in pi_games:
            teams_in_game = {g['home'], g['away']}
            if s7 in teams_in_game and s8 in teams_in_game:
                play_in['game_a'] = _format_game(g)
            elif s9 in teams_in_game and s10 in teams_in_game:
                play_in['game_b'] = _format_game(g)
            else:
                play_in['game_c'] = _format_game(g)

        # --- Quarterfinals ---
        qf_games = [g for g in playoff_games if g['phase'] == 'QF']

        final_seed7 = None
        final_seed8 = None
        if play_in['game_a']:
            final_seed7 = play_in['game_a']['winner']
        if play_in['game_c']:
            final_seed8 = play_in['game_c']['winner']

        qf_matchups = {
            '1v8': {'higher': seed_codes[0], 'lower': final_seed8},
            '2v7': {'higher': seed_codes[1], 'lower': final_seed7},
            '3v6': {'higher': seed_codes[2], 'lower': seed_codes[5]},
            '4v5': {'higher': seed_codes[3], 'lower': seed_codes[4]},
        }

        qf = {}
        for label, matchup in qf_matchups.items():
            series_games = []
            series_wins = [0, 0]
            series_winner = None

            for g in qf_games:
                teams_in_game = {g['home'], g['away']}
                if matchup['higher'] in teams_in_game and matchup['lower'] in teams_in_game:
                    series_games.append(_format_game(g))
                    if g['winner'] == matchup['higher']:
                        series_wins[0] += 1
                    else:
                        series_wins[1] += 1
                    if series_wins[0] >= 3:
                        series_winner = matchup['higher']
                    elif series_wins[1] >= 3:
                        series_winner = matchup['lower']

            qf[label] = {
                'games': series_games,
                'series': series_wins,
                'higher_seed': matchup['higher'],
                'lower_seed': matchup['lower'],
                'winner': series_winner,
            }

        # --- Semi-Finals ---
        sf_games = [g for g in playoff_games if g['phase'] == 'SF']
        sf = {'sf1': None, 'sf2': None}

        sf1_teams = {qf['1v8']['winner'], qf['4v5']['winner']} - {None}
        sf2_teams = {qf['2v7']['winner'], qf['3v6']['winner']} - {None}

        for g in sf_games:
            teams_in_game = {g['home'], g['away']}
            if sf1_teams and teams_in_game == sf1_teams:
                sf['sf1'] = _format_game(g)
            elif sf2_teams and teams_in_game == sf2_teams:
                sf['sf2'] = _format_game(g)

        # --- Final ---
        final_games = [g for g in playoff_games if g['phase'] == 'F']
        final = {'game': None, 'winner': None}
        if final_games:
            final['game'] = _format_game(final_games[0])
            final['winner'] = final_games[0]['winner']

        return {
            'play_in': play_in,
            'qf': qf,
            'sf': sf,
            'final': final,
        }

    def compute_championship_odds(playoff_results, matchup_probs, seeded_teams, n_sims=50000):
        """
        Run Monte Carlo simulation of the remaining bracket from current state.

        Returns dict with:
          - 'championship': {team_code: championship_prob_pct}
          - 'series': {slot_id: {team_code: series_win_prob_pct}}

        Slot IDs: qf1..qf4 (1v8, 2v7, 3v6, 4v5), sf1 (w(qf1) vs w(qf4)),
        sf2 (w(qf2) vs w(qf3)), final.
        """
        import random
        random.seed(42)

        if len(seeded_teams) < 10:
            return {'championship': {}, 'series': {}}

        seed_codes = [t['team'] for t in seeded_teams[:10]]

        def _get_prob(team_a, team_b, venue):
            entry = (matchup_probs.get(team_a) or {}).get(team_b)
            if entry:
                return entry.get(venue, 0.5)
            return 0.5

        def _sim_game(team_a, team_b, venue):
            p = _get_prob(team_a, team_b, venue)
            return team_a if random.random() < p else team_b

        def _sim_series(higher, lower):
            home_pattern = [True, True, False, False, True]
            wins_h, wins_l = 0, 0
            for g in range(5):
                venue = 'home' if home_pattern[g] else 'away'
                winner = _sim_game(higher, lower, venue)
                if winner == higher:
                    wins_h += 1
                else:
                    wins_l += 1
                if wins_h >= 3 or wins_l >= 3:
                    break
            return higher if wins_h >= 3 else lower

        # Extract known results
        pi_a_winner = None
        pi_a_loser = None
        pi_b_winner = None
        pi_c_winner = None
        qf_winners = {'1v8': None, '2v7': None, '3v6': None, '4v5': None}
        qf_series_state = {}
        sf_winners = {'sf1': None, 'sf2': None}
        final_winner = None

        if playoff_results:
            pi = playoff_results.get('play_in', {})
            if pi.get('game_a') and pi['game_a'].get('winner'):
                pi_a_winner = pi['game_a']['winner']
                ga = pi['game_a']
                pi_a_loser = ga['away'] if ga['winner'] == ga['home'] else ga['home']
            if pi.get('game_b') and pi['game_b'].get('winner'):
                pi_b_winner = pi['game_b']['winner']
            if pi.get('game_c') and pi['game_c'].get('winner'):
                pi_c_winner = pi['game_c']['winner']

            qf_data = playoff_results.get('qf', {})
            for label in ['1v8', '2v7', '3v6', '4v5']:
                qf_entry = qf_data.get(label, {})
                if qf_entry.get('winner'):
                    qf_winners[label] = qf_entry['winner']
                else:
                    series = qf_entry.get('series') or [0, 0]
                    # Only track in-progress state when at least one game was played.
                    # Otherwise the data-derived lower seed may be None (play-in seed 8
                    # isn't known until Game C finishes), so fall through to the
                    # fresh-simulation branch which uses the newly computed pair.
                    if (series[0] > 0 or series[1] > 0) and qf_entry.get('higher_seed') and qf_entry.get('lower_seed'):
                        qf_series_state[label] = (
                            series[0], series[1],
                            qf_entry['higher_seed'], qf_entry['lower_seed']
                        )

            sf_data = playoff_results.get('sf', {})
            if sf_data.get('sf1') and sf_data['sf1'].get('winner'):
                sf_winners['sf1'] = sf_data['sf1']['winner']
            if sf_data.get('sf2') and sf_data['sf2'].get('winner'):
                sf_winners['sf2'] = sf_data['sf2']['winner']

            final_data = playoff_results.get('final', {})
            if final_data.get('winner'):
                final_winner = final_data['winner']

        # Map from QF label (data-side) to slot ID (URL-side)
        qf_label_to_slot = {'1v8': 'qf1', '2v7': 'qf2', '3v6': 'qf3', '4v5': 'qf4'}

        counts = {code: 0 for code in seed_codes}
        series_counts = {slot: {} for slot in ('qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final')}

        for _ in range(n_sims):
            ga_w = pi_a_winner or _sim_game(seed_codes[6], seed_codes[7], 'home')
            ga_l = pi_a_loser or (seed_codes[7] if ga_w == seed_codes[6] else seed_codes[6])
            gb_w = pi_b_winner or _sim_game(seed_codes[8], seed_codes[9], 'home')
            gc_w = pi_c_winner or _sim_game(ga_l, gb_w, 'home')

            s7 = ga_w
            s8 = gc_w

            qf_pairs = {
                '1v8': (seed_codes[0], s8),
                '2v7': (seed_codes[1], s7),
                '3v6': (seed_codes[2], seed_codes[5]),
                '4v5': (seed_codes[3], seed_codes[4]),
            }

            qf_w = {}
            for label, (higher, lower) in qf_pairs.items():
                if qf_winners[label]:
                    qf_w[label] = qf_winners[label]
                elif label in qf_series_state:
                    h_wins, l_wins, h_seed, l_seed = qf_series_state[label]
                    while h_wins < 3 and l_wins < 3:
                        game_num = h_wins + l_wins
                        home_pattern = [True, True, False, False, True]
                        venue = 'home' if home_pattern[game_num] else 'away'
                        w = _sim_game(h_seed, l_seed, venue)
                        if w == h_seed:
                            h_wins += 1
                        else:
                            l_wins += 1
                    qf_w[label] = h_seed if h_wins >= 3 else l_seed
                else:
                    qf_w[label] = _sim_series(higher, lower)

                slot = qf_label_to_slot[label]
                series_counts[slot][qf_w[label]] = series_counts[slot].get(qf_w[label], 0) + 1

            sf1_w = sf_winners['sf1'] or _sim_game(qf_w['1v8'], qf_w['4v5'], 'neutral')
            sf2_w = sf_winners['sf2'] or _sim_game(qf_w['2v7'], qf_w['3v6'], 'neutral')
            series_counts['sf1'][sf1_w] = series_counts['sf1'].get(sf1_w, 0) + 1
            series_counts['sf2'][sf2_w] = series_counts['sf2'].get(sf2_w, 0) + 1

            champ = final_winner or _sim_game(sf1_w, sf2_w, 'neutral')
            series_counts['final'][champ] = series_counts['final'].get(champ, 0) + 1
            counts[champ] += 1

        championship_pcts = {code: round(count / n_sims * 100, 1) for code, count in counts.items()}
        series_pcts = {
            slot: {team: round(c / n_sims * 100, 1) for team, c in team_counts.items()}
            for slot, team_counts in series_counts.items()
        }

        return {'championship': championship_pcts, 'series': series_pcts}

    def build_playoff_recaps(playoff_results, odds_before, odds_after, matchup_probs, seeded_teams):
        """
        Generate recap card data for each completed playoff game.
        """
        if not playoff_results:
            return []

        recaps = []

        def _get_pre_game_prob(home, away, venue):
            entry = (matchup_probs.get(home) or {}).get(away)
            if entry:
                return entry.get(venue, 0.5)
            return 0.5

        def _add_recap(game, round_label, series=None, series_label_str=None):
            if not game or not game.get('winner'):
                return

            home, away = game['home'], game['away']
            winner = game['winner']

            venue = 'neutral' if round_label in ('Semi-Final 1', 'Semi-Final 2', 'Final') else 'home'
            home_prob = _get_pre_game_prob(home, away, venue)
            winner_prob = home_prob if winner == home else (1 - home_prob)

            is_upset = winner_prob < 0.4

            recap = {
                'gamecode': game.get('gamecode'),
                'date': game.get('date', ''),
                'round': round_label,
                'home': home,
                'away': away,
                'home_score': game['home_score'],
                'away_score': game['away_score'],
                'winner': winner,
                'pre_game_win_prob': round(winner_prob * 100, 1),
                'is_upset': is_upset,
            }

            if series is not None:
                recap['series'] = series
            if series_label_str is not None:
                recap['series_label'] = series_label_str

            recap['championship_odds_before'] = {
                home: odds_before.get(home, 0),
                away: odds_before.get(away, 0),
            }
            recap['championship_odds_after'] = {
                home: odds_after.get(home, 0),
                away: odds_after.get(away, 0),
            }

            recaps.append(recap)

        # Play-In games
        pi = playoff_results.get('play_in', {})
        _add_recap(pi.get('game_a'), 'Play-In Game A')
        _add_recap(pi.get('game_b'), 'Play-In Game B')
        _add_recap(pi.get('game_c'), 'Play-In Game C')

        # Quarterfinal games
        qf = playoff_results.get('qf', {})
        for label in ['1v8', '2v7', '3v6', '4v5']:
            qf_entry = qf.get(label, {})
            higher = qf_entry.get('higher_seed', '?')
            lower = qf_entry.get('lower_seed', '?')

            for i, game in enumerate(qf_entry.get('games', [])):
                h_w = sum(1 for g2 in qf_entry['games'][:i+1] if g2['winner'] == higher)
                l_w = (i + 1) - h_w

                if h_w > l_w:
                    sl = f"{higher} leads {h_w}-{l_w}"
                elif l_w > h_w:
                    sl = f"{lower} leads {l_w}-{h_w}"
                elif h_w == 3 or l_w == 3:
                    sl = f"Series over"
                else:
                    sl = f"Series tied {h_w}-{l_w}"

                _add_recap(game, f'QF {label} Game {i+1}', [h_w, l_w], sl)

        # Semi-Finals
        sf = playoff_results.get('sf', {})
        _add_recap(sf.get('sf1'), 'Semi-Final 1')
        _add_recap(sf.get('sf2'), 'Semi-Final 2')

        # Final
        final = playoff_results.get('final', {})
        _add_recap(final.get('game'), 'Final')

        # Sort by date descending
        recaps.sort(key=lambda r: r.get('date', ''), reverse=True)

        return recaps

    def compute_path_to_title(playoff_results, matchup_probs, seeded_teams, n_sims=10000):
        """
        For each playoff-eligible team, simulate the remaining bracket n_sims times.
        Track reach probability per round, opponent distribution, and win probabilities.
        Returns list of per-team path entries matching the path_to_title spec.
        """
        import random
        random.seed(42)

        if len(seeded_teams) < 10:
            return []

        seed_codes = [t['team'] for t in seeded_teams[:10]]

        def _get_prob(team_a, team_b, venue):
            entry = (matchup_probs.get(team_a) or {}).get(team_b)
            if entry:
                return entry.get(venue, 0.5)
            return 0.5

        def _sim_game(team_a, team_b, venue):
            p = _get_prob(team_a, team_b, venue)
            return team_a if random.random() < p else team_b

        def _sim_series(higher, lower):
            home_pattern = [True, True, False, False, True]
            wins_h, wins_l = 0, 0
            for g in range(5):
                venue = 'home' if home_pattern[g] else 'away'
                winner = _sim_game(higher, lower, venue)
                if winner == higher:
                    wins_h += 1
                else:
                    wins_l += 1
                if wins_h >= 3 or wins_l >= 3:
                    break
            return higher if wins_h >= 3 else lower

        # Extract locked results (same pattern as compute_championship_odds)
        pi_a_winner = None
        pi_a_loser = None
        pi_b_winner = None
        pi_c_winner = None
        qf_winners = {'1v8': None, '2v7': None, '3v6': None, '4v5': None}
        qf_series_state = {}
        sf_winners = {'sf1': None, 'sf2': None}
        final_winner = None

        if playoff_results:
            pi = playoff_results.get('play_in', {})
            if pi.get('game_a') and pi['game_a'].get('winner'):
                pi_a_winner = pi['game_a']['winner']
                ga = pi['game_a']
                pi_a_loser = ga['away'] if ga['winner'] == ga['home'] else ga['home']
            if pi.get('game_b') and pi['game_b'].get('winner'):
                pi_b_winner = pi['game_b']['winner']
            if pi.get('game_c') and pi['game_c'].get('winner'):
                pi_c_winner = pi['game_c']['winner']

            qf_data = playoff_results.get('qf', {})
            for label in ['1v8', '2v7', '3v6', '4v5']:
                qf_entry = qf_data.get(label, {})
                if qf_entry.get('winner'):
                    qf_winners[label] = qf_entry['winner']
                else:
                    series = qf_entry.get('series') or [0, 0]
                    # Only track in-progress state when at least one game was played.
                    # Otherwise the data-derived lower seed may be None (play-in seed 8
                    # isn't known until Game C finishes), so fall through to the
                    # fresh-simulation branch which uses the newly computed pair.
                    if (series[0] > 0 or series[1] > 0) and qf_entry.get('higher_seed') and qf_entry.get('lower_seed'):
                        qf_series_state[label] = (
                            series[0], series[1],
                            qf_entry['higher_seed'], qf_entry['lower_seed']
                        )

            sf_data = playoff_results.get('sf', {})
            if sf_data.get('sf1') and sf_data['sf1'].get('winner'):
                sf_winners['sf1'] = sf_data['sf1']['winner']
            if sf_data.get('sf2') and sf_data['sf2'].get('winner'):
                sf_winners['sf2'] = sf_data['sf2']['winner']

            final_data = playoff_results.get('final', {})
            if final_data.get('winner'):
                final_winner = final_data['winner']

        # Per-team counters: reach[round] and opponent_wins[round][opp] and opponent_faced[round][opp]
        round_keys = ['play_in_1', 'play_in_2', 'qf', 'sf', 'final', 'champion']
        reach = {code: {r: 0 for r in round_keys} for code in seed_codes}
        opp_faced = {code: {r: {} for r in round_keys} for code in seed_codes}
        opp_wins = {code: {r: {} for r in round_keys} for code in seed_codes}

        play_in_teams = set(seed_codes[6:10])  # seeds 7-10 participate in play-in

        # Pre-compute each play-in team's current state — which play-in game is the
        # next one we should attribute to them in the sim. Four shapes:
        #   ('first_game', opp_code) — haven't played Game A/B yet; opp is deterministic
        #   'game_c_vs_gbw'          — lost Game A, waiting for Game C; opp = gb_w per sim
        #   'game_c_vs_gal'          — won Game B, waiting for Game C; opp = ga_l per sim
        #   'done'                   — won Game A / lost Game B / played Game C: no next opp
        pi_state = {}
        s7c, s8c, s9c, s10c = seed_codes[6], seed_codes[7], seed_codes[8], seed_codes[9]
        if pi_a_winner is None:
            pi_state[s7c] = ('first_game', s8c)
            pi_state[s8c] = ('first_game', s7c)
        else:
            pi_state[pi_a_winner] = 'done'
            pi_state[pi_a_loser] = 'done' if pi_c_winner is not None else 'game_c_vs_gbw'
        if pi_b_winner is None:
            pi_state[s9c] = ('first_game', s10c)
            pi_state[s10c] = ('first_game', s9c)
        else:
            pi_b_loser = s10c if pi_b_winner == s9c else s9c
            pi_state[pi_b_loser] = 'done'
            pi_state[pi_b_winner] = 'done' if pi_c_winner is not None else 'game_c_vs_gal'

        for _ in range(n_sims):
            # Play-In
            ga_w = pi_a_winner or _sim_game(seed_codes[6], seed_codes[7], 'home')
            ga_l = pi_a_loser or (seed_codes[7] if ga_w == seed_codes[6] else seed_codes[6])
            gb_w = pi_b_winner or _sim_game(seed_codes[8], seed_codes[9], 'home')
            gb_l = seed_codes[9] if gb_w == seed_codes[8] else seed_codes[8]
            gc_w = pi_c_winner or _sim_game(ga_l, gb_w, 'home')

            # Play-In reach + opponent tracking — split into play_in_1 (first scheduled
            # game: A for 7/8, B for 9/10) and play_in_2 (Game C). pi_state determines
            # which stage(s) to attribute for each team based on pre-sim locked results.
            for code in play_in_teams:
                state = pi_state[code]
                if state == 'done':
                    continue
                if isinstance(state, tuple):  # ('first_game', opp)
                    opp = state[1]
                    reach[code]['play_in_1'] += 1
                    opp_faced[code]['play_in_1'][opp] = opp_faced[code]['play_in_1'].get(opp, 0) + 1
                    in_game_a = code in (s7c, s8c)
                    first_won = (ga_w == code) if in_game_a else (gb_w == code)
                    if first_won:
                        opp_wins[code]['play_in_1'][opp] = opp_wins[code]['play_in_1'].get(opp, 0) + 1
                    reaches_gc = (not first_won) if in_game_a else first_won
                    if reaches_gc:
                        reach[code]['play_in_2'] += 1
                        opp_c = gb_w if in_game_a else ga_l
                        opp_faced[code]['play_in_2'][opp_c] = opp_faced[code]['play_in_2'].get(opp_c, 0) + 1
                        if gc_w == code:
                            opp_wins[code]['play_in_2'][opp_c] = opp_wins[code]['play_in_2'].get(opp_c, 0) + 1
                elif state == 'game_c_vs_gbw':
                    reach[code]['play_in_2'] += 1
                    opp_c = gb_w
                    opp_faced[code]['play_in_2'][opp_c] = opp_faced[code]['play_in_2'].get(opp_c, 0) + 1
                    if gc_w == code:
                        opp_wins[code]['play_in_2'][opp_c] = opp_wins[code]['play_in_2'].get(opp_c, 0) + 1
                elif state == 'game_c_vs_gal':
                    reach[code]['play_in_2'] += 1
                    opp_c = ga_l
                    opp_faced[code]['play_in_2'][opp_c] = opp_faced[code]['play_in_2'].get(opp_c, 0) + 1
                    if gc_w == code:
                        opp_wins[code]['play_in_2'][opp_c] = opp_wins[code]['play_in_2'].get(opp_c, 0) + 1

            # s7 (winner of Game A), s8 (winner of Game C)
            s7 = ga_w
            s8 = gc_w

            # Seeds 1-6 and s7, s8 reach QF
            qf_participants = set(seed_codes[:6]) | {s7, s8}
            for t in qf_participants:
                reach[t]['qf'] += 1

            qf_pairs = {
                '1v8': (seed_codes[0], s8),
                '2v7': (seed_codes[1], s7),
                '3v6': (seed_codes[2], seed_codes[5]),
                '4v5': (seed_codes[3], seed_codes[4]),
            }

            qf_w = {}
            for label, (higher, lower) in qf_pairs.items():
                # Record opponents faced in QF
                opp_faced[higher]['qf'][lower] = opp_faced[higher]['qf'].get(lower, 0) + 1
                opp_faced[lower]['qf'][higher] = opp_faced[lower]['qf'].get(higher, 0) + 1

                if qf_winners[label]:
                    qf_w[label] = qf_winners[label]
                elif label in qf_series_state:
                    h_wins, l_wins, h_seed, l_seed = qf_series_state[label]
                    while h_wins < 3 and l_wins < 3:
                        game_num = h_wins + l_wins
                        home_pattern = [True, True, False, False, True]
                        venue = 'home' if home_pattern[game_num] else 'away'
                        w = _sim_game(h_seed, l_seed, venue)
                        if w == h_seed:
                            h_wins += 1
                        else:
                            l_wins += 1
                    qf_w[label] = h_seed if h_wins >= 3 else l_seed
                else:
                    qf_w[label] = _sim_series(higher, lower)

                winner = qf_w[label]
                loser = lower if winner == higher else higher
                opp_wins[winner]['qf'][loser] = opp_wins[winner]['qf'].get(loser, 0) + 1

            # SF
            sf1_participants = {qf_w['1v8'], qf_w['4v5']}
            sf2_participants = {qf_w['2v7'], qf_w['3v6']}
            for t in sf1_participants | sf2_participants:
                reach[t]['sf'] += 1

            opp_faced[qf_w['1v8']]['sf'][qf_w['4v5']] = opp_faced[qf_w['1v8']]['sf'].get(qf_w['4v5'], 0) + 1
            opp_faced[qf_w['4v5']]['sf'][qf_w['1v8']] = opp_faced[qf_w['4v5']]['sf'].get(qf_w['1v8'], 0) + 1
            opp_faced[qf_w['2v7']]['sf'][qf_w['3v6']] = opp_faced[qf_w['2v7']]['sf'].get(qf_w['3v6'], 0) + 1
            opp_faced[qf_w['3v6']]['sf'][qf_w['2v7']] = opp_faced[qf_w['3v6']]['sf'].get(qf_w['2v7'], 0) + 1

            sf1_w = sf_winners['sf1'] or _sim_game(qf_w['1v8'], qf_w['4v5'], 'neutral')
            sf2_w = sf_winners['sf2'] or _sim_game(qf_w['2v7'], qf_w['3v6'], 'neutral')

            sf1_loser = qf_w['4v5'] if sf1_w == qf_w['1v8'] else qf_w['1v8']
            sf2_loser = qf_w['3v6'] if sf2_w == qf_w['2v7'] else qf_w['2v7']
            opp_wins[sf1_w]['sf'][sf1_loser] = opp_wins[sf1_w]['sf'].get(sf1_loser, 0) + 1
            opp_wins[sf2_w]['sf'][sf2_loser] = opp_wins[sf2_w]['sf'].get(sf2_loser, 0) + 1

            # Final
            reach[sf1_w]['final'] += 1
            reach[sf2_w]['final'] += 1

            opp_faced[sf1_w]['final'][sf2_w] = opp_faced[sf1_w]['final'].get(sf2_w, 0) + 1
            opp_faced[sf2_w]['final'][sf1_w] = opp_faced[sf2_w]['final'].get(sf1_w, 0) + 1

            champ = final_winner or _sim_game(sf1_w, sf2_w, 'neutral')
            reach[champ]['champion'] += 1
            final_loser = sf2_w if champ == sf1_w else sf1_w
            opp_wins[champ]['final'][final_loser] = opp_wins[champ]['final'].get(final_loser, 0) + 1

        # Build output per team
        def _build_branches(team, round_key):
            """Top 2-3 opponents sorted by reach_prob_for_opp desc, truncate at cum 90% or 3 entries."""
            opps = opp_faced[team][round_key]
            team_reach = reach[team][round_key]
            if team_reach == 0:
                return []
            sorted_opps = sorted(opps.items(), key=lambda kv: kv[1], reverse=True)
            branches = []
            cum = 0.0
            for opp_code, faced_count in sorted_opps:
                reach_pct = faced_count / team_reach * 100
                wins_vs = opp_wins[team][round_key].get(opp_code, 0)
                win_pct = wins_vs / faced_count * 100 if faced_count > 0 else 0.0
                branches.append({
                    'opponent': opp_code,
                    'reach_prob_for_opp': round(reach_pct, 1),
                    'win_prob_vs': round(win_pct, 1),
                })
                cum += reach_pct
                if len(branches) >= 3 or cum >= 90.0:
                    break
            return branches

        def _round_win_prob(team, round_key):
            """P(team wins round_key | reached it) = (times reached next round) / (times reached this round)."""
            this_round_count = reach[team][round_key]
            if this_round_count == 0:
                return 0.0
            if round_key in ('play_in_1', 'play_in_2'):
                wins_total = sum(opp_wins[team][round_key].values())
                return round(wins_total / this_round_count * 100, 1)
            next_key = {'qf': 'sf', 'sf': 'final', 'final': 'champion'}.get(round_key)
            if next_key is None:
                return 0.0
            return round(reach[team][next_key] / this_round_count * 100, 1)

        # Determine completed rounds from playoff_results for each team
        def _completed_round_data(team):
            """Returns dict of round -> completed round info, based on playoff_results."""
            done = {}
            if not playoff_results:
                return done

            pi = playoff_results.get('play_in', {})
            ga = pi.get('game_a') or {}
            gb = pi.get('game_b') or {}
            gc = pi.get('game_c') or {}

            first_game = None
            if team in (ga.get('home'), ga.get('away')):
                first_game = ga
            elif team in (gb.get('home'), gb.get('away')):
                first_game = gb
            if first_game and first_game.get('winner'):
                opp = first_game['away'] if team == first_game['home'] else first_game['home']
                done['play_in_1'] = {
                    'status': 'completed',
                    'actual_opponent': opp,
                    'actual_result': 'won' if first_game['winner'] == team else 'lost',
                    'series': [1, 0] if first_game['winner'] == team else [0, 1],
                    'reach_prob': 100.0,
                }

            if gc and gc.get('winner') and team in (gc.get('home'), gc.get('away')):
                opp = gc['away'] if team == gc['home'] else gc['home']
                done['play_in_2'] = {
                    'status': 'completed',
                    'actual_opponent': opp,
                    'actual_result': 'won' if gc['winner'] == team else 'lost',
                    'series': [1, 0] if gc['winner'] == team else [0, 1],
                    'reach_prob': 100.0,
                }

            # QF
            qf_data = playoff_results.get('qf', {})
            for label, qf_entry in qf_data.items():
                higher = qf_entry.get('higher_seed')
                lower = qf_entry.get('lower_seed')
                if team not in (higher, lower):
                    continue
                opp = lower if team == higher else higher
                series = qf_entry.get('series', [0, 0])
                t_wins = series[0] if team == higher else series[1]
                o_wins = series[1] if team == higher else series[0]
                if qf_entry.get('winner'):
                    done['qf'] = {
                        'status': 'completed',
                        'actual_opponent': opp,
                        'actual_result': 'won' if qf_entry['winner'] == team else 'lost',
                        'series': [t_wins, o_wins],
                        'reach_prob': 100.0,
                    }
                elif series[0] > 0 or series[1] > 0:
                    done['qf'] = {
                        'status': 'in_progress',
                        'actual_opponent': opp,
                        'series': [t_wins, o_wins],
                        'reach_prob': 100.0,
                    }

            # SF
            sf_data = playoff_results.get('sf', {})
            for sk in ['sf1', 'sf2']:
                g = sf_data.get(sk)
                if g and g.get('winner') and team in (g.get('home'), g.get('away')):
                    opp = g['away'] if team == g['home'] else g['home']
                    done['sf'] = {
                        'status': 'completed',
                        'actual_opponent': opp,
                        'actual_result': 'won' if g['winner'] == team else 'lost',
                        'series': [1, 0] if g['winner'] == team else [0, 1],
                        'reach_prob': 100.0,
                    }

            # Final
            final_data = playoff_results.get('final', {})
            g = final_data.get('game') if final_data else None
            if g and g.get('winner') and team in (g.get('home'), g.get('away')):
                opp = g['away'] if team == g['home'] else g['home']
                done['final'] = {
                    'status': 'completed',
                    'actual_opponent': opp,
                    'actual_result': 'won' if g['winner'] == team else 'lost',
                    'series': [1, 0] if g['winner'] == team else [0, 1],
                    'reach_prob': 100.0,
                }

            return done

        result = []
        for idx, code in enumerate(seed_codes):
            is_play_in_team = idx >= 6
            completed = _completed_round_data(code)

            # Determine status + eliminated_at
            champ_pct = reach[code]['champion'] / n_sims * 100
            is_champion = final_winner == code

            # Find earliest completed 'lost' round. Losing play_in_1 only eliminates
            # seeds 9/10 (they don't get a Game C); seeds 7/8 advance to Game C.
            eliminated_at = None
            if not is_champion:
                for rk in ['play_in_1', 'play_in_2', 'qf', 'sf', 'final']:
                    if completed.get(rk, {}).get('actual_result') == 'lost':
                        if rk == 'play_in_1' and idx in (6, 7):
                            continue
                        eliminated_at = rk
                        break

            if is_champion:
                status = 'champion'
            elif eliminated_at:
                status = 'eliminated'
            else:
                status = 'alive'

            # Build rounds array
            rounds = []
            for rk in ['play_in_1', 'play_in_2', 'qf', 'sf', 'final']:
                if rk in ('play_in_1', 'play_in_2') and not is_play_in_team:
                    rounds.append({'round': rk, 'status': 'unreached', 'reach_prob': 0.0})
                    continue

                if rk in completed:
                    rounds.append({'round': rk, **completed[rk]})
                    continue

                # Not completed — upcoming or unreached
                rp = reach[code][rk] / n_sims * 100
                if rp == 0:
                    rounds.append({'round': rk, 'status': 'unreached', 'reach_prob': 0.0})
                else:
                    rounds.append({
                        'round': rk,
                        'status': 'upcoming',
                        'reach_prob': round(rp, 1),
                        'win_prob': _round_win_prob(code, rk),
                        'branches': _build_branches(code, rk),
                    })

            result.append({
                'team': code,
                'status': status,
                'eliminated_at': eliminated_at,
                'championship_odds': round(champ_pct, 1),
                'rounds': rounds,
            })

        # Sort by championship odds desc, eliminated teams at bottom
        result.sort(key=lambda e: (
            0 if e['status'] != 'eliminated' else 1,
            -e['championship_odds']
        ))

        return result

    def compute_series_data(playoff_results, matchup_probs, seeded_teams,
                            series_win_probs, games_df, teams_by_code,
                            box_metrics, paint_share, schedule_index=None):
        """
        Build per-series entries for Series Hub pages.

        Returns dict keyed by slot_id (qf1..qf4, sf1, sf2, final). Each entry has
        id, round, label, format, home_pattern, high_seed, low_seed, status, wins,
        winner, series_win_prob, games[], rs_h2h[].

        Seeds resolve left-to-right: QFs populate from initial seeding; SFs/Final
        populate once prerequisite series are decided. Unresolved sides remain null.

        schedule_index, if provided, maps frozenset({code_a, code_b}) → list of
        schedule rows (sorted by gameday) so upcoming games can carry their
        scheduled date and tip-off time.
        """
        schedule_index = schedule_index or {}
        if len(seeded_teams) < 10:
            return {}

        seed_codes = [t['team'] for t in seeded_teams[:10]]

        def _seed_obj(code, seed_num):
            if not code:
                return None
            return {'team': code, 'seed': seed_num}

        qf_winners = {'1v8': None, '2v7': None, '3v6': None, '4v5': None}
        sf_winners = {'sf1': None, 'sf2': None}
        final_winner = None
        pi_a_winner = None
        pi_c_winner = None
        if playoff_results:
            for label in qf_winners:
                entry = (playoff_results.get('qf') or {}).get(label) or {}
                if entry.get('winner'):
                    qf_winners[label] = entry['winner']
            sf_data = playoff_results.get('sf') or {}
            if sf_data.get('sf1') and sf_data['sf1'].get('winner'):
                sf_winners['sf1'] = sf_data['sf1']['winner']
            if sf_data.get('sf2') and sf_data['sf2'].get('winner'):
                sf_winners['sf2'] = sf_data['sf2']['winner']
            final_data = playoff_results.get('final') or {}
            if final_data.get('winner'):
                final_winner = final_data['winner']
            pi = playoff_results.get('play_in') or {}
            if pi.get('game_a') and pi['game_a'].get('winner'):
                pi_a_winner = pi['game_a']['winner']
            if pi.get('game_c') and pi['game_c'].get('winner'):
                pi_c_winner = pi['game_c']['winner']

        # Seeds 7 and 8 are decided by the play-in; leave unresolved until then.
        # Once the playoff bracket exists, prefer the explicit higher_seed /
        # lower_seed already recorded on each QF entry (authoritative source).
        seed_7_team = pi_a_winner
        seed_8_team = pi_c_winner

        def _qf_seeds(qf_label, default_high, default_low, seed_num_high, seed_num_low):
            high_code, low_code = default_high, default_low
            if playoff_results:
                qf_entry = (playoff_results.get('qf') or {}).get(qf_label) or {}
                if qf_entry.get('higher_seed'):
                    high_code = qf_entry['higher_seed']
                if qf_entry.get('lower_seed'):
                    low_code = qf_entry['lower_seed']
            return (_seed_obj(high_code, seed_num_high), _seed_obj(low_code, seed_num_low))

        qf_seeding = {
            'qf1': _qf_seeds('1v8', seed_codes[0], seed_8_team, 1, 8),
            'qf2': _qf_seeds('2v7', seed_codes[1], seed_7_team, 2, 7),
            'qf3': _qf_seeds('3v6', seed_codes[2], seed_codes[5], 3, 6),
            'qf4': _qf_seeds('4v5', seed_codes[3], seed_codes[4], 4, 5),
        }

        sf1_high = _seed_obj(qf_winners['1v8'], None) if qf_winners['1v8'] else None
        sf1_low = _seed_obj(qf_winners['4v5'], None) if qf_winners['4v5'] else None
        sf2_high = _seed_obj(qf_winners['2v7'], None) if qf_winners['2v7'] else None
        sf2_low = _seed_obj(qf_winners['3v6'], None) if qf_winners['3v6'] else None
        final_high = _seed_obj(sf_winners['sf1'], None) if sf_winners['sf1'] else None
        final_low = _seed_obj(sf_winners['sf2'], None) if sf_winners['sf2'] else None

        slot_defs = {
            'qf1':   {'round': 'qf',    'label': 'Quarterfinal 1', 'seeds': qf_seeding['qf1']},
            'qf2':   {'round': 'qf',    'label': 'Quarterfinal 2', 'seeds': qf_seeding['qf2']},
            'qf3':   {'round': 'qf',    'label': 'Quarterfinal 3', 'seeds': qf_seeding['qf3']},
            'qf4':   {'round': 'qf',    'label': 'Quarterfinal 4', 'seeds': qf_seeding['qf4']},
            'sf1':   {'round': 'sf',    'label': 'Semifinal 1',    'seeds': (sf1_high, sf1_low)},
            'sf2':   {'round': 'sf',    'label': 'Semifinal 2',    'seeds': (sf2_high, sf2_low)},
            'final': {'round': 'final', 'label': 'Final',          'seeds': (final_high, final_low)},
        }

        def _rs_h2h(team_a, team_b):
            if not team_a or not team_b or games_df is None or len(games_df) == 0:
                return []
            df = games_df[
                (games_df['round'] == 'RS') &
                (games_df['played'] == True) &
                (
                    ((games_df['homecode'] == team_a) & (games_df['awaycode'] == team_b)) |
                    ((games_df['homecode'] == team_b) & (games_df['awaycode'] == team_a))
                )
            ]
            meetings = []
            for _, row in df.iterrows():
                home = row['homecode']
                away = row['awaycode']
                hs = int(row['homescore']) if row['homescore'] else 0
                aws = int(row['awayscore']) if row['awayscore'] else 0
                winner = home if hs > aws else away
                meetings.append({
                    'round': int(row.get('gameday') or 0),
                    'home': home,
                    'away': away,
                    'home_score': hs,
                    'away_score': aws,
                    'winner': winner,
                })
            meetings.sort(key=lambda m: m['round'])
            return meetings

        qf_label_for_slot = {'qf1': '1v8', 'qf2': '2v7', 'qf3': '3v6', 'qf4': '4v5'}

        def _build_prob_pair(slot_id, high_code, low_code):
            sp = series_win_probs.get(slot_id, {}) if series_win_probs else {}
            h = round(sp.get(high_code, 0.0), 1) if high_code else 0.0
            l = round(sp.get(low_code, 0.0), 1) if low_code else 0.0
            return {'high': h, 'low': l}

        def _schedule_home(game_num, high_code, low_code):
            pattern = ['high', 'high', 'low', 'low', 'high']
            side = pattern[game_num - 1]
            if side == 'high':
                return high_code, low_code
            return low_code, high_code

        def _build_games(completed_games, high_code, low_code, wins_h, wins_l, status, fmt):
            games = []
            completed_by_num = {g.get('game_num', idx + 1): g for idx, g in enumerate(completed_games)}
            sweep_or_done = status == 'completed'
            games_played = wins_h + wins_l
            total_games = 1 if fmt == 'single_game' else 5

            sched_entries = []
            if high_code and low_code:
                sched_entries = schedule_index.get(frozenset({high_code, low_code}), [])

            def _sched_for(game_num):
                idx = game_num - 1
                if 0 <= idx < len(sched_entries):
                    row = sched_entries[idx]
                    # Schedule API encodes confirmeddate/confirmedtime as strings 'true'/'false'.
                    cd = str(row.get('confirmeddate', '')).lower() == 'true'
                    ct = str(row.get('confirmedtime', '')).lower() == 'true'
                    return {
                        'date': row.get('date') or '',
                        'tipoff': row.get('startime') or '',
                        'arena': row.get('arenaname') or '',
                        'confirmed': cd and ct,
                    }
                return None

            for game_num in range(1, total_games + 1):
                gc = completed_by_num.get(game_num)
                if gc:
                    games.append({
                        'game_num': game_num,
                        'status': 'completed',
                        'date': gc.get('date', ''),
                        'home': gc.get('home'),
                        'away': gc.get('away'),
                        'home_score': gc.get('home_score'),
                        'away_score': gc.get('away_score'),
                        'winner': gc.get('winner'),
                        'gamecode': gc.get('gamecode'),
                    })
                    continue

                if sweep_or_done and game_num > games_played:
                    games.append({
                        'game_num': game_num,
                        'status': 'unnecessary',
                        'home': None,
                        'away': None,
                    })
                    continue

                if not high_code or not low_code:
                    games.append({
                        'game_num': game_num,
                        'status': 'upcoming',
                        'home': None,
                        'away': None,
                    })
                    continue

                sched = _sched_for(game_num)

                if fmt == 'single_game':
                    # Neutral-court single game; no home advantage.
                    pair_fwd = (matchup_probs.get(high_code) or {}).get(low_code) or {}
                    p_high = pair_fwd.get('neutral', pair_fwd.get('home', 0.5))
                    entry = {
                        'game_num': game_num,
                        'status': 'upcoming',
                        'home': None,
                        'away': None,
                        'neutral': True,
                        'pregame_wp': {
                            'high': round(p_high * 100, 1),
                            'low': round((1 - p_high) * 100, 1),
                        },
                    }
                    if sched:
                        entry.update({
                            'date': sched['date'],
                            'tipoff': sched['tipoff'],
                            'arena': sched['arena'],
                            'tipoff_confirmed': sched['confirmed'],
                        })
                    games.append(entry)
                    continue

                home_code, away_code = _schedule_home(game_num, high_code, low_code)
                home_prob_entry = (matchup_probs.get(home_code) or {}).get(away_code) or {}
                p_home = home_prob_entry.get('home', 0.5)
                entry = {
                    'game_num': game_num,
                    'status': 'upcoming',
                    'home': home_code,
                    'away': away_code,
                    'pregame_wp': {
                        'home': round(p_home * 100, 1),
                        'away': round((1 - p_home) * 100, 1),
                    },
                }
                if sched:
                    entry.update({
                        'date': sched['date'],
                        'tipoff': sched['tipoff'],
                        'arena': sched['arena'],
                        'tipoff_confirmed': sched['confirmed'],
                    })
                games.append(entry)

            return games

        result = {}
        for slot_id, defn in slot_defs.items():
            high, low = defn['seeds']
            high_code = high['team'] if high else None
            low_code = low['team'] if low else None

            wins_h, wins_l = 0, 0
            winner = None
            status = 'not_started'
            completed_games = []

            if slot_id.startswith('qf') and playoff_results:
                qf_label = qf_label_for_slot[slot_id]
                qf_entry = (playoff_results.get('qf') or {}).get(qf_label) or {}
                series = qf_entry.get('series') or [0, 0]
                wins_h, wins_l = series[0], series[1]
                winner = qf_entry.get('winner')
                completed_games = qf_entry.get('games') or []
            elif slot_id in ('sf1', 'sf2') and playoff_results:
                sf_entry = (playoff_results.get('sf') or {}).get(slot_id) or {}
                if sf_entry.get('winner'):
                    winner = sf_entry['winner']
                    if winner == high_code:
                        wins_h = 1
                    else:
                        wins_l = 1
                    completed_games = [sf_entry] if sf_entry else []
            elif slot_id == 'final' and playoff_results:
                final_entry = (playoff_results.get('final') or {}).get('game') or {}
                final_winner_code = (playoff_results.get('final') or {}).get('winner')
                if final_winner_code:
                    winner = final_winner_code
                    if winner == high_code:
                        wins_h = 1
                    else:
                        wins_l = 1
                    completed_games = [final_entry] if final_entry else []

            if winner:
                status = 'completed'
            elif wins_h > 0 or wins_l > 0:
                status = 'in_progress'
            elif not high_code or not low_code:
                status = 'awaiting_teams'

            fmt = 'best_of_5' if defn['round'] == 'qf' else 'single_game'
            home_pattern = ['high', 'high', 'low', 'low', 'high'] if fmt == 'best_of_5' else ['neutral']

            games = _build_games(completed_games, high_code, low_code, wins_h, wins_l, status, fmt)

            result[slot_id] = {
                'id': slot_id,
                'round': defn['round'],
                'label': defn['label'],
                'format': fmt,
                'home_pattern': home_pattern,
                'high_seed': high,
                'low_seed': low,
                'status': status,
                'wins': {'high': wins_h, 'low': wins_l},
                'winner': winner,
                'series_win_prob': _build_prob_pair(slot_id, high_code, low_code),
                'games': games,
                'rs_h2h': _rs_h2h(high_code, low_code),
            }
            result[slot_id]['momentum'] = build_momentum(
                result[slot_id], matchup_probs, teams_by_code,
            )
            result[slot_id]['tale_of_the_tape'] = build_tale_of_the_tape(
                high_code, low_code, teams_by_code,
                box_metrics, paint_share, result[slot_id]['rs_h2h'],
            )

        return result

    # ── Build output ─────────────────────────────────────────────────────────
    from datetime import datetime

    # ── Playoff tracking ─────────────────────────────────────────────────────
    playoff_results_data = None
    championship_odds = {}
    playoff_recaps = []
    championship_odds_history = []
    path_to_title = []
    series_win_probs = {}
    series_data = {}

    # Build RS games df for Series Hub H2H lookups.
    # Uses mvp_game_results.json (has both legs of each home/away pair);
    # data_cache/games_{S}.csv only tracks one leg per pair.
    games_df = None
    try:
        h2h_src = load_json('mvp_game_results.json') or []
        rows = []
        for g in h2h_src:
            code = int(g.get('GameCode', 0))
            if code < 1 or code > 380:  # Regular season gamecodes only
                continue
            ls = g.get('LocalScore', 0) or 0
            rs = g.get('RoadScore', 0) or 0
            rows.append({
                'round': 'RS',
                'gameday': (code - 1) // 10 + 1,
                'homecode': g.get('LocalTeam'),
                'awaycode': g.get('RoadTeam'),
                'homescore': int(ls),
                'awayscore': int(rs),
                'played': ls > 0 and rs > 0,
            })
        if rows:
            games_df = pd.DataFrame(rows)
    except Exception as e:
        print(f"  [WARN] Could not build RS games for Series Hub: {e}")

    # Build schedule index for Series Hub upcoming-game date/tip-off lookups.
    # Keyed by frozenset({home, away}) → list of schedule rows ordered by gameday.
    # Excludes RS and PI rounds; only QF/SF/Final pairings are kept.
    schedule_index = {}
    try:
        sched_rows = load_json(f'schedule_{S}.json') or []
        for row in sched_rows:
            rnd = row.get('round')
            if rnd in ('RS', 'PI') or not rnd:
                continue
            h = row.get('homecode')
            a = row.get('awaycode')
            if not h or not a:
                continue
            schedule_index.setdefault(frozenset({h, a}), []).append(row)
        for key in schedule_index:
            schedule_index[key].sort(key=lambda r: int(r.get('gameday') or 0))
    except Exception as e:
        print(f"  [WARN] Could not build schedule index for Series Hub: {e}")

    rs_complete = regular_season_complete(load_json(f'schedule_{S}.json'))
    game_results_raw = load_json('mvp_game_results.json')
    if game_results_raw and len(teams) >= 10:
        seeded = teams[:10]  # Already in official standings order
        playoff_results_data = build_playoff_results(game_results_raw, seeded)

        if playoff_results_data:
            # Compute current championship odds
            mc_result = compute_championship_odds(
                playoff_results_data, playoff_matchup_probs, seeded
            )
            championship_odds = mc_result['championship']
            series_win_probs = mc_result['series']

            # Load previous odds history from existing dashboard
            prev_dashboard_path = os.path.join('docs', 'data', 'current', 'dashboard.json')
            prev_odds = {}
            try:
                with open(prev_dashboard_path, 'r', encoding='utf-8') as f:
                    prev_data = json.load(f)
                championship_odds_history = (prev_data.get('championship_odds_history', [])
                                             if prev_data.get('season') == CURRENT_SEASON else [])
                # Previous odds = last entry in history, or empty
                if championship_odds_history:
                    prev_odds = championship_odds_history[-1].get('odds', {})
            except Exception:
                pass

            # Append today's snapshot (avoid duplicate dates)
            today_str = datetime.utcnow().strftime('%Y-%m-%d')
            # Remove any existing entry for today (re-run scenario)
            championship_odds_history = [
                h for h in championship_odds_history if h.get('date') != today_str
            ]
            championship_odds_history.append({
                'date': today_str,
                'label': _detect_playoff_label(playoff_results_data),
                'odds': championship_odds,
            })

            # Build recap cards
            playoff_recaps = build_playoff_recaps(
                playoff_results_data, prev_odds, championship_odds,
                playoff_matchup_probs, seeded
            )

            # Build path-to-title data
            path_to_title = compute_path_to_title(
                playoff_results_data, playoff_matchup_probs, seeded
            )

            # Align championship_odds with the 50k-sim source for display consistency
            for entry in path_to_title:
                entry['championship_odds'] = round(championship_odds.get(entry['team'], 0.0), 1)
            path_to_title.sort(key=lambda e: (
                0 if e['status'] != 'eliminated' else 1,
                -e['championship_odds'],
            ))

            # Build Series Hub data
            teams_by_code = {t['team']: t for t in teams}
            all_game_stats = load_json(f'mvp_all_game_stats_{S}.json') or []
            gamecode_to_teams = {
                int(r['GameCode']): (r['LocalTeam'], r['RoadTeam'])
                for r in (load_json('mvp_game_results.json') or [])
            }
            box_metrics = compute_team_box_metrics(all_game_stats, gamecode_to_teams)
            shot_stats_for_paint = load_json('docs/data/current/shot_stats.json') or {}
            paint_share = compute_team_paint_share(shot_stats_for_paint)
            series_data = compute_series_data(
                playoff_results_data, playoff_matchup_probs, seeded,
                series_win_probs, games_df, teams_by_code,
                box_metrics, paint_share, schedule_index=schedule_index,
            )

            print(f"  Playoff results: {sum(1 for g in game_results_raw if int(g.get('GameCode', 0)) > 380 and g.get('LocalScore', 0) > 0)} games tracked")
            print(f"  Championship odds computed for {len([v for v in championship_odds.values() if v > 0])} contending teams")
        else:
            # Pre-playoff: compute baseline odds if not done yet
            prev_dashboard_path = os.path.join('docs', 'data', 'current', 'dashboard.json')
            try:
                with open(prev_dashboard_path, 'r', encoding='utf-8') as f:
                    prev_data = json.load(f)
                championship_odds_history = (prev_data.get('championship_odds_history', [])
                                             if prev_data.get('season') == CURRENT_SEASON else [])
            except Exception:
                pass

            if not rs_complete:
                # Seeds aren't final: no championship odds, path to title or
                # series yet, and drop any stale mid-season "Pre-Playoff" baseline.
                championship_odds_history = []
                print("  Regular season in progress — playoff forecasts skipped "
                      "(bracket stays a what-if)")

            if rs_complete and playoff_matchup_probs and len(teams) >= 10:
                seeded = teams[:10]
                # Always run the MC sim pre-playoff so the Series Hub can show
                # current per-series win probabilities. Only seed the history
                # with a baseline entry on the very first run.
                mc_result = compute_championship_odds(
                    None, playoff_matchup_probs, seeded
                )
                championship_odds = mc_result['championship']
                series_win_probs = mc_result['series']
                if not championship_odds_history:
                    championship_odds_history = [{
                        'date': datetime.utcnow().strftime('%Y-%m-%d'),
                        'label': 'Pre-Playoff',
                        'odds': championship_odds,
                    }]
                path_to_title = compute_path_to_title(
                    None, playoff_matchup_probs, seeded
                )
                # Align championship_odds with the 50k-sim source for display consistency
                for entry in path_to_title:
                    entry['championship_odds'] = round(championship_odds.get(entry['team'], 0.0), 1)
                path_to_title.sort(key=lambda e: (
                    0 if e['status'] != 'eliminated' else 1,
                    -e['championship_odds'],
                ))
                teams_by_code = {t['team']: t for t in teams}
                all_game_stats = load_json(f'mvp_all_game_stats_{S}.json') or []
                gamecode_to_teams = {
                    int(r['GameCode']): (r['LocalTeam'], r['RoadTeam'])
                    for r in (load_json('mvp_game_results.json') or [])
                }
                box_metrics = compute_team_box_metrics(all_game_stats, gamecode_to_teams)
                shot_stats_for_paint = load_json('docs/data/current/shot_stats.json') or {}
                paint_share = compute_team_paint_share(shot_stats_for_paint)
                series_data = compute_series_data(
                    None, playoff_matchup_probs, seeded, series_win_probs, games_df,
                    teams_by_code,
                    box_metrics, paint_share, schedule_index=schedule_index,
                )

    output = {
        'round': round_num,
        'season': CURRENT_SEASON,
        'season_label': season_label(),
        'regular_season_complete': rs_complete,
        'updated': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'teams': teams,
        'mvp': mvp_list,
        'mvp_race': mvp_race,
        'player_stats': player_stats,
        'rapm': rapm_data,
        'wpa': wpa_data,
        'tpm': tpm_data,
        'wir': wir_data,
        'oracle': oracle_data,
        'accuracy': accuracy_data,
        'game_control': gci_data,
        'playoff_matchup_probs': playoff_matchup_probs,
        'playoff_results': playoff_results_data,
        'championship_odds': championship_odds,
        'championship_odds_history': championship_odds_history,
        'playoff_recaps': playoff_recaps,
        'path_to_title': path_to_title,
        'series': series_data,
        'playoff_player_stats': build_playoff_player_stats(),
        'championship_finals_history': compute_championship_finals_history(),
    }

    # ── Write output ─────────────────────────────────────────────────────────
    out_dir = os.path.join('docs', 'data', 'current')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'dashboard.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== Export Summary ===")
    print(f"  Output: {out_path}")
    print(f"  Round: {round_num}")
    print(f"  Teams: {len(teams)}")
    print(f"  MVP entries: {len(mvp_list)}")
    print(f"  WPA ratings: {len(wpa_data)} players")
    print(f"  TPM ratings: {len(tpm_data)} players")
    print(f"  WIR ratings: {len(wir_data)} players")
    if oracle_data:
        preds = oracle_data.get('predictions', [])
        print(f"  Oracle predictions: {len(preds)} (Round {oracle_data.get('round', '?')})")
        if player_forecasts:
            print(f"  Player forecasts: {len(player_forecasts)}")
    else:
        print("  Oracle: not available")
    if accuracy_data:
        print(f"  Accuracy: {accuracy_data.get('accuracy', '?')}% over {accuracy_data.get('n_games', '?')} games")
    print(f"\nDone! dashboard.json written to {out_path}")

    # ── Shot stats export ────────────────────────────────────────────────────
    shot_stats = build_shot_stats()
    if shot_stats:
        shot_path = os.path.join(out_dir, 'shot_stats.json')
        with open(shot_path, 'w', encoding='utf-8') as f:
            json.dump(shot_stats, f, ensure_ascii=False, indent=2)
        n_players = len(shot_stats.get('players', {}))
        n_teams = len(shot_stats.get('teams', {}))
        print(f"  Shot stats: {n_teams} teams, {n_players} players -> {shot_path}")

    # ── Paint profiles export ──────────────────────────────────────────────
    print("\n--- Building paint profiles ---")
    paint_profiles = build_paint_profiles()
    if paint_profiles:
        paint_path = os.path.join(out_dir, 'paint_profiles.json')
        with open(paint_path, 'w', encoding='utf-8') as f:
            json.dump(paint_profiles, f, ensure_ascii=False, indent=2)
        n_players = len(paint_profiles.get('players', []))
        n_teams = len(paint_profiles.get('teams', {}))
        n_def = len(paint_profiles.get('team_defense', {}))
        print(f"  Paint profiles: {n_players} players, {n_teams} teams, {n_def} team defense -> {paint_path}")

    # ── Assist network export ─────────────────────────────────────────────
    print("\n--- Building assist network ---")
    assist_network = build_assist_network()
    if assist_network:
        assist_path = os.path.join(out_dir, 'assist_network.json')
        with open(assist_path, 'w', encoding='utf-8') as f:
            json.dump(assist_network, f, ensure_ascii=False, indent=2)
        n_teams = len(assist_network.get('teams', {}))
        n_combos = len(assist_network.get('top_combos', []))
        print(f"  Assist network: {n_teams} teams, {n_combos} top combos -> {assist_path}")

    # ── Game recaps export ─────────────────────────────────────────────────
    print("\n--- Building game recaps ---")
    game_recaps = build_game_recaps()
    if game_recaps:
        recap_path = os.path.join(out_dir, 'game_recaps.json')
        with open(recap_path, 'w', encoding='utf-8') as f:
            json.dump(game_recaps, f, ensure_ascii=False)
        print(f"  Game recaps -> {recap_path}")

    # Copy backtest predictions for H2H page
    import shutil
    backtest_src = f'oracle_backtest_predictions.json'
    if os.path.exists(backtest_src):
        shutil.copy2(backtest_src, os.path.join(out_dir, 'oracle_backtest_predictions.json'))
        print(f"  Copied backtest predictions to {out_dir}")


if __name__ == '__main__':
    main()
