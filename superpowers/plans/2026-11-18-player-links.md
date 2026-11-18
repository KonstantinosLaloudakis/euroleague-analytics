# Player Names Link to Career Pages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every player name on the listed pages (and the MVP chart bars / timeline points) links to that player's career page, through one shared helper.

**Architecture:** New `docs/player-links.js` loads `data/current/player_index.json` once and exposes a single global `PlayerLinks` (`ready`, `url`, `link`); a factory is exported for Node unit tests. Pages await `PlayerLinks.ready` once at init, then wrap names with `PlayerLinks.link` or navigate with `PlayerLinks.url` from Plotly click handlers. A shared `.player-link` CSS class gives every player link the same hover/focus style.

**Tech Stack:** vanilla JS (no build step, no dependencies), Plotly (already loaded on chart pages), Node 21 test runner, pytest.

**Spec:** `superpowers/specs/2026-11-18-player-links-design.md` — read it before any task.

## Global Constraints

- Static GitHub Pages site from `docs/`; no build step, no new dependencies.
- `player_index.json` format must not change (normalized `"LAST, FIRST"` → career code; codes are digits like `"003469"` or letters like `"THY"`).
- A link is produced only when the code is one of the index's values (a career page exists); otherwise plain text. Never link to a missing page.
- Labels from data are HTML-escaped whether linked or not.
- `PlayerLinks` is the only new global; `docs/nav.js` stays global-free and unchanged.
- Existing click behavior must keep working: MVP ladder row click opens the detail card; Playmaking chord click pins a player; table header clicks sort.
- If `player_index.json` fails to load, names render as plain text and chart clicks do nothing — pages must still render.
- Pages await `PlayerLinks.ready` once at init (in parallel with their own data fetch); later renders call `link`/`url` synchronously.
- Each page using `PlayerLinks` loads `<script src="player-links.js"></script>` after `constants.js` and before its page script.
- Tests: `node --test tests/js/*.test.js`; `C:/Users/klalo/PycharmProjects/pythonProject/.venv/Scripts/python.exe -m pytest tests/ -q`.
- Work on branch `feat/player-links`; commit per task; commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Clicking a linked name inside a clickable MVP ladder row** must open the career page, not (or not also) the detail card — Task 3 manual check.
2. **`player_index.json` unreachable** (blocked/404): every page in scope still renders, names plain, chart clicks no-op, no console errors beyond the failed fetch — Tasks 2 and 3 manual check (temporarily rename the file locally; restore before committing).
3. **Labels containing HTML-significant characters** (`O'SHAE`, `&`, `<`) render as text — Task 1 node test.
4. **Re-renders after init** (Lineups season/team filter, Shot Lab tabs, Playmaking table sorts, Compare slot changes) keep their links — Task 2 manual check.
5. **Keyboard users**: Tab reaches each player link and the focus style is visible — Task 2 manual check.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/player-links.js` (create) | lookup + link HTML; `PlayerLinks` global; `createPlayerLinks` for Node |
| `tests/js/player-links.test.js` (create) | helper unit tests |
| `tests/test_player_links_pages.py` (create) | pages that use `PlayerLinks` load the helper first |
| `docs/style.css` (modify) | `.player-link` style |
| `docs/h2h.js`, `shots.js`, `network.js`, `lineups.js`, `compare.js` + their `.html` (modify) | table/list links (Task 2) |
| `docs/mvp.js`, `season.js`, `mvp.html`, `index.html` (modify) | MVP ladder/detail links + chart clicks (Task 3) |
| `docs/recap.js`, `recap.html`, `team.js`, `players.js`, `records.js`, `about.html`, `CLAUDE.md` (modify) | reuse + consistent style + docs (Task 4) |

---

### Task 1: `player-links.js` helper, style and guard test

**Files:** Create `docs/player-links.js`, `tests/js/player-links.test.js`, `tests/test_player_links_pages.py`; modify `docs/style.css` (append a `.player-link` rule near the nav section end).

**Interfaces:**
- Produces (used by Tasks 2–4):
  - Browser global `PlayerLinks` with:
    - `ready: Promise<void>` — resolves after `data/current/player_index.json` loads **or fails**; never rejects; fetched once on script load.
    - `url(name: string, ids?: {code?: string, apiId?: string}) -> string | null` — `'player.html?code=' + encodeURIComponent(code)`.
    - `link(name: string, label?: string, ids?: {code?, apiId?}) -> string` — `<a class="player-link" href="URL">ESCAPED_LABEL</a>` or `ESCAPED_LABEL`; `label` defaults to `name`.
  - Node: `module.exports = { createPlayerLinks }`, where `createPlayerLinks(index: object | null) -> {url, link}` builds an instance over a given index (no fetch). The browser global is built from the same factory once the index loads.
- Rules: id wins over name; `apiId` strips exactly one leading `P`; name normalized = uppercase, NFD diacritics stripped, trimmed (same as `normalize_name` in `fetch_player_career_stats.py`); a code (from id or name) yields a URL only if it is one of the index's values.

- [ ] **Step 1: Write failing tests** in `tests/js/player-links.test.js` using an inline index `{"VEZENKOV, SASHA": "003469", "BRISSETT, O'SHAE J": "014111", "DONCIC, LUKA": "THY"}`:
  - `url('VEZENKOV, SASHA')`, `url(' vezenkov, sasha ')` → `'player.html?code=003469'`; `url('Dončić, Luka')` → `'player.html?code=THY'`.
  - `url('X', {code: '003469'})` and `url('X', {apiId: 'P003469'})` → `'player.html?code=003469'`; `url('VEZENKOV, SASHA', {code: 'THY'})` → `…THY` (id wins).
  - `url('NOBODY, X')` → `null`; `url('VEZENKOV, SASHA', {code: '999999'})` → `null`; `url('X', {apiId: 'P999999'})` → `null`.
  - `link('VEZENKOV, SASHA', 'S. Vezenkov')` → `'<a class="player-link" href="player.html?code=003469">S. Vezenkov</a>'`.
  - `link("BRISSETT, O'SHAE J")` → anchor whose text is `BRISSETT, O&#39;SHAE J` (or `&#x27;`); `link('NOBODY, <B>')` → `'NOBODY, &lt;B&gt;'` (no anchor).
  - `createPlayerLinks(null)`: `url` → `null`, `link('A, B')` → `'A, B'`.
