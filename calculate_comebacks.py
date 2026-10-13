"""
Biggest Comebacks: the largest deficits overcome by the eventual winner.

Reads cached play-by-play for every season in season_config.ALL_SEASONS
(data_cache/pbp_{season}.csv) and writes docs/data/current/comebacks.json
with three ranked lists: overall, fourth_quarter (deficit faced in Q4/OT)
and postseason (Playoffs, Play-In, Final Four).
"""
import json
import os
from collections import Counter
from datetime import date

import pandas as pd

from season_config import ALL_SEASONS, CURRENT_SEASON, season_label

CACHE_DIR = 'data_cache'
OUT_PATH = os.path.join('docs', 'data', 'current', 'comebacks.json')
REPLAY_DIR = os.path.join('docs', 'data')
TOP_N = 25
MIN_SCORING_ROWS = 30   # fewer scoring plays than this = truncated game
MIN_FINAL = 45          # a final under this is a data error, not a score
LAST_REGULATION_PERIOD = 4   # a log ending earlier is an incomplete game
GLITCH_TOL = 3          # one play moves the margin by at most 3 points
POSTSEASON = {'PO', 'PI', 'FF'}
NO_DEFICIT = {'deficit': 0, 'trailing': None, 'quarter': None, 'clock': None}


def _confirmed_margins(margins):
    """Zero out margins no neighbouring play agrees with (single-row score typos)."""
    out = []
    for i, m in enumerate(margins):
        nbrs = margins[max(i - 1, 0):i] + margins[i + 1:i + 2]
        out.append(m if any(abs(m - x) <= GLITCH_TOL for x in nbrs) else 0)
    return out


def _mode(series):
    m = series.dropna().astype(str).str.strip().mode()
    return m.iloc[0] if not m.empty else None


def _int_or_none(v):
    try:
        return None if pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def analyze_game(g):
    """One game's PBP rows -> comeback record, or None if the game is unusable."""
    key = ('TRUE_NUMBEROFPLAY'
           if 'TRUE_NUMBEROFPLAY' in g and g['TRUE_NUMBEROFPLAY'].notna().all()
           else 'NUMBEROFPLAY')
    g = g.drop_duplicates([key, 'PLAYTYPE', 'CODETEAM']).sort_values(['PERIOD', key], kind='stable')
    sc = g[g['POINTS_A'].notna() | g['POINTS_B'].notna()].reset_index(drop=True)
    if len(sc) < MIN_SCORING_ROWS:
        return None
    if sc['PERIOD'].max() < LAST_REGULATION_PERIOD:
        return None
    a = sc['POINTS_A'].ffill().fillna(0).astype(int).tolist()
    b = sc['POINTS_B'].ffill().fillna(0).astype(int).tolist()
    fa, fb = a[-1], b[-1]
    if fa == fb or min(fa, fb) < MIN_FINAL:
        return None

    a_up = pd.Series([a[0]] + [a[i] - a[i - 1] for i in range(1, len(a))]) > 0
    b_up = pd.Series([b[0]] + [b[i] - b[i - 1] for i in range(1, len(b))]) > 0
    code_a, name_a = _mode(sc.loc[a_up, 'CODETEAM']), _mode(sc.loc[a_up, 'TEAM'])
    code_b, name_b = _mode(sc.loc[b_up, 'CODETEAM']), _mode(sc.loc[b_up, 'TEAM'])

    a_won = fa > fb
    w_pts, l_pts = (a, b) if a_won else (b, a)
    conf = _confirmed_margins([w - l for w, l in zip(w_pts, l_pts)])
    periods = sc['PERIOD'].fillna(0).astype(int).tolist()
    clocks = sc['MARKERTIME'].tolist()

    def worst(indices):
        if not indices:
            return dict(NO_DEFICIT)
        i = min(indices, key=lambda j: (conf[j], j))
        if conf[i] >= 0:
            return dict(NO_DEFICIT)
        clk = clocks[i]
        return {'deficit': -conf[i], 'trailing': f'{w_pts[i]}-{l_pts[i]}',
                'quarter': periods[i], 'clock': None if pd.isna(clk) else str(clk)}

    first = g.iloc[0]
    phase = first.get('Phase')
    return {
        'season': int(first['Season']),
        'phase': None if pd.isna(phase) else str(phase).strip(),
        'round': _int_or_none(first.get('Round')),
        'gamecode': int(first['Gamecode']),
        'winner': code_a if a_won else code_b,
        'winner_name': name_a if a_won else name_b,
        'loser': code_b if a_won else code_a,
        'loser_name': name_b if a_won else name_a,
        'home': a_won,
        **worst(list(range(len(conf)))),
        'q4': worst([i for i, p in enumerate(periods) if p >= 4]),
        'final': f'{max(fa, fb)}-{min(fa, fb)}',
        'ot': bool(g['PERIOD'].max() > 4),
    }


