"""refresh_all.py must run each compute step after the steps whose outputs it reads."""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _step_order():
    src = open(os.path.join(ROOT, 'refresh_all.py'), encoding='utf-8').read()
    return re.findall(r"['\"]([a-z_0-9]+\.py)['\"]", src)


def test_wpa_runs_before_mvp_scores():
    # calculate_mvp_scores.py reads this round's wpa_ratings_R{N}.json (25% of the
    # score). If WPA runs later, the first run of every round scores WPA as 0.
    order = _step_order()
    assert order.index('calculate_wpa.py') < order.index('calculate_mvp_scores.py')
