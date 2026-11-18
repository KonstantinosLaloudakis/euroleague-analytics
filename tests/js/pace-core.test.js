const test = require('node:test');
const assert = require('node:assert');
const PC = require('../../docs/pace-core.js');

const LEAGUE = [70, 71, 70.5, 71, 72, 73].map((pace, i) => ({ season: 2010 + i, pace }));
const TEAMS = [
  { season: 2014, team: 'AAA', pace: 72, adj_rel: 1 },
  { season: 2015, team: 'AAA', pace: 74, adj_rel: 0.5 },
  { season: 2015, team: 'NEW', pace: 75, adj_rel: 2 },
];

test('paceStreak counts trailing increases', () => {
  const s = PC.paceStreak([...LEAGUE].reverse());
  assert.strictEqual(s.streak, 3);
  assert.strictEqual(s.base.season, 2012);
  assert.strictEqual(s.latest.season, 2015);
});

test('latestSeason ignores seasons without team rows', () => {
  assert.strictEqual(PC.latestSeason(TEAMS), 2015);
  assert.strictEqual(PC.latestSeason([]), null);
});

test('seasonTeams sorts and attaches previous season, null for new clubs', () => {
  const raw = PC.seasonTeams(TEAMS, 2015, 'pace');
  assert.deepStrictEqual(raw.map(r => [r.team, r.prev]), [['NEW', null], ['AAA', 72]]);
  const adj = PC.seasonTeams(TEAMS, 2015, 'adj_rel');
  assert.deepStrictEqual(adj.map(r => [r.team, r.prev]), [['NEW', null], ['AAA', 1]]);
});

test('teamHistory pairs team pace with league pace', () => {
  assert.deepStrictEqual(PC.teamHistory(TEAMS, LEAGUE, 'AAA'),
    [{ season: 2014, pace: 72, league: 72 }, { season: 2015, pace: 74, league: 73 }]);
});
