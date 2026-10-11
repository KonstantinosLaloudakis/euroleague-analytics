"""
Oracle Accuracy Tracker for Euroleague.

Two modes:
  1. Backtest  — retroactively applies the oracle prediction formula to all
                 played historical games using current ratings. Saves
                 oracle_backtest_predictions.json.
  2. Track     — reads backtest + any saved oracle forecast JSONs, matches
                 against actual results, and computes accuracy metrics.
                 Saves oracle_accuracy.json + oracle_accuracy.png.

Usage:
    python oracle_accuracy_tracker.py              # backtest + track + visualize
    python oracle_accuracy_tracker.py --no-backtest  # skip backtest regeneration
"""

from season_config import CURRENT_SEASON
import json
import os
import argparse
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from wp_model_utils import predict_wp


# ── Constants (mirror oracle formula exactly) ─────────────────────────────────
STARTING_ELO  = 1500
ADJ_NET_W     = 0.75
ELO_W         = 0.25
ELO_HCA       = 50       # Elo home-court advantage points
ELO_SCALE     = 25       # convert Elo pts → margin pts

NAME_TO_CODE = {
    'ALBA BERLIN': 'BER', 'ANADOLU EFES ISTANBUL': 'IST', 'AS MONACO': 'MCO',
    'BASKONIA VITORIA-GASTEIZ': 'BAS', 'KOSNER BASKONIA VITORIA-GASTEIZ': 'BAS',
    'CRVENA ZVEZDA MERIDIANBET BELGRADE': 'RED', 'EA7 EMPORIO ARMANI MILAN': 'MIL',
    'FC BARCELONA': 'BAR', 'FC BAYERN MUNICH': 'MUN',
    'FENERBAHCE BEKO ISTANBUL': 'ULK', 'LDLC ASVEL VILLEURBANNE': 'ASV',
    'MACCABI PLAYTIKA TEL AVIV': 'TEL', 'MACCABI RAPYD TEL AVIV': 'TEL',
    'OLYMPIACOS PIRAEUS': 'OLY', 'PANATHINAIKOS AKTOR ATHENS': 'PAN',
    'PARTIZAN MOZZART BET BELGRADE': 'PAR', 'PARIS BASKETBALL': 'PRS',
    'REAL MADRID': 'MAD', 'VALENCIA BASKET': 'PAM',
    'BESIKTAS ISTANBUL': 'BES', 'ARMANI OLIMPIA MILAN': 'MIL', 'FENERBAHCE TARFIN ISTANBUL': 'ULK',
    'VIRTUS SEGAFREDO BOLOGNA': 'VIR', 'VIRTUS BOLOGNA': 'VIR',
    'ZALGIRIS KAUNAS': 'ZAL', 'DUBAI BASKETBALL': 'DUB', 'HAPOEL IBI TEL AVIV': 'HTA',
}
# ─────────────────────────────────────────────────────────────────────────────


def _load_ratings():
    """Load current adj_net and Elo ratings into dicts."""
    adj_net, elo = {}, {}

    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    for fname, fallback, target in [
        (f'adjusted_ratings{round_suffix}.json', 'adjusted_ratings.json', (adj_net, 'Adj_Net')),
        (f'elo_ratings{round_suffix}.json',      'elo_ratings.json',      (elo,     'Elo')),
    ]:
        path = fname if os.path.exists(fname) else fallback
        if os.path.exists(path):
            with open(path) as f:
                for entry in json.load(f):
                    target[0][entry['Team']] = entry[target[1]]

    return adj_net, elo


def _predict_game(home, away, adj_net, elo, hca=3.3):
    """Apply oracle formula → (home_win_prob, predicted_margin)."""
    h_adj = adj_net.get(home, 0.0)
    a_adj = adj_net.get(away, 0.0)
    h_elo = elo.get(home, STARTING_ELO)
    a_elo = elo.get(away, STARTING_ELO)

    adj_diff   = h_adj - a_adj
    elo_margin = (h_elo - a_elo + ELO_HCA) / ELO_SCALE
    margin     = adj_diff * ADJ_NET_W + elo_margin * ELO_W + hca * 0.5

    home_win_prob = predict_wp(
        margin=margin,
        seconds_remaining=2400,
        elo_diff=h_elo - a_elo,
    )
    return round(home_win_prob * 100, 1), round(margin, 2)


