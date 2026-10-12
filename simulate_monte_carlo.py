import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import json
import os

from season_config import CURRENT_SEASON


# ── Team-strength model ──────────────────────────────────────────────
# margin(home) = HCA + s_home - s_away + N(0, SIGMA_GAME²), s ~ N(prior, TAU²).
# Backtested on 2016-2024 (backtest_monte_carlo.py): σ²/τ² ≈ 7 pseudo-games of
# shrinkage matches how much of an early-season margin actually persists.
SIGMA_GAME = 12.0     # residual sd of a single game's margin (pts)
TAU_STRENGTH = 4.5    # sd of true team strength around its preseason prior (pts/game)
HCA_PTS = 3.0         # home-court advantage (pts)
ELO_PER_POINT = 25.0  # Elo points per point of margin, for the preseason prior


def posterior_strength(num_teams, games, prior_mean,
                       sigma=SIGMA_GAME, tau=TAU_STRENGTH, hca=HCA_PTS):
    """Posterior mean and covariance of team strengths (pts/game vs average).

    games: iterable of (home_idx, away_idx, home_margin). Opponent strength and
    venue are both accounted for, so a home-heavy or soft early schedule does
    not inflate a team's rating.
    """
    prior_mean = np.asarray(prior_mean, dtype=float)
    precision = np.eye(num_teams) / tau ** 2
    b = prior_mean / tau ** 2
    for h, a, margin in games:
        x = np.zeros(num_teams)
        x[h], x[a] = 1.0, -1.0
        precision += np.outer(x, x) / sigma ** 2
        b = b + x * (margin - hca) / sigma ** 2
    cov = np.linalg.inv(precision)
    cov = (cov + cov.T) / 2   # exact symmetry for multivariate_normal
    return cov @ b, cov


def simulate_season(num_teams, played, remaining, prior_mean, num_simulations, rng,
                    sigma=SIGMA_GAME, tau=TAU_STRENGTH, hca=HCA_PTS):
    """Simulate the rest of the regular season.

    played:    list of (home_idx, away_idx, home_pts, away_pts)
    remaining: list of (home_idx, away_idx)
    Each simulation draws one strength vector from the posterior, so the
    uncertainty about how good a team really is carries through all of its
    remaining games. Returns (team_ranks, sim_wins), both (sims, teams).
    """
    base_wins = np.zeros(num_teams)
    base_pd = np.zeros(num_teams)
    base_h2h_wins = np.zeros((num_teams, num_teams))
    base_h2h_pd = np.zeros((num_teams, num_teams))
    for h, a, hp, ap in played:
        m = hp - ap
        winner, loser = (h, a) if m > 0 else (a, h)
        base_wins[winner] += 1
        base_h2h_wins[winner, loser] += 1
        base_pd[h] += m
        base_pd[a] -= m
        base_h2h_pd[h, a] += m
        base_h2h_pd[a, h] -= m

    mean, cov = posterior_strength(num_teams, [(h, a, hp - ap) for h, a, hp, ap in played],
                                   prior_mean, sigma, tau, hca)
    strengths = rng.multivariate_normal(mean, cov, size=num_simulations)

    sim_wins = np.tile(base_wins, (num_simulations, 1))
    sim_pd = np.tile(base_pd, (num_simulations, 1))
    sim_h2h_wins = np.tile(base_h2h_wins, (num_simulations, 1, 1))
    sim_h2h_pd = np.tile(base_h2h_pd, (num_simulations, 1, 1))

    for h, a in remaining:
        margins = rng.normal(strengths[:, h] - strengths[:, a] + hca, sigma)
        home_wins = (margins > 0).astype(int)
        away_wins = 1 - home_wins
        sim_wins[:, h] += home_wins
        sim_wins[:, a] += away_wins
        sim_pd[:, h] += margins
        sim_pd[:, a] -= margins
        sim_h2h_wins[:, h, a] += home_wins
        sim_h2h_wins[:, a, h] += away_wins
        sim_h2h_pd[:, h, a] += margins
        sim_h2h_pd[:, a, h] -= margins

    team_ranks = _rank_with_h2h(sim_wins, sim_pd, sim_h2h_wins, sim_h2h_pd,
                                num_teams, num_simulations)
    return team_ranks, sim_wins


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

    from team_aliases import NAME_TO_CODE as name_to_code
    from calculate_elo import STARTING_ELO, _load_prior_season_elos

    # 1. Schedule: the regular season's fixtures define teams and gamecodes
    try:
        items = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml').getroot().findall('item')
    except Exception as e:
        print(f"Error loading schedule: {e}")
        return
    fixtures = []  # (gamecode, home, away, xml_played)
    for item in items:
        gc_text = item.find('gamecode').text
        gc = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
        h = name_to_code.get(item.find('hometeam').text, "UNK")
        a = name_to_code.get(item.find('awayteam').text, "UNK")
        played_el = item.find('played')
        xml_played = played_el is not None and (played_el.text or '').lower() == 'true'
        if h != "UNK" and a != "UNK":
            fixtures.append((gc, h, a, xml_played))
    team_list = sorted({t for _, h, a, _ in fixtures for t in (h, a)})
    team_to_idx = {t: i for i, t in enumerate(team_list)}
    num_teams = len(team_list)
    rs_codes = {gc for gc, _, _, _ in fixtures}

    # 2. Results: regular-season games only (gamecodes that are in the RS schedule)
    game_scores = {}
    if os.path.exists('mvp_game_results.json'):
        df = pd.read_json('mvp_game_results.json')
        if len(df):
            df = df[(df['LocalScore'] > 0) & (df['RoadScore'] > 0) & (df['GameCode'].isin(rs_codes))]
            for _, row in df.iterrows():
                game_scores[int(row['GameCode'])] = (row['LocalTeam'], row['RoadTeam'],
                                                 int(row['LocalScore']), int(row['RoadScore']))
    played = [(team_to_idx[h], team_to_idx[a], hp, ap)
              for h, a, hp, ap in game_scores.values() if h in team_to_idx and a in team_to_idx]
    # A game counts as played if we have its score, or the XML says so (stale-XML guard
    # is the score check; an XML-played game without a score is skipped, not simulated)
    remaining = [(team_to_idx[h], team_to_idx[a]) for gc, h, a, xml_played in fixtures
                 if gc not in game_scores and not xml_played]
    print(f"Loaded {num_teams} teams, {len(played)} played games, "
          f"{len(remaining)} unplayed games to simulate.")

    # 3. Preseason prior: last season's Elo with regression to the mean
    prior_elos = _load_prior_season_elos(CURRENT_SEASON)
    prior_mean = np.array([(prior_elos.get(t, STARTING_ELO) - STARTING_ELO) / ELO_PER_POINT
                           for t in team_list])

    # 4. Simulate. Seed from the round number so each round is reproducible.
    _suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    _round_num = int(_suffix.replace('_R', '')) if _suffix else None
    rng = np.random.default_rng(_round_num)  # None = truly random each run
    team_ranks, sim_wins = simulate_season(num_teams, played, remaining, prior_mean,
                                           num_simulations, rng)
    base_wins = np.zeros(num_teams)
    for h, a, hp, ap in played:
        base_wins[h if hp > ap else a] += 1
    print("Aggregating ranks...")

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
