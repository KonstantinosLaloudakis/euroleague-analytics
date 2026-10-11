"""
Seed Probability Distribution Heatmap.
Shows the probability of each team finishing in each specific position (1st-20th).
Uses a color-intensity heatmap where brighter = higher probability.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.colors as mcolors
import numpy as np
from chart_utils import add_logo


CODE_TO_SHORT = {
    'BER': 'Berlin', 'IST': 'Efes', 'MCO': 'Monaco',
    'BAS': 'Baskonia', 'RED': 'Zvezda',
    'MIL': 'Milan', 'BAR': 'Barcelona', 'MUN': 'Bayern',
    'ULK': 'Fener', 'ASV': 'ASVEL',
    'TEL': 'Maccabi', 'OLY': 'Olympiacos',
    'PAN': 'Pana', 'PAR': 'Partizan',
    'PRS': 'Paris', 'MAD': 'Real Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia', 'VIR': 'Virtus',
    'ZAL': 'Zalgiris', 'DUB': 'Dubai',
    'HTA': 'Hapoel'
}


def create_seed_heatmap():
    print("Generating Seed Distribution Heatmap...")
    
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'monte_carlo_results{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'monte_carlo_results.json'
    with open(in_file, 'r') as f:
        mc_data = json.load(f)
    
    # Sort by average expected position (weighted from seed dist)
    mc_data.sort(key=lambda x: x['Avg_Wins'], reverse=True)
    
    num_teams = len(mc_data)
    
    # Build the probability matrix
    prob_matrix = np.zeros((num_teams, num_teams))
    team_codes = []
    
    for i, team in enumerate(mc_data):
        team_codes.append(team['Team'])
        seed_dist = team.get('Seed_Distribution', {})
        for pos in range(num_teams):
            prob_matrix[i, pos] = seed_dist.get(str(pos + 1), 0)
    
    # --- Figure ---
    fig_w = 16
    fig_h = 12
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    
    # Layout
    left_margin = 0.14
    top_margin = 0.90
    cell_w = (0.97 - left_margin) / num_teams
    cell_h = (top_margin - 0.06) / num_teams
    
    # Title
    ax.text(0.50, 0.96, "SEED PROBABILITY DISTRIBUTION",
            ha='center', va='center', fontsize=22, color='#fbbf24',
            fontweight='bold', transform=ax.transAxes)
    ax.text(0.50, 0.93, "Probability of each team finishing in each position  •  10,000 Simulations",
            ha='center', va='center', fontsize=11, color='#94a3b8',
            style='italic', transform=ax.transAxes)
    
    # Column headers (positions 1-20)
    for j in range(num_teams):
        x = left_margin + j * cell_w + cell_w / 2
        pos_label = str(j + 1)
        
        # Color the position headers by playoff zone
        if j < 4:
            col_color = '#22c55e'   # Top 4: green
        elif j < 6:
            col_color = '#3b82f6'   # Top 6: blue
        elif j < 10:
            col_color = '#f59e0b'   # Top 10: amber
        else:
            col_color = '#64748b'   # Bottom: gray
        
        ax.text(x, top_margin + 0.015, pos_label, ha='center', va='center',
                fontsize=8, color=col_color, fontweight='bold',
                transform=ax.transAxes)
    
    # Zone labels
    ax.text(left_margin + 2 * cell_w, top_margin + 0.035, "HCA",
            ha='center', va='center', fontsize=7, color='#22c55e',
            fontweight='bold', transform=ax.transAxes)
    ax.text(left_margin + 5 * cell_w, top_margin + 0.035, "PLAYOFFS",
            ha='center', va='center', fontsize=7, color='#3b82f6',
            fontweight='bold', transform=ax.transAxes)
    ax.text(left_margin + 8 * cell_w, top_margin + 0.035, "PLAY-IN",
            ha='center', va='center', fontsize=7, color='#f59e0b',
            fontweight='bold', transform=ax.transAxes)
    
    # Draw zone divider lines
    for div_pos in [4, 6, 10]:
        x_div = left_margin + div_pos * cell_w
        ax.plot([x_div, x_div], [0.06, top_margin],
                color='#475569', linewidth=1.5, linestyle='--',
                alpha=0.6, transform=ax.transAxes)
    
    # Row headers (team logos + names)
    for i, code in enumerate(team_codes):
        y = top_margin - i * cell_h - cell_h / 2
        
        # Logo
        try:
            logo_x = left_margin - 0.09
            add_logo(ax, code, logo_x, y, zoom=0.25,
                     transform=ax.transAxes)
        except:
            pass
        
        # Team name
        name = CODE_TO_SHORT.get(code, code)
        ax.text(left_margin - 0.04, y, name, ha='left', va='center',
                fontsize=9, color='white', fontweight='bold',
                transform=ax.transAxes)
    
    # Heatmap cells
    for i in range(num_teams):
        for j in range(num_teams):
            x = left_margin + j * cell_w
            y_cell = top_margin - (i + 1) * cell_h
            pct = prob_matrix[i, j]
            
            if pct <= 0:
                continue
            
            # Color intensity
            # Peak probability gets the brightest color
            max_pct_for_team = max(prob_matrix[i, :])
            intensity = pct / max(max_pct_for_team, 1)
            
            # Color based on position zone
            if j < 4:
                base_rgb = np.array([0.133, 0.773, 0.369])  # Green
            elif j < 6:
                base_rgb = np.array([0.231, 0.510, 0.965])  # Blue
            elif j < 10:
                base_rgb = np.array([0.961, 0.620, 0.043])  # Amber
            else:
                base_rgb = np.array([0.584, 0.647, 0.710])  # Gray
            
            alpha = max(0.1, min(0.85, pct / 40))
            
            cell_bg = patches.Rectangle(
                (x + 0.002, y_cell + 0.002),
                cell_w - 0.004, cell_h - 0.004,
                facecolor=base_rgb, alpha=alpha,
                transform=ax.transAxes, zorder=1
            )
            ax.add_patch(cell_bg)
            
            # Text (only show if significant)
            if pct >= 2:
                text_color = 'white' if alpha > 0.4 else '#94a3b8'
                ax.text(x + cell_w / 2, y_cell + cell_h / 2,
                        f"{pct:.0f}", ha='center', va='center',
                        fontsize=7, color=text_color, fontweight='bold',
                        transform=ax.transAxes, zorder=2)
    
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'seed_distribution{round_suffix}.png'

    plt.savefig(outfile, dpi=200, bbox_inches='tight',
                facecolor='#0f172a')
    print(f"Chart saved to {outfile}!")


if __name__ == '__main__':
    create_seed_heatmap()