def run_backtest():
    """
    Generate oracle predictions for every played historical game.
    Saves oracle_backtest_predictions.json.
    """
    print("Running historical backtest...")

    adj_net, elo = _load_ratings()
    if not adj_net:
        print("Warning: no adjusted ratings found — backtest predictions will be less accurate.")

    # Load played results
    results = pd.read_json('mvp_game_results.json')
    played  = results[(results['LocalScore'] > 0) & (results['RoadScore'] > 0)].copy()

    # Load XML schedule for round mapping
    round_map = {}  # GameCode int → round number
    if os.path.exists(f'official_schedule_{CURRENT_SEASON}.xml'):
        tree = ET.parse(f'official_schedule_{CURRENT_SEASON}.xml')
        for item in tree.getroot().findall('item'):
            gc_el = item.find('gamecode')
            gd_el = item.find('gameday')
            if gc_el is not None and gd_el is not None:
                gc_text = gc_el.text
                gc_num  = int(gc_text.split('_')[1]) if '_' in gc_text else int(gc_text)
                round_map[gc_num] = int(gd_el.text)

    # Compute global HCA from results
    hca = (played['LocalScore'] - played['RoadScore']).mean()

    records = []
    for _, row in played.iterrows():
        home, away = row['LocalTeam'], row['RoadTeam']
        if home == 'UNKNOWN' or away == 'UNKNOWN':
            continue

        home_win_prob, margin = _predict_game(home, away, adj_net, elo, hca)
        predicted_winner = home if home_win_prob >= 50 else away
        actual_winner    = row['Winner']
        correct          = predicted_winner == actual_winner
        # Probability assigned to the actual winner
        prob_correct     = home_win_prob / 100 if actual_winner == home else (100 - home_win_prob) / 100

        records.append({
            'GameCode':        int(row['GameCode']),
            'Round':           round_map.get(int(row['GameCode']), -1),
            'Home':            home,
            'Away':            away,
            'HomeWinProb':     home_win_prob,
            'PredictedMargin': margin,
            'PredictedWinner': predicted_winner,
            'ActualWinner':    actual_winner,
            'Correct':         correct,
            'ProbCorrect':     round(prob_correct, 4),
        })

    with open('oracle_backtest_predictions.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f"Backtest saved: {len(records)} games across "
          f"{len(set(r['Round'] for r in records if r['Round'] > 0))} rounds.")
    return records


def load_oracle_forecasts():
    """
    Scan for saved oracle forecast JSONs and extract predictions that have
    matching actual results.
    """
    results = pd.read_json('mvp_game_results.json')
    played  = results[(results['LocalScore'] > 0) & (results['RoadScore'] > 0)]
    played_set = set(zip(played['LocalTeam'], played['RoadTeam']))
    actual_map = {(r['LocalTeam'], r['RoadTeam']): r['Winner']
                  for _, r in played.iterrows()}

    records = []
    for fname in sorted(os.listdir('.')):
        if not (fname.startswith('oracle_forecast_round_') and fname.endswith('.json')):
            continue
        # Extract round number from filename
        try:
            # oracle_forecast_round_32_ml.json → 32
            part = fname.replace('oracle_forecast_round_', '').replace('.json', '')
            round_num = int(part.split('_')[0])
        except (ValueError, IndexError):
            continue

        with open(fname) as f:
            data = json.load(f)

        preds = data.get('predictions', [])
        for p in preds:
            home, away = p['Local'], p['Road']
            actual = actual_map.get((home, away))
            if actual is None:
                continue  # game not yet played

            home_win_prob    = p['HomeWinProb']
            predicted_winner = home if home_win_prob >= 50 else away
            correct          = predicted_winner == actual
            prob_correct     = home_win_prob / 100 if actual == home else (100 - home_win_prob) / 100

            records.append({
                'GameCode':        None,
                'Round':           round_num,
                'Home':            home,
                'Away':            away,
                'HomeWinProb':     home_win_prob,
                'PredictedWinner': predicted_winner,
                'ActualWinner':    actual,
                'Correct':         correct,
                'ProbCorrect':     round(prob_correct, 4),
                'Source':          fname,
            })

    return records


