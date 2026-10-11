from season_config import CURRENT_SEASON
import pandas as pd
import matplotlib.pyplot as plt
import argparse
import sys
import json
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import matplotlib.image as mpimg
from PIL import Image
import os

from wp_model_utils import predict_wp
from predict_round_mvp import predict_round_mvp, print_mvp_leaderboard
from predict_player_performance import predict_round as predict_player_round, print_leaderboard as print_player_leaderboard

def run_oracle(target_round=None):
    # 1. Load Data
    try:
        df = pd.read_json('mvp_game_results.json')
    except Exception as e:
        print(f"Error loading mvp_game_results.json: {e}")
        return

    # 2. Determine HCA (Home Court Advantage)
    # Filter for played games only
    played = df[(df['LocalScore'] > 0) & (df['RoadScore'] > 0)].copy()
    
    if played.empty:
        print("No played games found. Cannot calculate stats.")
        return
        
    avg_local = played['LocalScore'].mean()
    avg_road = played['RoadScore'].mean()
    hca = avg_local - avg_road
    print(f"Global Home Court Advantage (HCA): +{hca:.1f} pts")

    # 3. Calculate Team Ratings (ORTG/DRTG) with Home/Away Splits
    teams = {}
    
    for _, row in played.iterrows():
        local = row['LocalTeam']
        road = row['RoadTeam']
        l_pts = row['LocalScore']
        r_pts = row['RoadScore']
        
        if local not in teams: teams[local] = {
            'PTS': 0, 'PA': 0, 'GP': 0,
            'HomePTS': 0, 'HomePA': 0, 'HomeGP': 0,
            'AwayPTS': 0, 'AwayPA': 0, 'AwayGP': 0,
            'GameMargins': []
        }
        if road not in teams: teams[road] = {
            'PTS': 0, 'PA': 0, 'GP': 0,
            'HomePTS': 0, 'HomePA': 0, 'HomeGP': 0,
            'AwayPTS': 0, 'AwayPA': 0, 'AwayGP': 0,
            'GameMargins': []
        }
        
        teams[local]['PTS'] += l_pts
        teams[local]['PA'] += r_pts
        teams[local]['GP'] += 1
        teams[local]['HomePTS'] += l_pts
        teams[local]['HomePA'] += r_pts
        teams[local]['HomeGP'] += 1
        teams[local]['GameMargins'].append(l_pts - r_pts)
        
        teams[road]['PTS'] += r_pts
        teams[road]['PA'] += l_pts
        teams[road]['GP'] += 1
        teams[road]['AwayPTS'] += r_pts
        teams[road]['AwayPA'] += l_pts
        teams[road]['AwayGP'] += 1
        teams[road]['GameMargins'].append(r_pts - l_pts)
        
    team_names = {
        'OLY': 'Olympiacos', 'ULK': 'Fenerbahce', 'PAN': 'Panathinaikos',
        'MAD': 'Real Madrid', 'BAR': 'Barcelona', 'MCO': 'Monaco',
        'ZAL': 'Zalgiris', 'DUB': 'Dubai BC', 'IST': 'Anadolu Efes',
        'HTA': 'Hapoel Tel Aviv', 'PAR': 'Partizan', 'RED': 'Crvena Zvezda',
        'TEL': 'Maccabi', 'BAS': 'Baskonia', 'MUN': 'Bayern',
        'BES': 'Besiktas',
        'VIR': 'Virtus Bologna', 'PAM': 'Valencia', 'ASV': 'ASVEL',
        'PRS': 'Paris Basketball', 'BER': 'ALBA Berlin',
        'MIL': 'EA7 Milan'
    }

    team_stats = {}
    for t, s in teams.items():
        if s['GP'] > 0:
            home_net = (s['HomePTS'] - s['HomePA']) / s['HomeGP'] if s['HomeGP'] > 0 else 0
            away_net = (s['AwayPTS'] - s['AwayPA']) / s['AwayGP'] if s['AwayGP'] > 0 else 0
            form_margins = s['GameMargins'][-5:] if len(s['GameMargins']) >= 5 else s['GameMargins']
            form = sum(form_margins) / len(form_margins) if form_margins else 0
            team_stats[t] = {
                'ORTG': s['PTS'] / s['GP'],
                'DRTG': s['PA'] / s['GP'],
                'Net': (s['PTS'] - s['PA']) / s['GP'],
                'HomeNet': home_net,
                'AwayNet': away_net,
                'Form': form
            }
        else:
             team_stats[t] = {'ORTG': 80, 'DRTG': 80, 'Net': 0, 'HomeNet': 0, 'AwayNet': 0, 'Form': 0}

    # 3.1 Load KenPom Adjusted Net Ratings
    adj_net_lookup = {}
    sos_lookup = {}
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'adjusted_ratings{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'adjusted_ratings.json'
    if os.path.exists(in_file):
        with open(in_file, 'r') as f:
            adj_data = json.load(f)
        for entry in adj_data:
            adj_net_lookup[entry['Team']] = entry['Adj_Net']
            sos_lookup[entry['Team']] = entry.get('SOS_WinPct', 0.5)
        print(f"Loaded KenPom Adjusted Net Ratings for {len(adj_net_lookup)} teams.")
    else:
        print("Warning: adjusted_ratings.json not found. Falling back to raw ratings.")

    # 3.2 Load Rolling Elo Ratings
    elo_lookup = {}
    if os.path.exists('elo_ratings.json'):
        with open('elo_ratings.json', 'r') as f:
            elo_data = json.load(f)
        for entry in elo_data:
            elo_lookup[entry['Team']] = entry['Elo']
        print(f"Loaded Elo Ratings for {len(elo_lookup)} teams.")
    else:
        print("Warning: elo_ratings.json not found. Elo factor disabled.")

    # 3.3 Load WPA ratings for per-team key player context
    wpa_lookup = {}  # team -> {'player': str, 'wpa': float}
    wpa_file = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    wpa_file = f'wpa_ratings{wpa_file}.json'
    if not os.path.exists(wpa_file):
        wpa_file = 'wpa_ratings.json'
    if os.path.exists(wpa_file):
        with open(wpa_file, 'r') as f:
            wpa_data = json.load(f)
        # Keep only the top WPA player per team
        seen = set()
        for entry in sorted(wpa_data, key=lambda x: x.get('Action_WPA', 0), reverse=True):
            team = entry.get('Team')
            if team and team not in seen:
                wpa_lookup[team] = {
                    'player': entry.get('Player', ''),
                    'wpa': entry.get('Action_WPA', 0.0),
                }
                seen.add(team)
        print(f"Loaded WPA ratings for {len(wpa_lookup)} teams.")

    # 3.5 Calculate League Rankings
    # Sort by ORTG (Desc) and DRTG (Asc)
    sorted_ortg = sorted(team_stats.items(), key=lambda x: x[1]['ORTG'], reverse=True)
    sorted_drtg = sorted(team_stats.items(), key=lambda x: x[1]['DRTG']) # Lower is better
    
    # Create Rank Maps
    ortg_rank = {team: i+1 for i, (team, _) in enumerate(sorted_ortg)}
    drtg_rank = {team: i+1 for i, (team, _) in enumerate(sorted_drtg)}
    
    total_teams = len(team_stats)

    # 3.6 Calculate Form and Venue Stats
    team_form = {t: {'Streak': 0, 'Last5': [], 'HomeW': 0, 'HomeG': 0, 'RoadW': 0, 'RoadG': 0} for t in team_stats}
    
    # Re-iterate games in chronological order to build form
    # Sort by GameCode just in case
    df_sorted = df.sort_values('GameCode')
    
    for _, row in df_sorted.iterrows():
        if row['LocalScore'] == 0: continue # Skip unplayed
        
        local = row['LocalTeam']
        road = row['RoadTeam']
        l_pts = row['LocalScore']
        r_pts = row['RoadScore']
        
        l_win = l_pts > r_pts
        r_win = r_pts > l_pts # Tie unlikely but possible in agg? No, single game.
        
        # Update Local
        if local in team_form:
            team_form[local]['HomeG'] += 1
            if l_win: 
                team_form[local]['HomeW'] += 1
                if team_form[local]['Streak'] > 0: team_form[local]['Streak'] += 1
                else: team_form[local]['Streak'] = 1
                team_form[local]['Last5'].append('W')
            else:
                if team_form[local]['Streak'] < 0: team_form[local]['Streak'] -= 1
                else: team_form[local]['Streak'] = -1
                team_form[local]['Last5'].append('L')
            if len(team_form[local]['Last5']) > 5: team_form[local]['Last5'].pop(0)

        # Update Road
        if road in team_form:
            team_form[road]['RoadG'] += 1
            if r_win:
                team_form[road]['RoadW'] += 1
                if team_form[road]['Streak'] > 0: team_form[road]['Streak'] += 1
                else: team_form[road]['Streak'] = 1
                team_form[road]['Last5'].append('W')
            else:
                if team_form[road]['Streak'] < 0: team_form[road]['Streak'] -= 1
                else: team_form[road]['Streak'] = -1
                team_form[road]['Last5'].append('L')
            if len(team_form[road]['Last5']) > 5: team_form[road]['Last5'].pop(0)

    # 4. Identify Target Round
    # 20 teams → 10 games per round, 38 rounds
    games_per_round = 10  # 20 teams / 2
    
    if target_round is None:
        # Derive from standings: next round = max games played + 1
        # This is robust against postponed games having score 0
        try:
            with open('mvp_standings_derived.json', 'r') as f:
                standings_data = json.load(f)
            gp_values = [t.get('GP', 0) for t in standings_data.values() if t.get('GP', 0) > 0]
            # Use mode (most common GP) to avoid makeup games skewing the round detection
            from collections import Counter
            current_round = Counter(gp_values).most_common(1)[0][0] if gp_values else 0
            target_round = current_round + 1
            print(f"Auto-detected next round from standings: Round {target_round} (modal GP: {current_round}, max GP: {max(gp_values)})")
        except Exception as e:
            print(f"Warning: Could not read standings for round detection: {e}")
            target_round = 38
            
    # Try to load schedule from official XML first (most reliable for unplayed rounds)
    import xml.etree.ElementTree as ET
    
    from team_aliases import NAME_TO_CODE as name_to_code
    
    round_games = pd.DataFrame()
    
    # Strategy 1: Official XML schedule
    xml_path = f'official_schedule_{CURRENT_SEASON}.xml'
    if os.path.exists(xml_path):
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            xml_items = [i for i in root.findall('item') if i.find('gameday').text == str(target_round)]
            
            if xml_items:
                xml_games = []
                for item in xml_items:
                    home_name = item.find('hometeam').text
                    away_name = item.find('awayteam').text
                    home_code = name_to_code.get(home_name, 'UNK')
                    away_code = name_to_code.get(away_name, 'UNK')
                    
                    if home_code == 'UNK':
                        print(f"Warning: Unmapped team name '{home_name}'")
                    if away_code == 'UNK':
                        print(f"Warning: Unmapped team name '{away_name}'")
                    
                    xml_games.append({
                        'LocalTeam': home_code,
                        'RoadTeam': away_code,
                        'LocalScore': 0,
                        'RoadScore': 0
                    })
                
                round_games = pd.DataFrame(xml_games)
                print(f"Loaded {len(round_games)} games from official XML schedule")
        except Exception as e:
            print(f"Warning: Could not parse XML schedule: {e}")
    
    # Strategy 2: Manual JSON schedule
    if round_games.empty:
        manual_file = f'manual_round_{target_round}.json'
        if os.path.exists(manual_file):
            print(f"Loading manual schedule from {manual_file}...")
            try:
                round_games = pd.read_json(manual_file)
            except Exception as e:
                print(f"Error loading manual schedule: {e}")
    
    # Strategy 3: Game-code based lookup from results (works for already-played rounds)
    if round_games.empty:
        offset = 0
        start_gc = (target_round - 1) * games_per_round + 1 + offset
        end_gc = target_round * games_per_round + offset
        round_games = df[(df['GameCode'] >= start_gc) & (df['GameCode'] <= end_gc)].copy()

    # Drop already-played games and UNKNOWN placeholders. Oracle is a
    # regular-season-game forecaster; once the season ends, the next-round
    # slot is filled with played play-ins and dummy rows, neither of which
    # should be predicted.
    if not round_games.empty:
        round_games = round_games[
            (round_games['LocalScore'] == 0)
            & (round_games['RoadScore'] == 0)
            & (round_games['LocalTeam'] != 'UNKNOWN')
            & (round_games['RoadTeam'] != 'UNKNOWN')
        ].copy()

    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    json_out = f"oracle_forecast_round_{target_round}{round_suffix}.json"

    if round_games.empty:
        print(f"No upcoming games for Round {target_round} — writing empty forecast.")
        with open(json_out, 'w') as f:
            json.dump({
                'round': target_round,
                'predictions': [],
                'mvp_candidates': [],
                'player_forecasts': [],
            }, f, indent=2)
        print(f"Empty forecast saved to {json_out}")
        return

    print(f"Predicting {len(round_games)} games for Round {target_round}...")
    
    # Load Advanced Stats (optional, for X-Factor insights)
    adv_stats = {}
    try:
        with open('team_advanced_stats.json', 'r') as f:
            adv_stats = json.load(f)
    except:
        pass
    
    # 5. Predict Matches using 3-Factor Model
    predictions = []
    
    for _, row in round_games.iterrows():
        local = row['LocalTeam']
        road = row['RoadTeam']
        
        local_name = team_names.get(local, local)
        road_name = team_names.get(road, road)

        l_stat = team_stats.get(local, {'ORTG': 80, 'DRTG': 80, 'Net': 0, 'HomeNet': 0, 'AwayNet': 0, 'Form': 0})
        r_stat = team_stats.get(road, {'ORTG': 80, 'DRTG': 80, 'Net': 0, 'HomeNet': 0, 'AwayNet': 0, 'Form': 0})
        
        l_form = team_form.get(local, {'Streak': 0, 'HomeW': 0, 'HomeG': 1, 'Last5': [], 'RoadW': 0, 'RoadG': 1})
        r_form = team_form.get(road, {'Streak': 0, 'RoadW': 0, 'RoadG': 1, 'Last5': [], 'HomeW': 0, 'HomeG': 1})
        
        # Rankings
        l_o_rank = ortg_rank.get(local, 99)
        l_d_rank = drtg_rank.get(local, 99)
        r_o_rank = ortg_rank.get(road, 99)
        r_d_rank = drtg_rank.get(road, 99)
        
        l_home_pct = (l_form['HomeW'] / l_form['HomeG']) * 100 if l_form['HomeG'] > 0 else 0
        r_road_pct = (r_form['RoadW'] / r_form['RoadG']) * 100 if r_form['RoadG'] > 0 else 0
        
        # === OPTIMIZED PREDICTION MODEL ===
        # 25% Elo + 75% Adj Net + per-team HCA (optimized via incremental backtest)
        # Elo tracks real-time team quality; Adj Net corrects for opponent quality
        
        # Factor 1: KenPom Adjusted Net Rating (75%)
        l_adj = adj_net_lookup.get(local, l_stat['Net'])
        r_adj = adj_net_lookup.get(road, r_stat['Net'])
        
        # Factor 2: Rolling Elo Rating (25%) — converted to points scale
        l_elo = elo_lookup.get(local, 1500)
        r_elo = elo_lookup.get(road, 1500)
        elo_margin = (l_elo - r_elo + 50) / 25  # +50 for Elo HCA, /25 to convert to pts
        
        # Blended prediction: 75% Adj Net diff + 25% Elo margin
        adj_diff = l_adj - r_adj
        margin_raw = (adj_diff * 0.75) + (elo_margin * 0.25)
        
        # Per-team HCA: blend global HCA with team-specific home boost
        l_net_overall = l_stat['Net']
        team_hca = l_stat['HomeNet'] - l_net_overall
        hca_alpha = 0.3  # 30% team-specific, 70% global
        blended_hca = (hca * (1 - hca_alpha) + team_hca * hca_alpha) * 0.5
        
        margin = margin_raw + blended_hca
        
        # Win probability: feed the blended predicted margin into the ML model
        # (full time remaining = pre-game). Winner and confidence are derived
        # from the same signal so they are always consistent.
        home_win_prob = predict_wp(
            margin=margin,
            seconds_remaining=2400,
            elo_diff=l_elo - r_elo,
            is_home=True,
        ) * 100
        winner = local if home_win_prob >= 50 else road
        win_prob = home_win_prob if winner == local else 100 - home_win_prob
        
        # === X-FACTOR INSIGHTS ===
        # Now data-driven with SOS context
        insight = ""
        l_sos = sos_lookup.get(local, 0.5)
        r_sos = sos_lookup.get(road, 0.5)
        
        # 1. Hot Streaks (>=5)
        if l_form['Streak'] >= 5: insight = f"🔥 {local_name} Won {l_form['Streak']} Straight"
        elif r_form['Streak'] >= 5: insight = f"🔥 {road_name} Won {r_form['Streak']} Straight"
        elif l_form['Streak'] <= -5: insight = f"❄️ {local_name} Lost {abs(l_form['Streak'])} Straight"
        elif r_form['Streak'] <= -5: insight = f"❄️ {road_name} Lost {abs(r_form['Streak'])} Straight"
        
        # 2. Venue Fortress (>85% Home)
        elif l_home_pct >= 85:
             insight = f"🏟️ FORTRESS: {local_name} {l_home_pct:.0f}% at Home"
             
        # 3. Road Warriors (>55% Road)
        elif r_road_pct >= 55:
             insight = f"✈️ {road_name} {r_road_pct:.0f}% Away Win Rate"
        
        # 4. SOS mismatch (one team's SOS >> other's)
        elif abs(l_sos - r_sos) > 0.08:
            harder = local_name if l_sos > r_sos else road_name
            insight = f"📊 {harder} has faced tougher schedule"
        
        # 5. Rank Clash
        elif l_o_rank <= 4 and r_d_rank <= 4:
             insight = f"⚔️ Top 4 Offense vs Top 4 Defense"
             
        # Default: Adj Net gap
        else:
            gap = abs(l_adj - r_adj)
            if gap > 5:
                stronger = local_name if l_adj > r_adj else road_name
                insight = f"📈 {stronger} +{gap:.1f} Adj Net advantage"
            else:
                insight = f"⚖️ Evenly matched (Adj Net gap: {gap:.1f})"
        
        # Build insight block
        line2 = f"Adj Net: {l_adj:+.1f} v {r_adj:+.1f}  |  Elo: {l_elo:.0f} v {r_elo:.0f}"
        
        l_l5 = l_form.get('Last5', [])
        r_l5 = r_form.get('Last5', [])
        l_l5_w = l_l5.count('W')
        r_l5_w = r_l5.count('W')
        
        line3 = f"L5: {l_l5_w}-{(5-l_l5_w)} v {r_l5_w}-{(5-r_l5_w)}  |  H: {l_form['HomeW']}-{l_form['HomeG']-l_form['HomeW']} v A: {r_form.get('RoadW',0)}-{r_form.get('RoadG',0)-r_form.get('RoadW',0)}"

        # WPA key player per team — last name only, no value (cumulative total is not card-friendly)
        def _last_name(full):
            # Names stored as "SURNAME, FIRST" or "SURNAME FIRST"
            return full.split(',')[0].strip().title()

        wpa_parts = []
        for code, label in [(local, 'H'), (road, 'A')]:
            entry = wpa_lookup.get(code)
            if entry:
                wpa_parts.append(f"{label}: {_last_name(entry['player'])}")
        line4 = "Key players — " + "  |  ".join(wpa_parts) if wpa_parts else ""

        final_insight = f"{insight}\n{line2}\n{line3}" + (f"\n{line4}" if line4 else "")

        predictions.append({
            'Round': target_round,
            'Local': local,
            'LocalName': local_name,
            'Road': road,
            'RoadName': road_name,
            'Margin': round(margin, 2),
            'Winner': winner,
            'WinnerName': team_names.get(winner, winner),
            'HomeWinProb': round(home_win_prob, 1),
            'Conf': round(win_prob, 1),
            'Insight': final_insight,
        })

    # 6. Save game predictions first so player forecaster can read win probs
    with open(json_out, 'w') as f:
        json.dump({'round': target_round, 'predictions': predictions}, f, indent=2)

    # 7. Player performance forecast (more complete model: defence + form + home/away)
    player_forecasts = predict_player_round(target_round=target_round, oracle_path=json_out)
    if player_forecasts:
        print_player_leaderboard(player_forecasts, target_round)

    # 8. Derive MVP candidates from player forecasts (top 10 by PredictedPIR)
    #    This ensures consistency — same defensive / form / win-prob factors for both lists.
    if player_forecasts:
        mvp_candidates = [
            {
                'Player':       p['Player'],
                'Team':         p['Team'],
                'GP':           p['GP'],
                'AvgPIR':       p['AvgPIR'],
                'MaxPIR':       p.get('MaxPIR', p['AvgPIR']),
                'AvgPTS':       p['AvgPTS'],
                'WinProb':      p['WinProb'],
                'ExpectedPIR':  p['PredictedPIR'],
            }
            for p in player_forecasts[:10]
        ]
    else:
        mvp_candidates = predict_round_mvp(predictions, top_n=10)
    print_mvp_leaderboard(mvp_candidates, target_round)

    # 9. Save full JSON
    output = {
        'round':           target_round,
        'predictions':     predictions,
        'mvp_candidates':  mvp_candidates,
        'player_forecasts': player_forecasts,
    }
    with open(json_out, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Forecast JSON saved to {json_out}")

    # 7. Visualize
    cols = 3
    rows = (len(predictions) // cols) + (1 if len(predictions) % cols else 0)

    # Taller figsize to fit text (even taller for 3-line insight)
    # INCREASED HEIGHT: 8 inches per row to prevent layout cramping
    fig, axes = plt.subplots(rows, cols, figsize=(15, 8*rows))
    fig.suptitle(f"THE ORACLE: Round {target_round} Forecast", fontsize=24, fontweight='bold', color='#1d428a')
    
    axes = axes.flatten()
    
    team_colors = {
        'OLY': '#E2001A', 'ULK': '#002B5C', 'PAN': '#007F3D', 
        'MAD': '#645486', 'BAR': '#004D98', 'MCO': '#D4AF37',
        'ZAL': '#006233', 'DUB': '#000000', 'IST': '#003366',
        'HTA': '#000000', 'PAR': '#000000', 'RED': '#CC0000', 
        'TEL': '#F6C300', 'BAS': '#B50031', 'MUN': '#0066B2',
        'BES': '#d9d9d9',
        'VIR': '#000000', 'PAM': '#EB7622', 'ASV': '#000000',
        'PRS': '#000000' # Paris
    }
    


    for i, pred in enumerate(predictions):
        ax = axes[i]
        
        local = pred['Local']
        road = pred['Road']
        
        local_name = team_names.get(local, local)
        road_name = team_names.get(road, road)
        
        margin = pred['Margin']
        win_prob = pred['Conf']  # Already calibrated by logistic function
        
        # Card BG
        ax.set_facecolor('#f8f9fa')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        
        l_col = team_colors.get(local, '#333')
        r_col = team_colors.get(road, '#333')
        def add_normalized_logo(ax, team_code, x, y):
             logo_path = f"docs/logos/{team_code}.png"
             if os.path.exists(logo_path):
                 try:
                     img = Image.open(logo_path).convert("RGBA")
                     img.thumbnail((150, 150)) # Keep 150 for resolution
                     
                     # Zoom 0.75 was too big (112px). 
                     # Target ~60px effective size -> 0.40 zoom
                     imagebox = OffsetImage(img, zoom=0.40) 
                     ab = AnnotationBbox(imagebox, (x, y), frameon=False)
                     ax.add_artist(ab)
                     return True
                 except Exception as e:
                     print(f"Error loading logo for {team_code}: {e}")
             return False

        # Local (Top)
        # Logo at Top (0.5, 0.92)
        logo_loaded = add_normalized_logo(ax, local, 0.5, 0.92)
        
        # Name below Logo (0.5, 0.81)
        ax.text(0.5, 0.81, local_name, ha='center', va='center', fontsize=14, fontweight='bold', color=l_col)
        
        # VS (0.5, 0.74)
        ax.text(0.5, 0.74, "vs", ha='center', va='center', fontsize=10, color='#aaa')
        
        # Road (Below VS)
        # Name (0.5, 0.67)
        ax.text(0.5, 0.67, road_name, ha='center', va='center', fontsize=14, fontweight='bold', color=r_col)
        
        # Logo below Name (0.5, 0.55) - Increased gap
        logo_loaded_r = add_normalized_logo(ax, road, 0.5, 0.55)
        
        # Winner (0.5, 0.40) - Huge gap from logo
        winner = pred['Winner']
        # User request: "Winner: Team by X.X"
        ax.text(0.5, 0.40, f"WINNER: {team_names.get(winner, winner)} by {abs(margin):.1f}", ha='center', fontsize=16, fontweight='bold', color='green')
        ax.text(0.5, 0.34, f"{win_prob:.0f}% Confidence", ha='center', fontsize=11, color='#666')
        
        # Insight (0.5, 0.22)
        ax.text(0.5, 0.22, pred['Insight'], ha='center', fontsize=9, fontstyle='normal', color='#333', 
                bbox=dict(facecolor='white', alpha=0.9, edgecolor='#ddd', boxstyle='round,pad=0.3'))
        
        # Removed Bottom Bar as per user request. Margin is now in the Winner line.

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off') # Hide axes lines



    # MVP candidates card — use first available empty slot
    first_empty = i + 1
    if mvp_candidates and first_empty < len(axes):
        ax = axes[first_empty]
        ax.set_facecolor('#f0f4ff')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        ax.text(0.5, 0.95, f"MVP CANDIDATES — Round {target_round}",
                ha='center', va='top', fontsize=13, fontweight='bold', color='#1d428a')
        ax.axhline(0.88, color='#1d428a', linewidth=1, xmin=0.05, xmax=0.95)
        header = f"{'#':<3} {'Player':<22} {'Tm':<5} {'AvgPIR':>7} {'WinP':>6} {'ExpPIR':>7}"
        ax.text(0.05, 0.83, header, ha='left', va='top', fontsize=8,
                fontfamily='monospace', color='#555')
        for rank, c in enumerate(mvp_candidates[:8], 1):
            y = 0.83 - rank * 0.09
            name = c['Player'].split(',')[0].strip().title()  # last name only
            line = f"{rank:<3} {name:<22} {c['Team']:<5} {c['AvgPIR']:>7.1f} {c['WinProb']:>5.0f}% {c['ExpectedPIR']:>7.1f}"
            color = '#1a6b1a' if rank == 1 else '#333'
            weight = 'bold' if rank == 1 else 'normal'
            ax.text(0.05, y, line, ha='left', va='top', fontsize=8,
                    fontfamily='monospace', color=color, fontweight=weight)
        first_empty += 1

    # Hide any remaining unused subplots
    for j in range(first_empty, len(axes)):
        axes[j].set_visible(False)
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.92)
    
    outfile = f"oracle_forecast_round_{target_round}{round_suffix}.png"
    plt.savefig(outfile, dpi=150)
    print(f"Forecast saved to {outfile}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--round', type=int, help='Round number to predict')
    args = parser.parse_args()
    
    run_oracle(args.round)
