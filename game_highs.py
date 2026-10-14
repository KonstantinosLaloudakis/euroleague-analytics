"""
Game Highs: single-game player records rebuilt from play-by-play.

analyze_clean() turns a pbp_games.CleanGame into one stat line per player
(points, rebounds, assists, threes, PIR). build_output() ranks the top
lines per stat for docs/data/current/game_highs.json. Older logs record
made dunks/layups and blocked or missed layup attempts as separate play
types; they are counted like the modern ones.
"""
import os
from datetime import date

from pbp_games import REPLAY_DIR, finish_rows, mode_value, rank_by, season_span

OUT_PATH = os.path.join('docs', 'data', 'current', 'game_highs.json')
STATS = ('points', 'rebounds', 'assists', 'threes', 'pir')
CONTENT_KEYS = STATS + ('games_scanned', 'current_season')

SHOT_POINTS = {'2FGM': 2, 'DUNK': 2, 'LAYUPMD': 2, '3FGM': 3, 'FTM': 1}
REBOUNDS = {'D', 'O'}
PIR_PLUS = {'D', 'O', 'AS', 'ST', 'FV', 'RV'}          # rebounds, assists, steals, blocks, fouls drawn
MISSES = {'2FGA', '3FGA', 'FTA', '2FGAB', '3FGAB', 'LAYUPATT'}
FOULS = {'CM', 'OF', 'CMT', 'CMU', 'CMD', 'CMTI', 'C', 'B'}
PIR_MINUS = MISSES | FOULS | {'TO', 'AG'}             # + turnovers, shots blocked


def stat_line(play_types):
    """Play-type codes for one player in one game -> stat line."""
    points = sum(SHOT_POINTS.get(t, 0) for t in play_types)
    return {
        'points': points,
        'rebounds': sum(t in REBOUNDS for t in play_types),
        'assists': sum(t == 'AS' for t in play_types),
        'threes': sum(t == '3FGM' for t in play_types),
        'pir': (points + sum(t in PIR_PLUS for t in play_types)
                - sum(t in PIR_MINUS for t in play_types)),
    }


def analyze_clean(cg):
    """CleanGame -> one line per player with at least one event in the game."""
    rows = cg.rows[cg.rows['PID'].notna()]
    lines = []
    for pid, pr in rows.groupby('PID', sort=False):
        team = mode_value(pr['CODETEAM'])
        if team == cg.code_a:
            home, opp = True, cg.code_b
        elif team == cg.code_b:
            home, opp = False, cg.code_a
        else:
            continue
        team_pts, opp_pts = (cg.final_a, cg.final_b) if home else (cg.final_b, cg.final_a)
        lines.append({
            'season': cg.season, 'phase': cg.phase, 'round': cg.round, 'gamecode': cg.gamecode,
            'player': pid,
            'player_name': mode_value(pr['PLAYER']) if 'PLAYER' in pr else None,
            'team': team, 'opp': opp, 'home': home, 'won': home == cg.a_won,
            'final': f'{team_pts}-{opp_pts}', 'ot': cg.ot,
            'line': stat_line(pr['PT'].tolist()),
        })
    return lines


def build_output(lines, current_season, games_scanned, replay_dir=REPLAY_DIR, generated=None):
    out = {
        'generated': generated or date.today().isoformat(),
        'seasons': season_span(lines),
        'current_season': current_season,
        'games_scanned': games_scanned,
    }
    for stat in STATS:
        flat = [{**l, 'value': l['line'][stat]} for l in lines]
        out[stat] = finish_rows(rank_by(flat, 'value'), replay_dir)
    return out
