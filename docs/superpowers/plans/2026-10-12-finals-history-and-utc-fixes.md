# Finals History + UTC Timestamp Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three factual bugs on the public site: a non-final listed as the 2019-20 championship final, lead changes overcounted by one (and repeated tied scores double-counted) in the finals ranking, and local times labelled "UTC".

**Architecture:** `export_dashboard_data.compute_championship_finals_history()` stops treating "highest replay gamecode" as the final; it takes the highest Final Four (`Phase == 'FF'`) gamecode from `data_cache/pbp_{season}.csv` and skips seasons with no Final Four (2019-20, cancelled). Lead-change / tie counting moves into a pure helper with standard semantics. The finals header count becomes data-driven. Three JS files format timestamps in UTC.

**Tech Stack:** Python 3.12 + pandas + pytest; vanilla JS.

**Spec:** Site audit 2026-10-12, findings #3, #4, #5 (user: "do 3-5").

## Global Constraints

- Work on branch `fix/finals-history-utc`.
- Never hardcode a season year in pipeline scripts (`tests/test_no_hardcoded_season.py`).
- Python: `.venv/Scripts/python.exe`; tests: `.venv/Scripts/python.exe -m pytest tests/ -q`; prefix script runs with `PYTHONIOENCODING=utf-8`.
- Keep CRLF line endings in files that have them.
- `championship_finals_history` entry schema unchanged: `season, gamecode, home, away, home_name, away_name, home_score, away_score, winner, lead_changes, times_tied, max_deficit_overcome, has_replay`.
- Lead change = the leader switches from one team to the other (the first lead of the game is not a change). Times tied = the score becomes level after someone had led (0-0 at tip-off not counted; a level score repeated in consecutive timeline entries counts once).

## Review Focus

1. A season whose pbp file is missing must be skipped with a warning, not fall back to "highest gamecode" — test `test_final_gamecode_missing_pbp_returns_none`.
2. Third-place game: the final is the highest FF gamecode (third-place game has a lower code) — covered by `test_final_gamecode_picks_highest_ff`.
3. A tied score repeated in consecutive timeline entries counts as one tie — `test_game_flow_dedupes_repeated_scores`.
4. A wire-to-wire win has 0 lead changes — `test_game_flow_wire_to_wire`.
5. The finals header must not say a hardcoded number — Task 2 Step 1.

---

### Task 1: Correct championship finals (export) + lead-change counting

**Files:**
- Modify: `export_dashboard_data.py` (add two helpers above `def compute_championship_finals_history():` ~line 1511; replace the final-gamecode lookup and the lead-change/tie loop inside it)
- Create: `tests/test_championship_finals.py`