def compute_metrics(records):
    """Compute accuracy, Brier score, log-loss, and calibration buckets."""
    if not records:
        return {}

    df = pd.DataFrame(records)
    n  = len(df)

    accuracy   = df['Correct'].mean()
    brier      = ((df['ProbCorrect'] - 1) ** 2).mean()   # MSE vs outcome=1
    log_loss   = -np.log(df['ProbCorrect'].clip(0.01, 0.99)).mean()

    # Calibration buckets: group by predicted confidence
    df['Conf'] = df['HomeWinProb'].apply(lambda p: p if p >= 50 else 100 - p)
    bins   = [50, 60, 70, 80, 90, 101]
    labels = ['50-60%', '60-70%', '70-80%', '80-90%', '90%+']
    df['Bucket'] = pd.cut(df['Conf'], bins=bins, labels=labels, right=False)

    calibration = []
    for bucket in labels:
        sub = df[df['Bucket'] == bucket]
        if len(sub) == 0:
            continue
        calibration.append({
            'Bucket':       bucket,
            'Count':        len(sub),
            'Accuracy':     round(sub['Correct'].mean() * 100, 1),
            'AvgConfidence':round(sub['Conf'].mean(), 1),
        })

    # Per-round accuracy
    per_round = (
        df[df['Round'] > 0]
        .groupby('Round')
        .agg(Games=('Correct', 'count'), Accuracy=('Correct', 'mean'))
        .reset_index()
        .sort_values('Round')
    )
    per_round['Accuracy'] = (per_round['Accuracy'] * 100).round(1)

    return {
        'n_games':     n,
        'accuracy':    round(accuracy * 100, 1),
        'brier_score': round(brier, 4),
        'log_loss':    round(log_loss, 4),
        'calibration': calibration,
        'per_round':   per_round.to_dict(orient='records'),
    }


