# Playoff Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live playoff results, a championship odds history chart, and post-game recap cards to the existing playoff bracket page.

**Architecture:** The backend (`export_dashboard_data.py`) gains three new functions that detect playoff games from the existing game results data (GameCode > 380), build a structured `playoff_results` object, run a bracket-level Monte Carlo for championship odds, and generate recap card data. The frontend (`playoffs.js`) loads real results on init to lock completed games, renders a Plotly line chart for championship odds history, and displays recap cards below the bracket. All data flows through the existing `dashboard.json`.

**Tech Stack:** Python (backend export), vanilla JS + Plotly.js (frontend), existing Euroleague API data pipeline.

---

### Task 1: Bump max game code to cover playoffs

**Files:**
- Modify: `fetch_mvp_data_v2.py:33`

- [ ] **Step 1: Update max_games constant**

The current limit of 400 may not cover all playoff games (380 regular season + up to 26 playoff games = 406). Bump to 420 for safety.

```python
    max_games = 420 # Regular season (380) + Play-in (3) + QF (up to 20) + SF (2) + Final (1)
```

- [ ] **Step 2: Commit**

```bash
git add fetch_mvp_data_v2.py
git commit -m "fix: bump max game code to 420 to cover playoff games"
```

---

### Task 2: Build playoff results structure in backend

**Files:**
- Modify: `export_dashboard_data.py` (add new function after line ~1210, before the build-output section)

- [ ] **Step 1: Add the `build_playoff_results` function**

This function takes the game results list and the final standings (top 10 teams), identifies playoff games (GameCode > 380), and maps them into the structured bracket format. It uses the schedule XML `round` field to distinguish play-in vs QF vs SF vs Final.

Add this function before the `# ── Build output` section (around line 1212):

```python
def build_playoff_results(game_results, seeded_teams):
    """
    Detect playoff games and build structured bracket results.
    
    Playoff games have GameCode > 380 in the Euroleague API.
    The schedule XML 'round' field distinguishes phases:
      PI = Play-In, QF = Quarterfinals, SF = Semi-Finals, F = Final
    
    Args:
        game_results: list of dicts with GameCode, LocalTeam, RoadTeam, LocalScore, RoadScore, Winner
        seeded_teams: list of top-10 team dicts sorted by seed (index 0 = seed 1)
    
    Returns:
        dict with play_in, qf, sf, final structure, or None if no playoff games exist
    """
    import xml.etree.ElementTree as ET
    
    # Build game code → round-type mapping from schedule XML
    gc_to_phase = {}
    gc_to_date = {}
    try:
        tree = ET.parse('official_schedule_2025.xml')
        for item in tree.getroot().findall('item'):
            gc_el = item.find('gamecode')
            round_el = item.find('round')
            date_el = item.find('date')
            if gc_el is not None and gc_el.text:
                gc_text = gc_el.text
                gc_num = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
                if round_el is not None and round_el.text:
                    gc_to_phase[gc_num] = round_el.text  # RS, PI, QF, SF, F
                if date_el is not None and date_el.text:
                    gc_to_date[gc_num] = date_el.text
    except Exception:
        pass
    
    # Filter to playoff games with scores
    playoff_games = []
    for g in game_results:
        gc = g.get('GameCode', 0)
        if isinstance(gc, float):
            gc = int(gc)
        if gc > 380 and g.get('LocalScore', 0) > 0:
            phase = gc_to_phase.get(gc, '')
            playoff_games.append({
                'game_code': gc,
                'home': g['LocalTeam'],
                'away': g['RoadTeam'],
                'home_score': int(g['LocalScore']),
                'away_score': int(g['RoadScore']),
                'winner': g['Winner'],
                'phase': phase,
                'date': gc_to_date.get(gc, ''),
            })
    
    if not playoff_games:
        return None
    
    # Sort by game code (chronological)
    playoff_games.sort(key=lambda x: x['game_code'])
    
    # Build seed lookup
    seed_codes = [t['team'] for t in seeded_teams[:10]]
    
    # --- Play-In ---
    pi_games = [g for g in playoff_games if g['phase'] == 'PI']
    play_in = {
        'game_a': None,  # 7 vs 8
        'game_b': None,  # 9 vs 10
        'game_c': None,  # Loser(A) vs Winner(B)
    }
    
    s7, s8, s9, s10 = (seed_codes[6] if len(seed_codes) > 6 else None,
                        seed_codes[7] if len(seed_codes) > 7 else None,
                        seed_codes[8] if len(seed_codes) > 8 else None,
                        seed_codes[9] if len(seed_codes) > 9 else None)
    
    for g in pi_games:
        teams_in_game = {g['home'], g['away']}
        if s7 in teams_in_game and s8 in teams_in_game:
            play_in['game_a'] = _format_game(g)
        elif s9 in teams_in_game and s10 in teams_in_game:
            play_in['game_b'] = _format_game(g)
        else:
            # Game C: involves the loser of A and winner of B
            play_in['game_c'] = _format_game(g)
    
    # --- Quarterfinals ---
    qf_games = [g for g in playoff_games if g['phase'] == 'QF']
    
    # Determine play-in results to know seed 7 and seed 8
    final_seed7 = None  # Game A winner
    final_seed8 = None  # Game C winner
    if play_in['game_a']:
        final_seed7 = play_in['game_a']['winner']
    if play_in['game_c']:
        final_seed8 = play_in['game_c']['winner']
    
    # QF matchups: 1v8, 2v7, 3v6, 4v5
    qf_matchups = {
        '1v8': {'higher': seed_codes[0], 'lower': final_seed8},
        '2v7': {'higher': seed_codes[1], 'lower': final_seed7},
        '3v6': {'higher': seed_codes[2], 'lower': seed_codes[5]},
        '4v5': {'higher': seed_codes[3], 'lower': seed_codes[4]},
    }
    
    qf = {}
    for label, matchup in qf_matchups.items():
        series_games = []
        series_wins = [0, 0]  # [higher seed wins, lower seed wins]
        series_winner = None
        
        for g in qf_games:
            teams_in_game = {g['home'], g['away']}
            if matchup['higher'] in teams_in_game and matchup['lower'] in teams_in_game:
                series_games.append(_format_game(g))
                if g['winner'] == matchup['higher']:
                    series_wins[0] += 1
                else:
                    series_wins[1] += 1
                if series_wins[0] >= 3:
                    series_winner = matchup['higher']
                elif series_wins[1] >= 3:
                    series_winner = matchup['lower']
        
        qf[label] = {
            'games': series_games,
            'series': series_wins,
            'higher_seed': matchup['higher'],
            'lower_seed': matchup['lower'],
            'winner': series_winner,
        }
    
    # --- Semi-Finals ---
    sf_games = [g for g in playoff_games if g['phase'] == 'SF']
    sf = {'sf1': None, 'sf2': None}
    
    # SF1: winner of 1v8 vs winner of 4v5
    # SF2: winner of 2v7 vs winner of 3v6
    sf1_teams = {qf['1v8']['winner'], qf['4v5']['winner']} - {None}
    sf2_teams = {qf['2v7']['winner'], qf['3v6']['winner']} - {None}
    
    for g in sf_games:
        teams_in_game = {g['home'], g['away']}
        if sf1_teams and teams_in_game == sf1_teams:
            sf['sf1'] = _format_game(g)
        elif sf2_teams and teams_in_game == sf2_teams:
            sf['sf2'] = _format_game(g)
    
    # --- Final ---
    final_games = [g for g in playoff_games if g['phase'] == 'F']
    final = {'game': None, 'winner': None}
    if final_games:
        final['game'] = _format_game(final_games[0])
        final['winner'] = final_games[0]['winner']
    
    return {
        'play_in': play_in,
        'qf': qf,
        'sf': sf,
        'final': final,
    }


def _format_game(g):
    """Format a playoff game dict for JSON output."""
    return {
        'home': g['home'],
        'away': g['away'],
        'home_score': g['home_score'],
        'away_score': g['away_score'],
        'winner': g['winner'],
        'date': g.get('date', ''),
    }
```