- [ ] **Step 2: Write** `tests/test_player_links_pages.py::test_pages_load_helper_before_use`: for each `docs/*.html`, for each local `<script src="X.js">` whose file contains `PlayerLinks`, `player-links.js` must be loaded earlier in that HTML. (Passes now — no page uses it yet; it guards Tasks 2–4.)
- [ ] **Step 3: Run** `node --test tests/js/*.test.js` — expect the new file to FAIL (module missing).
- [ ] **Step 4: Implement** `docs/player-links.js` and the `.player-link` CSS (inherit color, no underline; underline + accent color on `:hover` and `:focus-visible`).
- [ ] **Step 5: Run** both suites — PASS.
- [ ] **Step 6: Commit** — `feat(links): shared PlayerLinks helper and link style`.

---

### Task 2: Links in tables and lists

**Files:** `docs/h2h.js`, `docs/shots.js`, `docs/network.js`, `docs/lineups.js`, `docs/compare.js`, and the matching `docs/h2h.html`, `shots.html`, `network.html`, `lineups.html`, `compare.html` (script tag).

**Interfaces:** Consumes `PlayerLinks.ready/link` (Task 1).

Per page (spec "Per page" table is binding):
- `h2h.js` `renderPlayerComparison` (`.pc-name`): `PlayerLinks.link(p.name, p.name, {code: p.code})`.
- `shots.js` paint profiles Players tab: player cell (~line 475) and detail name (~line 560) via `PlayerLinks.link(p.player)`. Teams/Team Defense tabs unchanged.
- `network.js`: combos table passer/scorer with `{apiId: passer_id/scorer_id}`; playmakers table player with `{apiId: player_id}` and top target by name (column formatter at ~line 485 keeps `formatPlayerName` as the label). Chord diagram and tooltips unchanged.
- `lineups.js` (~line 121): each name linked separately, joined with `', '` as today.
- `compare.js`: a "View career" link next to each chosen player (`PlayerLinks.url(name, {code: slot._code})`), shown only when non-null.
- Each page: add the script tag; await `PlayerLinks.ready` once at init alongside its data fetch.

