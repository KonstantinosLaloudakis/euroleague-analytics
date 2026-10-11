"""Single source of truth: schedule/API team name -> 3-letter team code.

Add new names here when a team is renamed or joins the league (the official
schedule XML uses upper-case names). Unknown names should map to "UNK" via
team_code(); scripts skip those games, so keep this list current.
"""

NAME_TO_CODE = {
    'LDLC ASVEL VILLEURBANNE': 'ASV',
    'FC BARCELONA': 'BAR',
    'BASKONIA VITORIA-GASTEIZ': 'BAS',
    'KOSNER BASKONIA VITORIA-GASTEIZ': 'BAS',
    'ALBA BERLIN': 'BER',
    'BESIKTAS ISTANBUL': 'BES',
    'DUBAI BASKETBALL': 'DUB',
    'HAPOEL IBI TEL AVIV': 'HTA',
    'ANADOLU EFES ISTANBUL': 'IST',
    'REAL MADRID': 'MAD',
    'AS MONACO': 'MCO',
    'ARMANI OLIMPIA MILAN': 'MIL',
    'EA7 EMPORIO ARMANI MILAN': 'MIL',
    'FC BAYERN MUNICH': 'MUN',
    'OLYMPIACOS PIRAEUS': 'OLY',
    'VALENCIA BASKET': 'PAM',
    'PANATHINAIKOS AKTOR ATHENS': 'PAN',
    'PARTIZAN MOZZART BET BELGRADE': 'PAR',
    'PARIS BASKETBALL': 'PRS',
    'CRVENA ZVEZDA MERIDIANBET BELGRADE': 'RED',
    'MACCABI PLAYTIKA TEL AVIV': 'TEL',
    'MACCABI RAPYD TEL AVIV': 'TEL',
    'FENERBAHCE BEKO ISTANBUL': 'ULK',
    'FENERBAHCE TARFIN ISTANBUL': 'ULK',
    'VIRTUS BOLOGNA': 'VIR',
    'VIRTUS SEGAFREDO BOLOGNA': 'VIR',
    'ZALGIRIS KAUNAS': 'ZAL',
}


def team_code(name, default="UNK"):
    """Return the team code for a schedule team name (case/whitespace-insensitive)."""
    return NAME_TO_CODE.get((name or "").strip().upper(), default)
