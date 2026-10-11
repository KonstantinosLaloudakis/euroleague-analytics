import ast
from collections import Counter

import pandas as pd
import numpy as np

FGA_TYPES = {'2FGM', '2FGA', '3FGM', '3FGA'}
TO_TYPES = {'TO'}
FTA_TYPES = {'FTM', 'FTA'}
OREB_TYPES = {'O'}


def parse_lineup(val):
    """Parse a lineup column value into a sorted tuple of player names."""
    if pd.isna(val):
        return None
    try:
        players = ast.literal_eval(val) if isinstance(val, str) else val
        if isinstance(players, list) and len(players) == 5 and len(set(players)) == 5:
            return tuple(sorted(players))
    except Exception:
        pass
    return None


def infer_team_a(game_df, teams):
    """Team whose baskets move POINTS_A (the home side in the Euroleague feed).

    Votes over every scoring event: a basket by team T that raises only
    POINTS_A means T is side A; one that raises only POINTS_B means the other
    team is. Returns None if the game has no usable scoring events.
    """
    teams = list(teams)
    if len(teams) != 2 or 'POINTS_A' not in game_df or 'POINTS_B' not in game_df:
        return None
    if 'NUMBEROFPLAY' in game_df:
        game_df = game_df.sort_values('NUMBEROFPLAY')
    pa = pd.to_numeric(game_df['POINTS_A'], errors='coerce')
    pb = pd.to_numeric(game_df['POINTS_B'], errors='coerce')
    votes = Counter()
    prev_a = prev_b = 0.0
    for team, a, b in zip(game_df['CODETEAM'], pa, pb):
        if pd.isna(a) and pd.isna(b):
            continue
        a = prev_a if pd.isna(a) else a
        b = prev_b if pd.isna(b) else b
        if team in teams:
            other = teams[1] if team == teams[0] else teams[0]
            if a > prev_a and b == prev_b:
                votes[team] += 1
            elif b > prev_b and a == prev_a:
                votes[other] += 1
        prev_a, prev_b = a, b
    return votes.most_common(1)[0][0] if votes else None


def order_lineup_cols(game_df, lineup_cols, home_code=None):
    """Return (col_a, col_b): the POINTS_A (home) team's lineup column first.

    CSV column order is first-appearance order across the season, not
    home/away, so it must not be trusted. Uses the known home team when
    `home_code` names one of the two columns, else infers it from scoring.
    """
    by_team = {c.replace('Lineup_', ''): c for c in lineup_cols}
    if len(by_team) != 2:
        return tuple(lineup_cols)
    team_a = home_code if home_code in by_team else infer_team_a(game_df, list(by_team))
    if team_a is None:
        return tuple(lineup_cols)
    team_b = next(t for t in by_team if t != team_a)
    return by_team[team_a], by_team[team_b]


def extract_stints(game_df, lineup_col_a, lineup_col_b):
    """
    Extract stints from a single game's play-by-play data.
    A stint = contiguous stretch where the same 10 players are on court.
    Returns list of stint dicts with lineup, points, and possession info.
    """
    team_a = lineup_col_a.replace('Lineup_', '')
    team_b = lineup_col_b.replace('Lineup_', '')

    game_df = game_df.sort_values('NUMBEROFPLAY').copy()

    # Forward-fill and clean scores
    for col in ['POINTS_A', 'POINTS_B']:
        if col in game_df.columns:
            game_df[col] = pd.to_numeric(game_df[col], errors='coerce')
            game_df[col] = game_df[col].ffill().fillna(0)

    stints = []
    prev_key = None
    cur_a = None
    cur_b = None
    start_score_a = 0.0
    start_score_b = 0.0
    last_a = 0.0
    last_b = 0.0
    stint_fga = 0
    stint_fta = 0
    stint_to = 0
    stint_oreb = 0

    for _, row in game_df.iterrows():
        la = parse_lineup(row.get(lineup_col_a))
        lb = parse_lineup(row.get(lineup_col_b))

        if la is None or lb is None:
            continue

        key = (la, lb)

        # Track running score
        sa = row.get('POINTS_A', np.nan)
        sb = row.get('POINTS_B', np.nan)
        if pd.notna(sa):
            last_a = float(sa)
        if pd.notna(sb):
            last_b = float(sb)

        if key != prev_key:
            # Flush previous stint
            if prev_key is not None:
                poss = stint_fga + 0.44 * stint_fta + stint_to - stint_oreb
                if poss >= 1:
                    stints.append({
                        'lineup_a': cur_a,
                        'lineup_b': cur_b,
                        'team_a': team_a,
                        'team_b': team_b,
                        'pts_a': last_a - start_score_a,
                        'pts_b': last_b - start_score_b,
                        'poss': max(poss, 1),
                    })

            # Start new stint
            prev_key = key
            cur_a, cur_b = la, lb
            start_score_a = last_a
            start_score_b = last_b
            stint_fga = 0
            stint_fta = 0
            stint_to = 0
            stint_oreb = 0

        # Count possession components
        pt = row.get('PLAYTYPE', '')
        if pt in FGA_TYPES:
            stint_fga += 1
        elif pt in FTA_TYPES:
            stint_fta += 1
        elif pt in TO_TYPES:
            stint_to += 1
        elif pt in OREB_TYPES:
            stint_oreb += 1

    # Final stint
    if prev_key is not None:
        poss = stint_fga + 0.44 * stint_fta + stint_to - stint_oreb
        if poss >= 1:
            stints.append({
                'lineup_a': cur_a,
                'lineup_b': cur_b,
                'team_a': team_a,
                'team_b': team_b,
                'pts_a': last_a - start_score_a,
                'pts_b': last_b - start_score_b,
                'poss': max(poss, 1),
            })

    return stints