def rank_entries(records, limit=TOP_N):
    """Top `limit` by deficit (ties: newest first), each with rank and tied flag."""
    rows = sorted((r for r in records if r['deficit'] > 0),
                  key=lambda r: (-r['deficit'], -r['season'], -r['gamecode']))
    counts = Counter(r['deficit'] for r in rows)   # before the cut, so cutoff ties count
    out, rank = [], 0
    for i, r in enumerate(rows[:limit]):
        if i == 0 or r['deficit'] != rows[i - 1]['deficit']:
            rank = i + 1
        out.append({'rank': rank, 'tied': counts[r['deficit']] > 1, **r})
    return out


def _without_q4(r):
    return {k: v for k, v in r.items() if k != 'q4'}


def _with_q4(r):
    return {**_without_q4(r), **r['q4']}


def build_output(records, current_season, replay_dir=REPLAY_DIR, generated=None):
    def finish(rows):
        for r in rows:
            r['season_label'] = season_label(r['season'])
            r['has_replay'] = os.path.exists(
                os.path.join(replay_dir, str(r['season']), f"{r['gamecode']}.json"))
        return rows

    seasons = sorted({r['season'] for r in records})
    return {
        'generated': generated or date.today().isoformat(),
        'seasons': [seasons[0], seasons[-1]] if seasons else [],
        'current_season': current_season,
        'games_scanned': len(records),
        'overall': finish(rank_entries([_without_q4(r) for r in records])),
        'fourth_quarter': finish(rank_entries([_with_q4(r) for r in records])),
        'postseason': finish(rank_entries(
            [_without_q4(r) for r in records if r['phase'] in POSTSEASON])),
    }


def load_records(seasons=ALL_SEASONS, cache_dir=CACHE_DIR):
    records = []
    for s in seasons:
        path = os.path.join(cache_dir, f'pbp_{s}.csv')
        if not os.path.exists(path):
            print(f'  [WARN] {path} missing, skipping {season_label(s)}')
            continue
        df = pd.read_csv(path, low_memory=False)
        for _, g in df.groupby('Gamecode', sort=False):
            r = analyze_game(g)
            if r:
                records.append(r)
    return records


CONTENT_KEYS = ('overall', 'fourth_quarter', 'postseason', 'games_scanned', 'current_season')


def keep_generated_date(old, new):
    """Reuse the old `generated` date when nothing but the date would change."""
    if old and all(old.get(k) == new.get(k) for k in CONTENT_KEYS):
        new['generated'] = old['generated']
    return new


def main():
    out = build_output(load_records(), CURRENT_SEASON)
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding='utf-8') as f:
                keep_generated_date(json.load(f), out)
        except (OSError, ValueError, KeyError):
            pass
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"Comebacks: {out['games_scanned']} games scanned -> {OUT_PATH}")
    if out['overall']:
        top = out['overall'][0]
        print(f"  Biggest: {top['winner']} over {top['loser']} "
              f"({top['season_label']}) from {top['deficit']} down")


if __name__ == '__main__':
    main()