- [ ] **Step 2: Verify by running a quick test**

The function should return `None` right now since there are no playoff games yet:

```bash
.venv/Scripts/python.exe -c "
import json
from export_dashboard_data import build_playoff_results
results = json.load(open('mvp_game_results.json'))
# Use empty seeded list for now
result = build_playoff_results(results, [])
print('Result:', result)  # Should be None
"
```

Expected: `Result: None`

- [ ] **Step 3: Commit**

```bash
git add export_dashboard_data.py
git commit -m "feat: add build_playoff_results function for bracket tracking"
```

---

### Task 3: Compute championship odds from bracket state

**Files:**
- Modify: `export_dashboard_data.py` (add function after `build_playoff_results`)

- [ ] **Step 1: Add the `compute_championship_odds` function**

This runs 10,000 Monte Carlo iterations of the remaining bracket from the current real state, using the pre-computed matchup probabilities. Add after `_format_game`:

```python
def compute_championship_odds(playoff_results, matchup_probs, seeded_teams, n_sims=10000):
    """
    Run Monte Carlo simulation of the remaining bracket from current state.
    
    Uses playoff_results for completed games and matchup_probs for simulating
    unplayed games. Returns dict of team_code → championship probability (0-100).
    
    Args:
        playoff_results: output of build_playoff_results (or None)
        matchup_probs: dict from playoff_matchup_probs computation
        seeded_teams: list of top-10 team dicts sorted by seed
        n_sims: number of simulations
    
    Returns:
        dict of team_code → championship percentage (0-100)
    """
    import random
    
    if len(seeded_teams) < 10:
        return {}
    
    seed_codes = [t['team'] for t in seeded_teams[:10]]
    
    def _get_prob(team_a, team_b, venue):
        """Get win probability for team_a vs team_b at venue."""
        entry = (matchup_probs.get(team_a) or {}).get(team_b)
        if entry:
            return entry.get(venue, 0.5)
        return 0.5
    
    def _sim_game(team_a, team_b, venue):
        """Simulate a single game, return winner code."""
        p = _get_prob(team_a, team_b, venue)
        return team_a if random.random() < p else team_b
    
    def _sim_series(higher, lower):
        """Simulate a best-of-5 series with 2-2-1 HCA, return winner code."""
        # higher seed is home games 1, 2, 5; away games 3, 4
        home_pattern = [True, True, False, False, True]
        wins_h, wins_l = 0, 0
        for g in range(5):
            venue = 'home' if home_pattern[g] else 'away'
            winner = _sim_game(higher, lower, venue)
            if winner == higher:
                wins_h += 1
            else:
                wins_l += 1
            if wins_h >= 3 or wins_l >= 3:
                break
        return higher if wins_h >= 3 else lower
    
    # Extract known results
    pi_a_winner = None
    pi_a_loser = None
    pi_b_winner = None
    pi_c_winner = None
    qf_winners = {'1v8': None, '2v7': None, '3v6': None, '4v5': None}
    sf_winners = {'sf1': None, 'sf2': None}
    final_winner = None
    
    # QF series state: track partial series
    qf_series_state = {}  # label → (higher_wins, lower_wins, higher_seed, lower_seed)
    
    if playoff_results:
        pi = playoff_results.get('play_in', {})
        if pi.get('game_a') and pi['game_a'].get('winner'):
            pi_a_winner = pi['game_a']['winner']
            ga = pi['game_a']
            pi_a_loser = ga['away'] if ga['winner'] == ga['home'] else ga['home']
        if pi.get('game_b') and pi['game_b'].get('winner'):
            pi_b_winner = pi['game_b']['winner']
        if pi.get('game_c') and pi['game_c'].get('winner'):
            pi_c_winner = pi['game_c']['winner']
        
        qf_data = playoff_results.get('qf', {})
        for label in ['1v8', '2v7', '3v6', '4v5']:
            qf_entry = qf_data.get(label, {})
            if qf_entry.get('winner'):
                qf_winners[label] = qf_entry['winner']
            elif qf_entry.get('series'):
                # Partial series — track state
                qf_series_state[label] = (
                    qf_entry['series'][0], qf_entry['series'][1],
                    qf_entry.get('higher_seed'), qf_entry.get('lower_seed')
                )
        
        sf_data = playoff_results.get('sf', {})
        if sf_data.get('sf1') and sf_data['sf1'].get('winner'):
            sf_winners['sf1'] = sf_data['sf1']['winner']
        if sf_data.get('sf2') and sf_data['sf2'].get('winner'):
            sf_winners['sf2'] = sf_data['sf2']['winner']
        
        final_data = playoff_results.get('final', {})
        if final_data.get('winner'):
            final_winner = final_data['winner']
    
    counts = {code: 0 for code in seed_codes}
    
    for _ in range(n_sims):
        # --- Play-In ---
        ga_w = pi_a_winner or _sim_game(seed_codes[6], seed_codes[7], 'home')
        ga_l = pi_a_loser or (seed_codes[7] if ga_w == seed_codes[6] else seed_codes[6])
        gb_w = pi_b_winner or _sim_game(seed_codes[8], seed_codes[9], 'home')
        gc_w = pi_c_winner or _sim_game(ga_l, gb_w, 'home')
        
        s7 = ga_w   # → QF vs seed 2
        s8 = gc_w   # → QF vs seed 1
        
        # --- Quarterfinals ---
        qf_pairs = {
            '1v8': (seed_codes[0], s8),
            '2v7': (seed_codes[1], s7),
            '3v6': (seed_codes[2], seed_codes[5]),
            '4v5': (seed_codes[3], seed_codes[4]),
        }
        
        qf_w = {}
        for label, (higher, lower) in qf_pairs.items():
            if qf_winners[label]:
                qf_w[label] = qf_winners[label]
            elif label in qf_series_state:
                # Continue from partial series
                h_wins, l_wins, h_seed, l_seed = qf_series_state[label]
                while h_wins < 3 and l_wins < 3:
                    game_num = h_wins + l_wins
                    home_pattern = [True, True, False, False, True]
                    venue = 'home' if home_pattern[game_num] else 'away'
                    w = _sim_game(h_seed, l_seed, venue)
                    if w == h_seed:
                        h_wins += 1
                    else:
                        l_wins += 1
                qf_w[label] = h_seed if h_wins >= 3 else l_seed
            else:
                qf_w[label] = _sim_series(higher, lower)
        
        # --- Semi-Finals (neutral) ---
        sf1_w = sf_winners['sf1'] or _sim_game(qf_w['1v8'], qf_w['4v5'], 'neutral')
        sf2_w = sf_winners['sf2'] or _sim_game(qf_w['2v7'], qf_w['3v6'], 'neutral')
        
        # --- Final (neutral) ---
        champ = final_winner or _sim_game(sf1_w, sf2_w, 'neutral')
        counts[champ] += 1
    
    return {code: round(count / n_sims * 100, 1) for code, count in counts.items()}
```

