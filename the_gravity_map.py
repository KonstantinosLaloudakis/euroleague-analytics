import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap, PowerNorm
import os

# --- Configuration ---
SEASON = 2025
GRIDSIZE = 25
MIN_SHOTS_PER_HEX = 3  # Min shots in a hex cell to annotate FG%

# --- Euroleague Team Names ---
# NOTE: Some codes change across seasons (e.g. Panathinaikos = PAM in 2022-23, PAN in 2024-25)
# This dict covers the most common/recent usage.
TEAM_NAMES = {
    "ULK": "Fenerbahce", "BAR": "FC Barcelona", "OLY": "Olympiacos",
    "PAR": "Partizan", "BAS": "Baskonia", "MAD": "Real Madrid",
    "MCO": "AS Monaco", "MIL": "EA7 Milano", "PAO": "Panathinaikos",
    "BAY": "Bayern Munich", "BER": "Alba Berlin", "ZAL": "Zalgiris",
    "MAC": "Maccabi Tel Aviv", "VIR": "Virtus Bologna", "ASV": "Anadolu Efes",
    "RED": "Crvena Zvezda", "IST": "Anadolu Efes",
    "TEL": "Maccabi Tel Aviv", "PRS": "Paris Basketball",
    "MUN": "Bayern Munich", "DUB": "Dubai", "BES": "Besiktas", "HTA": "Hapoel Tel Aviv",
    "PAM": "Valencia Basket", "PAN": "Panathinaikos",
}

# Season-specific overrides for teams whose codes change
TEAM_NAME_OVERRIDES = {
    # PAN is always Panathinaikos; PAM varies by season
}


def get_team_name(code, season=None):
    """Return full team name for a code, with optional season-specific override."""
    if season and season in TEAM_NAME_OVERRIDES:
        if code in TEAM_NAME_OVERRIDES[season]:
            return TEAM_NAME_OVERRIDES[season][code]
    return TEAM_NAMES.get(code, code)


def classify_shot_zone(row):
    """Classify a shot into Paint, Mid-Range, or 3PT based on coordinates and action."""
    x, y = row['COORD_X'], row['COORD_Y']
    action = str(row['ID_ACTION'])
    dist = np.sqrt(x**2 + y**2)
    
    # Paint: inside the painted area (including restricted area)
    in_paint_width = -245 <= x <= 245
    in_paint_length = y <= 422.5
    if dist <= 125 or (in_paint_width and in_paint_length):
        return 'Paint'
    
    # 3PT: action-based or distance-based
    is_3pt = '3FG' in action
    is_corner_3 = abs(x) >= 660 and y <= 300
    is_arc_3 = dist >= 675
    if is_3pt or is_corner_3 or is_arc_3:
        return '3PT'
    
    return 'Mid-Range'


def load_shot_data(season):
    """Load cached shot data for a given season."""
    cache_file = f"shot_data_{season}_{season}.csv"
    if not os.path.exists(cache_file):
        print(f"Cache file {cache_file} not found!")
        return pd.DataFrame()
    
    print(f"Loading {cache_file}...")
    df = pd.read_csv(cache_file, low_memory=False)
    
    # Filter to actual shot attempts (exclude free throws — no coordinates)
    df = df[df['ID_ACTION'].str.contains('2FG|3FG', na=False)].copy()
    
    # Ensure coordinates are numeric
    df['COORD_X'] = pd.to_numeric(df['COORD_X'], errors='coerce')
    df['COORD_Y'] = pd.to_numeric(df['COORD_Y'], errors='coerce')
    df = df.dropna(subset=['COORD_X', 'COORD_Y'])
    
    # Add make/miss column
    df['MADE'] = df['ID_ACTION'].str.contains('2FGM|3FGM', na=False).astype(int)
    
    # Classify zones
    df['SHOT_ZONE'] = df.apply(classify_shot_zone, axis=1)
    
    print(f"Loaded {len(df)} shot attempts for {season}.")
    return df


def draw_half_court(ax, color='#333333', lw=1.5):
    """Draw a Euroleague half-court diagram."""
    # Baseline
    ax.add_line(plt.Line2D([-750, 750], [-157.5, -157.5], color=color, linewidth=lw))
    
    # Backboard
    ax.add_line(plt.Line2D([-90, 90], [-37.5, -37.5], color=color, linewidth=lw))
    
    # Paint
    ax.plot([-245, -245], [-157.5, 422.5], color=color, linewidth=lw)
    ax.plot([245, 245], [-157.5, 422.5], color=color, linewidth=lw)
    ax.plot([-245, 245], [422.5, 422.5], color=color, linewidth=lw)
    
    # Restricted Area arc
    ax.add_patch(patches.Arc((0, 0), 250, 250, theta1=0, theta2=180,
                              linewidth=lw, color=color))
    
    # Basket
    ax.add_patch(patches.Circle((0, 0), radius=22.5, linewidth=lw,
                                 color=color, fill=False))
    
    # 3PT line
    corner_x = 660
    intersection_y = np.sqrt(675**2 - corner_x**2)
    ax.plot([corner_x, corner_x], [-157.5, intersection_y], color=color, linewidth=lw)
    ax.plot([-corner_x, -corner_x], [-157.5, intersection_y], color=color, linewidth=lw)
    theta = np.degrees(np.arctan2(intersection_y, corner_x))
    ax.add_patch(patches.Arc((0, 0), 1350, 1350, theta1=theta, theta2=180-theta,
                              linewidth=lw, color=color))


