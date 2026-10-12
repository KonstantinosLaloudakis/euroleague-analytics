# Honest Odds Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Top 4 / Top 6 / Top 10 odds show "100%" or "0%" only when a team has mathematically clinched or been eliminated; otherwise they cap at ">99.9%" / "<0.1%" (Season Hub, one decimal) or ">99%" / "<1%" (Team page, whole numbers). The Team page's odds descriptions use the correct Euroleague meanings.

**Architecture:** `export_dashboard_data.py` gains a pure `clinch_status(wins, remaining)` that, from current wins and remaining games per team, marks each team clinched / eliminated for cutoffs 4, 6, 10 using a conservative rule (ties never count as clinched or eliminated). Each team object gets `clinched: {"4","6","10": bool}` and `eliminated: {...}`. `docs/constants.js` gains `fmtOdds(pct, clinched, eliminated, decimals)`; season.js and team.js use it. Old dashboards without the fields fall back to capping only.

**Tech Stack:** Python + pytest; vanilla JS + node-driven pytest (pattern from tests/test_team_colors.py).

**Spec:** Site audit 2026-10-12 finding #10 ("100%" shown for outcomes that aren't certain; display ">99%" unless mathematically locked). Found during investigation: team.js labels Top 4 "Double-bye", Top 6 "Home court", Top 10 "Qualify" — wrong for the Euroleague (Top 4 = home-court advantage in the playoff quarterfinals, Top 6 = direct playoff spot, Top 10 = play-in spot). User: "fix all of them, one at a time".

## Global Constraints

- Branch `fix/honest-odds-display`.
- Clinched top N: the number of *other* teams that can still reach **at least** this team's current wins (their wins + remaining ≥ this team's wins) is < N. Eliminated from top N: the number of other teams whose current wins are **strictly greater** than this team's maximum (wins + remaining) is ≥ N. Ties never clinch/eliminate (tiebreaks unknown in advance).
- Remaining games per team come from the RS schedule (unplayed RS fixtures), computed in the export; do not rely on `remaining` from adjusted_ratings (keep it as is for its own uses).
- Display rules (`fmtOdds(pct, clinched, eliminated, decimals)`): clinched → "100%"; eliminated → "0%"; else with d decimals: if pct ≥ 100 − 0.5·10^−d → ">" + (100 − 10^−d).toFixed(d) + "%"; if pct ≤ 0.5·10^−d → "<" + (10^−d).toFixed(d) + "%"; else pct.toFixed(d) + "%". (d=1 → ">99.9%", "<0.1%"; d=0 → ">99%", "<1%".)
- Season Hub table cell keeps its colour shading driven by the numeric value; Team page bar width keeps the numeric value.
- Never hardcode a season year; keep line endings.

## Review Focus

1. A team at 99.97% that hasn't clinched shows ">99.9%" (Season Hub) and ">99%" (Team page).
2. A clinched team shows "100%" even if the simulation said 99.8%; an eliminated team shows "0%".
3. 0.0% from the simulation but not eliminated shows "<0.1%".
4. Old dashboards (no `clinched`/`eliminated`) still render, capped.
5. Sorting the Season Hub table by Top 4% still sorts numerically.

---

### Task 1: `clinch_status` in the export

**Files:** `export_dashboard_data.py` (new function above `def compute_championship_finals_history():`; wire into `main()` where team objects are built / after `official_standings` sort), `tests/test_clinch_status.py`

**Interfaces — Produces:** `clinch_status(wins: dict[str,int], remaining: dict[str,int], cutoffs=(4, 6, 10)) -> dict[str, dict]` returning `{code: {'clinched': {'4': bool, '6': bool, '10': bool}, 'eliminated': {...}}}`.

- [ ] **Step 1: Branch** — `git checkout -b fix/honest-odds-display`
- [ ] **Step 2: Failing tests** — `tests/test_clinch_status.py`:

```python
"""Mathematical clinch / elimination for Top 4/6/10 (ties never decide)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import clinch_status


def _teams(n, wins, remaining):
    codes = [f'T{i:02d}' for i in range(n)]
    return dict(zip(codes, wins)), dict(zip(codes, remaining))


def test_nothing_decided_early():
    w, r = _teams(20, [4, 4] + [2] * 18, [34] * 20)
    s = clinch_status(w, r)
    assert not any(s[t]['clinched'][k] or s[t]['eliminated'][k] for t in s for k in ('4', '6', '10'))


def test_clinched_when_fewer_than_n_can_catch_up():
    # T00 has 30 wins; only 3 others can still reach 30 → clinched top 4 (and 6, 10)
    w, r = _teams(20, [30, 28, 28, 28] + [20] * 16, [2, 2, 2, 2] + [2] * 16)
    s = clinch_status(w, r)
    assert s['T00']['clinched'] == {'4': True, '6': True, '10': True}


def test_tie_possible_is_not_clinched():
    # 4 others can reach exactly T00's wins → not clinched top 4
    w, r = _teams(20, [30, 28, 28, 28, 28] + [10] * 15, [0, 2, 2, 2, 2] + [0] * 15)
    s = clinch_status(w, r)
    assert s['T00']['clinched']['4'] is False
    assert s['T00']['clinched']['6'] is True


def test_eliminated_when_n_teams_already_above_max():
    # T19 max = 12; 10 teams already have more than 12 → eliminated from top 10
    w, r = _teams(20, [20] * 10 + [10] * 9 + [10], [0] * 19 + [2])
    s = clinch_status(w, r)
    assert s['T19']['eliminated']['10'] is True
    assert s['T19']['eliminated']['4'] is True


def test_equal_to_max_is_not_eliminated():
    # 10 teams have exactly T19's max → not eliminated (tiebreak could favour T19)
    w, r = _teams(20, [12] * 10 + [5] * 9 + [10], [0] * 19 + [2])
    s = clinch_status(w, r)
    assert s['T19']['eliminated']['10'] is False
```

- [ ] **Step 3:** run → ImportError.
- [ ] **Step 4: Implement** (above `def compute_championship_finals_history():`):

```python
def clinch_status(wins, remaining, cutoffs=(4, 6, 10)):
    """Which teams have mathematically clinched / been eliminated from each
    top-N cutoff. Conservative: a possible tie never clinches or eliminates
    (tiebreakers can't be known in advance)."""
    out = {}
    for t in wins:
        w, max_w = wins[t], wins[t] + remaining.get(t, 0)
        can_catch = sum(1 for o in wins if o != t and wins[o] + remaining.get(o, 0) >= w)
        already_above = sum(1 for o in wins if o != t and wins[o] > max_w)
        out[t] = {
            'clinched': {str(n): can_catch < n for n in cutoffs},
            'eliminated': {str(n): already_above >= n for n in cutoffs},
        }
    return out


```

- [ ] **Step 5:** tests pass.
- [ ] **Step 6: Wire into `main()`** — right after the block that sets `position` / `rank_history` / `record_history` and sorts `teams`, add:

```python
    # Mathematical clinch / elimination (for honest 100% / 0% display)
    rs_remaining = {}
    for row in load_json(f'schedule_{S}.json') or []:
        if row.get('round') == 'RS' and str(row.get('played', '')).lower() != 'true':
            for key in ('homecode', 'awaycode'):
                rs_remaining[row.get(key)] = rs_remaining.get(row.get(key), 0) + 1
    status = clinch_status({t['team']: t['wins'] for t in teams},
                           {t['team']: rs_remaining.get(t['team'], 0) for t in teams})
    for t in teams:
        t['clinched'] = status[t['team']]['clinched']
        t['eliminated'] = status[t['team']]['eliminated']
```

(If schedule codes might differ from team codes, map with `team_aliases.team_code(row['hometeam'], default=row['homecode'])` as `official_standings` does — reuse the same approach.)

- [ ] **Step 7:** Full suite; commit `feat: mathematical clinch / elimination status per team in the export`.

---

### Task 2: `fmtOdds` + Season Hub and Team page + labels