- [ ] **Step 2: Commit**

```bash
git add export_dashboard_data.py
git commit -m "feat: add compute_championship_odds Monte Carlo for bracket state"
```

---

### Task 4: Build playoff recap card data

**Files:**
- Modify: `export_dashboard_data.py` (add function after `compute_championship_odds`)

- [ ] **Step 1: Add the `build_playoff_recaps` function**

Add after `compute_championship_odds`:

```python
def build_playoff_recaps(playoff_results, odds_before, odds_after, matchup_probs, seeded_teams):
    """
    Generate recap card data for each completed playoff game.
    
    Args:
        playoff_results: output of build_playoff_results
        odds_before: championship odds dict before this game day (from previous run's history)
        odds_after: championship odds dict after this game day (just computed)
        matchup_probs: pairwise probability dict
        seeded_teams: top-10 team dicts sorted by seed
    
    Returns:
        list of recap card dicts, sorted by date descending
    """
    if not playoff_results:
        return []
    
    seed_lookup = {t['team']: i + 1 for i, t in enumerate(seeded_teams[:10])}
    recaps = []
    
    def _get_pre_game_prob(home, away, venue):
        """Get pre-game win probability for home team."""
        entry = (matchup_probs.get(home) or {}).get(away)
        if entry:
            return entry.get(venue, 0.5)
        return 0.5
    
    def _add_recap(game, round_label, series=None, series_label_str=None):
        if not game or not game.get('winner'):
            return
        
        home, away = game['home'], game['away']
        winner = game['winner']
        
        # Determine venue type
        venue = 'neutral' if round_label in ('Semi-Final', 'Final') else 'home'
        home_prob = _get_pre_game_prob(home, away, venue)
        winner_prob = home_prob if winner == home else (1 - home_prob)
        
        is_upset = winner_prob < 0.4
        
        recap = {
            'date': game.get('date', ''),
            'round': round_label,
            'home': home,
            'away': away,
            'home_score': game['home_score'],
            'away_score': game['away_score'],
            'winner': winner,
            'pre_game_win_prob': round(winner_prob * 100, 1),
            'is_upset': is_upset,
        }
        
        if series is not None:
            recap['series'] = series
        if series_label_str is not None:
            recap['series_label'] = series_label_str
        
        # Add championship odds delta
        recap['championship_odds_before'] = {
            home: odds_before.get(home, 0),
            away: odds_before.get(away, 0),
        }
        recap['championship_odds_after'] = {
            home: odds_after.get(home, 0),
            away: odds_after.get(away, 0),
        }
        
        recaps.append(recap)
    
    # Play-In games
    pi = playoff_results.get('play_in', {})
    _add_recap(pi.get('game_a'), 'Play-In Game A')
    _add_recap(pi.get('game_b'), 'Play-In Game B')
    _add_recap(pi.get('game_c'), 'Play-In Game C')
    
    # Quarterfinal games
    qf = playoff_results.get('qf', {})
    for label in ['1v8', '2v7', '3v6', '4v5']:
        qf_entry = qf.get(label, {})
        series = qf_entry.get('series', [0, 0])
        higher = qf_entry.get('higher_seed', '?')
        lower = qf_entry.get('lower_seed', '?')
        
        for i, game in enumerate(qf_entry.get('games', [])):
            # Compute running series score at this point
            h_w = sum(1 for g2 in qf_entry['games'][:i+1] if g2['winner'] == higher)
            l_w = (i + 1) - h_w
            
            if h_w > l_w:
                sl = f"{higher} leads {h_w}-{l_w}"
            elif l_w > h_w:
                sl = f"{lower} leads {l_w}-{h_w}"
            elif h_w == 3 or l_w == 3:
                sl = f"Series over"
            else:
                sl = f"Series tied {h_w}-{l_w}"
            
            _add_recap(game, f'QF {label} Game {i+1}', [h_w, l_w], sl)
    
    # Semi-Finals
    sf = playoff_results.get('sf', {})
    _add_recap(sf.get('sf1'), 'Semi-Final 1')
    _add_recap(sf.get('sf2'), 'Semi-Final 2')
    
    # Final
    final = playoff_results.get('final', {})
    _add_recap(final.get('game'), 'Final')
    
    # Sort by date descending (most recent first)
    recaps.sort(key=lambda r: r.get('date', ''), reverse=True)
    
    return recaps
```

