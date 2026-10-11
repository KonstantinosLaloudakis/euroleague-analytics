"""
Train an ML-based Win Probability model for Euroleague basketball.

Uses every completed season's play-by-play data to learn how margin,
time remaining, team strength, momentum, and game context affect the
probability that Team A (home) wins.

Features:
  - margin              : POINTS_A - POINTS_B
  - seconds_remaining   : time left in regulation
  - time_frac           : seconds_remaining / 2400
  - elo_diff            : rolling Elo(home) - Elo(away) at game start
  - is_home             : 1.0 (always, since POINTS_A = home)
  - margin_time         : margin * time_frac (interaction)
  - scoring_run         : net points in last ~10 scoring events for Team A
  - lead_changes        : cumulative lead changes so far
  - is_overtime         : 1.0 if in overtime

Label: did Team A (home) win the game? (binary)

Output: data_cache/wp_model.pkl (calibrated GradientBoostingClassifier)
"""

import pandas as pd
import numpy as np
import glob
import os
import time
import json
from collections import defaultdict

from wp_model_utils import CalibratedModel


def parse_seconds_remaining(marker_str, period):
    """Convert MARKERTIME + period to total seconds remaining in regulation."""
    if pd.isna(marker_str) or pd.isna(period):
        return np.nan
    try:
        parts = str(marker_str).split(':')
        minutes = int(parts[0])
        seconds = int(parts[1])
        period_secs = minutes * 60 + seconds
        period = int(period)
        if period <= 4:
            return (4 - period) * 600 + period_secs
        else:
            # Overtime periods — cap at a small positive value
            return period_secs
    except (ValueError, IndexError):
        return np.nan


def compute_rolling_elo(game_results, carryover=0.75):
    """
    Compute rolling Elo ratings from a list of (season, gamecode, home, away, home_won) tuples.

    At each season boundary, applies regression-to-mean:
        elo[team] = 1500 + carryover * (elo[team] - 1500)
    This prevents early-season Elo from being stale and reflects real-world
    roster turnover / team changes between seasons.

    Returns:
        game_elos: dict (season, gamecode) -> {'home_elo', 'away_elo', 'elo_diff'}
        season_snapshots: dict season -> {team: elo} end-of-season ratings
    """
    K_FACTOR = 10
    STARTING_ELO = 1500

    elo = defaultdict(lambda: STARTING_ELO)
    game_elos = {}
    season_snapshots = {}
    current_season = None

    for season, gamecode, home, away, home_won in game_results:
        # Detect season boundary — apply regression to mean before first game of new season
        if current_season is not None and season != current_season:
            # Save end-of-season snapshot
            season_snapshots[current_season] = {team: round(r, 2) for team, r in elo.items()}
            # Regress all known teams to mean
            for team in list(elo.keys()):
                elo[team] = STARTING_ELO + carryover * (elo[team] - STARTING_ELO)

        current_season = season

        # Snapshot Elo BEFORE the game (this is what we use as a feature)
        home_elo = elo[home]
        away_elo = elo[away]
        game_elos[(season, gamecode)] = {
            'home_elo': home_elo,
            'away_elo': away_elo,
            'elo_diff': home_elo - away_elo,
        }

        # Update Elo after game
        expected = 1.0 / (1.0 + 10 ** ((away_elo - home_elo) / 400))
        actual = 1.0 if home_won else 0.0
        elo[home] += K_FACTOR * (actual - expected)
        elo[away] += K_FACTOR * ((1.0 - actual) - (1.0 - expected))

    # Save final season snapshot
    if current_season is not None:
        season_snapshots[current_season] = {team: round(r, 2) for team, r in elo.items()}

    return game_elos, season_snapshots


