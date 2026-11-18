const test = require('node:test');
const assert = require('node:assert');
const { createPlayerLinks } = require('../../docs/player-links.js');

const INDEX = { 'VEZENKOV, SASHA': '003469', "BRISSETT, O'SHAE J": '014111', 'DONCIC, LUKA': 'THY' };
const PL = createPlayerLinks(INDEX);

test('url resolves names, normalized', () => {
  assert.strictEqual(PL.url('VEZENKOV, SASHA'), 'player.html?code=003469');
  assert.strictEqual(PL.url(' vezenkov, sasha '), 'player.html?code=003469');
  assert.strictEqual(PL.url('Dončić, Luka'), 'player.html?code=THY');
});

test('url ids win over names', () => {
  assert.strictEqual(PL.url('X', { code: '003469' }), 'player.html?code=003469');
  assert.strictEqual(PL.url('X', { apiId: 'P003469' }), 'player.html?code=003469');
  assert.strictEqual(PL.url('VEZENKOV, SASHA', { code: 'THY' }), 'player.html?code=THY');
});

test('url null for unknown names and codes', () => {
  assert.strictEqual(PL.url('NOBODY, X'), null);
  assert.strictEqual(PL.url('VEZENKOV, SASHA', { code: '999999' }), null);
  assert.strictEqual(PL.url('X', { apiId: 'P999999' }), null);
});

test('link renders anchor with escaped label', () => {
  assert.strictEqual(PL.link('VEZENKOV, SASHA', 'S. Vezenkov'),
    '<a class="player-link" href="player.html?code=003469">S. Vezenkov</a>');
  const a = PL.link("BRISSETT, O'SHAE J");
  assert.match(a, /^<a class="player-link" href="player\.html\?code=014111">BRISSETT, O(&#39;|&#x27;)SHAE J<\/a>$/);
  assert.strictEqual(PL.link('NOBODY, <B>'), 'NOBODY, &lt;B&gt;');
});

test('null index degrades to plain text', () => {
  const n = createPlayerLinks(null);
  assert.strictEqual(n.url('VEZENKOV, SASHA'), null);
  assert.strictEqual(n.link('A, B'), 'A, B');
});

const { createTapGate, raceWithTimeout } = require('../../docs/player-links.js');

test('tap gate: first tap no navigate, second tap same point navigates', () => {
  const g = createTapGate(3000);
  assert.strictEqual(g('0:1', 1000), false);
  assert.strictEqual(g('0:1', 1500), true);
  assert.strictEqual(g('0:1', 1600), false, 'resets after navigating');
});

test('tap gate: different point resets', () => {
  const g = createTapGate(3000);
  assert.strictEqual(g('0:1', 0), false);
  assert.strictEqual(g('0:2', 100), false);
  assert.strictEqual(g('0:1', 200), false);
  assert.strictEqual(g('0:1', 300), true);
});

test('tap gate: second tap outside window counts as a first tap', () => {
  const g = createTapGate(3000);
  assert.strictEqual(g('a', 0), false);
  assert.strictEqual(g('a', 5000), false);
  assert.strictEqual(g('a', 5100), true);
});

test('raceWithTimeout resolves when timer fires first and never rejects', async () => {
  let fire;
  const timer = cb => { fire = cb; };
  const never = new Promise(() => {});
  const p = raceWithTimeout(never, timer, 3000);
  fire();
  await p;
  await raceWithTimeout(Promise.reject(new Error('x')), timer, 3000);
});

test('link accepts an extra modifier class', () => {
  assert.strictEqual(PL.link('VEZENKOV, SASHA', 'View career', null, 'player-link--cta'),
    '<a class="player-link player-link--cta" href="player.html?code=003469">View career</a>');
});
