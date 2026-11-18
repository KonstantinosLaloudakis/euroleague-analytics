# Grouped navigation + player/team search — design

Date: 2026-11-18 · Status: approved by owner 2026-11-18

## Why

The site is positioned as "Basketball Reference for EuroLeague" and is shared publicly (LinkedIn), so many
visitors arrive cold. Today the nav is 11 top-level links plus a "More" menu of 7, with no search. A visitor who
wants "Vezenkov's career" or "Maccabi's season" has to know which of 18 pages holds it. Goal: find any player or
team in two keystrokes, and make the page list understandable at a glance.

## Goals

- Group the 18 pages into four menus (Season, Teams, Players, History) plus About.
- A search box in the nav that finds any of the ~1,210 players (2007–present) and the current season's teams,
  and jumps straight to their page.
- One source of truth for the nav, so all 19 pages always match and future nav changes are a one-file edit.
- The full nav fits on ordinary laptop widths (today it collapses to "☰ Menu" below 1440px).

## Non-goals

- Searching games, seasons, or stats ("most points 2019"). Explicitly deferred; players and teams first.
- Renaming pages, changing page headers, or any other visual redesign (separate review items).
- Changing the "LAST, FIRST" name format elsewhere on the site (separate review item).
- Linking player names on other pages to player pages (separate review item).

## Anti-goals (would make this a failure even if it works)

- The nav visibly flashing in after the page loads, or the page jumping when it appears.
- Every page download getting noticeably heavier: the search data must not load until someone uses search.
- Breaking existing deep links (`player.html?code=`, `team.html?team=`, etc.) or the Game Recap page, which
  reads `data/current/player_index.json`.
- A search that's hard to use on a phone.

## Constraints

- Static site on GitHub Pages from `docs/`, vanilla JS, no build step, no bundler. Each page is a standalone
  HTML file with inline `<style>` plus shared `docs/style.css`.
- The nav markup is currently duplicated in all 19 `docs/*.html` files with inline `onclick`/`onkeydown`
  handlers (`compare.html` and `players.html` have drifted slightly). Nav CSS is in `docs/style.css`
  (`.site-nav`, `.nav-link`, `.nav-more*`, `.nav-toggle`, collapse rule at `@media (max-width: 89.9375em)`).
- `docs/constants.js` holds `TEAM_NAMES`/`TEAM_COLORS` but is **not** loaded by `about.html`, `player.html`,
  `replay.html`. The nav must not depend on it.