- [ ] **Step 1: Implement** the five pages.
- [ ] **Step 2: Run** both suites (the Task 1 guard test now covers these pages) — PASS.
- [ ] **Step 3: Verify** (local server on `http://127.0.0.1:8765/`, phone via `http://127.0.0.1:8766/m.html?<page>`): each page shows linked names with the hover style; spot-check 2 links per page open the right career page; Review Focus 2 (rename `docs/data/current/player_index.json` temporarily → names plain, pages render; restore it), Review Focus 4 (Lineups filters, Shot Lab tabs, Playmaking sort, Compare slot change keep links), Review Focus 5 (Tab reaches links, focus visible), Playmaking chord click still pins.
- [ ] **Step 4: Commit** — `feat(links): link player names in H2H, Shot Lab, Playmaking, Lineups, Compare`.

---

### Task 3: MVP Race page and Season Hub chart

**Files:** `docs/mvp.js`, `docs/mvp.html`, `docs/season.js`, `docs/index.html`.

**Interfaces:** Consumes `PlayerLinks.ready/url/link` (Task 1).

- `mvp.js` `renderLadder` (row `onclick="selectPlayer(i)"` at ~line 122): the name cell becomes `PlayerLinks.link(p.player, <current display label>)`; a click on the link must not trigger the row's `selectPlayer` (stop propagation on links inside the row); clicking elsewhere on the row still opens the detail card.
- `mvp.js` detail card (`selectPlayer` ~line 157): add a "View career" link when `PlayerLinks.url(name)` is non-null.
- `mvp.js` `renderRaceChart` (~line 284) and `season.js` `renderMVPRace` (~line 298): carry the raw name per point (`customdata`); `plotly_click` navigates to `PlayerLinks.url(name)` when non-null, else no-op; pointer cursor only on hover of points with a URL (`plotly_hover`/`plotly_unhover`); hover text gets a short "Click for career" line only for those players (built after `ready`).
- Both pages: script tag; await `ready` once at init.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run** both suites — PASS.
- [ ] **Step 3: Verify:** Review Focus 1 (click name → career page; click row elsewhere → detail card); detail card link; MVP chart bar click and timeline point click open the right player; pointer only on players with pages (check one known no-page player if any is in the top 10 / timeline, else note none); Review Focus 2 on both pages.
- [ ] **Step 4: Commit** — `feat(links): MVP ladder, detail and chart clicks open career pages`.

---

### Task 4: Reuse, consistent style, docs

**Files:** `docs/recap.js`, `docs/recap.html`, `docs/team.js`, `docs/players.js`, `docs/records.js`, `docs/about.html`, `CLAUDE.md`.

- `recap.js` `playerRow` (~lines 236-248): replace the local `_playerCodeMap` / `normName` lookup with `PlayerLinks.link(p.name, displayName)`; remove the now-unused fetch of `player_index.json` in recap.js; add the script tag to recap.html; same visible result plus the shared class.
- `team.js` (~line 235), `players.js`, `records.js`: existing player anchors drop their inline `style="text-decoration:none;color:inherit"` and use `class="player-link"` (they keep their own codes — no lookup needed).
- `about.html`: one line in the nav/search entry or Dashboard Pages area: player names across the site open the player's career page.
- `CLAUDE.md` Frontend section: player links go through `docs/player-links.js` (`PlayerLinks.link/url`; links only when a career page exists).

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run** both suites — PASS.
- [ ] **Step 3: Verify:** Game Recap expanded game shows linked names with hover style; Team, Player Stats and Records links show the same hover style.
- [ ] **Step 4: Commit** — `refactor(links): Game Recap uses PlayerLinks; shared link style; docs`.
