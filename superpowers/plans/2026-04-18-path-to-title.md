# Path to Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "Path to Title" section to playoffs.html that visualizes each playoff-eligible team's road to the championship, as a hybrid grid (all teams at a glance) + click-to-expand SVG branching tree (detail view per team).

**Architecture:** Server-side Monte Carlo computation in `export_dashboard_data.py` reusing the same simulation engine as `compute_championship_odds`. Results serialized to `dashboard.json` under a new `path_to_title` key. Frontend renders the grid (HTML table) and detail tree (inline SVG) from the pre-computed data — no client-side simulation needed.

**Tech Stack:** Python (Monte Carlo), vanilla JS (rendering), inline SVG (tree), CSS (grid styling). No new libraries.

**Testing approach:** This codebase has no test runner (per CLAUDE.md). Each task uses pragmatic validation: a small Python sanity script checks backend shape; Playwright MCP browser verification validates frontend rendering. Commits happen after validation passes.

---

## File Structure

**Files to modify:**
- `export_dashboard_data.py` — add `compute_path_to_title` function and integrate into output (new lines in an already-long file; follow the pattern of `compute_championship_odds` / `build_playoff_recaps`)
- `docs/playoffs.html` — add new `<section id="path-to-title-section">` container and inline CSS
- `docs/playoffs.js` — add `renderPathToTitle`, `renderPathDetailTree`, `pathRoundCell` and call from `init()`
- `docs/about.html` — update Playoffs description to mention Path to Title

**No new files created.** Matching the existing playoffs tracker pattern where all playoff code lives in `playoffs.js` / `playoffs.html` / `export_dashboard_data.py`.

---

## Task 1: Backend — `compute_path_to_title` function

**Files:**
- Modify: `export_dashboard_data.py` (insert new function right before the `# ── Build output ───` comment at line ~1631, after `build_playoff_recaps`)

- [ ] **Step 1: Insert `compute_path_to_title` function**

Open `export_dashboard_data.py`. Find the line:

```python
        # Sort by date descending
        recaps.sort(key=lambda r: r.get('date', ''), reverse=True)

        return recaps
```

