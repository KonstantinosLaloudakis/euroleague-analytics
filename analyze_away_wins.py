import pandas as pd

df = pd.read_csv('data_cache/all_po_games.csv')
df['group'] = df['group'].str.strip()

# Exclude 2007 (BO3 format)
df = df[df['season'] != 2007]

series_list = []
for (season, group), grp in df.groupby(['season', 'group']):
    teams = set(grp['home'].tolist() + grp['away'].tolist())
    if len(teams) != 2:
        continue

    # The team that appears as 'home' most often is the series home team
    # Simpler: game 1 home team is the series home team
    first_game = grp.sort_values('gc').iloc[0]
    series_home = first_game['home']
    series_away = first_game['away']

    away_wins = 0
    home_wins = 0
    for _, row in grp.iterrows():
        if row['away_score'] > row['home_score']:
            away_wins += 1
        else:
            home_wins += 1

    total_games = len(grp)

    series_list.append({
        'season': season,
        'group': group,
        'series_home': series_home,
        'series_away': series_away,
        'away_wins': away_wins,
        'home_wins': home_wins,
        'total_games': total_games,
    })

series_df = pd.DataFrame(series_list)
ranked = series_df.sort_values('away_wins', ascending=False).reset_index(drop=True)

print("TOP 15 SERIES BY AWAY WINS (BO5 Playoffs, 2008-2026)")
print("=" * 80)
for i, row in ranked.head(15).iterrows():
    season_str = f"{int(row['season'])}-{str(int(row['season'])+1)[-2:]}"
    winner = row['series_away'] if row['away_wins'] > row['home_wins'] else row['series_home']
    print(
        f"{i+1:2}. {season_str}  {row['series_home']} (H) vs {row['series_away']} (A)  "
        f"| Away: {int(row['away_wins'])}W / Home: {int(row['home_wins'])}W  | {int(row['total_games'])} games  [{row['group']}]"
    )

# Also verify the 2022-23 Real Madrid vs Partizan stat
print("\n--- Verifying 2022-23 Real Madrid (MAD) vs Partizan (PAN) ---")
check = series_df[(series_df['season'] == 2023) &
                  (series_df['series_home'].isin(['MAD', 'PAN'])) &
                  (series_df['series_away'].isin(['MAD', 'PAN']))]
print(check.to_string(index=False))
