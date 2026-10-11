import json
import pandas as pd
from season_config import CURRENT_SEASON

def parse_game_data():
    with open(f'mvp_all_game_stats_{CURRENT_SEASON}.json', 'r') as f:
        games = json.load(f)
    
    player_stats_list = []
    game_results = []
    
    print(f"Parsing {len(games)} games...")
    
    for game in games:
        game_code = game.get('Gamecode')
        
        # Get team codes for standings (Winner logic needs Score)
        # But for player stats, use player's own club code to avoid mixups.
        
        local_players = game.get('local.players', [])
        road_players = game.get('road.players', [])
        
        # Infer Team Codes for Standings from first player if available
        # (This is still needed for W/L record assignment)
        local_team_standings = "UNKNOWN"
        if local_players:
             local_team_standings = local_players[0].get('player', {}).get('club', {}).get('code', 'UNKNOWN')
             
        road_team_standings = "UNKNOWN"
        if road_players:
             road_team_standings = road_players[0].get('player', {}).get('club', {}).get('code', 'UNKNOWN')

        local_points = 0
        road_points = 0
        
        # Process Local Players
        for p_entry in local_players:
            stats = p_entry.get('stats', {})
            info = p_entry.get('player', {})
            p_code = info.get('person', {}).get('code')
            p_name = info.get('person', {}).get('name')
            # USE PLAYER CLUB CODE DIRECTLY
            t_code = info.get('club', {}).get('code', local_team_standings)
            
            pts = stats.get('points', 0)
            local_points += pts
            
            # Game Score Calculation
            fgm = stats.get('fieldGoalsMadeTotal', 0)
            fga = stats.get('fieldGoalsAttemptedTotal', 0)
            ftm = stats.get('freeThrowsMade', 0)
            fta = stats.get('freeThrowsAttempted', 0)
            orb = stats.get('offensiveRebounds', 0)
            drb = stats.get('defensiveRebounds', 0)
            stl = stats.get('steals', 0)
            ast = stats.get('assistances', 0)
            blk = stats.get('blocksFavour', 0)
            pf = stats.get('foulsCommited', 0)
            tov = stats.get('turnovers', 0)
            
            gmsc = pts + 0.4*fgm - 0.7*fga - 0.4*(fta - ftm) + 0.7*orb + 0.3*drb + stl + 0.7*ast + 0.7*blk - 0.4*pf - tov
            
            player_stats_list.append({
                'PlayerCode': p_code,
                'PlayerName': p_name,
                'TeamCode': t_code,
                'GameCode': game_code,
                'GmSc': gmsc,
                'PIR': stats.get('valuation', 0),
                'PTS': pts
            })

        # Process Road Players
        for p_entry in road_players:
            stats = p_entry.get('stats', {})
            info = p_entry.get('player', {})
            p_code = info.get('person', {}).get('code')
            p_name = info.get('person', {}).get('name')
            # USE PLAYER CLUB CODE DIRECTLY
            t_code = info.get('club', {}).get('code', road_team_standings)
            
            pts = stats.get('points', 0)
            road_points += pts
            
            fgm = stats.get('fieldGoalsMadeTotal', 0)
            fga = stats.get('fieldGoalsAttemptedTotal', 0)
            ftm = stats.get('freeThrowsMade', 0)
            fta = stats.get('freeThrowsAttempted', 0)
            orb = stats.get('offensiveRebounds', 0)
            drb = stats.get('defensiveRebounds', 0)
            stl = stats.get('steals', 0)
            ast = stats.get('assistances', 0)
            blk = stats.get('blocksFavour', 0)
            pf = stats.get('foulsCommited', 0)
            tov = stats.get('turnovers', 0)
            
            gmsc = pts + 0.4*fgm - 0.7*fga - 0.4*(fta - ftm) + 0.7*orb + 0.3*drb + stl + 0.7*ast + 0.7*blk - 0.4*pf - tov
            
            player_stats_list.append({
                'PlayerCode': p_code,
                'PlayerName': p_name,
                'TeamCode': t_code,
                'GameCode': game_code,
                'GmSc': gmsc,
                'PIR': stats.get('valuation', 0),
                'PTS': pts
            })

        game_results.append({
            'GameCode': game_code,
            'LocalTeam': local_team_standings,
            'RoadTeam': road_team_standings,
            'LocalScore': local_points,
            'RoadScore': road_points,
            'Winner': local_team_standings if local_points > road_points else road_team_standings
        })

    print("Parsed Data Sample:")
    df_parsed = pd.DataFrame(player_stats_list)
    print(df_parsed.head(3))

    # Save Parsed Games (regular-season only — playoffs have GameCode > 380).
    # MVP ladder, per-round MVP, player performance models, and the MVP race
    # simulation all read this file and should see a 38-game RS sample.
    df_parsed_rs = df_parsed[df_parsed['GameCode'] <= 380].copy()
    df_parsed_rs.to_json('mvp_parsed_games.json', orient='records', indent=4)
    print(f"Saved mvp_parsed_games.json ({len(df_parsed_rs)} RS rows, {len(df_parsed) - len(df_parsed_rs)} playoff rows filtered)")

    print("Game Results Sample:")
    df_results = pd.DataFrame(game_results)
    print(df_results.head(3))
    
    # Save Game Results for Oracle (Matchup Predictor)
    df_results.to_json('mvp_game_results.json', orient='records', indent=4)
    print("Saved mvp_game_results.json")
    
    # Compute Standings (regular season only — playoff games have GameCode > 380)
    standings = {}

    for res in game_results:
        gc = res.get('GameCode', 0)
        if isinstance(gc, float):
            gc = int(gc)
        if gc > 380:  # Skip play-in, QF, SF, Final
            continue

        local = res['LocalTeam']
        road = res['RoadTeam']
        winner = res['Winner']

        if local == "UNKNOWN" or road == "UNKNOWN":
            continue

        if local not in standings: standings[local] = {'W': 0, 'L': 0, 'GP': 0}
        if road not in standings: standings[road] = {'W': 0, 'L': 0, 'GP': 0}

        standings[local]['GP'] += 1
        standings[road]['GP'] += 1

        if winner == local:
            standings[local]['W'] += 1
            standings[road]['L'] += 1
        else:
            standings[local]['L'] += 1
            standings[road]['W'] += 1
            
    # Compute WinPct
    for team, stats in standings.items():
        if stats['GP'] > 0:
            stats['WinPct'] = stats['W'] / stats['GP']
        else:
            stats['WinPct'] = 0.0
            
    with open('mvp_standings_derived.json', 'w') as f:
        json.dump(standings, f, indent=4)
    print("Saved mvp_standings_derived.json")

if __name__ == "__main__":
    parse_game_data()