def visualize(metrics, records):
    """Generate oracle_accuracy.png."""
    per_round   = pd.DataFrame(metrics['per_round'])
    calibration = pd.DataFrame(metrics['calibration'])

    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor('#0f172a')

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    ax_trend = fig.add_subplot(gs[0, :])   # full-width top
    ax_cal   = fig.add_subplot(gs[1, 0])
    ax_dist  = fig.add_subplot(gs[1, 1])

    text_color  = '#e2e8f0'
    grid_color  = '#334155'
    accent      = '#fbbf24'
    green       = '#22c55e'
    blue        = '#38bdf8'

    for ax in [ax_trend, ax_cal, ax_dist]:
        ax.set_facecolor('#1e293b')
        ax.tick_params(colors=text_color, labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor(grid_color)
        ax.grid(color=grid_color, linewidth=0.5, alpha=0.6)

    # ── Top: per-round accuracy trend ────────────────────────────────────────
    MIN_FULL_ROUND = 5  # rounds with fewer games are makeup/rescheduled games
    if not per_round.empty:
        full   = per_round[per_round['Games'] >= MIN_FULL_ROUND]
        makeup = per_round[per_round['Games'] <  MIN_FULL_ROUND]

        # Main trend line through full rounds only
        ax_trend.plot(full['Round'], full['Accuracy'],
                      color=accent, linewidth=2.0, marker='o', markersize=5,
                      label='Full round (≥5 games)')
        # Makeup games as hollow markers — not connected to the line
        if not makeup.empty:
            ax_trend.scatter(makeup['Round'], makeup['Accuracy'],
                             color='#94a3b8', s=50, marker='o', zorder=5,
                             linewidths=1.5, facecolors='none',
                             label='Makeup game (<5 games)')

        ax_trend.axhline(metrics['accuracy'], color=green, linewidth=1.5,
                         linestyle='--', label=f"Season avg {metrics['accuracy']}%")
        ax_trend.axhline(50, color='#64748b', linewidth=1.0, linestyle=':')
        ax_trend.set_ylim(0, 110)
        ax_trend.set_xlabel('Round', color=text_color, fontsize=10)
        ax_trend.set_ylabel('Accuracy %', color=text_color, fontsize=10)
        ax_trend.set_title('Prediction Accuracy by Round', color=text_color,
                            fontsize=13, fontweight='bold')
        ax_trend.legend(facecolor='#1e293b', labelcolor=text_color, fontsize=9)
        # Annotate full rounds
        for _, row in full.iterrows():
            ax_trend.annotate(f"{row['Accuracy']:.0f}%",
                              (row['Round'], row['Accuracy']),
                              textcoords='offset points', xytext=(0, 8),
                              color=text_color, fontsize=7, ha='center')
        # Annotate makeup games with game count
        for _, row in makeup.iterrows():
            ax_trend.annotate(f"{row['Accuracy']:.0f}%\n(n={row['Games']})",
                              (row['Round'], row['Accuracy']),
                              textcoords='offset points', xytext=(0, 10),
                              color='#94a3b8', fontsize=7, ha='center')

    # ── Bottom-left: calibration bar chart ───────────────────────────────────
    if not calibration.empty:
        x = range(len(calibration))
        bars = ax_cal.bar(x, calibration['Accuracy'], color=blue, alpha=0.8, width=0.6)
        # Overlay expected (midpoint of confidence bucket)
        mids = [55, 65, 75, 85, 95]
        for i, mid in enumerate(mids[:len(calibration)]):
            ax_cal.plot(i, mid, marker='D', color=accent, markersize=7, zorder=5)
        ax_cal.set_xticks(list(x))
        ax_cal.set_xticklabels(calibration['Bucket'], rotation=30, ha='right')
        ax_cal.set_ylim(0, 110)
        ax_cal.set_ylabel('Actual Win Rate %', color=text_color, fontsize=10)
        ax_cal.set_title('Calibration by Confidence Bucket\n(diamond = expected)',
                          color=text_color, fontsize=11, fontweight='bold')
        for bar, acc, cnt in zip(bars, calibration['Accuracy'], calibration['Count']):
            ax_cal.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                        f"{acc:.0f}%\n(n={cnt})", ha='center', va='bottom',
                        color=text_color, fontsize=8)

    # ── Bottom-right: confidence distribution ────────────────────────────────
    df = pd.DataFrame(records)
    conf = df['HomeWinProb'].apply(lambda p: p if p >= 50 else 100 - p)
    ax_dist.hist(conf, bins=20, range=(50, 100), color=accent, alpha=0.8, edgecolor='#0f172a')
    ax_dist.set_xlabel('Confidence %', color=text_color, fontsize=10)
    ax_dist.set_ylabel('Games', color=text_color, fontsize=10)
    ax_dist.set_title('Distribution of Prediction Confidence',
                       color=text_color, fontsize=11, fontweight='bold')

    # ── Header summary ────────────────────────────────────────────────────────
    fig.suptitle(
        f"ORACLE ACCURACY TRACKER  —  {metrics['n_games']} games  |  "
        f"Accuracy: {metrics['accuracy']}%  |  "
        f"Brier: {metrics['brier_score']:.4f}  |  "
        f"Log-loss: {metrics['log_loss']:.4f}",
        color=accent, fontsize=14, fontweight='bold', y=0.98
    )

    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'oracle_accuracy{round_suffix}.png'
    plt.savefig(outfile, dpi=150, bbox_inches='tight', facecolor='#0f172a')
    print(f"Saved {outfile}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-backtest', action='store_true',
                        help='Skip backtest regeneration, use existing file')
    args = parser.parse_args()

    # 1. Backtest
    if not args.no_backtest or not os.path.exists('oracle_backtest_predictions.json'):
        backtest_records = run_backtest()
    else:
        with open('oracle_backtest_predictions.json') as f:
            backtest_records = json.load(f)
        print(f"Loaded existing backtest: {len(backtest_records)} games.")

    # 2. Merge with any live oracle forecast JSONs that have played results
    live_records = load_oracle_forecasts()
    if live_records:
        print(f"Found {len(live_records)} verified predictions from saved oracle forecasts.")

    # Combine — live forecasts take priority over backtest for same game
    all_records = backtest_records + live_records  # deduplicate if needed

    # 3. Compute metrics
    metrics = compute_metrics(all_records)

    print(f"\n{'='*60}")
    print(f"  ORACLE ACCURACY SUMMARY — {metrics['n_games']} games")
    print(f"{'='*60}")
    print(f"  Overall accuracy : {metrics['accuracy']}%")
    print(f"  Brier score      : {metrics['brier_score']}  (lower = better, random = 0.25)")
    print(f"  Log-loss         : {metrics['log_loss']}  (lower = better, random = 0.693)")
    print(f"\n  Calibration by confidence bucket:")
    for b in metrics['calibration']:
        print(f"    {b['Bucket']:8s}  {b['Count']:3d} games  →  actual win rate {b['Accuracy']}%")

    # 4. Save metrics JSON
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    out_json = f'oracle_accuracy{round_suffix}.json'
    with open(out_json, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"\nMetrics saved to {out_json}")

    # 5. Visualize
    visualize(metrics, all_records)
