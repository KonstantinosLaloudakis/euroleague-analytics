import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import json
import os

from season_config import CURRENT_SEASON
from wp_model_utils import predict_wp


# ── Euroleague tiebreaker helpers ────────────────────────────────────
def _resolve_tie(group, h2h_wins, h2h_pd, overall_pd):
    """Resolve a tie among `group` (list of team indices) using Euroleague rules:
    1. H2H win-loss record among all tied teams (mini-table)
    2. H2H point differential among tied teams
    3. Overall point differential
    """
    if len(group) <= 1:
        return group

    # --- Two-way tie: direct comparison ---
    if len(group) == 2:
        i, j = group
        if h2h_wins[i, j] > h2h_wins[j, i]:
            return [i, j]
        if h2h_wins[j, i] > h2h_wins[i, j]:
            return [j, i]
        if h2h_pd[i, j] > h2h_pd[j, i]:
            return [i, j]
        if h2h_pd[j, i] > h2h_pd[i, j]:
            return [j, i]
        if overall_pd[i] >= overall_pd[j]:
            return [i, j]
        return [j, i]

    # --- Multi-way tie: mini-table h2h wins within the group ---
    group_wins = {t: sum(h2h_wins[t, o] for o in group if o != t) for t in group}
    sorted_teams = sorted(group, key=lambda t: group_wins[t], reverse=True)

    result = []
    i = 0
    while i < len(sorted_teams):
        # collect sub-group with equal h2h wins
        j = i + 1
        while j < len(sorted_teams) and group_wins[sorted_teams[j]] == group_wins[sorted_teams[i]]:
            j += 1
        sub = sorted_teams[i:j]
        if len(sub) == 1:
            result.append(sub[0])
        elif len(sub) < len(group):
            # smaller sub-group → re-apply h2h among just these teams
            result.extend(_resolve_tie(sub, h2h_wins, h2h_pd, overall_pd))
        else:
            # all equal h2h wins → fall through to h2h PD within group
            group_pd = {t: sum(h2h_pd[t, o] for o in sub if o != t) for t in sub}
            pd_sorted = sorted(sub, key=lambda t: (group_pd[t], overall_pd[t]), reverse=True)
            result.extend(pd_sorted)
        i = j

    return result


def _rank_with_h2h(sim_wins, sim_pd, sim_h2h_wins, sim_h2h_pd, num_teams, num_simulations):
    """Rank all teams per simulation using Euroleague tiebreaker rules."""
    team_ranks = np.zeros((num_simulations, num_teams), dtype=int)

    for sim in range(num_simulations):
        wins = sim_wins[sim]
        pd_arr = sim_pd[sim]
        h2h_w = sim_h2h_wins[sim]
        h2h_p = sim_h2h_pd[sim]

        # group teams by win count
        win_groups = {}
        for t in range(num_teams):
            w = int(wins[t])
            if w not in win_groups:
                win_groups[w] = []
            win_groups[w].append(t)

        rank = 0
        for w in sorted(win_groups.keys(), reverse=True):
            group = win_groups[w]
            if len(group) == 1:
                team_ranks[sim, group[0]] = rank
                rank += 1
            else:
                ordered = _resolve_tie(group, h2h_w, h2h_p, pd_arr)
                for t in ordered:
                    team_ranks[sim, t] = rank
                    rank += 1

    return team_ranks


