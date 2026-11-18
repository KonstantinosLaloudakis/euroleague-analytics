# UI/UX backlog

From the full-site review on 2026-11-18: all 19 pages at desktop (1440px) and phone (390px) widths, including
the states after picking a team, player or game. Already done and removed from this list: the bug batch
(MVP scoring order, MVP timeline, game counts, About copy, Game Control auto-scroll, mobile chart fixes) and
grouped navigation + search (in design: `superpowers/specs/2026-11-18-nav-and-search-design.md`).

Ordered by impact within each section. Start with the top section.

## Make the site work like a reference site

1. **Link every player name to its career page.** Only Team Deep-Dive, Player Stats, Game Recap and Records do
   it today. Missing on: Season Hub (MVP top 10), MVP Race (ladder and timeline), Head-to-Head (key players),
   Shot Lab (paint profiles), Playmaking (combo and playmaker tables), Lineups, Compare, Series. The player
   pages are good but hard to reach. Code format is `player.html?code=003469` (no `P` prefix).
2. **Give pages that open empty a useful default.** Today they open to a blank picker:
   - Careers (`player.html`): just a search box on an empty page. Show all-time leaders, this round's top
     performers, or recently viewed players under the search.
   - Compare: two empty search boxes, no header. Prefill a topical pair (e.g. this season's top 2 MVP
     candidates) with a "pick your own" prompt.
   - Head-to-Head: pre-select next round's biggest matchup.
   - Team Deep-Dive: a grid of 20 name cards. Open on the standings leader, or show logos plus each team's form.
   - Game Replay: open the latest round's most dramatic game.
   - Playmaking: defaults to ASVEL because it's first alphabetically. Default to the team with the best
     assist network, or remember the visitor's last pick.
3. **One name format everywhere.** The same player appears as "VEZENKOV, SASHA" (Player Stats, Careers,
   Records, Lineups, Shot Lab), "S. Vezenkov" (MVP) and "Vezenkov" (Playmaking). Use "Sasha Vezenkov" in
   tables and "S. Vezenkov" only where space is tight. Lineups is the worst case: five all-caps
   "LAST, FIRST" names joined with commas form an unreadable block.

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

## Data gaps seen on the site (not UI, but visible)

- MVP Race timeline has no rounds 10–11: no rankings were saved while the refresh workflow was failing
  (fixed 2026-11-18). They can't be rebuilt exactly; leave the gap or reconstruct approximately.
