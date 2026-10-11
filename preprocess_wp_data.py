"""
Pre-process PBP CSVs into compact JSON for the GitHub Pages WP Replay dashboard.
Reads data_cache/pbp_{year}.csv files and outputs:
  docs/data/seasons.json         — List of available seasons
  docs/data/{year}/games.json    — Game index for each season
  docs/data/{year}/{gc}.json     — Scoring timeline for each game
"""

import pandas as pd
import numpy as np
import json
import os
import math
import glob
import argparse

from season_config import ALL_SEASONS, season_label

from wp_model_utils import get_elo_diff


def win_probability(margin, seconds_remaining, elo_diff=0.0, total_seconds=2400):
    """Delegates to ML model if available, otherwise analytic fallback."""
    from wp_model_utils import predict_wp
    return predict_wp(margin, seconds_remaining, elo_diff=elo_diff)


def parse_marker_time(marker_str, period):
    if pd.isna(marker_str):
        return None
    try:
        parts = str(marker_str).split(':')
        minutes = int(parts[0])
        seconds = int(parts[1])
        period_seconds_left = minutes * 60 + seconds
        if period <= 4:
            remaining_periods = 4 - period
            total_remaining = period_seconds_left + remaining_periods * 600
        else:
            total_remaining = period_seconds_left
        return total_remaining
    except (ValueError, IndexError):
        return None


def detect_team_a(game, teams):
    """Auto-detect which team maps to POINTS_A."""
    scoring = game[game['POINTS_A'].notna() & game['CODETEAM'].isin(teams)]
    prev_a, prev_b = 0, 0
    for _, row in scoring.iterrows():
        try:
            a, b = int(float(row['POINTS_A'])), int(float(row['POINTS_B']))
        except (ValueError, TypeError):
            continue
        team = row['CODETEAM']
        if a > prev_a and b == prev_b:
            return team
        elif b > prev_b and a == prev_a:
            return [t for t in teams if t != team][0]
        prev_a, prev_b = a, b
    return teams[0]


def process_game(game_df, teams, elo_diff=0.0):
    """Process a single game into a scoring timeline."""
    team_a = detect_team_a(game_df, teams)
    team_b = [t for t in teams if t != team_a][0]

    timeline = []
    last_a, last_b = 0, 0

    for _, row in game_df.iterrows():
        pts_a = row.get('POINTS_A')
        pts_b = row.get('POINTS_B')
        if pd.isna(pts_a) or pd.isna(pts_b):
            continue
        try:
            pts_a, pts_b = int(float(pts_a)), int(float(pts_b))
        except (ValueError, TypeError):
            continue
            
        if pts_a == last_a and pts_b == last_b:
            continue

        period = int(row['PERIOD']) if pd.notna(row['PERIOD']) else 1
        secs = parse_marker_time(row.get('MARKERTIME'), period)
        if secs is None:
            continue

        elapsed = 2400 - secs
        margin_a = pts_a - pts_b
        wp_a = win_probability(margin_a, secs, elo_diff=elo_diff)

        player = str(row.get('PLAYER', '')) if pd.notna(row.get('PLAYER')) else ''
        team = str(row.get('CODETEAM', '')) if pd.notna(row.get('CODETEAM')) else ''
        play_info = str(row.get('PLAYINFO', '')) if pd.notna(row.get('PLAYINFO')) else ''
        desc = f"{player} ({team})" + (f" — {play_info}" if play_info else "")

        timeline.append({
            'e': round(elapsed, 1),      # elapsed seconds
            's': secs,                     # seconds remaining
            'a': pts_a,                    # team A score
            'b': pts_b,                    # team B score
            'w': round(wp_a, 4),           # WP for team A
            'p': period,                   # period
            'd': desc,                     # play description
        })

        last_a, last_b = pts_a, pts_b

    # Sort by elapsed to prevent backward jumps
    timeline.sort(key=lambda x: x['e'])

    # Add final buzzer
    final_wp = 1.0 if last_a > last_b else (0.0 if last_a < last_b else 0.5)
    timeline.append({
        'e': 2400, 's': 0, 'a': last_a, 'b': last_b,
        'w': final_wp, 'p': 4, 'd': 'Final Buzzer',
    })

    return timeline, team_a, team_b, last_a, last_b


