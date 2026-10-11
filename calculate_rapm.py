"""
Regularized Adjusted Plus-Minus (RAPM) — Euroleague (current season)
=========================================================
Uses Ridge Regression on stint-level data to isolate individual player impact,
controlling for teammate and opponent quality.

Unlike raw plus-minus (TPM), RAPM disentangles a player's contribution from
the strength of their lineups — a bench player on a great team won't be
inflated, and a star on a bad team won't be punished.

Informed Prior (Box-Score RAPM):
  Standard RAPM regularizes every player toward zero. This implementation
  first runs a basic RAPM pass, then trains a model to predict RAPM from
  box-score stats (PTS, AST, STL, BLK, REB, TO, TS%, usage). The predictions
  become the regularization center for a second pass — so low-minute players
  are pulled toward their box-score expectation, not toward zero. This is
  the same idea behind ESPN's RPM and FiveThirtyEight's RAPTOR.

Outputs:
  - Overall RAPM (single number: net impact per 100 possessions)
  - O-RAPM (offensive contribution)
  - D-RAPM (defensive contribution, positive = good defender)
"""

import pandas as pd
import numpy as np
import json
import os
from scipy.sparse import lil_matrix, csr_matrix
from sklearn.linear_model import RidgeCV, Ridge
from season_config import CURRENT_SEASON
from lineup_utils import parse_lineup, extract_stints, FGA_TYPES, TO_TYPES, FTA_TYPES, OREB_TYPES

SEASON = CURRENT_SEASON
CACHE_DIR = "data_cache"
MIN_MINUTES = 200  # Minimum estimated minutes for inclusion in output

BOX_FEATURES = [
    'pts_per_min', 'ast_per_min', 'orb_per_min', 'drb_per_min',
    'stl_per_min', 'blk_per_min', 'tov_per_min',
    'fga_per_min', 'ts_pct',
]


# ═══════════════════════════════════════════════════════════
#  BOX-SCORE INFORMED PRIOR
# ═══════════════════════════════════════════════════════════

def load_box_score_features():
    """
    Load per-minute box-score rate stats from game data.
    Returns dict: player_name -> {feature_name: value, ...}
    """
    stats_file = f'mvp_all_game_stats_{SEASON}.json'
    if not os.path.exists(stats_file):
        print(f"  Warning: {stats_file} not found. Prior disabled.")
        return {}

    with open(stats_file, 'r') as f:
        games = json.load(f)

    accum = {}  # player_name -> accumulated raw totals

    for game in games:
        for team_key in ['local.players', 'road.players']:
            for p_entry in game.get(team_key, []):
                stats = p_entry.get('stats', {})
                info = p_entry.get('player', {})
                p_name = info.get('person', {}).get('name')

                if not p_name:
                    continue

                time_played = stats.get('timePlayed', 0.0)
                if not time_played or time_played == 0:
                    continue

                if p_name not in accum:
                    accum[p_name] = {
                        'mins': 0, 'pts': 0, 'ast': 0, 'orb': 0, 'drb': 0,
                        'stl': 0, 'blk': 0, 'tov': 0,
                        'fga': 0, 'fgm': 0, 'fta': 0, 'ftm': 0,
                    }

                d = accum[p_name]
                d['mins'] += float(time_played) / 60.0
                d['pts'] += stats.get('points', 0)
                d['ast'] += stats.get('assistances', 0)
                d['orb'] += stats.get('offensiveRebounds', 0)
                d['drb'] += stats.get('defensiveRebounds', 0)
                d['stl'] += stats.get('steals', 0)
                d['blk'] += stats.get('blocksFavour', 0)
                d['tov'] += stats.get('turnovers', 0)
                d['fga'] += stats.get('fieldGoalsAttemptedTotal', 0)
                d['fgm'] += stats.get('fieldGoalsMadeTotal', 0)
                d['fta'] += stats.get('freeThrowsAttempted', 0)
                d['ftm'] += stats.get('freeThrowsMade', 0)

    features = {}
    for name, d in accum.items():
        if d['mins'] < 50:
            continue

        mins = d['mins']
        tsa = d['fga'] + 0.44 * d['fta']

        features[name] = {
            'pts_per_min': d['pts'] / mins,
            'ast_per_min': d['ast'] / mins,
            'orb_per_min': d['orb'] / mins,
            'drb_per_min': d['drb'] / mins,
            'stl_per_min': d['stl'] / mins,
            'blk_per_min': d['blk'] / mins,
            'tov_per_min': d['tov'] / mins,
            'fga_per_min': d['fga'] / mins,
            'ts_pct': (d['pts'] / (2 * tsa)) if tsa > 0 else 0,
        }

    print(f"  Loaded box-score features for {len(features)} players")
    return features