def run_monte_carlo(num_simulations=10000):
    print("--- 🏀 Euroleague Monte Carlo Playoff Matrix 🏀 ---")
    print(f"Running {num_simulations} simulations of the remaining season...")

    # 1. Load baseline data from mvp_game_results.json
    if not os.path.exists('mvp_game_results.json'):
        print("Error: mvp_game_results.json not found.")
        return

    try:
        df = pd.read_json('mvp_game_results.json')
        # Regular-season only: playoff games have GameCode > 380
        played = df[(df['LocalScore'] > 0) & (df['RoadScore'] > 0) & (df['GameCode'] <= 380)].copy()
        
        # Base HCA
        hca = (played['LocalScore'] - played['RoadScore']).mean()
        
        # Calculate current standings and advanced ratings
        teams_data = {}
        for _, row in played.iterrows():
            local, road = row['LocalTeam'], row['RoadTeam']
            l_pts, r_pts = row['LocalScore'], row['RoadScore']
            
            for t in (local, road):
                if t not in teams_data:
                    # Added arrays to track Home/Away specifically and game-by-game for Form
                    teams_data[t] = {
                        'W': 0, 'L': 0, 
                        'HomePTS': 0, 'HomePA': 0, 'HomeGP': 0,
                        'AwayPTS': 0, 'AwayPA': 0, 'AwayGP': 0,
                        'GameMargins': []
                    }
            
            if l_pts > r_pts:
                teams_data[local]['W'] += 1
                teams_data[road]['L'] += 1
            else:
                teams_data[road]['W'] += 1
                teams_data[local]['L'] += 1
                
            # Home Splits
            teams_data[local]['HomePTS'] += l_pts
            teams_data[local]['HomePA'] += r_pts
            teams_data[local]['HomeGP'] += 1
            teams_data[local]['GameMargins'].append(l_pts - r_pts)
            
            # Away Splits
            teams_data[road]['AwayPTS'] += r_pts
            teams_data[road]['AwayPA'] += l_pts
            teams_data[road]['AwayGP'] += 1
            teams_data[road]['GameMargins'].append(r_pts - l_pts)
            
        print(f"Loaded {len(teams_data)} teams with {len(played)} played games.")
        
    except Exception as e:
        print(f"Error loading base data: {e}")
        return

    # 1b. Load KenPom Adjusted Ratings
    adj_net_lookup = {}
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    in_file = f'adjusted_ratings{round_suffix}.json'
    if not os.path.exists(in_file):
        in_file = 'adjusted_ratings.json'
    if os.path.exists(in_file):
        with open(in_file, 'r') as f:
            adj_data = json.load(f)
        for entry in adj_data:
            adj_net_lookup[entry['Team']] = entry['Adj_Net']
        print(f"Loaded Adjusted Net Ratings for {len(adj_net_lookup)} teams.")
    else:
        print("Warning: adjusted_ratings.json not found. Using raw ratings only.")

    # 1c. Load Rolling Elo Ratings
    elo_lookup = {}
    elo_file = f'elo_ratings{round_suffix}.json'
    if not os.path.exists(elo_file):
        elo_file = 'elo_ratings.json'
    if os.path.exists(elo_file):
        with open(elo_file, 'r') as f:
            elo_data = json.load(f)
        for entry in elo_data:
            elo_lookup[entry['Team']] = entry['Elo']
        print(f"Loaded Elo Ratings for {len(elo_lookup)} teams.")
    else:
        print("Warning: elo_ratings.json not found. Elo factor disabled.")

    team_list = sorted(list(teams_data.keys()))
    num_teams = len(team_list)
    team_to_idx = {t: i for i, t in enumerate(team_list)}
    
    # Base Numpy Arrays
    base_wins = np.zeros(num_teams)
    base_pd = np.zeros(num_teams)
    home_net_ratings = np.zeros(num_teams)
    net_ratings = np.zeros(num_teams)
    adj_net_ratings = np.zeros(num_teams)
    elo_ratings = np.zeros(num_teams)

    for t in team_list:
        idx = team_to_idx[t]
        stats = teams_data[t]

        base_wins[idx] = stats['W']
        t_pts = stats['HomePTS'] + stats['AwayPTS']
        t_pa  = stats['HomePA']  + stats['AwayPA']
        base_pd[idx] = t_pts - t_pa

        gp = stats['HomeGP'] + stats['AwayGP']
        net_ratings[idx]      = (t_pts - t_pa) / gp if gp > 0 else 0
        home_net_ratings[idx] = (stats['HomePTS'] - stats['HomePA']) / stats['HomeGP'] if stats['HomeGP'] > 0 else 0
        adj_net_ratings[idx]  = adj_net_lookup.get(t, 0)
        elo_ratings[idx]      = elo_lookup.get(t, 1500)

    # 1e. Build head-to-head record matrix from played games
    base_h2h_wins = np.zeros((num_teams, num_teams))
    base_h2h_pd   = np.zeros((num_teams, num_teams))
    for _, row in played.iterrows():
        local, road = row['LocalTeam'], row['RoadTeam']
        l_idx, r_idx = team_to_idx.get(local), team_to_idx.get(road)
        if l_idx is None or r_idx is None:
            continue
        l_pts, r_pts = int(row['LocalScore']), int(row['RoadScore'])
        if l_pts > r_pts:
            base_h2h_wins[l_idx, r_idx] += 1
        else:
            base_h2h_wins[r_idx, l_idx] += 1
        base_h2h_pd[l_idx, r_idx] += (l_pts - r_pts)
        base_h2h_pd[r_idx, l_idx] += (r_pts - l_pts)
    print(f"Built head-to-head matrix ({num_teams}x{num_teams}) from played games.")

    # 2. Extract Unplayed Games
    name_to_code = {
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
        'VALENCIA BASKET': 'PAM', 
        'VIRTUS SEGAFREDO BOLOGNA': 'VIR', 'VIRTUS BOLOGNA': 'VIR',
        'ZALGIRIS KAUNAS': 'ZAL', 
        'DUBAI BASKETBALL': 'DUB',
        'HAPOEL IBI TEL AVIV': 'HTA'
    }

    try:
        tree = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')
        root = tree.getroot()
        all_items = root.findall('item')
        
        # Cross-check: build set of played game codes from actual results
        played_game_codes = set()
        for _, row in played.iterrows():
            played_game_codes.add(row['GameCode'])
        
        remaining_games = []
        for item in all_items:
            # Check XML played flag
            played_el = item.find('played')
            is_played = played_el is not None and played_el.text and played_el.text.lower() == 'true'
            
            # Also check against actual results (in case XML is stale)
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
            
            h_code = name_to_code.get(home_name, "UNK")
            a_code = name_to_code.get(away_name, "UNK")
            
            if h_code != "UNK" and a_code != "UNK":
                remaining_games.append((h_code, a_code))
                    
        print(f"Found {len(remaining_games)} unplayed games to simulate.")
        
    except Exception as e:
        print(f"Error loading schedule: {e}")
        return

    # 3. Simulate
    # Seed from the round number so each round's simulations are reproducible
    # but different from every other round (not stuck at a single fixed outcome).
    _suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    _round_num = int(_suffix.replace('_R', '')) if _suffix else None
    np.random.seed(_round_num)  # None = truly random each run
    
    sim_wins = np.tile(base_wins, (num_simulations, 1))
    sim_pd = np.tile(base_pd, (num_simulations, 1))
    sim_h2h_wins = np.tile(base_h2h_wins, (num_simulations, 1, 1))
    sim_h2h_pd   = np.tile(base_h2h_pd,   (num_simulations, 1, 1))

    for h_code, a_code in remaining_games:
        h_idx = team_to_idx[h_code]
        a_idx = team_to_idx[a_code]

        # Mirror oracle prediction formula exactly:
        # 75% Adj Net diff + 25% Elo margin (Elo HCA=+50, converted to pts /25)
        h_adj = adj_net_ratings[h_idx]
        a_adj = adj_net_ratings[a_idx]
        h_elo = elo_ratings[h_idx]
        a_elo = elo_ratings[a_idx]

        adj_diff   = h_adj - a_adj
        elo_margin = (h_elo - a_elo + 50) / 25
        margin_raw = adj_diff * 0.75 + elo_margin * 0.25

        # Per-team HCA (30% team-specific, 70% global)
        team_hca   = home_net_ratings[h_idx] - net_ratings[h_idx]
        blended_hca = (hca * 0.7 + team_hca * 0.3) * 0.5
        pred_margin = margin_raw + blended_hca

        # ML win probability — same call as the oracle
        home_win_prob = predict_wp(
            margin=pred_margin,
            seconds_remaining=2400,
            elo_diff=h_elo - a_elo,
        )

        # Vectorised Bernoulli draw for win/loss
        rand = np.random.uniform(size=num_simulations)
        home_wins = (rand < home_win_prob).astype(int)
        away_wins = 1 - home_wins

        # Sample margin magnitude for point-differential tracking;
        # sign is forced to match the win/loss outcome
        mag = np.abs(np.random.normal(loc=abs(pred_margin), scale=10.0, size=num_simulations))
        margins = np.where(home_wins, mag, -mag)

        sim_wins[:, h_idx] += home_wins
        sim_wins[:, a_idx] += away_wins
        sim_pd[:, h_idx]   += margins
        sim_pd[:, a_idx]   -= margins

        # Track head-to-head results for tiebreaking
        sim_h2h_wins[:, h_idx, a_idx] += home_wins
        sim_h2h_wins[:, a_idx, h_idx] += away_wins
        sim_h2h_pd[:, h_idx, a_idx]   += margins
        sim_h2h_pd[:, a_idx, h_idx]   -= margins

    # 4. Rank and Aggregate
    print("Aggregating ranks...")
    
    # Rank using Euroleague tiebreaker rules (h2h → h2h PD → overall PD)
    team_ranks = _rank_with_h2h(sim_wins, sim_pd, sim_h2h_wins, sim_h2h_pd,
                                num_teams, num_simulations)
    
    results = {}
    for i, t in enumerate(team_list):
        ranks_for_team = team_ranks[:, i] 
        
        # REVERTED COLUMNS: Standard Cumulative Probabilities
        top4 = np.sum(ranks_for_team < 4)
        top6 = np.sum(ranks_for_team < 6)
        top10 = np.sum(ranks_for_team < 10)
        
        avg_wins = np.mean(sim_wins[:, i])
        
        # Win distribution: P(wins >= threshold) for each threshold
        win_dist = {}
        for threshold in range(15, 31):
            pct = round(np.sum(sim_wins[:, i] >= threshold) / num_simulations * 100)
            win_dist[str(threshold)] = pct
        
        # Seed distribution: P(finishing in position N) for N=1..num_teams
        seed_dist = {}
        for pos in range(num_teams):
            pct = round(np.sum(ranks_for_team == pos) / num_simulations * 100, 1)
            seed_dist[str(pos + 1)] = pct
        
        results[t] = {
            'Top4_Pct': round(top4 / num_simulations * 100, 1),
            'Top6_Pct': round(top6 / num_simulations * 100, 1),
            'Top10_Pct': round(top10 / num_simulations * 100, 1),
            'Sort_Metric': int(top6),
            'Avg_Wins': round(avg_wins, 1),
            'Current_Wins': int(base_wins[i]),
            'Win_Distribution': win_dist,
            'Seed_Distribution': seed_dist
        }

    # Sort results
    sorted_results = sorted(list(results.items()), key=lambda x: (x[1]['Sort_Metric'], x[1]['Top10_Pct']), reverse=True)
    
    final_json = []
    print("\n--- FINAL SIMULATION RESULTS ---")
    for t_tuple in sorted_results:
        t = t_tuple[0]
        data = t_tuple[1]
        final_json.append({'Team': t, **data})
        print(f"{t}: Avg Wins: {data['Avg_Wins']} | Top 4: {data['Top4_Pct']:>5.1f}% | Top 6: {data['Top6_Pct']:>5.1f}% | Top 10: {data['Top10_Pct']:>5.1f}%")

    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'monte_carlo_results{round_suffix}.json'

    with open(outfile, 'w') as f:
        json.dump(final_json, f, indent=4)
        
    print(f"\nSaved fully aggregated matrix to {outfile}!")

if __name__ == "__main__":
    run_monte_carlo(10000)
