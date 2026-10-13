"""
🏀 EUROLEAGUE ANALYTICS MASTER REFRESH PIPELINE
=================================================
One command to update everything after a new round.

Usage:
    python refresh_all.py                  # Full refresh (fetch + compute + visualize)
    python refresh_all.py --no-fetch       # Skip data fetch (just recompute + visualize)
    python refresh_all.py --viz-only       # Only regenerate visualizations
    python refresh_all.py --skip-wp-train  # Skip WP model training (use existing model)
    python refresh_all.py --commit         # Automatically stage and commit new round files
"""

import subprocess
import sys
import time
import os

from season_config import CURRENT_SEASON, season_label

# Colors for terminal output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

os.environ.setdefault('EUROLEAGUE_SEASON', str(CURRENT_SEASON))  # child scripts agree

PYTHON = os.path.join('.venv', 'Scripts', 'python.exe') if os.name == 'nt' else 'python3'


def run_step(name, script, args=None):
    """Run a script and print status."""
    print(f"\n{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}⏳ {name}...{RESET}")
    print(f"{CYAN}{'='*60}{RESET}")
    
    cmd = [PYTHON, script]
    if args:
        cmd.extend(args)
    
    start = time.time()
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - start
    
    if result.returncode == 0:
        print(f"{GREEN}✅ {name} completed in {elapsed:.1f}s{RESET}")
        return True
    else:
        print(f"{RED}❌ {name} FAILED (exit code {result.returncode}){RESET}")
        return False


