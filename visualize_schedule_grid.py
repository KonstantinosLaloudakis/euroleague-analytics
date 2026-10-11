"""
Remaining Schedule Grid.
A compact grid showing each team's remaining opponents in order,
color-coded by opponent strength (green=easy, yellow=mid, red=hard).
Home games marked with filled cells, away games with bordered cells.
"""

from season_config import CURRENT_SEASON
import json
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from chart_utils import add_logo


CODE_TO_SHORT = {
    'BER': 'BER', 'IST': 'EFS', 'MCO': 'MCO',
    'BAS': 'BAS', 'RED': 'CZV',
    'MIL': 'MIL', 'BAR': 'BAR', 'MUN': 'MUN',
    'ULK': 'FNB', 'ASV': 'ASV',
    'TEL': 'MAC', 'OLY': 'OLY',
    'PAN': 'PAN', 'PAR': 'PAR',
    'PRS': 'PRS', 'MAD': 'MAD',
    'BES': 'BJK',
    'PAM': 'VAL', 'VIR': 'VIR',
    'ZAL': 'ZAL', 'DUB': 'DUB',
    'HTA': 'HAP'
}

CODE_TO_FULL = {
    'BER': 'Alba Berlin', 'IST': 'Efes', 'MCO': 'Monaco',
    'BAS': 'Baskonia', 'RED': 'Zvezda',
    'MIL': 'Milan', 'BAR': 'Barcelona', 'MUN': 'Bayern',
    'ULK': 'Fenerbahce', 'ASV': 'ASVEL',
    'TEL': 'Maccabi', 'OLY': 'Olympiacos',
    'PAN': 'Pana', 'PAR': 'Partizan',
    'PRS': 'Paris', 'MAD': 'R. Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia', 'VIR': 'Virtus',
    'ZAL': 'Zalgiris', 'DUB': 'Dubai',
    'HTA': 'Hapoel'
}

from team_aliases import NAME_TO_CODE


