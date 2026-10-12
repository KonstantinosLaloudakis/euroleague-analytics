import pandas as pd

df = pd.read_csv('data_cache/all_po_games.csv')
df['group'] = df['group'].str.strip()
df['diff'] = abs(df['home_score'] - df['away_score'])
df['home_win'] = df['home_score'] > df['away_score']

# 2007 season used BO3 quarterfinal format — exclude
df = df[df['season'] != 2007]

series_list = []
for (season, group), grp in df.groupby(['season', 'group']):
    teams = set(grp['home'].tolist() + grp['away'].tolist())
    if len(teams) != 2:
        continue
    wins = {}
    for _, row in grp.iterrows():
        winner = row['home'] if row['home_win'] else row['away']
        wins[winner] = wins.get(winner, 0) + 1

    winner = max(wins, key=wins.get)
    loser = [t for t in teams if t != winner][0]
    winner_wins = wins.get(winner, 0)
    loser_wins = wins.get(loser, 0)
    series_score = f"{winner_wins}-{loser_wins}"

    complete = winner_wins >= 3

    winner_diff = 0
    for _, row in grp.iterrows():
        if row['home'] == winner:
            winner_diff += row['home_score'] - row['away_score']
        else:
            winner_diff += row['away_score'] - row['home_score']

    # Sum of per-game absolute margins — measures how competitive the series was
    total_abs_diff = int(grp['diff'].sum())

    series_list.append({
        'season': season,
        'winner': winner,
        'loser': loser,
        'result': series_score,
        'games': len(grp),
        'net_diff': winner_diff,
        'total_abs_diff': total_abs_diff,
        'complete': complete,
    })

series_df = pd.DataFrame(series_list)
complete_df = series_df[series_df['complete']].copy()
live_df = series_df[~series_df['complete']].copy()

# ── CLOSEST SERIES (lowest cumulative absolute margin) ──
closest = complete_df.sort_values('total_abs_diff', ascending=True).reset_index(drop=True)

print("TOP 10 CLOSEST SERIES — CUMULATIVE POINT DIFFERENTIAL (BO5, 2008–2026)")
print("(sum of |margin| across every game played)")
print("=" * 72)
for i, row in enumerate(closest.head(10).itertuples(), 1):
    season_str = f"{row.season}-{str(row.season+1)[-2:]}"
    print(f"{i:2}. {season_str}  {row.winner} def. {row.loser:<6} {row.result}  {row.total_abs_diff} pts ({row.games}G)")

print("\nFULL RANKING (closest to most lopsided):")
print("-" * 72)
for i, row in enumerate(closest.itertuples(), 1):
    season_str = f"{row.season}-{str(row.season+1)[-2:]}"
    print(f"{i:2}. {season_str}  {row.winner} def. {row.loser:<6} {row.result}  {row.total_abs_diff} pts ({row.games}G)")

live_2025 = live_df[live_df['season'] == 2025]
data_gaps = live_df[live_df['season'] != 2025]

if not live_2025.empty:
    print("\nIN PROGRESS 2025-26 (excluded):")
    for _, row in live_2025.sort_values('total_abs_diff').iterrows():
        print(f"    {row['winner']} leads {row['loser']} {row['result']}  {row['total_abs_diff']} pts so far")

if not data_gaps.empty:
    print("\nINCOMPLETE API DATA (excluded):")
    for _, row in data_gaps.iterrows():
        season_str = f"{int(row['season'])}-{str(int(row['season'])+1)[-2:]}"
        print(f"    {season_str}  {row['winner']} vs {row['loser']} ({row['result']} in available data)")