- [ ] **Step 2: Commit**

```bash
git add export_dashboard_data.py
git commit -m "feat: add build_playoff_recaps for post-game recap cards"
```

---

### Task 5: Integrate playoff data into dashboard export

**Files:**
- Modify: `export_dashboard_data.py` (the `# ── Build output` section, around lines 1212-1237)

- [ ] **Step 1: Add playoff data generation before the output dict**

Insert this block just before `output = {` (around line 1214):

```python
    # ── Playoff tracking ─────────────────────────────────────────────────────
    playoff_results_data = None
    championship_odds = {}
    playoff_recaps = []
    championship_odds_history = []
    
    game_results_raw = load_json('mvp_game_results.json')
    if game_results_raw and len(teams) >= 10:
        seeded = teams[:10]  # Already sorted by wins desc, adj_net desc
        playoff_results_data = build_playoff_results(game_results_raw, seeded)
        
        if playoff_results_data:
            # Compute current championship odds
            championship_odds = compute_championship_odds(
                playoff_results_data, playoff_matchup_probs, seeded
            )
            
            # Load previous odds history from existing dashboard
            prev_dashboard_path = os.path.join('docs', 'data', 'current', 'dashboard.json')
            prev_odds = {}
            try:
                with open(prev_dashboard_path, 'r', encoding='utf-8') as f:
                    prev_data = json.load(f)
                championship_odds_history = prev_data.get('championship_odds_history', [])
                # Previous odds = last entry in history, or empty
                if championship_odds_history:
                    prev_odds = championship_odds_history[-1].get('odds', {})
            except Exception:
                pass
            
            # Append today's snapshot (avoid duplicate dates)
            today_str = datetime.utcnow().strftime('%Y-%m-%d')
            # Remove any existing entry for today (re-run scenario)
            championship_odds_history = [
                h for h in championship_odds_history if h.get('date') != today_str
            ]
            championship_odds_history.append({
                'date': today_str,
                'label': _detect_playoff_label(playoff_results_data),
                'odds': championship_odds,
            })
            
            # Build recap cards
            playoff_recaps = build_playoff_recaps(
                playoff_results_data, prev_odds, championship_odds,
                playoff_matchup_probs, seeded
            )
            
            print(f"  Playoff results: {sum(1 for g in game_results_raw if int(g.get('GameCode', 0)) > 380 and g.get('LocalScore', 0) > 0)} games tracked")
            print(f"  Championship odds computed for {len([v for v in championship_odds.values() if v > 0])} contending teams")
        else:
            # Pre-playoff: compute baseline odds if not done yet
            prev_dashboard_path = os.path.join('docs', 'data', 'current', 'dashboard.json')
            try:
                with open(prev_dashboard_path, 'r', encoding='utf-8') as f:
                    prev_data = json.load(f)
                championship_odds_history = prev_data.get('championship_odds_history', [])
            except Exception:
                pass
            
            if not championship_odds_history and playoff_matchup_probs:
                seeded = teams[:10]
                championship_odds = compute_championship_odds(
                    None, playoff_matchup_probs, seeded
                )
                championship_odds_history = [{
                    'date': datetime.utcnow().strftime('%Y-%m-%d'),
                    'label': 'Pre-Playoff',
                    'odds': championship_odds,
                }]
```

- [ ] **Step 2: Add the `_detect_playoff_label` helper**

Add this small helper right before `build_playoff_results`:

```python
def _detect_playoff_label(playoff_results):
    """Generate a human-readable label for the current playoff phase."""
    if not playoff_results:
        return 'Pre-Playoff'
    
    final = playoff_results.get('final', {})
    if final.get('winner'):
        return 'Final'
    
    sf = playoff_results.get('sf', {})
    if sf.get('sf1') or sf.get('sf2'):
        return 'Final Four'
    
    qf = playoff_results.get('qf', {})
    qf_games = sum(len(q.get('games', [])) for q in qf.values())
    if qf_games > 0:
        # Count total QF games to determine which game day
        return f'QF Day {qf_games}'
    
    pi = playoff_results.get('play_in', {})
    pi_count = sum(1 for k in ['game_a', 'game_b', 'game_c'] if pi.get(k) and pi[k].get('winner'))
    if pi_count > 0:
        return f'Play-In Day {pi_count}'
    
    return 'Playoffs'
```

- [ ] **Step 3: Add the new keys to the output dict**

Update the `output = {` block to include the new playoff data. Add these keys after `'playoff_matchup_probs'`:

```python
        'playoff_results': playoff_results_data,
        'championship_odds_history': championship_odds_history,
        'playoff_recaps': playoff_recaps,
```

So the full output dict becomes:

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
        'playoff_matchup_probs': playoff_matchup_probs,
        'playoff_results': playoff_results_data,
        'championship_odds_history': championship_odds_history,
        'playoff_recaps': playoff_recaps,
    }
```

- [ ] **Step 4: Run the export to verify no errors**

```bash
.venv/Scripts/python.exe export_dashboard_data.py
```

Expected: Script completes without errors. Since no playoff games exist yet, `playoff_results` should be `null` in the output and `championship_odds_history` should either be empty or contain a pre-playoff baseline.

- [ ] **Step 5: Verify the output**

```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
print('playoff_results:', d.get('playoff_results'))
print('championship_odds_history:', len(d.get('championship_odds_history', [])), 'entries')
print('playoff_recaps:', len(d.get('playoff_recaps', [])), 'recaps')
"
```

- [ ] **Step 6: Commit**

```bash
git add export_dashboard_data.py
git commit -m "feat: integrate playoff results, odds history, and recaps into dashboard export"
```

---

### Task 6: Apply real results to bracket on page load

**Files:**
- Modify: `docs/playoffs.js` (the `init` function and add `applyRealResults`)

- [ ] **Step 1: Store playoff data globally and call applyRealResults in init**

Add a new global variable at the top of the file (after `let _matchupProbs = {};` on line 24):

```javascript
let _realResults = null;  // locked playoff results from backend
```

Modify the `init` function. After `_matchupProbs = data.playoff_matchup_probs || {};` (line 159), add:

```javascript
        _realResults = data.playoff_results || null;
```

Then change the init sequence from:

```javascript
        resetBracket();
        loadFromURL();
        runMonteCarlo();
```

to:

```javascript
        resetBracket();
        if (_realResults) {
            applyRealResults();
        }
        loadFromURL();
        runMonteCarlo();
```

- [ ] **Step 2: Add the `applyRealResults` function**

Add after `resetBracketSilent` (after line 898):

```javascript
function applyRealResults() {
    if (!_realResults) return;

    const teamByCode = {};
    for (const t of _seeded) teamByCode[t.team] = t;

    // --- Play-In ---
    const pi = _realResults.play_in || {};

    if (pi.game_a && pi.game_a.winner) {
        const m = _bracket.playin[0];
        m.winner = teamByCode[pi.game_a.winner];
        m.score = { home: pi.game_a.home_score, away: pi.game_a.away_score };
        m.locked = true;
        const side = m.winner.team === m.a.team ? 'a' : 'b';
        cascadeForward('playin', 0, side);
    }

    if (pi.game_b && pi.game_b.winner) {
        const m = _bracket.playin[1];
        m.winner = teamByCode[pi.game_b.winner];
        m.score = { home: pi.game_b.home_score, away: pi.game_b.away_score };
        m.locked = true;
        const side = m.winner.team === m.a.team ? 'a' : 'b';
        cascadeForward('playin', 1, side);
    }

    if (pi.game_c && pi.game_c.winner) {
        const m = _bracket.playin[2];
        m.winner = teamByCode[pi.game_c.winner];
        m.score = { home: pi.game_c.home_score, away: pi.game_c.away_score };
        m.locked = true;
        const side = m.winner.team === m.a.team ? 'a' : 'b';
        cascadeForward('playin', 2, side);
    }

    // --- Quarterfinals ---
    const qf = _realResults.qf || {};
    const qfOrder = ['1v8', '2v7', '3v6', '4v5'];
    qfOrder.forEach((label, idx) => {
        const entry = qf[label];
        if (!entry) return;

        const m = _bracket.quarters[idx];
        // Store series state
        m.seriesScore = entry.series || [0, 0];
        m.seriesGames = entry.games || [];

        if (entry.winner) {
            m.winner = teamByCode[entry.winner];
            m.locked = true;
            const side = m.winner.team === m.a.team ? 'a' : 'b';
            cascadeForward('quarters', idx, side);
        } else if (entry.games && entry.games.length > 0) {
            // Partial series — lock matchup but no winner yet
            m.locked = false;  // user can still pick the winner
        }
    });

    // --- Semi-Finals ---
    const sf = _realResults.sf || {};
    if (sf.sf1 && sf.sf1.winner) {
        const m = _bracket.semis[0];
        m.winner = teamByCode[sf.sf1.winner];
        m.score = { home: sf.sf1.home_score, away: sf.sf1.away_score };
        m.locked = true;
        cascadeForward('semis', 0, m.winner.team === m.a.team ? 'a' : 'b');
    }
    if (sf.sf2 && sf.sf2.winner) {
        const m = _bracket.semis[1];
        m.winner = teamByCode[sf.sf2.winner];
        m.score = { home: sf.sf2.home_score, away: sf.sf2.away_score };
        m.locked = true;
        cascadeForward('semis', 1, m.winner.team === m.a.team ? 'a' : 'b');
    }

    // --- Final ---
    const fin = _realResults.final || {};
    if (fin.game && fin.winner) {
        const m = _bracket.final[0];
        m.winner = teamByCode[fin.winner];
        m.score = { home: fin.game.home_score, away: fin.game.away_score };
        m.locked = true;
        _champion = m.winner;
    }

    renderBracket();
}
```

- [ ] **Step 3: Update `renderSide` to show locked state and scores**

In the `renderSide` function (starting line 296), modify the click handler logic to respect the `locked` flag. Replace the onclick block (lines 318-323):

```javascript
    // Winner can be clicked to undo (unless locked by real results); non-winner side locked when winner is set
    let onclick = '';
    const matchup = _bracket[round][idx];
    const isLocked = matchup && matchup.locked;
    if (isWinner && !isLocked) {
        onclick = `onclick="undoPick('${round}',${idx})"`;
    } else if (!winner && !isLocked) {
        onclick = `onclick="pickWinner('${round}',${idx},'${side}')"`;
    }
