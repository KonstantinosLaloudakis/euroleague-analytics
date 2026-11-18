# UI/UX backlog

From the full-site review on 2026-11-18: all 19 pages at desktop (1440px) and phone (390px) widths, including
the states after picking a team, player or game. Ordered by impact within each section. Finished items move to
"Done" at the bottom with their merge commit.

## Make the site work like a reference site

3. **One name format everywhere** — *in progress on branch `feat/name-format`* (spec:
   `superpowers/specs/2026-11-18-name-format-design.md`). "Sasha Vezenkov" where there's room, "S. Vezenkov" when
   narrow or on phones, surname inside charts; one shared formatter (`docs/names.js`).

## Consistency and first impression

4. **One page-header style.** There are three today: a centered purple gradient title with an emoji (most
   pages), a plain left-aligned heading (Records, Lineups, Title Race) and no header (Compare, Careers,
   Series). Several emoji show up as plain purple squares (Season Hub, Game Recap). The big header also takes
   ~230px on every page before any data. Use one compact header everywhere.
5. **Season Hub should lead with what's new.** The first screen is spent on vanity stats (20 seasons /
   5,000+ / 2M+). Returning visitors want last night's results and the standings. Lead with a results strip
   for the latest round plus one featured story (e.g. the Maccabi–Olympiacos double buzzer-beater), then the
   standings.
6. **Use the team logos.** `docs/logos/` has all of them, but the team picker, standings, recap cards and
   Head-to-Head use text badges.

## Color and readability

7. **Standings odds columns:** Top 4 / Top 6 / Top 10 use three different hues (purple, green, blue) for the
   same kind of number. Use one hue that gets darker as the odds rise.
8. **Team names written in team colors** are hard to read for dark brand colors (Fenerbahce navy, Bayern
   blue, Real Madrid purple-grey) on the dark background. Use neutral text with a small team-color chip or the
   logo beside it.
9. **Traffic-light text colors** in Shot Lab paint profiles and elsewhere (green/yellow/red percentages) are
   hard to read and rely on color alone. Use neutral text, with color as a secondary cue.
10. **MVP Race timeline uses smoothed curves**, which overshoot between rounds (lines bulge above values that
    never happened). Use straight segments.

## Mobile

11. **Wide tables are cut off with no sign they scroll sideways** (standings, GCI leaderboard, Lineups,
    Player Stats). Add a sticky first column and an edge fade so it's clear there's more.
11b. **Pages that scroll sideways on phones** (measured 2026-11-18 at 390px): Game Recap with a game expanded
    (page 624px wide), Compare (481px), and career pages `player.html?code=…` (406px). Present before the name-format
    work; find the wide element on each and constrain it.
12. **Game Recap round picker** wraps with round 12 alone on a second line. Make it a single scrollable row
    or a dropdown on phones.
13. **Small scatter-plot labels overlap** on GCI History / Game Control ("Control vs Drama") and the Season
    Hub power ratings. Label only the notable teams on phones and show the rest on tap.

## Small things

14. **Filters on Player Stats and Records** stack as full-width bars. Put them on one row.
15. **Series page** is a bare list of links ("Quarterfinal 1 — OLY vs MCO") with no header. Show each series
    as a card with logos and the series score.
16. **Spelling:** the brand says "Euroleague"; the competition's own spelling is "EuroLeague". Pick one.
17. **Game Replay deep links** (`replay.html?season=…&game=…`) give up after 5 seconds of waiting for the game
    list and fail silently. Couldn't confirm in a real browser (seen only in headless Chrome), but a slow phone
    connection would hit the same limit. Wait for the list to load instead of polling with a timeout, and show
    a message if the game isn't available yet.
18. **Bare error states:** e.g. Careers shows only "Player not found: P003469" on an empty page. Say what
    happened and link to search.
19. **Pace page polish** (checked 2026-11-18): the "Pace vs league average" chart's x-axis label is clipped at
    390px; team names in the team chart and the extremes tables aren't links to Team Deep-Dive; historical clubs
    show only codes (CSK, LJU, GAL) — add names or a tooltip; the page sits under the Teams menu though it's
    league-wide (Season or History would fit — owner's call).
20. **No favicon:** every page logs a 404 for `/favicon.ico`. Add a small icon and a `<link rel="icon">`.

## Data gaps seen on the site (not UI, but visible)

- **Players with few games have no career page.** `fetch_player_career_stats.py` uses the API's per-game season
  stats, which omit low-game players (this season's rows start at 7 GP). On 2026-11-18, 13 of 255 current players
  (5–6 GP, e.g. Antonio Reeves, Nikola Djurisic) and ~4% of Lineups names had no page, so their names can't link.
  Fix in the pipeline (fetch without the minimum, or build those players' rows from box scores).

- MVP Race timeline has no rounds 10–11: no rankings were saved while the refresh workflow was failing
  (fixed 2026-11-18). They can't be rebuilt exactly; leave the gap or reconstruct approximately.

## Done

- **Bug batch** (2026-11-18, `30cccf5a`): MVP scoring order (WPA before MVP), MVP race timeline, game counts,
  About copy, Game Control auto-scroll, mobile chart fixes.
- **Grouped navigation + player/team search** (2026-11-18, merge `0ef745ef`): four menus, search box with `/`
  shortcut, nav in one file (`docs/nav.js`). Spec: `superpowers/specs/2026-11-18-nav-and-search-design.md`.
- **1. Player names link to career pages** (2026-11-18, merge `6625c1d7`): tables on H2H, Shot Lab, Playmaking,
  Lineups, Compare, MVP, Recap; Season Hub MVP bars and MVP timeline clicks (two taps on phones); shared
  `.player-link` style. Players without a career page stay plain text (see Data gaps).
  Spec: `superpowers/specs/2026-11-18-player-links-design.md`.
- **2. Topical defaults for pages that open empty** (2026-11-18, merge `8be674e7`): H2H headline matchup, Replay
  game of the round, Careers top performers, Compare MVP #1 vs #2, Team/Playmaking standings leader — from
  `highlights.json`. Spec: `superpowers/specs/2026-11-18-topical-defaults-design.md`.