def create_schedule_grid():
    print("Generating Remaining Schedule Grid...")
    
    # Load adjusted ratings for team strength
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'adjusted_ratings{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'adjusted_ratings.json'
    with open(in_file, 'r') as f:
        adj_data = json.load(f)
    
    adj_net_lookup = {t['Team']: t['Adj_Net'] for t in adj_data}
    wins_lookup = {t['Team']: t['Wins'] for t in adj_data}
    losses_lookup = {t['Team']: t['Losses'] for t in adj_data}
    
    # Parse schedule XML for remaining games with round info
    tree = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')
    root = tree.getroot()
    
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
    
    # Build remaining schedule per team, ordered by round
    team_schedule = {}  # {team: [(round, opponent, location), ...]}
    
    for item in root.findall('item'):
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
            continue
        
        home_name = item.find('hometeam').text
        away_name = item.find('awayteam').text
        gameday = int(item.find('gameday').text)
        
        h_code = NAME_TO_CODE.get(home_name, "UNK")
        a_code = NAME_TO_CODE.get(away_name, "UNK")
        
        if h_code == "UNK" or a_code == "UNK":
            continue
        
        team_schedule.setdefault(h_code, []).append((gameday, a_code, 'H'))
        team_schedule.setdefault(a_code, []).append((gameday, h_code, 'A'))
    
    # Sort each team's schedule by round
    for t in team_schedule:
        team_schedule[t].sort(key=lambda x: x[0])
    
    # Sort teams by current wins descending
    sorted_teams = sorted(team_schedule.keys(),
                         key=lambda t: (wins_lookup.get(t, 0), -losses_lookup.get(t, 0)),
                         reverse=True)

    if not sorted_teams:
        print("No remaining games — skipping schedule grid.")
        return

    # Determine opponent strength tiers
    # Get min/max adj_net for color scaling
    all_nets = list(adj_net_lookup.values())
    min_net = min(all_nets)
    max_net = max(all_nets)
    net_range = max_net - min_net
    
    num_teams = len(sorted_teams)
    max_games = max(len(team_schedule[t]) for t in sorted_teams)
    
    # --- Figure ---
    fig_w = 14
    fig_h = 1.5 + num_teams * 0.50
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    ax.axis('off')
    
    # Layout
    y_top = 0.95
    row_h = 0.82 / num_teams
    
    x_rank = 0.02
    x_logo = 0.05
    x_name = 0.08
    x_record = 0.22
    x_grid = 0.28
    grid_end = 0.97
    cell_w = (grid_end - x_grid) / max_games
    
    # Title
    ax.text(0.50, y_top, "REMAINING SCHEDULE GRID",
            ha='center', va='center', fontsize=20, color='#fbbf24',
            fontweight='bold')
    ax.text(0.50, y_top - 0.025, "Each cell = one remaining game  •  Color = opponent strength  •  H = Home, A = Away",
            ha='center', va='center', fontsize=9, color='#94a3b8', style='italic')
    
    # Header: round numbers
    y_header = y_top - 0.055
    rounds_seen = set()
    for t in sorted_teams:
        for rd, _, _ in team_schedule[t]:
            rounds_seen.add(rd)
    sorted_rounds = sorted(rounds_seen)
    
    # Header bg
    hdr_bg = patches.Rectangle((0.01, y_header - 0.012), 0.98, 0.03,
                                facecolor='#1e293b', alpha=0.9, zorder=0)
    ax.add_patch(hdr_bg)
    
    ax.text(x_rank, y_header, "#", ha='center', va='center', fontsize=8,
            color='#94a3b8', fontweight='bold')
    ax.text(x_name + 0.04, y_header, "Team", ha='left', va='center', fontsize=8,
            color='#94a3b8', fontweight='bold')
    ax.text(x_record, y_header, "W-L", ha='center', va='center', fontsize=8,
            color='#94a3b8', fontweight='bold')
    
    # Column headers for game slots
    for j in range(max_games):
        x = x_grid + j * cell_w + cell_w / 2
        ax.text(x, y_header, f"G{j+1}", ha='center', va='center', fontsize=7,
                color='#64748b', fontweight='bold')
    
    ax.plot([0.01, 0.99], [y_header - 0.018, y_header - 0.018],
            color='#334155', linewidth=1)
    
    # Legend
    legend_y = y_top - 0.025
    # Color swatches
    for label, color, x_pos in [("Hard", '#ef4444', 0.92), ("Mid", '#f59e0b', 0.95), ("Easy", '#22c55e', 0.98)]:
        ax.add_patch(patches.Rectangle((x_pos - 0.012, legend_y - 0.006), 0.01, 0.012,
                                        facecolor=color, alpha=0.7))
        ax.text(x_pos + 0.003, legend_y, label, fontsize=6, color='#94a3b8', va='center')
    
    # Data rows
    y_start = y_header - 0.035
    
    for i, team in enumerate(sorted_teams):
        y = y_start - i * row_h
        
        # Alternate bg
        if i % 2 == 0:
            bg = patches.Rectangle((0.01, y - row_h * 0.42), 0.98, row_h * 0.84,
                                    facecolor='#1e293b', alpha=0.2, zorder=0)
            ax.add_patch(bg)
        
        # Rank
        ax.text(x_rank, y, str(i + 1), ha='center', va='center', fontsize=9,
                color='#64748b', fontweight='bold')
        
        # Logo
        try:
            add_logo(ax, team, x_logo, y, zoom=0.22)
        except:
            pass
        
        # Name
        name = CODE_TO_FULL.get(team, team)
        ax.text(x_name, y, name, ha='left', va='center', fontsize=9,
                color='white', fontweight='bold')
        
        # Record
        w = wins_lookup.get(team, 0)
        l = losses_lookup.get(team, 0)
        ax.text(x_record, y, f"{w}-{l}", ha='center', va='center', fontsize=9,
                color='#94a3b8', fontweight='bold')
        
        # Schedule cells
        schedule = team_schedule[team]
        for j, (rd, opp, loc) in enumerate(schedule):
            x = x_grid + j * cell_w
            
            # Opponent strength → color
            opp_net = adj_net_lookup.get(opp, 0)
            # Normalize: -1 (weakest) to +1 (strongest)
            norm = (opp_net - min_net) / net_range if net_range > 0 else 0.5
            
            # Color interpolation: green (easy) → yellow (mid) → red (hard)
            if norm < 0.5:
                # Easy to mid: green → yellow
                r = norm * 2
                g = 0.8
                b = 0.2 * (1 - norm * 2)
            else:
                # Mid to hard: yellow → red
                r = 0.9
                g = 0.8 * (1 - (norm - 0.5) * 2)
                b = 0.1
            
            cell_color = (r, g, b)
            alpha = 0.6 + norm * 0.3  # Harder = more intense
            
            # Cell background
            cell = patches.FancyBboxPatch(
                (x + 0.002, y - row_h * 0.35),
                cell_w - 0.004, row_h * 0.7,
                boxstyle="round,pad=0.002",
                facecolor=cell_color, alpha=alpha, zorder=1
            )
            ax.add_patch(cell)
            
            # Away indicator: add border
            if loc == 'A':
                border = patches.FancyBboxPatch(
                    (x + 0.002, y - row_h * 0.35),
                    cell_w - 0.004, row_h * 0.7,
                    boxstyle="round,pad=0.002",
                    facecolor='none', edgecolor='white', linewidth=0.8,
                    zorder=2, alpha=0.5
                )
                ax.add_patch(border)
            
            # Opponent code + location marker
            opp_label = CODE_TO_SHORT.get(opp, opp[:3])
            text_color = '#0f172a' if norm > 0.3 else '#1e293b'
            
            ax.text(x + cell_w / 2, y + 0.003, opp_label, ha='center', va='center',
                    fontsize=6, color=text_color, fontweight='bold', zorder=3)
            
            # H/A indicator
            loc_color = '#ffffff' if loc == 'A' else '#0f172a'
            ax.text(x + cell_w / 2, y - row_h * 0.18, loc,
                    ha='center', va='center', fontsize=5,
                    color=loc_color, alpha=0.6, zorder=3)
    
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.02, 1)
    
    plt.tight_layout()
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'schedule_grid{round_suffix}.png'
    
    plt.savefig(outfile, dpi=200, bbox_inches='tight', facecolor='#0f172a')
    print(f"Chart saved to {outfile}!")


if __name__ == '__main__':
    create_schedule_grid()
