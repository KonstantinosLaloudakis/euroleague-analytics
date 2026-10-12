"""Playoff forecasts are only exported once the regular season is complete."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import regular_season_complete


def _rows(played_flags, extra=()):
    rows = [{'round': 'RS', 'played': p} for p in played_flags]
    return rows + list(extra)


def test_incomplete_regular_season():
    assert not regular_season_complete(_rows(['true'] * 40 + ['false'] * 340))


def test_complete_regular_season():
    assert regular_season_complete(_rows(['true'] * 380))


def test_unplayed_playoff_rows_do_not_block():
    assert regular_season_complete(_rows(['true'] * 380, [{'round': 'PO', 'played': 'false'}]))


def test_missing_or_empty_schedule_is_not_complete():
    assert not regular_season_complete(None)
    assert not regular_season_complete([])


def test_played_flag_case_and_bool():
    assert regular_season_complete(_rows(['True', True, 'TRUE']))
