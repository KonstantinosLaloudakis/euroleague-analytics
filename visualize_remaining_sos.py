"""
Visualize Remaining Strength of Schedule for all Euroleague teams (current season).
Creates a clean table-style visualization with color-coded rows.
SOS is expressed as average opponent Win% (intuitive percentage format).

Inspired by 3StepsBasket.com SOS tables.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from chart_utils import add_logo


# Full team name mapping for display
CODE_TO_FULL_NAME = {
    'BER': 'Alba Berlin', 'IST': 'Anadolu Efes Istanbul', 'MCO': 'AS Monaco',
    'BAS': 'Baskonia Vitoria-Gasteiz', 'RED': 'Crvena Zvezda Belgrade',
    'MIL': 'EA7 Emporio Armani Milan', 'BAR': 'FC Barcelona', 'MUN': 'FC Bayern Munich',
    'ULK': 'Fenerbahce Beko Istanbul', 'ASV': 'LDLC ASVEL Villeurbanne',
    'TEL': 'Maccabi Tel Aviv', 'OLY': 'Olympiacos Piraeus',
    'PAN': 'Panathinaikos Athens', 'PAR': 'Partizan Belgrade',
    'PRS': 'Paris Basketball', 'MAD': 'Real Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia Basket', 'VIR': 'Virtus Bologna',
    'ZAL': 'Zalgiris Kaunas', 'DUB': 'Dubai Basketball',
    'HTA': 'Hapoel Tel Aviv'
}


def create_sos_table():
    print("Generating Remaining SOS Table...")
    
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'adjusted_ratings{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'adjusted_ratings.json'
        
    with open(in_file, 'r') as f:
        data = json.load(f)
    
    # Only include teams that still have remaining games
    data = [t for t in data if t.get('Remaining_Games', 0) > 0]
    if not data:
        print("No teams with remaining games — skipping SOS table.")
        return

    # Use pre-calculated location-aware SOS from adjusted_ratings.json
    for team in data:
        # SOS_WinPct is already calculated in calculate_adjusted_ratings.py
        team['SOS_WinPct'] = team.get('SOS_WinPct', 0.5)

        total = team['Wins'] + team['Losses']
        team['Team_WinPct'] = team['Wins'] / total if total > 0 else 0.5

    # Sort by SOS (hardest first)
    data.sort(key=lambda x: x['SOS_WinPct'], reverse=True)
    
    # --- Create the Table ---
    num_teams = len(data)
    row_height = 0.045
    header_height = 0.05
    
    fig, ax = plt.subplots(figsize=(13, 16))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    ax.axis('off')
    
    # Calculate max games played to dynamically determine remaining rounds
    max_gp = max(team.get('Wins', 0) + team.get('Losses', 0) for team in data) if data else 0
    next_round = min(max_gp + 1, 38)
    if next_round <= 38:
        round_text = f"Remaining Games (Rounds {next_round}-38)"
    else:
        round_text = "End of Regular Season"
        
    # Title
    ax.text(0.5, 0.97, "REMAINING STRENGTH OF SCHEDULE",
            ha='center', va='center', fontsize=26, color='#fbbf24',
            fontweight='bold', fontname='Impact')
    ax.text(0.5, 0.94, f"Average Opponent Win%  •  {round_text}",
            ha='center', va='center', fontsize=13, color='#94a3b8', style='italic')
    
    # Column X positions
    col_logo = 0.08
    col_team = 0.15
    col_sos = 0.62
    col_winpct = 0.85
    
    # Header Row
    y_header = 0.89
    header_bg = patches.Rectangle((0.03, y_header - 0.02), 0.94, 0.04,
                                   facecolor='#1e293b', alpha=0.9, zorder=0)
    ax.add_patch(header_bg)
    
    ax.text(col_team, y_header, "TEAM", ha='left', va='center', fontsize=13,
            color='#94a3b8', fontweight='bold')
    ax.text(col_sos, y_header, "SOS", ha='center', va='center', fontsize=13,
            color='#94a3b8', fontweight='bold')
    ax.text(col_winpct, y_header, "TEAM W%", ha='center', va='center', fontsize=13,
            color='#94a3b8', fontweight='bold')
    
    # Divider line
    ax.plot([0.03, 0.97], [y_header - 0.023, y_header - 0.023],
            color='#334155', linewidth=2)
    
    # Data Rows
    y_start = 0.84
    y_step = 0.042
    
    # Get min/max SOS for color scaling
    sos_values = [d['SOS_WinPct'] for d in data]
    sos_min = min(sos_values)
    sos_max = max(sos_values)
    sos_range = sos_max - sos_min if sos_max != sos_min else 1
    
    for i, team in enumerate(data):
        y = y_start - (i * y_step)
        
        # Color gradient: hardest schedule = warm red/brown, easiest = dark slate
        # Normalize SOS to 0-1 range
        norm = (team['SOS_WinPct'] - sos_min) / sos_range
        
        # Create a warm gradient: hard = #8B4513 (saddle brown), easy = #1e293b (dark slate)
        r = int(0x1e + norm * (0xC0 - 0x1e))
        g = int(0x29 + norm * (0x60 - 0x29))
        b = int(0x3b + norm * (0x30 - 0x3b))
        row_color = f'#{r:02x}{g:02x}{b:02x}'
        
        # Row background
        bg = patches.Rectangle((0.03, y - 0.017), 0.94, 0.034,
                                facecolor=row_color, alpha=0.75, zorder=0)
        ax.add_patch(bg)
        
        # Row border (subtle)
        border = patches.Rectangle((0.03, y - 0.017), 0.94, 0.034,
                                    edgecolor='#334155', facecolor='none',
                                    linewidth=0.5, zorder=1)
        ax.add_patch(border)
        
        # Team Logo
        try:
            add_logo(ax, team['Team'], col_logo, y, zoom=0.35)
        except:
            pass
        
        # Team Full Name
        full_name = CODE_TO_FULL_NAME.get(team['Team'], team['Team'])
        ax.text(col_team, y, full_name, ha='left', va='center', fontsize=13,
                color='white', fontweight='bold', zorder=2)
        
        # SOS value (as percentage)
        sos_pct = team['SOS_WinPct'] * 100
        # Color the SOS text: brighter for harder schedules
        if sos_pct > 55:
            sos_color = '#fbbf24'  # Gold/amber for very hard
        elif sos_pct > 50:
            sos_color = '#f8fafc'  # White for above average
        else:
            sos_color = '#94a3b8'  # Muted for easy
        
        ax.text(col_sos, y, f"{sos_pct:.2f}%", ha='center', va='center', fontsize=14,
                color=sos_color, fontweight='bold', zorder=2)
        
        # Team Win%
        win_pct = team['Team_WinPct'] * 100
        if win_pct >= 60:
            wp_color = '#22c55e'  # Green for strong teams
        elif win_pct >= 50:
            wp_color = '#f8fafc'  # White for average
        else:
            wp_color = '#ef4444'  # Red for struggling
        
        ax.text(col_winpct, y, f"{win_pct:.2f}%", ha='center', va='center', fontsize=14,
                color=wp_color, fontweight='bold', zorder=2)
    
    # Set limits
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.02, 1.0)
    
    # Save
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'remaining_sos{round_suffix}.png'
    
    plt.tight_layout()
    plt.savefig(outfile, dpi=200, bbox_inches='tight', facecolor='#0f172a')
    print(f"Table saved to {outfile}!")


if __name__ == '__main__':
    create_sos_table()