```

- [ ] **Step 4: Update `renderMatchup` to show series score for locked QF matchups**

In `renderMatchup` (starting line 263), add series score display after the existing badge logic. Replace the `badgeHTML` block (lines 281-291):

```javascript
    let badgeHTML = '';
    const matchupData = _bracket[round][idx];
    if (label) {
        // Play-in games: show score if locked
        if (matchupData && matchupData.locked && matchupData.score) {
            badgeHTML = `<div class="series-badge">${label}<div class="locked-score">${matchupData.score.home} - ${matchupData.score.away}</div></div>`;
        } else {
            badgeHTML = `<div class="series-badge">${label}</div>`;
        }
    } else if (seriesLen > 1 && teamA && teamB) {
        // QF: show real series score if available
        if (matchupData && matchupData.seriesScore && (matchupData.seriesScore[0] > 0 || matchupData.seriesScore[1] > 0)) {
            const [hW, lW] = matchupData.seriesScore;
            const nameA = teamA.name.split(' ').pop();
            const nameB = teamB.name.split(' ').pop();
            const scoreText = `${nameA} ${hW} - ${lW} ${nameB}`;
            const prediction = matchupData.locked ? '' : getPredictedScore(teamA, teamB, seriesLen);
            badgeHTML = `<div class="series-badge">Best of ${seriesLen} · ${scoreText}${prediction}</div>`;
        } else {
            const prediction = getPredictedScore(teamA, teamB, seriesLen);
            badgeHTML = `<div class="series-badge">Best of ${seriesLen} · HCA 2-2-1<div class="series-prediction">${prediction}</div></div>`;
        }
    } else if (seriesLen > 1) {
        badgeHTML = `<div class="series-badge">Best of ${seriesLen} · HCA 2-2-1</div>`;
    } else {
        // SF/Final: show score if locked
        if (matchupData && matchupData.locked && matchupData.score) {
            badgeHTML = `<div class="series-badge">Single game<div class="locked-score">${matchupData.score.home} - ${matchupData.score.away}</div></div>`;
        } else {
            badgeHTML = `<div class="series-badge">Single game</div>`;
        }
    }
```

- [ ] **Step 5: Update `resetBracket` to preserve real results**

Change `resetBracket` to re-apply real results after reset. Replace lines 176-217:

```javascript
function resetBracket() {
    resetBracketSilent();
    if (_realResults) {
        applyRealResults();
    } else {
        renderBracket();
    }
    runMonteCarlo();
    updateURL();
}
```

- [ ] **Step 6: Commit**

```bash
git add docs/playoffs.js
git commit -m "feat: apply real playoff results to bracket on page load"
```

---

### Task 7: Add championship odds history chart

**Files:**
- Modify: `docs/playoffs.html` (add container)
- Modify: `docs/playoffs.js` (add render function)

- [ ] **Step 1: Add HTML containers**

In `playoffs.html`, after the MC chart stat-card (after line 492 `</div>`), add:

```html
        <div class="stat-card" id="championship-odds-section" style="margin-top:1rem;display:none">
            <h3>Championship Odds Tracker</h3>
            <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:1rem">
                How championship probabilities shift after each playoff game day.
            </p>
            <div id="championship-odds-chart"></div>
        </div>
```

- [ ] **Step 2: Add Plotly CDN to playoffs.html**

The page doesn't currently load Plotly. Add before the `</head>` tag:

```html
    <script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
