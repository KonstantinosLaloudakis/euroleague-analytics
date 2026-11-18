# Player names link to career pages — design

Date: 2026-11-18 · Status: approved by owner 2026-11-18

Verified facts: `player_stats[].code` and Compare's `_code` are career codes (same form as the index values, no
`P` prefix); `assist_network` ids are `P` + career code.

## Why

The site's direction is "Basketball Reference for EuroLeague": player career pages (`player.html?code=…`) are the
reference core, but today only Team Deep-Dive, Player Stats, Game Recap and All-Time Records link to them. A visitor
who sees Vezenkov on the MVP ladder, a lineup or an assist combo has no way to click through. Goal: any player name
on the site is one click from that player's career page. Backlog item 1 in `superpowers/ui-ux-backlog.md`.

## Goals

- Player names in tables and lists link to the career page on: Season Hub (MVP Top 10 chart), MVP Race (ladder,
  detail card, timeline chart), Head-to-Head (key players), Shot Lab (paint finishing profiles), Playmaking (assist
  combos and playmakers tables), Lineups, Compare (chosen players).
- Clicking a bar in the Season Hub's MVP Top 10 chart, or a point on the MVP Race timeline, opens that player.
- Linked names are recognizable as links (hover/focus feedback), consistently across the site, including the pages
  that already link.
- One shared implementation; Game Recap's own copy of the name lookup is replaced by it.

## Non-goals