def build_prior(player_list, basic_rapm, box_features, label="overall"):
    """
    Train a model: basic_RAPM ~ box_score_stats, then predict a prior for every player.
    Players with no box-score data get a prior of 0.

    The math:
      Standard ridge minimizes:  ||y - Xβ||² + α||β||²        → pulls toward 0
      Informed ridge minimizes:  ||y - Xβ||² + α||β - μ||²    → pulls toward μ
      Equivalent to: fit ridge on y' = y - Xμ, then β_final = μ + β'
    """
    # Build training set: players that appear in both RAPM and box-score
    X_train, y_train = [], []
    for i, player in enumerate(player_list):
        if player in box_features:
            feat = box_features[player]
            X_train.append([feat[f] for f in BOX_FEATURES])
            y_train.append(basic_rapm[i])

    if len(X_train) < 30:
        print(f"  Warning: Only {len(X_train)} players matched for {label} prior. Skipping.")
        return np.zeros(len(player_list))

    X_train = np.array(X_train)
    y_train = np.array(y_train)

    # Fit box-score → RAPM predictor (moderate regularization to avoid overfitting)
    prior_model = Ridge(alpha=10, fit_intercept=True)
    prior_model.fit(X_train, y_train)
    r2 = prior_model.score(X_train, y_train)
    print(f"  {label.upper()} prior model R² = {r2:.3f} (trained on {len(X_train)} players)")

    # Generate priors for all players in the design matrix
    priors = np.zeros(len(player_list))
    for i, player in enumerate(player_list):
        if player in box_features:
            feat = box_features[player]
            x = np.array([[feat[f] for f in BOX_FEATURES]])
            priors[i] = prior_model.predict(x)[0]
        # else: stays 0 (no box-score data → regularize toward average)

    return priors