def plot_team_heatmap(df, team, season, ax=None, show_colorbar=True):
    """
    Create a hexbin heatmap of shot attempts for a single team.
    Color intensity = shot frequency. 
    """
    team_df = df[df['TEAM'] == team]
    
    if team_df.empty:
        print(f"No shot data found for team '{team}'.")
        return
    
    total_shots = len(team_df)
    total_makes = team_df['MADE'].sum()
    team_fg_pct = total_makes / total_shots * 100 if total_shots > 0 else 0
    
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(10, 9))
        fig.patch.set_facecolor('#0E1117')
    
    ax.set_facecolor('#0E1117')
    
    # Draw court (light lines on dark background)
    draw_half_court(ax, color='#AAAAAA', lw=1.2)
    
    # Brightened colormap with power normalization so mid-range areas are visible
    colors_cmap = ['#2a1a4e', '#6a3d9a', '#e6b800', '#ff6600', '#ff1a1a']
    cmap = LinearSegmentedColormap.from_list('shot_heat', colors_cmap, N=256)
    
    # Hexbin with PowerNorm (gamma < 1 brightens low values)
    hb = ax.hexbin(
        team_df['COORD_X'], team_df['COORD_Y'],
        gridsize=GRIDSIZE,
        cmap=cmap,
        norm=PowerNorm(gamma=0.5),
        mincnt=1,
        extent=[-800, 800, -200, 1000],
        alpha=0.85,
        edgecolors='none',
        zorder=2
    )
    
    if show_colorbar:
        cb = plt.colorbar(hb, ax=ax, shrink=0.6, pad=0.02)
        cb.set_label('Shot Attempts', color='white', fontsize=10)
        cb.ax.yaxis.set_tick_params(color='white')
        plt.setp(plt.getp(cb.ax.axes, 'yticklabels'), color='white')
    
    # Calculate FG% per hex cell and annotate high-volume cells
    # Get hex cell data
    offsets = hb.get_offsets()
    counts = hb.get_array()
    
    if len(offsets) > 0 and len(counts) > 0:
        # For FG% we need to create a second hexbin for makes only
        makes_df = team_df[team_df['MADE'] == 1]
        if not makes_df.empty:
            hb_makes = ax.hexbin(
                makes_df['COORD_X'], makes_df['COORD_Y'],
                gridsize=GRIDSIZE,
                mincnt=0,
                extent=[-800, 800, -200, 1000],
                alpha=0,  # Invisible — just for counting
                zorder=1
            )
            make_counts = hb_makes.get_array()
            make_offsets = hb_makes.get_offsets()
            
            # Build a lookup: (rounded offset) -> make count
            make_lookup = {}
            for i, off in enumerate(make_offsets):
                if i < len(make_counts):
                    key = (round(off[0], 1), round(off[1], 1))
                    make_lookup[key] = make_counts[i]
            
            # Annotate cells with enough shots
            for i, off in enumerate(offsets):
                if i < len(counts) and counts[i] >= MIN_SHOTS_PER_HEX:
                    key = (round(off[0], 1), round(off[1], 1))
                    makes = make_lookup.get(key, 0)
                    fg_pct = makes / counts[i] * 100 if counts[i] > 0 else 0
                    
                    # Only annotate cells with meaningful shot volume
                    if counts[i] >= 8:
                        color_text = '#00ff88' if fg_pct >= 45 else '#ffffff' if fg_pct >= 35 else '#ff6666'
                        ax.text(off[0], off[1], f"{fg_pct:.0f}%",
                                ha='center', va='center', fontsize=6,
                                color=color_text, fontweight='bold',
                                zorder=10, alpha=0.9)
            
            # Remove the invisible hexbin
            hb_makes.remove()
    
    # Shot distribution breakdown
    zone_counts = team_df['SHOT_ZONE'].value_counts()
    paint_pct = zone_counts.get('Paint', 0) / total_shots * 100
    mid_pct = zone_counts.get('Mid-Range', 0) / total_shots * 100
    three_pct = zone_counts.get('3PT', 0) / total_shots * 100
    
    breakdown = f"Paint: {paint_pct:.0f}%  |  Mid-Range: {mid_pct:.0f}%  |  3PT: {three_pct:.0f}%"
    ax.text(0, -130, breakdown, ha='center', va='center', fontsize=9,
            color='#cccccc', fontweight='bold', zorder=10,
            bbox=dict(facecolor='#1a1a2e', alpha=0.8, edgecolor='#444444',
                      boxstyle='round,pad=0.4'))
    
    # Title
    team_name = get_team_name(team, season)
    ax.set_title(f"{team_name} Shot Chart — {season}\n"
                 f"{total_shots} Attempts | {team_fg_pct:.1f}% FG",
                 color='white', fontsize=14, fontweight='bold', pad=15)
    
    ax.set_xlim(-800, 800)
    ax.set_ylim(-200, 1000)
    ax.set_aspect('equal')
    ax.axis('off')
    
    if standalone:
        plt.tight_layout()
        filename = f"gravity_map_{team}_{season}.png"
        plt.savefig(filename, dpi=150, bbox_inches='tight',
                    facecolor='#0E1117', edgecolor='none')
        plt.close()
        print(f"Saved {filename}")


