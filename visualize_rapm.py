"""
RAPM Visualizations — Euroleague (current season)
======================================
1. O-RAPM vs D-RAPM scatter (offensive vs defensive impact)
2. RAPM vs TPM comparison (context-adjusted vs raw plus-minus)
"""

from season_config import season_label
from chart_utils import ratings_path
import pandas as pd
import matplotlib.pyplot as plt
from adjustText import adjust_text
import os

# Dark theme colors (matching repo style)
BG_OUTER = '#0d1117'
BG_INNER = '#161b22'
GRID_COLOR = '#30363d'
TEXT_MAIN = '#e6edf3'
TEXT_DIM = '#8b949e'
GREEN = '#39d353'
RED = '#f85149'
BLUE = '#58a6ff'
PURPLE = '#d2a8ff'
GOLD = '#FFD700'


def clean_name(raw):
    """Convert 'LAST, FIRST' to 'First Last'."""
    parts = raw.split(',')
    if len(parts) == 2:
        return f"{parts[1].strip().title()} {parts[0].strip().title()}"
    return raw.title()


def create_orapm_drapm_chart():
    """Quadrant scatter: Offensive RAPM vs Defensive RAPM."""
    rapm_path = ratings_path('rapm_ratings')
    if not rapm_path:
        print("No rapm_ratings for this round yet - skipping O/D RAPM chart.")
        return
    df = pd.read_json(rapm_path)
    df = df[df['est_minutes'] >= 300].copy()

    fig, ax = plt.subplots(figsize=(13, 10))
    fig.patch.set_facecolor(BG_OUTER)
    ax.set_facecolor(BG_INNER)

    med_o = df['ORAPM'].median()
    med_d = df['DRAPM'].median()

    # Quadrant dividers
    ax.axhline(med_d, color=GRID_COLOR, linestyle='--', zorder=1)
    ax.axvline(med_o, color=GRID_COLOR, linestyle='--', zorder=1)

    # Color by quadrant
    colors = []
    for _, r in df.iterrows():
        if r['ORAPM'] >= med_o and r['DRAPM'] >= med_d:
            colors.append(GREEN)    # Two-way stars
        elif r['ORAPM'] < med_o and r['DRAPM'] < med_d:
            colors.append(RED)      # Negative impact
        elif r['ORAPM'] >= med_o and r['DRAPM'] < med_d:
            colors.append(PURPLE)   # Offensive-only
        else:
            colors.append(BLUE)     # Defensive specialists

    ax.scatter(df['ORAPM'], df['DRAPM'], c=colors, s=120,
               edgecolors=BG_INNER, linewidths=1.5, zorder=5, alpha=0.9)

    # Quadrant labels
    x_min, x_max = df['ORAPM'].min(), df['ORAPM'].max()
    y_min, y_max = df['DRAPM'].min(), df['DRAPM'].max()

    ax.text(x_max - 0.1, y_max - 0.1, 'TWO-WAY STARS\n(Elite Offense + Defense)',
            fontsize=11, color=GREEN, ha='right', va='top', fontweight='bold', alpha=0.5)
    ax.text(x_min + 0.1, y_max - 0.1, 'DEFENSIVE ANCHORS\n(Low Offense, Elite Defense)',
            fontsize=11, color=BLUE, ha='left', va='top', fontweight='bold', alpha=0.5)
    ax.text(x_max - 0.1, y_min + 0.1, 'OFFENSIVE ENGINES\n(Elite Offense, Weak Defense)',
            fontsize=11, color=PURPLE, ha='right', va='bottom', fontweight='bold', alpha=0.5)

    # Label top players in each quadrant
    two_way = df[(df['ORAPM'] >= med_o) & (df['DRAPM'] >= med_d)].nlargest(8, 'RAPM')
    def_anchors = df[(df['ORAPM'] < med_o) & (df['DRAPM'] >= med_d)].nlargest(5, 'DRAPM')
    off_engines = df[(df['ORAPM'] >= med_o) & (df['DRAPM'] < med_d)].nlargest(5, 'ORAPM')
    worst = df.nsmallest(4, 'RAPM')

    to_label = pd.concat([two_way, def_anchors, off_engines, worst]).drop_duplicates(subset=['player'])

    texts = []
    for _, r in to_label.iterrows():
        label = f"{clean_name(r['player'])} ({r['team']})"
        texts.append(ax.text(r['ORAPM'], r['DRAPM'], label,
                             fontsize=8, color=TEXT_MAIN, fontweight='bold'))

    adjust_text(texts, ax=ax,
                arrowprops=dict(arrowstyle='-', color=TEXT_DIM, alpha=0.6, lw=0.8),
                force_text=(2.0, 2.5), force_points=(1.5, 2.0), expand=(2.5, 2.5),
                ensure_inside_axes=False, time_lim=5)

    ax.set_title(f"Offensive RAPM vs Defensive RAPM\nEuroleague {season_label()} (min 300 est. minutes)",
                 fontsize=16, color=TEXT_MAIN, fontweight='bold', pad=20)
    ax.set_xlabel('O-RAPM (Offensive Impact per 100 Possessions)', fontsize=12, color=TEXT_DIM, fontweight='bold')
    ax.set_ylabel('D-RAPM (Defensive Impact per 100 Possessions)', fontsize=12, color=TEXT_DIM, fontweight='bold')

    ax.tick_params(colors=TEXT_DIM)
    ax.spines['bottom'].set_color(GRID_COLOR)
    ax.spines['left'].set_color(GRID_COLOR)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.15, color=GRID_COLOR)

    plt.tight_layout()
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    outfile = f'rapm_orapm_vs_drapm{round_suffix}.png'
    plt.savefig(outfile, dpi=150, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {outfile}")


def create_rapm_vs_tpm_chart():
    """Show how RAPM differs from raw TPM — who gains/loses from context adjustment."""
    rapm_path = ratings_path('rapm_ratings')
    tpm_file = ratings_path('tpm_ratings')
    if not rapm_path or not tpm_file:
        print("Missing rapm/tpm ratings for this round - skipping RAPM vs TPM chart.")
        return
    rapm_df = pd.read_json(rapm_path)

    tpm_df = pd.read_json(tpm_file)

    # Merge: RAPM uses full player name, TPM uses player.name
    # Normalize both to merge
    rapm_df['merge_key'] = rapm_df['player'].str.strip().str.upper()
    tpm_df['merge_key'] = tpm_df['player.name'].str.strip().str.upper()

    df = pd.merge(rapm_df, tpm_df, on='merge_key', suffixes=('_rapm', '_tpm'))
    df = df[df['est_minutes'] >= 300].copy()

    if len(df) < 10:
        print(f"Warning: Only {len(df)} players merged. Check name matching.")
        return

    fig, ax = plt.subplots(figsize=(13, 10))
    fig.patch.set_facecolor(BG_OUTER)
    ax.set_facecolor(BG_INNER)

    x = df['TPM_40']
    y = df['RAPM']

    # Color by how much RAPM differs from TPM (context adjustment delta)
    delta = y - (x / 5)  # Scale TPM to roughly same range as RAPM
    # Simpler: color by RAPM directly
    colors = []
    for _, r in df.iterrows():
        if r['RAPM'] >= 0.5:
            colors.append(GREEN)
        elif r['RAPM'] <= -0.5:
            colors.append(RED)
        else:
            colors.append(TEXT_DIM)

    ax.scatter(x, y, c=colors, s=120, edgecolors=BG_INNER, linewidths=1.5, zorder=5, alpha=0.9)

    # Reference line: perfect correlation
    ax.axhline(0, color=GRID_COLOR, linestyle='-', linewidth=1, alpha=0.5)
    ax.axvline(0, color=GRID_COLOR, linestyle='-', linewidth=1, alpha=0.5)

    # Label biggest movers (players whose RAPM diverges most from raw TPM rank)
    df['tpm_rank'] = df['TPM_40'].rank(ascending=False)
    df['rapm_rank'] = df['RAPM'].rank(ascending=False)
    df['rank_shift'] = df['tpm_rank'] - df['rapm_rank']  # Positive = RAPM ranks them higher

    biggest_risers = df.nlargest(6, 'rank_shift')
    biggest_fallers = df.nsmallest(6, 'rank_shift')
    top_rapm = df.nlargest(5, 'RAPM')

    to_label = pd.concat([biggest_risers, biggest_fallers, top_rapm]).drop_duplicates(subset=['merge_key'])

    texts = []
    for _, r in to_label.iterrows():
        name = clean_name(r['player'])
        team = r['team']
        shift = int(r['rank_shift'])
        arrow = f"+{shift}" if shift > 0 else str(shift)
        label = f"{name} ({team}) [{arrow}]"
        texts.append(ax.text(r['TPM_40'], r['RAPM'], label,
                             fontsize=8, color=TEXT_MAIN, fontweight='bold'))

    adjust_text(texts, ax=ax,
                arrowprops=dict(arrowstyle='-', color=TEXT_DIM, alpha=0.6, lw=0.8),
                force_text=(2.0, 2.5), force_points=(1.5, 2.0), expand=(2.5, 2.5),
                ensure_inside_axes=False, time_lim=5)

    ax.set_title("RAPM vs Raw Plus-Minus (TPM)\nWho benefits most from context adjustment?",
                 fontsize=16, color=TEXT_MAIN, fontweight='bold', pad=20)
    ax.set_xlabel('Raw TPM per 40 min (unadjusted)', fontsize=12, color=TEXT_DIM, fontweight='bold')
    ax.set_ylabel('RAPM (context-adjusted, per 100 possessions)', fontsize=12, color=TEXT_DIM, fontweight='bold')

    ax.tick_params(colors=TEXT_DIM)
    ax.spines['bottom'].set_color(GRID_COLOR)
    ax.spines['left'].set_color(GRID_COLOR)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.15, color=GRID_COLOR)

    plt.tight_layout()
    outfile = f'rapm_vs_tpm{round_suffix}.png'
    plt.savefig(outfile, dpi=150, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {outfile}")


if __name__ == '__main__':
    create_orapm_drapm_chart()
    create_rapm_vs_tpm_chart()