**Interfaces:**
- Produces: `championship_final_gamecode(season: int, pbp_dir: str = 'data_cache') -> int | None`; `game_flow(plays: list[tuple[int, int]]) -> tuple[int, int]` returning `(lead_changes, times_tied)`.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b fix/finals-history-utc
```

- [ ] **Step 2: Write the failing tests** — create `tests/test_championship_finals.py`:

```python
"""Championship finals history: correct final game and lead-change counting."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from export_dashboard_data import championship_final_gamecode, game_flow


def _write_pbp(tmp_path, season, rows):
    lines = ['Season,Phase,Round,Gamecode,POINTS_A,POINTS_B']
    lines += [f'{season},{ph},1,{gc},,' for ph, gc in rows]
    (tmp_path / f'pbp_{season}.csv').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def test_final_gamecode_picks_highest_ff(tmp_path):
    _write_pbp(tmp_path, 2018, [('RS', 240), ('PO', 256), ('FF', 257), ('FF', 258), ('FF', 259), ('FF', 260)])
    assert championship_final_gamecode(2018, str(tmp_path)) == 260


def test_final_gamecode_none_without_final_four(tmp_path):
    # 2019-20 was cancelled: regular season only
    _write_pbp(tmp_path, 2019, [('RS', 1), ('RS', 252)])
    assert championship_final_gamecode(2019, str(tmp_path)) is None


def test_final_gamecode_missing_pbp_returns_none(tmp_path):
    assert championship_final_gamecode(2011, str(tmp_path)) is None


def test_game_flow_wire_to_wire():
    assert game_flow([(2, 0), (4, 0), (4, 3), (6, 3)]) == (0, 0)


def test_game_flow_counts_switches_not_first_lead():
    # A leads, B leads, A leads → 2 changes; one tie after a lead
    assert game_flow([(2, 0), (2, 2), (2, 3), (5, 3)]) == (2, 1)


def test_game_flow_dedupes_repeated_scores():
    # 4-4 appears in two consecutive entries → one tie
    assert game_flow([(2, 0), (2, 2), (4, 2), (4, 4), (4, 4), (4, 6)]) == (1, 2)


def test_game_flow_ignores_opening_zero_zero():
    assert game_flow([(0, 0), (0, 2), (3, 2)]) == (1, 0)
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_championship_finals.py -q`
Expected: FAIL — `ImportError: cannot import name 'championship_final_gamecode'`.

- [ ] **Step 4: Add the helpers** — insert directly above `def compute_championship_finals_history():` in `export_dashboard_data.py`:

```python
def championship_final_gamecode(season, pbp_dir='data_cache'):
    """Gamecode of the season's championship final: the highest Final Four
    (Phase 'FF') gamecode in the play-by-play. None when the season had no
    Final Four (2019-20 was cancelled) or its pbp file is missing."""
    path = os.path.join(pbp_dir, f'pbp_{season}.csv')
    if not os.path.exists(path):
        return None
    pbp = pd.read_csv(path, usecols=['Phase', 'Gamecode'], low_memory=False)
    ff = pbp.loc[pbp['Phase'] == 'FF', 'Gamecode']
    return int(ff.max()) if len(ff) else None


def game_flow(plays):
    """(lead_changes, times_tied) for a sequence of (a, b) scores.
    A lead change is the leader switching sides (the first lead is not a
    change); a tie counts when the score becomes level after someone led.
    Consecutive identical scores are one moment."""
    lead_changes = times_tied = 0
    leader = 0          # +1 a leads, -1 b leads, 0 nobody has led yet
    prev = None
    for a, b in plays:
        if (a, b) == prev:
            continue
        prev = (a, b)
        if a == b:
            if leader != 0:
                times_tied += 1
            continue
        side = 1 if a > b else -1
        if leader != 0 and side != leader:
            lead_changes += 1
        leader = side
    return lead_changes, times_tied


```

Note: with this definition a tie followed by the same team retaking the lead is a tie but not a lead change.

- [ ] **Step 5: Use them in `compute_championship_finals_history`**

(a) Update the docstring line `(highest gamecode in docs/data/{season}/), compute lead changes / times` to `(the season's highest Final Four gamecode, see championship_final_gamecode), compute lead changes / times`.

(b) Replace

```python
        # Championship final = highest gamecode in the season directory
        gc_files = [
            f for f in os.listdir(season_dir)
            if f.endswith('.json') and f[:-5].isdigit()
        ]
        if not gc_files:
            continue
        final_gc = max(int(f[:-5]) for f in gc_files)
```

with

```python
        final_gc = championship_final_gamecode(season)
        if final_gc is None:
            print(f'  [INFO] championship finals {season}: no Final Four in pbp, skipping')
            continue
```

(c) Replace the whole `# ── Lead changes & times tied ──` block (from `lead_changes = 0` through the end of its `for a, b in plays:` loop, i.e. up to but not including `# ── Max deficit overcome by winner`) with:

```python
        # ── Lead changes & times tied ────────────────────────────────────
        lead_changes, times_tied = game_flow(plays)

```

The existing `path = os.path.join(season_dir, f'{final_gc}.json')` / load / `except` (warn + continue) stays, so a final without a replay file is skipped with a warning.

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass (121 + 7 new).

- [ ] **Step 7: Check the real output**

Run:
```bash
.venv/Scripts/python.exe -c "
import export_dashboard_data as e
r = e.compute_championship_finals_history()
print(len(r), sorted(x['season'] for x in r))
for x in r[:5]: print(x['season'], x['home'], x['away'], x['home_score'], x['away_score'], x['lead_changes'], x['times_tied'])
"
```
Expected: `18` seasons, 2007–2025 without 2019; no `BAS`/`BER` 2019 entry; the 2013 final (Maccabi–Real Madrid 98-86) at or near the top with lead changes one lower than before (previously 22).

- [ ] **Step 8: Commit**

```bash
git add export_dashboard_data.py tests/test_championship_finals.py
git commit -m "fix: championship finals history uses the real Final Four final; correct lead-change count

The 'highest replay gamecode' heuristic listed a 2019-20 regular-season
game as a final (that season was cancelled). Lead changes counted the
first lead as a change, and repeated tied scores were double-counted."
```

---

### Task 2: Data-driven finals header + UTC timestamps (frontend)

**Files:**
- Modify: `docs/playoffs.html:1009`, `docs/playoffs.js` (`renderChampionshipFinals`, ~line 1679)
- Modify: `docs/team.js:16`, `docs/players.js:30`, `docs/h2h.js:19`

- [ ] **Step 1: Finals header count** — in `docs/playoffs.html` change

```html
            <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:1rem">
                All 19 Euroleague championship finals ranked by lead changes — the most contested games at the top.
            </p>
```

to

```html
            <p id="championship-finals-desc" style="font-size:0.78rem;color:var(--text-muted);margin-bottom:1rem">
                Every Euroleague championship final ranked by lead changes — the most contested games at the top.
            </p>
```

In `docs/playoffs.js`, inside `renderChampionshipFinals`, directly after `    section.style.display = '';` add:

```javascript
    const desc = document.getElementById('championship-finals-desc');
    if (desc) desc.textContent = `All ${data.length} Euroleague championship finals since ${Math.min(...data.map(e => e.season))}-${String(Math.min(...data.map(e => e.season)) + 1).slice(-2)}, ranked by lead changes — the most contested games at the top.`;
```

- [ ] **Step 2: UTC timestamps** — in each of `docs/team.js:16`, `docs/players.js:30`, `docs/h2h.js:19` the line has the form

```javascript
... `Updated ${d.toLocaleDateString('en-GB', {day:'numeric',month:'short',year:'numeric'})} ${d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})} UTC`;
```

Add `timeZone:'UTC'` to both option objects so it reads:

```javascript
... `Updated ${d.toLocaleDateString('en-GB', {day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})} ${d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'})} UTC`;
```

(Keep each line's existing leading code — `el.textContent =` — exactly as it is; only the two option objects change.)

- [ ] **Step 3: Verify**

Run: `grep -c "timeZone:'UTC'" docs/team.js docs/players.js docs/h2h.js` → each `2`.
Run: `grep -rn "UTC\`" docs/*.js | grep -v "timeZone:'UTC'"` → no output (no other "UTC"-labelled local times).
Run: `node --check docs/playoffs.js docs/team.js docs/players.js docs/h2h.js` (skip if node is unavailable; say so).
Run: `grep -n "All 19" docs/playoffs.html` → no output.

- [ ] **Step 4: Commit**

```bash
git add docs/playoffs.html docs/playoffs.js docs/team.js docs/players.js docs/h2h.js
git commit -m "fix: show update times in UTC; finals header counts from data"
```

---

### Task 3: Regenerate and verify

- [ ] **Step 1:** `EUROLEAGUE_ROUND_SUFFIX=_R4 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe export_dashboard_data.py`
- [ ] **Step 2:** Check `docs/data/current/dashboard.json`: `championship_finals_history` has 18 entries, none with season 2019; `regular_season_complete` still `false`; team Top-4 sums still 400.
- [ ] **Step 3:** Serve `docs/` on port 8765 and check with a browser: playoffs.html finals section header reads "All 18 Euroleague championship finals since 2007-08…" with no 2019 entry; team.html / players.html / h2h.html show "Updated 12 Oct 2026 HH:MM UTC" matching the `updated` field's UTC time; no console errors besides favicon / analytics-on-localhost. Stop the server.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/ -q` → all pass.
- [ ] **Step 5:** Commit regenerated `docs/data/current/*.json` that changed: `chore: regenerate dashboard with corrected finals history`.
