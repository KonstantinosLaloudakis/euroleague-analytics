# Game Control Index (GCI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Game Control Index that captures how teams win using Win Probability trajectory analysis, delivered as a new frontend page with narrative-first layout.

**Architecture:** Python compute script (`calculate_gci.py`) reads existing WP replay JSON files and game metadata, computes 6 per-game sub-metrics, aggregates into team season profiles with auto-generated storylines, and outputs `gci_ratings.json`. The export pipeline adds this to `dashboard.json`. A new vanilla JS page (`game-control.html`) renders storyline cards, game-of-the-round, scatter plot, leaderboard, and team deep-dive.

**Tech Stack:** Python 3 (json, os, math, statistics), Plotly.js (scatter + bar charts), inline SVG (radar chart, mini WP curves), vanilla HTML/JS following existing dark-theme patterns.

---

## File Structure

**Create:**
- `calculate_gci.py` — Core GCI computation engine (reads WP replay data, outputs gci_ratings.json)
- `docs/game-control.html` — Frontend page with narrative-first layout
- `docs/game-control.js` — Frontend logic: data loading, rendering, interactivity

**Modify:**
- `refresh_all.py:145` — Add GCI compute step in Phase 2 after RAPM
- `export_dashboard_data.py:891,1118-1133` — Load gci_ratings.json, add `game_control` key to output
- `docs/about.html:276` — Add GCI methodology section after Playmaking Network entry
- `docs/index.html`, `docs/team.html`, `docs/players.html`, `docs/h2h.html`, `docs/recap.html`, `docs/shots.html`, `docs/network.html`, `docs/replay.html`, `docs/playoffs.html`, `docs/mvp.html`, `docs/about.html` — Add "Game Control" nav link

---

### Task 1: `calculate_gci.py` — Per-game metric computation

**Files:**
- Create: `calculate_gci.py`

- [ ] **Step 1: Create script with imports, constants, and data loading**

```python
"""
Game Control Index (GCI) — How teams win, not just that they win.

Computes per-game control metrics from Win Probability trajectory data,
aggregates into team season profiles, and generates storylines.

Usage:
    python calculate_gci.py
"""

import json
import os
import math
import statistics


SEASON = "2025"
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
```

- [ ] **Step 2: Write `compute_game_metrics()` function**

This is the core algorithm that computes all 6 sub-metrics from a WP timeline.

```python
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
    #    Positive = home dominated, Negative = away dominated
    dominance = sum(wp - 0.5 for wp in wp_values) / len(wp_values)

    # 2. Control Duration: % of plays where the team had WP > 0.6
    #    Computed from BOTH perspectives so each team gets its own value
    control_home = sum(1 for wp in wp_values if wp > 0.6) / len(wp_values)
    control_away = sum(1 for wp in wp_values if wp < 0.4) / len(wp_values)

    # 3. Drama Index: total variation of WP curve
    drama = sum(abs(wp_values[i + 1] - wp_values[i]) for i in range(len(wp_values) - 1))

    # 4. Comeback Magnitude: 1.0 - min(winner_WP)
    #    If winner is home: min winner WP = min(w)
    #    If winner is away: winner WP = 1-w, so min winner WP = 1-max(w)
    if winner_is_home:
        comeback = 1.0 - min(wp_values)
    else:
        comeback = max(wp_values)  # = 1.0 - (1.0 - max(w)) = max(w)... NO
        # Away winner WP = 1 - w_home.  min(away WP) = 1 - max(w_home).
        # Comeback = 1 - min(away WP) = 1 - (1 - max(w_home)) = max(w_home)
        comeback = max(wp_values)

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

    # 6. Killer Instinct: avg WP delta in Q4+ when leading with WP > 0.6
    #    Home perspective
    q4_plays = [p for p in timeline if p['p'] >= 4]
    killer_home_deltas = []
    killer_away_deltas = []
    for i in range(len(q4_plays) - 1):
        wp_now = q4_plays[i]['w']
        wp_next = q4_plays[i + 1]['w']
        if wp_now > 0.6:  # home leading comfortably
            killer_home_deltas.append(wp_next - wp_now)
        if wp_now < 0.4:  # away leading comfortably (away WP > 0.6)
            killer_away_deltas.append(wp_now - wp_next)  # positive = away extending lead

    killer_home = statistics.mean(killer_home_deltas) if killer_home_deltas else 0.0
    killer_away = statistics.mean(killer_away_deltas) if killer_away_deltas else 0.0

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
```

- [ ] **Step 3: Write `extract_wp_curve()` helper for mini WP visualizations**

```python
def extract_wp_curve(timeline, max_points=40):
    """Extract a condensed WP curve for SVG rendering. Returns list of [pct_elapsed, wp] pairs."""
    if not timeline:
        return []
    total_time = timeline[0]['s']  # seconds remaining at start ~ total game time
    if total_time <= 0:
        total_time = 2400
    curve = []
    for play in timeline:
        elapsed_pct = round(1.0 - play['s'] / total_time, 4)
        curve.append([elapsed_pct, round(play['w'], 4)])
    # Downsample if too many points
    if len(curve) > max_points:
        step = len(curve) / max_points
        curve = [curve[int(i * step)] for i in range(max_points)]
        # Always include last point
        last = [1.0, round(timeline[-1]['w'], 4)]
        if curve[-1] != last:
            curve.append(last)
    return curve
```

- [ ] **Step 4: Run on a single game to verify**

Run:
```bash
.venv/Scripts/python.exe -c "
from calculate_gci import load_game_results, load_wp_timeline, compute_game_metrics, extract_wp_curve
games = load_game_results()
g = games[1]
timeline, ta, tb = load_wp_timeline(1)
winner_is_home = (g['winner'] == g['home'])
metrics = compute_game_metrics(timeline, winner_is_home)
print('Game:', g)
print('Metrics:', metrics)
curve = extract_wp_curve(timeline)
print('WP curve points:', len(curve))
print('First 3:', curve[:3])
"
```

Expected: metric values printed with no errors. Dominance should be positive (IST won at home 85-78).

- [ ] **Step 5: Commit**

```bash
git add calculate_gci.py
git commit -m "feat: add calculate_gci.py with per-game metric computation"
```

---

### Task 2: `calculate_gci.py` — Team aggregation, GCI rating, storylines, and output

**Files:**
- Modify: `calculate_gci.py`

- [ ] **Step 1: Write `determine_round()` helper**

Add above `main()`:

```python
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
```

- [ ] **Step 2: Write `aggregate_team_profiles()` and `compute_gci_ratings()`**

Add below `determine_round()`:

```python
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
        return {t: 50.0 for t in raw_scores}, components

    values = list(raw_scores.values())
    mu = statistics.mean(values)
    sigma = statistics.stdev(values)
    if sigma == 0:
        return {t: 50.0 for t in raw_scores}, components

    gci_ratings = {}
    for team, raw in raw_scores.items():
        z = (raw - mu) / sigma
        # Map z-score to 0-100 (mean=50, ±3σ covers 0-100)
        gci = max(0.0, min(100.0, 50.0 + z * 16.67))
        gci_ratings[team] = round(gci, 1)

    return gci_ratings, components
```

- [ ] **Step 3: Write `generate_storylines()` and `find_superlatives()`**

```python
def generate_storylines(team_profiles, gci_ratings, components):
    """Generate auto-storylines for the top teams in each category."""
    storylines = []

    # Dominant Force: highest GCI
    top_gci = max(gci_ratings, key=gci_ratings.get)
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
    top_drama = max(drama_avgs, key=drama_avgs.get)
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
    top_comeback = max(comeback_counts, key=comeback_counts.get)
    if comeback_counts[top_comeback] > 0:
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
    top_killer = max(killer_avgs, key=killer_avgs.get)
    storylines.append({
        'label': 'The Closers',
        'team': top_killer,
        'color': '#a8e6cf',
        'text': f"Highest killer instinct rating. When ahead in Q4, "
                f"WP rises +{killer_avgs[top_killer]:.2f} on average.",
        'stat_label': f"Killer {killer_avgs[top_killer]:.2f}",
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
        top_fortress = max(home_away_gap, key=home_away_gap.get)
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
            'wp_curve': wp_timelines.get(gc, []),
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
```

- [ ] **Step 4: Write `main()` function to tie everything together**

```python
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

    # Aggregate team profiles
    print("  Aggregating team profiles...")
    team_profiles = aggregate_team_profiles(game_results, game_metrics)
    print(f"  {len(team_profiles)} teams")

    # Compute GCI ratings
    gci_ratings, components = compute_gci_ratings(team_profiles)

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

        # Home vs away GCI (simplified: average dominance)
        home_doms = [g['dominance'] for g in profile['home_games']]
        away_doms = [g['dominance'] for g in profile['away_games']]
        home_gci = statistics.mean(home_doms) if home_doms else 0.0
        away_gci = statistics.mean(away_doms) if away_doms else 0.0

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
```

- [ ] **Step 5: Run the full script and verify output**

Run:
```bash
.venv/Scripts/python.exe calculate_gci.py
```

Expected output:
```
=== Computing Game Control Index (GCI) ===
  Loading game results...
  Found ~340+ completed games
  Computing per-game metrics from WP data...
  Computed metrics for ~340+ games
  Aggregating team profiles...
  20 teams
  Round: 37
  Generated 5 storylines
  Found superlatives
  Output: gci_ratings.json
  Teams: 20
  Games: ~340+
=== GCI computation complete ===
```

Then verify the output:
```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('gci_ratings.json'))
print('Keys:', list(d.keys()))
print('Teams:', len(d['teams']))
print('Games:', len(d['games']))
print('Storylines:', [(s['label'], s['team']) for s in d['storylines']])
# Print top 5 by GCI
ranked = sorted(d['teams'].items(), key=lambda x: -x[1]['gci'])
for team, data in ranked[:5]:
    print(f'  {team}: GCI={data[\"gci\"]}, Dom={data[\"dominance_avg\"]:.3f}, Ctrl={data[\"control_pct\"]:.1%}')
"
```

- [ ] **Step 6: Commit**

```bash
git add calculate_gci.py gci_ratings.json
git commit -m "feat: complete calculate_gci.py with team aggregation, storylines, and JSON output"
```

---

### Task 3: Pipeline integration

**Files:**
- Modify: `refresh_all.py:145`
- Modify: `export_dashboard_data.py:891,1118-1133`

- [ ] **Step 1: Add GCI to Phase 2 in `refresh_all.py`**

In `refresh_all.py`, after the RAPM step (line 145), add the GCI step:

```python
        results.append(('RAPM Ratings', run_step(
            'Computing Regularized Adjusted Plus-Minus (RAPM)',
            'calculate_rapm.py'
        )))
        results.append(('GCI Ratings', run_step(
            'Computing Game Control Index (GCI)',
            'calculate_gci.py'
        )))
```

The new code to insert after line 145:
```python
        results.append(('GCI Ratings', run_step(
            'Computing Game Control Index (GCI)',
            'calculate_gci.py'
        )))
```

- [ ] **Step 2: Add GCI loading and export in `export_dashboard_data.py`**

In `export_dashboard_data.py`, after loading WIR ratings (~line 1116), add:

```python
    # ── Load GCI ratings ─────────────────────────────────────────────────
    gci_raw = load_with_fallback(suffix, 'gci_ratings.json')
    gci_data = None
    if gci_raw:
        gci_data = {
            'teams': gci_raw.get('teams', {}),
            'games': gci_raw.get('games', []),
            'storylines': gci_raw.get('storylines', []),
            'game_of_round': gci_raw.get('game_of_round', {}),
            'superlatives': gci_raw.get('superlatives', {}),
        }
        # Also add GCI to each team object
        for team_obj in teams:
            code = team_obj['team']
            tgci = gci_raw.get('teams', {}).get(code, {})
            team_obj['gci'] = tgci.get('gci', 0.0)
            team_obj['drama_avg'] = round(tgci.get('drama_avg', 0.0), 2)
            team_obj['comeback_count'] = tgci.get('comeback_count', 0)
        print(f"  GCI ratings: {len(gci_raw.get('teams', {}))} teams")
    else:
        gci_data = None
```

Then in the output dict (around line 1133), add the `game_control` key:

```python
    output = {
        'round': round_num,
        'updated': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'teams': teams,
        'mvp': mvp_list,
        'mvp_race': mvp_race,
        'player_stats': player_stats,
        'rapm': rapm_data,
        'wpa': wpa_data,
        'tpm': tpm_data,
        'wir': wir_data,
        'oracle': oracle_data,
        'accuracy': accuracy_data,
        'game_control': gci_data,
    }
```

- [ ] **Step 3: Run export and verify dashboard.json**

Run:
```bash
.venv/Scripts/python.exe export_dashboard_data.py
```

Then verify:
```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/dashboard.json'))
gc = d.get('game_control')
if gc:
    print('game_control keys:', list(gc.keys()))
    print('Storylines:', len(gc.get('storylines', [])))
    print('Games:', len(gc.get('games', [])))
    print('Teams with GCI:', sum(1 for t in d['teams'] if t.get('gci', 0) > 0))
else:
    print('ERROR: game_control not found in dashboard.json')
"
```