**Files:** `docs/constants.js` (append), `docs/season.js` (`pctCell` ~line 164 and its 3 callers ~154–156), `docs/team.js` (`renderPlayoffOdds` ~309), `tests/test_fmt_odds.py`

- [ ] **Step 1: Failing test** — `tests/test_fmt_odds.py` (same node harness as tests/test_team_colors.py: stub `document`, strip `'use strict'`, `const`/`let` → `var`, eval docs/constants.js; skip when node is missing; `check=False` + assert returncode with stderr). Assert:
  - `fmtOdds(99.97, false, false, 1)` → `">99.9%"`; `fmtOdds(99.97, false, false, 0)` → `">99%"`
  - `fmtOdds(99.8, true, false, 1)` → `"100%"`; `fmtOdds(0.3, false, true, 0)` → `"0%"`
  - `fmtOdds(0, false, false, 1)` → `"<0.1%"`; `fmtOdds(0.04, false, false, 1)` → `"<0.1%"`; `fmtOdds(0.4, false, false, 0)` → `"<1%"`
  - `fmtOdds(43.4, false, false, 1)` → `"43.4%"`; `fmtOdds(43.4, false, false, 0)` → `"43%"`
  - `fmtOdds(100, undefined, undefined, 1)` → `">99.9%"` (old dashboard, no flags)

- [ ] **Step 2: Implement** — append to `docs/constants.js`:

```javascript
// Probability text that never claims certainty the maths doesn't support:
// "100%"/"0%" only when clinched/eliminated, otherwise capped at >99.9% / <0.1%.
function fmtOdds(pct, clinched, eliminated, decimals) {
    const d = decimals == null ? 1 : decimals;
    if (clinched) return '100%';
    if (eliminated) return '0%';
    const step = Math.pow(10, -d);
    const v = Number(pct) || 0;
    if (v >= 100 - step / 2) return '>' + (100 - step).toFixed(d) + '%';
    if (v <= step / 2) return '<' + step.toFixed(d) + '%';
    return v.toFixed(d) + '%';
}
```

- [ ] **Step 3: Season Hub** — `pctCell(val, color)` → `pctCell(val, color, clinched, eliminated)`: keep the numeric shading from `val`, replace the text `${val.toFixed(1)}%` with `${fmtOdds(val, clinched, eliminated, 1)}`; add `title="Clinched"` / `title="Eliminated"` when applicable. Callers pass `(t.clinched || {})['4']`, `(t.eliminated || {})['4']` (and '6', '10').

- [ ] **Step 4: Team page** — in `renderPlayoffOdds`: keep `const pct = Math.round(item.pct || 0)` for the bar width/colour; display `fmtOdds(item.pct, clinched, eliminated, 0)` where `clinched = (team.clinched || {})[item.key]` etc. (add `key: '4' | '6' | '10'` to the items). Change the descriptions: Top 4 → `'Home-court advantage in the playoffs'`, Top 6 → `'Direct playoff spot'`, Top 10 → `'Play-in spot (7–10) or better'`.

- [ ] **Step 5:** tests pass; `node --check` the three JS files; full suite; commit `fix: odds never show 100%/0% unless clinched/eliminated; correct Top 4/6/10 meanings`.

---

### Task 3: Regenerate + verify

- [ ] `EUROLEAGUE_ROUND_SUFFIX=_R4 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe export_dashboard_data.py`; every team has `clinched` / `eliminated` with keys '4','6','10' (all False at Round 4).
- [ ] Browser (serve docs; no-cache): Season Hub table shows no "100.0%"/"0.0%" text (PAN Top 10 shows ">99.9%" if its value ≥ 99.95, else its number); sorting by Top 4% still numeric; Team page (Panathinaikos) shows the new descriptions and no "100%" unless clinched. No console errors besides Cloudflare/favicon on localhost.
- [ ] About page: if `docs/about.html` describes Top 4/6/10 meanings or the odds display, align it (Top 4 home court, Top 6 direct playoffs, 7–10 play-in; ">99.9%" until clinched).
- [ ] pytest; commit regenerated `docs/data/current/*.json` (+ about.html if changed): `chore: regenerate dashboard with clinch status`.