def extract_advanced_stats(game_df, team_a, team_b):
    stats = {}
    
    # Calculate Quarter Margins
    try:
        q_scores = game_df.groupby('PERIOD')[['POINTS_A', 'POINTS_B']].max().reset_index()
        q_scores['Q_PTS_A'] = q_scores['POINTS_A'].diff().fillna(q_scores['POINTS_A'])
        q_scores['Q_PTS_B'] = q_scores['POINTS_B'].diff().fillna(q_scores['POINTS_B'])
        
        q_margins = []
        for _, row in q_scores.iterrows():
            q_margins.append({
                'p': int(row['PERIOD']),
                'a': int(row['Q_PTS_A']),
                'b': int(row['Q_PTS_B'])
            })
        stats['q'] = q_margins
    except:
        stats['q'] = []
        
    # Player Impact
    try:
        player_events = game_df[pd.notna(game_df['PLAYER'])].copy()
        impacts = []
        if not player_events.empty:
            for player, pdf in player_events.groupby('PLAYER'):
                pts = (len(pdf[pdf['PLAYTYPE'] == '2FGM']) * 2 + 
                       len(pdf[pdf['PLAYTYPE'] == '3FGM']) * 3 + 
                       len(pdf[pdf['PLAYTYPE'] == 'FTM']) * 1)
                
                hustle = (len(pdf[pdf['PLAYTYPE'] == 'D']) + 
                          len(pdf[pdf['PLAYTYPE'] == 'O']) + 
                          len(pdf[pdf['PLAYTYPE'] == 'AS']) + 
                          len(pdf[pdf['PLAYTYPE'] == 'ST']))
                          
                if pts > 0 or hustle > 0:
                    team = pdf['CODETEAM'].iloc[0]
                    name_parts = str(player).split(',')
                    clean_name = name_parts[0].title() if len(name_parts) > 0 else str(player)
                    impacts.append({'n': clean_name, 'p': pts, 'h': hustle, 't': team})
        stats['i'] = impacts
    except:
        stats['i'] = []
        
    # Scoring Runs
    try:
        def parse_marker(m_str, p):
            if pd.isna(m_str): return None
            try:
                mins, secs = map(int, str(m_str).split(':'))
                ps_left = mins * 60 + secs
                return ps_left + (4 - p) * 600 if p <= 4 else ps_left
            except: return None
            
        runs = []
        curr_team = None
        curr_pts = 0
        run_start = None
        last_a, last_b = 0, 0
        
        for _, row in game_df.sort_values('NUMBEROFPLAY').iterrows():
            pa, pb = row.get('POINTS_A'), row.get('POINTS_B')
            if pd.isna(pa) or pd.isna(pb): continue
            try: pa, pb = int(float(pa)), int(float(pb))
            except: continue
            
            if pa == last_a and pb == last_b: continue
            period = int(row['PERIOD']) if pd.notna(row['PERIOD']) else 1
            sf = parse_marker(row.get('MARKERTIME'), period)
            if sf is None: continue
            elapsed = 2400 - sf
            
            scoring_team = team_a if pa > last_a else team_b
            pts = (pa - last_a) if pa > last_a else (pb - last_b)
            
            if curr_team == scoring_team:
                curr_pts += pts
            else:
                if curr_pts >= 8:
                    runs.append({'t': curr_team, 'p': curr_pts, 'st': run_start, 'en': elapsed})
                curr_team = scoring_team
                curr_pts = pts
                run_start = elapsed
            last_a, last_b = pa, pb
            
        if curr_pts >= 8:
            runs.append({'t': curr_team, 'p': curr_pts, 'st': run_start, 'en': 2400})
            
        stats['r'] = runs
    except:
        stats['r'] = []
        
    # Four Factors
    try:
        ff_stats = {
            team_a: {'2FGM': 0, '2FGA': 0, '3FGM': 0, '3FGA': 0, 'FTA': 0, 'TO': 0, 'ORB': 0, 'DRB': 0},
            team_b: {'2FGM': 0, '2FGA': 0, '3FGM': 0, '3FGA': 0, 'FTA': 0, 'TO': 0, 'ORB': 0, 'DRB': 0}
        }
        for _, row in game_df.iterrows():
            team, ptype = row.get('CODETEAM'), row.get('PLAYTYPE')
            if team not in ff_stats: continue
            if ptype == '2FGM': ff_stats[team]['2FGM'] += 1; ff_stats[team]['2FGA'] += 1
            elif ptype == '2FGA': ff_stats[team]['2FGA'] += 1
            elif ptype == '3FGM': ff_stats[team]['3FGM'] += 1; ff_stats[team]['3FGA'] += 1
            elif ptype == '3FGA': ff_stats[team]['3FGA'] += 1
            elif ptype == 'FTA' or ptype == 'FTM': ff_stats[team]['FTA'] += 1
            elif ptype == 'TO': ff_stats[team]['TO'] += 1
            elif ptype == 'O': ff_stats[team]['ORB'] += 1
            elif ptype == 'D': ff_stats[team]['DRB'] += 1
            
        factors = []
        for team in [team_a, team_b]:
            s = ff_stats[team]
            opp_s = ff_stats[team_b if team == team_a else team_a]
            FGA = s['2FGA'] + s['3FGA']
            efg = round(((s['2FGM'] + 1.5 * s['3FGM']) / FGA) * 100, 1) if FGA > 0 else 0
            possessions = FGA + 0.44 * s['FTA'] + s['TO']
            tov = round((s['TO'] / possessions) * 100, 1) if possessions > 0 else 0
            orb_opp = s['ORB'] + opp_s['DRB']
            orb = round((s['ORB'] / orb_opp) * 100, 1) if orb_opp > 0 else 0
            ftr = round((s['FTA'] / FGA) * 100, 1) if FGA > 0 else 0
            factors.append({'t': team, 'eFG': efg, 'TOV': tov, 'ORB': orb, 'FTR': ftr})
        stats['f'] = factors
    except:
        stats['f'] = []

    # Top Lineups
    try:
        def get_cont_time(period, clock):
            if pd.isna(clock) or pd.isna(period): return 0.0
            try:
                m, s = map(int, str(clock).split(':'))
                minutes_remaining = m + s/60.0
                period = int(period)
                if period <= 4: return (period - 1) * 10.0 + (10.0 - minutes_remaining)
                else: return 40.0 + (period - 5) * 5.0 + (5.0 - minutes_remaining)
            except: return 0.0

        game_df['GameTimeMinute'] = game_df.apply(lambda row: get_cont_time(row['PERIOD'], row['MARKERTIME']), axis=1)
        active_lineups = {team_a: set(), team_b: set()}
        curr_a = {'l': frozenset(), 'st': 0.0, 'pf': 0, 'pa': 0}
        curr_b = {'l': frozenset(), 'st': 0.0, 'pf': 0, 'pa': 0}
        stints = []
        pra, prb = 0, 0
        
        for i in range(len(game_df)):
            row = game_df.iloc[i]
            time, ptype, team = row['GameTimeMinute'], row['PLAYTYPE'], row['CODETEAM']
            pa, pb = row.get('POINTS_A'), row.get('POINTS_B')
            try: pa, pb = int(float(pa)), int(float(pb))
            except: pa, pb = pra, prb
            
            p = str(row['PLAYER']) if pd.notna(row['PLAYER']) else None
            if p and ptype in ['IN', 'OUT']:
                clean = p.split(',')[0].title() if ',' in p else p
                if team == team_a:
                    stints.append({'t': team_a, 'l': frozenset(active_lineups[team_a]), 'd': time - curr_a['st'], 'pf': pa - curr_a['pf'], 'pa': pb - curr_a['pa']})
                    if ptype == 'IN': active_lineups[team_a].add(clean)
                    elif clean in active_lineups[team_a]: active_lineups[team_a].remove(clean)
                    curr_a = {'l': frozenset(active_lineups[team_a]), 'st': time, 'pf': pa, 'pa': pb}
                elif team == team_b:
                    stints.append({'t': team_b, 'l': frozenset(active_lineups[team_b]), 'd': time - curr_b['st'], 'pf': pb - curr_b['pf'], 'pa': pa - curr_b['pa']})
                    if ptype == 'IN': active_lineups[team_b].add(clean)
                    elif clean in active_lineups[team_b]: active_lineups[team_b].remove(clean)
                    curr_b = {'l': frozenset(active_lineups[team_b]), 'st': time, 'pf': pb, 'pa': pa}
            pra, prb = pa, pb

        final_time = game_df['GameTimeMinute'].iloc[-1] if not game_df.empty else 40.0
        stints.append({'t': team_a, 'l': curr_a['l'], 'd': final_time - curr_a['st'], 'pf': pra - curr_a['pf'], 'pa': prb - curr_a['pa']})
        stints.append({'t': team_b, 'l': curr_b['l'], 'd': final_time - curr_b['st'], 'pf': prb - curr_b['pf'], 'pa': pra - curr_b['pa']})
        
        sdf = pd.DataFrame(stints)
        sdf = sdf[sdf['l'].apply(len) == 5].copy()
        if not sdf.empty:
            sdf['l_str'] = sdf['l'].apply(lambda x: ' + '.join(sorted(list(x))))
            agg = sdf.groupby(['t', 'l_str']).agg({'d': 'sum', 'pf': 'sum', 'pa': 'sum'}).reset_index()
            agg['net'] = agg['pf'] - agg['pa']
            agg = agg[agg['d'] >= 1.5]
            
            top_lu = []
            for t in [team_a, team_b]:
                t_agg = agg[agg['t'] == t].sort_values('net', ascending=False)
                for _, r in t_agg.head(2).iterrows():
                    top_lu.append({'t': r['t'], 'l': r['l_str'], 'd': round(r['d'], 1), 'n': int(r['net'])})
                bot = t_agg.tail(1)
                if not bot.empty and bot.iloc[0]['net'] < 0:
                    top_lu.append({'t': bot.iloc[0]['t'], 'l': bot.iloc[0]['l_str'], 'd': round(bot.iloc[0]['d'], 1), 'n': int(bot.iloc[0]['net'])})
            stats['l'] = top_lu
        else: stats['l'] = []
    except:
        stats['l'] = []

    # Box Score
    try:
        box = {}
        for _, row in game_df.iterrows():
            team = row.get('CODETEAM')
            ptype = row.get('PLAYTYPE')
            p = str(row.get('PLAYER', '')) if pd.notna(row.get('PLAYER')) else None
            if not p or team not in [team_a, team_b]: continue
            clean = p.split(',')[0].title() if ',' in p else p
            key = (team, clean)
            if key not in box:
                box[key] = {'t': team, 'n': clean, 'pts': 0, 'reb': 0, 'ast': 0, 'stl': 0, 'blk': 0, 'to': 0,
                            'fgm': 0, 'fga': 0, 'fg3m': 0, 'fg3a': 0, 'ftm': 0, 'fta': 0}
            s = box[key]
            if ptype == '2FGM': s['pts'] += 2; s['fgm'] += 1; s['fga'] += 1
            elif ptype == '2FGA': s['fga'] += 1
            elif ptype == '3FGM': s['pts'] += 3; s['fgm'] += 1; s['fga'] += 1; s['fg3m'] += 1; s['fg3a'] += 1
            elif ptype == '3FGA': s['fg3a'] += 1; s['fga'] += 1
            elif ptype == 'FTM': s['pts'] += 1; s['ftm'] += 1; s['fta'] += 1
            elif ptype == 'FTA': s['fta'] += 1
            elif ptype == 'D': s['reb'] += 1
            elif ptype == 'O': s['reb'] += 1
            elif ptype == 'AS': s['ast'] += 1
            elif ptype == 'ST': s['stl'] += 1
            elif ptype == 'FV': s['blk'] += 1
            elif ptype == 'TO': s['to'] += 1
        stats['b'] = sorted(box.values(), key=lambda x: (x['t'] != team_a, -x['pts']))
    except:
        stats['b'] = []
        
    return stats


