"""
Power Ranking Trajectory Chart.
Shows how each team's KenPom Adjusted Net Rating evolved over the season.
Re-runs the iterative adjustment engine at each round checkpoint.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from chart_utils import add_logo


# Team name mapping
CODE_TO_SHORT = {
    'BER': 'Berlin', 'IST': 'Efes', 'MCO': 'Monaco',
    'BAS': 'Baskonia', 'RED': 'Zvezda',
    'MIL': 'Milan', 'BAR': 'Barcelona', 'MUN': 'Bayern',
    'ULK': 'Fenerbahce', 'ASV': 'ASVEL',
    'TEL': 'Maccabi', 'OLY': 'Olympiacos',
    'PAN': 'Panathinaikos', 'PAR': 'Partizan',
    'PRS': 'Paris', 'MAD': 'Real Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia', 'VIR': 'Virtus',
    'ZAL': 'Zalgiris', 'DUB': 'Dubai',
    'HTA': 'Hapoel'
}

# Distinct team colors
TEAM_COLORS = {
    'ULK': '#FFD700', 'OLY': '#CC0000', 'MAD': '#FEBE10',
    'BES': '#9E9E9E',
    'PAM': '#FF6600', 'MCO': '#CC0000', 'BAR': '#A50044',
    'ZAL': '#006633', 'RED': '#CC0000', 'PAN': '#006633',
    'MIL': '#CE2B37', 'BAS': '#003DA5', 'MUN': '#DD0000',
    'HTA': '#FFD700', 'PRS': '#1B365D', 'TEL': '#FFD700',
    'DUB': '#C5B358', 'VIR': '#000000', 'IST': '#00205B',
    'BER': '#F6E500', 'PAR': '#000000', 'ASV': '#006633'
}


def compute_adj_net_at_round(all_games, max_game_code, num_iterations=15):
    """
    Compute Adjusted Net Rating for all teams using only games 
    with GameCode <= max_game_code.
    """
    games = [g for g in all_games if g['GameCode'] <= max_game_code 
             and g['LocalScore'] > 0 and g['RoadScore'] > 0]
    
    if len(games) < 10:
        return {}
    
    # Build raw ratings
    teams = {}
    for g in games:
        home, away = g['LocalTeam'], g['RoadTeam']
        h_pts, a_pts = g['LocalScore'], g['RoadScore']
        
        for t in (home, away):
            if t not in teams:
                teams[t] = {'games': [], 'total_scored': 0, 'total_allowed': 0, 'gp': 0}
        
        teams[home]['games'].append({'opp': away, 'scored': h_pts, 'allowed': a_pts})
        teams[home]['total_scored'] += h_pts
        teams[home]['total_allowed'] += a_pts
        teams[home]['gp'] += 1
        
        teams[away]['games'].append({'opp': home, 'scored': a_pts, 'allowed': h_pts})
        teams[away]['total_scored'] += a_pts
        teams[away]['total_allowed'] += h_pts
        teams[away]['gp'] += 1
    
    # League average
    total_scored = sum(t['total_scored'] for t in teams.values())
    total_gp = sum(t['gp'] for t in teams.values())
    league_avg = total_scored / total_gp if total_gp > 0 else 80
    
    # Initialize
    team_list = list(teams.keys())
    adj_off = {t: teams[t]['total_scored'] / teams[t]['gp'] for t in team_list}
    adj_def = {t: teams[t]['total_allowed'] / teams[t]['gp'] for t in team_list}
    
    # Iterative convergence
    for _ in range(num_iterations):
        new_off, new_def = {}, {}
        for t in team_list:
            adj_scored, adj_allowed = 0, 0
            for g in teams[t]['games']:
                opp = g['opp']
                if opp not in adj_def:
                    continue
                opp_def_factor = adj_def[opp] / league_avg
                opp_off_factor = adj_off[opp] / league_avg
                adj_scored += g['scored'] / opp_def_factor if opp_def_factor > 0 else g['scored']
                adj_allowed += g['allowed'] / opp_off_factor if opp_off_factor > 0 else g['allowed']
            new_off[t] = adj_scored / teams[t]['gp']
            new_def[t] = adj_allowed / teams[t]['gp']
        adj_off, adj_def = new_off, new_def
    
    return {t: adj_off[t] - adj_def[t] for t in team_list}


def create_trajectory_chart():
    print("Computing Power Rankings over the season...")
    
    # Load all games
    with open('mvp_game_results.json', 'r') as f:
        all_games = json.load(f)
    
    played = [g for g in all_games if g['LocalScore'] > 0 and g['RoadScore'] > 0]
    played.sort(key=lambda x: x['GameCode'])
    
    # Group games by approximate rounds (10 games per round)
    max_code = max(g['GameCode'] for g in played)
    
    # Compute ratings at checkpoints (every ~2 rounds = 20 games)
    checkpoints = list(range(40, max_code + 1, 20))
    if checkpoints[-1] < max_code:
        checkpoints.append(max_code)
    
    # Track ratings
    all_teams = set()
    trajectory = {}  # {team_code: [(round_label, adj_net), ...]}
    
    for cp in checkpoints:
        round_num = round(cp / 10)
        ratings = compute_adj_net_at_round(all_games, cp)
        
        for team, net in ratings.items():
            all_teams.add(team)
            if team not in trajectory:
                trajectory[team] = []
            trajectory[team].append((round_num, net))
        
        print(f"  Round ~{round_num}: {len(ratings)} teams rated")
    
    # Sort teams by final rating
    final_ratings = {}
    for team in all_teams:
        if trajectory.get(team):
            final_ratings[team] = trajectory[team][-1][1]
    
    sorted_teams = sorted(final_ratings.keys(), key=lambda t: final_ratings[t], reverse=True)
    
    # --- PLOT ---
    fig, ax = plt.subplots(figsize=(16, 10))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    
    # Grid
    ax.grid(True, axis='y', color='#1e293b', linewidth=0.5)
    ax.grid(True, axis='x', color='#1e293b', linewidth=0.5)
    ax.axhline(y=0, color='#475569', linewidth=1, linestyle='-', alpha=0.5)
    
    # Draw top 10 prominently, bottom 10 dimmed
    top_teams = sorted_teams[:10]
    bottom_teams = sorted_teams[10:]
    
    # Background teams (dimmed)
    for team in bottom_teams:
        data = trajectory.get(team, [])
        if len(data) < 2:
            continue
        rounds = [d[0] for d in data]
        nets = [d[1] for d in data]
        ax.plot(rounds, nets, color='#334155', linewidth=1, alpha=0.3)
    
    # Foreground teams (bright)
    for team in top_teams:
        data = trajectory.get(team, [])
        if len(data) < 2:
            continue
        rounds = [d[0] for d in data]
        nets = [d[1] for d in data]
        
        color = TEAM_COLORS.get(team, '#ffffff')
        ax.plot(rounds, nets, color=color, linewidth=2.5, alpha=0.9,
                marker='o', markersize=3)
        
        # Label at end
        name = CODE_TO_SHORT.get(team, team)
        ax.annotate(name, (rounds[-1], nets[-1]),
                    xytext=(8, 0), textcoords='offset points',
                    fontsize=8, color=color, fontweight='bold',
                    va='center')
    
    # Labels
    ax.set_xlabel("Round", fontsize=12, color='#94a3b8', labelpad=10)
    ax.set_ylabel("Adjusted Net Rating", fontsize=12, color='#94a3b8', labelpad=10)
    ax.tick_params(colors='#94a3b8')
    
    # Title
    ax.set_title("POWER RANKING TRAJECTORY | KenPom Adjusted Net Rating Over Time",
                 fontsize=18, color='#fbbf24', fontweight='bold', pad=20)
    
    # Subtitle
    fig.text(0.5, 0.92, "Top 10 teams highlighted  •  Each point = recalculated Adjusted Net Rating at that round",
             ha='center', fontsize=10, color='#94a3b8', style='italic')
    
    # Spines
    for spine in ax.spines.values():
        spine.set_color('#334155')
    
    plt.tight_layout(rect=[0, 0, 0.92, 0.90])
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'power_trajectory{round_suffix}.png'
    
    plt.savefig(outfile, dpi=200, bbox_inches='tight', facecolor='#0f172a')
    print(f"Chart saved to {outfile}!")


if __name__ == '__main__':
    create_trajectory_chart()
