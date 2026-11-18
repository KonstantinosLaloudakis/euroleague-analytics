"""
Game Pace: possessions per game and per 40 minutes from play-by-play.

analyze_clean() turns a pbp_games.CleanGame into one line per game with each
side's estimated possessions (FGA + 0.44 FTA - OREB + TO), their average, and
pace per 40 minutes. The feed labels every overtime as PERIOD 5, so overtimes
are counted from the running MINUTE column (OT1 ends at 46, OT2 at 51, ...).
Older logs record made dunks/layups and missed layup attempts as separate play
types; they are counted as field-goal attempts like the modern ones.
"""
import os
from collections import defaultdict
from datetime import date

import pandas as pd

from pbp_games import REPLAY_DIR, finish_rows
from season_config import season_label

REGULATION_PERIODS = 4
REGULATION_MINUTES = 40
OT_MINUTES = 5
OT_MINUTE_OFFSET = 41        # MINUTE runs 46, 51, ... at the ends of OT1, OT2, ...
FTA_WEIGHT = 0.44
EXTREMES_N = 5
OUT_PATH = os.path.join('docs', 'data', 'current', 'pace.json')
CONTENT_KEYS = ('league', 'teams', 'playoffs', 'extremes', 'current_season')
REGULAR_PHASES = ('RS', 'TS')

FGA_CODES = frozenset({'2FGM', '2FGA', '2FGAB', '3FGM', '3FGA', '3FGAB',
                       'DUNK', 'LAYUPMD', 'LAYUPATT'})
FTA_CODES = frozenset({'FTM', 'FTA'})


def overtimes(rows):
    """Number of overtime periods played (0 for a game decided in regulation).

    Counted from the running MINUTE column; without a usable one, from the
    number of Begin Period rows logged in PERIOD 5 or later.
    """
    if rows['PERIOD'].max() <= REGULATION_PERIODS:
        return 0
    last = (pd.to_numeric(rows['MINUTE'], errors='coerce').max()
            if 'MINUTE' in rows else float('nan'))
    if pd.isna(last):
        begins = ((rows['PT'] == 'BP') & (rows['PERIOD'] > REGULATION_PERIODS)).sum()
        return max(1, int(begins))
    return max(1, int(round((last - OT_MINUTE_OFFSET) / OT_MINUTES)))


def team_possessions(play_types):
    """One team's play-type codes for a game -> estimated possessions."""
    fga = play_types.isin(FGA_CODES).sum()
    fta = play_types.isin(FTA_CODES).sum()
    oreb = (play_types == 'O').sum()
    tov = (play_types == 'TO').sum()
    return float(fga + FTA_WEIGHT * fta - oreb + tov)


def analyze_clean(cg):
    """CleanGame -> one pace line, or None if either team code is unknown."""
    if cg.code_a is None or cg.code_b is None:
        return None
    team = cg.rows['CODETEAM'].astype(str).str.strip()
    home_poss = team_possessions(cg.rows.loc[team == cg.code_a, 'PT'])
    away_poss = team_possessions(cg.rows.loc[team == cg.code_b, 'PT'])
    ot = overtimes(cg.rows)
    minutes = REGULATION_MINUTES + OT_MINUTES * ot
    poss = (home_poss + away_poss) / 2
    return {
        'season': cg.season, 'phase': cg.phase, 'round': cg.round, 'gamecode': cg.gamecode,
        'home': cg.code_a, 'away': cg.code_b,
        'home_pts': cg.final_a, 'away_pts': cg.final_b,
        'home_poss': home_poss, 'away_poss': away_poss, 'poss': poss,
        'minutes': minutes, 'ot': ot,
        'pace40': poss * REGULATION_MINUTES / minutes,
    }


def _regular(games):
    return [g for g in games if g['phase'] in REGULAR_PHASES]


def _mean(values):
    values = list(values)
    return sum(values) / len(values)


def _rank_desc(values):
    """1 = largest; ties share the lower (better) rank."""
    return {k: 1 + sum(1 for o in values.values() if o > v) for k, v in values.items()}