```

- [ ] **Step 3: Add `renderChampionshipOdds` function in playoffs.js**

Add after `renderMonteCarloChart` (after line 646):

```javascript
function renderChampionshipOdds(history) {
    const section = document.getElementById('championship-odds-section');
    const container = document.getElementById('championship-odds-chart');
    if (!section || !container || !history || history.length < 2) return;

    section.style.display = '';

    // Collect all teams that ever appeared
    const allTeams = new Set();
    for (const entry of history) {
        for (const code of Object.keys(entry.odds || {})) allTeams.add(code);
    }

    const traces = [];
    for (const code of allTeams) {
        const xs = history.map(h => h.label || h.date);
        const ys = history.map(h => (h.odds || {})[code] || 0);
        const color = TEAM_COLORS[code] || '#555';
        const name = (_seeded.find(t => t.team === code) || {}).name || code;

        // Check if team is eliminated (last value is 0)
        const isEliminated = ys[ys.length - 1] === 0 && ys.some(v => v > 0);

        traces.push({
            x: xs,
            y: ys,
            name: name,
            mode: 'lines+markers',
            line: {
                color: isEliminated ? '#555' : color,
                width: isEliminated ? 1 : 2.5,
                dash: isEliminated ? 'dot' : 'solid',
            },
            marker: { size: 5 },
            hovertemplate: `<b>${name}</b><br>%{x}<br>%{y:.1f}%<extra></extra>`,
            opacity: isEliminated ? 0.4 : 1,
        });
    }

    // Sort: non-eliminated first (by last value desc), then eliminated
    traces.sort((a, b) => {
        const aLast = a.y[a.y.length - 1];
        const bLast = b.y[b.y.length - 1];
        if (aLast === 0 && bLast > 0) return 1;
        if (bLast === 0 && aLast > 0) return -1;
        return bLast - aLast;
    });

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: '#0f1117',
        font: { color: '#9ca3af', family: 'Inter' },
        margin: { t: 10, b: 50, l: 50, r: 10 },
        height: 400,
        xaxis: {
            gridcolor: '#2d2e3a',
            tickfont: { size: 11 },
        },
        yaxis: {
            title: 'Championship Probability (%)',
            gridcolor: '#2d2e3a',
            ticksuffix: '%',
            tickfont: { size: 11 },
            rangemode: 'tozero',
        },
        legend: {
            orientation: 'h',
            y: -0.25,
            x: 0.5,
            xanchor: 'center',
            font: { size: 10 },
        },
        hovermode: 'x unified',
    };

    Plotly.newPlot('championship-odds-chart', traces, layout, {
        displayModeBar: false,
        responsive: true,
    });
}
```

- [ ] **Step 4: Call `renderChampionshipOdds` from init**

In the `init` function, after `runMonteCarlo();` (around line 169), add:

```javascript
        renderChampionshipOdds(data.championship_odds_history || []);
```

- [ ] **Step 5: Commit**

```bash
git add docs/playoffs.html docs/playoffs.js
git commit -m "feat: add championship odds tracker Plotly chart to playoffs page"
```

---

### Task 8: Add playoff recap cards

**Files:**
- Modify: `docs/playoffs.html` (add container and CSS)
- Modify: `docs/playoffs.js` (add render function)

- [ ] **Step 1: Add HTML container**

In `playoffs.html`, after the championship odds section, add:

```html
        <div class="stat-card" id="playoff-recaps-section" style="margin-top:1rem;display:none">
            <h3>Game Recaps</h3>
            <div id="playoff-recaps"></div>
        </div>
