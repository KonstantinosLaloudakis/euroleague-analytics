# Early-Season Empty States Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Early in the season (before Round 5) the Player Stats leaderboard must list players instead of "No players match your filters", and every MVP view must explain why it is empty instead of rendering a blank box.

**Architecture:** Frontend only. The export already includes every player with `gp >= min(5, max(1, round))` (`export_dashboard_data.py:203`); the leaderboard's default "Min GP" filter now uses that same threshold. MVP scores require 5 games (`calculate_mvp_scores.py:60`), so the MVP list is empty before then; a shared `mvpPendingHTML(round)` helper in `docs/constants.js` renders one consistent message in the three MVP views.

**Tech Stack:** Vanilla JS (no build step), static HTML.

**Spec:** Site audit 2026-10-12 finding #6 ("Player Stats defaults to Min 5 GP → 'No players match your filters' with 182 players available; MVP Ladder and Season Hub MVP panel are empty with no explanation"). User: "fix all of them, one at a time, start with 6".

## Global Constraints

- Work on branch `fix/early-season-empty-states`.
- Keep the 5-game MVP rule (an MVP ranking after 4 games is noise) — only the presentation changes.
- From Round 5 on, the pages must behave exactly as today (Min 5 GP default; MVP views render normally).
- Keep each file's existing line endings (check with `file`).
- No new dependencies; scripts load `constants.js` before the page script (already true for index.html, players.html, mvp.html).

## Review Focus

1. Round ≥ 5: the leaderboard default stays "Min 5 GP" and no extra option is added — Task 1 Step 4 check.
2. Round 1 (threshold 1): option reads "Min 1 GP" — covered by the helper's `Math.max(1, …)`.
3. `data.round` missing/0: treat as threshold 1 for the leaderboard; MVP message omits the round number.
4. User changes the filter to Min 10 GP early in the season: "No players match your filters" is correct there and stays.
5. Season Hub MVP panel must not keep a 420px blank chart area when the list is empty.

---

### Task 1: Leaderboard default filter + MVP empty states

**Files:**
- Modify: `docs/constants.js` (append helpers)
- Modify: `docs/players.js` (boot block ~lines 18–64; `renderMvpRace` ~line 195)
- Modify: `docs/mvp.js` (`init` ~line 20, `renderLadder` ~line 75, `renderRaceChart` ~line 276)
- Modify: `docs/season.js` (`renderMVPRace` ~line 286)

- [ ] **Step 1: Create the branch**

```bash
git checkout -b fix/early-season-empty-states
```

- [ ] **Step 2: Shared helpers** — append to `docs/constants.js`:

```javascript
// MVP scores need MVP_MIN_GP games (calculate_mvp_scores.py); before that
// the MVP list is empty and pages show this message instead.
const MVP_MIN_GP = 5;
function mvpPendingHTML(round) {
    const now = round ? ` We're at Round ${round}.` : '';
    return `<p class="empty-state" style="color:var(--text-muted);text-align:center;padding:2rem 1rem">` +
        `The MVP race opens once players have ${MVP_MIN_GP} games — after Round ${MVP_MIN_GP}.${now}</p>`;
}
// The export lists players with at least min(5, round) games; the
// leaderboard's default filter uses the same threshold.
function defaultMinGP(round) {
    return Math.min(5, Math.max(1, round || 0));
}
```

- [ ] **Step 3: Player Stats** — in `docs/players.js`:

(a) Add a module-level `let _round = 0;` next to the other `let _…` declarations at the top of the file.

(b) In the boot `.then(data => {` block, right after `_rapmData = data.rapm || [];`, add:

```javascript
        _round = data.round || 0;

        // Early season the export only has players with < 5 games: default
        // the GP filter to the export's threshold so the table isn't empty.
        const minSel = document.getElementById('lb-mingp');
        const minGP0 = defaultMinGP(_round);
        if (minSel && minGP0 < 5) {
            const o = document.createElement('option');
            o.value = String(minGP0);
            o.textContent = `Min ${minGP0} GP`;
            minSel.insertBefore(o, minSel.firstChild);
            minSel.value = String(minGP0);
        }
```

(c) In `_renderLeaderboard`, change the fallback `'5'` in `parseInt(document.getElementById('lb-mingp')?.value || '5', 10)` to `String(defaultMinGP(_round))`.

(d) At the very top of `renderMvpRace(mvpList, playerStats)`, add:

```javascript
    if (!mvpList.length) {
        document.getElementById('mvp-podium').innerHTML = mvpPendingHTML(_round);
        return;
    }
```

Then check what else `renderMvpRace` writes (the full rankings table container after the podium). If returning early leaves a table header or a "Loading…" spinner visible in that container, clear it too (set its `innerHTML = ''` or hide its wrapper) inside the same `if` block, and note in the report which element you cleared.

- [ ] **Step 4: Check the leaderboard default logic** — run:

```bash
node -e "
eval(require('fs').readFileSync('docs/constants.js','utf8').replace(/^const /gm,'var '));
for (const r of [0,1,4,5,12]) console.log(r, defaultMinGP(r));
console.log(mvpPendingHTML(4)); console.log(mvpPendingHTML(0));
"
```
Expected: `0 1`, `1 1`, `4 4`, `5 5`, `12 5`; the first message contains "We're at Round 4.", the second does not contain "Round 0". (If `node` is not available, say so and rely on Task 2's browser check.)

- [ ] **Step 5: MVP page** — in `docs/mvp.js`:

(a) Add `let _round = 0;` with the other module-level `let`s; in `init`, after `_raceData = data.mvp_race || [];` add `_round = data.round || 0;`.

(b) At the top of `renderLadder()` add:

```javascript
    if (!_mvpData.length) {
        document.querySelector('#mvp-table thead').innerHTML = '';
        document.getElementById('mvp-tbody').innerHTML =
            `<tr><td colspan="${MVP_COLS.length}">${mvpPendingHTML(_round)}</td></tr>`;
        return;
    }
```

(c) In `renderRaceChart()`, replace the empty-data message so that when `_mvpData` is also empty it shows the pending message:

```javascript
    if (!_raceData.length) {
        container.innerHTML = _mvpData.length
            ? '<p style="color:var(--text-muted);text-align:center;padding:2rem">No historical snapshots available.</p>'
            : mvpPendingHTML(_round);
        return;
    }
```

(d) If `renderLegend()` renders the colour legend for the breakdown bars, hide it when `_mvpData` is empty (`el.style.display = 'none'`), since there are no bars to explain.

- [ ] **Step 6: Season Hub** — in `docs/season.js`, change the start of `renderMVPRace(mvp)` from `if (!mvp.length) return;` to:

```javascript
    if (!mvp.length) {
        const el = document.getElementById('mvp-chart');
        if (el) { el.style.height = 'auto'; el.innerHTML = mvpPendingHTML(_seasonRound); }
        return;
    }
```

and, in the loader where `renderMVPRace(data.mvp || [])` is called (~line 21), set a module-level `let _seasonRound = 0;` (declare it at the top of the file) to `data.round || 0` just before that call.

- [ ] **Step 7: Syntax check**

Run: `node --check docs/constants.js docs/players.js docs/mvp.js docs/season.js` (skip with a note if node is unavailable).

- [ ] **Step 8: Commit**

```bash
git add docs/constants.js docs/players.js docs/mvp.js docs/season.js
git commit -m "fix: early-season Player Stats default filter and MVP empty states"
```

---

### Task 2: Browser verification + About page

**Files:**
- Modify: `docs/about.html` only if it states the leaderboard's minimum-games rule or the MVP 5-game rule in a way that is now inaccurate (search for "5 GP", "five games", "minimum"); otherwise no change.

- [ ] **Step 1:** Serve `docs/` (`.venv/Scripts/python.exe -m http.server 8765 --directory docs`, in the background) and check with a browser (current data is Round 4, `mvp` empty):
  - `players.html` — leaderboard lists players (expect ~182 rows available, default filter "Min 4 GP"); switching to "Min 10 GP" shows "No players match your filters"; the MVP Race tab shows the pending message (no spinner, no empty table).
  - `mvp.html` — ladder shows the pending message in the table, timeline shows the pending message, legend hidden.
  - `index.html` — "MVP Race — Top 10" card shows the pending message, no blank 420px area.
  - No console errors other than favicon / Cloudflare analytics on localhost.
  Stop the server afterwards.
- [ ] **Step 2:** Round ≥ 5 regression check without new data: in the browser console on `players.html`, run `defaultMinGP(5)` → 5 and confirm the `lb-mingp` options in `docs/players.html` are unchanged (5/10/15/20).
- [ ] **Step 3:** `.venv/Scripts/python.exe -m pytest tests/ -q` → all pass (frontend change, sanity only).
- [ ] **Step 4:** Commit `docs/about.html` if changed: `docs: about page reflects early-season MVP/leaderboard behaviour`.