def plot_comparison(df, team1, team2, season):
    """
    Generate a side-by-side comparison of two teams' shot charts.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 9))
    fig.patch.set_facecolor('#0E1117')
    
    plot_team_heatmap(df, team1, season, ax=ax1, show_colorbar=False)
    plot_team_heatmap(df, team2, season, ax=ax2, show_colorbar=False)
    
    name1, name2 = get_team_name(team1, season), get_team_name(team2, season)
    fig.suptitle(f"The Gravity Map: {name1} vs {name2} — {season}",
                 color='white', fontsize=18, fontweight='bold', y=0.98)
    
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    filename = f"gravity_map_{team1}_vs_{team2}_{season}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight',
                facecolor='#0E1117', edgecolor='none')
    plt.close()
    print(f"Saved {filename}")


def plot_league_heatmap(df, season):
    """
    Generate a league-wide heatmap showing where all teams shoot from.
    """
    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor('#0E1117')
    ax.set_facecolor('#0E1117')
    
    draw_half_court(ax, color='#AAAAAA', lw=1.2)
    
    colors_cmap = ['#2a1a4e', '#6a3d9a', '#e6b800', '#ff6600', '#ff1a1a']
    cmap = LinearSegmentedColormap.from_list('league_heat', colors_cmap, N=256)
    
    total_shots = len(df)
    total_makes = df['MADE'].sum()
    lg_fg_pct = total_makes / total_shots * 100 if total_shots > 0 else 0
    
    hb = ax.hexbin(
        df['COORD_X'], df['COORD_Y'],
        gridsize=GRIDSIZE,
        cmap=cmap,
        norm=PowerNorm(gamma=0.5),
        mincnt=1,
        extent=[-800, 800, -200, 1000],
        alpha=0.85,
        edgecolors='none',
        zorder=2
    )
    
    cb = plt.colorbar(hb, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label('Shot Attempts', color='white', fontsize=10)
    cb.ax.yaxis.set_tick_params(color='white')
    plt.setp(plt.getp(cb.ax.axes, 'yticklabels'), color='white')
    
    # Shot distribution breakdown
    zone_counts = df['SHOT_ZONE'].value_counts()
    paint_pct = zone_counts.get('Paint', 0) / total_shots * 100
    mid_pct = zone_counts.get('Mid-Range', 0) / total_shots * 100
    three_pct = zone_counts.get('3PT', 0) / total_shots * 100
    
    breakdown = f"Paint: {paint_pct:.0f}%  |  Mid-Range: {mid_pct:.0f}%  |  3PT: {three_pct:.0f}%"
    ax.text(0, -130, breakdown, ha='center', va='center', fontsize=10,
            color='#cccccc', fontweight='bold', zorder=10,
            bbox=dict(facecolor='#1a1a2e', alpha=0.8, edgecolor='#444444',
                      boxstyle='round,pad=0.4'))
    
    ax.set_title(f"Euroleague Shot Distribution — {season}\n"
                 f"{total_shots:,} Attempts | {lg_fg_pct:.1f}% FG (League)",
                 color='white', fontsize=14, fontweight='bold', pad=15)
    
    ax.set_xlim(-800, 800)
    ax.set_ylim(-200, 1000)
    ax.set_aspect('equal')
    ax.axis('off')
    
    plt.tight_layout()
    filename = f"gravity_map_league_{season}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight',
                facecolor='#0E1117', edgecolor='none')
    plt.close()
    print(f"Saved {filename}")


def main():
    df = load_shot_data(SEASON)
    if df.empty:
        print("No data loaded. Exiting.")
        return
    
    # 1. League-wide heatmap
    print("\n--- Generating League-Wide Heatmap ---")
    plot_league_heatmap(df, SEASON)
    
    # 2. Individual team heatmaps (top 4 teams by shot volume)
    print("\n--- Generating Individual Team Heatmaps ---")
    team_counts = df['TEAM'].value_counts()
    top_teams = team_counts.head(4).index.tolist()
    print(f"Top 4 teams by volume: {top_teams}")
    
    for team in top_teams:
        plot_team_heatmap(df, team, SEASON)
    
    # 3. Head-to-head comparison (top 2 teams)
    if len(top_teams) >= 2:
        print(f"\n--- Generating Comparison: {top_teams[0]} vs {top_teams[1]} ---")
        plot_comparison(df, top_teams[0], top_teams[1], SEASON)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
