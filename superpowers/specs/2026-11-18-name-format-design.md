# One player-name format across the site — design

Date: 2026-11-18 · Status: approved by owner 2026-11-18

## Why

The same player appears as "VEZENKOV, SASHA" (most pages), "S. Vezenkov" (MVP, Recap), "Vezenkov" (Playmaking) and
"Sasha Vezenkov" (nav search). Four separate formatters disagree and already mangle hyphenated names
("Miller-mcintyre", "Miller-Mcintyre"). A reference site for a public audience should write names one way.
Backlog item 3 in `superpowers/ui-ux-backlog.md`.

## Goals (owner-approved convention)

- **Full — "Sasha Vezenkov"** (first name first) wherever there's room: tables, lists, page titles and headers.
- **Short — "S. Vezenkov"** in narrow places and on phones, where full names would wrap.
- **Surname — "Vezenkov"** inside charts where space is tightest (Season Hub MVP bars, Playmaking chord labels).
- One shared implementation; the four existing formatters (`mvp.js formatName`, `recap.js formatName`,
  `network.js formatPlayerName`, `nav.js formatPlayerName`) are removed in favor of it.

## Non-goals

- Changing the underlying data (it stays `"LAST, FIRST"` uppercase; lookups such as `PlayerLinks` keep using it).
- Team names, coach names, or anything that isn't a player name.
- Perfect capitalization of every rare name: the rules cover common patterns; a small override list handles known
  exceptions and can grow.

## Anti-goals (failure even if it works)