def extract_shot_data(year, gamecode, team_a, team_b):
    try:
        shot_path = f'data/shot_data_{year}_{year}.csv'
        if not os.path.exists(shot_path): return []
        shots_df = pd.read_csv(shot_path, low_memory=False)
        shots_df = shots_df[shots_df['Gamecode'] == gamecode]
        if shots_df.empty: return []
        
        shots_df = shots_df[shots_df['ID_ACTION'].str.contains('2FG|3FG', na=False)].copy()
        shots_df['COORD_X'] = pd.to_numeric(shots_df['COORD_X'], errors='coerce')
        shots_df['COORD_Y'] = pd.to_numeric(shots_df['COORD_Y'], errors='coerce')
        shots_df = shots_df.dropna(subset=['COORD_X', 'COORD_Y'])
        shots_df['MADE'] = shots_df['ID_ACTION'].str.contains('2FGM|3FGM', na=False).astype(int)
        
        shots_list = []
        for _, r in shots_df.iterrows():
            t = r['TEAM']
            if t not in [team_a, team_b]: continue
            p = str(r.get('PLAYER', ''))
            clean = p.split(',')[0].title() if ',' in p else p
            shots_list.append({
                't': t,
                'n': clean,
                'x': float(r['COORD_X']),
                'y': float(r['COORD_Y']),
                'm': int(r['MADE']),
                'q': int(r.get('PERIOD', 1)),
                'clk': str(r.get('MARKERTIME', ''))
            })
        return shots_list
    except Exception as e:
        print(f'      [Shot Parsing Error]: {e}')
        return []