- [ ] **Step 4: Commit**

```bash
git add refresh_all.py export_dashboard_data.py
git commit -m "feat: integrate GCI into refresh pipeline and dashboard export"
```

---

### Task 4: Frontend page structure — `game-control.html`

**Files:**
- Create: `docs/game-control.html`

- [ ] **Step 1: Create the complete HTML page**

Create `docs/game-control.html` following the exact patterns from `network.html`:

```html
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#0f1117">
    <title>Game Control Index — Euroleague Analytics</title>
    <meta name="description"
        content="How teams win, not just that they win. Game Control Index with dominance, drama, comebacks, and crunch-time metrics for all 20 Euroleague teams.">
    <meta property="og:title" content="Game Control Index — Euroleague Analytics">
    <meta property="og:description" content="How teams win — dominance, drama, comebacks, and crunch-time analysis.">
    <meta property="og:image" content="og-image.png">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Outfit:wght@700;800&display=swap"
        rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <link rel="stylesheet" href="style.css">
    <style>
        /* ── Storyline cards ── */
        .storyline-scroll {
            display: flex;
            gap: 0.75rem;
            overflow-x: auto;
            padding-bottom: 0.5rem;
            scroll-snap-type: x mandatory;
        }
        .storyline-card {
            min-width: 240px;
            flex: 1;
            background: linear-gradient(135deg, var(--bg-card), var(--bg-secondary));
            border-radius: var(--radius);
            padding: 1.1rem;
            border-left: 3px solid var(--accent-purple);
            scroll-snap-align: start;
            cursor: pointer;
            transition: var(--transition);
        }
        .storyline-card:hover { transform: translateY(-2px); }
        .storyline-label {
            font-size: 0.65rem;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        .storyline-team {
            font-family: 'Outfit', sans-serif;
            font-size: 1.15rem;
            font-weight: 800;
            color: var(--text-primary);
            margin: 0.3rem 0 0.2rem;
        }
        .storyline-text {
            font-size: 0.78rem;
            color: var(--text-secondary);
            line-height: 1.45;
        }
        .storyline-badges {
            display: flex;
            gap: 0.4rem;
            margin-top: 0.6rem;
            flex-wrap: wrap;
        }
        .storyline-badge {
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
            font-size: 0.65rem;
            font-weight: 600;
        }

        /* ── Game of the Round ── */
        .gor-card {
            background: linear-gradient(135deg, var(--bg-card), var(--bg-secondary));
            border-radius: var(--radius);
            padding: 1.2rem;
            border: 1px solid var(--border);
        }
        .gor-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.8rem;
        }
        .gor-body {
            display: flex;
            gap: 1rem;
            align-items: center;
        }
        .gor-score {
            text-align: center;
            flex: 0 0 auto;
        }
        .gor-team-code {
            font-size: 0.85rem;
            font-weight: 700;
        }
        .gor-pts {
            font-family: 'Outfit', sans-serif;
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--text-primary);
        }
        .gor-venue {
            font-size: 0.65rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }
        .gor-wp-wrap {
            flex: 1;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 0.6rem;
        }
        .gor-tags {
            display: flex;
            gap: 0.4rem;
            margin-top: 0.7rem;
            flex-wrap: wrap;
        }
        .gor-tag {
            padding: 0.2rem 0.5rem;
            border-radius: 5px;
            font-size: 0.68rem;
            font-weight: 600;
        }

        /* ── Scatter section ── */
        #scatter-plot { width: 100%; height: 420px; }

        /* ── Leaderboard table ── */
        .gci-tbl {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.8rem;
            white-space: nowrap;
        }
        .gci-tbl th {
            background: var(--bg-secondary);
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.68rem;
            padding: 0.55rem 0.6rem;
            border-bottom: 2px solid var(--border);
            cursor: pointer;
            user-select: none;
        }
        .gci-tbl th:hover { color: var(--text-primary); }
        .gci-tbl th.sorted-asc::after { content: ' ▲'; }
        .gci-tbl th.sorted-desc::after { content: ' ▼'; }
        .gci-tbl td {
            padding: 0.45rem 0.6rem;
            border-bottom: 1px solid var(--border);
            color: var(--text-primary);
        }
        .gci-tbl tbody tr {
            cursor: pointer;
            transition: background var(--transition);
        }
        .gci-tbl tbody tr:hover { background: rgba(78, 205, 196, 0.07); }
        .gci-tbl tbody tr.selected { background: rgba(78, 205, 196, 0.12); }

        /* ── Team deep-dive ── */
        .team-selector-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 0.5rem;
            margin-bottom: 1.2rem;
        }
        @media (max-width: 900px) { .team-selector-grid { grid-template-columns: repeat(4, 1fr); } }
        @media (max-width: 600px) { .team-selector-grid { grid-template-columns: repeat(2, 1fr); } }
        .team-chip {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.45rem 0.4rem;
            text-align: center;
            cursor: pointer;
            transition: var(--transition);
        }
        .team-chip:hover { border-color: #4b5563; background: var(--bg-card); }
        .team-chip.selected { border-color: #4ecdc4; background: rgba(78, 205, 196, 0.08); }
        .team-chip-name { font-weight: 700; font-size: 0.82rem; display: block; }

        .deep-dive-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }
        @media (max-width: 768px) { .deep-dive-grid { grid-template-columns: 1fr; } }
        .dd-panel {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 0.8rem;
            border: 1px solid var(--border);
        }
        .dd-panel-title {
            font-size: 0.65rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }
        #dd-histogram { width: 100%; height: 200px; }
        .game-log-row {
            display: flex;
            justify-content: space-between;
            padding: 0.3rem 0;
            border-bottom: 1px solid var(--border);
            font-size: 0.75rem;
        }
        .home-away-bar {
            height: 8px;
            background: var(--bg-card);
            border-radius: 4px;
            overflow: hidden;
            display: flex;
            margin-top: 0.5rem;
        }

        /* ── Superlatives ── */
        .superlative-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.75rem;
        }
        @media (max-width: 768px) { .superlative-grid { grid-template-columns: 1fr; } }
        .superlative-card {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 1rem;
            text-align: center;
            border: 1px solid var(--border);
        }
        .superlative-icon { font-size: 1.5rem; margin-bottom: 0.3rem; }
        .superlative-label {
            font-size: 0.6rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .superlative-matchup {
            font-family: 'Outfit', sans-serif;
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--text-primary);
            margin: 0.3rem 0;
        }

        /* ── Section labels ── */
        .section-label {
            font-size: 0.68rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.3rem;
        }
        .section-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 0.8rem;
        }
    </style>
</head>

<body>
    <nav class="site-nav">
        <span class="site-nav-brand">🏀 Euroleague Analytics</span>
        <a href="index.html" class="nav-link">Season Hub</a>
        <a href="team.html" class="nav-link">Team Deep-Dive</a>
        <a href="players.html" class="nav-link">Player Stats</a>
        <a href="h2h.html" class="nav-link">Head-to-Head</a>
        <a href="recap.html" class="nav-link">Game Recap</a>
        <a href="shots.html" class="nav-link">Shot Lab</a>
        <a href="network.html" class="nav-link">Playmaking</a>
        <a href="replay.html" class="nav-link">Game Replay</a>
        <a href="playoffs.html" class="nav-link">Playoffs</a>
        <a href="mvp.html" class="nav-link">MVP Race</a>
        <a href="game-control.html" class="nav-link active">Game Control</a>
        <a href="about.html" class="nav-link">About</a>
    </nav>

    <header>
        <h1>Game Control Index</h1>
        <p class="subtitle">How teams win, not just that they win</p>
    </header>

    <div id="load-error" class="hidden" style="text-align:center;padding:3rem 1rem;">
        <div style="font-size:3rem;margin-bottom:1rem;">⚠️</div>
        <p style="color:var(--text-muted);font-size:1rem;">
            Could not load data. Run <code>python export_dashboard_data.py</code> to generate it.
        </p>
    </div>

    <main id="main-content">
        <div class="loading-placeholder" id="loading">
            <span class="loading-spinner"></span> Loading Game Control data…
        </div>

        <div id="content" class="hidden">
            <!-- Section 1: Storyline Hero Cards -->
            <div class="stat-card" id="section-storylines">
                <div class="section-label">Season Storylines</div>
                <div id="storylines" class="storyline-scroll"></div>
            </div>

            <!-- Section 2: Game of the Round -->
            <div class="stat-card" id="section-gor">
                <div class="section-label">Game of the Round</div>
                <div id="game-of-round"></div>
            </div>

            <!-- Section 3: Control vs Drama Scatter -->
            <div class="stat-card" id="section-scatter">
                <div class="section-label">Team Profiles</div>
                <div class="section-title">Control vs. Drama</div>
                <div id="scatter-plot"></div>
            </div>

            <!-- Section 4: GCI Leaderboard -->
            <div class="stat-card" id="section-leaderboard">
                <div class="section-label">Rankings</div>
                <div class="section-title">GCI Leaderboard</div>
                <div style="overflow-x:auto;">
                    <table class="gci-tbl" id="leaderboard">
                        <thead></thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>

            <!-- Section 5: Team Deep-Dive -->
            <div class="stat-card" id="section-deepdive">
                <div class="section-label">Deep Dive</div>
                <div class="section-title">Team Profile</div>
                <div id="team-grid" class="team-selector-grid"></div>
                <div id="team-detail"></div>
            </div>

            <!-- Section 6: Season Superlatives -->
            <div class="stat-card" id="section-superlatives">
                <div class="section-label">Season Awards</div>
                <div class="section-title">Superlatives</div>
                <div id="superlatives" class="superlative-grid"></div>
            </div>
        </div>
    </main>

    <footer class="site-footer">
        <div class="footer-links">
            <a href="about.html">About & Methodology</a>
            <span class="footer-sep">·</span>
            <a href="https://github.com/giasemidis/euroleague_api" target="_blank" rel="noopener">Data: Euroleague API</a>
            <span class="footer-sep">·</span>
            <a href="https://github.com/KonstantinosLaloudakis" target="_blank" rel="noopener">GitHub</a>
        </div>
        <div>19 seasons · 7,000+ games · Updated daily</div>
    </footer>

    <script src="constants.js"></script>
    <script src="game-control.js"></script>
</body>

</html>
```

