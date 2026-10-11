"""
Round Preview Card.
Generates a visual preview of the next upcoming round's matchups,
with win probabilities, team form, and stakes for each game.
"""

from season_config import CURRENT_SEASON
import json
import xml.etree.ElementTree as ET
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from chart_utils import add_logo


CODE_TO_FULL = {
    'BER': 'Alba Berlin', 'IST': 'Anadolu Efes', 'MCO': 'AS Monaco',
    'BAS': 'Baskonia', 'RED': 'Crvena Zvezda',
    'MIL': 'EA7 Milan', 'BAR': 'FC Barcelona', 'MUN': 'Bayern Munich',
    'ULK': 'Fenerbahce', 'ASV': 'ASVEL',
    'TEL': 'Maccabi Tel Aviv', 'OLY': 'Olympiacos',
    'PAN': 'Panathinaikos', 'PAR': 'Partizan',
    'PRS': 'Paris Basketball', 'MAD': 'Real Madrid',
    'BES': 'Besiktas',
    'PAM': 'Valencia Basket', 'VIR': 'Virtus Bologna',
    'ZAL': 'Zalgiris Kaunas', 'DUB': 'Dubai Basketball',
    'HTA': 'Hapoel Tel Aviv'
}

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


def get_next_round_games():
    """Find the next round's games from the schedule."""
    tree = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')
    root = tree.getroot()
    
    # Cross-check played games
    played_game_codes = set()
    try:
        with open('mvp_game_results.json', 'r') as f:
            results_data = json.load(f)
        for g in results_data:
            if g.get('LocalScore', 0) > 0:
                played_game_codes.add(g['GameCode'])
    except:
        pass
    
    # Find first unplayed round
    unplayed_by_round = {}
    for item in root.findall('item'):
        played_el = item.find('played')
        is_played = played_el is not None and played_el.text and played_el.text.lower() == 'true'
        
        gc_el = item.find('gamecode')
        if gc_el is not None:
            gc_text = gc_el.text
            gc_num = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
            if gc_num in played_game_codes:
                is_played = True
        
        if is_played:
            continue
        
        gd = int(item.find('gameday').text)
        h_code = NAME_TO_CODE.get(item.find('hometeam').text, 'UNK')
        a_code = NAME_TO_CODE.get(item.find('awayteam').text, 'UNK')
        
        if h_code != 'UNK' and a_code != 'UNK':
            unplayed_by_round.setdefault(gd, []).append((h_code, a_code))
    
    if not unplayed_by_round:
        return 0, []
    
    # Find the next FULL round (10 games), skipping postponed partial rounds
    for rd in sorted(unplayed_by_round.keys()):
        if len(unplayed_by_round[rd]) >= 5:  # At least 5 games = real round
            return rd, unplayed_by_round[rd]
    
    # Fallback: return earliest round
    next_round = min(unplayed_by_round.keys())
    return next_round, unplayed_by_round[next_round]


def calculate_win_prob(h_code, a_code, adj_ratings, teams_data):
    """Calculate win probability using the 3-factor model."""
    h_adj = adj_ratings.get(h_code, {}).get('Adj_Net', 0)
    a_adj = adj_ratings.get(a_code, {}).get('Adj_Net', 0)
    
    h_stats = teams_data.get(h_code, {})
    a_stats = teams_data.get(a_code, {})
    
    # Home/Away location ratings
    h_home_gp = h_stats.get('HomeGP', 1)
    h_loc = (h_stats.get('HomePTS', 0) - h_stats.get('HomePA', 0)) / max(h_home_gp, 1)
    
    a_away_gp = a_stats.get('AwayGP', 1)
    a_loc = (a_stats.get('AwayPTS', 0) - a_stats.get('AwayPA', 0)) / max(a_away_gp, 1)
    
    # Form (last 5 games)
    h_form = np.mean(h_stats.get('GameMargins', [0])[-5:])
    a_form = np.mean(a_stats.get('GameMargins', [0])[-5:])
    
    # 3-factor blend
    h_power = h_adj * 0.50 + h_loc * 0.20 + h_form * 0.30
    a_power = a_adj * 0.50 + a_loc * 0.20 + a_form * 0.30
    
    # HCA
    hca = 3.4 * 0.5
    pred_margin = (h_power - a_power) + hca
    
    # Convert margin to win probability using logistic function
    # σ=12 is our noise parameter
    win_prob = 1 / (1 + np.exp(-pred_margin / 6))
    
    return round(win_prob * 100, 1), round(pred_margin, 1)


