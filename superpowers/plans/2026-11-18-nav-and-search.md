# Grouped Navigation + Player/Team Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 19 copy-pasted navs with one shared `docs/nav.js` that renders four grouped menus (Season, Teams, Players, History) + About + a player/team search box.

**Architecture:** `fetch_player_career_stats.py` additionally writes a small `docs/data/current/search_index.json`. `docs/nav.js` holds the menu structure and pure search helpers (unit-tested with `node --test`), and renders the nav synchronously into a `<nav>` placeholder on every page; it fetches the search index only on first use of the search box.

**Tech Stack:** Python 3.12 + pytest (pipeline), vanilla JS (no build step, no dependencies), Node 21 built-in test runner for JS unit tests, `docs/style.css`.

**Spec:** `superpowers/specs/2026-11-18-nav-and-search-design.md` — read it before starting any task.

## Global Constraints

- Static GitHub Pages site from `docs/`; no build step, no bundler, no new dependencies (JS or Python).
- Never hardcode a season year in pipeline scripts; use `season_config.CURRENT_SEASON` (`tests/test_no_hardcoded_season.py`).
- Do not change the format of `docs/data/current/player_index.json` (read by `docs/recap.js`).
- Existing deep links keep working: `player.html?code=<code>` (code without `P` prefix, e.g. `003469`), `team.html?team=<CODE>`.
- `nav.js` must not depend on `constants.js` (not loaded by `about.html`, `player.html`, `replay.html`).
- Search data is fetched only when the search box is first focused/used, never on page load.
- Plans/specs live in `superpowers/`, never under `docs/` (published).
- Run Python tests with `.venv/Scripts/python.exe -m pytest tests/ -q`; JS tests with `node --test tests/js/`.
- Work on branch `feat/nav-search`; commit per task.

## Review Focus

1. **Typing before the index has loaded** (slow phone): the typed query must produce results as soon as the index arrives, without retyping. — manual check in Task 3.
2. **Pressing `/` while typing in another field** (Player Stats "Search player…", Compare, Careers search): must type a `/`, not jump to nav search. — manual check in Task 3.
3. **Names with diacritics, apostrophes, hyphens, suffixes** ("O'SHAE J", "HAYES-DAVIS, NIGEL", "DONČIĆ", "CLARK III, JIMMY", "BACOT JR., ARMANDO") must match natural queries and display sensibly. — tests in Task 2.
4. **Site served from a subpath** (`/euroleague-analytics/`), with a trailing `/` (no filename), or with a query string: current-page highlighting must still work. — tests in Task 2.
5. **Mid-season transfer rows** (`"OLY;PAR"`) must never produce a team result or a `team.html?team=` link containing `;`. — tests in Task 1.

---

## File Structure

| File | Responsibility |
|---|---|
| `fetch_player_career_stats.py` (modify) | add `build_search_index()` + write `search_index.json` |
| `tests/test_search_index.py` (create) | index builder tests |
| `docs/data/current/search_index.json` (generated, committed) | search data |
| `docs/nav.js` (create) | menu data, pure search helpers, DOM rendering + search UI |
| `tests/js/nav.test.js` (create) | unit tests for the pure helpers |
| `docs/style.css` (modify) | group menus, search box, new collapse breakpoint, mobile search |
| `docs/*.html` ×19 (modify) | replace `<nav>…</nav>` with placeholder + script |
| `tests/test_nav_pages.py` (create) | every page uses the placeholder; every nav target exists |
| `docs/about.html`, `CLAUDE.md` (modify) | document the feature |

---

### Task 1: Search index export

**Files:**
- Modify: `fetch_player_career_stats.py` (constants at top; write after `OUT_INDEX` near the end of `fetch_career_stats()`)
- Test: `tests/test_search_index.py`
- Generate: `docs/data/current/search_index.json`

**Interfaces:**
- Produces: `build_search_index(players: dict, schedule_rows: list, season: int) -> dict` and `OUT_SEARCH = os.path.join('docs', 'data', 'current', 'search_index.json')`.
- Output shape (consumed by Task 2/3), exact keys:
  `{"season": 2026, "players": [{"c": "003469", "n": "VEZENKOV, SASHA", "t": "OLY", "f": 2015, "l": 2026, "s": 10}], "teams": [{"c": "OLY", "n": "OLYMPIACOS PIRAEUS"}]}`
  - `players` input is the existing `players_dict` (code → `{'name', 'seasons': [{'season_code': 'E2026', 'team_code', ...}, …]}`, most recent season first).
  - `t`: team of the most recent season; a combined code `"OLY;PAR"` becomes `"OLY/PAR"`.
  - `f`/`l`: min/max season start year from `season_code` (`'E2015'` → 2015); `s`: number of seasons.
  - `teams`: unique `homecode` → `hometeam` from `schedule_rows` (rows of `schedule_{season}.json`), sorted by code; names kept as given (uppercase; the frontend capitalizes).
  - Players with no seasons are skipped.

