import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _root_glob(pattern):
    return glob.glob(os.path.join(ROOT, pattern))


def test_no_stale_round_files_in_root():
    # Round-suffixed outputs at root must belong to the current season only.
    # Right after archiving there are none; the 2026 pipeline recreates them.
    import season_config
    marker = os.path.join(ROOT, 'archive', str(season_config.CURRENT_SEASON - 1))
    assert os.path.isdir(marker), 'previous season archive folder missing'
    for f in _root_glob('oracle_forecast_round_*.json'):
        # any forecast present must be newer than the archive move
        assert os.path.getmtime(f) > os.path.getmtime(marker), f'stale forecast {f}'


def test_final_2025_dashboard_archived():
    path = os.path.join(ROOT, 'docs', 'data', 'archive', '2025', 'dashboard.json')
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
    assert d['round'] == 38
    assert d.get('series'), 'archived dashboard should contain 2025-26 playoff series'
