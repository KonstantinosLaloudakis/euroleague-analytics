"""
Game Pace: possessions per game and per 40 minutes from play-by-play.

analyze_clean() turns a pbp_games.CleanGame into one line per game with each
side's estimated possessions (FGA + 0.44 FTA - OREB + TO), their average, and
pace per 40 minutes. The feed labels every overtime as PERIOD 5, so overtimes
are counted from the running MINUTE column (OT1 ends at 46, OT2 at 51, ...).
Older logs record made dunks/layups and missed layup attempts as separate play
types; they are counted as field-goal attempts like the modern ones.
"""
import pandas as pd

REGULATION_PERIODS = 4
REGULATION_MINUTES = 40
OT_MINUTES = 5
OT1_END_MINUTE = 46          # MINUTE value that closes the first overtime
FTA_WEIGHT = 0.44

FGA_CODES = frozenset({'2FGM', '2FGA', '2FGAB', '3FGM', '3FGA', '3FGAB',
                       'DUNK', 'LAYUPMD', 'LAYUPATT'})
FTA_CODES = frozenset({'FTM', 'FTA'})


def overtimes(rows):
    """Number of overtime periods played (0 for a game decided in regulation)."""
    if rows['PERIOD'].max() <= REGULATION_PERIODS:
        return 0
    if 'MINUTE' not in rows:
        return 1
    last = pd.to_numeric(rows['MINUTE'], errors='coerce').max()
    if pd.isna(last):
        return 1
    return max(1, int((last - OT1_END_MINUTE) // OT_MINUTES) + 1)


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
