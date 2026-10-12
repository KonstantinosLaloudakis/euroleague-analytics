# Readable Team Colours Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every team name, code, line and marker drawn in a team colour is readable on the site's dark background, and every solid team-colour badge has readable text.

**Architecture:** Two helpers in `docs/constants.js`: `teamInk(code)` returns the team colour mixed toward white just enough to reach WCAG 4.5:1 contrast against the lightest dark surface (`--bg-card` #1f2029); `teamOnColor(code)` returns `#ffffff` or `#111111`, whichever contrasts more with the solid team colour. `getTeamColor` / `TEAM_COLORS` stay unchanged (brand colours for fills). Each page script switches **foreground** uses (text, borders used as accents, chart lines/markers/bars, SVG strokes/fills of marks on the page background) to `teamInk`, and **text on a solid team-colour fill** to `teamOnColor`.

**Tech Stack:** Vanilla JS, Plotly, inline SVG; pytest + node for a helper test.

**Spec:** Site audit 2026-10-12 finding #7: Fenerbahce, Partizan, ASVEL, Virtus Bologna, Paris (and similar dark colours) are unreadable as text on dark tiles/cards (team.html picker, finals list, tables). User: "fix all of them, one at a time".

## Global Constraints

- Branch `fix/readable-team-colors`.
- The site is dark-only (no light theme); reference background for contrast is `#1f2029`.
- Contrast targets: text and marks ≥ 4.5:1 vs `#1f2029` (via `teamInk`); badge text vs its solid team-colour background picks the better of white / `#111111` (via `teamOnColor`).
- Do not change `TEAM_COLORS` values or `getTeamColor` behaviour.
- Teams whose colour already passes keep their exact brand colour (`teamInk` returns it unchanged).
- Translucent tints (`${color}15`, `${color}22`, `${color}30` used as backgrounds/borders behind text) may keep the raw brand colour; the **text** on them must use `teamInk`.
- Keep each file's line endings. No new dependencies.

## Review Focus

1. A badge whose background is the solid raw colour and whose text is white: switch the text to `teamOnColor` (Besiktas #d9d9d9, Maccabi #F6C300 would otherwise be white-on-light).
2. Plotly traces: `line.color`, `marker.color`, bar `marker.color` arrays drawn on the dark plot area are foreground → `teamInk`.
3. Concatenating an alpha suffix to `teamInk(...)` output must still produce a valid 8-digit hex (`teamInk` always returns `#rrggbb`).
4. Unknown codes: `teamInk('XXX')` must work (falls back to the grey default).
5. Teams with already-readable colours must look exactly as before (e.g. PAM orange, TEL yellow keep their hex).

---

### Task 1: Colour helpers + test

**Files:**
- Modify: `docs/constants.js` (insert after `function getTeamColor(code) { … }`, ~line 119)
- Create: `tests/test_team_colors.py`

**Interfaces — Produces:** `teamInk(code) -> '#rrggbb'`, `teamOnColor(code) -> '#ffffff' | '#111111'`, `contrastRatio(hexA, hexB) -> number`.

- [ ] **Step 1: Branch** — `git checkout -b fix/readable-team-colors`

- [ ] **Step 2: Write the failing test** — create `tests/test_team_colors.py`:

```python
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
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_team_colors.py -q`
Expected: FAIL (node `ReferenceError: teamInk is not defined` → `CalledProcessError`).

- [ ] **Step 4: Add the helpers** — in `docs/constants.js`, directly after the `getTeamColor` line:

```javascript

// ── Readable team colours on the dark theme ────────────────────────────
// teamInk: brand colour lifted toward white just enough for 4.5:1 contrast
// on --bg-card (the lightest dark surface). Use for text, lines, markers.
// teamOnColor: text colour for a solid team-colour background (badges).
const INK_BG = '#1f2029';
function _rgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function _luminance(hex) {
    const [r, g, b] = _rgb(hex).map(v => {
        v /= 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrastRatio(a, b) {
    const [hi, lo] = [_luminance(a), _luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
}
function _towardWhite(hex, t) {
    return '#' + _rgb(hex)
        .map(v => Math.round(v + (255 - v) * t).toString(16).padStart(2, '0'))
        .join('');
}
const _inkCache = {};
function teamInk(code) {
    if (_inkCache[code]) return _inkCache[code];
    const base = getTeamColor(code).toLowerCase();
    let ink = base;
    for (let t = 0.05; contrastRatio(ink, INK_BG) < 4.5 && t <= 1.0001; t += 0.05) {
        ink = _towardWhite(base, Math.min(t, 1));
    }
    return (_inkCache[code] = ink);
}
function teamOnColor(code) {
    const bg = getTeamColor(code);
    return contrastRatio('#ffffff', bg) >= contrastRatio('#111111', bg) ? '#ffffff' : '#111111';
}
```

- [ ] **Step 5: Run the test** — `.venv/Scripts/python.exe -m pytest tests/test_team_colors.py -q` → 5 passed. Then print the table for the report: `node -e "<SCRIPT from the test with the eval path>"` or a one-off: for ULK, ASV, PAR, PRS, VIR, DUB, BAR, MUN, MAD, PAN, ZAL, BES, TEL print raw → ink.

- [ ] **Step 6: Full suite** — `.venv/Scripts/python.exe -m pytest tests/ -q` → all pass.

- [ ] **Step 7: Commit** — `git add docs/constants.js tests/test_team_colors.py && git commit -m "feat: teamInk / teamOnColor helpers for readable team colours"`

---

### Task 2: Apply to Season Hub, Team, Players, MVP, Playoffs, Title Race, Series

**Files:** `docs/season.js`, `docs/team.js`, `docs/players.js`, `docs/mvp.js`, `docs/playoffs.js`, `docs/title-race.js`, `docs/series.js`

- [ ] **Step 1:** In each file, find every use of `TEAM_COLORS[...]`, `getTeamColor(...)` and local variables holding them (`grep -n "TEAM_COLORS\|getTeamColor" <file>`, then follow each variable to where it is used). Classify each use:
  - **Foreground** — CSS `color:`; `border-color`/`border-left`/`border-top` used as an accent stripe or outline on the dark card; Plotly `line.color`, `marker.color` (including bar colour arrays), `font.color`, annotation colours; SVG `stroke`/`fill` of lines, dots, bars, text on the page background → replace with `teamInk(code)`.
  - **Text on a solid team fill** — an element whose `background`/`background-color`/SVG `fill` is the solid raw team colour and that contains text: keep the background raw; set the text colour to `teamOnColor(code)` (replace hardcoded `#fff`/`white`/`#ffffff` there).
  - **Translucent tint** — `${color}15|22|30|40` etc. used as background/border behind text: may stay raw; the text on it is foreground → `teamInk`.
  - **Logo images, gradients purely decorative behind nothing** — leave.
- [ ] **Step 2:** Make the replacements. Where a variable like `const color = TEAM_COLORS[t] || '#555'` feeds both a fill and a text colour, introduce a second variable (`const ink = teamInk(t)`) rather than changing the shared one.
- [ ] **Step 3:** `node --check` each changed file.
- [ ] **Step 4:** Write in the report a per-file list: line → old → new → category.
- [ ] **Step 5:** Commit: `fix: readable team colours on Season Hub, Team, Players, MVP, Playoffs, Title Race, Series`

---

### Task 3: Apply to H2H, Recap, Playmaking, Shot Lab, Game Control, GCI History, Compare

**Files:** `docs/h2h.js`, `docs/recap.js`, `docs/network.js`, `docs/shots.js`, `docs/game-control.js`, `docs/gci-history.js`, `docs/compare.js`

- [ ] **Steps 1–4:** identical procedure and categories to Task 2 Steps 1–4 (repeat them for these files). Also grep the matching `.html` files (`h2h.html recap.html network.html shots.html game-control.html gci-history.html compare.html`) for inline `<script>` blocks using `TEAM_COLORS`/`getTeamColor` and treat them the same way.
- [ ] **Step 5:** Commit: `fix: readable team colours on H2H, Recap, Playmaking, Shot Lab, Game Control, GCI History, Compare`

---

### Task 4: Browser verification

- [ ] **Step 1:** Serve `docs/` on 8765 (background) and, for each of: index.html, team.html (picker + one team detail, e.g. click "Fenerbahce"), players.html, playoffs.html (finals list), h2h.html, recap.html, network.html, shots.html, game-control.html, gci-history.html, title-race.html, series.html, mvp.html, compare.html — check no JS errors (other than Cloudflare analytics / favicon on localhost) and take a screenshot under `.playwright-mcp/`.
- [ ] **Step 2:** On team.html run in the page: for each tile, compute the text colour's contrast against `#1f2029` with `contrastRatio(getComputedStyle(el).color → hex, '#1f2029')` and report the minimum (expect ≥ 4.5).
- [ ] **Step 3:** Visually confirm in screenshots: Fenerbahce, Partizan, ASVEL, Virtus Bologna, Paris Basketball tile names readable; Besiktas / Maccabi badges with dark text where the badge is solid.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/ -q`. Stop the server. No commit unless a fix was needed (then commit it with a message naming the page).
