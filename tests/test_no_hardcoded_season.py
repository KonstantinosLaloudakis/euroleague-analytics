"""Pipeline scripts must take the season from season_config."""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), '..')
ALLOWED = {'season_config.py', 'train_wp_model.py'}   # train: historical split


def _pipeline_scripts():
    src = open(os.path.join(ROOT, 'refresh_all.py'), encoding='utf-8').read()
    names = set(re.findall(r"['\"]([a-z_0-9]+\.py)['\"]", src))
    names |= {'refresh_all.py', 'fetch_all_seasons.py', 'incremental_fetch.py'}
    return sorted(n for n in names if os.path.exists(os.path.join(ROOT, n)))


def test_no_literal_current_years():
    offenders = []
    for name in _pipeline_scripts():
        if name in ALLOWED:
            continue
        for i, line in enumerate(open(os.path.join(ROOT, name), encoding='utf-8'), 1):
            code = line.split('#', 1)[0]
            if re.search(r'\b202[5-9]\b', code):
                offenders.append(f'{name}:{i}: {line.strip()}')
    assert not offenders, '\n'.join(offenders)
