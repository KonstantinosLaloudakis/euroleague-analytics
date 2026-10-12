import pandas as pd
import sys

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv('data_cache/all_po_games.csv')
df['group'] = df['group'].str.strip()

# Exclude 2007 (BO3 format)
df = df[df['season'] != 2007]

results = []
for (season, group), grp in df.groupby(['season', 'group']):
    teams = set(grp['home'].tolist() + grp['away'].tolist())
    if len(teams) != 2:
        continue

    total_games = len(grp)
    if total_games != 5:
        continue  # Only care about 5-game series

    # Game 5 = last game by gc (game code)
    game5 = grp.sort_values('gc').iloc[-1]

    away_won_g5 = game5['away_score'] > game5['home_score']

    # Series home/away team = from game 1
    first_game = grp.sort_values('gc').iloc[0]
    series_home = first_game['home']
    series_away = first_game['away']

    series_winner = series_away if away_won_g5 else series_home

    results.append({
        'season': season,
        'group': group,
        'series_home': series_home,
        'series_away': series_away,
        'g5_home': game5['home'],
        'g5_away': game5['away'],
        'g5_home_score': int(game5['home_score']),
        'g5_away_score': int(game5['away_score']),
        'away_won_g5': away_won_g5,
        'series_winner': series_winner,
    })

res_df = pd.DataFrame(results)
away_won = res_df[res_df['away_won_g5']]
home_won = res_df[~res_df['away_won_g5']]

total_g5s = len(res_df)
print(f"GAME 5 RESULTS IN PLAYOFF SERIES (BO5, 2008-2026)")
print("=" * 65)
print(f"Total 5-game series:   {total_g5s}")
print(f"Away team won Game 5:  {len(away_won)}  ({len(away_won)/total_g5s*100:.1f}%)")
print(f"Home team won Game 5:  {len(home_won)}  ({len(home_won)/total_g5s*100:.1f}%)")

print("\n" + "-" * 65)
print("SERIES WHERE AWAY TEAM WON GAME 5 (upset closer):")
print("-" * 65)
for _, row in away_won.sort_values('season').iterrows():
    season_str = f"{int(row['season'])}-{str(int(row['season'])+1)[-2:]}"
    margin = int(row['g5_away_score']) - int(row['g5_home_score'])
    print(
        f"  {season_str}  {row['series_home']} vs {row['series_away']}  |  "
        f"G5: {row['g5_home']} {row['g5_home_score']}-{row['g5_away_score']} {row['g5_away']}  "
        f"(+{margin})  -> {row['series_winner']} wins series"
    )

print("\n" + "-" * 65)
print("SERIES WHERE HOME TEAM WON GAME 5:")
print("-" * 65)
for _, row in home_won.sort_values('season').iterrows():
    season_str = f"{int(row['season'])}-{str(int(row['season'])+1)[-2:]}"
    margin = int(row['g5_home_score']) - int(row['g5_away_score'])
    print(
        f"  {season_str}  {row['series_home']} vs {row['series_away']}  |  "
        f"G5: {row['g5_home']} {row['g5_home_score']}-{row['g5_away_score']} {row['g5_away']}  "
        f"(+{margin})  -> {row['series_winner']} wins series"
    )
