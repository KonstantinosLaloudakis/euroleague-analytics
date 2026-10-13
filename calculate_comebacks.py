"""
Biggest Comebacks: the largest deficits overcome by the eventual winner.

analyze_clean() takes a pbp_games.CleanGame and returns the winner's worst
confirmed deficit, overall and in Q4/OT only. build_output() ranks three
lists for docs/data/current/comebacks.json: overall, fourth_quarter and
postseason (Playoffs, Play-In, Final Four).
"""
import os
from datetime import date

import pandas as pd

from pbp_games import (GLITCH_TOL, LAST_REGULATION_PERIOD, REPLAY_DIR, TOP_N, clean_game,
                       finish_rows, iter_games, rank_by, season_span, write_json_if_changed)
from season_config import CURRENT_SEASON

OUT_PATH = os.path.join('docs', 'data', 'current', 'comebacks.json')
POSTSEASON = {'PO', 'PI', 'FF'}
NO_DEFICIT = {'deficit': 0, 'trailing': None, 'quarter': None, 'clock': None}
CONTENT_KEYS = ('overall', 'fourth_quarter', 'postseason', 'games_scanned', 'current_season')


def _confirmed_margins(margins):
    """Zero out margins no neighbouring play agrees with (single-row score typos)."""
    out = []
    for i, m in enumerate(margins):
        nbrs = margins[max(i - 1, 0):i] + margins[i + 1:i + 2]
        out.append(m if any(abs(m - x) <= GLITCH_TOL for x in nbrs) else 0)
    return out


def analyze_game(g):
    """One game's raw PBP rows -> comeback record, or None if the game is unusable."""
    cg = clean_game(g)
    return None if cg is None else analyze_clean(cg)


def analyze_clean(cg):
    """CleanGame -> comeback record (worst confirmed deficit overall and in Q4/OT)."""
    w_pts, l_pts = (cg.a, cg.b) if cg.a_won else (cg.b, cg.a)
    conf = _confirmed_margins([w - l for w, l in zip(w_pts, l_pts)])

    def worst(indices):
        if not indices:
            return dict(NO_DEFICIT)
        i = min(indices, key=lambda j: (conf[j], j))
        if conf[i] >= 0:
            return dict(NO_DEFICIT)
        clk = cg.clocks[i]
        return {'deficit': -conf[i], 'trailing': f'{w_pts[i]}-{l_pts[i]}',
                'quarter': cg.periods[i], 'clock': None if pd.isna(clk) else str(clk)}

    return {
        'season': cg.season,
        'phase': cg.phase,
        'round': cg.round,
        'gamecode': cg.gamecode,
        'winner': cg.code_a if cg.a_won else cg.code_b,
        'winner_name': cg.name_a if cg.a_won else cg.name_b,
        'loser': cg.code_b if cg.a_won else cg.code_a,
        'loser_name': cg.name_b if cg.a_won else cg.name_a,
        'home': cg.a_won,
        **worst(list(range(len(conf)))),
        'q4': worst([i for i, p in enumerate(cg.periods) if p >= LAST_REGULATION_PERIOD]),
        'final': f'{max(cg.final_a, cg.final_b)}-{min(cg.final_a, cg.final_b)}',
        'ot': cg.ot,
    }


def rank_entries(records, limit=TOP_N):
    """Top `limit` by deficit (ties: newest first), each with rank and tied flag."""
    return rank_by(records, 'deficit', limit)


def _without_q4(r):
    return {k: v for k, v in r.items() if k != 'q4'}


def _with_q4(r):
    return {**_without_q4(r), **r['q4']}


def build_output(records, current_season, replay_dir=REPLAY_DIR, generated=None):
    return {
        'generated': generated or date.today().isoformat(),
        'seasons': season_span(records),
        'current_season': current_season,
        'games_scanned': len(records),
        'overall': finish_rows(rank_entries([_without_q4(r) for r in records]), replay_dir),
        'fourth_quarter': finish_rows(rank_entries([_with_q4(r) for r in records]), replay_dir),
        'postseason': finish_rows(rank_entries(
            [_without_q4(r) for r in records if r['phase'] in POSTSEASON]), replay_dir),
    }


def main():
    out = build_output([analyze_clean(cg) for cg in iter_games()], CURRENT_SEASON)
    write_json_if_changed(OUT_PATH, out, CONTENT_KEYS)
    print(f"Comebacks: {out['games_scanned']} games scanned -> {OUT_PATH}")
    if out['overall']:
        top = out['overall'][0]
        print(f"  Biggest: {top['winner']} over {top['loser']} "
              f"({top['season_label']}) from {top['deficit']} down")


if __name__ == '__main__':
    main()