- [ ] **Step 2: Commit**

```bash
git add docs/game-control.html
git commit -m "feat: add game-control.html page structure"
```

---

### Task 5: `game-control.js` — Data loading, storylines, and game of the round

**Files:**
- Create: `docs/game-control.js`

- [ ] **Step 1: Create JS file with data loading and storyline rendering**

```javascript
/* game-control.js — Game Control Index page logic */

let _data = null;      // full dashboard.json
let _gc = null;        // game_control sub-object
let _selectedTeam = null;
let _sortCol = 'gci';
let _sortAsc = false;

// ── Boot ────────────────────────────────────────────────────────────────────
fetchJSON('data/current/dashboard.json')
    .then(data => {
        _data = data;
        _gc = data.game_control;
        if (!_gc) throw new Error('game_control not found in dashboard.json');
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('content').classList.remove('hidden');
        renderStorylines();
        renderGameOfRound();
        renderScatter();
        renderLeaderboard();
        renderTeamGrid();
        renderSuperlatives();
        restoreFromURL();
    })
    .catch(err => {
        console.error('Failed to load data:', err);
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('load-error').classList.remove('hidden');
    });

function restoreFromURL() {
    const params = new URLSearchParams(location.search);
    const team = params.get('team');
    if (team && _gc.teams[team]) {
        selectTeam(team);
    } else {
        // Default to top GCI team
        const topTeam = Object.entries(_gc.teams)
            .sort((a, b) => b[1].gci - a[1].gci)[0];
        if (topTeam) selectTeam(topTeam[0]);
    }
}

// ── Storylines ──────────────────────────────────────────────────────────────
function renderStorylines() {
    const container = document.getElementById('storylines');
    container.innerHTML = _gc.storylines.map(s => {
        const teamName = TEAM_NAMES[s.team] || s.team;
        const color = s.color || '#4ecdc4';
        const bgAlpha = color + '22';
        return `<div class="storyline-card" style="border-left-color:${color}"
                     onclick="selectTeam('${s.team}')">
            <div class="storyline-label" style="color:${color}">${s.label}</div>
            <div class="storyline-team">${teamName}</div>
            <div class="storyline-text">${s.text}</div>
            <div class="storyline-badges">
                <span class="storyline-badge" style="background:${bgAlpha};color:${color}">${s.stat_label}</span>
                <span class="storyline-badge" style="background:${bgAlpha};color:${color}">${s.stat_sub}</span>
            </div>
        </div>`;
    }).join('');
}

// ── Game of the Round ───────────────────────────────────────────────────────
function renderGameOfRound() {
    const gor = _gc.game_of_round;
    if (!gor) return;

    const homeColor = TEAM_COLORS[gor.home] || '#888';
    const awayColor = TEAM_COLORS[gor.away] || '#888';
    const wpCurve = gor.wp_curve || [];

    // Build SVG polyline for mini WP curve
    let svgPoints = '';
    if (wpCurve.length > 0) {
        const w = 300, h = 70;
        svgPoints = wpCurve.map(([pct, wp]) => {
            const x = pct * w;
            const y = h - (wp * h);  // flip: WP=1 at top
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');
    }

    const container = document.getElementById('game-of-round');
    container.innerHTML = `
        <div class="gor-card">
            <div class="gor-header">
                <div>
                    <div style="font-size:0.95rem;font-weight:700;color:var(--text-primary);">
                        Round ${_data.round}
                    </div>
                </div>
                <div class="gor-tag" style="background:rgba(255,107,107,0.15);color:#ff6b6b">
                    Drama: ${gor.drama.toFixed(2)}
                </div>
            </div>
            <div class="gor-body">
                <div class="gor-score">
                    <div class="gor-team-code" style="color:${homeColor}">${gor.home}</div>
                    <div class="gor-pts">${gor.home_score}</div>
                    <div class="gor-venue">HOME</div>
                </div>
                <div style="color:var(--text-muted);font-size:0.75rem;padding:0 0.3rem;">vs</div>
                <div class="gor-score">
                    <div class="gor-team-code" style="color:${awayColor}">${gor.away}</div>
                    <div class="gor-pts">${gor.away_score}</div>
                    <div class="gor-venue">AWAY</div>
                </div>
                <div class="gor-wp-wrap">
                    <div style="color:var(--text-muted);font-size:0.65rem;margin-bottom:0.3rem;">Win Probability Flow</div>
                    <svg viewBox="0 0 300 70" style="width:100%;height:60px;">
                        <line x1="0" y1="35" x2="300" y2="35" stroke="#333" stroke-dasharray="4" stroke-width="1"/>
                        <line x1="75" y1="0" x2="75" y2="70" stroke="#1a2332" stroke-width="1"/>
                        <line x1="150" y1="0" x2="150" y2="70" stroke="#1a2332" stroke-width="1"/>
                        <line x1="225" y1="0" x2="225" y2="70" stroke="#1a2332" stroke-width="1"/>
                        ${svgPoints ? `<polyline points="${svgPoints}" fill="none" stroke="#4ecdc4" stroke-width="2" stroke-linejoin="round"/>` : ''}
                        <text x="37" y="68" fill="#555" font-size="8" text-anchor="middle">Q1</text>
                        <text x="112" y="68" fill="#555" font-size="8" text-anchor="middle">Q2</text>
                        <text x="187" y="68" fill="#555" font-size="8" text-anchor="middle">Q3</text>
                        <text x="262" y="68" fill="#555" font-size="8" text-anchor="middle">Q4</text>
                    </svg>
                </div>
            </div>
            <div class="gor-tags">
                ${gor.comeback > 0.5 ? `<span class="gor-tag" style="background:rgba(255,215,0,0.12);color:#ffd700">Comeback: ${(gor.comeback * 100).toFixed(0)}%</span>` : ''}
                <span class="gor-tag" style="background:rgba(78,205,196,0.12);color:#4ecdc4">
                    Crunch: ${gor.crunch_home > 0 ? '+' : ''}${gor.crunch_home.toFixed(2)}
                </span>
                <a href="replay.html?season=2025&game=${gor.gamecode}"
                   class="gor-tag" style="background:rgba(168,230,207,0.12);color:#a8e6cf;text-decoration:none;">
                    Watch Replay →
                </a>
            </div>
        </div>`;
}
```

