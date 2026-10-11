"""
KenPom-Style Adjusted Net Rating Engine for Euroleague (current season).
Calculates Adjusted Offensive, Defensive, and Net Ratings for all teams
using an iterative convergence algorithm that accounts for Strength of Schedule.

Includes regular season + play-in + playoff games once played, with per-round
recency decay so playoff games carry full weight and older regular-season
games gradually fade.

Also calculates Remaining Strength of Schedule (SOS) for each team based on
the unplayed games in the official schedule.
"""

import json
import os
import xml.etree.ElementTree as ET
import numpy as np

from season_config import CURRENT_SEASON


# --- Configuration ---
NUM_ITERATIONS = 50  # Number of convergence passes
LEAGUE_AVG_PPG = 80.0  # Approximate league average PPG (will be calculated)
RECENCY_DECAY = 0.97  # Per-round exponential decay (0.97 = game from 20 rounds ago counts 54%)

# Team name to code mapping (shared with other scripts)
from team_aliases import NAME_TO_CODE


def load_gamecode_to_round():
    """Build {GameCode: round_number} from the official schedule XML.

    Used so recency decay is applied per round, not per game code (which
    would be ~10× more aggressive given 10 games per round).
    """
    tree = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')
    mapping = {}
    for item in tree.getroot().findall('item'):
        gc_el = item.find('gamecode')
        gd_el = item.find('gameday')
        if gc_el is None or gd_el is None:
            continue
        gc_text = gc_el.text
        try:
            gc = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
            mapping[gc] = int(gd_el.text)
        except (ValueError, AttributeError):
            continue
    return mapping


