# One Player-Name Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every player name on the site is written one way — "Sasha Vezenkov" where there's room, "S. Vezenkov" when narrow or on phones, surname inside charts — through one shared formatter.

**Architecture:** New `docs/names.js` exposes one global `PlayerNames` (full/short/surname/responsiveHtml/chartLabels/matches) and a Node export for tests; every page loads it right before `nav.js`. `PlayerLinks.link` without a label renders the responsive name. Page scripts replace their own formatters and inline name splitting with these functions.

**Tech Stack:** vanilla JS (no build step, no deps), Node 21 test runner, pytest static tests.

**Spec:** `superpowers/specs/2026-11-18-name-format-design.md` — read it (incl. "Builder-check calls") before any task.

## Global Constraints

- Data stays `"LAST, FIRST"` uppercase; lookups, links and sort keys keep using the raw name.
- All names inserted into HTML are escaped; text-only sites (options, inputs, titles, textContent, SVG/Plotly labels) use plain strings with no phone swap.
- Forms: responsive (full desktop / short ≤640px) where there's room; short in narrow places and legends; chart labels via `chartLabels` (surname, short on collision); tooltips/hover/options/titles/inputs full.
- Search boxes that match names accept raw and full forms: token-prefix, any order, accent-insensitive.
- No page script defines `formatName`, `formatPlayerName` or `_cleanName` (only names.js formats names).
- Every page with the nav placeholder loads `<script src="names.js"></script>` immediately before `<script src="nav.js"></script>`.
- `docs/nav.js` stays one IIFE with no globals.
- Tests: `node --test tests/js/*.test.js`; `C:/Users/klalo/PycharmProjects/pythonProject/.venv/Scripts/python.exe -m pytest tests/ -q`.
- Branch `feat/name-format`; commit per task; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Phone width (390px)**: responsive names show the short form and tables don't overflow (Player Stats, MVP, Recap box score, Careers) — Tasks 2 and 3 screenshot checks.
2. **Typing the displayed form into a search box** ("Sasha Vezenkov", "sasha vez", "vezenkov") finds the player on Player Stats, Compare and Careers — Task 2 manual check.
3. **Names the rules get wrong** in current data (scan for `MC`, `MAC`, particles) render correctly via overrides — Task 1 data scan + test.
4. **Two players with the same surname in one chart** get distinct labels — Task 1 unit test (`chartLabels`) + Task 3 check.
5. **Pages where `PlayerNames` loads but a page script runs before it** (script order) — Task 1 static test.

---

### Task 1: `names.js`, wiring, nav and PlayerLinks default

**Files:** Create `docs/names.js`, `tests/js/names.test.js`; modify every `docs/*.html` with the nav placeholder (add the script tag before nav.js), `docs/nav.js` (use `PlayerNames.full` at render time, remove its `formatPlayerName`), `docs/player-links.js` (default label = responsive name), `tests/js/player-links.test.js`, `tests/js/nav.test.js` (adjust any `formatPlayerName` tests — they move to names.test.js), `docs/style.css` (`.pn-full`/`.pn-short` swap at `max-width: 640px`), `tests/test_nav_pages.py` or new `tests/test_names_pages.py`.

**Interfaces (produces):**
- Global `PlayerNames` (browser) and `module.exports = { full, short, surname, responsiveHtml, chartLabels, matches, OVERRIDES }` (Node):
  - `full(raw) -> string`, `short(raw) -> string`, `surname(raw) -> string` — rules per spec.
  - `responsiveHtml(raw) -> string` — `<span class="pn-full">…</span><span class="pn-short">…</span>`, both escaped.
  - `chartLabels(raws: string[]) -> string[]` — surname each; short for entries whose surnames collide in the set.
  - `matches(raw, query) -> boolean` — every query token (accent/case-insensitive, apostrophes removed) is a prefix of some token of `raw` or `full(raw)`; empty query → true.
- `PlayerLinks.link(name, label?, ids?, extraClass?)`: when `label` is `undefined`, anchor text = `PlayerNames.responsiveHtml(name)` if `PlayerNames` exists, else escaped `name`. Explicit labels unchanged.

