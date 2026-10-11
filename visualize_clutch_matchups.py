"""
Clutch Matchup Chart.
Identifies the remaining games with the highest impact on playoff seeding.
Impact = how much the average league-wide playoff probabilities swing 
if Team A wins vs Team B wins.
"""

from season_config import CURRENT_SEASON
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from chart_utils import add_logo


CODE_TO_SHORT = {
    'BER': 'Berlin', 'IST': 'Efes', 'MCO': 'Monaco',
    'BAS': 'Baskonia', 'RED': 'Zvezda',
    'MIL': 'Milan', 'BAR': 'Barca', 'MUN': 'Bayern',
    'ULK': 'Fener', 'ASV': 'ASVEL',
    'TEL': 'Maccabi', 'OLY': 'Olympiacos',
    'PAN': 'Pana', 'PAR': 'Partizan',
    'PRS': 'Paris', 'MAD': 'R. Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia', 'VIR': 'Virtus',
    'ZAL': 'Zalgiris', 'DUB': 'Dubai',
    'HTA': 'Hapoel'
}


def calculate_clutch_games():
    """
    For each remaining game, calculate the 'swing' impact.
    Uses the seed distribution to measure: 
    how much does this game shift seeding probabilities for BOTH teams?
    """
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'monte_carlo_results{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'monte_carlo_results.json'
    with open(in_file, 'r') as f:
        mc_data = json.load(f)
    
    # Build lookup
    team_lookup = {}
    for t in mc_data:
        team_lookup[t['Team']] = t
    
    # Get remaining games from schedule
    import xml.etree.ElementTree as ET
    
    NAME_TO_CODE = {
        'ALBA BERLIN': 'BER', 'ANADOLU EFES ISTANBUL': 'IST', 'AS MONACO': 'MCO',
        'BASKONIA VITORIA-GASTEIZ': 'BAS', 'KOSNER BASKONIA VITORIA-GASTEIZ': 'BAS',
        'CRVENA ZVEZDA MERIDIANBET BELGRADE': 'RED',
        'EA7 EMPORIO ARMANI MILAN': 'MIL',
        'FC BARCELONA': 'BAR', 'FC BAYERN MUNICH': 'MUN',
        'FENERBAHCE BEKO ISTANBUL': 'ULK',
        'LDLC ASVEL VILLEURBANNE': 'ASV',
        'MACCABI PLAYTIKA TEL AVIV': 'TEL', 'MACCABI RAPYD TEL AVIV': 'TEL',
        'OLYMPIACOS PIRAEUS': 'OLY',
        'PANATHINAIKOS AKTOR ATHENS': 'PAN',
        'PARTIZAN MOZZART BET BELGRADE': 'PAR',
        'PARIS BASKETBALL': 'PRS',
        'REAL MADRID': 'MAD',
        'BESIKTAS ISTANBUL': 'BES', 'ARMANI OLIMPIA MILAN': 'MIL', 'FENERBAHCE TARFIN ISTANBUL': 'ULK',
        'VALENCIA BASKET': 'PAM',
        'VIRTUS SEGAFREDO BOLOGNA': 'VIR', 'VIRTUS BOLOGNA': 'VIR',
        'ZALGIRIS KAUNAS': 'ZAL',
        'DUBAI BASKETBALL': 'DUB',
        'HAPOEL IBI TEL AVIV': 'HTA'
    }
    
    tree = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')
    root = tree.getroot()
    
    # Cross-check: build set of played game codes from actual results
    played_game_codes = set()
    try:
        with open('mvp_game_results.json', 'r') as f:
            results_data = json.load(f)
        for g in results_data:
            if g.get('LocalScore', 0) > 0:
                played_game_codes.add(g['GameCode'])
    except:
        pass
    
    remaining_games = []
    for item in root.findall('item'):
        played_el = item.find('played')
        is_played = played_el is not None and played_el.text and played_el.text.lower() == 'true'
        
        # Also check against actual results
        gc_el = item.find('gamecode')
        if gc_el is not None:
            gc_text = gc_el.text
            gc_num = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
            if gc_num in played_game_codes:
                is_played = True
        
        if is_played:
            continue
        
        home_name = item.find('hometeam').text
        away_name = item.find('awayteam').text
        gameday = item.find('gameday').text
        
        h_code = NAME_TO_CODE.get(home_name, "UNK")
        a_code = NAME_TO_CODE.get(away_name, "UNK")
        
        if h_code != "UNK" and a_code != "UNK":
            remaining_games.append({
                'home': h_code,
                'away': a_code,
                'round': int(gameday) if gameday else 0
            })
    
    # Calculate impact score for each game
    # Impact = how close both teams are in the standings + are they in the 
    # playoff bubble zone (positions 3-11)
    clutch_scores = []
    
    for game in remaining_games:
        h = game['home']
        a = game['away']
        
        h_data = team_lookup.get(h)
        a_data = team_lookup.get(a)
        if not h_data or not a_data:
            continue
        
        # 1. How close are they in expected wins? (closer = more impactful)
        wins_gap = abs(h_data['Avg_Wins'] - a_data['Avg_Wins'])
        closeness_score = max(0, 15 - wins_gap) / 15  # 0-1, higher = closer
        
        # 2. Are both teams in the bubble zone? (Top6 probability between 5-95%)
        h_bubble = 1 if 5 < h_data['Top6_Pct'] < 95 else 0.3
        a_bubble = 1 if 5 < a_data['Top6_Pct'] < 95 else 0.3
        bubble_factor = (h_bubble + a_bubble) / 2
        
        # 3. Are they competing for the same spot? (seed overlap)
        h_seeds = h_data.get('Seed_Distribution', {})
        a_seeds = a_data.get('Seed_Distribution', {})
        
        overlap = 0
        for pos in range(1, 21):
            h_pct = h_seeds.get(str(pos), 0)
            a_pct = a_seeds.get(str(pos), 0)
            overlap += min(h_pct, a_pct)
        overlap_score = overlap / 100  # Normalize
        
        # 4. Combined "swing" impact
        # Direct rivalry (competing for same seed) is the biggest factor
        swing = (closeness_score * 0.30 + bubble_factor * 0.30 + overlap_score * 0.40) * 100
        
        clutch_scores.append({
            'home': h,
            'away': a,
            'round': game['round'],
            'swing': round(swing, 1),
            'h_xwins': h_data['Avg_Wins'],
            'a_xwins': a_data['Avg_Wins'],
            'h_top6': h_data['Top6_Pct'],
            'a_top6': a_data['Top6_Pct']
        })
    
    # Sort by swing impact
    clutch_scores.sort(key=lambda x: x['swing'], reverse=True)
    
    return clutch_scores[:15]  # Top 15 most impactful games