(That's the end of `build_playoff_recaps`, around line 1627-1629.)

Directly after `return recaps` and before the next blank line, insert this new function (use the same indentation as `build_playoff_recaps` — 4 spaces):

```python
    def compute_path_to_title(playoff_results, matchup_probs, seeded_teams, n_sims=10000):
        """
        For each playoff-eligible team, simulate the remaining bracket n_sims times.
        Track reach probability per round, opponent distribution, and win probabilities.
        Returns list of per-team path entries matching the path_to_title spec.
        """
        import random

        if len(seeded_teams) < 10:
            return []

        seed_codes = [t['team'] for t in seeded_teams[:10]]

        def _get_prob(team_a, team_b, venue):
            entry = (matchup_probs.get(team_a) or {}).get(team_b)
            if entry:
                return entry.get(venue, 0.5)
            return 0.5

        def _sim_game(team_a, team_b, venue):
            p = _get_prob(team_a, team_b, venue)
            return team_a if random.random() < p else team_b

        def _sim_series(higher, lower):
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

        # Extract locked results (same pattern as compute_championship_odds)
        pi_a_winner = None
        pi_a_loser = None
        pi_b_winner = None
        pi_c_winner = None
        qf_winners = {'1v8': None, '2v7': None, '3v6': None, '4v5': None}
        qf_series_state = {}
        sf_winners = {'sf1': None, 'sf2': None}
        final_winner = None

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

        # Per-team counters: reach[round] and opponent_wins[round][opp] and opponent_faced[round][opp]
        round_keys = ['play_in', 'qf', 'sf', 'final', 'champion']
        reach = {code: {r: 0 for r in round_keys} for code in seed_codes}
        opp_faced = {code: {r: {} for r in round_keys} for code in seed_codes}
        opp_wins = {code: {r: {} for r in round_keys} for code in seed_codes}

        play_in_teams = set(seed_codes[6:10])  # seeds 7-10 participate in play-in

        for _ in range(n_sims):
            # Play-In
            ga_w = pi_a_winner or _sim_game(seed_codes[6], seed_codes[7], 'home')
            ga_l = pi_a_loser or (seed_codes[7] if ga_w == seed_codes[6] else seed_codes[6])
            gb_w = pi_b_winner or _sim_game(seed_codes[8], seed_codes[9], 'home')
            gb_l = seed_codes[9] if gb_w == seed_codes[8] else seed_codes[8]
            gc_w = pi_c_winner or _sim_game(ga_l, gb_w, 'home')

            # Mark reach: all 4 play-in teams reach play-in
            for t in play_in_teams:
                reach[t]['play_in'] += 1

            # s7 (winner of Game A), s8 (winner of Game C)
            s7 = ga_w
            s8 = gc_w

            # Seeds 1-6 and s7, s8 reach QF
            qf_participants = set(seed_codes[:6]) | {s7, s8}
            for t in qf_participants:
                reach[t]['qf'] += 1

            qf_pairs = {
                '1v8': (seed_codes[0], s8),
                '2v7': (seed_codes[1], s7),
                '3v6': (seed_codes[2], seed_codes[5]),
                '4v5': (seed_codes[3], seed_codes[4]),
            }

            qf_w = {}
            for label, (higher, lower) in qf_pairs.items():
                # Record opponents faced in QF
                opp_faced[higher]['qf'][lower] = opp_faced[higher]['qf'].get(lower, 0) + 1
                opp_faced[lower]['qf'][higher] = opp_faced[lower]['qf'].get(higher, 0) + 1

                if qf_winners[label]:
                    qf_w[label] = qf_winners[label]
                elif label in qf_series_state:
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

                winner = qf_w[label]
                loser = lower if winner == higher else higher
                opp_wins[winner]['qf'][loser] = opp_wins[winner]['qf'].get(loser, 0) + 1

            # SF
            sf1_participants = {qf_w['1v8'], qf_w['4v5']}
            sf2_participants = {qf_w['2v7'], qf_w['3v6']}
            for t in sf1_participants | sf2_participants:
                reach[t]['sf'] += 1

            opp_faced[qf_w['1v8']]['sf'][qf_w['4v5']] = opp_faced[qf_w['1v8']]['sf'].get(qf_w['4v5'], 0) + 1
            opp_faced[qf_w['4v5']]['sf'][qf_w['1v8']] = opp_faced[qf_w['4v5']]['sf'].get(qf_w['1v8'], 0) + 1
            opp_faced[qf_w['2v7']]['sf'][qf_w['3v6']] = opp_faced[qf_w['2v7']]['sf'].get(qf_w['3v6'], 0) + 1
            opp_faced[qf_w['3v6']]['sf'][qf_w['2v7']] = opp_faced[qf_w['3v6']]['sf'].get(qf_w['2v7'], 0) + 1

            sf1_w = sf_winners['sf1'] or _sim_game(qf_w['1v8'], qf_w['4v5'], 'neutral')
            sf2_w = sf_winners['sf2'] or _sim_game(qf_w['2v7'], qf_w['3v6'], 'neutral')

            sf1_loser = qf_w['4v5'] if sf1_w == qf_w['1v8'] else qf_w['1v8']
            sf2_loser = qf_w['3v6'] if sf2_w == qf_w['2v7'] else qf_w['2v7']
            opp_wins[sf1_w]['sf'][sf1_loser] = opp_wins[sf1_w]['sf'].get(sf1_loser, 0) + 1
            opp_wins[sf2_w]['sf'][sf2_loser] = opp_wins[sf2_w]['sf'].get(sf2_loser, 0) + 1

            # Final
            reach[sf1_w]['final'] += 1
            reach[sf2_w]['final'] += 1

            opp_faced[sf1_w]['final'][sf2_w] = opp_faced[sf1_w]['final'].get(sf2_w, 0) + 1
            opp_faced[sf2_w]['final'][sf1_w] = opp_faced[sf2_w]['final'].get(sf1_w, 0) + 1

            champ = final_winner or _sim_game(sf1_w, sf2_w, 'neutral')
            reach[champ]['champion'] += 1
            final_loser = sf2_w if champ == sf1_w else sf1_w
            opp_wins[champ]['final'][final_loser] = opp_wins[champ]['final'].get(final_loser, 0) + 1

        # Build output per team
        def _build_branches(team, round_key):
            """Top 2-3 opponents sorted by reach_prob_for_opp desc, truncate at cum 90% or 3 entries."""
            opps = opp_faced[team][round_key]
            team_reach = reach[team][round_key]
            if team_reach == 0:
                return []
            sorted_opps = sorted(opps.items(), key=lambda kv: kv[1], reverse=True)
            branches = []
            cum = 0.0
            for opp_code, faced_count in sorted_opps:
                reach_pct = faced_count / team_reach * 100
                wins_vs = opp_wins[team][round_key].get(opp_code, 0)
                win_pct = wins_vs / faced_count * 100 if faced_count > 0 else 0.0
                branches.append({
                    'opponent': opp_code,
                    'reach_prob_for_opp': round(reach_pct, 1),
                    'win_prob_vs': round(win_pct, 1),
                })
                cum += reach_pct
                if len(branches) >= 3 or cum >= 90.0:
                    break
            return branches

        def _round_win_prob(team, round_key):
            """P(team wins round_key | reached it) = (times reached next round) / (times reached this round)."""
            this_round_count = reach[team][round_key]
            if this_round_count == 0:
                return 0.0
            # The "win" means advancing. For qf, advancing means reaching sf. For sf, final. For final, champion.
            next_key = {'play_in': 'qf', 'qf': 'sf', 'sf': 'final', 'final': 'champion'}.get(round_key)
            if next_key is None:
                return 0.0
            # Play-In win means the team reached QF (i.e., they were a play-in team AND reached QF)
            if round_key == 'play_in':
                # Only teams with reach[play_in] > 0 count; the fraction of those who reach QF
                return round(reach[team]['qf'] / this_round_count * 100, 1) if this_round_count > 0 else 0.0
            return round(reach[team][next_key] / this_round_count * 100, 1)

        # Determine completed rounds from playoff_results for each team
        def _completed_round_data(team):
            """Returns dict of round -> completed round info, based on playoff_results."""
            done = {}
            if not playoff_results:
                return done

            # Play-In
            pi = playoff_results.get('play_in', {})
            for gk in ['game_a', 'game_b', 'game_c']:
                g = pi.get(gk)
                if g and g.get('winner') and team in (g.get('home'), g.get('away')):
                    opp = g['away'] if team == g['home'] else g['home']
                    done['play_in'] = {
                        'status': 'completed',
                        'actual_opponent': opp,
                        'actual_result': 'won' if g['winner'] == team else 'lost',
                        'series': [1, 0] if g['winner'] == team else [0, 1],
                        'reach_prob': 100.0,
                    }

            # QF
            qf_data = playoff_results.get('qf', {})
            for label, qf_entry in qf_data.items():
                higher = qf_entry.get('higher_seed')
                lower = qf_entry.get('lower_seed')
                if team not in (higher, lower):
                    continue
                opp = lower if team == higher else higher
                series = qf_entry.get('series', [0, 0])
                t_wins = series[0] if team == higher else series[1]
                o_wins = series[1] if team == higher else series[0]
                if qf_entry.get('winner'):
                    done['qf'] = {
                        'status': 'completed',
                        'actual_opponent': opp,
                        'actual_result': 'won' if qf_entry['winner'] == team else 'lost',
                        'series': [t_wins, o_wins],
                        'reach_prob': 100.0,
                    }
                elif series[0] > 0 or series[1] > 0:
                    done['qf'] = {
                        'status': 'in_progress',
                        'actual_opponent': opp,
                        'series': [t_wins, o_wins],
                        'reach_prob': 100.0,
                    }

            # SF
            sf_data = playoff_results.get('sf', {})
            for sk in ['sf1', 'sf2']:
                g = sf_data.get(sk)
                if g and g.get('winner') and team in (g.get('home'), g.get('away')):
                    opp = g['away'] if team == g['home'] else g['home']
                    done['sf'] = {
                        'status': 'completed',
                        'actual_opponent': opp,
                        'actual_result': 'won' if g['winner'] == team else 'lost',
                        'series': [1, 0] if g['winner'] == team else [0, 1],
                        'reach_prob': 100.0,
                    }

            # Final
            final_data = playoff_results.get('final', {})
            g = final_data.get('game') if final_data else None
            if g and g.get('winner') and team in (g.get('home'), g.get('away')):
                opp = g['away'] if team == g['home'] else g['home']
                done['final'] = {
                    'status': 'completed',
                    'actual_opponent': opp,
                    'actual_result': 'won' if g['winner'] == team else 'lost',
                    'series': [1, 0] if g['winner'] == team else [0, 1],
                    'reach_prob': 100.0,
                }

            return done

        result = []
        for idx, code in enumerate(seed_codes):
            is_play_in_team = idx >= 6
            completed = _completed_round_data(code)

            # Determine status + eliminated_at
            champ_pct = reach[code]['champion'] / n_sims * 100
            is_champion = final_winner == code

            # Find earliest completed 'lost' round
            eliminated_at = None
            if not is_champion:
                for rk in ['play_in', 'qf', 'sf', 'final']:
                    if completed.get(rk, {}).get('actual_result') == 'lost':
                        eliminated_at = rk
                        break

            if is_champion:
                status = 'champion'
            elif eliminated_at:
                status = 'eliminated'
            else:
                status = 'alive'

            # Build rounds array
            rounds = []
            for rk in ['play_in', 'qf', 'sf', 'final']:
                if rk == 'play_in' and not is_play_in_team:
                    rounds.append({'round': rk, 'status': 'unreached', 'reach_prob': 0.0})
                    continue

                if rk in completed:
                    rounds.append({'round': rk, **completed[rk]})
                    continue

                # Not completed — upcoming or unreached
                rp = reach[code][rk] / n_sims * 100
                if rp == 0:
                    rounds.append({'round': rk, 'status': 'unreached', 'reach_prob': 0.0})
                else:
                    rounds.append({
                        'round': rk,
                        'status': 'upcoming',
                        'reach_prob': round(rp, 1),
                        'win_prob': _round_win_prob(code, rk),
                        'branches': _build_branches(code, rk),
                    })

            result.append({
                'team': code,
                'status': status,
                'eliminated_at': eliminated_at,
                'championship_odds': round(champ_pct, 1),
                'rounds': rounds,
            })

        # Sort by championship odds desc, eliminated teams at bottom
        result.sort(key=lambda e: (
            0 if e['status'] != 'eliminated' else 1,
            -e['championship_odds']
        ))

        return result
```

- [ ] **Step 2: Write a sanity-check script**

Create `check_path_to_title.py` in the repo root:

```python
"""Quick sanity check for compute_path_to_title."""
import importlib.util, json, os, sys

# Load export_dashboard_data as a module so we can reach its inner functions.
# Simplest: run export and inspect dashboard.json instead.
dash_path = os.path.join('docs', 'data', 'current', 'dashboard.json')
with open(dash_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

path = data.get('path_to_title')
assert path is not None, "path_to_title key missing from dashboard.json"
assert isinstance(path, list), f"path_to_title must be a list, got {type(path)}"

if not path:
    print("path_to_title is empty (no playoff-eligible teams). This is expected pre-playoffs when Monte Carlo has not run.")
    sys.exit(0)

assert len(path) == 10, f"Expected 10 playoff-eligible teams, got {len(path)}"

for entry in path:
    assert 'team' in entry
    assert entry['status'] in ('alive', 'eliminated', 'champion')
    assert entry['eliminated_at'] in (None, 'play_in', 'qf', 'sf', 'final')
    assert isinstance(entry['championship_odds'], (int, float))
    assert 0 <= entry['championship_odds'] <= 100
    assert isinstance(entry['rounds'], list)
    assert len(entry['rounds']) == 4, f"{entry['team']} should have 4 rounds, got {len(entry['rounds'])}"
    for r in entry['rounds']:
        assert r['round'] in ('play_in', 'qf', 'sf', 'final')
        assert r['status'] in ('completed', 'in_progress', 'upcoming', 'unreached')
        if r['status'] == 'upcoming':
            assert 'reach_prob' in r and 'win_prob' in r and 'branches' in r
            for b in r['branches']:
                assert 'opponent' in b and 'reach_prob_for_opp' in b and 'win_prob_vs' in b

# Pre-playoff sanity: with no real results, seeds 1-6 should have play_in status=unreached
# and seeds 7-10 should have play_in status=upcoming
pre_playoff = not data.get('playoff_results')
if pre_playoff:
    by_team = {e['team']: e for e in path}
    seeded = data.get('teams', [])[:10]
    top6 = [t['team'] for t in seeded[:6]]
    bottom4 = [t['team'] for t in seeded[6:10]]
    for t in top6:
        e = by_team.get(t)
        if e:
            pi = next((r for r in e['rounds'] if r['round'] == 'play_in'), None)
            assert pi and pi['status'] == 'unreached', f"{t} should have play_in status=unreached"
    for t in bottom4:
        e = by_team.get(t)
        if e:
            pi = next((r for r in e['rounds'] if r['round'] == 'play_in'), None)
            assert pi and pi['status'] == 'upcoming', f"{t} should have play_in status=upcoming, got {pi}"

# Championship odds should sum close to 100 (small Monte Carlo noise)
total = sum(e['championship_odds'] for e in path)
assert 98.0 <= total <= 102.0, f"championship_odds across all teams should sum close to 100, got {total}"

print(f"OK — path_to_title has {len(path)} teams, sum of championship odds = {total:.1f}")
print("Top 3 by championship odds:")
for e in path[:3]:
    print(f"  {e['team']}: {e['championship_odds']}% ({e['status']})")
```

- [ ] **Step 3: Run sanity script — expect failure (not yet integrated)**

Run: `.venv/Scripts/python.exe check_path_to_title.py`

Expected output: `AssertionError: path_to_title key missing from dashboard.json`

(The function is defined but not yet wired into the output. Task 2 wires it up.)

- [ ] **Step 4: Commit**

```bash
git add export_dashboard_data.py check_path_to_title.py
git commit -m "feat: add compute_path_to_title Monte Carlo function

Computes per-team path probabilities through the playoff bracket: reach
probability per round, top opponent branches, and win probability per round.
Reuses the simulation engine from compute_championship_odds.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Backend — Integrate `path_to_title` into dashboard output

**Files:**
- Modify: `export_dashboard_data.py` (two edits — one inside the playoff tracking block, one in the output dict)

- [ ] **Step 1: Add a variable initialization**

Find the playoff tracking init block (around line 1634-1638):

```python
    # ── Playoff tracking ─────────────────────────────────────────────────────
    playoff_results_data = None
    championship_odds = {}
    playoff_recaps = []
    championship_odds_history = []
```

Add a new line after `championship_odds_history = []`:

```python
    # ── Playoff tracking ─────────────────────────────────────────────────────
    playoff_results_data = None
    championship_odds = {}
    playoff_recaps = []
    championship_odds_history = []
    path_to_title = []
```

- [ ] **Step 2: Call `compute_path_to_title` when playoff_results exist**

Find the block where `build_playoff_recaps` is called (around line 1677-1680):

```python
            # Build recap cards
            playoff_recaps = build_playoff_recaps(
                playoff_results_data, prev_odds, championship_odds,
                playoff_matchup_probs, seeded
            )
```

Directly after that call, add:

```python
            # Build path-to-title data
            path_to_title = compute_path_to_title(
                playoff_results_data, playoff_matchup_probs, seeded
            )
```

- [ ] **Step 3: Also call `compute_path_to_title` in the pre-playoff branch**

Find the pre-playoff baseline block (around line 1694-1703):

```python
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

Modify this to always compute `path_to_title` when we have matchup_probs and 10 seeded teams, even without playoff_results. Replace the block with:

```python
            if playoff_matchup_probs and len(teams) >= 10:
                seeded = teams[:10]
                if not championship_odds_history:
                    championship_odds = compute_championship_odds(
                        None, playoff_matchup_probs, seeded
                    )
                    championship_odds_history = [{
                        'date': datetime.utcnow().strftime('%Y-%m-%d'),
                        'label': 'Pre-Playoff',
                        'odds': championship_odds,
                    }]
                path_to_title = compute_path_to_title(
                    None, playoff_matchup_probs, seeded
                )
```

- [ ] **Step 4: Add `path_to_title` to the output dict**

Find the output dict (around line 1705-1723):

```python
    output = {
        'round': round_num,
        'updated': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        ...
        'playoff_matchup_probs': playoff_matchup_probs,
        'playoff_results': playoff_results_data,
        'championship_odds_history': championship_odds_history,
        'playoff_recaps': playoff_recaps,
    }
```

Add the new key right after `playoff_recaps`:

```python
        'playoff_recaps': playoff_recaps,
        'path_to_title': path_to_title,
    }
```

- [ ] **Step 5: Run the export**

Run: `.venv/Scripts/python.exe export_dashboard_data.py`

Expected output includes:
```
  Playoff matchup probs: 10 teams, 90 pairs
```
and the script exits with code 0.

- [ ] **Step 6: Run sanity script — expect success**

Run: `.venv/Scripts/python.exe check_path_to_title.py`

Expected output:
```
OK — path_to_title has 10 teams, sum of championship odds = ~100.0
Top 3 by championship odds:
  <team>: <pct>% (alive)
  ...
```

- [ ] **Step 7: Commit**

```bash
git add export_dashboard_data.py docs/data/current/dashboard.json
git commit -m "feat: integrate path_to_title into dashboard export

Wires compute_path_to_title into the playoff tracking block so the frontend
has per-team path data. Also computes a baseline during pre-playoff state
(when no games have been played yet) so the new section can render from
day 1.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Frontend HTML/CSS — Path to Title section container

**Files:**
- Modify: `docs/playoffs.html` (add CSS block + new `<section>` container)

- [ ] **Step 1: Add CSS styles**

Open `docs/playoffs.html`. Find the closing `</style>` tag (around line 530, just before `</head>`). Insert this new CSS block directly before `</style>`:

```css
        /* ── Path to Title ──────────────────────────────────── */
        .ptt-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }

        .ptt-table thead th {
            font-family: 'Outfit', sans-serif;
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-muted);
            text-align: center;
            padding: 0.5rem 0.4rem;
            border-bottom: 1px solid var(--border);
        }

        .ptt-table thead th.ptt-th-team {
            text-align: left;
            padding-left: 0.8rem;
        }

        .ptt-row {
            border-bottom: 1px solid var(--border);
            cursor: pointer;
            transition: background 0.15s ease;
        }

        .ptt-row:hover:not(.ptt-row-eliminated) {
            background: var(--bg-secondary);
        }

        .ptt-row.ptt-row-eliminated {
            opacity: 0.45;
            cursor: default;
        }

        .ptt-row.ptt-row-champion {
            background: rgba(212, 175, 55, 0.08);
        }

        .ptt-row td {
            padding: 0.65rem 0.4rem;
            text-align: center;
            vertical-align: middle;
            font-variant-numeric: tabular-nums;
        }

        .ptt-row td.ptt-td-team {
            text-align: left;
            padding-left: 0.8rem;
        }

        .ptt-team-wrap {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .ptt-status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }

        .ptt-status-dot.alive { background: #22c55e; }
        .ptt-status-dot.eliminated { background: #64748b; }
        .ptt-status-dot.champion { background: #fbbf24; }

        .ptt-team-name {
            font-weight: 600;
        }

        .ptt-team-color {
            width: 4px;
            height: 22px;
            border-radius: 2px;
            flex-shrink: 0;
        }

        .ptt-cell-won {
            color: #22c55e;
            font-weight: 700;
        }

        .ptt-cell-lost {
            color: #f87171;
            font-weight: 700;
        }

        .ptt-cell-progress {
            color: var(--text-primary);
            font-weight: 700;
        }

        .ptt-cell-progress::before {
            content: '';
            display: inline-block;
            width: 6px;
            height: 6px;
            background: #22c55e;
            border-radius: 50%;
            margin-right: 0.35rem;
            animation: pttPulse 1.4s ease-in-out infinite;
        }

        @keyframes pttPulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.35; }
        }

        .ptt-cell-dash {
            color: var(--text-muted);
        }

        .ptt-cell-pct {
            font-weight: 700;
        }

        .ptt-cell-pct-high { color: #22c55e; }
        .ptt-cell-pct-mid { color: #f59e0b; }
        .ptt-cell-pct-low { color: #f87171; }

        .ptt-cell-champ {
            font-family: 'Outfit', sans-serif;
            font-weight: 800;
            font-size: 0.95rem;
        }

        .ptt-expand-hint {
            font-size: 0.7rem;
            color: var(--text-muted);
        }

        .ptt-row.ptt-row-expanded + .ptt-detail-row {
            display: table-row;
        }

        .ptt-detail-row {
            display: none;
        }

        .ptt-detail-row td {
            padding: 1rem 0.8rem 1.25rem;
            background: var(--bg-secondary);
        }

        .ptt-tree-svg {
            display: block;
            width: 100%;
            height: auto;
            max-height: 420px;
        }

        @media (max-width: 768px) {
            .ptt-table { font-size: 0.75rem; }
            .ptt-expand-hint { display: none; }
        }
```

- [ ] **Step 2: Add the new `<section>` container**

Find the last `stat-card` block inside `<main>` — it's the recaps section at line 592-595:

```html
        <div class="stat-card" id="playoff-recaps-section" style="margin-top:1rem;display:none">
            <h3>Game Recaps</h3>
            <div id="playoff-recaps"></div>
        </div>
```

Directly after this closing `</div>` (before `</main>`), insert:

```html
        <div class="stat-card" id="path-to-title-section" style="margin-top:1rem;display:none">
            <h3>Path to Title</h3>
            <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:1rem">
                Each team's road to the championship: completed rounds with actual results,
                upcoming rounds with probabilities from 10,000-run Monte Carlo. Click any alive
                team's row to see the branching tree of possible opponents.
            </p>
            <div style="overflow-x:auto">
                <table class="ptt-table" id="ptt-table">
                    <thead>
                        <tr>
                            <th class="ptt-th-team">Team</th>
                            <th>Play-In</th>
                            <th>QF</th>
                            <th>SF</th>
                            <th>Final</th>
                            <th>🏆</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="ptt-tbody"></tbody>
                </table>
            </div>
        </div>
```

- [ ] **Step 3: Verify HTML is well-formed**

Run: `.venv/Scripts/python.exe -c "from xml.etree import ElementTree as ET; import re; html = open('docs/playoffs.html','r',encoding='utf-8').read(); body = re.search(r'<body>(.*)</body>', html, re.DOTALL).group(1); print('body length:', len(body), 'chars — OK if > 0')"`

Expected: a positive character count (quick smoke test that the file still reads).

- [ ] **Step 4: Commit**

```bash
git add docs/playoffs.html
git commit -m "feat: add Path to Title section container and styles

New empty section on playoffs.html with grid table shell and CSS for status
indicators, color-coded probability cells, and expanded detail row.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Frontend JS — `renderPathToTitle` grid rendering

**Files:**
- Modify: `docs/playoffs.js` (add new functions + wire into `init()`)

- [ ] **Step 1: Add helper functions and `renderPathToTitle`**

Open `docs/playoffs.js`. Find the existing `renderPlayoffRecaps` function (around line 1078). Directly after its closing `}` (around line 1141), insert the new functions (at the same top-level indentation):

```javascript
// ── Path to Title ──────────────────────────────────────────────────────────

let _pttExpanded = null; // currently-expanded team code

function renderPathToTitle(pathData) {
    const section = document.getElementById('path-to-title-section');
    const tbody = document.getElementById('ptt-tbody');
    if (!section || !tbody || !pathData || !pathData.length) return;

    section.style.display = '';

    let html = '';
    for (const entry of pathData) {
        html += buildPathRow(entry);
        html += `<tr class="ptt-detail-row" id="ptt-detail-${entry.team}"><td colspan="7"></td></tr>`;
    }
    tbody.innerHTML = html;

    // Wire up click handlers
    tbody.querySelectorAll('.ptt-row').forEach(row => {
        row.addEventListener('click', () => {
            const teamCode = row.dataset.team;
            if (row.classList.contains('ptt-row-eliminated')) return;
            togglePathDetail(teamCode);
        });
    });
}

function buildPathRow(entry) {
    const teamName = (() => {
        const t = _seeded.find(s => s.team === entry.team);
        return t ? t.name : entry.team;
    })();
    const teamColor = TEAM_COLORS[entry.team] || '#555';

    const rowCls = [
        'ptt-row',
        entry.status === 'eliminated' ? 'ptt-row-eliminated' : '',
        entry.status === 'champion' ? 'ptt-row-champion' : '',
    ].filter(Boolean).join(' ');

    const byRound = {};
    for (const r of entry.rounds) byRound[r.round] = r;

    const cells = ['play_in', 'qf', 'sf', 'final'].map(rk => pathRoundCell(byRound[rk])).join('');

    const champPctCls = pathPctCls(entry.championship_odds);
    const hint = entry.status === 'alive' ? '<span class="ptt-expand-hint">click to expand ▾</span>' : '';

    return `<tr class="${rowCls}" data-team="${entry.team}">
        <td class="ptt-td-team">
            <div class="ptt-team-wrap">
                <div class="ptt-status-dot ${entry.status}"></div>
                <div class="ptt-team-color" style="background:${teamColor}"></div>
                <span class="ptt-team-name">${teamName}</span>
            </div>
        </td>
        ${cells}
        <td class="ptt-cell-champ ${champPctCls}">${entry.championship_odds.toFixed(1)}%</td>
        <td>${hint}</td>
    </tr>`;
}

function pathRoundCell(round) {
    if (!round || round.status === 'unreached') {
        return '<td class="ptt-cell-dash">—</td>';
    }
    if (round.status === 'completed') {
        const cls = round.actual_result === 'won' ? 'ptt-cell-won' : 'ptt-cell-lost';
        const label = round.actual_result === 'won' ? 'WON' : 'LOST';
        const seriesStr = round.series ? `${round.series[0]}-${round.series[1]}` : '';
        return `<td class="${cls}">${label} ${seriesStr} <span style="font-weight:400;color:var(--text-muted);font-size:0.72rem">vs ${round.actual_opponent}</span></td>`;
    }
    if (round.status === 'in_progress') {
        const s = round.series ? `${round.series[0]}-${round.series[1]}` : '';
        return `<td class="ptt-cell-progress">${s} vs ${round.actual_opponent}</td>`;
    }
    // upcoming
    const pct = round.reach_prob;
    const cls = pathPctCls(pct);
    return `<td class="ptt-cell-pct ${cls}">${pct.toFixed(0)}%</td>`;
}

function pathPctCls(pct) {
    if (pct >= 50) return 'ptt-cell-pct-high';
    if (pct >= 20) return 'ptt-cell-pct-mid';
    return 'ptt-cell-pct-low';
}

function togglePathDetail(teamCode) {
    const tbody = document.getElementById('ptt-tbody');
    if (!tbody) return;

    // Close currently expanded
    if (_pttExpanded) {
        const prevRow = tbody.querySelector(`.ptt-row[data-team="${_pttExpanded}"]`);
        const prevDetail = document.getElementById(`ptt-detail-${_pttExpanded}`);
        if (prevRow) prevRow.classList.remove('ptt-row-expanded');
        if (prevDetail) prevDetail.querySelector('td').innerHTML = '';
    }

    // Toggle same row = close
    if (_pttExpanded === teamCode) {
        _pttExpanded = null;
        return;
    }

    // Open new row — placeholder content; Task 5 will render the SVG tree
    const row = tbody.querySelector(`.ptt-row[data-team="${teamCode}"]`);
    const detail = document.getElementById(`ptt-detail-${teamCode}`);
    if (!row || !detail) return;
    row.classList.add('ptt-row-expanded');
    detail.querySelector('td').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem">Tree rendering — implemented in Task 5.</div>';
    _pttExpanded = teamCode;
}
```

- [ ] **Step 2: Call `renderPathToTitle` from `init()`**

Find the line in `init()` (around line 182):

```javascript
        renderPlayoffRecaps(data.playoff_recaps || []);
```

Add a new line directly after it:

```javascript
        renderPlayoffRecaps(data.playoff_recaps || []);
        renderPathToTitle(data.path_to_title || []);
```

- [ ] **Step 3: Start local server and verify in browser**

Start the server in the background:

```bash
.venv/Scripts/python.exe -m http.server 8000 --directory docs
```

Using Playwright MCP tools:
1. Navigate to `http://localhost:8000/playoffs.html`
2. Take a full-page screenshot (`playoffs_ptt_grid.png`)
3. Evaluate in browser:
   ```javascript
   const section = document.getElementById('path-to-title-section');
   const rows = document.querySelectorAll('.ptt-row');
   return {
     sectionVisible: section && section.style.display !== 'none',
     rowCount: rows.length,
     firstTeam: rows[0] ? rows[0].dataset.team : null,
   };
   ```

Expected:
- `sectionVisible: true`
- `rowCount: 10`
- `firstTeam` is a valid team code (the #1 seed by championship odds)

4. Click an alive row — verify placeholder text appears.
5. Click again — verify placeholder disappears (collapse).

Kill the server.

- [ ] **Step 4: Commit**

```bash
git add docs/playoffs.js
git commit -m "feat: render Path to Title grid from dashboard data

Populates the new section with a per-team row showing status, round-by-round
outcomes or probabilities, and championship odds. Click-to-expand scaffolding
in place; the detail tree SVG arrives in the next task.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Frontend JS — Detail tree SVG

**Files:**
- Modify: `docs/playoffs.js` (replace placeholder in `togglePathDetail` with real SVG rendering)

- [ ] **Step 1: Add `renderPathDetailTree` function**

In `docs/playoffs.js`, find the `pathPctCls` function added in Task 4 and add the new function directly after it (and before `togglePathDetail`):

```javascript
function renderPathDetailTree(entry, container) {
    const byRound = {};
    for (const r of entry.rounds) byRound[r.round] = r;
    const rounds = ['qf', 'sf', 'final']; // Root, then these columns, then trophy
    if (entry.rounds.find(r => r.round === 'play_in' && r.status !== 'unreached')) {
        rounds.unshift('play_in');
    }

    const width = 900;
    const colCount = rounds.length + 2; // team + rounds + trophy
    const colW = width / colCount;
    const rowH = 60;
    const branchPad = 20;

    // Determine max branches per column to size vertically
    let maxBranches = 1;
    for (const rk of rounds) {
        const r = byRound[rk];
        if (!r) continue;
        if (r.status === 'upcoming' && r.branches) {
            maxBranches = Math.max(maxBranches, r.branches.length);
        }
    }
    const height = Math.max(180, maxBranches * rowH + 80);

    const teamColor = TEAM_COLORS[entry.team] || '#60a5fa';
    const centerY = height / 2;

    let svg = `<svg class="ptt-tree-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">`;

    // Root node (team)
    svg += nodeLabel(colW / 2, centerY, entry.team, teamColor, '', 'ROOT');

    // Draw each round column
    rounds.forEach((rk, idx) => {
        const r = byRound[rk];
        const cx = colW * (idx + 1) + colW / 2;
        const prevX = idx === 0 ? colW / 2 : colW * idx + colW / 2;

        if (!r || r.status === 'unreached') {
            svg += nodeLabel(cx, centerY, '—', '#334155', roundLabel(rk), '');
            svg += edge(prevX + 30, centerY, cx - 30, centerY, '#334155', 0.4);
            return;
        }

        if (r.status === 'completed' || r.status === 'in_progress') {
            const opp = r.actual_opponent;
            const color = r.actual_result === 'won' ? '#22c55e' : (r.actual_result === 'lost' ? '#f87171' : '#60a5fa');
            const topLabel = roundLabel(rk);
            const oppLabel = r.status === 'completed'
                ? `${r.actual_result === 'won' ? 'WON' : 'LOST'} ${r.series ? r.series.join('-') : ''} vs ${opp}`
                : `${r.series ? r.series.join('-') : ''} vs ${opp}`;
            svg += nodeLabel(cx, centerY, opp, color, topLabel, oppLabel);
            svg += edge(prevX + 30, centerY, cx - 30, centerY, color, 0.9);
            return;
        }

        // Upcoming — draw branches
        const branches = r.branches || [];
        const winProbLabel = `${roundLabel(rk)} (${r.reach_prob.toFixed(0)}% to reach · ${r.win_prob.toFixed(0)}% to win)`;
        if (branches.length === 0) {
            svg += nodeLabel(cx, centerY, 'TBD', '#64748b', winProbLabel, '');
            svg += edge(prevX + 30, centerY, cx - 30, centerY, '#64748b', 0.5);
            return;
        }
        const totalH = branches.length * rowH;
        const startY = centerY - totalH / 2 + rowH / 2;
        branches.forEach((b, bi) => {
            const by = startY + bi * rowH;
            const bColor = TEAM_COLORS[b.opponent] || '#60a5fa';
            svg += edge(prevX + 30, centerY, cx - 30, by, bColor, 0.75);
            svg += nodeLabel(cx, by, b.opponent, bColor,
                `${b.reach_prob_for_opp.toFixed(0)}% opp`,
                `${b.win_prob_vs.toFixed(0)}% win`);
        });
        // Round label above column
        svg += `<text x="${cx}" y="${20}" text-anchor="middle" fill="#94a3b8" font-size="11" font-weight="700" font-family="Outfit,sans-serif">${winProbLabel}</text>`;
    });

    // Trophy column
    const trophyX = colW * (rounds.length + 1) + colW / 2;
    svg += edge(colW * rounds.length + colW / 2 + 30, centerY, trophyX - 30, centerY, '#fbbf24', 0.9);
    svg += `<text x="${trophyX}" y="${centerY - 10}" text-anchor="middle" font-size="28">🏆</text>`;
    svg += `<text x="${trophyX}" y="${centerY + 18}" text-anchor="middle" fill="#fbbf24" font-size="13" font-weight="800" font-family="Outfit,sans-serif">${entry.championship_odds.toFixed(1)}%</text>`;

    svg += '</svg>';
    container.innerHTML = svg;
}

function nodeLabel(cx, cy, code, color, topLabel, bottomLabel) {
    const r = 22;
    let s = '';
    if (topLabel) {
        s += `<text x="${cx}" y="${cy - 30}" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="600" font-family="Inter,sans-serif">${topLabel}</text>`;
    }
    s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" opacity="0.18" stroke="${color}" stroke-width="1.5"/>`;
    s += `<text x="${cx}" y="${cy + 4}" text-anchor="middle" fill="${color}" font-size="11" font-weight="800" font-family="Outfit,sans-serif">${code}</text>`;
    if (bottomLabel) {
        s += `<text x="${cx}" y="${cy + 40}" text-anchor="middle" fill="#cbd5e1" font-size="10" font-family="Inter,sans-serif">${bottomLabel}</text>`;
    }
    return s;
}

function edge(x1, y1, x2, y2, color, opacity) {
    // Smooth curve between columns
    const midX = (x1 + x2) / 2;
    return `<path d="M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}" stroke="${color}" stroke-width="1.5" fill="none" opacity="${opacity}"/>`;
}

function roundLabel(rk) {
    return { 'play_in': 'Play-In', 'qf': 'QF', 'sf': 'SF', 'final': 'Final' }[rk] || rk;
}
```

- [ ] **Step 2: Replace placeholder in `togglePathDetail` with real render**

Find this block inside `togglePathDetail`:

```javascript
    row.classList.add('ptt-row-expanded');
    detail.querySelector('td').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem">Tree rendering — implemented in Task 5.</div>';
    _pttExpanded = teamCode;
```

Replace the middle line (`detail.querySelector(...).innerHTML = ...`) with:

```javascript
    row.classList.add('ptt-row-expanded');
    const entry = (_pathData || []).find(e => e.team === teamCode);
    if (entry) {
        renderPathDetailTree(entry, detail.querySelector('td'));
    }
    _pttExpanded = teamCode;
```

- [ ] **Step 3: Stash `pathData` on global so `togglePathDetail` can find the entry**

In `renderPathToTitle`, stash the data. Find:

```javascript
function renderPathToTitle(pathData) {
    const section = document.getElementById('path-to-title-section');
    const tbody = document.getElementById('ptt-tbody');
    if (!section || !tbody || !pathData || !pathData.length) return;
```

Add `_pathData = pathData;` right after the guard:

```javascript
function renderPathToTitle(pathData) {
    const section = document.getElementById('path-to-title-section');
    const tbody = document.getElementById('ptt-tbody');
    if (!section || !tbody || !pathData || !pathData.length) return;
    _pathData = pathData;
```

And add the declaration near the other path-to-title globals. Find:

```javascript
let _pttExpanded = null; // currently-expanded team code
```

Replace it with:

```javascript
let _pttExpanded = null; // currently-expanded team code
let _pathData = null;
```

- [ ] **Step 4: Browser verification**

Start the server:

```bash
.venv/Scripts/python.exe -m http.server 8000 --directory docs
```

Via Playwright MCP:
1. Navigate to `http://localhost:8000/playoffs.html`
2. Scroll to the Path to Title section
3. Click the first alive team row
4. Take a screenshot (`path_to_title_expanded.png`)
5. Evaluate:
   ```javascript
   const svg = document.querySelector('#path-to-title-section .ptt-tree-svg');
   const paths = svg ? svg.querySelectorAll('path') : [];
   const circles = svg ? svg.querySelectorAll('circle') : [];
   return { hasSvg: !!svg, pathCount: paths.length, circleCount: circles.length };
   ```

Expected: `hasSvg: true`, `pathCount >= 3`, `circleCount >= 4` (root + at least one per round).

6. Click the row again — verify SVG disappears.
7. Click a different alive row — verify the new tree renders and the previous one collapsed.

Kill the server.

- [ ] **Step 5: Commit**

```bash
git add docs/playoffs.js
git commit -m "feat: render Path to Title detail tree SVG on row expand

Inline SVG tree with root team node, branching opponent columns per round,
and a trophy node with championship odds. Completed rounds show the locked
actual opponent; upcoming rounds show top 2-3 branches sorted by opponent
reach probability.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Update about.html

**Files:**
- Modify: `docs/about.html` (extend Playoffs description — line ~276)

- [ ] **Step 1: Update Playoffs description**

Open `docs/about.html`. Find the `<li>` for Playoffs (around line 276). Replace the current content with:

```html
                <li><span class="metric-name">Playoffs</span> — Interactive playoff bracket with live result tracking. Completed games are locked into the bracket with actual scores and series status, while unplayed games remain interactive for "what if" simulation. Championship Odds Tracker: a Plotly line chart showing how each team's title probability evolves after every playoff game day, with eliminated teams grayed out. Post-game Recap Cards for every completed playoff game, showing scores, series status, pre-game win probability, upset badges (when the underdog wins), and championship odds deltas. Path to Title: a per-team grid showing each road to the championship (completed rounds with actual results, upcoming rounds with probabilities); click any alive team's row to expand a branching tree of possible future opponents. Probabilities use model-based matchup odds (adjusted ratings + Elo + ML win probability) with a 10,000-run Monte Carlo. Share your bracket via URL.</li>
```

- [ ] **Step 2: Commit**

```bash
git add docs/about.html
git commit -m "docs: mention Path to Title in about page Playoffs description

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: End-to-end verification

**Files:**
- No new changes; this task only runs checks.

- [ ] **Step 1: Clean export**

Run: `.venv/Scripts/python.exe export_dashboard_data.py`

Expected: exits with code 0, prints `Done! dashboard.json written to docs\data\current\dashboard.json`.

- [ ] **Step 2: Sanity script**

Run: `.venv/Scripts/python.exe check_path_to_title.py`

Expected: `OK — path_to_title has 10 teams, sum of championship odds = ~100.0`.

- [ ] **Step 3: Browser verification**

Start the server:

```bash
.venv/Scripts/python.exe -m http.server 8000 --directory docs
```

Via Playwright MCP:
1. Navigate to `http://localhost:8000/playoffs.html`
2. Check for console errors: only `favicon.ico 404` is acceptable.
3. Take a full-page screenshot (`playoffs_final.png`).
4. Scroll to the Path to Title section; verify 10 rows present.
5. Click the top-seeded alive team row; verify SVG tree appears.
6. Click a mid-seeded alive team row; verify previous collapsed and new tree appears.
7. Click the same row again; verify it collapses.
8. Verify eliminated rows (if any) cannot expand.
9. Resize browser to 480px width; verify section is still usable (horizontal scroll acceptable).

Kill the server.

- [ ] **Step 4: No commit needed**

This task produces no new changes. If the screenshots look good and the browser checks pass, move on.

---

## Final Commit & Push

After all tasks pass:

```bash
git status    # verify nothing uncommitted except screenshots
git log --oneline -7   # verify all commits are in place
git push      # push to origin
```

Done!
