import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from season_config import CURRENT_SEASON
from team_aliases import NAME_TO_CODE, team_code

CODES_2026 = {
    'ASV', 'BAR', 'BAS', 'BES', 'DUB', 'HTA', 'IST', 'MAD', 'MIL', 'MUN',
    'OLY', 'PAM', 'PAN', 'PAR', 'PRS', 'RED', 'TEL', 'ULK', 'VIR', 'ZAL',
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, f'official_schedule_{CURRENT_SEASON}.xml')


@pytest.mark.parametrize('name,code', [
    ('Besiktas Istanbul', 'BES'),
    ('BESIKTAS ISTANBUL', 'BES'),
    ('Armani Olimpia Milan', 'MIL'),
    ('Fenerbahce Tarfin Istanbul', 'ULK'),
    ('Valencia Basket', 'PAM'),
])
def test_known_names(name, code):
    assert team_code(name) == code


def test_unknown_name_defaults():
    assert team_code('Nobody FC') == 'UNK'
    assert team_code(None) == 'UNK'


def test_all_values_are_codes():
    assert set(NAME_TO_CODE.values()) >= CODES_2026


@pytest.mark.skipif(CURRENT_SEASON != 2026 or not os.path.exists(XML), reason='needs 2026 schedule xml')
def test_every_schedule_team_resolves():
    names = set()
    for item in ET.parse(XML).getroot().findall('item'):
        names.add(item.find('hometeam').text)
        names.add(item.find('awayteam').text)
    codes = {n: team_code(n) for n in names}
    assert all(c in CODES_2026 for c in codes.values()), codes
    assert set(codes.values()) == CODES_2026