- Player data: `fetch_player_career_stats.py` writes `docs/data/current/player_career_stats.json` (1.7 MB,
  has every player's per-season rows with `season_code`, `team_code`, `team_name`) and `player_index.json`
  (name → code, used by `recap.js`; must keep its format). CI runs it with `--force` on every refresh.
- Player career page: `player.html?code=<code>` where code is the API code without the `P` prefix (e.g.
  `003469`). Team page: `team.html?team=<CODE>` (current-season teams only).
- Every page except `about.html` already requires JS to show any content, so a JS-rendered nav costs those
  visitors nothing. `about.html` is static: without JS it would show its text with no nav. *(Claude's call: no
  `<noscript>` fallback. It would put a second copy of the link list in all 19 pages, which is the drift this
  design removes, for the rare no-JS visitor; search engines render JS. Each page's footer already links to
  About.)*

## Approaches considered

- **A. Shared `docs/nav.js` renders the nav (chosen).** Each page has a placeholder `<nav class="site-nav"
  id="site-nav"></nav>` followed immediately by `<script src="nav.js"></script>`, which synchronously builds
  the menus, marks the current page, and adds search. One file to edit; pages can't drift; no flash because
  the script runs before the rest of the body renders. Trade-off: nav requires JS (already true for content).
- **B. Keep the nav duplicated in 19 files, add a shared search script.** Plain HTML nav, but 19 copies to keep
  in sync, which have already drifted. Rejected.
- **C. Generate the nav into the HTML from Python at export time.** Couples page layout to the data pipeline;
  the site has no HTML build step. Rejected.

## What was decided with the owner

- Approach A.
- Search covers **players and teams only**.
- Player results open the career page (`player.html?code=`); team results open Team Deep-Dive (`team.html?team=`).
- Search data is a new small file loaded only when search is first used; the existing heavy career file and
  `player_index.json` are not reused for this.
- Grouping (proposed by Claude, accepted):

  | Season | Teams | Players | History |
  |---|---|---|---|
  | Season Hub (`index.html`) | Team Deep-Dive (`team.html`) | Player Stats (`players.html`) | All-Time Records (`records.html`) |
  | Game Recap (`recap.html`) | Head-to-Head (`h2h.html`) | Careers (`player.html`) | GCI History (`gci-history.html`) |
  | MVP Race (`mvp.html`) | Game Control (`game-control.html`) | Compare (`compare.html`) | Game Replay (`replay.html`) |
  | Playoffs (`playoffs.html`) | Lineups (`lineups.html`) | Shot Lab (`shots.html`) | |
  | Title Race (`title-race.html`) | Playmaking (`network.html`) | | |

  About (`about.html`) stays a plain top-level link. `series.html` stays off the nav (reached from Playoffs).

## Design

### Search data — `docs/data/current/search_index.json`

Produced by `fetch_player_career_stats.py` next to its other two outputs (same run, same `--force` behavior).

```json
{
  "players": [
    {"c": "003469", "n": "VEZENKOV, SASHA", "t": "OLY", "f": 2015, "l": 2026}
  ],
  "teams": [
    {"c": "OLY", "n": "Olympiacos Piraeus"}
  ]
}
```

- Players: every player in the career data. `t` = team of their most recent season; `f`/`l` = first/last season
  start year. Short keys keep it small (~60 KB raw, far less gzipped by Pages).
- **Mid-season transfers:** the API gives a transferred player one row per season with a combined code such as
  `"OLY;PAR"` and combined name. The parts are in **alphabetical order, not chronological** (verified: Tyrique
  Jones's 2025-26 row is `OLY;PAR` but he started at PAR and finished at OLY), so the current club can't be
  read from it. `t` keeps every club, displayed joined with "/" (`OLY/PAR`). *(Claude's call: honest, and no
  extra data source needed.)*
- Teams: taken from `schedule_{CURRENT_SEASON}.json` (`homecode` → `hometeam`), which lists all 20 clubs as
  soon as the schedule is published, before any game is played, and never contains combined transfer codes.
  The schedule's names are uppercase ("OLYMPIACOS PIRAEUS"); display them with word capitalization.
  *(Claude's call: player rows can't be used, because transfers would create fake teams like `VIR;IST`
  linking to a broken page, and at season start there are no current-season rows at all. Names come from the
  data rather than `constants.js` because three pages don't load it.)*
- At season start, before any games, no player counts as "active this season"; ranking then falls back to
  surname match and seasons played. Acceptable.
- Season years come from `season_config`; no hardcoded years (`tests/test_no_hardcoded_season.py`).

### Nav — `docs/nav.js`

- Holds the menu structure (table above) as data and renders: brand, four menu buttons with dropdowns,
  About link, search box, and the mobile "☰ Menu" toggle. Replaces all inline nav markup and handlers.
- Current page: the link for `location.pathname` gets `active` and `aria-current="page"`, and its menu
  button is marked active too, so visitors see which section they're in. `series.html` marks Playoffs/Season.
- Menus open on click (not hover), close on Escape, outside click, or focus leaving; one menu open at a time.
  Buttons use `aria-expanded`; behavior matches today's "More" menu.
- Each page's `<nav>…</nav>` block is replaced by the placeholder + script tag. Nothing else on the pages
  changes (the playoff banner, headers, etc. stay).

### Search behavior

- Box in the nav bar, placeholder "Search players, teams". Pressing `/` anywhere (outside text fields)
  focuses it. *(Claude's call.)*
- First focus fetches `search_index.json` (once; cached for the page). Typing before it arrives queues the
  query.
- Matching *(Claude's calls)*: case- and accent-insensitive ("Dončić" ≈ "doncic"); every typed word must
  match the start of some word in the name, in any order ("sasha vez", "vez sa", "vezenkov"). Teams also match
  on their 3-letter code ("oly").
- Ranking: teams first when they match; then players whose surname starts with the query, then players active
  in the current season, then more seasons played. Show at most 8 results.
- Each result row: name, team code, and season range, e.g. `Sasha Vezenkov · OLY · 2015–2026`; teams show
  `Team · Olympiacos Piraeus`. Player names are displayed "First Last" with simple word capitalization
  *(Claude's call; known imperfect for names like "McKinley" — acceptable here, full name formatting is a
  separate review item)*.
- Keyboard: ↑/↓ move, Enter opens the highlighted result (first by default), Escape clears and closes. Mouse
  click and tap open a result. ARIA combobox/listbox pattern so screen readers announce results.
- No matches: a single line "No players or teams match "…"". Fetch failure: "Search is unavailable right now."

### Layout and widths

- Desktop: brand · Season ▾ · Teams ▾ · Players ▾ · History ▾ · About · search box (right).
- The collapse to "☰ Menu" moves from 1440px down to roughly where the new nav stops fitting (builder measures;
  expected ~900px).
- Below that: the bar shows brand, a search icon button, and "☰ Menu". The search button expands a full-width
  search field under the bar *(Claude's call: search must be one tap away on phones, not buried in the menu)*.
  "☰ Menu" opens the four groups as labeled lists (all links visible, no nested taps).

### Other changes

- `docs/about.html`: mention search and the grouped menus (project rule: About documents new features).
- `CLAUDE.md`: note that the nav lives in `docs/nav.js` (pages contain only the placeholder) and list
  `search_index.json` under key data files.

### Testing

- Python: a test for the search-index builder (players have code/name/team/first/last; a combined transfer
  code becomes all its clubs; teams are exactly the schedule's clubs with no `;` codes; works when the season
  has no games yet), following `tests/` conventions.
- Python: a static test that every `docs/*.html` page contains the nav placeholder + `nav.js` and no leftover
  inline nav links, and that every page listed in `nav.js` exists.
- Manual/screenshot check at 1440px, ~1024px and 390px: menus, active state, search results, keyboard use,
  mobile search and menu.

## Left to the builder

- CSS details within the existing look (reuse `.nav-link` etc. from `style.css`), exact collapse breakpoint.
- How `nav.js` structures its code; whether matching precomputes normalized names on load.
- Exact wording of empty/error lines (keep them plain and specific).
