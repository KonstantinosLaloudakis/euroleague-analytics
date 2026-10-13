# Game Records Engine — Design

**Date:** 2026-10-14
**Status:** Approved in chat, pending spec review
**Builds on:** `superpowers/specs/2026-10-14-biggest-comebacks-design.md` (shipped)

## Goal

Turn the comebacks scan into a reusable **Game Records engine**: one cleaned pass over every play-by-play game since 2007-08. The pass feeds two new all-time record boards on the All-Time Records page:

- **Game Highs:** single-game player records for Points, Rebounds, Assists, Threes and PIR, rebuilt from play-by-play.
- **Game-Winners:** made field goals in the last 10 seconds of the 4th quarter or OT that gave the eventual winner the lead for good, plus career leaders.

Runs, lead changes and extremes (blowouts, highest-scoring games) are **out of scope**. The engine is shaped so they can be added later as further analyzers.

## Findings that shape the design (verified on real data, 2026-10-14)

- **Box scores from play-by-play are reliable.**
  - 2024-25 and 2025-26 player-games match the official boxes (`mvp_all_game_stats_{s}.json`): 100% for points, assists and threes, 99.99% for rebounds, and 99.9%+ for PIR (max off by 2).
  - Season totals vs `player_career_stats.json`:
    - Points match for every player-season from 2016-17 on.
    - Before that, nearly every mismatch is explained by games missing from the play-by-play (2012-13: 16 players, 2018-19: 14). A few small unexplained gaps remain in 2007-09.
- **Older seasons use more play types.**
  - Made 2s are also `DUNK` and `LAYUPMD`.
  - Missed attempts are also `LAYUPATT`, `2FGAB` and `3FGAB` (blocked attempts). These must count as misses: dropping them breaks PIR in 2015-16 (19/159 match instead of 148/159).
  - Some `PLAYTYPE` values carry trailing spaces, so they must be stripped.
- **Player codes:** play-by-play `PLAYER_ID` is `P` + the career-page code (`P012774` → `012774`, as used by `player.html?code=`).
- **Game-winner volume:** go-ahead-for-good made field goals in Q4/OT come to about 180 in the final 10 s, about 150 in the final 5 s, and about 90 at 0:01 or less. Go-ahead free throws in the final 10 s add about 70 more; they are excluded.

## Architecture

```
calculate_game_records.py   (entry point; one pass; writes 3 JSON files)
  ├─ pbp_games.py           clean_game(g) -> CleanGame | None ; iter_games(seasons)
  │                         rank_by(...) ; finish_rows(...) ; write_json_if_changed(...)
  ├─ calculate_comebacks.py analyze_clean(cg) -> comeback record     (existing, refactored)
  ├─ game_highs.py          analyze_clean(cg) -> list of player-game lines
  └─ game_winners.py        analyze_clean(cg) -> game-winner record | None
```

### `pbp_games.py`: shared cleaning (single source of truth)

`clean_game(g: pd.DataFrame) -> CleanGame | None` moves the cleaning steps that already exist in `calculate_comebacks.analyze_game` into one place. The behaviour must be identical:

1. Choose the sort key: `TRUE_NUMBEROFPLAY` if present and fully non-null, else `NUMBEROFPLAY`. Drop duplicates on (key, `PLAYTYPE`, `CODETEAM`).
2. `pd.to_numeric(errors='coerce')` on `POINTS_A`, `POINTS_B` and `PERIOD`. Add a stripped `PT` column (from `PLAYTYPE`) and a `PID` column: `PLAYER_ID` stripped, with one leading `P` removed (NaN stays NaN).
3. Stable sort by `['PERIOD', key]`.
4. The scoring rows are those where either `POINTS_*` is non-null. Return None if any of these holds:
   - there are fewer than 30 of them
   - the max scoring `PERIOD` is below 4
   - after forward-fill and fill-0, the final is tied
   - either final is under 45
5. Team codes and names are the mode of `CODETEAM` / `TEAM` on rows where that side's score increases.

