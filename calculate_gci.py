"""
Game Control Index (GCI) — How teams win, not just that they win.

Computes per-game control metrics from Win Probability trajectory data,
aggregates into team season profiles, and generates storylines.

Usage:
    python calculate_gci.py
"""

import json
import os
import statistics

from season_config import CURRENT_SEASON


SEASON = str(CURRENT_SEASON)
WP_DATA_DIR = os.path.join("docs", "data", SEASON)
GAME_RESULTS_PATH = "mvp_game_results.json"


def load_game_results():
    """Load game metadata: teams, scores, winner per gamecode."""
    with open(GAME_RESULTS_PATH, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    games = {}
    for g in raw:
        gc = g['GameCode']
        if g.get('Winner', 'UNKNOWN') == 'UNKNOWN':
            continue
        games[gc] = {
            'home': g['LocalTeam'],
            'away': g['RoadTeam'],
            'home_score': int(g['LocalScore']),
            'away_score': int(g['RoadScore']),
            'winner': g['Winner'],
        }
    return games


def load_wp_timeline(gamecode):
    """Load WP replay timeline for a single game. Returns list of play dicts or None."""
    path = os.path.join(WP_DATA_DIR, f"{gamecode}.json")
    if not os.path.exists(path):
        return None, None, None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('timeline', []), data.get('ta'), data.get('tb')


def compute_game_metrics(timeline, winner_is_home):
    """
    Compute GCI sub-metrics from a WP timeline.

    Args:
        timeline: list of dicts with keys {e, s, a, b, w, p, d}
                  w = WP for home team (0.0 to 1.0)
                  s = seconds remaining (2400 -> 0)
                  p = period (1-4 regulation, 5+ OT)
        winner_is_home: True if home team won

    Returns:
        dict with per-game metrics, or None if insufficient data.
    """
    if not timeline or len(timeline) < 3:
        return None

    wp_values = [play['w'] for play in timeline]

    # 1. Dominance Score: mean(WP_home - 0.5)
    dominance = sum(wp - 0.5 for wp in wp_values) / len(wp_values)

    # 2. Control Duration: % of plays where the team had WP > 0.6
    #    Computed from BOTH perspectives so each team gets its own value
    control_home = sum(1 for wp in wp_values if wp > 0.6) / len(wp_values)
    control_away = sum(1 for wp in wp_values if wp < 0.4) / len(wp_values)

    # 3. Drama Index: total variation of WP curve
    drama = sum(abs(wp_values[i + 1] - wp_values[i]) for i in range(len(wp_values) - 1))

    # 4. Comeback Magnitude: 1.0 - min(winner_WP)
    if winner_is_home:
        comeback = 1.0 - min(wp_values)
    else:
        comeback = max(wp_values)  # = 1 - min(1-w) = max(w)

    # 5. Crunch-Time Swing: WP change in final 5 minutes (s <= 300)
    pre_crunch = [p for p in timeline if p['s'] > 300]
    crunch_plays = [p for p in timeline if p['s'] <= 300]
    if pre_crunch and crunch_plays:
        wp_at_5min = pre_crunch[-1]['w']
        wp_final = timeline[-1]['w']
        crunch_home = wp_final - wp_at_5min
        crunch_away = -crunch_home
    else:
        crunch_home = 0.0
        crunch_away = 0.0

    # 6. Killer Instinct: net WP change in Q4+ during plays where team was leading.
    #    Sum (not average) of WP deltas when leading — captures total close-out pressure.
    #    Positive = team extended their lead in Q4; Negative = team surrendered it.
    q4_plays = [p for p in timeline if p['p'] >= 4]
    killer_home = 0.0
    killer_away = 0.0
    for i in range(len(q4_plays) - 1):
        wp_now = q4_plays[i]['w']
        wp_next = q4_plays[i + 1]['w']
        delta = wp_next - wp_now
        if wp_now > 0.55:   # home leading
            killer_home += delta
        if wp_now < 0.45:   # away leading
            killer_away -= delta  # flip sign: positive = away extended lead

    return {
        'dominance': round(dominance, 4),
        'control_home': round(control_home, 4),
        'control_away': round(control_away, 4),
        'drama': round(drama, 4),
        'comeback': round(comeback, 4),
        'crunch_home': round(crunch_home, 4),
        'crunch_away': round(crunch_away, 4),
        'killer_home': round(killer_home, 4),
        'killer_away': round(killer_away, 4),
    }


def extract_wp_curve(timeline, max_points=40):
    """Extract a condensed WP curve for SVG rendering. Returns list of [pct_elapsed, wp] pairs."""
    if not timeline:
        return []
    total_time = timeline[0]['s']
    if total_time <= 0:
        total_time = 2400
    curve = []
    for play in timeline:
        elapsed_pct = round(1.0 - play['s'] / total_time, 4)
        curve.append([elapsed_pct, round(play['w'], 4)])
    if len(curve) > max_points:
        step = len(curve) / max_points
        curve = [curve[int(i * step)] for i in range(max_points)]
        last = [1.0, round(timeline[-1]['w'], 4)]
        if curve[-1] != last:
            curve.append(last)
    return curve


def determine_round(game_results, game_metrics):
    """Determine the current round number from game data."""
    try:
        with open('mvp_standings_derived.json', 'r', encoding='utf-8') as f:
            standings = json.load(f)
        return max((t.get('GP', 0) for t in standings.values()), default=0)
    except Exception:
        # Fallback: count max games per team
        team_counts = {}
        for gc in game_metrics:
            g = game_results.get(gc, {})
            for t in [g.get('home'), g.get('away')]:
                if t:
                    team_counts[t] = team_counts.get(t, 0) + 1
        return max(team_counts.values(), default=0) if team_counts else 0


def aggregate_team_profiles(game_results, game_metrics):
    """Aggregate per-game metrics into team season profiles."""
    teams = {}
    for gc, metrics in game_metrics.items():
        g = game_results[gc]
        home, away = g['home'], g['away']
        winner = g['winner']

        for team in [home, away]:
            if team not in teams:
                teams[team] = {
                    'games': [],
                    'wins': [],
                    'losses': [],
                    'home_games': [],
                    'away_games': [],
                }
            is_home = (team == home)
            is_winner = (team == winner)

            # Team-perspective dominance: positive = team dominated
            team_dominance = metrics['dominance'] if is_home else -metrics['dominance']

            game_entry = {
                'gamecode': gc,
                'round': gc,  # gamecodes approximate round ordering
                'opponent': away if is_home else home,
                'is_home': is_home,
                'is_win': is_winner,
                'dominance': team_dominance,
                'control': metrics['control_home'] if is_home else metrics['control_away'],
                'drama': metrics['drama'],
                'comeback': metrics['comeback'] if is_winner else 0.0,
                'crunch': metrics['crunch_home'] if is_home else metrics['crunch_away'],
                'killer': metrics['killer_home'] if is_home else metrics['killer_away'],
                'home_score': g['home_score'],
                'away_score': g['away_score'],
            }

            teams[team]['games'].append(game_entry)
            if is_winner:
                teams[team]['wins'].append(game_entry)
            else:
                teams[team]['losses'].append(game_entry)
            if is_home:
                teams[team]['home_games'].append(game_entry)
            else:
                teams[team]['away_games'].append(game_entry)

    return teams


def compute_gci_ratings(team_profiles):
    """
    Compute GCI Rating per team: weighted composite, z-normalized to 0-100.
    Weights: Dominance(35%) + Control(25%) + Crunch(20%) + Killer(20%)
    """
    raw_scores = {}
    components = {}
    for team, profile in team_profiles.items():
        games = profile['games']
        if not games:
            continue
        dom_avg = statistics.mean(g['dominance'] for g in games)
        ctrl_avg = statistics.mean(g['control'] for g in games)
        crunch_avg = statistics.mean(g['crunch'] for g in games)
        killer_avg = statistics.mean(g['killer'] for g in games)

        raw = 0.35 * dom_avg + 0.25 * ctrl_avg + 0.20 * crunch_avg + 0.20 * killer_avg
        raw_scores[team] = raw
        components[team] = {
            'dominance_avg': dom_avg,
            'control_pct': ctrl_avg,
            'crunch_swing_avg': crunch_avg,
            'killer_instinct': killer_avg,
        }

    # Z-normalize to 0-100 scale
    if len(raw_scores) < 2:
        return {t: 50.0 for t in raw_scores}, components, (0.0, 1.0)

    values = list(raw_scores.values())
    mu = statistics.mean(values)
    sigma = statistics.stdev(values)
    if sigma == 0:
        return {t: 50.0 for t in raw_scores}, components, (0.0, 1.0)

    gci_ratings = {}
    for team, raw in raw_scores.items():
        z = (raw - mu) / sigma
        # Map z-score to 0-100 (mean=50, ±3σ covers 0-100)
        gci = max(0.0, min(100.0, 50.0 + z * 16.67))
        gci_ratings[team] = round(gci, 1)

    return gci_ratings, components, (mu, sigma)


def generate_storylines(team_profiles, gci_ratings, components):
    """Generate auto-storylines for the top teams in each category.
    Each team can only win one storyline — runner-up gets the award if taken."""
    storylines = []
    used_teams = set()

    def pick_top(rankings, exclude):
        """Pick the highest-ranked team not in exclude set."""
        for team in sorted(rankings, key=rankings.get, reverse=True):
            if team not in exclude:
                return team
        return max(rankings, key=rankings.get)  # fallback: ignore exclusion

    # Dominant Force: highest GCI
    top_gci = pick_top(gci_ratings, used_teams)
    used_teams.add(top_gci)
    ctrl = components[top_gci]['control_pct']
    n_dominant_wins = sum(1 for g in team_profiles[top_gci]['wins'] if g['dominance'] > 0.15)
    storylines.append({
        'label': 'Dominant Force',
        'team': top_gci,
        'color': '#4ecdc4',
        'text': f"Controlled {ctrl * 100:.0f}% of game time on average. "
                f"{n_dominant_wins} dominant wins this season.",
        'stat_label': f"GCI {gci_ratings[top_gci]}",
        'stat_sub': '#1 Overall',
    })

    # Drama Magnets: highest average drama
    drama_avgs = {t: statistics.mean(g['drama'] for g in p['games'])
                  for t, p in team_profiles.items() if p['games']}
    top_drama = pick_top(drama_avgs, used_teams)
    used_teams.add(top_drama)
    close_games = sum(1 for g in team_profiles[top_drama]['games'] if g['drama'] > 3.0)
    storylines.append({
        'label': 'Drama Magnets',
        'team': top_drama,
        'color': '#ff6b6b',
        'text': f"Highest drama index in the league. "
                f"{close_games} high-drama games this season.",
        'stat_label': f"Drama {drama_avgs[top_drama]:.2f}",
        'stat_sub': '#1 Volatility',
    })

    # Comeback Kings: most comeback wins from below 20% WP
    comeback_counts = {}
    for team, profile in team_profiles.items():
        count = sum(1 for g in profile['wins'] if g['comeback'] > 0.80)
        comeback_counts[team] = count
    top_comeback = pick_top(comeback_counts, used_teams)
    if comeback_counts[top_comeback] > 0:
        used_teams.add(top_comeback)
        max_cb = max((g['comeback'] for g in team_profiles[top_comeback]['wins']), default=0)
        storylines.append({
            'label': 'Comeback Kings',
            'team': top_comeback,
            'color': '#ffd700',
            'text': f"{comeback_counts[top_comeback]} wins from below 20% WP. "
                    f"Largest comeback from {(1.0 - max_cb) * 100:.0f}% WP.",
            'stat_label': f"{comeback_counts[top_comeback]} Comebacks",
            'stat_sub': f"Min WP: {(1.0 - max_cb) * 100:.0f}%",
        })

    # The Closers: highest killer instinct
    killer_avgs = {t: components[t]['killer_instinct']
                   for t in components}
    top_killer = pick_top(killer_avgs, used_teams)
    used_teams.add(top_killer)
    storylines.append({
        'label': 'The Closers',
        'team': top_killer,
        'color': '#a8e6cf',
        'text': f"Best at closing out games. Average net WP gain of "
                f"+{killer_avgs[top_killer]:.2f} per game when leading in Q4.",
        'stat_label': f"Killer +{killer_avgs[top_killer]:.2f}",
        'stat_sub': '#1 Closer',
    })

    # Fortress: largest home vs away GCI gap
    home_away_gap = {}
    for team, profile in team_profiles.items():
        home_games = profile['home_games']
        away_games = profile['away_games']
        if home_games and away_games:
            home_dom = statistics.mean(g['dominance'] for g in home_games)
            away_dom = statistics.mean(g['dominance'] for g in away_games)
            home_away_gap[team] = home_dom - away_dom
    if home_away_gap:
        top_fortress = pick_top(home_away_gap, used_teams)
        used_teams.add(top_fortress)
        gap = home_away_gap[top_fortress]
        storylines.append({
            'label': 'Fortress',
            'team': top_fortress,
            'color': '#a855f7',
            'text': f"Strongest home court advantage. "
                    f"Dominance gap of {gap:.2f} between home and away.",
            'stat_label': f"Gap {gap:.2f}",
            'stat_sub': '#1 Home Court',
        })

    return storylines


def find_superlatives(game_results, game_metrics, wp_timelines):
    """Find season-best single-game performances."""
    most_dominant = None
    most_dramatic = None
    biggest_comeback = None

    for gc, metrics in game_metrics.items():
        g = game_results[gc]
        entry = {
            'gamecode': gc,
            'home': g['home'],
            'away': g['away'],
            'home_score': g['home_score'],
            'away_score': g['away_score'],
        }

        abs_dom = abs(metrics['dominance'])
        if most_dominant is None or abs_dom > abs(most_dominant['dominance']):
            most_dominant = {**entry, 'dominance': metrics['dominance'], 'value': abs_dom}

        if most_dramatic is None or metrics['drama'] > most_dramatic['drama']:
            most_dramatic = {**entry, 'drama': metrics['drama']}

        if metrics['comeback'] > 0.5:  # meaningful comeback
            if biggest_comeback is None or metrics['comeback'] > biggest_comeback['comeback']:
                winner = g['winner']
                biggest_comeback = {**entry, 'comeback': metrics['comeback'], 'winner': winner}

    return {
        'most_dominant': most_dominant,
        'most_dramatic': most_dramatic,
        'biggest_comeback': biggest_comeback,
    }


def main():
    print("\n=== Computing Game Control Index (GCI) ===")

    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')

    # Load data
    print("  Loading game results...")
    game_results = load_game_results()
    print(f"  Found {len(game_results)} completed games")

    # Compute per-game metrics
    print("  Computing per-game metrics from WP data...")
    game_metrics = {}
    wp_timelines = {}
    skipped = 0
    for gc in sorted(game_results.keys()):
        timeline, ta, tb = load_wp_timeline(gc)
        if not timeline:
            skipped += 1
            continue
        g = game_results[gc]
        winner_is_home = (g['winner'] == g['home'])
        metrics = compute_game_metrics(timeline, winner_is_home)
        if metrics:
            game_metrics[gc] = metrics
            wp_timelines[gc] = extract_wp_curve(timeline)
    print(f"  Computed metrics for {len(game_metrics)} games ({skipped} skipped)")

    if not game_metrics:
        print(f"  No WP replay data for season {SEASON} in {WP_DATA_DIR} yet - skipping GCI.")
        return

    # Aggregate team profiles
    print("  Aggregating team profiles...")
    team_profiles = aggregate_team_profiles(game_results, game_metrics)
    print(f"  {len(team_profiles)} teams")

    # Compute GCI ratings
    gci_ratings, components, (gci_mu, gci_sigma) = compute_gci_ratings(team_profiles)

    # Determine round
    round_num = determine_round(game_results, game_metrics)
    print(f"  Round: {round_num}")

    # Build per-team output
    teams_output = {}
    for team in sorted(team_profiles.keys()):
        profile = team_profiles[team]
        games = profile['games']
        wins = profile['wins']
        losses = profile['losses']
        if not games:
            continue

        drama_avg = statistics.mean(g['drama'] for g in games)
        comeback_count = sum(1 for g in wins if g['comeback'] > 0.80)
        comeback_rating = statistics.mean(g['comeback'] for g in wins) if wins else 0.0

        # Home vs away GCI: same weighted composite, z-normalized on the same scale
        def venue_raw(game_list):
            if not game_list:
                return None
            return (0.35 * statistics.mean(g['dominance'] for g in game_list)
                  + 0.25 * statistics.mean(g['control'] for g in game_list)
                  + 0.20 * statistics.mean(g['crunch'] for g in game_list)
                  + 0.20 * statistics.mean(g['killer'] for g in game_list))

        home_raw = venue_raw(profile['home_games'])
        away_raw = venue_raw(profile['away_games'])

        def raw_to_gci(raw):
            if raw is None or gci_sigma == 0:
                return 50.0
            z = (raw - gci_mu) / gci_sigma
            return round(max(0.0, min(100.0, 50.0 + z * 16.67)), 1)

        home_gci = raw_to_gci(home_raw)
        away_gci = raw_to_gci(away_raw)

        # Win quality histogram: 5 bins [0-0.1), [0.1-0.2), [0.2-0.3), [0.3-0.4), [0.4+)
        bins = [0.0, 0.1, 0.2, 0.3, 0.4, float('inf')]
        win_hist = [0] * 5
        for g in wins:
            d = abs(g['dominance'])
            for i in range(5):
                if bins[i] <= d < bins[i + 1]:
                    win_hist[i] += 1
                    break
        loss_hist = [0] * 5
        for g in losses:
            d = abs(g['dominance'])
            for i in range(5):
                if bins[i] <= d < bins[i + 1]:
                    loss_hist[i] += 1
                    break

        # Game log (sorted by gamecode as proxy for chronological order)
        game_log = []
        for g in sorted(games, key=lambda x: x['gamecode']):
            game_log.append({
                'gamecode': g['gamecode'],
                'opponent': g['opponent'],
                'is_home': g['is_home'],
                'is_win': g['is_win'],
                'dominance': round(g['dominance'], 3),
                'drama': round(g['drama'], 3),
                'home_score': g['home_score'],
                'away_score': g['away_score'],
            })

        teams_output[team] = {
            'gci': gci_ratings.get(team, 50.0),
            'dominance_avg': round(components.get(team, {}).get('dominance_avg', 0.0), 4),
            'control_pct': round(components.get(team, {}).get('control_pct', 0.0), 4),
            'crunch_swing_avg': round(components.get(team, {}).get('crunch_swing_avg', 0.0), 4),
            'killer_instinct': round(components.get(team, {}).get('killer_instinct', 0.0), 4),
            'drama_avg': round(drama_avg, 4),
            'comeback_rating': round(comeback_rating, 4),
            'comeback_count': comeback_count,
            'home_gci': round(home_gci, 4),
            'away_gci': round(away_gci, 4),
            'win_quality_hist': win_hist,
            'loss_quality_hist': loss_hist,
            'game_log': game_log,
        }

    # Generate storylines
    storylines = generate_storylines(team_profiles, gci_ratings, components)
    print(f"  Generated {len(storylines)} storylines")

    # Find superlatives
    superlatives = find_superlatives(game_results, game_metrics, wp_timelines)
    print(f"  Found superlatives")

    # Build games array for frontend
    games_output = []
    for gc in sorted(game_metrics.keys()):
        g = game_results[gc]
        m = game_metrics[gc]
        games_output.append({
            'gamecode': gc,
            'home': g['home'],
            'away': g['away'],
            'home_score': g['home_score'],
            'away_score': g['away_score'],
            'winner': g['winner'],
            'dominance': m['dominance'],
            'drama': m['drama'],
            'comeback': m['comeback'],
            'control_home': m['control_home'],
            'control_away': m['control_away'],
            'crunch_home': m['crunch_home'],
            'crunch_away': m['crunch_away'],
        })

    # Game of the Round: highest drama in the latest round's games
    # Approximate latest round: last 10 gamecodes
    latest_gcs = sorted(game_metrics.keys())[-10:]
    gor_gc = max(latest_gcs, key=lambda gc: game_metrics[gc]['drama'])
    gor_game = game_results[gor_gc]
    gor_metrics = game_metrics[gor_gc]
    game_of_round = {
        'gamecode': gor_gc,
        'round': round_num,
        'home': gor_game['home'],
        'away': gor_game['away'],
        'home_score': gor_game['home_score'],
        'away_score': gor_game['away_score'],
        'winner': gor_game['winner'],
        'drama': gor_metrics['drama'],
        'comeback': gor_metrics['comeback'],
        'crunch_home': gor_metrics['crunch_home'],
        'dominance': gor_metrics['dominance'],
        'wp_curve': wp_timelines.get(gor_gc, []),
    }

    # Also add wp_curve to superlatives
    for key in ['most_dominant', 'most_dramatic', 'biggest_comeback']:
        if superlatives.get(key) and superlatives[key].get('gamecode'):
            sc_gc = superlatives[key]['gamecode']
            superlatives[key]['wp_curve'] = wp_timelines.get(sc_gc, [])

    # Build final output
    output = {
        'season': SEASON,
        'round': round_num,
        'teams': teams_output,
        'games': games_output,
        'storylines': storylines,
        'game_of_round': game_of_round,
        'superlatives': superlatives,
    }

    # Write output
    outfile = f"gci_ratings{round_suffix}.json"
    with open(outfile, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Output: {outfile}")
    print(f"  Teams: {len(teams_output)}")
    print(f"  Games: {len(games_output)}")

    # Also write without suffix for fallback
    if round_suffix:
        with open('gci_ratings.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n=== GCI computation complete ===")


if __name__ == '__main__':
    main()
