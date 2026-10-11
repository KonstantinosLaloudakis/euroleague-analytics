from season_config import season_label
import pandas as pd
from chart_utils import ratings_path
import matplotlib.pyplot as plt
import seaborn as sns

def create_wpa_chart():
    wpa_path = ratings_path('wpa_ratings')
    if not wpa_path:
        print("No wpa_ratings for this round yet - skipping WPA chart.")
        return
    df = pd.read_json(wpa_path)
    
    # Convert from percentage points to "Wins Added"
    df['Wins_Added'] = df['Action_WPA'] / 100.0
    
    top15 = df.head(15).copy()
    
    # Setup plot
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#161b22')
    
    sns.barplot(
        x='Wins_Added', 
        y='Player', 
        data=top15,
        palette='magma',
        ax=ax
    )
    
    # Add values to the ends of the bars
    for i, p in enumerate(ax.patches):
        width = p.get_width()
        team = top15.iloc[i]['Team']
        ax.text(width + 0.1, p.get_y() + p.get_height()/2.,
                f"+{width:.1f} Wins ({team})",
                va='center', fontsize=10, color='#e6edf3', fontweight='bold')
                
    # Formatting
    ax.set_title(f"Action Win Probability Added (WPA) Leaders\nEuroleague {season_label()} Season", 
                 fontsize=16, color='#e6edf3', fontweight='bold', pad=20)
    ax.set_xlabel('Total Expected Wins Added (via Individual Actions)', fontsize=12, color='#8b949e', fontweight='bold')
    ax.set_ylabel('')
    
    ax.tick_params(colors='#e6edf3', labelsize=10)
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.15, color='#30363d')
    
    # Note explaining the metric
    fig.text(0.5, 0.01, 
             "Metric evaluates the exact Win Probability shift (Score & Time Remaining) caused by a player's direct actions.", 
             ha='center', fontsize=9, color='#8b949e', style='italic')
             
    plt.tight_layout()
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'wpa_leaders{round_suffix}.png'
    plt.savefig(outfile, dpi=150, facecolor=fig.get_facecolor(), bbox_inches='tight')
    print(f"Saved {outfile}")

if __name__ == '__main__':
    create_wpa_chart()
