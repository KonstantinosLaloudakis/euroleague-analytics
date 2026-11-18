"""
Game Records engine: one pass over every cached play-by-play game.

Each usable game (pbp_games.iter_games) goes through the comebacks, game
highs, game-winners and pace analyzers, and the record boards are written
to docs/data/current/: comebacks.json, game_highs.json, game_winners.json,
pace.json.
"""
import calculate_comebacks as comebacks
import game_highs
import game_pace
import game_winners
from pbp_games import iter_games, write_json_if_changed
from season_config import CURRENT_SEASON


def collect(games):
    """Run every analyzer on each CleanGame -> (comebacks, highs lines, game-winners, paces)."""
    cbs, lines, winners, paces = [], [], [], []
    for cg in games:
        cbs.append(comebacks.analyze_clean(cg))
        lines.extend(game_highs.analyze_clean(cg))
        r = game_winners.analyze_clean(cg)
        if r:
            winners.append(r)
        p = game_pace.analyze_clean(cg)
        if p is not None:
            paces.append(p)
    return cbs, lines, winners, paces


def main():
    cbs, lines, winners, paces = collect(iter_games())
    n = len(cbs)
    outputs = [
        (comebacks.OUT_PATH, comebacks.build_output(cbs, CURRENT_SEASON), comebacks.CONTENT_KEYS),
        (game_highs.OUT_PATH, game_highs.build_output(lines, CURRENT_SEASON, n),
         game_highs.CONTENT_KEYS),
        (game_winners.OUT_PATH, game_winners.build_output(winners, CURRENT_SEASON, n),
         game_winners.CONTENT_KEYS),
        (game_pace.OUT_PATH, game_pace.build_output(paces, CURRENT_SEASON),
         game_pace.CONTENT_KEYS),
    ]
    for path, out, keys in outputs:
        write_json_if_changed(path, out, keys)
    print(f'Game records: {n} games scanned')
    highs, gws = outputs[1][1], outputs[2][1]
    if highs['points']:
        top = highs['points'][0]
        print(f"  Top scoring game: {top['player_name']} {top['value']} "
              f"({top['team']} vs {top['opp']}, {top['season_label']})")
    print(f"  Game-winners: {len(gws['all'])} ({len(gws['buzzer_beaters'])} buzzer-beaters)")
    league = outputs[3][1]['league']
    if league:
        print(f"  League pace {league[-1]['season_label']}: {league[-1]['pace']}")


if __name__ == '__main__':
    main()