def detect_team_a(game_df, teams):
    """Auto-detect which team maps to POINTS_A (home team)."""
    scoring = game_df[game_df['POINTS_A'].notna() & game_df['CODETEAM'].isin(teams)]
    prev_a, prev_b = 0, 0
    for _, row in scoring.iterrows():
        try:
            a, b = int(float(row['POINTS_A'])), int(float(row['POINTS_B']))
        except (ValueError, TypeError):
            continue
        team = row['CODETEAM']
        if a > prev_a and b == prev_b:
            return team
        elif b > prev_b and a == prev_a:
            return [t for t in teams if t != team][0]
        prev_a, prev_b = a, b
    return teams[0]


def save_game_elos(game_elos, game_results, season_snapshots=None):
    """
    Persist per-game pre-game Elo snapshots to data_cache/game_elos.json.
    Format: {"SEASON_GC": {"elo_diff": float, "home": str, "away": str}}

    Optionally saves season_snapshots to data_cache/elo_season_snapshots.json.
    Format: {2024: {"MAD": 1523.5, "CSK": 1488.0, ...}, ...}
    """
    os.makedirs('data_cache', exist_ok=True)

    # Build a (season, gc) -> (home, away) map from game_results
    team_map = {(s, gc): (home, away) for s, gc, home, away, _ in game_results}

    output = {}
    for (season, gc), info in game_elos.items():
        key = f"{season}_{gc}"
        home, away = team_map.get((season, gc), ('', ''))
        output[key] = {
            'elo_diff': round(info['elo_diff'], 2),
            'home': home,
            'away': away,
        }

    path = os.path.join('data_cache', 'game_elos.json')
    with open(path, 'w') as f:
        json.dump(output, f)
    print(f"Saved per-game Elo snapshots to {path} ({len(output)} games)")

    if season_snapshots:
        snap_path = os.path.join('data_cache', 'elo_season_snapshots.json')
        # JSON keys must be strings
        str_keyed = {str(s): ratings for s, ratings in season_snapshots.items()}
        with open(snap_path, 'w') as f:
            json.dump(str_keyed, f, indent=2)
        print(f"Saved season Elo snapshots to {snap_path} ({len(season_snapshots)} seasons)")


