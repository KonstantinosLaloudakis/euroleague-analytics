import json

from export_dashboard_data import build_highlights


def _teams():
    return [
        {'team': 'AAA', 'elo': 1500, 'position': 1},
        {'team': 'BBB', 'elo': 1400, 'position': 2},
        {'team': 'CCC', 'elo': 1550, 'position': 3},
        {'team': 'DDD', 'elo': 1350, 'position': 4},
    ]


def _oracle(preds):
    return {'round': 13, 'predictions': preds}


def _call(**kw):
    args = dict(teams=[], oracle={}, game_control={}, mvp=[], player_stats=[],
                recaps={}, career_codes=set(), season=2026, round_num=12)
    args.update(kw)
    return build_highlights(**args)


def test_headline_picks_max_combined_elo():
    preds = [
        {'Round': 13, 'Local': 'AAA', 'Road': 'BBB', 'HomeWinProb': 50.0},
        {'Round': 13, 'Local': 'CCC', 'Road': 'AAA', 'HomeWinProb': 60.0},
        {'Round': 13, 'Local': 'BBB', 'Road': 'DDD', 'HomeWinProb': 50.0},
    ]
    h = _call(teams=_teams(), oracle=_oracle(preds))
    assert h['headline_matchup'] == {'round': 13, 'home': 'CCC', 'away': 'AAA'}


def test_headline_tie_breaks_on_closest_to_50():
    teams = [{'team': t, 'elo': 1500, 'position': i} for i, t in enumerate('ABCD', 1)]
    preds = [
        {'Round': 13, 'Local': 'A', 'Road': 'B', 'HomeWinProb': 80.0},
        {'Round': 13, 'Local': 'C', 'Road': 'D', 'HomeWinProb': 45.0},
    ]
    h = _call(teams=teams, oracle=_oracle(preds))
    assert h['headline_matchup'] == {'round': 13, 'home': 'C', 'away': 'D'}


def test_headline_none_without_fixtures():
    assert _call(teams=_teams(), oracle=_oracle([]))['headline_matchup'] is None
    assert _call(teams=_teams(), oracle={})['headline_matchup'] is None


def test_game_of_round_copied_with_season():
    gc = {'game_of_round': {'gamecode': 112, 'round': 12, 'home': 'ZAL', 'away': 'MUN',
                            'home_score': 117, 'away_score': 114, 'drama': 12.5,
                            'wp_curve': [[0, 0.5]]}}
    h = _call(game_control=gc)
    assert h['game_of_round'] == {'season': 2026, 'gamecode': 112, 'round': 12,
                                  'home': 'ZAL', 'away': 'MUN',
                                  'home_score': 117, 'away_score': 114}


def test_standings_leader():
    assert _call(teams=_teams())['standings_leader'] == 'AAA'


def _mvp():
    return [{'player': 'ONE, A'}, {'player': 'TWO, B'}, {'player': 'THREE, C'}]


def _stats():
    return [{'name': 'ONE, A', 'code': '1'}, {'name': 'TWO, B', 'code': '2'},
            {'name': 'THREE, C', 'code': '3'}]


def test_mvp_top2_skips_players_without_career_page():
    h = _call(mvp=_mvp(), player_stats=_stats(), career_codes={'1', '3'})
    assert h['mvp_top2'] == [{'name': 'ONE, A', 'code': '1'}, {'name': 'THREE, C', 'code': '3'}]


def test_mvp_top2_none_when_fewer_than_two():
    assert _call(mvp=_mvp(), player_stats=_stats(), career_codes={'2'})['mvp_top2'] is None


def _game(home, away, hp, ap, hr, ar, top):
    return {'home': home, 'away': away, 'homePts': hp, 'awayPts': ap,
            'homeRoster': [{'name': n} for n in hr], 'awayRoster': [{'name': n} for n in ar],
            'topPerformer': top}


def test_top_performers_latest_round_sorted_by_pir_with_team_and_score():
    recaps = {'rounds': {
        '11': [_game('X', 'Y', 1, 2, ['OLD'], ['OLD2'],
                     {'name': 'OLD', 'pts': 1, 'reb': 1, 'ast': 1, 'pir': 99})],
        '12': [
            _game('DUB', 'IST', 80, 75, ['MUSA'], ['KOS'],
                  {'name': 'MUSA', 'pts': 14, 'reb': 6, 'ast': 7, 'pir': 27}),
            _game('ZAL', 'MUN', 117, 114, ['Z1'], ['M1'],
                  {'name': 'M1', 'pts': 30, 'reb': 2, 'ast': 3, 'pir': 35}),
        ]}}
    tp = _call(recaps=recaps)['top_performers']
    assert tp['round'] == 12
    assert [p['name'] for p in tp['players']] == ['M1', 'MUSA']
    assert tp['players'][0] == {'name': 'M1', 'team': 'MUN', 'pts': 30, 'reb': 2, 'ast': 3,
                                'pir': 35, 'game': {'home': 'ZAL', 'away': 'MUN',
                                                    'home_score': 117, 'away_score': 114}}
    assert tp['players'][1]['team'] == 'DUB'


def test_all_sections_none_on_empty_inputs():
    h = _call()
    assert h == {'season': 2026, 'round': 12, 'headline_matchup': None, 'game_of_round': None,
                 'standings_leader': None, 'mvp_top2': None, 'top_performers': None}


def test_output_is_json_serializable():
    h = _call(teams=_teams(), game_control={'game_of_round': {'gamecode': 1, 'round': 1, 'home': 'A',
               'away': 'B', 'home_score': 1, 'away_score': 2}}, mvp=_mvp(),
              player_stats=_stats(), career_codes={'1', '2'})
    json.dumps(h, ensure_ascii=False)