- [ ] **Step 2: Commit**

```bash
git add docs/game-control.js
git commit -m "feat: add game-control.js with data loading, storylines, and game of the round"
```

---

### Task 6: `game-control.js` — Scatter plot and leaderboard

**Files:**
- Modify: `docs/game-control.js`

- [ ] **Step 1: Add scatter plot and leaderboard rendering**

Append to `docs/game-control.js`:

```javascript
// ── Scatter Plot: Control vs Drama ──────────────────────────────────────────
function renderScatter() {
    const teams = Object.entries(_gc.teams);
    const codes = teams.map(([code]) => code);
    const gcis = teams.map(([, t]) => t.gci);
    const dramas = teams.map(([, t]) => t.drama_avg);
    const colors = codes.map(c => TEAM_COLORS[c] || '#888');
    const names = codes.map(c => TEAM_NAMES[c] || c);

    const trace = {
        x: gcis,
        y: dramas,
        mode: 'markers+text',
        type: 'scatter',
        text: codes,
        textposition: 'top center',
        textfont: { size: 10, color: colors, family: 'Inter, sans-serif' },
        marker: {
            size: 14,
            color: colors.map(c => c + '44'),
            line: { color: colors, width: 2 },
        },
        hovertemplate: names.map((n, i) =>
            `<b>${n}</b><br>GCI: ${gcis[i].toFixed(1)}<br>Drama: ${dramas[i].toFixed(2)}<extra></extra>`
        ),
    };

    const xMid = (Math.max(...gcis) + Math.min(...gcis)) / 2;
    const yMid = (Math.max(...dramas) + Math.min(...dramas)) / 2;

    const layout = {
        ...PLOTLY_THEME,
        xaxis: {
            ...PLOTLY_THEME.xaxis,
            title: { text: 'GCI Rating →', font: { size: 11 } },
        },
        yaxis: {
            ...PLOTLY_THEME.yaxis,
            title: { text: 'Drama Index →', font: { size: 11 } },
        },
        annotations: [
            { x: Math.min(...gcis), y: Math.max(...dramas), text: 'Dramatic &<br>Inconsistent',
              showarrow: false, font: { size: 9, color: '#444' }, xanchor: 'left', yanchor: 'top' },
            { x: Math.max(...gcis), y: Math.max(...dramas), text: 'Dramatic &<br>Dominant',
              showarrow: false, font: { size: 9, color: '#444' }, xanchor: 'right', yanchor: 'top' },
            { x: Math.min(...gcis), y: Math.min(...dramas), text: 'Quiet &<br>Inconsistent',
              showarrow: false, font: { size: 9, color: '#444' }, xanchor: 'left', yanchor: 'bottom' },
            { x: Math.max(...gcis), y: Math.min(...dramas), text: 'Quiet &<br>Dominant',
              showarrow: false, font: { size: 9, color: '#444' }, xanchor: 'right', yanchor: 'bottom' },
        ],
        shapes: [
            { type: 'line', x0: xMid, x1: xMid, y0: Math.min(...dramas) * 0.95, y1: Math.max(...dramas) * 1.05,
              line: { color: '#1a2332', width: 1 } },
            { type: 'line', y0: yMid, y1: yMid, x0: Math.min(...gcis) * 0.95, x1: Math.max(...gcis) * 1.05,
              line: { color: '#1a2332', width: 1 } },
        ],
        margin: { t: 10, r: 20, b: 50, l: 60 },
    };

    Plotly.newPlot('scatter-plot', [trace], layout, PLOTLY_CONFIG);

    // Click handler: select team on dot click
    document.getElementById('scatter-plot').on('plotly_click', function(data) {
        if (data.points.length > 0) {
            const idx = data.points[0].pointIndex;
            selectTeam(codes[idx]);
        }
    });
}

// ── Leaderboard ─────────────────────────────────────────────────────────────
function renderLeaderboard() {
    const table = document.getElementById('leaderboard');
    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');

    const cols = [
        { key: 'rank', label: '#', fmt: v => v },
        { key: 'team', label: 'Team', fmt: (v, row) => {
            const c = TEAM_COLORS[v] || '#888';
            return `<span style="display:inline-block;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.7rem;font-weight:600;background:${c}22;color:${c}">${v}</span> ${TEAM_NAMES[v] || v}`;
        }},
        { key: 'gci', label: 'GCI', fmt: v => `<strong style="color:#4ecdc4">${v.toFixed(1)}</strong>` },
        { key: 'dominance_avg', label: 'Dominance', fmt: v => v.toFixed(3) },
        { key: 'control_pct', label: 'Control%', fmt: v => (v * 100).toFixed(0) + '%' },
        { key: 'drama_avg', label: 'Drama', fmt: v => v.toFixed(2) },
        { key: 'crunch_swing_avg', label: 'Crunch', fmt: v => {
            const s = v >= 0 ? '+' : '';
            const c = v >= 0 ? '#4ecdc4' : '#ff6b6b';
            return `<span style="color:${c}">${s}${v.toFixed(3)}</span>`;
        }},
        { key: 'killer_instinct', label: 'Killer', fmt: v => v.toFixed(3) },
        { key: 'comeback_count', label: 'Comebacks', fmt: v => v },
    ];

    // Header
    thead.innerHTML = '<tr>' + cols.map(c =>
        `<th data-col="${c.key}" onclick="sortLeaderboard('${c.key}')">${c.label}</th>`
    ).join('') + '</tr>';

    // Build rows from teams data
    const rows = Object.entries(_gc.teams).map(([code, t], i) => ({
        rank: 0, team: code, ...t
    }));

    // Sort
    rows.sort((a, b) => {
        const av = a[_sortCol], bv = b[_sortCol];
        if (typeof av === 'string') return _sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
        return _sortAsc ? av - bv : bv - av;
    });
    rows.forEach((r, i) => r.rank = i + 1);

    tbody.innerHTML = rows.map(row => {
        const cls = row.team === _selectedTeam ? ' class="selected"' : '';
        return `<tr${cls} onclick="selectTeam('${row.team}')">`
            + cols.map(c => `<td>${c.fmt(row[c.key], row)}</td>`).join('')
            + '</tr>';
    }).join('');

    // Mark sorted column
    thead.querySelectorAll('th').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (th.dataset.col === _sortCol) {
            th.classList.add(_sortAsc ? 'sorted-asc' : 'sorted-desc');
        }
    });
}

function sortLeaderboard(col) {
    if (_sortCol === col) {
        _sortAsc = !_sortAsc;
    } else {
        _sortCol = col;
        _sortAsc = col === 'team';  // ascending for team name, descending for numbers
    }
    renderLeaderboard();
}
```