def create_round_preview():
    print("Generating Round Preview Card...")
    
    # Get next round's games
    round_num, games = get_next_round_games()
    if not games:
        print("No upcoming games found!")
        return
    
    print(f"Next round: {round_num} with {len(games)} games")
    
    # Load adjusted ratings
    adj_ratings = {}
    try:
        import os
        round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
        in_file = f'adjusted_ratings{round_suffix}.json'
        if not os.path.exists(in_file):
            in_file = 'adjusted_ratings.json'
        with open(in_file, 'r') as f:
            for t in json.load(f):
                adj_ratings[t['Team']] = t
    except:
        pass
    
    # Load Monte Carlo results for context
    mc_lookup = {}
    try:
        import os
        round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
        in_file = f'monte_carlo_results{round_suffix}.json'
        if not os.path.exists(in_file):
            in_file = 'monte_carlo_results.json'
        with open(in_file, 'r') as f:
            for t in json.load(f):
                mc_lookup[t['Team']] = t
    except:
        pass
    
    # Load game data for form/splits
    teams_data = {}
    try:
        with open('mvp_game_results.json', 'r') as f:
            all_games = json.load(f)
        for g in all_games:
            if g['LocalScore'] <= 0:
                continue
            local, road = g['LocalTeam'], g['RoadTeam']
            for t in (local, road):
                if t not in teams_data:
                    teams_data[t] = {
                        'W': 0, 'L': 0,
                        'HomePTS': 0, 'HomePA': 0, 'HomeGP': 0,
                        'AwayPTS': 0, 'AwayPA': 0, 'AwayGP': 0,
                        'GameMargins': []
                    }
            if g['LocalScore'] > g['RoadScore']:
                teams_data[local]['W'] += 1
                teams_data[road]['L'] += 1
            else:
                teams_data[road]['W'] += 1
                teams_data[local]['L'] += 1
            teams_data[local]['HomePTS'] += g['LocalScore']
            teams_data[local]['HomePA'] += g['RoadScore']
            teams_data[local]['HomeGP'] += 1
            teams_data[local]['GameMargins'].append(g['LocalScore'] - g['RoadScore'])
            teams_data[road]['AwayPTS'] += g['RoadScore']
            teams_data[road]['AwayPA'] += g['LocalScore']
            teams_data[road]['AwayGP'] += 1
            teams_data[road]['GameMargins'].append(g['RoadScore'] - g['LocalScore'])
    except:
        pass
    
    # Calculate win probabilities for each game
    matchups = []
    for h, a in games:
        win_prob, pred_margin = calculate_win_prob(h, a, adj_ratings, teams_data)
        
        h_record = f"{teams_data.get(h, {}).get('W', 0)}-{teams_data.get(h, {}).get('L', 0)}"
        a_record = f"{teams_data.get(a, {}).get('W', 0)}-{teams_data.get(a, {}).get('L', 0)}"
        
        h_top6 = mc_lookup.get(h, {}).get('Top6_Pct', 0)
        a_top6 = mc_lookup.get(a, {}).get('Top6_Pct', 0)
        
        # Form: last 3 results
        h_margins = teams_data.get(h, {}).get('GameMargins', [])[-3:]
        a_margins = teams_data.get(a, {}).get('GameMargins', [])[-3:]
        h_form_str = ''.join(['W' if m > 0 else 'L' for m in h_margins])
        a_form_str = ''.join(['W' if m > 0 else 'L' for m in a_margins])
        
        matchups.append({
            'home': h, 'away': a,
            'h_win_pct': win_prob, 'a_win_pct': round(100 - win_prob, 1),
            'pred_margin': pred_margin,
            'h_record': h_record, 'a_record': a_record,
            'h_top6': h_top6, 'a_top6': a_top6,
            'h_form': h_form_str, 'a_form': a_form_str
        })
    
    # Sort by game importance (both teams' bubble proximity)
    matchups.sort(key=lambda m: abs(m['h_win_pct'] - 50), reverse=False)
    
    num_games = len(matchups)
    
    # --- FIGURE ---
    fig_h = 2.5 + num_games * 1.1
    fig, ax = plt.subplots(figsize=(12, fig_h))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    ax.axis('off')
    
    # Title
    ax.text(0.50, 0.97, f"ROUND {round_num} PREVIEW",
            ha='center', va='center', fontsize=26, color='#fbbf24',
            fontweight='bold')
    ax.text(0.50, 0.94, "Win probabilities based on KenPom Adjusted Ratings  •  Sorted by closeness",
            ha='center', va='center', fontsize=10, color='#94a3b8', style='italic')
    
    y_start = 0.88
    card_h = 0.80 / num_games
    
    for i, m in enumerate(matchups):
        y = y_start - i * card_h
        
        # Card background
        card_bg = patches.FancyBboxPatch(
            (0.03, y - card_h * 0.42), 0.94, card_h * 0.84,
            boxstyle="round,pad=0.008",
            facecolor='#1e293b', alpha=0.5, zorder=0
        )
        ax.add_patch(card_bg)
        
        # Home team (left side)
        try:
            add_logo(ax, m['home'], 0.08, y, zoom=0.38)
        except:
            pass
        h_name = CODE_TO_FULL.get(m['home'], m['home'])
        ax.text(0.14, y + card_h * 0.12, h_name, ha='left', va='center',
                fontsize=12, color='white', fontweight='bold')
        ax.text(0.14, y - card_h * 0.05, f"{m['h_record']}  •  Form: {m['h_form']}",
                ha='left', va='center', fontsize=8, color='#94a3b8')
        ax.text(0.14, y - card_h * 0.18, f"Playoff: {m['h_top6']}%",
                ha='left', va='center', fontsize=7, color='#64748b')
        
        # Win probability bar (center)
        bar_x = 0.42
        bar_w = 0.16
        bar_y = y - card_h * 0.08
        bar_h_size = card_h * 0.16
        
        h_ratio = m['h_win_pct'] / 100
        a_ratio = m['a_win_pct'] / 100
        
        # Home portion (green)
        h_bar = patches.Rectangle(
            (bar_x, bar_y), bar_w * h_ratio, bar_h_size,
            facecolor='#22c55e', alpha=0.8, zorder=1
        )
        ax.add_patch(h_bar)
        
        # Away portion (red)
        a_bar = patches.Rectangle(
            (bar_x + bar_w * h_ratio, bar_y), bar_w * a_ratio, bar_h_size,
            facecolor='#ef4444', alpha=0.8, zorder=1
        )
        ax.add_patch(a_bar)
        
        # Win probability text
        ax.text(bar_x - 0.02, y - card_h * 0.0, f"{m['h_win_pct']:.0f}%",
                ha='right', va='center', fontsize=11, color='#22c55e', fontweight='bold')
        ax.text(bar_x + bar_w + 0.02, y - card_h * 0.0, f"{m['a_win_pct']:.0f}%",
                ha='left', va='center', fontsize=11, color='#ef4444', fontweight='bold')
        
        # Predicted margin
        if m['pred_margin'] > 0:
            margin_text = f"Home by {abs(m['pred_margin']):.0f}"
        else:
            margin_text = f"Away by {abs(m['pred_margin']):.0f}"
        ax.text(bar_x + bar_w / 2, y + card_h * 0.15, margin_text,
                ha='center', va='center', fontsize=7, color='#94a3b8')
        
        # Away team (right side)
        try:
            add_logo(ax, m['away'], 0.92, y, zoom=0.38)
        except:
            pass
        a_name = CODE_TO_FULL.get(m['away'], m['away'])
        ax.text(0.86, y + card_h * 0.12, a_name, ha='right', va='center',
                fontsize=12, color='white', fontweight='bold')
        ax.text(0.86, y - card_h * 0.05, f"Form: {m['a_form']}  •  {m['a_record']}",
                ha='right', va='center', fontsize=8, color='#94a3b8')
        ax.text(0.86, y - card_h * 0.18, f"Playoff: {m['a_top6']}%",
                ha='right', va='center', fontsize=7, color='#64748b')
        
        # Game number indicator
        ax.text(0.50, y + card_h * 0.28, f"Game {i + 1}",
                ha='center', va='center', fontsize=7, color='#475569')
    
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.02, 1)
    
    plt.tight_layout()
    import os
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'round_preview{round_suffix}.png'
    
    plt.savefig(outfile, dpi=200, bbox_inches='tight', facecolor='#0f172a')
    print(f"Card saved to {outfile}!")


if __name__ == '__main__':
    create_round_preview()