- [ ] **Step 1: Write the failing tests** in `tests/test_search_index.py` (import `build_search_index` from `fetch_player_career_stats`; add repo root to `sys.path` like `tests/test_clinch_status.py`):
  - `test_player_entry_fields`: player `003469` with seasons `E2026/OLY`, `E2015/BAR`, `E2016/BAR` → `{"c": "003469", "n": "VEZENKOV, SASHA", "t": "OLY", "f": 2015, "l": 2026, "s": 3}`.
  - `test_transfer_code_joined_with_slash`: most recent season `team_code "OLY;PAR"` → `t == "OLY/PAR"`.
  - `test_teams_come_from_schedule_without_transfer_codes`: schedule rows with `homecode` OLY/PAN (duplicates) and a player row `VIR;IST` → `teams == [{"c": "OLY", "n": "OLYMPIACOS PIRAEUS"}, {"c": "PAN", "n": "PANATHINAIKOS AKTOR ATHENS"}]`; no team code contains `;`.
  - `test_works_before_any_games`: no player has a `E{season}` row → `teams` still has the schedule's clubs; `season` key equals the argument.
  - `test_skips_players_without_seasons`.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_search_index.py -q` — expect ImportError/FAIL.

- [ ] **Step 3: Implement** `build_search_index` and `OUT_SEARCH`; in `fetch_career_stats()` after writing `OUT_INDEX`, load `schedule_{CURRENT_SEASON}.json` (repo root; `[]` with a printed warning if missing), call the builder with `CURRENT_SEASON`, and write compact JSON (`separators=(',', ':')`, `ensure_ascii=False`) to `OUT_SEARCH`. Import `CURRENT_SEASON` from `season_config`.

- [ ] **Step 4: Run** the new tests + `tests/test_no_hardcoded_season.py` — expect PASS.

- [ ] **Step 5: Generate the file without re-fetching the API:** run a one-off `python -c` that loads `players` from the existing `docs/data/current/player_career_stats.json` and rows from `schedule_2026.json`, calls `build_search_index(..., CURRENT_SEASON)` and writes `OUT_SEARCH`. Check: ~1,210 players, 20 teams, file < 80 KB.

- [ ] **Step 6: Commit** `fetch_player_career_stats.py tests/test_search_index.py docs/data/current/search_index.json` — `feat(search): export search_index.json for nav search`.

---

### Task 2: Pure nav + search helpers in `docs/nav.js`

**Files:**
- Create: `docs/nav.js` (helpers + menu data only in this task; rendering is Task 3)
- Test: `tests/js/nav.test.js`

**Interfaces:**
- Consumes: `search_index.json` shape from Task 1.
- Produces (exported for Node via `if (typeof module === 'object' && module.exports) module.exports = {...}`; in the browser they are top-level functions in the same file):
  - `NAV_GROUPS`: `[{label: 'Season', links: [{href: 'index.html', text: 'Season Hub'}, …]}, …]` — exactly the spec's table (Season, Teams, Players, History, in that order, links in the table's order), plus `NAV_ABOUT = {href: 'about.html', text: 'About'}`.
  - `currentPage(pathname: string) -> string`: last path segment; `''` → `'index.html'`; `'series.html'` → `'playoffs.html'`.
  - `normalizeText(s: string) -> string`: NFD, strip combining marks, lowercase, remove apostrophes (`'` and `’`).
  - `tokens(s: string) -> string[]`: `normalizeText` then split on any non `[a-z0-9]`, drop empties.
  - `formatPlayerName(raw: string) -> string`: `"LAST, FIRST"` → `"First Last"`; capitalize each word and each part after `-` or `'`; keep roman numerals `II, III, IV, V` uppercase; keep `Jr.`.
  - `formatTeamName(raw: string) -> string`: capitalize words, but keep words of ≤2 letters and words containing a digit uppercase.
  - `search(index: object, query: string, limit = 8) -> Array<{type: 'team'|'player', href: string, label: string, detail: string}>`.
    - Match: every query token is a prefix of some token of the name (players: `n`; teams: `n` plus the code as an extra token). Empty query → `[]`.
    - Order: teams first; then players whose surname (text before the comma) has a token starting with the first query token; then `l === index.season`; then larger `s`; then name.
    - Player: `href: 'player.html?code=' + c`, `label: formatPlayerName(n)`, `detail: t + ' · ' + f + '–' + l` (en dash; single season shows just `f`).
    - Team: `href: 'team.html?team=' + c`, `label: formatTeamName(n)`, `detail: 'Team'`.