def process_season(year):
    """Process one season's PBP data."""
    csv_path = f'data_cache/pbp_{year}.csv'
    if not os.path.exists(csv_path):
        print(f"  [SKIP] {csv_path} not found")
        return None

    print(f"  Processing season {year}-{str(year+1)[-2:]}...")
    df = pd.read_csv(csv_path, low_memory=False)

    # Get unique gamecodes
    gamecodes = sorted(df['Gamecode'].unique())
    games_index = []
    out_dir = f'docs/data/{year}'
    os.makedirs(out_dir, exist_ok=True)

    for gc in gamecodes:
        game = df[df['Gamecode'] == gc].sort_values('NUMBEROFPLAY')
        teams = [t for t in game['CODETEAM'].dropna().unique() if t and str(t).strip()]
        if len(teams) < 2:
            continue

        try:
            elo_diff = get_elo_diff(year, gc)
            timeline, team_a, team_b, score_a, score_b = process_game(game, teams, elo_diff=elo_diff)
            adv = extract_advanced_stats(game, team_a, team_b)
            shots = extract_shot_data(year, gc, team_a, team_b)
            if shots: adv['s'] = shots
            
            
            # Extract Round
            round_val = game['Round'].dropna().iloc[0] if not game['Round'].dropna().empty else "Unknown"
            
            # Extract Full Team Names
            ta_name = game[game['CODETEAM'] == team_a]['TEAM'].dropna().iloc[0] if not game[game['CODETEAM'] == team_a]['TEAM'].dropna().empty else team_a
            tb_name = game[game['CODETEAM'] == team_b]['TEAM'].dropna().iloc[0] if not game[game['CODETEAM'] == team_b]['TEAM'].dropna().empty else team_b

        except Exception as e:
            print(f"    Error on gamecode {gc}: {e}")
            continue

        if len(timeline) < 5:
            continue

        # Save game timeline
        game_file = os.path.join(out_dir, f'{gc}.json')
        with open(game_file, 'w') as f:
            json.dump({'ta': team_a, 'tb': team_b, 'timeline': timeline, 'adv': adv}, f,
                     separators=(',', ':'))

        games_index.append({
            'gc': int(gc),
            'rnd': int(round_val) if str(round_val).isdigit() else str(round_val),
            'ta': team_a,
            'ta_name': str(ta_name),
            'tb': team_b,
            'tb_name': str(tb_name),
            'sa': int(score_a),
            'sb': int(score_b),
        })

    # Save games index
    index_file = os.path.join(out_dir, 'games.json')
    with open(index_file, 'w') as f:
        json.dump(games_index, f, separators=(',', ':'))

    print(f"    Processed {len(games_index)} games for {year}")
    return {'season': year, 'label': season_label(year), 'count': len(games_index)}