`CleanGame` (a dataclass) exposes:
- `season, phase, round, gamecode` (same parsing as today)
- `rows` (all rows, sorted, with `PT` / `PID`)
- `sc` (scoring rows, reset index)
- `a, b` (int score lists), `periods, clocks` (scoring rows)
- `final_a, final_b, a_won`
- `code_a, name_a, code_b, name_b`
- `ot` (max `PERIOD` > 4)

The constants `MIN_SCORING_ROWS`, `MIN_FINAL`, `LAST_REGULATION_PERIOD` and `GLITCH_TOL` move here. `calculate_comebacks.py` imports what it needs.

Shared helpers:
- `iter_games(seasons=ALL_SEASONS, cache_dir='data_cache')` yields a `CleanGame` for every usable game. A missing season file prints a warning and is skipped (same as today).
- `rank_by(records, key, limit=25)` is today's `rank_entries` generalized:
  - keeps records with `key > 0`
  - sorts by value desc, then season desc, then gamecode desc
  - counts ties before the cut
  - returns new dicts with `rank` and `tied`
- `finish_rows(rows, replay_dir)` adds `season_label` and `has_replay`.
- `keep_generated_date(old, new, content_keys)` and `write_json_if_changed(path, out, content_keys)` hold the current stable-`generated` logic, generalized.

### `calculate_comebacks.py`: refactor, no behaviour change

- `analyze_game(g)` stays, as `clean_game(g)` followed by `analyze_clean(cg)`, so existing tests keep calling it unchanged.
- `analyze_clean(cg)` holds the deficit logic (confirmed margins, `worst()`, q4).
- `rank_entries(records, limit)` stays as `rank_by(records, 'deficit', limit)`.
- `build_output` keeps its signature and output.
- `main()` / `load_records()` are removed. `calculate_game_records.py` is the only entry point.
- **Acceptance:** after the refactor, regenerating `docs/data/current/comebacks.json` gives byte-identical output, and every existing test passes. The only test edit allowed is pointing `keep_generated_date` tests at the shared helper.

### `game_highs.py`

`analyze_clean(cg) -> list[dict]` returns one line per player who has any event in the game. It uses `cg.rows` where `PID` is non-null, grouped by `PID`:

| Stat | Counting rule (`PT`) |
|---|---|
| points | `2FGM`, `DUNK`, `LAYUPMD` = 2; `3FGM` = 3; `FTM` = 1 |
| rebounds | `D` + `O` |
| assists | `AS` |
| threes | `3FGM` |
| pir | points + (`D`,`O`,`AS`,`ST`,`FV`,`RV`) − (`2FGA`,`3FGA`,`FTA`,`2FGAB`,`3FGAB`,`LAYUPATT`) − (`TO`,`AG`) − (`CM`,`OF`,`CMT`,`CMU`,`CMD`,`CMTI`,`C`,`B`) |

- **Team:** each line's team is the mode of that player's `CODETEAM`.
- **Fields:** `player` (code), `player_name` (mode of `PLAYER`, as recorded, e.g. `"ROBINSON, JUSTIN"`), `team`, `opp`, `home` (team == `code_a`), `won`, `final` (`"{team pts}-{opp pts}"`, from the player's team's side), `ot`, `season, phase, round, gamecode`, and `line: {points, rebounds, assists, threes, pir}`.
- A line whose team matches neither `code_a` nor `code_b` is dropped.

`build_output(lines, current_season, replay_dir, generated=None)` returns:
- `generated, seasons, current_season, games_scanned`
- and five lists: `points, rebounds, assists, threes, pir`

Each list is `rank_by` on that stat (top 25). Each entry carries `value` (the stat) plus all line fields. The rows then go through `finish_rows`.

### `game_winners.py`