```

- [ ] **Step 2: Add CSS for recap cards**

In the `<style>` block of `playoffs.html`, add:

```css
        /* ── Recap cards ─────────────────────────────────────── */
        .recap-cards {
            display: grid;
            gap: 0.75rem;
        }

        .recap-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1rem 1.25rem;
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 0.75rem;
            align-items: center;
        }

        .recap-card.upset {
            border-color: rgba(251, 191, 36, 0.4);
        }

        .recap-team {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .recap-team.away {
            justify-content: flex-end;
            text-align: right;
        }

        .recap-team-name {
            font-weight: 600;
            font-size: 0.9rem;
        }

        .recap-team.loser .recap-team-name {
            opacity: 0.5;
        }

        .recap-score {
            font-size: 1.5rem;
            font-weight: 800;
            text-align: center;
            font-variant-numeric: tabular-nums;
        }

        .recap-meta {
            grid-column: 1 / -1;
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            font-size: 0.75rem;
            color: var(--text-muted);
            border-top: 1px solid var(--border);
            padding-top: 0.5rem;
        }

        .recap-badge {
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.7rem;
        }

        .recap-badge.upset-badge {
            background: rgba(251, 191, 36, 0.15);
            color: #fbbf24;
        }

        .recap-badge.round-badge {
            background: rgba(99, 102, 241, 0.15);
            color: #818cf8;
        }

        .recap-odds-delta {
            font-size: 0.72rem;
            font-variant-numeric: tabular-nums;
        }

        .recap-odds-delta .positive {
            color: #22c55e;
        }

        .recap-odds-delta .negative {
            color: #f87171;
        }
```

- [ ] **Step 3: Add `renderPlayoffRecaps` function in playoffs.js**

Add after `renderChampionshipOdds`:

```javascript
function renderPlayoffRecaps(recaps) {
    const section = document.getElementById('playoff-recaps-section');
    const container = document.getElementById('playoff-recaps');
    if (!section || !container || !recaps || !recaps.length) return;

    section.style.display = '';

    const teamName = code => {
        const t = _seeded.find(s => s.team === code);
        return t ? t.name : code;
    };

    let html = '<div class="recap-cards">';

    for (const r of recaps) {
        const homeColor = TEAM_COLORS[r.home] || '#555';
        const awayColor = TEAM_COLORS[r.away] || '#555';
        const isHomeWinner = r.winner === r.home;
        const upsetClass = r.is_upset ? ' upset' : '';

        // Odds delta
        let oddsHTML = '';
        if (r.championship_odds_before && r.championship_odds_after) {
            const teams = [r.home, r.away];
            const deltas = teams.map(t => {
                const before = r.championship_odds_before[t] || 0;
                const after = r.championship_odds_after[t] || 0;
                const diff = after - before;
                const cls = diff >= 0 ? 'positive' : 'negative';
                const sign = diff >= 0 ? '+' : '';
                return `<span class="recap-odds-delta">${teamName(t)}: ${after.toFixed(1)}% (<span class="${cls}">${sign}${diff.toFixed(1)}</span>)</span>`;
            });
            oddsHTML = deltas.join(' · ');
        }

        html += `<div class="recap-card${upsetClass}">
            <div class="recap-team${isHomeWinner ? '' : ' loser'}">
                <div class="recap-team-color" style="width:4px;height:28px;border-radius:2px;background:${homeColor}"></div>
                <div>
                    <div class="recap-team-name">${teamName(r.home)}</div>
                    <div style="font-size:0.7rem;color:var(--text-muted)">Home</div>
                </div>
            </div>
            <div class="recap-score">${r.home_score} - ${r.away_score}</div>
            <div class="recap-team away${isHomeWinner ? ' loser' : ''}">
                <div>
                    <div class="recap-team-name">${teamName(r.away)}</div>
                    <div style="font-size:0.7rem;color:var(--text-muted)">Away</div>
                </div>
                <div class="recap-team-color" style="width:4px;height:28px;border-radius:2px;background:${awayColor}"></div>
            </div>
            <div class="recap-meta">
                <span class="recap-badge round-badge">${r.round}</span>
                ${r.series_label ? `<span>${r.series_label}</span>` : ''}
                ${r.is_upset ? '<span class="recap-badge upset-badge">UPSET</span>' : ''}
                <span>Win prob: ${r.pre_game_win_prob.toFixed(0)}%</span>
                ${r.date ? `<span>${r.date}</span>` : ''}
                ${oddsHTML ? `<span style="margin-left:auto">${oddsHTML}</span>` : ''}
            </div>
        </div>`;
    }

    html += '</div>';
    container.innerHTML = html;
}
```

- [ ] **Step 4: Call `renderPlayoffRecaps` from init**

In the `init` function, after the `renderChampionshipOdds` call, add:

```javascript
        renderPlayoffRecaps(data.playoff_recaps || []);
```

- [ ] **Step 5: Commit**

```bash
git add docs/playoffs.html docs/playoffs.js
git commit -m "feat: add playoff recap cards with scores, upset badges, and odds deltas"
```

---

### Task 9: Update page title and subtitle for live mode

**Files:**
- Modify: `docs/playoffs.js` (update init to change title/subtitle when real results exist)

- [ ] **Step 1: Update the page header when real results are loaded**

In the `init` function, after the `applyRealResults` call, add:

```javascript
        if (_realResults) {
            const h1 = document.querySelector('header h1');
            const sub = document.querySelector('header .subtitle');
            if (h1) h1.textContent = '\u{1F3C6} Playoff Bracket';
            if (sub) sub.textContent = 'Live results are locked. Click unplayed matchups to simulate forward.';
        }
```

- [ ] **Step 2: Commit**

```bash
git add docs/playoffs.js
git commit -m "style: update page title when live playoff results are present"
```

---

### Task 10: Generate pre-playoff baseline odds

**Files:**
- Modify: `export_dashboard_data.py` (already handled in Task 5)

This step is about running the pipeline once to seed the `championship_odds_history` with the pre-playoff baseline, before any playoff games are played.

- [ ] **Step 1: Run the full export**

```bash
.venv/Scripts/python.exe export_dashboard_data.py
```

- [ ] **Step 2: Verify the baseline was created**

```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/dashboard.json', encoding='utf-8'))
history = d.get('championship_odds_history', [])
print(f'History entries: {len(history)}')
if history:
    print(f'First entry: {history[0][\"label\"]}')
    odds = history[0]['odds']
    for team, pct in sorted(odds.items(), key=lambda x: -x[1])[:5]:
        print(f'  {team}: {pct}%')
"
```

Expected: One "Pre-Playoff" entry with championship odds for all 10 teams.

- [ ] **Step 3: Commit the updated dashboard data**

```bash
git add docs/data/current/dashboard.json
git commit -m "data: seed championship odds history with pre-playoff baseline"
```

---

### Task 11: Update CI schedule for playoffs

**Files:**
- Modify: `.github/workflows/refresh_data.yml`

- [ ] **Step 1: Check the current schedule**

```bash
cat .github/workflows/refresh_data.yml | head -20
```

- [ ] **Step 2: Update the cron schedule**

The exact days will depend on the playoff calendar. For the play-in and quarterfinal phase, games typically happen on Tuesday-Friday. Update the cron to run daily during playoffs:

Change the schedule from the regular-season pattern (Wed-Sat) to daily:

```yaml
    schedule:
      - cron: '0 1 * * *'  # Daily at 01:00 UTC during playoffs
```

Note: This should be adjusted back after the season ends. Add a comment:

```yaml
    schedule:
      # During regular season: '0 1 * * 3-6' (Wed-Sat)
      # During playoffs: '0 1 * * *' (daily)
      - cron: '0 1 * * *'
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/refresh_data.yml
git commit -m "ci: switch to daily refresh schedule for playoff phase"
```

---

### Task 12: Update about page

**Files:**
- Modify: `docs/about.html`

- [ ] **Step 1: Add a section about the playoff tracker features**

Find the methodology or features section in `about.html` and add a paragraph about the new playoff tracking features:

- Live playoff bracket with locked real results
- Championship odds tracker showing probability shifts after each game day
- Post-game recap cards with upset detection and odds deltas
- 10,000-iteration Monte Carlo simulation from current bracket state

- [ ] **Step 2: Commit**

```bash
git add docs/about.html
git commit -m "docs: add playoff tracker features to about page"
```

---

### Task 13: End-to-end verification

- [ ] **Step 1: Run the full pipeline**

```bash
.venv/Scripts/python.exe export_dashboard_data.py
```

Verify no errors in output.

- [ ] **Step 2: Start a local server and test the playoffs page**

```bash
cd docs && python -m http.server 8000
```

Open `http://localhost:8000/playoffs.html` and verify:
- Bracket loads correctly with team names and probabilities
- No real results locked yet (all interactive)
- MC chart shows championship odds
- Championship odds tracker section is hidden (less than 2 data points)
- Recap cards section is hidden (no games)
- Auto-fill and reset still work
- Share bracket URL still works

- [ ] **Step 3: Commit all remaining changes and push**

```bash
git push
```
