# Topical defaults for pages that open empty — design

Date: 2026-11-18 · Status: approved by owner 2026-11-18 (builder check: nothing important left)

Builder-check calls: a top performer's team is derived from the game's `homeRoster`/`awayRoster`; `mvp_top2` maps
MVP names to codes through `player_stats`; playoffs/off-season fall under the "fall back to empty state" rule.

## Why

Visitors arriving cold (the site is shared on LinkedIn) land on pages that show a blank picker: Careers, Compare,
Head-to-Head and Game Replay open empty; Team Deep-Dive shows a grid of names; Playmaking defaults to ASVEL only
because it's alphabetically first. Every page should show something worth seeing immediately — something topical
from the current round — while staying one click from choosing anything else. Backlog item 2 in
`superpowers/ui-ux-backlog.md`. The owner chose **topical** defaults (not "remember the visitor's last pick").

## Goals

| Page | Opens on (when the URL selects nothing) | Label shown |
|---|---|---|
| Head-to-Head (`h2h.html`) | Next round's headline matchup | e.g. "Next round's headline matchup · pick any two teams" |
| Game Replay (`replay.html`) | The latest round's most dramatic game ("game of the round") | e.g. "Round 12's most dramatic game · pick any game" |
| Careers (`player.html`, no `code`) | The existing search box, plus a "This round's top performers" list linking to career pages | section heading |
| Compare (`compare.html`) | The current #1 vs #2 of the MVP race | e.g. "MVP race #1 vs #2 · pick any two players" |
| Team Deep-Dive (`team.html`) | Team grid stays; the standings leader's deep-dive opens below it | e.g. "Standings leader · pick any team" |
| Playmaking (`network.html`) | The standings leader's assist network (instead of ASVEL) | same style |

## Non-goals

- Remembering the visitor's previous picks (owner chose topical).
- Changing what a page shows once the visitor picks something, or any page with no empty state.
- New metrics: picks come from data the pipeline already computes.

## Anti-goals (failure even if it works)

- **Defaults leaking into URLs.** A default must not write `?team=`, `?a=&b=`, `?season=&game=` etc. into the address
  bar — shared links stay clean, and a reload still shows the current topical default rather than a frozen one.
- **Defaults overriding a deep link.** If the URL selects something, it wins; defaults apply only to an empty state.
- **Page jumping on load.** A default must not scroll the page (Team Deep-Dive currently scrolls on selection).
- **Heavier pages.** No page may download `dashboard.json` (≈670 KB) or `game_recaps.json` (≈550 KB) just to pick a
  default.
- **Breaking when picks are missing** (early season, off-season, playoffs, failed fetch): the page falls back to
  today's empty state, with no error.

## Constraints

- Static GitHub Pages site from `docs/`, vanilla JS, no build step; pipeline in Python, export via
  `export_dashboard_data.py` (bridge to the frontend; writes `docs/data/current/*.json`).
- Season/round from `season_config` / the export's `round_num`; no hardcoded years (`tests/test_no_hardcoded_season.py`).
- Existing data the picks come from (all already built inside the export):
  - Next round's fixtures: `oracle['predictions']` — list of `{Round, Local, Road, LocalName, RoadName, HomeWinProb, …}`.
  - Current Elo and standings: the dashboard `teams` list (`team`, `elo`, `position`, …).
  - Game of the round: `gci_data['game_of_round']` — `{gamecode, round, home, away, home_score, away_score, drama, …}`.
  - MVP race: dashboard `mvp` (ranked, `player` names) and `player_stats` (`name`, `code`).
  - Latest round's top performers: `build_game_recaps()` → `rounds[<round>][i]['topPerformer']` =
    `{name, pts, reb, ast, pir}` plus the game's `home`, `away`, scores.
  - Career pages exist only for codes in `player_index.json` / career data (some low-game players have none).
- Page selection code today: `team.js selectTeam` writes `?team=` and scrolls; `network.js selectTeam` writes
  `?team=`; `compare.js` reads `?a=&b=` (career codes); `h2h.js` reads `?a=&b=` (team codes); `app.js` (Replay)
  reads `?season=&game=` and fills its selects; `player.js` shows `showWelcome()` when there's no `code`.
- `docs/player-links.js` (`PlayerLinks.link/url`) is the way to link player names.

