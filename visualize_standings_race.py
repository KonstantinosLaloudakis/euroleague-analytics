"""
Standings Race Animation.
Creates an animated GIF showing the standings evolve round by round.
Bar chart races where each frame = one round's cumulative standings.
"""

from season_config import season_label
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from PIL import Image
import os
from chart_utils import add_logo


CODE_TO_SHORT = {
    'BER': 'Berlin', 'IST': 'Efes', 'MCO': 'Monaco',
    'BAS': 'Baskonia', 'RED': 'Zvezda',
    'MIL': 'Milan', 'BAR': 'Barcelona', 'MUN': 'Bayern',
    'ULK': 'Fenerbahce', 'ASV': 'ASVEL',
    'TEL': 'Maccabi', 'OLY': 'Olympiacos',
    'PAN': 'Panathinaikos', 'PAR': 'Partizan',
    'PRS': 'Paris', 'MAD': 'R. Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia', 'VIR': 'Virtus',
    'ZAL': 'Zalgiris', 'DUB': 'Dubai',
    'HTA': 'Hapoel'
}

TEAM_COLORS = {
    'ULK': '#FFD700', 'OLY': '#CC0000', 'MAD': '#FEBE10',
    'BES': '#9E9E9E',
    'PAM': '#FF6600', 'MCO': '#CC0000', 'BAR': '#A50044',
    'ZAL': '#006633', 'RED': '#CC0000', 'PAN': '#006633',
    'MIL': '#CE2B37', 'BAS': '#003DA5', 'MUN': '#DD0000',
    'HTA': '#FFD700', 'PRS': '#1B365D', 'TEL': '#FFD700',
    'DUB': '#C5B358', 'VIR': '#000000', 'IST': '#00205B',
    'BER': '#F6E500', 'PAR': '#000000', 'ASV': '#006633'
}


