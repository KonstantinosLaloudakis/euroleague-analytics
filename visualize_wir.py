import pandas as pd
from chart_utils import ratings_path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def create_wir_visualization():
    # Load rankings
    wir_path = ratings_path('wir_ratings')
    if not wir_path:
        print("No wir_ratings for this round yet - skipping WIR chart.")
        return
    df = pd.read_json(wir_path)
    
    # Visualization
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#161b22')
    
    # Filter to top 150 WIR or top 150 PIR for readability
    plot_df = df[(df['WIR_Rank'] <= 150) | (df['PIR_Rank'] <= 150)].copy()
    
    x = plot_df['PIR_40']
    y = plot_df['WIR_40']
    
    # Diagonal line where WIR = PIR
    min_val = min(min(x), min(y)) - 2
    max_val = max(max(x), max(y)) + 2
    ax.plot([min_val, max_val], [min_val, max_val], '--', color='#30363d', linewidth=2, zorder=1)
    
    # Fill regions
    ax.fill_between([min_val, max_val], [min_val, max_val], [max_val, max_val], 
                     alpha=0.08, color='#39d353', zorder=0)  # WIR > PIR (Underrated)
    ax.fill_between([min_val, max_val], [min_val, min_val], [min_val, max_val], 
                     alpha=0.08, color='#f85149', zorder=0)  # WIR < PIR (Overrated)
    
    # Scatter points
    luck = plot_df['WIR_40'] - plot_df['PIR_40']
    sizes = 80 + abs(luck) * 20
    colors = ['#39d353' if l > 0.5 else '#f85149' if l < -0.5 else '#8b949e' for l in luck]
    
    ax.scatter(x, y, s=sizes, c=colors, edgecolors='#161b22', linewidths=1.5, zorder=5, alpha=0.8)
    
    # Highlight specific extreme players (Risers and Fallers)
    from adjustText import adjust_text
    texts = []
    
    # Label top 5 risers and top 5 fallers in the dataset
    risers = df.sort_values('Rank_Diff', ascending=False).head(8)
    fallers = df.sort_values('Rank_Diff', ascending=True).head(8)
    legends = df.sort_values('WIR_40', ascending=False).head(5)
    
    to_label = pd.concat([risers, fallers, legends]).drop_duplicates(subset=['player.name'])
    
    for _, row in to_label.iterrows():
        # Clean name format "LASTNAME, FIRSTNAME"
        name_parts = row['player.name'].split(',')
        if len(name_parts) == 2:
            clean_name = f"{name_parts[1].strip().capitalize()} {name_parts[0].strip().capitalize()}"
        else:
            clean_name = row['player.name'].capitalize()
            
        texts.append(ax.text(row['PIR_40'], row['WIR_40'], clean_name, 
                             fontsize=8, color='#e6edf3', fontweight='bold'))
    
    # Region labels
    ax.text(min_val + 2, max_val - 2, 'UNDERRATED BY PIR\n(High Efficiency / Defense)', 
            fontsize=12, color='#39d353', ha='left', va='top', fontweight='bold')
    ax.text(max_val - 2, min_val + 2, 'OVERRATED BY PIR\n(Inefficient / Volume)', 
            fontsize=12, color='#f85149', ha='right', va='bottom', fontweight='bold')
            
    # Labels and title
    ax.set_xlabel('PIR per 40 Minutes', fontsize=13, color='#e6edf3', fontweight='bold')
    ax.set_ylabel('Weighted Impact Rating (WIR) per 40', fontsize=13, color='#e6edf3', fontweight='bold')
    ax.set_title('WIR vs PIR: Finding the True Impact Players\n(All-Time Euroleague Data)', 
                 fontsize=16, color='#e6edf3', fontweight='bold', pad=20)
                 
    # Style
    ax.tick_params(colors='#8b949e')
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.15, color='#30363d')
    ax.set_xlim(min_val, max_val)
    ax.set_ylim(min_val, max_val)
    
    adjust_text(texts, ax=ax, 
                arrowprops=dict(arrowstyle='-', color='#8b949e', alpha=0.5, lw=0.7),
                force_text=(1.5, 2.0),
                force_points=(1.0, 1.5),
                expand=(2.0, 2.0))
                
    # Subtitle with methodology
    fig.text(0.5, 0.02, 
             'WIR down-weights points/rebounds, heavily penalizes inefficiency & turnovers, and rewards steals/assists.',
             ha='center', fontsize=9, color='#8b949e', fontstyle='italic')
             
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.07)
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'wir_vs_pir{round_suffix}.png'
    plt.savefig(outfile, dpi=150, facecolor=fig.get_facecolor())
    print(f"Visualization saved to {outfile}")

if __name__ == '__main__':
    create_wir_visualization()
