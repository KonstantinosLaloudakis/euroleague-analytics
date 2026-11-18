# Topical Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pages that open with nothing selected (Head-to-Head, Game Replay, Careers, Compare, Team Deep-Dive, Playmaking) show a labeled, topical default from a small pipeline-written `highlights.json`.

**Architecture:** `export_dashboard_data.py` gains a pure `build_highlights(...)` that picks the headline matchup, game of the round, standings leader, MVP top two and this round's top performers from structures it already builds, and writes `docs/data/current/highlights.json` (~2 KB). Each page, only when its URL selects nothing, fetches that file and applies its pick through a "quiet" selection path that neither writes the URL nor scrolls, with a short label; on any failure it keeps today's empty state.

**Tech Stack:** Python 3.12 + pytest (pipeline), vanilla JS (no build step), Plotly (existing).

**Spec:** `superpowers/specs/2026-11-18-topical-defaults-design.md` — read it before any task.

## Global Constraints

- Defaults apply only when the URL selects nothing; a deep link always wins.
- Defaults never write to the URL (no `history.replaceState`/`pushState`, no `?team=`, `?a=&b=`, `?season=&game=`) and never scroll the page.
- A visitor's own selection afterwards behaves exactly as today (URL updates, scroll if it did before) and removes the default label.
- No page downloads `dashboard.json` or `game_recaps.json` just to pick a default; pages fetch `data/current/highlights.json` (fetch failure, 404 or a `null` section → today's empty state, no console errors beyond the failed request).
- `highlights.json` shape exactly as in the spec ("`highlights.json`" section); every section may be `null`; the file is always written.
- No hardcoded season years in pipeline code (`tests/test_no_hardcoded_season.py`).
- Player names link via `PlayerLinks.link` (docs/player-links.js); pages using it load `<script src="player-links.js"></script>` before the page script (`tests/test_player_links_pages.py`).
- Labels: plain, short, in sentence case, e.g. "Next round's headline matchup · pick any two teams"; one shared CSS class `.topical-label` in `docs/style.css`.
- Tests: `C:/Users/klalo/PycharmProjects/pythonProject/.venv/Scripts/python.exe -m pytest tests/ -q`; `node --test tests/js/*.test.js`.
- Branch `feat/topical-defaults`; commit per task; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A deep link is present** (`h2h.html?a=OLY&b=PAN`, `team.html?team=BAR`, `network.html?team=RED`, `compare.html?a=…&b=…`, `replay.html?season=2025&game=…`, `player.html?code=…`): the page shows exactly what the link asks for and no label — manual check in each page task.
2. **`highlights.json` unreachable** (rename it locally, then restore and confirm `git status` clean): each page shows today's empty state, no crash — manual check in each page task.
3. **Address bar after load** is exactly the URL the visitor opened — manual check in each page task.
4. **No scroll on load** on Team Deep-Dive and Playmaking (their selection functions scroll today) — manual check in Task 2.
5. **Default game not in Replay data** (e.g. `game_of_round` points at a game missing from that season's `games.json`): Replay keeps its empty prompt — manual check in Task 3 (edit a local copy's gamecode, restore).

---

## File Structure

| File | Responsibility |
|---|---|
| `export_dashboard_data.py` (modify) | `build_highlights(...)` + write `highlights.json` |
| `tests/test_highlights.py` (create) | builder tests |
| `docs/data/current/highlights.json` (generated, committed) | the picks |
| `docs/style.css` (modify) | `.topical-label` |
| `docs/h2h.js`, `docs/team.js`, `docs/network.js` (modify) | team-based defaults (Task 2) |
| `docs/app.js` (Replay), `docs/compare.js` (modify) | game/player-pair defaults (Task 3) |
| `docs/player.js`, `docs/player.html`, `docs/about.html`, `CLAUDE.md` (modify) | Careers top performers + docs (Task 4) |

---

### Task 1: `build_highlights` and `highlights.json`

**Files:** Modify `export_dashboard_data.py` (new function near other pure helpers such as `build_mvp_race`; write the file where the other `docs/data/current` files are written, near `recap_path`); Create `tests/test_highlights.py`; Generate `docs/data/current/highlights.json`.

**Interfaces:**
- Produces: `build_highlights(teams: list, oracle: dict, game_control: dict, mvp: list, player_stats: list, recaps: dict, career_codes: set, season: int, round_num: int) -> dict` with exactly the spec's keys: `season`, `round`, `headline_matchup` (`{round, home, away}` | None), `game_of_round` (`{season, gamecode, round, home, away, home_score, away_score}` | None), `standings_leader` (str | None), `mvp_top2` (`[{name, code}, {name, code}]` | None), `top_performers` (`{round, players: [{name, team, pts, reb, ast, pir, game: {home, away, home_score, away_score}}]}` | None).
  - Inputs are the export's existing structures: `teams` (list of `{team, elo, position, …}`), `oracle` (`{predictions: [{Round, Local, Road, HomeWinProb, …}], …}`), `game_control` (`{game_of_round: {…}, …}`), `mvp` (ranked list with `player`), `player_stats` (`{name, code, …}`), `recaps` (output of `build_game_recaps()`: `{'rounds': {'<n>': [game, …]}, …}`; each game has `home`, `away`, `homePts`, `awayPts`, `homeRoster`, `awayRoster`, `topPerformer: {name, pts, reb, ast, pir}`), `career_codes` (set of codes with a career page).
- Pick rules (spec): headline = max combined Elo of the two teams among `oracle.predictions`, tie → `HomeWinProb` closest to 50; `game_of_round` copied with `season` added; leader = `position == 1`; `mvp_top2` = first two MVP-ranked players whose `player_stats` code is in `career_codes`, else None; top performers = latest round present in `recaps`, one per game, team from the roster containing the name, sorted by `pir` desc.

- [ ] **Step 1: Write failing tests** `tests/test_highlights.py` (small inline inputs): `test_headline_picks_max_combined_elo`, `test_headline_tie_breaks_on_closest_to_50`, `test_headline_none_without_fixtures`, `test_game_of_round_copied_with_season`, `test_standings_leader`, `test_mvp_top2_skips_players_without_career_page`, `test_mvp_top2_none_when_fewer_than_two`, `test_top_performers_latest_round_sorted_by_pir_with_team_and_score`, `test_all_sections_none_on_empty_inputs`, `test_output_is_json_serializable`.
- [ ] **Step 2: Run** `-m pytest tests/test_highlights.py -q` — FAIL (import error).
- [ ] **Step 3: Implement** `build_highlights` and call it in the export's main flow after its inputs exist; write `docs/data/current/highlights.json` (compact JSON, `ensure_ascii=False`). Career codes = values of the already-available `player_index.json` data (load it if the export doesn't hold it).
- [ ] **Step 4: Run** the new tests and `tests/test_no_hardcoded_season.py` — PASS.
- [ ] **Step 5: Generate the file without the full export:** a one-off `python -c` that loads `docs/data/current/dashboard.json` (teams, oracle, game_control, mvp, player_stats, season, round), `docs/data/current/game_recaps.json` and `player_index.json` values, calls `build_highlights`, and writes the file. Check: every section non-null with current data; < 5 KB.
- [ ] **Step 6: Run** the full suite — PASS. **Commit** `feat(highlights): export highlights.json with topical picks`.

