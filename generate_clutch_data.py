"""Generate current-season clutch stats from the cached play-by-play CSV."""
import sys

import pandas as pd

from clutchStats import analyze_clutch_stats
from season_config import CURRENT_SEASON


def main():
    pbp_path = f'pbp_{CURRENT_SEASON}.csv'
    out_path = f'clutch_stats_{CURRENT_SEASON}_{CURRENT_SEASON}.json'
    df = pd.read_csv(pbp_path, low_memory=False)
    analyze_clutch_stats(CURRENT_SEASON, CURRENT_SEASON, full_df=df, output_path=out_path)
    print(f"Saved {out_path}")


if __name__ == '__main__':
    sys.exit(main())
