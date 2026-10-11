import json
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import os

def plot_clutch_ts_2025():
    # Load Data
    files = ['clutch_stats_2025_2025.json', 'clutch_stats_multiple_seasons.json']
    data_file = None
    for f in files:
        if os.path.exists(f):
            data_file = f
            break
            
    if not data_file:
        print("Data file not found. Please run generate_clutch_data.py first.")
        return

    with open(data_file, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
        
    # Get 2025 Data
    season_data = full_data.get("2025", [])
    if not season_data:
        print("No data found for season 2025.")
        return
        
    print(f"Loaded {len(season_data)} players for season 2025.")
    
    # Process Data
    processed_players = []
    
    for p in season_data:
        player = p.get('Player')
        team = p.get('Team')
        points = p.get('ClutchPoints', 0)
        fga = p.get('ClutchFGA', 0)
        fta = p.get('ClutchFTA', 0)
        
        # Calculate TS%
        # formula: PTS / (2 * (FGA + 0.44 * FTA))
        try:
            ts_denom = 2 * (fga + 0.44 * fta)
            if ts_denom > 0:
                ts_pct = (points / ts_denom) * 100
            else:
                ts_pct = 0
        except:
            ts_pct = 0
            
        # Filter: Only players with significant attempts?
        # Let's say at least 10 points or 5 FGA to avoid noise
        if points >= 10: 
            processed_players.append({
                'Player': player,
                'Team': team,
                'ClutchPoints': points,
                'TS%': ts_pct
            })
            
    if not processed_players:
        print("No players met the criteria.")
        return

    df = pd.DataFrame(processed_players)
    
    # Plotting
    plt.figure(figsize=(14, 10))
    sns.set_style("whitegrid")
    
    # Create scatterplot
    # Hue by Team if possible, but might be too many colors. 
    # Let's just use a nice color and label top players.
    
    scatter = sns.scatterplot(
        data=df, 
        x='ClutchPoints', 
        y='TS%', 
        hue='Team', # Try mapping if not too cluttered
        s=150, 
        alpha=0.8,
        palette='tab20' # Standard qualitative palette
    )
    
    # Create texts for all players
    texts = []
    annotated_players = df.sort_values(['ClutchPoints'], ascending=False)
    
    # We want to annotate EVERYONE over the threshold, as requested.
    for _, row in annotated_players.iterrows():
        # Optional: Add small offset or formatting
        t = plt.text(
            row['ClutchPoints'], 
            row['TS%'], 
            row['Player'], 
            fontsize=8, 
            alpha=0.8
        )
        texts.append(t)
        
    # Use adjust_text to repel labels
    from adjustText import adjust_text
    adjust_text(
        texts,
        arrowprops=dict(arrowstyle='-', color='gray', alpha=0.5),
        expand_points=(1.2, 1.2),
        force_text=(0.5, 0.5)
    )

    # Titles and Labels
    plt.title('Clutch Scoring Efficiency: Points vs True Shooting % (2025-26)', fontsize=16, weight='bold')
    plt.xlabel('Total Clutch Points', fontsize=12)
    plt.ylabel('True Shooting Percentage (TS%)', fontsize=12)
    
    # Lines for averages?
    avg_ts = df['TS%'].mean()
    avg_pts = df['ClutchPoints'].mean()
    
    plt.axhline(avg_ts, color='gray', linestyle='--', alpha=0.5, label=f'Avg TS%: {avg_ts:.1f}%')
    plt.axvline(avg_pts, color='gray', linestyle='--', alpha=0.5, label=f'Avg Pts: {avg_pts:.1f}')
    
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    
    plt.tight_layout()
    
    output_file = 'clutch_ts_2025.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Chart saved to {output_file}")
    plt.close()

if __name__ == "__main__":
    plot_clutch_ts_2025()
