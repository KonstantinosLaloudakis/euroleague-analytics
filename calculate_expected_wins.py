"""
Expected Wins (xW) Model for Euroleague.
Like xG in football: calculates how many wins each team DESERVES
based on their game-by-game point margins and opponent quality.

Teams above the diagonal (Actual > xW) are "lucky" — winning close games.
Teams below (Actual < xW) are "unlucky" — losing despite dominating.
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from adjustText import adjust_text
import os


# Logistic function: converts margin to win probability
def margin_to_win_prob(margin, sigma=10.5):
    """
    Convert point margin to win probability.
    sigma calibrated so that:
      +3 pts => ~62% win prob
      +10 pts => ~81% win prob
      +20 pts => ~95% win prob
    """
    return 1 / (1 + np.exp(-margin / sigma))


def calculate_expected_wins():
    """Calculate xW for all teams based on game-level margins."""
    
    with open('mvp_game_results.json', 'r') as f:
        all_games = json.load(f)
    
    # Load adjusted ratings for opponent-quality weighting
    adj_net = {}
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'adjusted_ratings{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'adjusted_ratings.json'
    if os.path.exists(in_file):
        with open(in_file, 'r') as f:
            for e in json.load(f):
                adj_net[e['Team']] = e['Adj_Net']
    
    def _rs(g):
        gc = g.get('GameCode', 0)
        if isinstance(gc, float):
            gc = int(gc)
        return gc <= 380 and g['LocalScore'] > 0
    played = [g for g in all_games if _rs(g)]
    
    # Track per-team stats
    teams = {}
    
    team_names = {
        'OLY': 'Olympiacos', 'ULK': 'Fenerbahce', 'PAN': 'Panathinaikos',
        'MAD': 'Real Madrid', 'BAR': 'Barcelona', 'MCO': 'Monaco',
        'ZAL': 'Zalgiris', 'DUB': 'Dubai', 'IST': 'Efes',
        'HTA': 'Hapoel TA', 'PAR': 'Partizan', 'RED': 'C. Zvezda',
        'TEL': 'Maccabi', 'BAS': 'Baskonia', 'MUN': 'Bayern',
        'VIR': 'Virtus', 'PAM': 'Valencia', 'ASV': 'ASVEL',
        'PRS': 'Paris', 'BER': 'ALBA Berlin', 'MIL': 'EA7 Milan', 'BES': 'Besiktas'
    }
    
    team_colors = {
        'OLY': '#E2001A', 'ULK': '#002B5C', 'PAN': '#007F3D', 
        'MAD': '#645486', 'BAR': '#004D98', 'MCO': '#D4AF37',
        'ZAL': '#006233', 'DUB': '#1a1a2e', 'IST': '#003366', 'BES': '#d9d9d9',
        'HTA': '#C8102E', 'PAR': '#000000', 'RED': '#CC0000', 
        'TEL': '#F6C300', 'BAS': '#B50031', 'MUN': '#0066B2',
        'VIR': '#000000', 'PAM': '#EB7622', 'ASV': '#1a1a2e',
        'PRS': '#1a1a2e', 'MIL': '#CE0E2D'
    }
    
    def get_team(t):
        if t not in teams:
            teams[t] = {
                'actual_wins': 0,
                'actual_losses': 0,
                'xW': 0.0,       # Expected wins (sum of win probs)
                'xL': 0.0,       # Expected losses
                'games': [],     # Per-game details
                'close_wins': 0, # Wins by <= 5
                'close_losses': 0,
                'blowout_wins': 0,   # Wins by >= 15
                'blowout_losses': 0,
                'total_margin': 0,
                'luck_games': []     # Games where result differs from xW prediction
            }
        return teams[t]
    
    for game in played:
        local = game['LocalTeam']
        road = game['RoadTeam']
        l_pts = game['LocalScore']
        r_pts = game['RoadScore']
        margin = l_pts - r_pts
        
        local_won = margin > 0
        
        # Opponent-quality adjustment:
        # If you beat a strong team (high adj net), your xW for that game is boosted
        # If you beat a weak team, your xW is slightly reduced
        opp_adj_local = adj_net.get(road, 0)  # opponent's Adj Net
        opp_adj_road = adj_net.get(local, 0)
        
        # Quality factor: scale margin by relative opponent strength
        # Against a +10 Adj Net team, a +5 margin is worth more
        # Against a -10 Adj Net team, a +5 margin is worth less
        quality_bonus_local = opp_adj_local / 40  # Scaled so +10 team adds ~0.25 pts
        quality_bonus_road = opp_adj_road / 40
        
        adj_margin_local = margin + quality_bonus_local
        adj_margin_road = -margin + quality_bonus_road
        
        # Win probabilities
        xw_local = margin_to_win_prob(adj_margin_local)
        xw_road = margin_to_win_prob(adj_margin_road)
        
        # Update local team
        lt = get_team(local)
        lt['xW'] += xw_local
        lt['xL'] += (1 - xw_local)
        lt['total_margin'] += margin
        if local_won:
            lt['actual_wins'] += 1
            if abs(margin) <= 5: lt['close_wins'] += 1
            if abs(margin) >= 15: lt['blowout_wins'] += 1
        else:
            lt['actual_losses'] += 1
            if abs(margin) <= 5: lt['close_losses'] += 1
            if abs(margin) >= 15: lt['blowout_losses'] += 1
        
        lt['games'].append({
            'vs': road, 'margin': margin, 'xW': round(xw_local, 3),
            'won': local_won, 'home': True
        })
        
        # "Luck" game: won but xW < 0.5, or lost but xW > 0.5
        if (local_won and xw_local < 0.45) or (not local_won and xw_local > 0.55):
            lt['luck_games'].append({
                'vs': road, 'margin': margin, 'xW': round(xw_local, 3), 'won': local_won
            })
        
        # Update road team
        rt = get_team(road)
        rt['xW'] += xw_road
        rt['xL'] += (1 - xw_road)
        rt['total_margin'] -= margin
        if not local_won:
            rt['actual_wins'] += 1
            if abs(margin) <= 5: rt['close_wins'] += 1
            if abs(margin) >= 15: rt['blowout_wins'] += 1
        else:
            rt['actual_losses'] += 1
            if abs(margin) <= 5: rt['close_losses'] += 1
            if abs(margin) >= 15: rt['blowout_losses'] += 1
        
        rt['games'].append({
            'vs': local, 'margin': -margin, 'xW': round(xw_road, 3),
            'won': not local_won, 'home': False
        })
        
        if (not local_won and xw_road < 0.45) or (local_won and xw_road > 0.55):
            rt['luck_games'].append({
                'vs': local, 'margin': -margin, 'xW': round(xw_road, 3), 'won': not local_won
            })
    
    # === PRINT RESULTS ===
    print(f"\n{'='*75}")
    print(f"  EXPECTED WINS (xW) MODEL — Euroleague 2025-26")
    print(f"{'='*75}")
    print(f"  {'Team':<14} {'W':>3} {'L':>3} {'xW':>6} {'xL':>6} {'Luck':>6} {'Close':>8} {'AvgMar':>7}")
    print(f"  {'-'*62}")
    
    sorted_teams = sorted(teams.items(), 
                          key=lambda x: x[1]['actual_wins'] - x[1]['xW'], 
                          reverse=True)
    
    results = []
    for code, t in sorted_teams:
        gp = t['actual_wins'] + t['actual_losses']
        luck = t['actual_wins'] - t['xW']
        close_rec = f"{t['close_wins']}-{t['close_losses']}"
        avg_margin = t['total_margin'] / gp if gp > 0 else 0
        
        icon = "🍀" if luck > 1.5 else "💀" if luck < -1.5 else "  "
        
        name = team_names.get(code, code)
        print(f"  {name:<14} {t['actual_wins']:>3} {t['actual_losses']:>3} "
              f"{t['xW']:>5.1f} {t['xL']:>5.1f} {luck:>+5.1f} {close_rec:>8} {avg_margin:>+6.1f}  {icon}")
        
        results.append({
            'Team': code,
            'Name': name,
            'W': t['actual_wins'],
            'L': t['actual_losses'],
            'GP': gp,
            'xW': round(t['xW'], 2),
            'xL': round(t['xL'], 2),
            'Luck': round(luck, 2),
            'CloseWins': t['close_wins'],
            'CloseLosses': t['close_losses'],
            'BlowoutWins': t['blowout_wins'],
            'BlowoutLosses': t['blowout_losses'],
            'AvgMargin': round(avg_margin, 2),
            'LuckGames': len(t['luck_games'])
        })
    
    # Save raw data
    with open('expected_wins.json', 'w') as f:
        json.dump(results, f, indent=4)
    print(f"\n  Saved expected_wins.json")
    
    # === VISUALIZATION ===
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#161b22')
    
    # Diagonal line (Actual = xW)
    max_w = max(max(t['actual_wins'] for _, t in sorted_teams), 
                max(t['xW'] for _, t in sorted_teams)) + 2
    min_w = min(min(t['actual_wins'] for _, t in sorted_teams),
                min(t['xW'] for _, t in sorted_teams)) - 2
    ax.plot([min_w, max_w], [min_w, max_w], '--', color='#30363d', linewidth=2, zorder=1)
    
    # Fill regions — extend to full axis range so no dots are outside
    ax.fill_between([min_w, max_w], [min_w, max_w], [max_w, max_w], 
                     alpha=0.08, color='#39d353', zorder=0)  # Lucky region (above)
    ax.fill_between([min_w, max_w], [min_w, min_w], [min_w, max_w], 
                     alpha=0.08, color='#f85149', zorder=0)  # Unlucky region (below)
    ax.set_xlim(min_w, max_w)
    ax.set_ylim(min_w, max_w)
    
    # Region labels
    ax.text(max_w - 3, min_w + 1.5, 'UNLUCKY\n(deserves more wins)', 
            fontsize=10, color='#f8514960', ha='center', fontstyle='italic')  
    ax.text(min_w + 3, max_w - 2, 'LUCKY\n(record flatters them)', 
            fontsize=10, color='#39d35360', ha='center', fontstyle='italic')
    
    # Plot teams and collect labels
    texts = []
    for code, t in sorted_teams:
        xw = t['xW']
        aw = t['actual_wins']
        luck = aw - xw
        
        color = team_colors.get(code, '#8b949e')
        size = 120 + abs(luck) * 40  # Bigger dot = more lucky/unlucky
        
        # Edge color based on luck
        if luck > 1.5:
            edge = '#39d353'  # Green = lucky
        elif luck < -1.5:
            edge = '#f85149'  # Red = unlucky
        else:
            edge = '#8b949e'  # Gray = fair
        
        ax.scatter(xw, aw, s=size, c=color, edgecolors=edge, 
                   linewidths=2.5, zorder=5, alpha=0.9)
        
        # Collect label for adjustText
        name = team_names.get(code, code)
        texts.append(ax.text(xw, aw, name, fontsize=7.5, color='#e6edf3', 
                             fontweight='bold', ha='center', va='center'))
    
    # Auto-resolve label overlaps (tuned for tight bottom-5 cluster)
    adjust_text(texts, ax=ax, 
                arrowprops=dict(arrowstyle='-', color='#8b949e', alpha=0.5, lw=0.7),
                force_text=(1.5, 2.0),
                force_points=(0.5, 1.0),
                expand=(2.0, 2.0),
                ensure_inside_axes=True,
                time_lim=5)
    
    # Labels and title
    ax.set_xlabel('Expected Wins (xW)', fontsize=13, color='#e6edf3', fontweight='bold')
    ax.set_ylabel('Actual Wins (W)', fontsize=13, color='#e6edf3', fontweight='bold')
    ax.set_title('EXPECTED WINS vs ACTUAL WINS\nWho\'s Lucky? Who Deserves Better?', 
                 fontsize=16, color='#e6edf3', fontweight='bold', pad=20)
    
    # Style
    ax.tick_params(colors='#8b949e')
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.15, color='#30363d')
    
    # Legend
    lucky_patch = mpatches.Patch(facecolor='none', edgecolor='#39d353', 
                                  linewidth=2, label='Lucky (Actual > xW)')
    unlucky_patch = mpatches.Patch(facecolor='none', edgecolor='#f85149', 
                                    linewidth=2, label='Unlucky (Actual < xW)')
    fair_patch = mpatches.Patch(facecolor='none', edgecolor='#8b949e', 
                                 linewidth=2, label='Fair Record')
    ax.legend(handles=[lucky_patch, unlucky_patch, fair_patch], 
              loc='upper left', fontsize=9, facecolor='#161b22', 
              edgecolor='#30363d', labelcolor='#e6edf3')
    
    # Subtitle with methodology
    fig.text(0.5, 0.01, 
             'xW = sum of game-level win probabilities based on margin + opponent quality adjustment',
             ha='center', fontsize=8, color='#8b949e', fontstyle='italic')
    
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.06)
    outfile = 'expected_wins.png'
    plt.savefig(outfile, dpi=150, facecolor=fig.get_facecolor())
    print(f"  Visualization saved to {outfile}")
    
    # Print insights
    luckiest = max(results, key=lambda x: x['Luck'])
    unluckiest = min(results, key=lambda x: x['Luck'])
    print(f"\n  🍀 LUCKIEST: {luckiest['Name']} ({luckiest['W']}W actual vs {luckiest['xW']:.1f} xW = +{luckiest['Luck']:.1f} luck)")
    print(f"  💀 UNLUCKIEST: {unluckiest['Name']} ({unluckiest['W']}W actual vs {unluckiest['xW']:.1f} xW = {unluckiest['Luck']:.1f} luck)")
    
    # Close game analysis
    best_close = max(results, key=lambda x: x['CloseWins'] - x['CloseLosses'])
    worst_close = min(results, key=lambda x: x['CloseWins'] - x['CloseLosses'])
    print(f"  🎯 BEST IN CLOSE GAMES: {best_close['Name']} ({best_close['CloseWins']}-{best_close['CloseLosses']})")
    print(f"  😰 WORST IN CLOSE GAMES: {worst_close['Name']} ({worst_close['CloseWins']}-{worst_close['CloseLosses']})")
    
    return results


if __name__ == '__main__':
    calculate_expected_wins()