- [ ] **Step 1: Failing tests** `tests/js/names.test.js` with the spec's cases: `full('VEZENKOV, SASHA')` "Sasha Vezenkov"; `short` "S. Vezenkov"; `surname` "Vezenkov"; `MILLER-MCINTYRE, CODI` → "Codi Miller-McIntyre" / "C. Miller-McIntyre"; `HAYES-DAVIS, NIGEL` → "Nigel Hayes-Davis"; `BRISSETT, O'SHAE J` → "O'Shae J Brissett"; `CLARK III, JIMMY` → "Jimmy Clark III" / "J. Clark III"; `BACOT JR., ARMANDO` → "Armando Bacot Jr."; `DE COLO, NANDO` → "Nando De Colo"; no-comma `"NEDOVIC"` → "Nedovic"; an OVERRIDES entry wins; `''`/`null` → `''`; `responsiveHtml('A<B, C')` contains `&lt;` and both classes; `chartLabels(['CLARK, JIMMY','CLARK, IAN','VEZENKOV, SASHA'])` → `['J. Clark','I. Clark','Vezenkov']`; `matches('VEZENKOV, SASHA', 'sasha vez')`, `'vezenkov'`, `'VEZENKOV, SASHA'` true; `'luka'` false; `matches('DONČIĆ, LUKA','doncic')` true. In player-links tests: `link('VEZENKOV, SASHA')` with a `PlayerNames` global stub contains `pn-full`.
- [ ] **Step 2: Data scan for overrides:** list current names (docs/data/current/player_index.json keys) where `full()` is likely wrong (`MAC`, all-caps particles like `VAN`/`DE`/`DA`/`DI`/`LA`/`LE`/`DEL`, `D'`), decide which need overrides, add only real players; note the list in the report.
- [ ] **Step 3: Implement** names.js (IIFE; one global; Node export), the CSS, nav.js render change, player-links default label; add the script tag to every page with the nav placeholder; static test: every such page loads `names.js` immediately before `nav.js`, and no `docs/*.js` other than names.js defines `function formatName`, `function formatPlayerName` or `_cleanName` (this test will FAIL until Tasks 2–3 remove them — mark it `xfail` with reason "removed in Tasks 2–3" and Task 3 removes the xfail).
- [ ] **Step 4: Run** both suites — PASS (one xfail).
- [ ] **Step 5: Commit** — `feat(names): shared PlayerNames formatter, nav and link defaults`.

---

### Task 2: Responsive names in tables, headers and searches

**Files:** `docs/players.js` (remove `_cleanName`, its uses; search/filter at ~120/~429/~581; compare pickers ~599), `docs/records.js`, `docs/shots.js` (paint table + detail; `<option>` text full), `docs/h2h.js`, `docs/team.js`, `docs/compare.js` (hero cards; search ~127 via `matches`; input value full), `docs/player.js` (title/header full; welcome search ~250 via `matches`; top performers via `PlayerLinks.link(name)`), `docs/recap.js` (remove `formatName`; box scores responsive), `docs/playoffs.js` (player tables), `docs/mvp.js` ladder + detail card (remove `formatName` once Task 3's legend use is also switched — coordinate: Task 2 switches ladder/detail to responsive; the function is deleted in Task 3).

**Interfaces:** Consumes Task 1's `PlayerNames.*` and `PlayerLinks.link(name)` default label.

- [ ] **Step 1: Implement** per the spec's per-page table: linked names → `PlayerLinks.link(rawName)` (no label) where they were linked; unlinked names in HTML → `PlayerNames.responsiveHtml(raw)`; text-only sites → `full()`; searches → `PlayerNames.matches`. Keep sort keys raw.
- [ ] **Step 2: Run** both suites — PASS.
- [ ] **Step 3: Verify** (local server at http://127.0.0.1:8765/ started by the controller; headless Chrome/CDP; evidence in the git-ignored SDD folder): desktop shows "Sasha Vezenkov", 390px shows "S. Vezenkov" with no horizontal overflow on Player Stats, Records, MVP ladder, Recap box score, Careers; Review Focus 2 on Player Stats, Compare and Careers searches; links still go to the right career pages; sorting unchanged.
- [ ] **Step 4: Commit** — `feat(names): responsive player names in tables, headers and searches`.

---

### Task 3: Short names, charts, remaining pages, docs

**Files:** `docs/lineups.js` (short), `docs/network.js` (tables short incl. top target; chord labels via `chartLabels`; remove `formatPlayerName`; `#pd-name`/title full), `docs/season.js` (MVP bars `chartLabels`; forecast card short; hovers full; remove inline splits), `docs/mvp.js` (timeline legend short; hovers full; delete `formatName`), `docs/app.js` (WPA bar labels short), `docs/gci-history.js` (pills `chartLabels`), and any other player-name site found by grepping `docs/*.js` for inline name splitting (`split(',')`/`split(', ')` on player names) — series.js, game-control.js, title-race.js, pace.js included if they show names; `tests/` (remove the xfail from Task 1's static test); `CLAUDE.md` Frontend line.

**Interfaces:** Consumes Task 1's `PlayerNames.*`.

- [ ] **Step 1: Implement**; grep for remaining inline name splitting and convert each.
- [ ] **Step 2: Remove the xfail**; run both suites — PASS.
- [ ] **Step 3: Verify:** Lineups and Playmaking show short names; MVP bars and chord labels show surnames, with a collision case showing short (find one in data or simulate on a temporary copy you revert); Replay WPA labels short; 390px on Lineups/Playmaking has no overflow; Playmaking chord click-to-pin and MVP chart clicks still work.
- [ ] **Step 4: Commit** — `feat(names): short names and chart labels across remaining pages; docs`.