---

### Task 2: Team-based defaults — Head-to-Head, Team Deep-Dive, Playmaking

**Files:** `docs/h2h.js`, `docs/team.js`, `docs/network.js`, `docs/style.css` (add `.topical-label`).

**Interfaces:** Consumes `highlights.json` (`headline_matchup`, `standings_leader`).

- `h2h.js`: when neither `?a` nor `?b` is set, set the dropdowns to `headline_matchup.home` / `.away` and render without `history.replaceState` (today `onSelectionChange` writes the URL and scrolls — give it a quiet option); label "Next round's headline matchup · pick any two teams".
- `team.js`: when no `?team`, open `standings_leader`'s deep-dive below the grid without writing the URL and without scrolling (`selectTeam` writes `?team=` and scrolls — add a quiet option, the `{explicit: false}` pattern from `docs/game-control.js`); label "Standings leader · pick any team" at the top of the deep-dive.
- `network.js`: when no `?team`, open `standings_leader` instead of the alphabetical first, quietly; same label style.
- A visitor's own pick: label removed, URL/scroll behavior as today.

- [ ] **Step 1: Implement** the three pages + `.topical-label` CSS.
- [ ] **Step 2: Run** both suites — PASS.
- [ ] **Step 3: Verify** (local server: `cd docs && python -m http.server 8765 --bind 127.0.0.1`; headless Chrome or the Playwright MCP tools if available; evidence in the git-ignored `.superpowers/sdd/<plan>/task2-shots/`): defaults + labels on all three; Review Focus 1–4 on each; a manual pick afterwards updates the URL and drops the label.
- [ ] **Step 4: Commit** `feat(defaults): topical defaults on Head-to-Head, Team Deep-Dive, Playmaking`.

---

### Task 3: Game and player-pair defaults — Game Replay, Compare

**Files:** `docs/app.js` (Replay), `docs/compare.js`.

**Interfaces:** Consumes `highlights.json` (`game_of_round`, `mvp_top2`).

- `app.js`: when no `?season`/`?game`, select `game_of_round.season` and its game once the season's games list has loaded — only if that gamecode exists in it (else keep the empty prompt); no URL write; label e.g. "Round 12's most dramatic game · pick any game" (round from the data). Note the existing URL-param path polls with a 5 s timeout; the default must wait for the games list properly (e.g. hook the season-change load's completion), not poll.
- `compare.js`: when no `?a`/`?b`, fill both slots from `mvp_top2` codes without writing `?a=&b=`; label "MVP race #1 vs #2 · pick any two players".

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run** both suites — PASS.
- [ ] **Step 3: Verify:** defaults + labels; Review Focus 1–3 on both; Review Focus 5 on Replay; a manual pick afterwards updates the URL and drops the label.
- [ ] **Step 4: Commit** `feat(defaults): topical defaults on Game Replay and Compare`.

---

### Task 4: Careers top performers and docs

**Files:** `docs/player.js` (`showWelcome`, ~line 203), `docs/player.html` (add `<script src="player-links.js"></script>` before `player.js`), `docs/about.html`, `CLAUDE.md`.

**Interfaces:** Consumes `highlights.json` (`top_performers`); `PlayerLinks.ready/link` (docs/player-links.js).

- Under the existing search box, a "Round N's top performers" section: one row per player — name linked via `PlayerLinks.link`, team code, short line `"27 PIR · 14 pts · 6 reb · 7 ast"`, game score e.g. `"DUB 80–75 IST"`. Missing/`null` → section absent (search page as today). Await `PlayerLinks.ready` alongside the highlights fetch.
- `about.html`: one sentence (spec "Other changes"); `CLAUDE.md` Key Data Files: `docs/data/current/highlights.json` — topical picks for page defaults, written by `export_dashboard_data.py`.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Run** both suites (the player-links guard test now covers `player.html`) — PASS.
- [ ] **Step 3: Verify:** section renders with links to the right career pages; Review Focus 2 (section absent, search still works); `player.html?code=003469` unchanged.
- [ ] **Step 4: Commit** `feat(defaults): Careers shows this round's top performers; docs`.