def load_game_data():
    """Load all played games (regular season + play-in + playoffs) from
    mvp_game_results.json.

    Each game is annotated with its round number from the schedule XML
    for recency-decay weighting. Playoff games have GameCode > 380 and
    aren't in the XML; they fall back to (gc-1)//10+1, which assigns the
    play-in round to round 39, QF games to rounds 39-40, etc. This means
    the most recent playoff games carry full weight while regular-season
    games decay slightly behind them.

    If EUROLEAGUE_MAX_ROUND is set, games from rounds beyond that are
    excluded — used to regenerate historical R{N}.json snapshots.
    """
    with open('mvp_game_results.json', 'r') as f:
        data = json.load(f)

    def _played(g):
        gc = g.get('GameCode', 0)
        if isinstance(gc, float):
            gc = int(gc)
        return gc > 0 and g['LocalScore'] > 0 and g['RoadScore'] > 0

    played = [g for g in data if _played(g)]

    gc_to_round = load_gamecode_to_round()
    for g in played:
        gc = int(g.get('GameCode', 0))
        g['Round'] = gc_to_round.get(gc, (gc - 1) // 10 + 1)

    max_round_env = os.environ.get('EUROLEAGUE_MAX_ROUND')
    if max_round_env:
        max_round = int(max_round_env)
        played = [g for g in played if g['Round'] <= max_round]
        print(f"Filtered to round <= {max_round}: {len(played)} played games.")
    else:
        reg_count = sum(1 for g in played if int(g.get('GameCode', 0)) <= 380)
        po_count = len(played) - reg_count
        print(f"Loaded {len(played)} played games ({reg_count} regular season + {po_count} playoff).")
    return played


def calculate_raw_ratings(games):
    """Calculate raw Offensive and Defensive ratings per team (points per game)."""
    teams = {}
    
    for g in games:
        home, away = g['LocalTeam'], g['RoadTeam']
        h_pts, a_pts = g['LocalScore'], g['RoadScore']
        game_round = g.get('Round', g.get('GameCode', 0))

        for t in (home, away):
            if t not in teams:
                teams[t] = {
                    'games': [],
                    'total_pts_scored': 0, 'total_pts_allowed': 0, 'gp': 0,
                    'wins': 0, 'losses': 0,
                    'home_w': 0, 'home_l': 0, 'away_w': 0, 'away_l': 0
                }

        # Home team data
        teams[home]['games'].append({
            'opponent': away, 'pts_scored': h_pts, 'pts_allowed': a_pts,
            'location': 'home', 'round': game_round
        })
        teams[home]['total_pts_scored'] += h_pts
        teams[home]['total_pts_allowed'] += a_pts
        teams[home]['gp'] += 1
        if h_pts > a_pts:
            teams[home]['wins'] += 1
            teams[home]['home_w'] += 1
        else:
            teams[home]['losses'] += 1
            teams[home]['home_l'] += 1
        
        # Away team data
        teams[away]['games'].append({
            'opponent': home, 'pts_scored': a_pts, 'pts_allowed': h_pts,
            'location': 'away', 'round': game_round
        })
        teams[away]['total_pts_scored'] += a_pts
        teams[away]['total_pts_allowed'] += h_pts
        teams[away]['gp'] += 1
        if a_pts > h_pts:
            teams[away]['wins'] += 1
            teams[away]['away_w'] += 1
        else:
            teams[away]['losses'] += 1
            teams[away]['away_l'] += 1
    
    # Calculate raw ratings
    league_total_scored = sum(t['total_pts_scored'] for t in teams.values())
    league_total_gp = sum(t['gp'] for t in teams.values())
    league_avg = league_total_scored / league_total_gp  # True league avg PPG
    
    print(f"League Average PPG: {league_avg:.1f}")
    print(f"Teams found: {len(teams)}")
    
    return teams, league_avg


def run_iterative_adjustment(teams, league_avg, num_iterations=NUM_ITERATIONS):
    """
    Run the KenPom-style iterative convergence algorithm with recency weighting.

    For each iteration:
    1. For each team, adjust their offensive rating by the quality of defenses faced.
    2. For each team, adjust their defensive rating by the quality of offenses faced.
    3. Weight each game by recency (exponential decay from most recent round).
    4. Repeat until convergence.
    """
    team_list = sorted(teams.keys())

    # Compute per-game recency weights: weight = RECENCY_DECAY ^ (max_round - game_round)
    max_round = max(g['round'] for t in teams.values() for g in t['games'])
    for t in team_list:
        for game in teams[t]['games']:
            game['weight'] = RECENCY_DECAY ** (max_round - game['round'])

    # Initialize adjusted ratings with recency-weighted raw values
    adj_off = {}
    adj_def = {}
    for t in team_list:
        w_total = sum(g['weight'] for g in teams[t]['games'])
        adj_off[t] = sum(g['pts_scored'] * g['weight'] for g in teams[t]['games']) / w_total
        adj_def[t] = sum(g['pts_allowed'] * g['weight'] for g in teams[t]['games']) / w_total

    print(f"\nRunning {num_iterations} convergence iterations (recency decay={RECENCY_DECAY})...")

    for iteration in range(num_iterations):
        new_adj_off = {}
        new_adj_def = {}

        for t in team_list:
            # --- Adjust Offensive Rating ---
            # For each game, what SHOULD this team have scored against a league-average defense?
            # actual_scored * (league_avg_defense / opponent_adj_defense)
            adjusted_scored_total = 0
            adjusted_allowed_total = 0

            for game in teams[t]['games']:
                opp = game['opponent']
                w = game['weight']

                # Offensive adjustment:
                # Scale points scored by how good/bad the opponent's defense is vs average
                opp_def_factor = adj_def[opp] / league_avg  # >1 = weak defense, <1 = strong defense
                # If opponent has a weak defense (allows more), our actual scoring is less impressive
                # So we divide by the factor to normalize
                adjusted_scored = game['pts_scored'] / opp_def_factor
                adjusted_scored_total += adjusted_scored * w

                # Defensive adjustment:
                # Scale points allowed by how good/bad the opponent's offense is vs average
                opp_off_factor = adj_off[opp] / league_avg  # >1 = strong offense, <1 = weak offense
                # If opponent has a strong offense, allowing them points is more understandable
                # So we divide by the factor to normalize
                adjusted_allowed = game['pts_allowed'] / opp_off_factor
                adjusted_allowed_total += adjusted_allowed * w

            w_total = sum(g['weight'] for g in teams[t]['games'])
            new_adj_off[t] = adjusted_scored_total / w_total
            new_adj_def[t] = adjusted_allowed_total / w_total
        
        # Check convergence (max change across all teams)
        max_change = 0
        for t in team_list:
            off_change = abs(new_adj_off[t] - adj_off[t])
            def_change = abs(new_adj_def[t] - adj_def[t])
            max_change = max(max_change, off_change, def_change)
        
        adj_off = new_adj_off
        adj_def = new_adj_def
        
        if iteration < 3 or iteration == num_iterations - 1:
            print(f"  Iteration {iteration + 1}: max change = {max_change:.4f}")
    
    # Calculate Adjusted Net Rating
    adj_net = {t: adj_off[t] - adj_def[t] for t in team_list}
    
    return adj_off, adj_def, adj_net


def calculate_remaining_sos(adj_net, teams):
    """
    Calculate the Remaining Strength of Schedule for each team.
    Uses LOCATION-AWARE opponent Win%:
      - Playing AWAY → use opponent's Home Win% (they're at home = harder)
      - Playing HOME → use opponent's Away Win% (they're on the road = easier)
    """
    # Build Home/Away Win% lookup from team data
    home_win_pct = {}
    away_win_pct = {}
    overall_win_pct = {}
    
    for t, stats in teams.items():
        home_gp = stats.get('home_w', 0) + stats.get('home_l', 0)
        away_gp = stats.get('away_w', 0) + stats.get('away_l', 0)
        total_gp = stats['gp']
        
        home_win_pct[t] = stats['home_w'] / home_gp if home_gp > 0 else 0.5
        away_win_pct[t] = stats['away_w'] / away_gp if away_gp > 0 else 0.5
        overall_win_pct[t] = stats['wins'] / total_gp if total_gp > 0 else 0.5
    
    # Parse schedule XML
    try:
        tree = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')
        root = tree.getroot()
        all_items = root.findall('item')
    except Exception as e:
        print(f"Error loading schedule: {e}")
        return {}
    
    # Cross-check: build set of played game codes from actual results
    played_game_codes = set()
    try:
        with open('mvp_game_results.json', 'r') as f:
            results_data = json.load(f)
        for g in results_data:
            if g.get('LocalScore', 0) > 0:
                played_game_codes.add(g['GameCode'])
    except:
        pass
    
    # Build remaining games with location context
    remaining_games_by_team = {t: [] for t in adj_net.keys()}
    total_remaining = 0
    total_played = 0
    
    for item in all_items:
        # Check XML played flag
        played_el = item.find('played')
        is_played = played_el is not None and played_el.text and played_el.text.lower() == 'true'
        
        # Also check against actual results (in case XML is stale)
        gc_el = item.find('gamecode')
        if gc_el is not None:
            gc_text = gc_el.text
            gc_num = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
            if gc_num in played_game_codes:
                is_played = True
        
        if is_played:
            total_played += 1
            continue
        
        home_name = item.find('hometeam').text
        away_name = item.find('awayteam').text
        
        h_code = NAME_TO_CODE.get(home_name, "UNK")
        a_code = NAME_TO_CODE.get(away_name, "UNK")
        
        if h_code != "UNK" and a_code != "UNK":
            # Home team faces away opponent → use opponent's Away Win%
            remaining_games_by_team.setdefault(h_code, []).append({
                'opponent': a_code, 'location': 'home'
            })
            # Away team faces home opponent → use opponent's Home Win%
            remaining_games_by_team.setdefault(a_code, []).append({
                'opponent': h_code, 'location': 'away'
            })
            total_remaining += 1
    
    print(f"\nSchedule: {total_played} played, {total_remaining} remaining (out of {len(all_items)} total)")
    
    # Calculate LOCATION-AWARE SOS using POOLED RECORD method
    # (matches 3StepsBasket methodology: sum all opponent W-L into one record)
    remaining_sos = {}
    for team, games in remaining_games_by_team.items():
        if games:
            pooled_wins = 0
            pooled_losses = 0
            opponents_list = []
            
            for g in games:
                opp = g['opponent']
                opponents_list.append({'team': opp, 'loc': g['location']})
                if opp not in teams:
                    continue
                    
                if g['location'] == 'away':
                    # I'm playing away → opponent is at home → pool their HOME record
                    pooled_wins += teams[opp].get('home_w', 0)
                    pooled_losses += teams[opp].get('home_l', 0)
                else:
                    # I'm playing home → opponent is away → pool their AWAY record
                    pooled_wins += teams[opp].get('away_w', 0)
                    pooled_losses += teams[opp].get('away_l', 0)
            
            pooled_total = pooled_wins + pooled_losses
            pooled_pct = pooled_wins / pooled_total if pooled_total > 0 else 0.5
            
            remaining_sos[team] = {
                'avg_opp_net_rating': round(adj_net.get(team, 0), 2),
                'sos_win_pct': round(pooled_pct, 4),
                'pooled_record': f"{pooled_wins}-{pooled_losses}",
                'num_remaining_games': len(games),
                'opponents': opponents_list,
                'home_games': sum(1 for g in games if g['location'] == 'home'),
                'away_games': sum(1 for g in games if g['location'] == 'away')
            }
        else:
            remaining_sos[team] = {
                'avg_opp_net_rating': 0,
                'sos_win_pct': 0.5,
                'pooled_record': '0-0',
                'num_remaining_games': 0,
                'opponents': [],
                'home_games': 0,
                'away_games': 0
            }
    
    return remaining_sos


def main():
    print("=" * 60)
    print("🏀 EUROLEAGUE ADJUSTED NET RATINGS ENGINE (KenPom Style)")
    print("=" * 60)
    
    # 1. Load data
    games = load_game_data()
    
    # 2. Calculate raw ratings
    teams, league_avg = calculate_raw_ratings(games)
    
    # 3. Run iterative adjustment
    adj_off, adj_def, adj_net = run_iterative_adjustment(teams, league_avg)
    
    # 4. Calculate remaining SOS (location-aware)
    remaining_sos = calculate_remaining_sos(adj_net, teams)
    
    # 5. Build final output
    team_list = sorted(adj_net.keys(), key=lambda t: adj_net[t], reverse=True)
    
    print("\n" + "=" * 80)
    print(f"{'Rank':<5} {'Team':<6} {'W-L':<8} {'Adj Off':>8} {'Adj Def':>8} {'Adj Net':>8} {'Raw Net':>8} {'Rem SOS':>8}")
    print("-" * 80)
    
    output_data = []
    for rank, t in enumerate(team_list, 1):
        raw_net = (teams[t]['total_pts_scored'] - teams[t]['total_pts_allowed']) / teams[t]['gp']
        wl = f"{teams[t]['wins']}-{teams[t]['losses']}"
        sos_pct = remaining_sos.get(t, {}).get('sos_win_pct', 0.5) * 100
        home_g = remaining_sos.get(t, {}).get('home_games', 0)
        away_g = remaining_sos.get(t, {}).get('away_games', 0)
        
        print(f"{rank:<5} {t:<6} {wl:<8} {adj_off[t]:>8.1f} {adj_def[t]:>8.1f} {adj_net[t]:>+8.1f} {raw_net:>+8.1f} {sos_pct:>7.2f}% ({home_g}H/{away_g}A)")
        
        output_data.append({
            'Team': t,
            'Rank': rank,
            'Record': wl,
            'Wins': teams[t]['wins'],
            'Losses': teams[t]['losses'],
            'Adj_Off': round(adj_off[t], 2),
            'Adj_Def': round(adj_def[t], 2),
            'Adj_Net': round(adj_net[t], 2),
            'Raw_Net': round(raw_net, 2),
            'Remaining_SOS': round(sos_pct, 2),
            'SOS_WinPct': remaining_sos.get(t, {}).get('sos_win_pct', 0.5),
            'Remaining_Games': remaining_sos.get(t, {}).get('num_remaining_games', 0),
            'Home_Games': home_g,
            'Away_Games': away_g,
            'Remaining_Opponents': remaining_sos.get(t, {}).get('opponents', [])
        })
    
    # Save to JSON
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'adjusted_ratings{round_suffix}.json'
    
    with open(outfile, 'w') as f:
        json.dump(output_data, f, indent=4)
    
    print(f"\nSaved adjusted ratings to {outfile}")
    
    return output_data


if __name__ == '__main__':
    main()