- [ ] **Step 2: Commit**

```bash
git add docs/game-control.js
git commit -m "feat: add scatter plot and sortable leaderboard to game-control.js"
```

---

### Task 7: `game-control.js` — Team deep-dive and superlatives

**Files:**
- Modify: `docs/game-control.js`

- [ ] **Step 1: Add team grid, deep-dive rendering, and superlatives**

Append to `docs/game-control.js`:

```javascript
// ── Team Grid ───────────────────────────────────────────────────────────────
function renderTeamGrid() {
    const grid = document.getElementById('team-grid');
    const codes = Object.keys(_gc.teams).sort((a, b) =>
        (TEAM_NAMES[a] || a).localeCompare(TEAM_NAMES[b] || b)
    );
    grid.innerHTML = codes.map(code => {
        const color = TEAM_COLORS[code] || '#6b7280';
        const name = TEAM_NAMES[code] || code;
        return `<div class="team-chip" id="chip-${code}"
                     onclick="selectTeam('${code}')"
                     style="border-top:3px solid ${color}40">
            <span class="team-chip-name" style="color:${color}">${name}</span>
        </div>`;
    }).join('');
}

function selectTeam(code) {
    _selectedTeam = code;
    // Update URL
    const url = new URL(location);
    url.searchParams.set('team', code);
    history.replaceState(null, '', url);

    // Update chip selection
    document.querySelectorAll('.team-chip').forEach(el => el.classList.remove('selected'));
    const chip = document.getElementById('chip-' + code);
    if (chip) chip.classList.add('selected');

    // Update leaderboard selection
    renderLeaderboard();
    renderTeamDetail(code);

    // Scroll to deep-dive
    document.getElementById('section-deepdive').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Team Detail ─────────────────────────────────────────────────────────────
function renderTeamDetail(code) {
    const team = _gc.teams[code];
    if (!team) return;
    const color = TEAM_COLORS[code] || '#4ecdc4';
    const container = document.getElementById('team-detail');

    // Normalize metrics for radar chart (0-1 relative to league min/max)
    const allTeams = Object.values(_gc.teams);
    function norm(key) {
        const vals = allTeams.map(t => t[key]);
        const min = Math.min(...vals), max = Math.max(...vals);
        return max > min ? (team[key] - min) / (max - min) : 0.5;
    }
    const radarData = [
        { label: 'Dominance', value: norm('dominance_avg') },
        { label: 'Control', value: norm('control_pct') },
        { label: 'Crunch', value: norm('crunch_swing_avg') },
        { label: 'Comeback', value: norm('comeback_rating') },
        { label: 'Drama', value: norm('drama_avg') },
        { label: 'Killer', value: norm('killer_instinct') },
    ];

    // Build radar SVG
    const radarSVG = buildRadarSVG(radarData, color);

    // Win quality histogram
    const winHist = team.win_quality_hist || [0,0,0,0,0];
    const lossHist = team.loss_quality_hist || [0,0,0,0,0];
    const binLabels = ['Grind', 'Close', 'Solid', 'Comfort', 'Blowout'];

    // Game log (last 10)
    const gameLog = (team.game_log || []).slice(-10).reverse();
    const logHTML = gameLog.map(g => {
        const prefix = g.is_home ? 'vs' : '@';
        const oppColor = TEAM_COLORS[g.opponent] || '#888';
        const wl = g.is_win ? 'W' : 'L';
        const wlColor = g.is_win ? '#4ecdc4' : '#ff6b6b';
        const score = g.is_home ? `${g.home_score}-${g.away_score}` : `${g.away_score}-${g.home_score}`;
        return `<div class="game-log-row">
            <span style="color:var(--text-muted)">${prefix} <span style="color:${oppColor};font-weight:600">${g.opponent}</span></span>
            <span><span style="color:${wlColor};font-weight:600">${wl}</span> ${score} · <span style="color:var(--text-muted)">${g.dominance.toFixed(2)}</span></span>
        </div>`;
    }).join('');

    // Home vs Away
    const homeGCI = team.home_gci;
    const awayGCI = team.away_gci;
    const total = Math.abs(homeGCI) + Math.abs(awayGCI);
    const homePct = total > 0 ? (Math.max(0, homeGCI) / total * 100) : 50;

    container.innerHTML = `
        <div class="deep-dive-grid">
            <div class="dd-panel">
                <div class="dd-panel-title">GCI Profile</div>
                ${radarSVG}
            </div>
            <div class="dd-panel">
                <div class="dd-panel-title">Win Quality Distribution</div>
                <div id="dd-histogram"></div>
            </div>
            <div class="dd-panel">
                <div class="dd-panel-title">Game Log (Last 10)</div>
                ${logHTML || '<div style="color:var(--text-muted);font-size:0.8rem;">No games</div>'}
            </div>
        </div>
        <div class="dd-panel">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div class="dd-panel-title" style="margin-bottom:0">Home vs Away Dominance</div>
                <div style="display:flex;gap:0.8rem;font-size:0.85rem;">
                    <span style="color:#4ecdc4;font-weight:700">Home: ${homeGCI >= 0 ? '+' : ''}${homeGCI.toFixed(3)}</span>
                    <span style="color:var(--text-muted)">|</span>
                    <span style="color:#ff6b6b;font-weight:700">Away: ${awayGCI >= 0 ? '+' : ''}${awayGCI.toFixed(3)}</span>
                </div>
            </div>
            <div class="home-away-bar">
                <div style="width:${homePct}%;background:linear-gradient(90deg,#4ecdc4,#45b7aa);border-radius:4px 0 0 4px;"></div>
                <div style="width:${100 - homePct}%;background:linear-gradient(90deg,#e55,#ff6b6b);border-radius:0 4px 4px 0;"></div>
            </div>
        </div>
    `;

    // Render Plotly histogram for win/loss quality
    const winTrace = {
        x: binLabels, y: winHist, name: 'Wins', type: 'bar',
        marker: { color: '#4ecdc4' },
    };
    const lossTrace = {
        x: binLabels, y: lossHist.map(v => -v), name: 'Losses', type: 'bar',
        marker: { color: '#ff6b6b' },
    };
    Plotly.newPlot('dd-histogram', [winTrace, lossTrace], {
        ...PLOTLY_THEME,
        barmode: 'relative',
        margin: { t: 5, r: 10, b: 30, l: 30 },
        legend: { orientation: 'h', y: 1.15, font: { size: 10 } },
        yaxis: { ...PLOTLY_THEME.yaxis, title: '' },
        xaxis: { ...PLOTLY_THEME.xaxis, title: '' },
    }, PLOTLY_CONFIG);
}

// ── Radar Chart SVG builder ─────────────────────────────────────────────────
function buildRadarSVG(data, color) {
    const cx = 100, cy = 100, r = 70;
    const n = data.length;
    const angleStep = (2 * Math.PI) / n;

    // Grid rings
    let gridLines = '';
    for (const scale of [0.33, 0.66, 1.0]) {
        const pts = [];
        for (let i = 0; i < n; i++) {
            const angle = -Math.PI / 2 + i * angleStep;
            pts.push(`${cx + r * scale * Math.cos(angle)},${cy + r * scale * Math.sin(angle)}`);
        }
        gridLines += `<polygon points="${pts.join(' ')}" fill="none" stroke="#1a2332" stroke-width="1"/>`;
    }

    // Axis lines
    let axisLines = '';
    for (let i = 0; i < n; i++) {
        const angle = -Math.PI / 2 + i * angleStep;
        const x2 = cx + r * Math.cos(angle);
        const y2 = cy + r * Math.sin(angle);
        axisLines += `<line x1="${cx}" y1="${cy}" x2="${x2}" y2="${y2}" stroke="#1a2332" stroke-width="1"/>`;
    }

    // Data polygon
    const dataPts = data.map((d, i) => {
        const angle = -Math.PI / 2 + i * angleStep;
        const val = Math.max(0.05, d.value); // min 5% so shape is visible
        return `${cx + r * val * Math.cos(angle)},${cy + r * val * Math.sin(angle)}`;
    }).join(' ');

    // Labels
    let labels = '';
    for (let i = 0; i < n; i++) {
        const angle = -Math.PI / 2 + i * angleStep;
        const lx = cx + (r + 16) * Math.cos(angle);
        const ly = cy + (r + 16) * Math.sin(angle);
        const anchor = Math.abs(Math.cos(angle)) < 0.3 ? 'middle' : (Math.cos(angle) > 0 ? 'start' : 'end');
        labels += `<text x="${lx}" y="${ly}" fill="#888" font-size="9" text-anchor="${anchor}" dominant-baseline="central">${data[i].label}</text>`;
    }

    return `<svg viewBox="0 0 200 200" style="width:100%;max-width:220px;margin:0 auto;display:block;">
        ${gridLines}${axisLines}
        <polygon points="${dataPts}" fill="${color}22" stroke="${color}" stroke-width="2"/>
        ${labels}
    </svg>`;
}

// ── Superlatives ────────────────────────────────────────────────────────────
function renderSuperlatives() {
    const sup = _gc.superlatives;
    if (!sup) return;

    const cards = [
        { key: 'most_dominant', icon: '★', label: 'Most Dominant Game', color: '#4ecdc4',
          metric: s => `Dominance: ${Math.abs(s.dominance).toFixed(2)}` },
        { key: 'most_dramatic', icon: '⚡', label: 'Most Dramatic Game', color: '#ff6b6b',
          metric: s => `Drama: ${s.drama.toFixed(2)}` },
        { key: 'biggest_comeback', icon: '↻', label: 'Biggest Comeback', color: '#ffd700',
          metric: s => `From ${((1 - s.comeback) * 100).toFixed(0)}% WP` },
    ];

    const container = document.getElementById('superlatives');
    container.innerHTML = cards.map(c => {
        const s = sup[c.key];
        if (!s) return '';
        return `<div class="superlative-card">
            <div class="superlative-icon" style="color:${c.color}">${c.icon}</div>
            <div class="superlative-label">${c.label}</div>
            <div class="superlative-matchup">${s.home} ${s.home_score} - ${s.away_score} ${s.away}</div>
            <div style="color:${c.color};font-size:0.8rem;">${c.metric(s)}</div>
        </div>`;
    }).join('');
}
```

