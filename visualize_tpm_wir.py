from season_config import season_label
import pandas as pd
from chart_utils import ratings_path
import matplotlib.pyplot as plt
from adjustText import adjust_text

def create_tpm_wir_chart():
    # Load both datasets
    tpm_path = ratings_path('tpm_ratings')
    if not tpm_path:
        print("No tpm_ratings for this round yet - skipping TPM vs WIR chart.")
        return
    wir_path = ratings_path('wir_ratings')
    if not wir_path:
        print("No wir_ratings for this round yet - skipping TPM vs WIR chart.")
        return
    tpm_df = pd.read_json(tpm_path)
    wir_df = pd.read_json(wir_path)
    
    # Merge on player code
    df = pd.merge(tpm_df, wir_df, on='player.code', suffixes=('_tpm', '_wir'))
    
    # Filter for players playing real minutes
    df = df[(df['mins_played_tpm'] >= 15) & (df['gamesPlayed_tpm'] >= 15)].copy()
    
    # Setup plot
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#161b22')
    
    # Medians to divide into quadrants
    med_tpm = df['TPM_40'].median()
    med_wir = df['WIR_40'].median()
    
    # Quadrant lines
    ax.axhline(med_wir, color='#30363d', linestyle='--', zorder=1)
    ax.axvline(med_tpm, color='#30363d', linestyle='--', zorder=1)
    
    # Plot points
    x = df['TPM_40']
    y = df['WIR_40']
    
    # Color based on quadrant
    colors = []
    for _, row in df.iterrows():
        if row['TPM_40'] >= med_tpm and row['WIR_40'] >= med_wir:
            colors.append('#39d353') # Elite (Top Right)
        elif row['TPM_40'] < med_tpm and row['WIR_40'] < med_wir:
            colors.append('#f85149') # Poor (Bottom Left)
        elif row['TPM_40'] >= med_tpm and row['WIR_40'] < med_wir:
            colors.append('#58a6ff') # Glue Guys (High TPM, Low WIR)
        else:
            colors.append('#d2a8ff') # Empty Stats (Low TPM, High WIR)
            
    ax.scatter(x, y, color=colors, s=120, edgecolors='#161b22', linewidths=1.5, zorder=5, alpha=0.9)
    
    # Quadrant Labels
    ax.text(x.max() - 1, y.max() - 1, 'THE SUPERSTARS\n(High Impact & High Efficiency)', 
            fontsize=12, color='#39d353', ha='right', va='top', fontweight='bold', alpha=0.6)
    
    ax.text(x.min() + 1, y.max() - 1, 'EMPTY STATS?\n(Great Stats, Bad Team Impact)', 
            fontsize=12, color='#d2a8ff', ha='left', va='top', fontweight='bold', alpha=0.6)
            
    ax.text(x.max() - 1, y.min() + 1, 'GLUE GUYS / DEFENDERS\n(Low Stats, Huge Team Impact)', 
            fontsize=12, color='#58a6ff', ha='right', va='bottom', fontweight='bold', alpha=0.6)
            
    # Labels for key players
    texts = []
    # Sort for top players in each quadrant
    elites = df[(df['TPM_40'] > med_tpm) & (df['WIR_40'] > med_wir)].sort_values(by=['TPM_40', 'WIR_40'], ascending=[False, False]).head(8)
    empty = df[(df['TPM_40'] < 0) & (df['WIR_40'] > med_wir)].sort_values(by='WIR_40', ascending=False).head(5)
    glue = df[(df['TPM_40'] > med_tpm + 2) & (df['WIR_40'] < med_wir)].sort_values(by='TPM_40', ascending=False).head(5)
    worst = df[(df['TPM_40'] < -6)].sort_values(by='TPM_40', ascending=True).head(4)
    
    # Specific interesting players (like Vezenkov)
    vz = df[df['player.name_tpm'].str.contains('VEZEN', case=False, na=False)]
    
    to_label = pd.concat([elites, empty, glue, worst, vz]).drop_duplicates(subset=['player.code'])
    
    for _, row in to_label.iterrows():
        name_parts = row['player.name_tpm'].split(',')
        clean_name = f"{name_parts[1].strip().title()} {name_parts[0].strip().title()}" if len(name_parts) == 2 else row['player.name_tpm'].title()
        team = str(row['player.team.code_tpm'])
        label = f"{clean_name} ({team})"
        texts.append(ax.text(row['TPM_40'], row['WIR_40'], label, fontsize=8, color='#e6edf3', fontweight='bold'))
    
    adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle='-', color='#8b949e', alpha=0.6, lw=0.8),
                force_text=(2.0, 2.5), force_points=(1.5, 2.0), expand=(2.5, 2.5),
                ensure_inside_axes=False, time_lim=5)
    
    # Formatting
    ax.set_title(f"True Plus-Minus (TPM) vs Weighted Impact Rating (WIR)\nEuroleague {season_label()} Season (>15 MPG)", 
                 fontsize=16, color='#e6edf3', fontweight='bold', pad=20)
    ax.set_xlabel('True Plus-Minus per 40 mins (Team Point Differential)', fontsize=12, color='#8b949e', fontweight='bold')
    ax.set_ylabel('Weighted Impact Rating per 40 (Individual Efficiency)', fontsize=12, color='#8b949e', fontweight='bold')
    
    ax.tick_params(colors='#8b949e')
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.15, color='#30363d')
    
    plt.tight_layout()
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'tpm_vs_wir_quadrants{round_suffix}.png'
    plt.savefig(outfile, dpi=150, facecolor=fig.get_facecolor(), bbox_inches='tight')
    print(f"Saved {outfile}")

if __name__ == '__main__':
    create_tpm_wir_chart()
