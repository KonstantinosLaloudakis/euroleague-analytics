import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from chart_utils import add_logo
from chart_utils import ratings_path

def create_playoff_matrix():
    print("Generating Playoff Matrix Visualization...")
    
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = ratings_path('monte_carlo_results')
    if in_file is None:
        print("No monte_carlo_results for this round yet - skipping playoff matrix.")
        return
        
    with open(in_file, 'r') as f:
        data = json.load(f)
        
    # Data is sorted in JSON
    # data.sort(key=lambda x: (x['Top6_Pct'], x['Top10_Pct']), reverse=True)
    
    fig, ax = plt.subplots(figsize=(13, 16)) 
    fig.patch.set_facecolor('#0f172a') # Deep Slate
    ax.set_facecolor('#0f172a')
    
    ax.axis('off')
    
    # Titling
    ax.text(0.5, 0.97, "ADVANCED PLAYOFF PROBABILITY MATRIX", ha='center', va='center', fontsize=26, color='#fbbf24', fontweight='bold', fontname='Impact')
    ax.text(0.5, 0.94, "10,000 Simulations · ML Win Probability Model (Adj Net + Elo)", ha='center', va='center', fontsize=14, color='#94a3b8', style='italic')
    
    # Grid Layout X Coordinates
    cols = {
        'Logo': 0.12,
        'Team': 0.22,
        'xWINS': 0.36,
        'Top 4 (HCA)': 0.55,
        'Top 6 (Playoffs)': 0.73,
        'Top 10 (Play-In)': 0.91
    }
    
    # Table Headers
    y_header = 0.89
    for title, x in cols.items():
        if title == 'Logo': continue
        ha = 'center' if title in ['xWINS', 'Top 4 (HCA)', 'Top 6 (Playoffs)', 'Top 10 (Play-In)'] else 'left'
        ax.text(x, y_header, title.upper(), ha=ha, va='center', fontsize=12, color='white', fontweight='bold', fontname='Montserrat', alpha=0.9)
        
    # Horizontal line under headers
    ax.plot([0.05, 1.0], [y_header - 0.02, y_header - 0.02], color='#334155', linewidth=2)
    
    # Rows iteration
    y_start = 0.84
    y_step = 0.045
    
    for i, row in enumerate(data):
        y = y_start - (i * y_step)
        
        # Zebra striping background for readability
        if i % 2 == 0:
            bg_rect = patches.Rectangle((0.05, y - 0.02), 0.95, 0.04, facecolor='#1e293b', alpha=0.5, zorder=0)
            ax.add_patch(bg_rect)
        
        # Add Logo
        add_logo(ax, row['Team'], cols['Logo'], y, zoom=0.45)
        
        # Team Acronym
        ax.text(cols['Team'], y, row['Team'], ha='left', va='center', fontsize=15, color='white', fontweight='bold')
        
        # xWins (formatted as integer to reflect a realistic final record)
        ax.text(cols['xWINS'], y, f"{int(round(row['Avg_Wins']))}", ha='center', va='center', fontsize=15, color='#cbd5e1')
        
        # The Three Probability Columns (The Heatmap)
        for col_name, pct in [
            ('Top 4 (HCA)', row['Top4_Pct']),
            ('Top 6 (Playoffs)', row['Top6_Pct']),
            ('Top 10 (Play-In)', row['Top10_Pct'])
        ]:
            x = cols[col_name]
            
            if pct > 0:
                # Dynamic Opacity strictly based on probability (0.1 to 0.7)
                alpha = 0.15 + (pct / 100) * 0.65
                
                # Base Colors updated for Top 4/6/10
                if col_name == 'Top 4 (HCA)':
                    color = '#8b5cf6' # Purple for Premium (HCA)
                elif col_name == 'Top 6 (Playoffs)':
                    color = '#22c55e' # Green for Playoffs
                else:
                    color = '#38bdf8' # Blue for Play-In
                
                # Draw colored background box
                rect = patches.Rectangle((x - 0.075, y - 0.015), 0.15, 0.03, facecolor=color, alpha=alpha, zorder=1)
                ax.add_patch(rect)
                
                # Optional: draw a solid left border on the box for aesthetic punch
                border = patches.Rectangle((x - 0.075, y - 0.015), 0.005, 0.03, facecolor=color, alpha=1.0, zorder=2)
                ax.add_patch(border)
                
            # Formatting the text
            # Bold and bright if high probability, muted if low, invisible if 0
            if pct >= 50:
                weight = 'bold'
                txt_color = 'white'
            elif pct > 0:
                weight = 'normal'
                txt_color = '#cbd5e1'
            else:
                weight = 'normal'
                txt_color = '#334155' # Very dark gray for zero
                
            display_text = f"{pct:.1f}%" if pct > 0 else "-"
                
            ax.text(x, y, display_text, ha='center', va='center', fontsize=14, color=txt_color, fontweight=weight, zorder=3)
            
    # Set limits clearly
    ax.set_xlim(0, 1.05)
    ax.set_ylim(-0.02, 1)
    
    # Save Output
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'playoff_matrix{round_suffix}.png'
    
    plt.tight_layout()
    plt.savefig(outfile, dpi=200, bbox_inches='tight', facecolor='#0f172a')
    print(f"Poster saved to {outfile}!")

if __name__ == "__main__":
    create_playoff_matrix()