def existing_season_meta(year, data_root='docs/data'):
    """seasons.json entry for a season that was not reprocessed this run."""
    index_file = os.path.join(data_root, str(year), 'games.json')
    if not os.path.exists(index_file):
        return None
    with open(index_file) as f:
        count = len(json.load(f))
    return {'season': year, 'label': season_label(year), 'count': count}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Build WP replay JSON from data_cache/pbp_{year}.csv')
    parser.add_argument('--seasons', type=int, nargs='+', default=None,
                        help='Seasons to (re)process (default: every season). '
                             'seasons.json always lists every season with replay data.')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    targets = set(args.seasons) if args.seasons else set(ALL_SEASONS)
    os.makedirs('docs/data', exist_ok=True)
    seasons_meta = []

    for year in sorted(set(ALL_SEASONS) | targets):
        result = process_season(year) if year in targets else None
        if result is None:
            result = existing_season_meta(year)
        if result:
            seasons_meta.append(result)

    # Save seasons index
    with open('docs/data/seasons.json', 'w') as f:
        json.dump(seasons_meta, f, indent=2)

    print(f"\nDone! Processed {len(targets)} season(s); seasons.json lists {len(seasons_meta)}.")
    print(f"Total games: {sum(s['count'] for s in seasons_meta)}")


if __name__ == '__main__':
    main()
