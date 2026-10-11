"""
Expected Wins Profile Matrix Visualization.
Shows probability of each team reaching specific win thresholds.
Inspired by @g_giase's Euroleague sims model.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from chart_utils import add_logo
from chart_utils import ratings_path


CODE_TO_FULL_NAME = {
    'BER': 'Alba Berlin', 'IST': 'Anadolu Efes', 'MCO': 'AS Monaco',
    'BAS': 'Baskonia', 'RED': 'Crvena Zvezda',
    'MIL': 'EA7 Milan', 'BAR': 'FC Barcelona', 'MUN': 'Bayern Munich',
    'ULK': 'Fenerbahce', 'ASV': 'ASVEL',
    'TEL': 'Maccabi Tel Aviv', 'OLY': 'Olympiacos',
    'PAN': 'Panathinaikos', 'PAR': 'Partizan',
    'PRS': 'Paris Basketball', 'MAD': 'Real Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia Basket', 'VIR': 'Virtus Bologna',
    'ZAL': 'Zalgiris Kaunas', 'DUB': 'Dubai Basketball',
    'HTA': 'Hapoel Tel Aviv'
}


def get_sos_label(team_code, sos_data):
    """Get SOS category (HIGH/MEDIUM/LOW) from adjusted_ratings.json."""
    for t in sos_data:
        if t['Team'] == team_code:
            sos = t.get('SOS_WinPct', 0.5)
            if sos >= 0.55:
                return 'HIGH', '#ef4444'
            elif sos >= 0.48:
                return 'MEDIUM', '#f59e0b'
            else:
                return 'LOW', '#22c55e'
    return 'MEDIUM', '#f59e0b'


def create_wins_profile():
    print("Generating Expected Wins Profile Matrix...")
    
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    
    # Load Monte Carlo results
    mc_file = ratings_path('monte_carlo_results')
    if mc_file is None:
        print("No monte_carlo_results for this round yet - skipping wins profile matrix.")
        return
    with open(mc_file, 'r') as f:
        mc_data = json.load(f)
    
    # Load SOS data
    try:
        sos_file = f'adjusted_ratings{round_suffix}.json'
        if not os.path.exists(sos_file):
            sos_file = 'adjusted_ratings.json'
        with open(sos_file, 'r') as f:
            sos_data = json.load(f)
    except:
        sos_data = []
    
    # Sort by Avg_Wins descending
    mc_data.sort(key=lambda x: x['Avg_Wins'], reverse=True)
    
    # Determine the win threshold columns
    # Find the range of relevant win counts
    all_xwins = [t['Avg_Wins'] for t in mc_data]
    min_relevant = max(int(min(all_xwins)) - 2, 10)
    max_relevant = min(int(max(all_xwins)) + 2, 30)
    
    # Pick ~9 evenly spaced thresholds
    thresholds = list(range(min_relevant, max_relevant + 1))
    # Trim to a reasonable number of columns (max 10)
    if len(thresholds) > 10:
        step = len(thresholds) // 9
        thresholds = thresholds[::step]
        if thresholds[-1] < max_relevant:
            thresholds.append(max_relevant)
    
    num_teams = len(mc_data)
    num_cols = len(thresholds)
    
    # --- Figure Setup ---
    fig_width = 14
    fig_height = 1.2 + num_teams * 0.55
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    ax.axis('off')
    
    # Layout constants
    y_top = 0.95
    row_h = 0.78 / num_teams
    
    # Column X positions
    x_rank = 0.03
    x_logo = 0.06
    x_name = 0.10
    x_xwins = 0.28
    x_sos = 0.35
    x_grid_start = 0.44
    x_grid_end = 0.97
    col_width = (x_grid_end - x_grid_start) / num_cols
    
    # --- Title ---
    ax.text(0.50, y_top, "Expected Wins Profile Matrix | The Fight for Playoff and Play-In",
            ha='center', va='center', fontsize=18, color='#fbbf24',
            fontweight='bold')
    ax.text(0.50, y_top - 0.03, "10k Sims on KenPom Adjusted Net Ratings & Location Splits | R29 / 38",
            ha='center', va='center', fontsize=10, color='#94a3b8', style='italic')
    
    # --- Header Row ---
    y_header = y_top - 0.07
    
    # Header background
    hdr_bg = patches.Rectangle((0.01, y_header - 0.015), 0.98, 0.035,
                                facecolor='#1e293b', alpha=0.9, zorder=0)
    ax.add_patch(hdr_bg)
    
    ax.text(x_rank, y_header, "#", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(x_name + 0.04, y_header, "Team", ha='left', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(x_xwins, y_header, "xWins", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(x_sos, y_header, "SoS", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    
    # Win threshold column headers
    for j, thresh in enumerate(thresholds):
        x_col = x_grid_start + j * col_width + col_width / 2
        ax.text(x_col, y_header, str(thresh), ha='center', va='center', fontsize=9,
                color='#fbbf24', fontweight='bold')
    
    # Divider
    ax.plot([0.01, 0.99], [y_header - 0.02, y_header - 0.02],
            color='#334155', linewidth=1.5)
    
    # --- Data Rows ---
    y_start = y_header - 0.04
    
    for i, team in enumerate(mc_data):
        y = y_start - (i * row_h)
        code = team['Team']
        
        # Alternate row background
        if i % 2 == 0:
            bg = patches.Rectangle((0.01, y - row_h * 0.45), 0.98, row_h * 0.9,
                                    facecolor='#1e293b', alpha=0.3, zorder=0)
            ax.add_patch(bg)
        
        # Rank
        ax.text(x_rank, y, str(i + 1), ha='center', va='center', fontsize=11,
                color='#94a3b8', fontweight='bold')
        
        # Logo
        try:
            add_logo(ax, code, x_logo, y, zoom=0.30)
        except:
            pass
        
        # Team name
        name = CODE_TO_FULL_NAME.get(code, code)
        ax.text(x_name, y, name, ha='left', va='center', fontsize=11,
                color='white', fontweight='bold')
        
        # xWins
        ax.text(x_xwins, y, str(int(team['Avg_Wins'])), ha='center', va='center',
                fontsize=12, color='white', fontweight='bold')
        
        # SOS label
        sos_label, sos_color = get_sos_label(code, sos_data)
        ax.text(x_sos, y, sos_label, ha='center', va='center', fontsize=8,
                color=sos_color, fontweight='bold')
        
        # Win distribution cells
        win_dist = team.get('Win_Distribution', {})
        for j, thresh in enumerate(thresholds):
            x_col = x_grid_start + j * col_width
            pct = win_dist.get(str(thresh), 0)
            
            if pct <= 0:
                continue
            
            # Color: green gradient based on probability
            # High probability = vivid green, low = dimmer
            if pct >= 90:
                cell_color = '#22c55e'
                text_color = '#0f172a'
                alpha = 0.85
            elif pct >= 70:
                cell_color = '#4ade80'
                text_color = '#0f172a'
                alpha = 0.75
            elif pct >= 50:
                cell_color = '#86efac'
                text_color = '#0f172a'
                alpha = 0.6
            elif pct >= 30:
                cell_color = '#bbf7d0'
                text_color = '#1e293b'
                alpha = 0.45
            elif pct >= 10:
                cell_color = '#dcfce7'
                text_color = '#334155'
                alpha = 0.3
            else:
                cell_color = '#f0fdf4'
                text_color = '#64748b'
                alpha = 0.15
            
            # Cell background
            cell_bg = patches.FancyBboxPatch(
                (x_col + 0.003, y - row_h * 0.38),
                col_width - 0.006, row_h * 0.76,
                boxstyle="round,pad=0.002",
                facecolor=cell_color, alpha=alpha, zorder=1
            )
            ax.add_patch(cell_bg)
            
            # Cell text
            ax.text(x_col + col_width / 2, y, f"{pct}%",
                    ha='center', va='center', fontsize=8,
                    color=text_color, fontweight='bold', zorder=2)
    
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.02, 1.0)
    
    plt.tight_layout()
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'wins_profile_matrix{round_suffix}.png'
    
    plt.savefig(outfile, dpi=200, bbox_inches='tight', facecolor='#0f172a')
    print(f"Chart saved to {outfile}!")


if __name__ == '__main__':
    create_wins_profile()