def run_informed_ridge(X_sparse, y, weights, priors_player, alphas, n_players, label="overall"):
    """
    Run ridge regression with an informed prior.
    Shifts the target by the prior contribution, fits, then adds prior back.
    """
    # Build prior vector for full design matrix (players + HCA)
    n_extra = X_sparse.shape[1] - n_players
    prior_vec = np.concatenate([priors_player, np.zeros(n_extra)])

    # Shift target: y_adj = y - X @ prior
    y_adj = y - X_sparse.dot(prior_vec)

    ridge = RidgeCV(alphas=alphas, cv=5, fit_intercept=True)
    ridge.fit(X_sparse, y_adj, sample_weight=weights)
    print(f"  {label} informed ridge — best alpha: {ridge.alpha_}")

    # Final coefficients = prior + adjustment
    coefs = prior_vec + ridge.coef_
    intercept = ridge.intercept_

    return coefs, intercept


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def calculate_rapm():
    print("=" * 60)
    print("  REGULARIZED ADJUSTED PLUS-MINUS (RAPM)")
    print(f"  Euroleague {SEASON} — Box-Score Informed Prior")
    print("=" * 60)

    # ── 1. Load lineup data ──
    cache_file = os.path.join(CACHE_DIR, f"pbp_lineups_{SEASON}.csv")
    if not os.path.exists(cache_file):
        print(f"{cache_file} not found (no games played yet?) - skipping RAPM.")
        return

    print(f"Loading {cache_file}...")
    df = pd.read_csv(cache_file, low_memory=False)
    print(f"  {len(df):,} rows, {df['Gamecode'].nunique()} games")

    # Team whitelist = teams in the current standings
    with open('mvp_standings_derived.json', encoding='utf-8') as f:
        EL_TEAMS = set(json.load(f).keys())

    # Load home/away mapping
    games_file = os.path.join(CACHE_DIR, f"games_{SEASON}.csv")
    home_map = {}
    if os.path.exists(games_file):
        gdf = pd.read_csv(games_file)
        home_map = dict(zip(gdf['gamenumber'], gdf['homecode']))

    # ── 2. Extract stints ──
    print("Extracting stints...")
    all_stints = []
    skipped = 0

    for gc, game_df in df.groupby('Gamecode'):
        lineup_cols = [c for c in game_df.columns
                       if c.startswith('Lineup_') and game_df[c].notna().any()]
        if len(lineup_cols) != 2:
            skipped += 1
            continue

        ta = lineup_cols[0].replace('Lineup_', '')
        tb = lineup_cols[1].replace('Lineup_', '')
        if ta not in EL_TEAMS or tb not in EL_TEAMS:
            skipped += 1
            continue

        # Score sanity check
        pa = pd.to_numeric(game_df['POINTS_A'], errors='coerce').max()
        pb = pd.to_numeric(game_df['POINTS_B'], errors='coerce').max()
        if pd.isna(pa) or pd.isna(pb) or pa > 250 or pb > 250 or pa < 10 or pb < 10:
            skipped += 1
            continue

        home_code = home_map.get(gc)
        stints = extract_stints(game_df, lineup_cols[0], lineup_cols[1])
        for s in stints:
            s['home_team'] = home_code
        all_stints.extend(stints)

        if gc % 50 == 0:
            print(f"  Game {gc}: {len(all_stints):,} stints extracted")

    print(f"  Total stints: {len(all_stints):,} ({skipped} games skipped)")

    if len(all_stints) < 100:
        print("Error: Not enough stints for RAPM. Check lineup data.")
        return

    # ── 3. Build player index ──
    all_players = set()
    player_teams = {}
    for s in all_stints:
        for p in s['lineup_a']:
            all_players.add(p)
            player_teams[p] = s['team_a']
        for p in s['lineup_b']:
            all_players.add(p)
            player_teams[p] = s['team_b']

    player_list = sorted(all_players)
    p2i = {p: i for i, p in enumerate(player_list)}
    n_players = len(player_list)
    n_stints = len(all_stints)
    print(f"  Unique players: {n_players}")

    # ── 4a. Overall RAPM design matrix ──
    print("Building overall RAPM matrix...")
    n_cols = n_players + 1  # +1 for HCA
    X = lil_matrix((n_stints, n_cols))
    y = np.zeros(n_stints)
    w = np.zeros(n_stints)
    player_poss = np.zeros(n_players)

    for i, s in enumerate(all_stints):
        poss = s['poss']
        margin_per100 = ((s['pts_a'] - s['pts_b']) / poss) * 100

        y[i] = margin_per100
        w[i] = poss

        for p in s['lineup_a']:
            idx = p2i[p]
            X[i, idx] = 1
            player_poss[idx] += poss
        for p in s['lineup_b']:
            idx = p2i[p]
            X[i, idx] = -1
            player_poss[idx] += poss

        home = s.get('home_team')
        if home == s['team_a']:
            X[i, n_players] = 1
        elif home == s['team_b']:
            X[i, n_players] = -1

    X_overall = csr_matrix(X)

    # ── 4b. O/D split design matrix ──
    print("Building O/D split RAPM matrix...")
    n_rows_od = n_stints * 2
    n_cols_od = n_players * 2 + 1
    X_od = lil_matrix((n_rows_od, n_cols_od))
    y_od = np.zeros(n_rows_od)
    w_od = np.zeros(n_rows_od)

    for i, s in enumerate(all_stints):
        poss = s['poss']
        pts_a_per100 = (s['pts_a'] / poss) * 100
        pts_b_per100 = (s['pts_b'] / poss) * 100
        home = s.get('home_team')

        r1 = i * 2
        y_od[r1] = pts_a_per100
        w_od[r1] = poss
        for p in s['lineup_a']:
            X_od[r1, p2i[p]] = 1
        for p in s['lineup_b']:
            X_od[r1, n_players + p2i[p]] = 1
        if home == s['team_a']:
            X_od[r1, n_cols_od - 1] = 1
        elif home == s['team_b']:
            X_od[r1, n_cols_od - 1] = -1

        r2 = i * 2 + 1
        y_od[r2] = pts_b_per100
        w_od[r2] = poss
        for p in s['lineup_b']:
            X_od[r2, p2i[p]] = 1
        for p in s['lineup_a']:
            X_od[r2, n_players + p2i[p]] = 1
        if home == s['team_b']:
            X_od[r2, n_cols_od - 1] = 1
        elif home == s['team_a']:
            X_od[r2, n_cols_od - 1] = -1

    X_od = csr_matrix(X_od)

    # ── 5. PASS 1: Low-regularization RAPM for prior training ──
    # Use a LOW alpha here on purpose — we want higher-variance estimates
    # so the box-score model has real signal to learn from. These noisy
    # estimates are NOT the final output; they only train the prior model.
    alphas_final = [0.01, 0.1, 1, 10, 50, 100, 500, 1000, 5000]
    ALPHA_PASS1 = 100  # Low regularization → more variance → better prior training

    print(f"\n--- PASS 1: Low-regularization RAPM (alpha={ALPHA_PASS1}) for prior training ---")
    ridge_p1 = Ridge(alpha=ALPHA_PASS1, fit_intercept=True)
    ridge_p1.fit(X_overall, y, sample_weight=w)
    p1_rapm = ridge_p1.coef_[:n_players]
    p1_std = np.std(p1_rapm)
    print(f"  Pass 1 RAPM std: {p1_std:.3f} (higher = more signal for prior)")

    ridge_od_p1 = Ridge(alpha=ALPHA_PASS1, fit_intercept=True)
    ridge_od_p1.fit(X_od, y_od, sample_weight=w_od)
    p1_orapm = ridge_od_p1.coef_[:n_players]
    p1_drapm = -ridge_od_p1.coef_[n_players:n_players * 2]

    # Also run CV-tuned basic RAPM as a reference point
    ridge_basic = RidgeCV(alphas=alphas_final, cv=5, fit_intercept=True)
    ridge_basic.fit(X_overall, y, sample_weight=w)
    basic_rapm = ridge_basic.coef_[:n_players]
    print(f"  Basic RAPM (CV) best alpha: {ridge_basic.alpha_}, std: {np.std(basic_rapm):.3f}")

    # ── 6. Build box-score informed priors ──
    # Train prior model on the HIGH-VARIANCE pass 1 estimates, not the
    # heavily-shrunk basic RAPM. This gives the model actual signal to learn from.
    print("\n--- Building Box-Score Priors ---")
    box_features = load_box_score_features()

    if box_features:
        prior_overall = build_prior(player_list, p1_rapm, box_features, "overall")
        prior_orapm = build_prior(player_list, p1_orapm, box_features, "offensive")
        prior_drapm = build_prior(player_list, p1_drapm, box_features, "defensive")

        # ── 7. PASS 2: Informed RAPM (regularize toward box-score prediction) ──
        # Now use full cross-validated alpha — heavy regularization is fine because
        # it pulls toward the informed prior, not toward zero.
        print("\n--- PASS 2: Informed RAPM (prior = box-score prediction) ---")

        coefs_overall, _ = run_informed_ridge(
            X_overall, y, w, prior_overall, alphas_final, n_players, "Overall")
        rapm_vals = coefs_overall[:n_players]
        hca_coef = coefs_overall[n_players]

        # For O/D: D-prior needs negating back to raw "points allowed" scale
        prior_od = np.concatenate([prior_orapm, -prior_drapm])
        coefs_od, _ = run_informed_ridge(
            X_od, y_od, w_od, prior_od, alphas_final, n_players * 2, "O/D")
        orapm_vals = coefs_od[:n_players]
        drapm_vals = -coefs_od[n_players:n_players * 2]
    else:
        print("  No box-score data available. Using basic RAPM.")
        rapm_vals = basic_rapm
        orapm_vals = ridge_od_p1.coef_[:n_players]
        drapm_vals = -ridge_od_p1.coef_[n_players:n_players * 2]
        hca_coef = ridge_basic.coef_[n_players]

    print(f"\n  HCA coefficient: {hca_coef:.2f} pts/100poss")

    # ── 8. Build results ──
    POSS_PER_MIN = 1.75

    rows = []
    for i, player in enumerate(player_list):
        est_min = player_poss[i] / POSS_PER_MIN
        rows.append({
            'player': player,
            'team': player_teams.get(player, 'UNK'),
            'RAPM': round(float(rapm_vals[i]), 2),
            'ORAPM': round(float(orapm_vals[i]), 2),
            'DRAPM': round(float(drapm_vals[i]), 2),
            'RAPM_basic': round(float(basic_rapm[i]), 2),
            'prior': round(float(prior_overall[i]), 2) if box_features else 0,
            'est_minutes': round(est_min, 0),
            'possessions': round(float(player_poss[i]), 0),
        })

    df_out = pd.DataFrame(rows)
    df_out = df_out[df_out['est_minutes'] >= MIN_MINUTES].copy()
    df_out = df_out.sort_values('RAPM', ascending=False).reset_index(drop=True)
    df_out['RAPM_Rank'] = df_out.index + 1

    # ── 9. Print ──
    print(f"\n{'=' * 80}")
    print(f"  INFORMED RAPM LEADERS — Euroleague {SEASON} (min {MIN_MINUTES} est. min)")
    print(f"{'=' * 80}")
    print(f"  {'Rk':<4} {'Player':<28} {'Team':<5} {'RAPM':>7} {'O-RAPM':>7} {'D-RAPM':>7} {'Prior':>7} {'Basic':>7}")
    print(f"  {'-' * 78}")

    for _, r in df_out.head(25).iterrows():
        print(f"  {r['RAPM_Rank']:<4} {r['player']:<28} {r['team']:<5} "
              f"{r['RAPM']:>+7.2f} {r['ORAPM']:>+7.2f} {r['DRAPM']:>+7.2f} "
              f"{r['prior']:>+7.2f} {r['RAPM_basic']:>+7.2f}")

    print(f"\n  --- BIGGEST PRIOR BOOSTS (box score says they're better than basic RAPM) ---")
    df_out['prior_boost'] = df_out['RAPM'] - df_out['RAPM_basic']
    boosted = df_out.nlargest(5, 'prior_boost')
    for _, r in boosted.iterrows():
        print(f"  {r['player']:<28} ({r['team']}) Basic: {r['RAPM_basic']:+.2f} -> Informed: {r['RAPM']:+.2f} (boost: {r['prior_boost']:+.2f})")

    print(f"\n  --- BIGGEST PRIOR DROPS (box score says they're worse than basic RAPM) ---")
    dropped = df_out.nsmallest(5, 'prior_boost')
    for _, r in dropped.iterrows():
        print(f"  {r['player']:<28} ({r['team']}) Basic: {r['RAPM_basic']:+.2f} -> Informed: {r['RAPM']:+.2f} (drop: {r['prior_boost']:+.2f})")

    # ── 10. Save ──
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'rapm_ratings{round_suffix}.json'
    save_cols = ['player', 'team', 'RAPM', 'ORAPM', 'DRAPM', 'RAPM_basic', 'prior',
                 'est_minutes', 'possessions', 'RAPM_Rank']
    df_out[save_cols].to_json(outfile, orient='records', indent=4)
    print(f"\n  Saved {len(df_out)} player ratings to {outfile}")

    return df_out


if __name__ == '__main__':
    calculate_rapm()