def create_standings_race():
    print("Generating Standings Race Animation...")
    
    # Load all games
    with open('mvp_game_results.json', 'r') as f:
        all_games = json.load(f)
    
    played = [g for g in all_games if g['LocalScore'] > 0 and g['RoadScore'] > 0]
    played.sort(key=lambda x: x['GameCode'])
    
    max_code = max(g['GameCode'] for g in played)
    
    # Compute standings at each round (every 10 games ≈ 1 round)
    round_checkpoints = list(range(10, max_code + 1, 10))
    if round_checkpoints[-1] < max_code:
        round_checkpoints.append(max_code)
    
    frames = []
    temp_dir = '/tmp/standings_frames'
    os.makedirs(temp_dir, exist_ok=True)
    
    for frame_idx, cp in enumerate(round_checkpoints):
        round_num = round(cp / 10)
        
        # Compute standings up to this checkpoint
        games_so_far = [g for g in played if g['GameCode'] <= cp]
        
        standings = {}
        for g in games_so_far:
            h, a = g['LocalTeam'], g['RoadTeam']
            for t in (h, a):
                if t not in standings:
                    standings[t] = {'W': 0, 'L': 0}
            if g['LocalScore'] > g['RoadScore']:
                standings[h]['W'] += 1
                standings[a]['L'] += 1
            else:
                standings[a]['W'] += 1
                standings[h]['L'] += 1
        
        # Sort by wins (then by fewest losses as tiebreaker)
        sorted_teams = sorted(standings.keys(), 
                             key=lambda t: (standings[t]['W'], -standings[t]['L']),
                             reverse=True)
        
        # --- Draw Frame ---
        fig, ax = plt.subplots(figsize=(12, 10))
        fig.patch.set_facecolor('#0f172a')
        ax.set_facecolor('#0f172a')
        ax.axis('off')
        
        # Title
        ax.text(0.50, 0.97, f"EUROLEAGUE STANDINGS RACE {season_label()}",
                ha='center', va='center', fontsize=22, color='#fbbf24',
                fontweight='bold')
        ax.text(0.50, 0.94, f"After Round {round_num}",
                ha='center', va='center', fontsize=14, color='#94a3b8',
                fontweight='bold')
        
        num_teams = len(sorted_teams)
        max_wins = max(standings[t]['W'] for t in sorted_teams) if sorted_teams else 1
        
        y_start = 0.88
        row_h = 0.80 / max(num_teams, 1)
        bar_max_width = 0.50
        
        for i, team in enumerate(sorted_teams):
            y = y_start - i * row_h
            w = standings[team]['W']
            l = standings[team]['L']
            
            # Rank
            ax.text(0.03, y, str(i + 1), ha='center', va='center',
                    fontsize=10, color='#64748b', fontweight='bold')
            
            # Logo
            try:
                add_logo(ax, team, 0.07, y, zoom=0.25)
            except:
                pass
            
            # Team name
            name = CODE_TO_SHORT.get(team, team)
            ax.text(0.11, y, name, ha='left', va='center',
                    fontsize=10, color='white', fontweight='bold')
            
            # Record
            ax.text(0.25, y, f"{w}-{l}", ha='center', va='center',
                    fontsize=10, color='#94a3b8', fontweight='bold')
            
            # Bar
            bar_width = (w / max(max_wins, 1)) * bar_max_width
            color = TEAM_COLORS.get(team, '#3b82f6')
            # Make dark colors visible
            if color in ('#000000',):
                color = '#64748b'
            
            bar = patches.FancyBboxPatch(
                (0.32, y - row_h * 0.3), bar_width, row_h * 0.6,
                boxstyle="round,pad=0.003",
                facecolor=color, alpha=0.7, zorder=1
            )
            ax.add_patch(bar)
            
            # Wins count on bar
            if bar_width > 0.03:
                ax.text(0.32 + bar_width - 0.01, y, str(w),
                        ha='right', va='center', fontsize=9,
                        color='white', fontweight='bold', zorder=2)
            
            # Zone indicators
            if i < 4:
                zone_color = '#22c55e'  # HCA
            elif i < 6:
                zone_color = '#3b82f6'  # Playoffs
            elif i < 10:
                zone_color = '#f59e0b'  # Play-In
            else:
                zone_color = None
            
            if zone_color:
                zone_bar = patches.Rectangle(
                    (0.01, y - row_h * 0.4), 0.005, row_h * 0.8,
                    facecolor=zone_color, zorder=1
                )
                ax.add_patch(zone_bar)
        
        # Zone legend
        ax.text(0.88, 0.88, "● HCA (Top 4)", fontsize=8, color='#22c55e',
                ha='left', va='center')
        ax.text(0.88, 0.85, "● Playoffs (Top 6)", fontsize=8, color='#3b82f6',
                ha='left', va='center')
        ax.text(0.88, 0.82, "● Play-In (Top 10)", fontsize=8, color='#f59e0b',
                ha='left', va='center')
        
        ax.set_xlim(0, 1)
        ax.set_ylim(-0.02, 1)
        
        frame_path = os.path.join(temp_dir, f'frame_{frame_idx:03d}.png')
        plt.savefig(frame_path, dpi=120, bbox_inches='tight', facecolor='#0f172a')
        plt.close(fig)
        frames.append(frame_path)
        print(f"  Frame {frame_idx + 1}/{len(round_checkpoints)}: Round {round_num}")
    
    # Combine into GIF
    print("Combining frames into GIF...")
    images = [Image.open(f) for f in frames]
    
    # Add extra copies of the last frame for a pause
    for _ in range(5):
        images.append(images[-1].copy())
    
    images[0].save(
        'standings_race.gif',
        save_all=True,
        append_images=images[1:],
        duration=400,  # ms per frame
        loop=0
    )
    
    # Cleanup
    for f in frames:
        os.remove(f)
    os.rmdir(temp_dir)
    
    print("Animation saved to standings_race.gif!")


if __name__ == '__main__':
    create_standings_race()