def build_dataset():
    """
    Build the training dataset from all PBP CSVs.
    Returns (features_df, labels) ready for sklearn.
    """
    pbp_files = sorted(glob.glob('data/pbp_*.csv'))
    if not pbp_files:
        raise FileNotFoundError("No PBP files found in data/pbp_*.csv")

    print(f"Found {len(pbp_files)} PBP files")

    # ── PASS 1: Extract game results for Elo computation ─────
    print("Pass 1: Extracting game results for Elo ratings...")
    game_results = []  # (season, gamecode, home_team, away_team, home_won)

    for fpath in pbp_files:
        season = int(os.path.basename(fpath).replace('pbp_', '').replace('.csv', ''))
        df = pd.read_csv(fpath, low_memory=False)
        df = df.sort_values(['Gamecode', 'NUMBEROFPLAY']).reset_index(drop=True)

        for gc, gdf in df.groupby('Gamecode'):
            teams = [t for t in gdf['CODETEAM'].dropna().unique() if t and str(t).strip()]
            if len(teams) < 2:
                continue

            # Forward fill scores
            gdf = gdf.copy()
            gdf['POINTS_A'] = gdf['POINTS_A'].ffill().fillna(0)
            gdf['POINTS_B'] = gdf['POINTS_B'].ffill().fillna(0)

            final_a = gdf['POINTS_A'].iloc[-1]
            final_b = gdf['POINTS_B'].iloc[-1]
            if final_a == 0 and final_b == 0:
                continue

            # Detect which team is POINTS_A (home)
            home_team = detect_team_a(gdf, teams)
            away_team = [t for t in teams if t != home_team][0]
            home_won = final_a > final_b

            game_results.append((season, gc, home_team, away_team, home_won))

    print(f"  Extracted {len(game_results)} game results across {len(pbp_files)} seasons")

    # Compute rolling Elo with regression-to-mean at season boundaries
    game_elos, season_snapshots = compute_rolling_elo(game_results)

    # Save per-game Elo snapshots + season snapshots for use by inference modules
    save_game_elos(game_elos, game_results, season_snapshots)

    # ── PASS 2: Build play-by-play features ──────────────────
    print("Pass 2: Building play-by-play features...")
    all_rows = []

    for fpath in pbp_files:
        season = int(os.path.basename(fpath).replace('pbp_', '').replace('.csv', ''))
        df = pd.read_csv(fpath, low_memory=False)
        df = df.sort_values(['Gamecode', 'NUMBEROFPLAY']).reset_index(drop=True)

        game_count = 0
        for gc, gdf in df.groupby('Gamecode'):
            gdf = gdf.copy()
            gdf['POINTS_A'] = gdf['POINTS_A'].ffill().fillna(0)
            gdf['POINTS_B'] = gdf['POINTS_B'].ffill().fillna(0)

            final_a = gdf['POINTS_A'].iloc[-1]
            final_b = gdf['POINTS_B'].iloc[-1]
            if final_a == 0 and final_b == 0:
                continue

            label = 1.0 if final_a > final_b else 0.0  # Did Team A (home) win?

            # Get pre-game Elo
            elo_info = game_elos.get((season, gc), {'elo_diff': 0.0})
            elo_diff = elo_info['elo_diff']

            # Extract scoring events only (where score changes)
            prev_a, prev_b = 0, 0
            scoring_events = []
            lead_changes = 0
            prev_leader = 0  # 0=tied, 1=A leads, -1=B leads

            for _, row in gdf.iterrows():
                pa, pb = row['POINTS_A'], row['POINTS_B']
                if pd.isna(pa) or pd.isna(pb):
                    continue
                pa, pb = int(pa), int(pb)
                if pa == prev_a and pb == prev_b:
                    continue

                secs = parse_seconds_remaining(row.get('MARKERTIME'), row.get('PERIOD'))
                if pd.isna(secs):
                    prev_a, prev_b = pa, pb
                    continue

                margin = pa - pb

                # Track lead changes
                curr_leader = 1 if margin > 0 else (-1 if margin < 0 else 0)
                if prev_leader != 0 and curr_leader != 0 and curr_leader != prev_leader:
                    lead_changes += 1
                prev_leader = curr_leader

                # Track scoring run (net points for Team A in last 10 events)
                scoring_events.append(pa - pb)
                if len(scoring_events) > 1:
                    recent = scoring_events[-min(10, len(scoring_events)):]
                    scoring_run = recent[-1] - recent[0]
                else:
                    scoring_run = 0.0

                period = int(row['PERIOD']) if pd.notna(row['PERIOD']) else 1
                time_frac = secs / 2400.0 if secs > 0 else 0.0
                is_overtime = 1.0 if period > 4 else 0.0
                # Key nonlinear feature: margin / sqrt(time_frac) captures the
                # analytic formula's z-score (standard deviations of lead).
                # Directly encodes how "safe" a lead is given time remaining.
                sqrt_tf = time_frac ** 0.5 if time_frac > 0 else 0.01
                normalized_lead = float(margin) / sqrt_tf

                all_rows.append({
                    'margin': float(margin),
                    'seconds_remaining': float(secs),
                    'time_frac': time_frac,
                    'elo_diff': elo_diff,
                    'is_home': 1.0,  # POINTS_A is always home
                    'margin_time': margin * time_frac,
                    'normalized_lead': normalized_lead,
                    'scoring_run': float(scoring_run),
                    'lead_changes': float(lead_changes),
                    'is_overtime': is_overtime,
                    'label': label,
                    'season': season,
                })

                prev_a, prev_b = pa, pb

            game_count += 1

        print(f"  {season}: {game_count} games")

    features_df = pd.DataFrame(all_rows)
    print(f"\nTotal training rows: {len(features_df):,}")
    print(f"Label distribution: {features_df['label'].value_counts().to_dict()}")

    return features_df