- Changing how names are formatted ("VEZENKOV, SASHA" vs "S. Vezenkov") — separate backlog item 3.
- Pipeline changes (no new `code` fields in exports).
- The Playmaking chord diagram, its tooltips and the Shot Lab shot charts (clicking already does something there,
  or there's no single player to open).
- Series page (shows no player names).

## Anti-goals (failure even if it works)

- Breaking existing click behavior: MVP ladder row click opens the detail card; Playmaking chord click pins a player;
  table header clicks sort.
- A name disappearing or a page failing to render if the lookup file can't load — names must fall back to plain text.
- Noticeably slower pages.

## Constraints

- Static GitHub Pages site from `docs/`, vanilla JS, no build step, no new dependencies.
- Name format is uniform in all data: `"LAST, FIRST"` uppercase (e.g. `"VEZENKOV, SASHA"`, `"MILLER-MCINTYRE, CODI"`).
- `docs/data/current/player_index.json` (31 KB, written by `fetch_player_career_stats.py`) maps normalized name →
  career code for all 1,210 players since 2007-08: keys are uppercase with diacritics stripped (`normalize_name`).
  Verified: no two players share a normalized name. Codes are either digits (`"003469"`) or letters (`"THY"`).
  Its format must not change (Game Recap reads it).
- Some data already carries IDs: `dashboard.json` `player_stats[].code` (`"003469"`, no prefix — used by Head-to-Head
  key players); `assist_network.json` `passer_id` / `scorer_id` / `player_id` (`"P009048"`, API form with a `P`
  prefix = `P` + career code).
- Career page URL: `player.html?code=<code>`.
- `docs/nav.js` is deliberately global-free; the new helper is a separate file.
- Every page except about/player/replay loads `constants.js`; script order is `constants.js` then the page script.

## Approaches considered

- **A. Shared `docs/player-links.js` (chosen).** Loads `player_index.json` once and offers "URL for this player" and
  "link HTML for this player", using an ID when the data has one and the name otherwise. One place for lookup and link
  style; no pipeline change; Game Recap reuses it. Cost: pages wait for one more small file before names become links
  (they render as plain text if it fails).
- **B. Add a `code` field to every export in the pipeline.** Self-describing data, but five exporters to change and
  test for a collision problem that doesn't exist, and only effective after the next pipeline run. Rejected.
- **C. Put the lookup in `nav.js`.** nav.js is global-free and about navigation. Rejected.

## Decided with the owner

- Approach A.
- Charts link too where a click is natural: the Season Hub MVP Top 10 bars and the MVP Race timeline points.
  The chord diagram and shot charts are left alone.

## Design

### `docs/player-links.js`

A classic script exposing exactly one global, `PlayerLinks` (unique name, no collision with existing globals —
builder verifies), and exporting the same object for Node tests via the guarded `module.exports` pattern used in
`docs/nav.js`. Browser-only code (the fetch) runs only when `fetch`/`document` exist.

- `PlayerLinks.ready` — a Promise that resolves once `data/current/player_index.json` has loaded **or failed**; it
  never rejects. Fetched once per page, on script load.
- `PlayerLinks.url(name, ids?)` → `'player.html?code=<code>'` or `null`.
  `ids` is optional `{code}` (already a career code, e.g. `player_stats[].code`) or `{apiId}` (`P`-prefixed API id,
  e.g. `assist_network` ids; strip exactly one leading `P`). An id wins over the name; otherwise the name is
  normalized (uppercase, diacritics stripped, trimmed) and looked up. Code is URL-encoded.
  **A URL is returned only if the code is one of the index's values** — i.e. a career page exists. An id that
  isn't in the index → `null` (no link), never a link to a missing page.
- **Players without a career page.** The EuroLeague stats API that builds the career data omits players with too few
  games (this season's career rows start at 7 GP), so some names have no page: 13 of 255 current players today (all
  new this season, 5–6 GP — e.g. Antonio Reeves, Nikola Djurisic), and ~4% of names on Lineups (low-minute players,
  incl. past seasons). These names stay plain text; they gain links automatically once the player appears in the
  career data. *(Claude's call: expanding career coverage is a pipeline change outside this design — logged as a
  follow-up in the UI/UX backlog.)*
- `PlayerLinks.link(name, label?, ids?)` → HTML string: `<a class="player-link" href="…">label</a>` when a URL is
  found, else the label as plain text. `label` defaults to `name`. The label is HTML-escaped in both cases (names
  come from data).
- Each page awaits `PlayerLinks.ready` **once, at init**, in parallel with its own data fetch (e.g. in its existing
  `Promise.all`), before its first render. Later renders (filters, tabs, season switches, Compare slot changes) call
  `PlayerLinks.link/url` synchronously — `ready` is already settled by then. *(Claude's call: render once with links
  rather than re-render later; the file is small and fetched in parallel.)*

### Chart clicks (Season Hub MVP Top 10, MVP Race timeline)

Each bar/point carries the player's raw name (e.g. Plotly `customdata`). Clicking navigates only when
`PlayerLinks.url(name)` is non-null; otherwise the click does nothing. The pointer cursor and the "Click for career"
hover line appear only for players with a page: toggle the cursor on `plotly_hover`/`plotly_unhover` per point (Plotly
has no per-point cursor setting), and build the hover text after `ready`. *(Claude's calls.)*

### Link style (`docs/style.css`)

`.player-link`: inherits color, no underline; on hover and keyboard focus: underline and the site's accent color.
Existing player links on Team Deep-Dive, Player Stats, Game Recap and Records switch to this class (replacing their
inline `style="text-decoration:none;color:inherit"`) so all player links behave the same.

### Per page

| Page (script) | What links | ID available |
|---|---|---|
| Season Hub (`season.js` `renderMVPRace`) | Click a bar in the MVP Top 10 chart → career page; pointer cursor on bars; hover text gains a short "Click for career" line | name only |
| MVP Race (`mvp.js`) | Ladder: the name cell is a link; clicking the link navigates, clicking elsewhere on the row still opens the detail card (the link must not trigger row selection). Detail card: a "View career" link. Timeline (`renderRaceChart`): clicking a point opens that player | name only |
| Head-to-Head (`h2h.js` `renderPlayerComparison`) | Key player names | `code` |
| Shot Lab (`shots.js`) | Paint Finishing Profiles → Players tab: player cell, and the player name in the paint detail view. Teams/Team Defense tabs unchanged | name only |
| Playmaking (`network.js`) | Top 20 Assist Combos: passer and scorer; Top 20 Playmakers: player and top target. Chord diagram and tooltips unchanged | `apiId` for passer/scorer/player; top target by name |
| Lineups (`lineups.js`) | Each of the five (or two) names in a row links separately; still joined with ", " | name only (all seasons) |
| Compare (`compare.js`) | A "View career" link next to each chosen player | `code` (`_code`) |
| Game Recap (`recap.js`) | Unchanged behavior; its inline name lookup is replaced by `PlayerLinks.link` | name only |

Each listed page loads `<script src="player-links.js"></script>` before its page script (after `constants.js`).

### Other changes

- `docs/about.html`: one line saying player names across the site open the player's career page (project rule: About
  documents new features).
- `CLAUDE.md` Frontend section: player links go through `docs/player-links.js` (`PlayerLinks.link/url`).

### Testing

- Node (`node --test tests/js/*.test.js`, new `tests/js/player-links.test.js`): `url` by name (case/diacritics
  insensitive, surrounding spaces), by `{code}`, by `{apiId}` (`'P003469'` → `003469`), id beats name, unknown name →
  `null`, **a `{code}`/`{apiId}` not in the index → `null`**; `link` escapes the label (`<b>` stays text) for both linked and unknown names; `ready` resolves when no
  index is available (Node). Uses a small inline index injected through a test-only setter or constructor argument —
  builder's choice, but no test hooks visible in the browser API beyond what's documented.
- Python static test (`tests/test_player_links_pages.py`): every `docs/*.js` page script that references
  `PlayerLinks` is loaded by an HTML page that includes `player-links.js` before it.
- Manual/screenshot: each page in the table — names show as links with hover style, link targets open the right
  career page (spot-check 2 per page), MVP row click still opens the detail card, chord pin still works, MVP chart bar
  and timeline point clicks navigate, names render as plain text when `player_index.json` is unreachable.

## Left to the builder

- Internal structure of `player-links.js`; how tests inject an index.
- Exact hover color token and the wording of the "View career" links / chart hover line (plain, short).
- How the MVP chart/timeline carry the raw name to the click handler (e.g. Plotly `customdata`).