def league_by_season(games):
    by_season = defaultdict(list)
    for g in _regular(games):
        by_season[g['season']].append(g)
    rows = []
    for season in sorted(by_season):
        gs = by_season[season]
        points = sum(g['home_pts'] + g['away_pts'] for g in gs)
        poss = sum(g['poss'] for g in gs)
        rounds = [g['round'] for g in gs if g['round'] is not None]
        rows.append({
            'season': int(season), 'season_label': season_label(season),
            'pace': round(_mean(g['pace40'] for g in gs), 2),
            'pts_per_game': round(points / (2 * len(gs)), 2),
            'ortg': round(100 * points / (2 * poss), 2),
            'games': len(gs),
            'last_round': int(max(rounds)) if rounds else None,
        })
    return rows


def champions(games):
    """Season -> winner of its highest-gamecode Final Four game (the final)."""
    finals = {}
    for g in games:
        if g['phase'] == 'FF' and (g['season'] not in finals
                                   or g['gamecode'] > finals[g['season']]['gamecode']):
            finals[g['season']] = g
    return {int(s): (g['home'] if g['home_pts'] > g['away_pts'] else g['away'])
            for s, g in finals.items()}


def team_seasons(games):
    champs = champions(games)
    by_season = defaultdict(list)
    for g in _regular(games):
        by_season[g['season']].append(g)
    rows = []
    for season in sorted(by_season):
        gs = by_season[season]
        league = _mean(g['pace40'] for g in gs)
        mine = defaultdict(list)       # team -> [(game, scored, allowed, opponent code)]
        for g in gs:
            mine[g['home']].append((g, g['home_pts'], g['away_pts'], g['away']))
            mine[g['away']].append((g, g['away_pts'], g['home_pts'], g['home']))
        pace = {t: _mean(x[0]['pace40'] for x in v) for t, v in mine.items()}
        rel = {t: p - league for t, p in pace.items()}
        adj = {t: _mean((x[0]['pace40'] - league) - rel[x[3]] for x in v) for t, v in mine.items()}
        rank, adj_rank = _rank_desc(pace), _rank_desc(adj)
        for t, v in sorted(mine.items()):
            poss = sum(x[0]['poss'] for x in v)
            scored, allowed = sum(x[1] for x in v), sum(x[2] for x in v)
            rows.append({
                'season': int(season), 'team': t,
                'pace': round(pace[t], 2), 'pace_rel': round(rel[t], 2),
                'adj_rel': round(adj[t], 2),
                'rank': rank[t], 'adj_rank': adj_rank[t], 'teams': len(mine),
                'gp': len(v), 'wins': sum(1 for x in v if x[1] > x[2]),
                'ortg': round(100 * scored / poss, 2),
                'drtg': round(100 * allowed / poss, 2),
                'net': round(100 * (scored - allowed) / poss, 2),
                'champion': bool(champs.get(season) == t),
            })
    return rows


def playoff_vs_regular(games):
    regular = {r['season']: r['pace'] for r in league_by_season(games)}
    po = defaultdict(list)
    for g in games:
        if g['phase'] == 'PO':
            po[g['season']].append(g['pace40'])
    return [{'season': int(s), 'season_label': season_label(s), 'regular': regular[s],
             'playoffs': round(_mean(po[s]), 2),
             'diff': round(round(_mean(po[s]), 2) - regular[s], 2)}
            for s in sorted(po) if s in regular]


def _game_row(g):
    row = {k: g[k] for k in ('season', 'phase', 'gamecode', 'home', 'away',
                             'home_pts', 'away_pts')}
    row.update(poss=round(g['poss'], 2), pace40=round(g['pace40'], 2), ot=int(g['ot']))
    return row


def extremes(games, n=EXTREMES_N):
    ordered = sorted(games, key=lambda g: (g['pace40'], g['season'], g['gamecode']))
    return {'slowest': [_game_row(g) for g in ordered[:n]],
            'fastest': [_game_row(g) for g in ordered[::-1][:n]]}


def build_output(games, current_season, replay_dir=REPLAY_DIR, generated=None):
    ex = extremes(games)
    return {
        'generated': generated or date.today().isoformat(),
        'current_season': current_season,
        'league': league_by_season(games),
        'teams': team_seasons(games),
        'playoffs': playoff_vs_regular(games),
        'extremes': {k: finish_rows(v, replay_dir) for k, v in ex.items()},
    }
