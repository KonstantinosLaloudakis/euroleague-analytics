const test = require('node:test');
const assert = require('node:assert/strict');
const N = require('../../docs/names.js');

test('full / short / surname basics', () => {
  assert.equal(N.full('VEZENKOV, SASHA'), 'Sasha Vezenkov');
  assert.equal(N.short('VEZENKOV, SASHA'), 'S. Vezenkov');
  assert.equal(N.surname('VEZENKOV, SASHA'), 'Vezenkov');
});

test('hyphens, apostrophes, suffixes, particles', () => {
  assert.equal(N.full('MILLER-MCINTYRE, CODI'), 'Codi Miller-McIntyre');
  assert.equal(N.short('MILLER-MCINTYRE, CODI'), 'C. Miller-McIntyre');
  assert.equal(N.full('HAYES-DAVIS, NIGEL'), 'Nigel Hayes-Davis');
  assert.equal(N.full("BRISSETT, O'SHAE J"), "O'Shae J Brissett");
  assert.equal(N.full('CLARK III, JIMMY'), 'Jimmy Clark III');
  assert.equal(N.short('CLARK III, JIMMY'), 'J. Clark III');
  assert.equal(N.surname('CLARK III, JIMMY'), 'Clark III');
  assert.equal(N.full('BACOT JR., ARMANDO'), 'Armando Bacot Jr.');
  assert.equal(N.full('DE COLO, NANDO'), 'Nando De Colo');
  assert.equal(N.full('BALDWIN IV, WADE'), 'Wade Baldwin IV');
  assert.equal(N.full('SMITH, C.J.'), 'C.J. Smith');
});

test('no comma, empty, non-string', () => {
  assert.equal(N.full('NEDOVIC'), 'Nedovic');
  assert.equal(N.short('NEDOVIC'), 'Nedovic');
  assert.equal(N.full(''), '');
  assert.equal(N.full(null), '');
  assert.equal(N.short(undefined), '');
  assert.equal(N.surname(42), '');
  assert.equal(N.full('  vezenkov, sasha '), 'Sasha Vezenkov');
});

test('overrides win', () => {
  assert.ok(Object.keys(N.OVERRIDES).length > 0);
  const [k, v] = Object.entries(N.OVERRIDES)[0];
  assert.equal(N.full(k), v);
  assert.equal(N.full(k.toLowerCase()), v);
});

test('responsiveHtml escapes and has both spans', () => {
  const h = N.responsiveHtml('A<B, C');
  assert.ok(h.includes('&lt;'));
  assert.ok(!h.includes('<B'));
  assert.ok(h.includes('class="pn-full"') && h.includes('class="pn-short"'));
  assert.equal(N.responsiveHtml('VEZENKOV, SASHA'),
    '<span class="pn-full">Sasha Vezenkov</span><span class="pn-short">S. Vezenkov</span>');
});

test('chartLabels uses surname, short on collisions', () => {
  assert.deepEqual(N.chartLabels(['CLARK, JIMMY', 'CLARK, IAN', 'VEZENKOV, SASHA']),
    ['J. Clark', 'I. Clark', 'Vezenkov']);
});

test('matches', () => {
  assert.ok(N.matches('VEZENKOV, SASHA', 'sasha vez'));
  assert.ok(N.matches('VEZENKOV, SASHA', 'vezenkov'));
  assert.ok(N.matches('VEZENKOV, SASHA', 'VEZENKOV, SASHA'));
  assert.ok(!N.matches('VEZENKOV, SASHA', 'luka'));
  assert.ok(N.matches('DONČIĆ, LUKA', 'doncic'));
  assert.ok(N.matches("BRISSETT, O'SHAE J", 'oshae'));
  assert.ok(N.matches('VEZENKOV, SASHA', ''));
});
