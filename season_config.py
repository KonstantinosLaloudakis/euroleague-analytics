"""Single source of truth for which Euroleague season the pipeline processes.

Bump CURRENT_SEASON each autumn when the new season tips off, or set the
EUROLEAGUE_SEASON env var for a one-off run against another season.
Seasons are identified by their start year (2026 = 2026-27).
"""
import os

FIRST_SEASON = 2007
CURRENT_SEASON = int(os.environ.get('EUROLEAGUE_SEASON', '2026'))

ALL_SEASONS = list(range(FIRST_SEASON, CURRENT_SEASON + 1))
COMPLETED_SEASONS = list(range(FIRST_SEASON, CURRENT_SEASON))


def season_label(season=None):
    """2026 -> '2026-27'"""
    s = CURRENT_SEASON if season is None else season
    return f"{s}-{str(s + 1)[-2:]}"


def season_code(season=None):
    """2026 -> 'E2026' (API season code)"""
    s = CURRENT_SEASON if season is None else season
    return f"E{s}"
