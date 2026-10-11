"""
Historical GCI Trends — cross-season Game Control Index analysis.

Processes all completed seasons (2007-2024) of WP replay data,
derives game results directly from WP replay files, and computes
per-season GCI, league-wide trends, per-team trends, era breakdowns,
superlatives, and season leaderboards.

No main() — see Task 4 for the CLI entry point.
"""

import json
import os
import statistics

from season_config import COMPLETED_SEASONS

from calculate_gci import (
    compute_game_metrics,
    aggregate_team_profiles,
    compute_gci_ratings,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEASONS = COMPLETED_SEASONS
WP_DATA_ROOT = os.path.join("docs", "data")
OUTPUT_PATH = os.path.join("docs", "gci_historical.json")

ERA_DEFINITIONS = [
    {"name": "Expansion Era",   "start": 2007, "end": 2015},
    {"name": "Contraction Era", "start": 2016, "end": 2019},
    {"name": "Modern Era",      "start": 2020, "end": 2024},
]


# ---------------------------------------------------------------------------
# Phase 1: Load season data
# ---------------------------------------------------------------------------

def load_season_games(season_dir):
    """
    Load all WP replay files from season_dir.

    Derives game results (teams, scores, winner) directly from each
    replay file — no dependency on mvp_game_results.json.

    Args:
        season_dir: path to a directory containing {gamecode}.json files.

    Returns:
        (games, timelines)
        games:     dict gamecode → {home, away, home_score, away_score, winner}
        timelines: dict gamecode → full timeline list
    """
    games = {}
    timelines = {}

    if not os.path.isdir(season_dir):
        return games, timelines

    for fname in os.listdir(season_dir):
        if not fname.endswith('.json'):
            continue
        gamecode = fname[:-5]  # strip .json
        path = os.path.join(season_dir, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        # Skip non-dict files (e.g. games.json which is a list)
        if not isinstance(data, dict):
            continue

        ta = data.get('ta')
        tb = data.get('tb')
        timeline = data.get('timeline', [])

        # Need at least 3 entries to compute meaningful metrics
        if not timeline or len(timeline) < 3 or not ta or not tb:
            continue

        # Derive result from the final timeline entry.
        # Some replay files have a corrupted "Final Buzzer" entry where
        # scores drop below the penultimate entry.  In those cases, use
        # the penultimate entry for scores and the final entry only for WP.
        last = timeline[-1]
        home_score = last.get('a', 0)
        away_score = last.get('b', 0)
        final_wp = last.get('w', 0.5)

        if len(timeline) >= 2:
            prev = timeline[-2]
            prev_a = prev.get('a', 0)
            prev_b = prev.get('b', 0)
            if home_score < prev_a or away_score < prev_b:
                # Corrupted "Final Buzzer" entry — take scores and WP
                # from the penultimate entry, and strip the bad entry
                # from the timeline so compute_game_metrics doesn't
                # see the spurious WP jump.
                home_score = prev_a
                away_score = prev_b
                final_wp = prev.get('w', final_wp)
                timeline = timeline[:-1]

        # Winner determined by final WP: 1.0 → home won, 0.0 → away won
        # For OT games the model also converges to 1 or 0.
        winner = ta if final_wp >= 0.5 else tb

        games[gamecode] = {
            'home': ta,
            'away': tb,
            'home_score': int(home_score),
            'away_score': int(away_score),
            'winner': winner,
        }
        timelines[gamecode] = timeline

    return games, timelines


# ---------------------------------------------------------------------------
# Phase 2: Single-season GCI
# ---------------------------------------------------------------------------

def compute_season_gci(games, timelines):
    """
    Run the full GCI pipeline for one season.

    Args:
        games:     dict from load_season_games
        timelines: dict from load_season_games

    Returns:
        dict with keys:
            gci_ratings   – team → float (0-100)
            components    – team → {dominance_avg, control_pct, crunch_swing_avg, killer_instinct}
            team_profiles – team → profile dict (from aggregate_team_profiles)
            game_metrics  – gamecode → metrics dict
            games         – list of game dicts for output
    """
    if not games:
        return {
            'gci_ratings': {},
            'components': {},
            'team_profiles': {},
            'game_metrics': {},
            'games': [],
        }

    # Compute per-game metrics
    game_metrics = {}
    for gc, g in games.items():
        tl = timelines.get(gc)
        if not tl:
            continue
        winner_is_home = (g['winner'] == g['home'])
        metrics = compute_game_metrics(tl, winner_is_home)
        if metrics:
            game_metrics[gc] = metrics

    # Aggregate team profiles
    team_profiles = aggregate_team_profiles(game_metrics=game_metrics, game_results=games)

    # Compute GCI ratings
    gci_ratings, components, _ = compute_gci_ratings(team_profiles)

    # Build flat games list
    games_list = []
    for gc in sorted(game_metrics.keys()):
        g = games[gc]
        m = game_metrics[gc]
        games_list.append({
            'gamecode': gc,
            'home': g['home'],
            'away': g['away'],
            'home_score': g['home_score'],
            'away_score': g['away_score'],
            'winner': g['winner'],
            'drama': m['drama'],
            'dominance': m['dominance'],
            'comeback': m['comeback'],
            'control_home': m['control_home'],
            'control_away': m['control_away'],
        })

    return {
        'gci_ratings': gci_ratings,
        'components': components,
        'team_profiles': team_profiles,
        'game_metrics': game_metrics,
        'games': games_list,
    }


# ---------------------------------------------------------------------------
# Phase 3: Cross-season aggregations
# ---------------------------------------------------------------------------

def compute_league_trends(season_results):
    """
    Compute league-wide trend arrays across all seasons.

    Args:
        season_results: dict season_year → compute_season_gci result

    Returns:
        dict with parallel arrays (sorted by season year):
            seasons        – list[int]
            avg_drama      – list[float]  average drama per game per season
            comeback_count – list[int]    games with comeback > 0.80 per season
            avg_gci_spread – list[float]  max(GCI) - min(GCI) per season
            game_count     – list[int]    total games per season
    """
    if not season_results:
        return {
            'seasons': [],
            'avg_drama': [],
            'comeback_count': [],
            'avg_gci_spread': [],
            'game_count': [],
        }

    sorted_seasons = sorted(season_results.keys())

    seasons = []
    avg_drama = []
    comeback_count = []
    avg_gci_spread = []
    game_count = []

    for s in sorted_seasons:
        sr = season_results[s]
        metrics = sr.get('game_metrics', {})
        ratings = sr.get('gci_ratings', {})

        seasons.append(s)

        # Average drama
        dramas = [m['drama'] for m in metrics.values()]
        avg_drama.append(round(statistics.mean(dramas), 4) if dramas else 0.0)

        # Comeback count: games with comeback > 0.80
        # Iterate game_metrics directly — comeback there reflects the winner's CB magnitude
        comebacks = sum(1 for m in metrics.values() if m.get('comeback', 0) > 0.80)
        comeback_count.append(comebacks)

        # GCI spread
        if len(ratings) >= 2:
            spread = max(ratings.values()) - min(ratings.values())
        elif len(ratings) == 1:
            spread = 0.0
        else:
            spread = 0.0
        avg_gci_spread.append(round(spread, 2))

        # Game count
        game_count.append(len(metrics))

    return {
        'seasons': seasons,
        'avg_drama': avg_drama,
        'comeback_count': comeback_count,
        'avg_gci_spread': avg_gci_spread,
        'game_count': game_count,
    }


def compute_team_trends(season_results, min_seasons=3):
    """
    Compute per-team trend arrays across seasons in which each team appeared.

    Args:
        season_results: dict season_year → compute_season_gci result
        min_seasons:    minimum appearances required for inclusion

    Returns:
        dict team_code → {
            seasons:         list[int]   (sorted)
            gci:             list[float]
            win_pct:         list[float]
            avg_drama:       list[float]
            dominance_avg:   list[float]
            killer_instinct: list[float]
            comeback_count:  list[int]
        }
    """
    # Collect all team data points keyed by (team, season)
    # Each entry: (season, gci, win_pct, avg_drama, dominance_avg, killer_instinct, comeback_count)
    team_data = {}

    for season in sorted(season_results.keys()):
        sr = season_results[season]
        ratings = sr.get('gci_ratings', {})
        profiles = sr.get('team_profiles', {})
        components = sr.get('components', {})

        for team, gci in ratings.items():
            profile = profiles.get(team, {})
            comp = components.get(team, {})
            all_games = profile.get('games', [])
            wins = profile.get('wins', [])

            n_games = len(all_games)
            win_pct = len(wins) / n_games if n_games > 0 else 0.0

            dramas = [g['drama'] for g in all_games]
            avg_drama = statistics.mean(dramas) if dramas else 0.0

            dominance_avg = comp.get('dominance_avg', 0.0)
            killer_instinct = comp.get('killer_instinct', 0.0)
            comeback_count = sum(1 for g in wins if g.get('comeback', 0) > 0.80)

            if team not in team_data:
                team_data[team] = []
            team_data[team].append((
                season,
                round(gci, 1),
                round(win_pct, 4),
                round(avg_drama, 4),
                round(dominance_avg, 4),
                round(killer_instinct, 4),
                comeback_count,
            ))

    # Filter by min_seasons and build output arrays
    result = {}
    for team, entries in team_data.items():
        if len(entries) < min_seasons:
            continue
        entries_sorted = sorted(entries, key=lambda x: x[0])
        result[team] = {
            'seasons':         [e[0] for e in entries_sorted],
            'gci':             [e[1] for e in entries_sorted],
            'win_pct':         [e[2] for e in entries_sorted],
            'avg_drama':       [e[3] for e in entries_sorted],
            'dominance_avg':   [e[4] for e in entries_sorted],
            'killer_instinct': [e[5] for e in entries_sorted],
            'comeback_count':  [e[6] for e in entries_sorted],
        }

    return result


def compute_era_breakdowns(season_results):
    """
    Aggregate GCI metrics by era.

    Args:
        season_results: dict season_year → compute_season_gci result

    Returns:
        list of era dicts:
            {name, start, end, avg_drama, avg_comeback_rate, total_games, seasons_included}
    """
    output = []
    for era in ERA_DEFINITIONS:
        era_seasons = [
            sr for year, sr in season_results.items()
            if era['start'] <= year <= era['end']
        ]

        all_dramas = []
        total_comebacks = 0
        total_games = 0

        for sr in era_seasons:
            metrics = sr.get('game_metrics', {})
            for m in metrics.values():
                all_dramas.append(m.get('drama', 0.0))
                if m.get('comeback', 0) > 0.80:
                    total_comebacks += 1
                total_games += 1

        avg_drama = round(statistics.mean(all_dramas), 4) if all_dramas else 0.0
        comeback_rate = round(total_comebacks / total_games, 4) if total_games > 0 else 0.0

        output.append({
            'name': era['name'],
            'start': era['start'],
            'end': era['end'],
            'avg_drama': avg_drama,
            'avg_comeback_rate': comeback_rate,
            'total_games': total_games,
            'seasons_included': len(era_seasons),
        })

    return output


# ---------------------------------------------------------------------------
# Phase 4: Superlatives and leaderboards
# ---------------------------------------------------------------------------

def find_historical_superlatives(season_results):
    """
    Find all-time single-game and single-season records across all seasons.

    Returns:
        dict with 4 keys:
            most_dramatic   – {gamecode, season, home, away, home_score, away_score, drama}
            most_dominant   – {gamecode, season, home, away, dominance, value}
            biggest_comeback – {gamecode, season, home, away, comeback, winner}
            highest_gci     – {season, team, gci}
    """
    most_dramatic = None
    most_dominant = None
    biggest_comeback = None
    highest_gci_entry = None

    for season, sr in season_results.items():
        games_list = sr.get('games', [])
        ratings = sr.get('gci_ratings', {})

        # Game-level superlatives
        games_by_code = {g['gamecode']: g for g in games_list}
        metrics = sr.get('game_metrics', {})

        for gc, m in metrics.items():
            g = games_by_code.get(gc, {})
            entry_base = {
                'gamecode': gc,
                'season': season,
                'home': g.get('home', ''),
                'away': g.get('away', ''),
                'home_score': g.get('home_score', 0),
                'away_score': g.get('away_score', 0),
            }

            # Most dramatic
            if most_dramatic is None or m['drama'] > most_dramatic['drama']:
                most_dramatic = {**entry_base, 'drama': m['drama']}

            # Most dominant (by absolute dominance)
            abs_dom = abs(m['dominance'])
            if most_dominant is None or abs_dom > abs(most_dominant['dominance']):
                most_dominant = {**entry_base, 'dominance': m['dominance'], 'value': abs_dom}

            # Biggest comeback (threshold: > 0.5)
            if m['comeback'] > 0.5:
                if biggest_comeback is None or m['comeback'] > biggest_comeback['comeback']:
                    biggest_comeback = {
                        **entry_base,
                        'comeback': m['comeback'],
                        'winner': g.get('winner', ''),
                    }

        # Season-level superlative: highest GCI
        for team, gci in ratings.items():
            if highest_gci_entry is None or gci > highest_gci_entry['gci']:
                highest_gci_entry = {'season': season, 'team': team, 'gci': gci}

    return {
        'most_dramatic': most_dramatic,
        'most_dominant': most_dominant,
        'biggest_comeback': biggest_comeback,
        'highest_gci': highest_gci_entry,
    }


def build_season_leaderboards(season_results, top_n=5):
    """
    Build per-season team leaderboard lists for key metrics.

    Args:
        season_results: dict season_year → compute_season_gci result
        top_n:          number of teams to include per category

    Returns:
        dict season_year → {
            top_gci:      list of {team, gci}  (descending)
            top_drama:    list of {team, avg_drama}  (descending)
            top_comeback: list of {team, comeback_count}  (descending)
            top_killer:   list of {team, killer_instinct}  (descending)
        }
    """
    leaderboards = {}

    for season, sr in season_results.items():
        ratings = sr.get('gci_ratings', {})
        components = sr.get('components', {})
        profiles = sr.get('team_profiles', {})

        # Top GCI
        top_gci = [
            {'team': t, 'gci': round(gci, 1)}
            for t, gci in sorted(ratings.items(), key=lambda x: x[1], reverse=True)
        ][:top_n]

        # Top drama (average drama per game)
        drama_avgs = {}
        for team, profile in profiles.items():
            games = profile.get('games', [])
            if games:
                drama_avgs[team] = round(statistics.mean(g['drama'] for g in games), 4)
        top_drama = [
            {'team': t, 'avg_drama': v}
            for t, v in sorted(drama_avgs.items(), key=lambda x: x[1], reverse=True)
        ][:top_n]

        # Top comeback: count of wins from below 20% WP (comeback > 0.80)
        comeback_counts = {}
        for team, profile in profiles.items():
            wins = profile.get('wins', [])
            comeback_counts[team] = sum(1 for g in wins if g.get('comeback', 0) > 0.80)
        top_comeback = [
            {'team': t, 'comeback_count': v}
            for t, v in sorted(comeback_counts.items(), key=lambda x: x[1], reverse=True)
            if v > 0
        ][:top_n]

        # Top killer instinct
        killer_avgs = {
            t: round(comp.get('killer_instinct', 0.0), 4)
            for t, comp in components.items()
        }
        top_killer = [
            {'team': t, 'killer_instinct': v}
            for t, v in sorted(killer_avgs.items(), key=lambda x: x[1], reverse=True)
        ][:top_n]

        leaderboards[season] = {
            'top_gci': top_gci,
            'top_drama': top_drama,
            'top_comeback': top_comeback,
            'top_killer': top_killer,
        }

    return leaderboards


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n=== Computing Historical GCI Trends ===")
    print(f"  Seasons: {SEASONS[0]}–{SEASONS[-1]} ({len(SEASONS)} seasons)")

    season_results = {}
    total_games = 0

    for season in SEASONS:
        season_dir = os.path.join(WP_DATA_ROOT, str(season))
        if not os.path.exists(season_dir):
            print(f"  {season}: directory not found, skipping")
            continue

        games, timelines = load_season_games(season_dir)
        if not games:
            print(f"  {season}: no valid games, skipping")
            continue

        result = compute_season_gci(games, timelines)
        season_results[season] = result
        n_games = len(result['game_metrics'])
        n_teams = len(result['gci_ratings'])
        total_games += n_games
        print(f"  {season}: {n_games} games, {n_teams} teams")

    print(f"\n  Total: {total_games} games across {len(season_results)} seasons")

    # Cross-season aggregation
    print("  Computing league trends...")
    league_trends = compute_league_trends(season_results)

    print("  Computing team trends...")
    team_trends = compute_team_trends(season_results, min_seasons=3)
    print(f"  {len(team_trends)} teams with 3+ seasons")

    print("  Computing era breakdowns...")
    eras = compute_era_breakdowns(season_results)

    print("  Finding historical superlatives...")
    superlatives = find_historical_superlatives(season_results)

    print("  Building season leaderboards...")
    leaderboards = build_season_leaderboards(season_results)

    # Build output
    from datetime import date
    output = {
        'generated': date.today().isoformat(),
        'seasons_computed': sorted(season_results.keys()),
        'total_games': total_games,
        'league_trends': league_trends,
        'eras': eras,
        'team_trends': team_trends,
        'season_leaderboards': leaderboards,
        'superlatives': superlatives,
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Output: {OUTPUT_PATH}")
    print(f"  File size: {os.path.getsize(OUTPUT_PATH) / 1024:.0f} KB")
    print("\n=== Historical GCI computation complete ===")


if __name__ == '__main__':
    main()