- [ ] **Step 1: Write the failing tests** in `tests/js/nav.test.js` (`node:test` + `node:assert/strict`, `require('../../docs/nav.js')`). Use a small inline index (season 2026) containing Vezenkov (`OLY`, 2015–2026, s 10), `"BRISSETT, O'SHAE J"`, `"HAYES-DAVIS, NIGEL"`, `"DONČIĆ, LUKA"` (l 2018), `"CLARK III, JIMMY"`, `"BACOT JR., ARMANDO"`, `"JONES, TYRIQUE"` (`OLY/PAR`), `"JONES, CARLIK"` (l 2026, s 6), `"JONES, OLD"` (l 2012, s 2), and teams OLY `OLYMPIACOS PIRAEUS`, BAR `FC BARCELONA`, MIL `EA7 EMPORIO ARMANI MILAN`:
  - `currentPage`: `'/euroleague-analytics/'` → `index.html`; `'/euroleague-analytics/team.html'` → `team.html`; `'/series.html'` → `playoffs.html`; `'/'` → `index.html`.
  - `NAV_GROUPS` labels are `['Season','Teams','Players','History']` and contain 17 links total; `series.html` is not among them.
  - `formatPlayerName`: Vezenkov → `Sasha Vezenkov`; `O'Shae J Brissett`; `Nigel Hayes-Davis`; `Jimmy Clark III`; `Armando Bacot Jr.`.
  - `formatTeamName`: `FC Barcelona`, `EA7 Emporio Armani Milan`, `Olympiacos Piraeus`.
  - `search` matching: `'vez'`, `'sasha vez'`, `'vez sasha'` → first result href `player.html?code=003469`; `'doncic'` finds Dončić; `"o'shae"` and `'oshae'` find Brissett; `'davis'` finds Hayes-Davis; `''` → `[]`; `'zzz'` → `[]`.
  - `search` teams: `'oly'` → first result `{type: 'team', href: 'team.html?team=OLY', label: 'Olympiacos Piraeus'}`; no result href contains `;`.
  - `search` ranking: `'jones'` → Carlik Jones (active) before Old Jones; Tyrique Jones detail starts with `OLY/PAR`.
  - `search` limit: a query matching >8 entries returns 8.

- [ ] **Step 2: Run** `node --test tests/js/` — expect FAIL (module not found).

- [ ] **Step 3: Implement** the helpers and menu data in `docs/nav.js`. Wrap any DOM code (Task 3) so the file loads in Node without `document`.

- [ ] **Step 4: Run** `node --test tests/js/` — expect all PASS.

- [ ] **Step 5: Commit** `docs/nav.js tests/js/nav.test.js` — `feat(nav): menu data and search helpers`.

---

### Task 3: Render the nav and search UI

**Files:**
- Modify: `docs/nav.js` (DOM rendering, runs only when `document` exists)
- Modify: `docs/style.css` (nav section around lines 637–800)
- Modify: `docs/index.html` (only, as the first page converted — placeholder from Task 4)

**Interfaces:**
- Consumes: Task 2 exports; `data/current/search_index.json` (Task 1).
- Produces: on load, `nav.js` fills `<nav class="site-nav" id="site-nav" aria-label="Main">` synchronously (it is included right after the placeholder). Task 4 relies on this exact placeholder:
  ```html
  <nav class="site-nav" id="site-nav" aria-label="Main"></nav>
  <script src="nav.js"></script>
  ```

- [ ] **Step 1: Render the bar:** brand `🏀 Euroleague Analytics` (link to `index.html`), the four group menus, About link, search box, and on narrow screens a search icon button and the existing `☰ Menu` toggle. Reuse existing classes: each group is a `.nav-more` with a `.nav-link.nav-more-btn` button (`aria-expanded`) and `.nav-more-dropdown` of `.nav-link`s. Mark the `currentPage()` link `active` + `aria-current="page"`, and its group button `active`. One group open at a time; close on Escape (focus returns to the button), outside click, or focus leaving — same behavior as today's More menu, now with event listeners instead of inline handlers.