def create_clutch_chart():
    print("Generating Clutch Matchup Chart...")

    clutch_games = calculate_clutch_games()
    if not clutch_games:
        print("No remaining games — skipping clutch matchup chart.")
        return
    num_games = len(clutch_games)
    
    fig_h = 1.5 + num_games * 0.52
    fig, ax = plt.subplots(figsize=(14, fig_h))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    ax.axis('off')
    
    # Title
    ax.text(0.50, 0.96, "CLUTCH MATCHUPS | Highest-Impact Remaining Games",
            ha='center', va='center', fontsize=20, color='#fbbf24',
            fontweight='bold')
    ax.text(0.50, 0.93, "Games ranked by seeding impact  •  Bubble teams competing for the same positions",
            ha='center', va='center', fontsize=11, color='#94a3b8', style='italic')
    
    # Header
    y_header = 0.88
    hdr_bg = patches.Rectangle((0.02, y_header - 0.015), 0.96, 0.035,
                                facecolor='#1e293b', alpha=0.9, zorder=0)
    ax.add_patch(hdr_bg)
    
    ax.text(0.04, y_header, "#", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(0.09, y_header, "RD", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(0.30, y_header, "HOME", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(0.50, y_header, "vs", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(0.70, y_header, "AWAY", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    ax.text(0.88, y_header, "IMPACT", ha='center', va='center', fontsize=9,
            color='#94a3b8', fontweight='bold')
    
    ax.plot([0.02, 0.98], [y_header - 0.02, y_header - 0.02],
            color='#334155', linewidth=1.5)
    
    # Data rows
    y_start = 0.83
    row_h = 0.75 / num_games
    max_swing = max(g['swing'] for g in clutch_games)
    
    for i, game in enumerate(clutch_games):
        y = y_start - i * row_h
        
        # Alternate backgrounds
        if i % 2 == 0:
            bg = patches.Rectangle((0.02, y - row_h * 0.4), 0.96, row_h * 0.8,
                                    facecolor='#1e293b', alpha=0.2, zorder=0)
            ax.add_patch(bg)
        
        # Rank
        ax.text(0.04, y, str(i + 1), ha='center', va='center', fontsize=11,
                color='#94a3b8', fontweight='bold')
        
        # Round
        ax.text(0.09, y, f"R{game['round']}", ha='center', va='center',
                fontsize=10, color='#64748b', fontweight='bold')
        
        # Home team
        try:
            add_logo(ax, game['home'], 0.18, y, zoom=0.30)
        except:
            pass
        h_name = CODE_TO_SHORT.get(game['home'], game['home'])
        ax.text(0.23, y + 0.005, h_name, ha='left', va='center', fontsize=11,
                color='white', fontweight='bold')
        ax.text(0.23, y - 0.015, f"xW: {game['h_xwins']:.0f}  T6: {game['h_top6']}%",
                ha='left', va='center', fontsize=7, color='#94a3b8')
        
        # VS
        ax.text(0.50, y, "vs", ha='center', va='center', fontsize=10,
                color='#475569', fontweight='bold')
        
        # Away team
        try:
            add_logo(ax, game['away'], 0.58, y, zoom=0.30)
        except:
            pass
        a_name = CODE_TO_SHORT.get(game['away'], game['away'])
        ax.text(0.63, y + 0.005, a_name, ha='left', va='center', fontsize=11,
                color='white', fontweight='bold')
        ax.text(0.63, y - 0.015, f"xW: {game['a_xwins']:.0f}  T6: {game['a_top6']}%",
                ha='left', va='center', fontsize=7, color='#94a3b8')
        
        # Impact bar
        bar_width = 0.10 * (game['swing'] / max_swing)
        
        # Color based on impact level
        if game['swing'] >= max_swing * 0.75:
            bar_color = '#ef4444'  # Red: critical
        elif game['swing'] >= max_swing * 0.5:
            bar_color = '#f59e0b'  # Amber: important
        else:
            bar_color = '#3b82f6'  # Blue: notable
        
        bar = patches.FancyBboxPatch(
            (0.83, y - row_h * 0.2), bar_width, row_h * 0.4,
            boxstyle="round,pad=0.002",
            facecolor=bar_color, alpha=0.7, zorder=1
        )
        ax.add_patch(bar)
        
        ax.text(0.83 + bar_width + 0.01, y, f"{game['swing']:.0f}",
                ha='left', va='center', fontsize=9, color=bar_color,
                fontweight='bold')
    
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.02, 1)
    
    plt.tight_layout()
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'clutch_matchups{round_suffix}.png'
    
    plt.savefig(outfile, dpi=200, bbox_inches='tight', facecolor='#0f172a')
    print(f"Chart saved to {outfile}!")


if __name__ == '__main__':
    create_clutch_chart()
