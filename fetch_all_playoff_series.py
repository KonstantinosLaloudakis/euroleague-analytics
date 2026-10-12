"""Fetch all best-of-5 PO phase games from Euroleague API (2007–2025, excluding 2019 COVID)."""
from euroleague_api import game_stats
import time, json, pandas as pd

gs = game_stats.GameStats()

# (season, start_gc, end_gc) — covers the PO phase range for each season
season_configs = [
    (2007, 215, 290),   # PO starts ~round 21
    (2008, 170, 240),   # PO starts ~round 19
    (2009, 170, 240),
    (2010, 170, 240),
    (2011, 170, 240),
    (2012, 230, 310),   # expanded format, PO starts ~round 26
    (2013, 230, 310),
    (2014, 230, 310),
    (2015, 230, 310),
    (2016, 230, 310),   # new format (no Top 16 from 2016-17 onward)
    (2017, 230, 310),
    (2018, 230, 310),
    # 2019 skipped — COVID cancellation
    (2020, 295, 380),
    (2021, 295, 380),
    (2022, 295, 380),
    (2023, 295, 380),
    (2024, 295, 380),
    (2025, 378, 420),
]

all_games = []
for season, start_gc, end_gc in season_configs:
    consec_404 = 0
    found = 0
    for gc in range(start_gc, end_gc + 1):
        try:
            df = gs.get_game_report(season, gc)
            consec_404 = 0
            if not df.empty:
                row = df.iloc[0]
                if row['phaseType.code'] == 'PO':
                    try:
                        hs = int(row['local.score'])
                        as_ = int(row['road.score'])
                        if hs > 0:
                            all_games.append({
                                'season': season,
                                'gc': gc,
                                'group': str(row['group.name']).strip(),
                                'home': row['local.club.code'],
                                'away': row['road.club.code'],
                                'home_score': hs,
                                'away_score': as_,
                            })
                            found += 1
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            if '404' in str(e):
                consec_404 += 1
                if consec_404 > 8:
                    break
        time.sleep(0.05)
    print(f'{season}: {found} played PO games found')

df_games = pd.DataFrame(all_games)
df_games.to_csv('data_cache/all_po_games.csv', index=False)
print(f'\nTotal: {len(df_games)} games saved to data_cache/all_po_games.csv')
