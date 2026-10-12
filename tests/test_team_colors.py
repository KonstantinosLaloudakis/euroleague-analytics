"""Team colours used as text/marks on the dark theme stay readable."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), '..')
NODE = shutil.which('node')

SCRIPT = r"""
global.document = { addEventListener() {}, getElementById() { return null; } };
const fs = require('fs');
eval(fs.readFileSync(process.argv[1], 'utf8')
     .replace(/^\s*['"]use strict['"];?\s*$/m, '')
     .replace(/^const /gm, 'var ').replace(/^let /gm, 'var '));
const out = {};
for (const code of Object.keys(TEAM_COLORS).concat(['XXX'])) {
  const ink = teamInk(code), on = teamOnColor(code);
  out[code] = { raw: getTeamColor(code), ink, on,
    ink_c: contrastRatio(ink, '#1f2029'),
    raw_c: contrastRatio(getTeamColor(code), '#1f2029'),
    on_c: contrastRatio(on, getTeamColor(code)) };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def colors():
    if not NODE:
        pytest.skip('node not installed')
    res = subprocess.run([NODE, '-e', SCRIPT, os.path.join(ROOT, 'docs', 'constants.js')],
                         capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def test_ink_is_readable_on_dark_cards(colors):
    bad = {k: v for k, v in colors.items() if v['ink_c'] < 4.5}
    assert not bad, bad


def test_ink_is_hex6(colors):
    import re
    assert all(re.fullmatch(r'#[0-9a-f]{6}', v['ink']) for v in colors.values())


def test_readable_brand_colours_unchanged(colors):
    for code, v in colors.items():
        if v['raw_c'] >= 4.5:
            assert v['ink'] == v['raw'].lower(), code
        else:
            assert v['ink'] != v['raw'].lower(), code


def test_dark_teams_are_lightened(colors):
    for code in ('ULK', 'ASV', 'PAR', 'PRS', 'VIR'):
        assert colors[code]['ink'] != colors[code]['raw'].lower(), code


def test_badge_text_picks_better_contrast(colors):
    assert colors['BES']['on'] == '#111111'   # light grey badge → dark text
    assert colors['ASV']['on'] == '#ffffff'   # near-black badge → white text
    assert all(v['on_c'] >= 4.0 for v in colors.values())
