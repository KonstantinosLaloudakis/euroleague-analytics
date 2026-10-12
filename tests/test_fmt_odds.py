"""fmtOdds never claims certainty unless clinched/eliminated."""
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
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(c => fmtOdds(c[0], c[1], c[2], c[3]))));
"""

CASES = [
    ((99.97, False, False, 1), '>99.9%'),
    ((99.97, False, False, 0), '>99%'),
    ((99.8, True, False, 1), '100%'),
    ((0.3, False, True, 0), '0%'),
    ((0, False, False, 1), '<0.1%'),
    ((0.04, False, False, 1), '<0.1%'),
    ((0.4, False, False, 0), '<1%'),
    ((43.4, False, False, 1), '43.4%'),
    ((43.4, False, False, 0), '43%'),
    ((100, None, None, 1), '>99.9%'),
]


def test_fmt_odds():
    if not NODE:
        pytest.skip('node not installed')
    res = subprocess.run(
        [NODE, '-e', SCRIPT, os.path.join(ROOT, 'docs', 'constants.js'),
         json.dumps([list(c) for c, _ in CASES])],
        capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [exp for _, exp in CASES]