`analyze_clean(cg) -> dict | None`:
1. Compute the winner's margin per scoring row. Let `j` be one past the last index where margin ≤ 0. If there is no such index, or `j` is past the end, return None.
2. Row `j` qualifies only if all of these hold:
   - `PT` ∈ {`2FGM`,`3FGM`,`DUNK`,`LAYUPMD`}
   - `CODETEAM` is the winner's code
   - `PERIOD` ≥ 4
   - `MARKERTIME` parses as `mm:ss` with total seconds ≤ `WINDOW_SECONDS = 10`
   - **Glitch guard:** the winner's score rose by exactly the shot value (3 for `3FGM`, else 2) from row `j-1` to row `j`, and the loser's score is unchanged.
3. Return:
   - `player` (`PID`), `player_name`, `team`, `opp`, `home`
   - `season, phase, round, gamecode`
   - `quarter`, `clock` (string), `seconds_left` (int)
   - `points` (2 or 3), `shot` (`"3PT"`, `"2PT"`, `"Dunk"`, `"Layup"`)
   - `before` / `after` (`"{winner}-{loser}"` scores at rows `j-1` and `j`)
   - `final`, `ot`
   - `buzzer` (`seconds_left` ≤ 1)

`build_output(records, current_season, replay_dir, generated=None)` returns:
- `generated, seasons, current_season, games_scanned, window_seconds`
- `all`: every record, newest first (season desc, gamecode desc), finished.
- `buzzer_beaters`: the `buzzer` subset, same order.
- `leaders`: one row per player with `player, player_name, count, buzzer_count, last_season_label`, sorted by count desc, then buzzer_count desc, then most recent season desc. Top 25, with rank and tied (ties on `count`).

### `calculate_game_records.py`

- `main()` iterates `iter_games()` once and calls the three `analyze_clean` functions. It writes, via `write_json_if_changed`:
  - `docs/data/current/comebacks.json` (unchanged schema)
  - `docs/data/current/game_highs.json`
  - `docs/data/current/game_winners.json`
- It prints one summary line per file.
- `games_scanned` is the same count in all three files.

### Pipeline

- `refresh_all.py` Phase 2: the "Biggest Comebacks" step becomes "Game Records" and runs `calculate_game_records.py`.
- `.github/workflows/wp_replay_update.yml`: the step becomes "Compute Game Records", runs `python calculate_game_records.py`, and keeps `continue-on-error: true`.
- `tests/test_no_hardcoded_season.py`: add `pbp_games.py`, `game_highs.py`, `game_winners.py` and `calculate_comebacks.py` to the always-scanned set, since they are imported rather than named in `refresh_all.py`. No literal years `\b202[5-9]\b` may appear in any of them outside `#` comments.

## Frontend: `docs/records.js` / `records.html`

- **Tabs:** add `{key:'highs', label:'Game Highs'}` and `{key:'winners', label:'Game-Winners'}` after Comebacks.
- **Shared loader:** generalize the lazy loader into one `loadJson(url)` that returns the data or `{error:true}`. Comebacks, highs and winners each cache their own result. `_activeTab` is set only after the load completes (same as today). The error message is the same pattern as Comebacks.
- **Hidden filter:** the career-minimum filter is hidden on both new tabs. Each tab shows a one-line legend:
  - Game Highs: "Single-game bests rebuilt from play-by-play · {N} games since 2007-08 · click a game for its replay"
  - Game-Winners: "Made field goals in the last 10 seconds of the 4th quarter or OT that gave the winner the lead for good"
- **Game Highs:** five cards (Points, Rebounds, Assists, Threes, PIR) in the existing `.records-grid` (3 + 2 on desktop, stacked on mobile). Top 10, with "Show top 25". Columns: # · Player · Game · value.
  - **Player cell:** the name, linking to `player.html?code={player}`. Under it, a meta line: `{team} · {season_label} · {stage}`.
  - **Game cell:** `vs OPP` / `@ OPP`, linking to the replay when `has_replay`. Under it, `W 102-97` or `L 88-91` (plus ` OT`).
  - **Value cell:** the value, large. Under it, the full line: `41 PTS · 7 REB · 3 AST · 45 PIR` (threes shown only on the Threes card as `8 3PM`).
  - **Rank:** `T-n` when tied. The NEW tag shows when the season equals `current_season`.