- [ ] **Step 2: Verify the page in a browser**

Start a local dev server:
```bash
cd docs && python3 -m http.server 8000
```

Open `http://localhost:8000/game-control.html` in a browser. Verify:
- Storyline cards render with team names and descriptions
- Game of the Round shows score, mini WP curve, and tags
- Scatter plot shows team dots with correct colors
- Leaderboard table sorts on column click
- Team selector grid works and deep-dive shows radar, histogram, game log
- Superlatives show 3 award cards
- No console errors

- [ ] **Step 3: Commit**

```bash
git add docs/game-control.js
git commit -m "feat: add team deep-dive, radar chart, and superlatives to game-control.js"
```

---

### Task 8: Navigation update and about page

**Files:**
- Modify: `docs/index.html`, `docs/team.html`, `docs/players.html`, `docs/h2h.html`, `docs/recap.html`, `docs/shots.html`, `docs/network.html`, `docs/replay.html`, `docs/playoffs.html`, `docs/mvp.html`, `docs/about.html`

- [ ] **Step 1: Add "Game Control" nav link to all 11 existing pages**

In every HTML file under `docs/`, find the nav block:

```html
        <a href="mvp.html" class="nav-link">MVP Race</a>
        <a href="about.html" class="nav-link">About</a>
```

Replace with:

