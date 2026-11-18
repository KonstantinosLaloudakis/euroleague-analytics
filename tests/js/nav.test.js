const test = require('node:test');
const assert = require('node:assert/strict');
const nav = require('../../docs/nav.js');

const P = (c, n, t, f, l, s) => ({ c, n, t, f, l, s });
const INDEX = {
  season: 2026,
  players: [
    P('003469', 'VEZENKOV, SASHA', 'OLY', 2015, 2026, 10),
    P('000001', "BRISSETT, O'SHAE J", 'BAR', 2020, 2026, 4),
    P('000002', 'HAYES-DAVIS, NIGEL', 'MIL', 2018, 2026, 5),
    P('000003', 'DONČIĆ, LUKA', 'RMB', 2018, 2018, 1),
    P('000004', 'CLARK III, JIMMY', 'BAR', 2024, 2026, 2),
    P('000005', 'BACOT JR., ARMANDO', 'OLY', 2025, 2026, 1),
    P('000006', 'JONES, TYRIQUE', 'OLY/PAR', 2023, 2026, 3),
    P('000007', 'JONES, CARLIK', 'MIL', 2024, 2026, 6),
    P('000008', 'JONES, OLD', 'BAR', 2010, 2012, 2),
  ],
  teams: [
    { c: 'OLY', n: 'OLYMPIACOS PIRAEUS' },
    { c: 'BAR', n: 'FC BARCELONA' },
    { c: 'MIL', n: 'EA7 EMPORIO ARMANI MILAN' },
  ],
};

test('currentPage', () => {
  assert.equal(nav.currentPage('/euroleague-analytics/'), 'index.html');
  assert.equal(nav.currentPage('/euroleague-analytics/team.html'), 'team.html');
  assert.equal(nav.currentPage('/series.html'), 'playoffs.html');
  assert.equal(nav.currentPage('/'), 'index.html');
});

test('NAV_GROUPS', () => {
  assert.deepEqual(nav.NAV_GROUPS.map(g => g.label), ['Season', 'Teams', 'Players', 'History']);
  const links = nav.NAV_GROUPS.flatMap(g => g.links);
  assert.equal(links.length, 17);
  assert.ok(!links.some(l => l.href === 'series.html'));
  assert.deepEqual(nav.NAV_ABOUT, { href: 'about.html', text: 'About' });
});

test('formatPlayerName', () => {
  assert.equal(nav.formatPlayerName('VEZENKOV, SASHA'), 'Sasha Vezenkov');
  assert.equal(nav.formatPlayerName("BRISSETT, O'SHAE J"), "O'Shae J Brissett");
  assert.equal(nav.formatPlayerName('HAYES-DAVIS, NIGEL'), 'Nigel Hayes-Davis');
  assert.equal(nav.formatPlayerName('CLARK III, JIMMY'), 'Jimmy Clark III');
  assert.equal(nav.formatPlayerName('BACOT JR., ARMANDO'), 'Armando Bacot Jr.');
});

test('formatTeamName', () => {
  assert.equal(nav.formatTeamName('FC BARCELONA'), 'FC Barcelona');
  assert.equal(nav.formatTeamName('EA7 EMPORIO ARMANI MILAN'), 'EA7 Emporio Armani Milan');
  assert.equal(nav.formatTeamName('OLYMPIACOS PIRAEUS'), 'Olympiacos Piraeus');
});

test('search matching', () => {
  for (const q of ['vez', 'sasha vez', 'vez sasha']) {
    assert.equal(nav.search(INDEX, q)[0].href, 'player.html?code=003469', q);
  }
  assert.ok(nav.search(INDEX, 'doncic').some(r => r.label === 'Luka Dončić'));
  assert.ok(nav.search(INDEX, "o'shae").some(r => r.href === 'player.html?code=000001'));
  assert.ok(nav.search(INDEX, 'oshae').some(r => r.href === 'player.html?code=000001'));
  assert.ok(nav.search(INDEX, 'davis').some(r => r.href === 'player.html?code=000002'));
  assert.deepEqual(nav.search(INDEX, ''), []);
  assert.deepEqual(nav.search(INDEX, 'zzz'), []);
});

test('search teams', () => {
  const r = nav.search(INDEX, 'oly');
  assert.equal(r[0].type, 'team');
  assert.equal(r[0].href, 'team.html?team=OLY');
  assert.equal(r[0].label, 'Olympiacos Piraeus');
  assert.equal(r[0].detail, 'Team');
  assert.ok(!r.some(x => x.href.includes(';')));
});

test('search ranking and detail', () => {
  const r = nav.search(INDEX, 'jones');
  const labels = r.map(x => x.label);
  assert.ok(labels.indexOf('Carlik Jones') < labels.indexOf('Old Jones'));
  assert.ok(r.find(x => x.label === 'Tyrique Jones').detail.startsWith('OLY/PAR'));
  assert.equal(r.find(x => x.label === 'Old Jones').detail, 'BAR · 2010–2012');
  assert.equal(nav.search(INDEX, 'doncic')[0].detail, 'RMB · 2018');
});

test('search limit', () => {
  const players = Array.from({ length: 12 }, (_, i) => P('9' + i, 'SMITH, P' + i, 'OLY', 2020, 2026, i));
  assert.equal(nav.search({ season: 2026, players, teams: [] }, 'smith').length, 8);
});
