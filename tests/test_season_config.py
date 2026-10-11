import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import season_config


def test_defaults_to_2026(monkeypatch):
    monkeypatch.delenv('EUROLEAGUE_SEASON', raising=False)
    cfg = importlib.reload(season_config)
    assert cfg.CURRENT_SEASON == 2026
    assert cfg.ALL_SEASONS[0] == 2007 and cfg.ALL_SEASONS[-1] == 2026
    assert cfg.COMPLETED_SEASONS[-1] == 2025
    assert len(cfg.ALL_SEASONS) == 20


def test_env_override(monkeypatch):
    monkeypatch.setenv('EUROLEAGUE_SEASON', '2027')
    cfg = importlib.reload(season_config)
    assert cfg.CURRENT_SEASON == 2027
    assert cfg.COMPLETED_SEASONS[-1] == 2026
    monkeypatch.delenv('EUROLEAGUE_SEASON')
    importlib.reload(season_config)


def test_labels():
    assert season_config.season_label(2026) == '2026-27'
    assert season_config.season_label(2009) == '2009-10'
    assert season_config.season_label(2099) == '2099-00'
    assert season_config.season_code(2026) == 'E2026'
    assert season_config.season_label() == season_config.season_label(season_config.CURRENT_SEASON)
