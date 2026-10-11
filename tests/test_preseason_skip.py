"""Before the first game there are no pbp/lineup CSVs: consumers skip cleanly."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import calculate_rapm
import calculate_wpa
import generate_clutch_data


def test_consumers_skip_without_csvs(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert not generate_clutch_data.main()
    assert calculate_wpa.calculate_action_wpa() is None
    assert calculate_rapm.calculate_rapm() is None
    out = capsys.readouterr().out
    assert out.count('skipping') == 3
    assert os.listdir(tmp_path) == []          # nothing written
