"""
Shared play-by-play cleaning for the game-records engine.

clean_game() turns one game's raw PBP rows into a CleanGame (sorted rows,
numeric scores, team codes, final score) or None when the log is unusable.
iter_games() yields a CleanGame for every usable cached game. The ranking,
row-finishing and JSON-writing helpers are shared by every record board.
"""
import json
import os
from collections import Counter
from dataclasses import dataclass

import pandas as pd

from season_config import ALL_SEASONS, season_label

CACHE_DIR = 'data_cache'
REPLAY_DIR = os.path.join('docs', 'data')
TOP_N = 25
MIN_SCORING_ROWS = 30        # fewer scoring plays than this = truncated game
MIN_FINAL = 45               # a final under this is a data error, not a score
LAST_REGULATION_PERIOD = 4   # a log ending earlier is an incomplete game
GLITCH_TOL = 3               # one play moves the margin by at most 3 points


@dataclass
class CleanGame:
    season: int
    phase: object            # str | None
    round: object            # int | None
    gamecode: int
    rows: pd.DataFrame       # every row, sorted, with PT and PID columns
    sc: pd.DataFrame         # scoring rows only, index reset
    a: list
    b: list
    periods: list
    clocks: list
    final_a: int
    final_b: int
    a_won: bool
    code_a: object
    name_a: object
    code_b: object
    name_b: object
    ot: bool


def mode_value(series):
    m = series.dropna().astype(str).str.strip().mode()
    return m.iloc[0] if not m.empty else None


def int_or_none(v):
    try:
        return None if pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def _pid(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s[1:] if s.startswith('P') else s


def clean_game(g):
    """One game's raw PBP rows -> CleanGame, or None if the game is unusable."""
    key = ('TRUE_NUMBEROFPLAY'
           if 'TRUE_NUMBEROFPLAY' in g and g['TRUE_NUMBEROFPLAY'].notna().all()
           else 'NUMBEROFPLAY')
    g = g.drop_duplicates([key, 'PLAYTYPE', 'CODETEAM']).copy()
    for col in ('POINTS_A', 'POINTS_B', 'PERIOD'):
        g[col] = pd.to_numeric(g[col], errors='coerce')
    g['PT'] = g['PLAYTYPE'].astype(str).str.strip()
    g['PID'] = g['PLAYER_ID'].map(_pid) if 'PLAYER_ID' in g else None
    g = g.sort_values(['PERIOD', key], kind='stable')
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

    first = g.iloc[0]
    phase = first.get('Phase')
    return CleanGame(
        season=int(first['Season']),
        phase=None if pd.isna(phase) else str(phase).strip(),
        round=int_or_none(first.get('Round')),
        gamecode=int(first['Gamecode']),
        rows=g.reset_index(drop=True),
        sc=sc,
        a=a, b=b,
        periods=sc['PERIOD'].fillna(0).astype(int).tolist(),
        clocks=sc['MARKERTIME'].tolist(),
        final_a=fa, final_b=fb, a_won=fa > fb,
        code_a=mode_value(sc.loc[a_up, 'CODETEAM']), name_a=mode_value(sc.loc[a_up, 'TEAM']),
        code_b=mode_value(sc.loc[b_up, 'CODETEAM']), name_b=mode_value(sc.loc[b_up, 'TEAM']),
        ot=bool(g['PERIOD'].max() > LAST_REGULATION_PERIOD),
    )


def iter_games(seasons=ALL_SEASONS, cache_dir=CACHE_DIR):
    """Yield a CleanGame for every usable game in data_cache/pbp_{season}.csv."""
    for s in seasons:
        path = os.path.join(cache_dir, f'pbp_{s}.csv')
        if not os.path.exists(path):
            print(f'  [WARN] {path} missing, skipping {season_label(s)}')
            continue
        df = pd.read_csv(path, low_memory=False)
        for _, g in df.groupby('Gamecode', sort=False):
            cg = clean_game(g)
            if cg is not None:
                yield cg


def rank_by(records, key, limit=TOP_N):
    """Top `limit` records with key > 0 (ties: newest first), each with rank and tied flag."""
    rows = sorted((r for r in records if r[key] > 0),
                  key=lambda r: (-r[key], -r['season'], -r['gamecode']))
    counts = Counter(r[key] for r in rows)   # before the cut, so cutoff ties count
    out, rank = [], 0
    for i, r in enumerate(rows[:limit]):
        if i == 0 or r[key] != rows[i - 1][key]:
            rank = i + 1
        out.append({'rank': rank, 'tied': counts[r[key]] > 1, **r})
    return out


def finish_rows(rows, replay_dir=REPLAY_DIR):
    """Add season_label and has_replay to each row (in place) and return them."""
    for r in rows:
        r['season_label'] = season_label(r['season'])
        r['has_replay'] = os.path.exists(
            os.path.join(replay_dir, str(r['season']), f"{r['gamecode']}.json"))
    return rows


def season_span(records):
    seasons = sorted({r['season'] for r in records})
    return [seasons[0], seasons[-1]] if seasons else []


def keep_generated_date(old, new, content_keys):
    """Reuse the old `generated` date when nothing but the date would change."""
    if old and all(old.get(k) == new.get(k) for k in content_keys):
        new['generated'] = old['generated']
    return new


def write_json_if_changed(path, out, content_keys):
    """Write `out` to `path`, keeping the old generated date if the content is unchanged."""
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                keep_generated_date(json.load(f), out, content_keys)
        except (OSError, ValueError, KeyError):
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out