- A name rendered as raw HTML (data is untrusted text) — everything stays escaped.
- Breaking player links, search, or sorting (sort by the raw/surname key, not by the display string, where a table
  sorts by name today — keep today's sort order).
- Layout regressions: long full names overflowing narrow cells on phones.

## Constraints

- Static GitHub Pages site from `docs/`, vanilla JS, no build step, no new dependencies.
- Data names: `"LAST, FIRST"` uppercase, sometimes with suffixes (`"CLARK III, JIMMY"`, `"BACOT JR., ARMANDO"`,
  `"BALDWIN IV, WADE"`), hyphens (`"MILLER-MCINTYRE, CODI"`, `"HAYES-DAVIS, NIGEL"`), apostrophes
  (`"BRISSETT, O'SHAE J"`), particles (`"DE COLO, NANDO"`, `"VAN DEN SPIEGEL, TOMAS"`), initials (`"C.J."`-style
  first names), and occasionally no comma.
- The EuroLeague API has no reliable mixed-case full name (`abbreviatedName` is sometimes empty or passport-based;
  `jerseyName` is mostly uppercase), so capitalization is rule-based.
- `docs/nav.js` is one IIFE with no globals and is loaded on every page right after the nav placeholder.
- `docs/player-links.js`: `PlayerLinks.link(name, label?, ids?, extraClass?)` escapes `label`; used on most pages
  that show names.

## Approaches considered

- **A. Shared `docs/names.js`, loaded on every page (chosen).** One formatter + override list; unit-tested; no
  downloads or pipeline changes. Cost: one more script tag per page (test-enforced).
- **B. Format in the Python pipeline** (display names in every export or a lookup file). Many exporters change, a new
  download, fixes only after a pipeline run. Rejected.
- **C. Fix each page's formatter in place.** Keeps 4+ copies that drift. Rejected.

## Design

### `docs/names.js`

A classic script exposing one global `PlayerNames`, with a Node export for tests (pattern of `docs/player-links.js`):

- `PlayerNames.full(raw) -> string` — "Sasha Vezenkov".
- `PlayerNames.short(raw) -> string` — first-name initial + surname: "S. Vezenkov", "J. Clark III", "C. Miller-McIntyre".
- `PlayerNames.surname(raw) -> string` — "Vezenkov", "Clark III".
- `PlayerNames.responsiveHtml(raw) -> string` — escaped `<span class="pn-full">Sasha Vezenkov</span><span
  class="pn-short">S. Vezenkov</span>`; CSS in `docs/style.css` shows `.pn-full` by default and swaps to `.pn-short`
  at `max-width: 640px` (the site's existing phone breakpoint).
- Capitalization rules *(Claude's calls)*: split `raw` on the first comma into surname / first name (no comma → the
  whole string is the surname); title-case each word and each part after `-` and `'`; `Mc` prefix capitalizes the
  next letter (`MCINTYRE` → `McIntyre`; `Mac` is left alone — ambiguous); suffixes `JR`/`JR.`/`SR`/`SR.` → `Jr.`/`Sr.`;
  roman numerals `II III IV V` stay uppercase; single letters and dotted initials stay uppercase (`J`, `C.J.`);
  particles are title-cased (`De Colo`, `Van Den Spiegel`) unless overridden.
- An `OVERRIDES` map (normalized raw name → full display) in the same file for names the rules get wrong; the
  builder seeds it by scanning current data for likely misses (`MAC…`, names with lowercase-in-real-life particles
  that the owner's audience would notice) — keep it short and only for real players in the data.
- Input is matched case-insensitively and trimmed; non-string/empty → `''`.

### Integration

- **Every page** loads `<script src="names.js"></script>` immediately before `<script src="nav.js"></script>`
  (so nav search and all page scripts can use it). `tests/test_nav_pages.py` (or a new test) enforces it.
- **`nav.js`** search results use `PlayerNames.full` (its private `formatPlayerName` is removed; nav.js stays
  global-free and reads the global only at render time; if absent, fall back to the raw name).
- **`PlayerLinks.link(name, label?, ids?, extraClass?)`**: when `label` is omitted/undefined, the anchor text is
  `PlayerNames.responsiveHtml(name)` (when `PlayerNames` is loaded; otherwise the escaped raw name). Passing a label
  keeps today's escaped-label behavior. This is how most pages get full-on-desktop / short-on-phones names.

### Per page (which form where)

| Page / place | Form |
|---|---|
| Player Stats table, Records tables, Shot Lab paint profiles, Head-to-Head key players, Team top contributors, Compare hero cards, Careers page title/header and top-performers list, Game Recap box scores, Playoffs player tables, MVP ladder + detail card | Full on desktop, short on phones (responsive) |
| Lineups (five names per cell), Playmaking combos/playmakers tables (incl. top target), any table where the name column is narrow by design | Short |
| Season Hub MVP Top 10 bars, Playmaking chord labels | Surname |
| MVP Race timeline legend | Short *(Claude's call: a legend can hold two players with the same surname; short disambiguates)* |
| Chart hover text, tooltips | Full |
| Nav search results | Full |

Places not listed that show a player name follow the same rule of thumb (room → full/responsive; narrow → short;
inside a chart → surname/short). Sorting keeps today's keys.

### Builder-check calls *(Claude's calls)*

1. **Text-only sites** (`<option>` text, `input.value`, `document.title`, `textContent`, SVG `<text>`, Plotly
   ticks/hover/legend/annotations) use plain strings with no phone swap: hover text, tooltips, options, titles and
   inputs → `full()`; chart legends, the Season Hub forecast card and Replay WPA bar labels → `short()`; MVP bars,
   chord labels and GCI history pills → chart labels (call 4).
2. **Search/filter boxes** that match names (`players.js` ~120/~429/~581, `compare.js` ~127, `player.js` ~250) match
   on both the raw name and the full display name, using the same token-prefix, any-order, accent-insensitive
   matching as the nav search ("sasha vez", "vezenkov", "VEZENKOV, SASHA" all work). Pickers that write a chosen
   player into an input write `full()`.
3. **All ad-hoc name formatting is in scope**, not just the four named functions: `players.js _cleanName`, inline
   `split(',')[0]` / `split(', ')` on player names in `season.js`, `app.js`, `mvp.js`, `recap.js`, and any other the
   builder finds by grepping page scripts. The static test forbids `formatName`, `formatPlayerName` and `_cleanName`
   definitions outside `names.js`; reviewers check for inline splits.
4. **Chart-label collisions:** add `PlayerNames.chartLabels(raws) -> string[]` — surname for each, but short form for
   any players whose surnames collide within that set. Used for MVP bars, chord labels and GCI pills.
5. **Script-tag scope:** every page with the nav placeholder loads `names.js` (the nav search needs it everywhere).
   Name sites on Series, Game Control, GCI History, Title Race, Pace, Playoffs and the Season Hub forecast tables
   follow the per-page rule of thumb; the builder finds them by grep.
6. **Sorting:** keep today's keys, including Lineups sorting by the joined raw names.

### Other changes

- `about.html`: none needed (no new feature). `CLAUDE.md` Frontend: names go through `docs/names.js`
  (`PlayerNames.full/short/surname/responsiveHtml`); never format names ad hoc.

### Testing

- Node `tests/js/names.test.js`: full/short/surname for `VEZENKOV, SASHA`, `MILLER-MCINTYRE, CODI` →
  "Codi Miller-McIntyre", `HAYES-DAVIS, NIGEL`, `BRISSETT, O'SHAE J` → "O'Shae J Brissett", `CLARK III, JIMMY` →
  "Jimmy Clark III", `BACOT JR., ARMANDO` → "Armando Bacot Jr.", `DE COLO, NANDO` → "Nando De Colo", a no-comma
  name, an override entry, empty/non-string; `responsiveHtml` escapes (`<` stays text) and contains both spans.
- Node `player-links` test: `link(name)` without label uses the responsive markup when `PlayerNames` is present.
- Python static test: every page loads `names.js` before `nav.js`; no page script defines its own name formatter
  (`function formatName` / `function formatPlayerName` outside names.js).
- Screenshot check: desktop and 390 px on Player Stats, MVP, Lineups, Playmaking, Recap, Careers; no overflow; names
  read as specified.

## Left to the builder

- Exact spots in each page script (the table above is binding for the form; the builder finds every render site).
- The initial override list contents (from scanning data), kept short.