def main():
    args = sys.argv[1:]
    skip_fetch = '--no-fetch' in args
    viz_only = '--viz-only' in args
    skip_wp_train = '--skip-wp-train' in args
    
    print(f"\n{BOLD}{YELLOW}{'='*60}{RESET}")
    print(f"{BOLD}{YELLOW}  🏀 EUROLEAGUE ANALYTICS - FULL REFRESH PIPELINE{RESET}")
    print(f"{BOLD}{YELLOW}{'='*60}{RESET}")
    print(f"Season: {season_label()}")
    
    start_time = time.time()
    results = []

    # ── PHASE 1: DATA FETCH ──
    if not skip_fetch and not viz_only:
        print(f"\n{BOLD}📡 PHASE 1: Fetching Latest Data{RESET}")
        results.append(('Fetch Schedule', run_step(
            'Fetching season schedule (dates + tip-off times)',
            'fetch_schedule.py',
            ['--force']
        )))
        results.append(('Fetch Standings', run_step('Fetching official standings per round', 'fetch_standings.py')))
        results.append(('Fetch Game Stats', run_step(
            'Fetching game stats from Euroleague API',
            'fetch_mvp_data_v2.py'
        )))
        results.append(('Fetch Play-By-Play', run_step(
            'Fetching play-by-play data from Euroleague API',
            'fetch_pbp.py',
            ['--force']
        )))
        results.append(('Fetch Shot Data', run_step(
            'Fetching spatial shot data coordinates',
            'fetch_shot_data.py',
            ['--force']
        )))
        results.append(('Fetch Lineups', run_step(
            'Fetching lineups and game metadata',
            'fetch_lineups.py'
        )))
        results.append(('Fetch Player Career Stats', run_step(
            'Fetching all-season player career stats from Euroleague API',
            'fetch_player_career_stats.py',
            ['--force']
        )))
        results.append(('Parse Game Data', run_step(
            'Parsing game results',
            'parse_mvp_data.py'
        )))
        results.append(('Clutch Stats', run_step(
            'Generating clutch stats from play-by-play',
            'generate_clutch_data.py'
        )))
    else:
        print(f"\n{YELLOW}⏭️  Skipping data fetch{RESET}")
    
    # ── COMPUTE CURRENT ROUND FOR HISTORY KEEPING ──
    # (placed after fetch+parse so standings reflect the latest data)
    try:
        import json
        with open('mvp_standings_derived.json', 'r') as f:
            standings = json.load(f)
        max_gp = max((t.get('GP', 0) for t in standings.values()), default=0)
        round_suffix = f"_R{max_gp}" if max_gp > 0 else ""
    except Exception as e:
        print(f"{YELLOW}⚠️  Could not determine current round for suffix: {e}{RESET}")
        round_suffix = ""
    
    os.environ['EUROLEAGUE_ROUND_SUFFIX'] = round_suffix
    if round_suffix:
        print(f"{CYAN}📌 Active Round Suffix for Outputs: {round_suffix}{RESET}")
    
    if not viz_only:
        print(f"\n{BOLD}🧮 PHASE 2: Running Compute Engines{RESET}")
        if skip_wp_train:
            print(f"{YELLOW}⏭️  Skipping WP model training (--skip-wp-train){RESET}")
        else:
            results.append(('WP Model Training', run_step(
                'Training ML Win Probability Model',
                'train_wp_model.py'
            )))
        results.append(('Adjusted Ratings', run_step(
            'Computing KenPom Adjusted Ratings + SOS',
            'calculate_adjusted_ratings.py'
        )))
        results.append(('MVP Scores', run_step(
            'Computing MVP Ladder Scores',
            'calculate_mvp_scores.py'
        )))
        results.append(('TPM Ratings', run_step(
            'Computing True Plus-Minus (TPM)',
            'calculate_tpm.py'
        )))
        results.append(('WIR Ratings', run_step(
            'Computing Weighted Impact Ratings (WIR)',
            'calculate_wir.py'
        )))
        results.append(('WPA Ratings', run_step(
            'Computing Win Probability Added (WPA)',
            'calculate_wpa.py'
        )))
        results.append(('Elo Ratings', run_step(
            'Computing Elo Ratings',
            'calculate_elo.py'
        )))
        results.append(('Monte Carlo Sim', run_step(
            'Running Monte Carlo Simulation (10K iterations)',
            'simulate_monte_carlo.py'
        )))
        results.append(('RAPM Ratings', run_step(
            'Computing Regularized Adjusted Plus-Minus (RAPM)',
            'calculate_rapm.py'
        )))
        results.append(('Lineup Net Ratings', run_step(
            'Computing Lineup Net Ratings (5-man + pairs)',
            'calculate_lineups.py'
        )))
        results.append(('GCI Ratings', run_step(
            'Computing Game Control Index (GCI)',
            'calculate_gci.py'
        )))
        results.append(('Biggest Comebacks', run_step(
            'Computing all-time biggest comebacks from play-by-play',
            'calculate_comebacks.py'
        )))
    else:
        print(f"\n{YELLOW}⏭️  Skipping compute engines{RESET}")
    
    # ── PHASE 3: VISUALIZATIONS ──
    print(f"\n{BOLD}🎨 PHASE 3: Generating Visualizations{RESET}")
    
    viz_scripts = [
        ('Remaining SOS Table', 'visualize_remaining_sos.py'),
        ('Playoff Matrix', 'visualize_playoff_matrix.py'),
        ('Wins Profile Matrix', 'visualize_wins_profile.py'),
        ('Seed Distribution', 'visualize_seed_distribution.py'),
        ('Clutch Matchups', 'visualize_clutch_matchups.py'),
        ('Schedule Grid', 'visualize_schedule_grid.py'),
        ('Power Trajectory', 'visualize_power_trajectory.py'),
        ('Round Preview Card', 'visualize_round_preview.py'),
        ('MVP Ladder', 'visualize_mvp_ladder.py'),
        ('TPM vs WIR Quadrants', 'visualize_tpm_wir.py'),
        ('WIR vs PIR', 'visualize_wir.py'),
        ('WPA Leaders', 'visualize_wpa.py'),
        ('RAPM Charts', 'visualize_rapm.py'),
        ('Oracle Forecast', 'mvp_oracle.py'),
        ('Oracle Accuracy Tracker', 'oracle_accuracy_tracker.py'),
        ('Dashboard Export', 'export_dashboard_data.py'),
    ]
    
    for name, script in viz_scripts:
        if os.path.exists(script):
            results.append((name, run_step(f'Generating {name}', script)))
        else:
            print(f"{YELLOW}⚠️  {script} not found, skipping{RESET}")
    
    # ── PHASE 4: ANIMATIONS (optional, slower) ──
    if '--with-animations' in args:
        print(f"\n{BOLD}🎬 PHASE 4: Generating Animations{RESET}")
        results.append(('Standings Race GIF', run_step(
            'Generating Standings Race Animation',
            'visualize_standings_race.py'
        )))
    else:
        print(f"\n{YELLOW}⏭️  Skipping animations (use --with-animations to include){RESET}")
    
    # ── PHASE 5: GIT AUTOMATION ──
    if '--commit' in args and round_suffix:
        print(f"\n{BOLD}📦 PHASE 5: Git Automation{RESET}")
        import glob
        files_to_add = glob.glob(f"*{round_suffix}.png") + glob.glob(f"*{round_suffix}.json")
        # Always include the dashboard export — it doesn't carry a round suffix
        files_to_add += glob.glob('docs/data/current/*.json')
        if files_to_add:
            round_num = round_suffix.replace('_R', '')
            print(f"{CYAN}Staging {len(files_to_add)} files for Round {round_num}...{RESET}")
            subprocess.run(['git', 'add'] + files_to_add)
            
            commit_msg = f"feat(analytics): update visualizations for Round {round_num}"
            print(f"{CYAN}Committing: '{commit_msg}'{RESET}")
            git_result = subprocess.run(['git', 'commit', '-m', commit_msg], capture_output=True, text=True)
            
            if git_result.returncode == 0:
                print(f"{GREEN}✅ Git commit successful{RESET}")
                results.append(('Git Commit', True))
            else:
                print(f"{YELLOW}⚠️  Git commit output:\n{git_result.stdout}{RESET}")
                results.append(('Git Commit', False))
        else:
            print(f"{YELLOW}⚠️  No files found with suffix {round_suffix} to commit.{RESET}")
    
    # ── SUMMARY ──
    total_time = time.time() - start_time
    
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}📊 REFRESH COMPLETE — {total_time:.1f}s total{RESET}")
    print(f"{'='*60}")
    
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    
    for name, ok in results:
        status = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
        print(f"  {status} {name}")
    
    print(f"\n  {GREEN}{passed} passed{RESET}, {RED}{failed} failed{RESET}")
    
    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