## Approaches considered

- **A. Each page computes its default from data it already loads.** Easy for Head-to-Head/Team (they load the
  dashboard), but Replay, Careers and Playmaking would each need a 550–670 KB download just to pick a default, and the
  "what's topical" rules would be spread over six files. Rejected.
- **B. The pipeline writes one small `docs/data/current/highlights.json` (chosen).** One pure, tested Python function
  decides every pick; pages fetch ~2 KB. Picks refresh with every pipeline run. Cost: a pipeline change, and new
  defaults appear after the next run.

## Design

### `highlights.json` (written by `export_dashboard_data.py`)

A pure function `build_highlights(...)` (inputs: the already-built teams, oracle, game-control, mvp, player_stats and
recaps structures plus the set of career codes; output: a dict) in `export_dashboard_data.py`, written next to the
other current-season files. Shape:

```json
{
  "season": 2026, "round": 12,
  "headline_matchup": {"round": 13, "home": "PRS", "away": "HTA"},
  "game_of_round": {"season": 2026, "gamecode": 112, "round": 12,
                    "home": "ZAL", "away": "MUN", "home_score": 117, "away_score": 114},
  "standings_leader": "PAM",
  "mvp_top2": [{"name": "VEZENKOV, SASHA", "code": "003469"}, {"name": "…", "code": "…"}],
  "top_performers": {"round": 12, "players": [
    {"name": "MUSA, DZANAN", "team": "DUB", "pts": 14, "reb": 6, "ast": 7, "pir": 27,
     "game": {"home": "DUB", "away": "IST", "home_score": 80, "away_score": 75}}
  ]}
}
```

Pick rules *(Claude's calls)*:
- **headline_matchup:** among next-round fixtures, the one with the highest combined current Elo of the two teams;
  ties → the one whose `HomeWinProb` is closest to 50. No fixtures → `null`.
- **game_of_round:** copied from the game-control data; `null` if absent.
- **standings_leader:** team with `position == 1`; `null` if no standings.
- **mvp_top2:** the first two MVP-ranked players who have a career page (code in the career set); fewer than two →
  `null`.
- **top_performers:** each game of the latest round that has recaps contributes its `topPerformer` (with the player's
  team — the side whose roster contains them — and the game score), sorted by PIR descending; empty → `null`.
- Any section that can't be computed is `null`; the file is always written (so a stale one never lingers).

### Pages (all: fetch `data/current/highlights.json` only when the URL selects nothing; on any failure or `null`
section, keep today's empty state)

- **Head-to-Head:** select `home`/`away` in the two dropdowns and render, without `history.replaceState`; show the
  label above the result. A visitor's own selection replaces the label and updates the URL as today.
- **Game Replay:** select the season and game from `game_of_round` (only if that game exists in the season's
  `games.json`; otherwise keep the empty prompt), without writing the URL; label above the chart.
- **Careers:** under the existing search box, a "This round's top performers" list (name linked via
  `PlayerLinks.link`, team, short stat line, game score). `player.html` must load `player-links.js`.
- **Compare:** fill both slots from `mvp_top2` codes without writing `?a=&b=`; label above.
- **Team Deep-Dive:** open the standings leader's deep-dive below the grid without writing `?team=` and without
  scrolling; label at the top of the deep-dive.
- **Playmaking:** open the standings leader's network without writing `?team=`; label as above.
- Pages that select via a function that writes the URL / scrolls get a "quiet" path (e.g. an
  `{explicit: false}` option, the pattern `game-control.js` already uses) rather than duplicated logic.

### Other changes

- `about.html`: one sentence — pages that open without a selection show this round's highlights.
- `CLAUDE.md`: list `docs/data/current/highlights.json` under Key Data Files.

### Testing

- pytest `tests/test_highlights.py` for `build_highlights`: headline pick by combined Elo + tie-break; no fixtures →
  `null`; standings leader; `mvp_top2` skips players without a career page and is `null` below two; top performers
  sorted by PIR with team and score; every section `null` on empty inputs; output is JSON-serializable.
- Manual/screenshot per page: empty URL → default with label and clean address bar, no scroll; a deep link still
  wins; `highlights.json` missing → today's empty state.

## Left to the builder

- Exact label wording (plain, short) and placement styling within each page's existing look.
- How each page structures its quiet-selection path.