def train_model(features_df):
    """Train and calibrate the WP model."""
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import brier_score_loss, log_loss
    import joblib

    FEATURE_COLS = [
        'margin', 'seconds_remaining', 'time_frac', 'elo_diff',
        'is_home', 'margin_time', 'normalized_lead',
        'scoring_run', 'lead_changes', 'is_overtime',
    ]

    # Time-based split: train on 2007-2022, validate on 2023, test on 2024-2025
    train_mask = features_df['season'] <= 2022
    val_mask = features_df['season'] == 2023
    test_mask = features_df['season'] >= 2024

    X_train = features_df.loc[train_mask, FEATURE_COLS].values
    y_train = features_df.loc[train_mask, 'label'].values
    X_val = features_df.loc[val_mask, FEATURE_COLS].values
    y_val = features_df.loc[val_mask, 'label'].values
    X_test = features_df.loc[test_mask, FEATURE_COLS].values
    y_test = features_df.loc[test_mask, 'label'].values

    print(f"\nSplit sizes — Train: {len(X_train):,}  Val: {len(X_val):,}  Test: {len(X_test):,}")

    GBM_PARAMS = dict(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=100,
        random_state=42,
    )

    # ── OOF Calibration (expanding window, 3 folds) ─────────────
    # Train fold models on progressively larger windows, collect out-of-fold
    # predictions (~170K rows) so isotonic regression has enough data to
    # learn the true calibration shape without overfitting.
    print("\nBuilding OOF predictions for calibration (3 expanding folds)...")
    train_seasons = features_df.loc[train_mask, 'season']
    oof_folds = [
        (2016, 2019),   # train 2007-2015, OOF on 2016-2018
        (2019, 2022),   # train 2007-2018, OOF on 2019-2021
        (2022, 2023),   # train 2007-2021, OOF on 2022
    ]
    oof_probs = np.zeros(len(X_train))
    oof_labels = y_train.copy()
    t_oof = time.time()

    for fold_idx, (oof_start, oof_end) in enumerate(oof_folds):
        fold_train_mask = train_seasons < oof_start
        fold_val_mask = (train_seasons >= oof_start) & (train_seasons < oof_end)
        X_ftrain = features_df.loc[train_mask].loc[fold_train_mask.values, FEATURE_COLS].values
        y_ftrain = features_df.loc[train_mask].loc[fold_train_mask.values, 'label'].values
        X_fval   = features_df.loc[train_mask].loc[fold_val_mask.values, FEATURE_COLS].values
        n_fval   = fold_val_mask.sum()

        print(f"  Fold {fold_idx+1}: train {oof_start-len(X_ftrain)//28000+2007:.0f}–{oof_start-1}  "
              f"OOF {oof_start}–{oof_end-1}  ({n_fval:,} rows)...")
        gb_fold = GradientBoostingClassifier(**GBM_PARAMS)
        gb_fold.fit(X_ftrain, y_ftrain)
        oof_probs[fold_val_mask.values] = gb_fold.predict_proba(X_fval)[:, 1]

    print(f"  OOF generation took {time.time() - t_oof:.1f}s")
    oof_probs = np.clip(oof_probs[oof_probs > 0], 1e-7, 1 - 1e-7)   # drop un-filled rows
    oof_labels_used = oof_labels[np.flatnonzero(
        (train_seasons >= oof_folds[0][0]).values
    )]

    iso_oof = IsotonicRegression(y_min=0.001, y_max=0.999, out_of_bounds='clip')
    iso_oof.fit(oof_probs, oof_labels_used)
    print(f"  Isotonic calibration fit on {len(oof_probs):,} OOF samples")

    # ── Final model trained on full training set ─────────────────
    print("\nTraining final GradientBoostingClassifier on full training set...")
    t0 = time.time()
    gb = GradientBoostingClassifier(**GBM_PARAMS)
    gb.fit(X_train, y_train)
    print(f"  Training took {time.time() - t0:.1f}s")

    calibrated = CalibratedModel(gb, iso_oof)

    # Evaluate on test set
    print("\n" + "=" * 55)
    print("  MODEL EVALUATION (Test Set: 2024-2025)")
    print("=" * 55)

    y_pred_ml = calibrated.predict_proba(X_test)[:, 1]

    # Compare with analytic baseline
    test_df = features_df.loc[test_mask].copy()
    import math

    def analytic_wp(margin, secs):
        if secs <= 0:
            return 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
        sigma = 11.0 * math.sqrt(secs / 2400.0)
        if sigma < 0.1:
            sigma = 0.1
        z = margin / sigma
        return 1.0 / (1.0 + math.exp(-0.8 * z))

    y_pred_analytic = test_df.apply(
        lambda r: analytic_wp(r['margin'], r['seconds_remaining']), axis=1
    ).values

    ml_brier = brier_score_loss(y_test, y_pred_ml)
    analytic_brier = brier_score_loss(y_test, y_pred_analytic)

    ml_logloss = log_loss(y_test, y_pred_ml)
    analytic_logloss = log_loss(y_test, y_pred_analytic)

    print(f"\n  {'Metric':<20} {'Analytic':>12} {'ML Model':>12} {'Improvement':>14}")
    print(f"  {'-'*58}")
    print(f"  {'Brier Score':<20} {analytic_brier:>12.6f} {ml_brier:>12.6f} {(1 - ml_brier/analytic_brier)*100:>+13.2f}%")
    print(f"  {'Log Loss':<20} {analytic_logloss:>12.6f} {ml_logloss:>12.6f} {(1 - ml_logloss/analytic_logloss)*100:>+13.2f}%")

    # Feature importance
    print(f"\n  Feature Importances:")
    importances = gb.feature_importances_
    for name, imp in sorted(zip(FEATURE_COLS, importances), key=lambda x: -x[1]):
        bar = '#' * int(imp * 50)
        print(f"    {name:<22} {imp:.4f}  {bar}")

    # Calibration check: bin predictions and compare to actual win rate
    print(f"\n  Calibration Check (10 bins):")
    print(f"  {'Predicted WP':>14} {'Actual Win%':>14} {'Count':>8} {'Error':>8}")
    print(f"  {'-'*48}")
    bins = np.linspace(0, 1, 11)
    for i in range(len(bins) - 1):
        mask = (y_pred_ml >= bins[i]) & (y_pred_ml < bins[i + 1])
        if mask.sum() > 0:
            pred_mean = y_pred_ml[mask].mean()
            actual_mean = y_test[mask].mean()
            error = pred_mean - actual_mean
            print(f"  {pred_mean:>13.1%} {actual_mean:>13.1%} {mask.sum():>8,} {error:>+7.1%}")

    # Save model
    os.makedirs('data_cache', exist_ok=True)
    model_path = os.path.join('data_cache', 'wp_model.pkl')
    joblib.dump(calibrated, model_path)
    print(f"\nSaved calibrated model to {model_path}")

    # Save evaluation metrics for reference
    metrics = {
        'ml_brier': round(ml_brier, 6),
        'analytic_brier': round(analytic_brier, 6),
        'ml_logloss': round(ml_logloss, 6),
        'analytic_logloss': round(analytic_logloss, 6),
        'brier_improvement_pct': round((1 - ml_brier / analytic_brier) * 100, 2),
        'logloss_improvement_pct': round((1 - ml_logloss / analytic_logloss) * 100, 2),
        'train_seasons': '2007-2022',
        'val_season': '2023',
        'test_seasons': '2024-2025',
        'train_rows': int(len(X_train)),
        'val_rows': int(len(X_val)),
        'test_rows': int(len(X_test)),
        'features': FEATURE_COLS,
    }
    metrics_path = os.path.join('data_cache', 'wp_model_metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved metrics to {metrics_path}")

    return calibrated


def main():
    print("=" * 55)
    print("  EUROLEAGUE ML WIN PROBABILITY MODEL — TRAINING")
    print("=" * 55)
    t0 = time.time()

    features_df = build_dataset()
    model = train_model(features_df)

    print(f"\nTotal pipeline time: {time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()
