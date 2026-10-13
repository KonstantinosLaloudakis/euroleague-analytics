"""Tests for calculate_game_records.py (one pass, every analyzer)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import calculate_game_records as gr
import pbp_games as pg
from tests.pbp_fixtures import BASIC, build, ev, filler, game


def test_collect_runs_every_analyzer_once_per_game():
    g1 = pg.clean_game(game(BASIC))          # no player ids; ends with AWY's 50-50 tie-breaker at 0:10
    g2 = pg.clean_game(build(filler(25, 25, period=4)
                             + ev('B', '3FGM', 4, '00:01', player='P000009', name='SHOOTER, S'),
                             gamecode=8))
    comebacks, lines, winners = gr.collect([g1, g2])
    assert [c['gamecode'] for c in comebacks] == [7, 8]
    assert [l['player'] for l in lines] == ['000009']
    assert [w['gamecode'] for w in winners] == [7, 8]
