"""Fetch and cache the Euroleague season schedule (date + tip-off time per game).

Used by export_dashboard_data.py to populate scheduled dates/times for upcoming
playoff games on the Series Hub timeline.
"""
import argparse
import json
import os
import sys
import time

import pandas as pd
import requests
import xmltodict

from season_config import CURRENT_SEASON, season_code


SCHEDULE_COLUMNS = [
    'gameday', 'round', 'date', 'startime', 'gamecode',
    'hometeam', 'homecode', 'awayteam', 'awaycode',
    'arenaname', 'confirmeddate', 'confirmedtime', 'played',
]


SCHEDULE_URL = 'https://api-live.euroleague.net/v1/schedules'


def _download_schedule_xml(season, retries=3, wait=10):
    for attempt in range(1, retries + 1):
        r = requests.get(SCHEDULE_URL, params={'seasonCode': season_code(season)}, timeout=30)
        if r.status_code == 200:
            return r.text
        print(f"Schedule request failed (HTTP {r.status_code}), attempt {attempt}/{retries}")
        if attempt < retries:
            time.sleep(wait)
    raise RuntimeError(f"Could not fetch schedule for {season} after {retries} attempts")


def fetch_and_cache_schedule(season=CURRENT_SEASON):
    out_path = f'schedule_{season}.json'
    force_fetch = '--force' in sys.argv

    if os.path.exists(out_path) and not force_fetch:
        print(f"Loading cached schedule from {out_path}")
        with open(out_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    print(f"Fetching schedule for {season} season...")
    xml_text = _download_schedule_xml(season)
    with open(f'official_schedule_{season}.xml', 'w', encoding='utf-8') as f:
        f.write(xml_text)
    df = pd.DataFrame(xmltodict.parse(xml_text)['schedule']['item'])

    keep = [c for c in SCHEDULE_COLUMNS if c in df.columns]
    df = df[keep].copy()

    for col in ('gameday', 'gamecode'):
        if col in df.columns:
            df[col] = df[col].astype(str)

    records = df.to_dict(orient='records')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(records)} schedule rows to {out_path}")
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch Euroleague schedule')
    parser.add_argument('--season', type=int, default=CURRENT_SEASON, help='Season year (default: current season)')
    parser.add_argument('--force', action='store_true', help='Force re-fetch even if cached')
    args = parser.parse_args()
    fetch_and_cache_schedule(season=args.season)
