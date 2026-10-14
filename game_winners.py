"""
Game-Winners: made field goals in the last seconds of the 4th quarter or
overtime that gave the eventual winner the lead for good.

analyze_clean() finds the play after which the winner never trailed or
was tied again, and keeps it if it is a made field goal by the winner
inside WINDOW_SECONDS of a 4th-quarter/OT clock whose score jump matches
the shot value. build_output() writes every game-winner (newest first),
the buzzer-beaters and a career leaderboard to
docs/data/current/game_winners.json.
"""
import os
from collections import Counter
from datetime import date

import pandas as pd

from pbp_games import (LAST_REGULATION_PERIOD, REPLAY_DIR, TOP_N, clock_seconds, finish_rows,
                       season_span)
from season_config import season_label

OUT_PATH = os.path.join('docs', 'data', 'current', 'game_winners.json')
CONTENT_KEYS = ('all', 'leaders', 'games_scanned', 'current_season')
WINDOW_SECONDS = 10
BUZZER_SECONDS = 1
SHOT_LABEL = {'3FGM': '3PT', '2FGM': '2PT', 'DUNK': 'Dunk', 'LAYUPMD': 'Layup'}


_seconds = clock_seconds


def analyze_clean(cg):
    """CleanGame -> game-winner record, or None if the game had none."""
    w, l = (cg.a, cg.b) if cg.a_won else (cg.b, cg.a)
    not_ahead = [i for i in range(len(w)) if w[i] - l[i] <= 0]
    if not not_ahead:
        return None
    j = not_ahead[-1] + 1
    if j >= len(w):
        return None
    row = cg.sc.iloc[j]
    pt = row['PT']
    winner, loser = (cg.code_a, cg.code_b) if cg.a_won else (cg.code_b, cg.code_a)
    if pt not in SHOT_LABEL or str(row['CODETEAM']).strip() != winner:
        return None
    if cg.periods[j] < LAST_REGULATION_PERIOD:
        return None
    secs = _seconds(cg.clocks[j])
    if secs is None or secs > WINDOW_SECONDS:
        return None
    value = 3 if pt == '3FGM' else 2
    if w[j] - w[j - 1] != value or l[j] != l[j - 1]:
        return None
    name = row['PLAYER'] if 'PLAYER' in row.index else None
    pid = row['PID']
    return {
        'season': cg.season, 'phase': cg.phase, 'round': cg.round, 'gamecode': cg.gamecode,
        'player': None if pd.isna(pid) else pid,   # never NaN: it must serialise as JSON null
        'player_name': None if pd.isna(name) else str(name).strip(),
        'team': winner, 'opp': loser, 'home': cg.a_won,
        'quarter': cg.periods[j], 'clock': str(cg.clocks[j]), 'seconds_left': secs,
        'points': value, 'shot': SHOT_LABEL[pt],
        'before': f'{w[j - 1]}-{l[j - 1]}', 'after': f'{w[j]}-{l[j]}',
        'final': f'{w[-1]}-{l[-1]}', 'ot': cg.ot,
        'buzzer': secs <= BUZZER_SECONDS,
    }


def _newest_first(records):
    return sorted(records, key=lambda r: (-r['season'], -r['gamecode']))


def leaders(records, limit=TOP_N):
    """Career game-winner counts per player (shooters without an id are skipped)."""
    by_player = {}
    for r in records:
        if r['player'] is None:
            continue
        e = by_player.setdefault(r['player'], {
            'player': r['player'], 'player_name': r['player_name'],
            'count': 0, 'buzzer_count': 0, 'last_season': r['season']})
        e['count'] += 1
        e['buzzer_count'] += int(r['buzzer'])
        e['last_season'] = max(e['last_season'], r['season'])
    rows = sorted(by_player.values(),
                  key=lambda e: (-e['count'], -e['buzzer_count'], -e['last_season']))
    counts = Counter(e['count'] for e in rows)
    out, rank = [], 0
    for i, e in enumerate(rows[:limit]):
        if i == 0 or e['count'] != rows[i - 1]['count']:
            rank = i + 1
        out.append({'rank': rank, 'tied': counts[e['count']] > 1, **e,
                    'last_season_label': season_label(e['last_season'])})
    return out


def build_output(records, current_season, games_scanned, replay_dir=REPLAY_DIR, generated=None):
    all_rows = finish_rows([dict(r) for r in _newest_first(records)], replay_dir)
    return {
        'generated': generated or date.today().isoformat(),
        'seasons': season_span(records),
        'current_season': current_season,
        'games_scanned': games_scanned,
        'window_seconds': WINDOW_SECONDS,
        'all': all_rows,
        'buzzer_beaters': [r for r in all_rows if r['buzzer']],
        'leaders': leaders(records),
    }