```html
        <a href="mvp.html" class="nav-link">MVP Race</a>
        <a href="game-control.html" class="nav-link">Game Control</a>
        <a href="about.html" class="nav-link">About</a>
```

Apply this to all 11 files: `index.html`, `team.html`, `players.html`, `h2h.html`, `recap.html`, `shots.html`, `network.html`, `replay.html`, `playoffs.html`, `mvp.html`, `about.html`.

- [ ] **Step 2: Add GCI methodology section to `about.html`**

In `docs/about.html`, find the Playmaking Network list item (around line 272):

```html
                <li><span class="metric-name">Playmaking Network</span> — Interactive chord diagrams...
```

After that `</li>`, add a new list item for Game Control:

```html
                <li><span class="metric-name">Game Control</span> — How teams win, not just that they win. The Game Control Index (GCI) uses Win Probability trajectory analysis to measure dominance, drama, comeback resilience, crunch-time performance, and killer instinct for every game and team.</li>
```

Then find the team metrics section (or add a new about-section after the existing metrics). Add a new section:

```html
        <!-- ── Game Control Metrics ─────────────────────────────────── -->
        <div class="about-section">
            <h3>Game Control Metrics</h3>
            <p>
                The Game Control Index (GCI) analyzes Win Probability trajectories — the second-by-second likelihood
                of each team winning — to measure <em>how</em> teams win, not just whether they did.
                Built from WP replay data across every game this season.
            </p>
            <ul>
                <li>
                    <span class="metric-name">Dominance Score</span>
                    <span class="metric-tag team">Team</span>
                    <span class="metric-tag game">Game</span>
                    <br>
                    Average distance of WP from 50% across all plays: <code>mean(WP - 0.5)</code>.
                    Positive means the home team controlled the game; negative means the away team did.
                    Range: -0.5 to +0.5.
                </li>
                <li>
                    <span class="metric-name">Control Duration</span>
                    <span class="metric-tag team">Team</span>
                    <span class="metric-tag game">Game</span>
                    <br>
                    Percentage of plays where the eventual winner held WP above 60%.
                    100% means wire-to-wire cruise control; lower values indicate a contested game.
                </li>
                <li>
                    <span class="metric-name">Drama Index</span>
                    <span class="metric-tag game">Game</span>
                    <br>
                    Total variation of the WP curve: sum of absolute WP changes between consecutive plays.
                    Higher values indicate more momentum swings and lead changes.
                </li>
                <li>
                    <span class="metric-name">Comeback Magnitude</span>
                    <span class="metric-tag game">Game</span>
                    <br>
                    For wins: <code>1.0 - min(winner WP)</code>. Measures how deep a deficit the winning team
                    overcame. A comeback from 10% WP scores 0.90.
                </li>
                <li>
                    <span class="metric-name">Crunch-Time Swing</span>
                    <span class="metric-tag team">Team</span>
                    <span class="metric-tag game">Game</span>
                    <br>
                    Net WP change in the final 5 minutes of game clock (Q4 from 5:00 to buzzer, plus overtime).
                    Positive means the team gained control in the clutch.
                </li>
                <li>
                    <span class="metric-name">Killer Instinct</span>
                    <span class="metric-tag team">Team</span>
                    <br>
                    Average WP change per play in Q4 when leading with WP above 60%.
                    Measures the ability to close out games rather than letting opponents back in.
                </li>
                <li>
                    <span class="metric-name">GCI Rating</span>
                    <span class="metric-tag team">Team</span>
                    <br>
                    Weighted composite of Dominance (35%), Control Duration (25%), Crunch-Time Swing (20%),
                    and Killer Instinct (20%), z-normalized to a 0–100 scale across the league.
                    Higher = more dominant game control profile.
                </li>
            </ul>
        </div>
```

- [ ] **Step 3: Verify navigation works across pages**

Open several pages in the browser and confirm:
- "Game Control" link appears in the nav bar on every page
- Clicking it navigates to `game-control.html`
- The link is marked `active` on the Game Control page itself

- [ ] **Step 4: Commit**

```bash
git add docs/index.html docs/team.html docs/players.html docs/h2h.html docs/recap.html docs/shots.html docs/network.html docs/replay.html docs/playoffs.html docs/mvp.html docs/about.html
git commit -m "feat: add Game Control nav link to all pages and methodology to about.html"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Per-game metric computation | `calculate_gci.py` (create) |
| 2 | Team aggregation, GCI rating, storylines, output | `calculate_gci.py` (modify) |
| 3 | Pipeline integration | `refresh_all.py`, `export_dashboard_data.py` |
| 4 | Frontend HTML page | `docs/game-control.html` (create) |
| 5 | JS: data loading, storylines, game of round | `docs/game-control.js` (create) |
| 6 | JS: scatter plot and leaderboard | `docs/game-control.js` (modify) |
| 7 | JS: team deep-dive, radar, superlatives | `docs/game-control.js` (modify) |
| 8 | Navigation + about page | 11 HTML files |