- [ ] **Step 2: Search UI:** `<input type="search" placeholder="Search players, teams" aria-label="Search players and teams">` with an ARIA combobox (`role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`) and a `role="listbox"` results list. On first focus, fetch `data/current/search_index.json` once; if the user typed before it arrived, run their current query when it lands. Results: label + muted detail; ↑/↓ move, Enter opens the highlighted (default first), Escape clears/closes, click/tap opens. Empty: `No players or teams match "<query>"`. Fetch error: `Search is unavailable right now.` Global `/` focuses the search box only when the event target is not an `input`, `textarea`, `select` or `contenteditable`.

- [ ] **Step 3: CSS:** move the collapse breakpoint from `89.9375em` to the width where the new bar stops fitting (start at `56.25em` = 900px; adjust after measuring). In the collapsed state: bar shows brand, search icon button and `☰ Menu`; the search button toggles a full-width search row under the bar (auto-focused); the open menu lists all four groups with their labels visible as headings and all links visible (no nested taps). Results dropdown width ≥ 18rem on desktop, full width on phones.

- [ ] **Step 4: Convert `docs/index.html`** to the placeholder (exact markup above), serve `docs/` locally (`python -m http.server 8765 --bind 127.0.0.1` from `docs/`), and verify by screenshot at 1440px, ~1024px and 390px (headless Chrome; phone width via a 390px iframe, since Chrome's minimum window width is ~500px):
  - Groups open/close; Season Hub highlighted; no layout jump on load.
  - Search `vez` → Sasha Vezenkov first; `oly` → Olympiacos team first; Enter navigates.
  - **Review Focus 1:** throttle or delay the index fetch (e.g. temporarily point the URL at a slow local endpoint, or type immediately after first focus) — results appear without retyping.
  - **Review Focus 2:** on `players.html` (after Task 4) type `/` in its "Search player…" box — a `/` is typed, nav search not focused.

- [ ] **Step 5: Run** `node --test tests/js/` and `.venv/Scripts/python.exe -m pytest tests/ -q` — all PASS.

- [ ] **Step 6: Commit** `docs/nav.js docs/style.css docs/index.html` — `feat(nav): render grouped nav and search from nav.js`.

---

### Task 4: Convert all pages

**Files:**
- Modify: the other 18 `docs/*.html` pages
- Test: `tests/test_nav_pages.py`

**Interfaces:**
- Consumes: the placeholder markup from Task 3; `NAV_GROUPS` hrefs in `docs/nav.js`.

- [ ] **Step 1: Write the failing tests** in `tests/test_nav_pages.py`:
  - `test_every_page_uses_shared_nav`: every `docs/*.html` contains `<nav class="site-nav" id="site-nav" aria-label="Main"></nav>` immediately followed (ignoring whitespace) by `<script src="nav.js"></script>`, exactly once.
  - `test_no_inline_nav_left`: no `docs/*.html` contains `nav-more-dropdown`, `nav-toggle` or `class="nav-link`.
  - `test_nav_targets_exist`: every `href: '…html'` in `docs/nav.js` names an existing `docs/` file.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_nav_pages.py -q` — expect FAIL (18 pages still inline).

- [ ] **Step 3: Replace** each page's `<nav class="site-nav" …>…</nav>` block (from `<nav` to its `</nav>`, including the drifted variants in `compare.html` and `players.html`) with the placeholder. Change nothing else on the pages.

- [ ] **Step 4: Run** all Python and JS tests — PASS. Screenshot-check `player.html`, `about.html`, `replay.html` (pages without `constants.js`) and `series.html` (Playoffs highlighted) at 1440px and 390px; do the Review Focus 2 check on `players.html`.

- [ ] **Step 5: Commit** `docs/*.html tests/test_nav_pages.py` — `feat(nav): use shared nav on all pages`.

---

### Task 5: Documentation

**Files:**
- Modify: `docs/about.html` (Dashboard Pages section, near the "Season Hub" entry), `CLAUDE.md` (Frontend section and Key Data Files)

- [ ] **Step 1:** `about.html`: add a short entry describing the grouped menus and the search box (what it finds, `/` shortcut, where results go).
- [ ] **Step 2:** `CLAUDE.md`: under Frontend, state that the nav lives only in `docs/nav.js` (pages contain just the placeholder; add new pages to `NAV_GROUPS`), and that JS unit tests run with `node --test tests/js/`; under Key Data Files add `docs/data/current/search_index.json` (written by `fetch_player_career_stats.py`).
- [ ] **Step 3:** Run all tests; commit `docs/about.html CLAUDE.md` — `docs: document grouped nav and search`.