- **Game-Winners:** three cards.
  - **All Game-Winners:** newest first, top 10. The expander shows every row ("Show all N").
  - **Buzzer-Beaters:** newest first, top 10, with "Show all N".
  - **Most Game-Winners:** columns # · Player · GW · Buzzer; top 10, with "Show top 25".
  - Shot rows show:
    - the player (linked to the career page), with meta `OLY @ PAM · 2026-27 · RS R5` (the matchup links to the replay)
    - the shot, `3PT · Q4 0:01`, with a `BUZZER` badge when `buzzer` is set
    - the score, `go-ahead 80-77 · final 85-80` (plus ` OT`)
  - The NEW tag works as on Comebacks.
- **Reuse:** the existing card, table, rank-colour, NEW-tag and `esc()` helpers. The show-more logic gains an "all rows" variant for the two shot lists.
- **Meta description:** add "single-game highs and game-winners".

## About page (`docs/about.html`, All-Time Records section)

Add two h4 entries after "Biggest Comebacks":
- **Game Highs:** box scores are rebuilt from play-by-play. List the counting rules in plain language, including that old-format dunks, layups and blocked attempts count. State that the rebuilt boxes match the official ones for 2024-25 and 2025-26. State that ties share a rank, newest first.
- **Game-Winners:** the definition (made field goal in the last 10 s of Q4/OT that gave the eventual winner the lead for good; free throws excluded; ≤ 0:01 marked as a buzzer-beater). The clock in play-by-play has 1-second resolution.
- **Coverage note** (shared by the comebacks, highs and game-winners entries): only games with play-by-play are included. A few 2012-13 and 2018-19 games are missing from the source, and a game whose log ends before the 4th quarter is skipped.

## Testing

- **Shared fixture:** move the made-up PBP builder from `tests/test_comebacks.py` into `tests/pbp_fixtures.py`. Extend it so a leg can carry a player (`PLAYER_ID`, `PLAYER`) and a play type, and so non-scoring events (`D`, `AS`, `TO`, …) can be inserted.
- **`tests/test_pbp_games.py`:** sorting by period then play number, numeric coercion, the skip rules (30 rows, final < 45, tie, ends before Q4), `PID` stripping (`P012774` → `012774`), team code and name detection, `rank_by` ties and cutoff, `keep_generated_date`.
- **`tests/test_comebacks.py`:** unchanged except imports and the moved `keep_generated_date` test. All existing tests still pass.
- **`tests/test_game_highs.py`:**
  - counting rules for each stat, including `DUNK` / `LAYUPMD` = 2, `2FGAB` / `LAYUPATT` as misses, and fouls
  - PIR formula on a hand-built line
  - team, opponent, home and won detection
  - `build_output` lists ranked per stat with ties
- **`tests/test_game_winners.py`:**
  - a 3 at Q4 0:01 that takes the lead for good counts (buzzer true)
  - a go-ahead shot at 0:15 doesn't count (outside the window)
  - a go-ahead shot at 0:05 followed by an opponent tie and an OT win doesn't count; only the OT go-ahead can count
  - a go-ahead free throw doesn't count
  - a row whose score jump doesn't equal the shot value doesn't count
  - a Q3 go-ahead doesn't count
  - `leaders` counting and ordering
- **Real-data verification** (plan step, not a unit test):
  - `comebacks.json` is byte-identical before and after the refactor.
  - For 2024-25 and 2025-26, every rebuilt player-game line matches the official box for at least 99.9% of player-games on points, rebounds, assists and threes, and at least 99.5% on PIR.
  - `game_winners.json` contains season 2026, gamecode 44, Justin Robinson, `3PT`, Q4, `buzzer: true`.
  - Total game-winners are between 150 and 220.

## Out of scope

Runs, lead changes and ties, blowouts, highest- and lowest-scoring games, team or player streaks, "on this day", and per-season filters on the new tabs.
