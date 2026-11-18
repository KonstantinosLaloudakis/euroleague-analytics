/* Shared player-name formatter. Data names are "LAST, FIRST" uppercase; this turns
   them into "Sasha Vezenkov" (full), "S. Vezenkov" (short) or "Vezenkov" (surname).
   Capitalization is rule-based (see caseWord) plus a small OVERRIDES list.
   Defines one browser global, PlayerNames; in Node the same object is module.exports.
   Pages load it right before nav.js. Everything that writes HTML goes through
   responsiveHtml(), which escapes. */

(function () {
  'use strict';

  // normalized raw name -> full display, for names the rules get wrong
  const OVERRIDES = {
    'DE LA FUENTE, RODRIGO': 'Rodrigo de la Fuente',
    'DA SILVA, OSCAR': 'Oscar da Silva',
    'DOS SANTOS, YAGO': 'Yago dos Santos',
    'VAN DEN SPIEGEL, TOMAS': 'Tomas van den Spiegel',
    'DIBARTOLOMEO, JOHN': 'John DiBartolomeo',
    'STRAWBERRY, DJ': 'DJ Strawberry',
    'STEWART, DJ': 'DJ Stewart',
    'LEAF, TJ': 'TJ Leaf',
  };

  const FOLD = { 'đ': 'dj', 'Đ': 'dj', 'ł': 'l', 'Ł': 'l', 'ø': 'o', 'Ø': 'o', 'ß': 'ss', 'ı': 'i', 'İ': 'i' };
  const ROMAN = ['II', 'III', 'IV', 'V'];

  function normalizeKey(s) {
    return s.trim().replace(/\s+/g, ' ').toUpperCase();
  }

  function searchTokens(s) {
    const folded = String(s).replace(/[đĐłŁøØßıİ]/g, c => FOLD[c]);
    return folded.normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/['’]/g, '').split(/[^a-z0-9]+/).filter(Boolean);
  }

  function cap(s) {
    return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  }

  // One word of a name ("MILLER-MCINTYRE", "O'SHAE", "JR.", "C.J.").
  function caseWord(word) {
    const bare = word.replace(/\.$/, '').toUpperCase();
    if (bare === 'JR') return 'Jr.';
    if (bare === 'SR') return 'Sr.';
    if (ROMAN.includes(bare)) return bare;
    if (word.length === 1 || /^(?:[A-Za-z]\.)+[A-Za-z]?\.?$/.test(word)) return word.toUpperCase();
    return word.split(/([-'’])/).map(p => {
      if (p === '-' || p === "'" || p === '’') return p;
      const c = cap(p);
      return /^Mc[a-z]/.test(c) ? 'Mc' + cap(c.slice(2)) : c;
    }).join('');
  }

  function caseWords(s) {
    return s.split(/\s+/).filter(Boolean).map(caseWord);
  }

  // -> { first: ['Sasha'], last: ['Vezenkov'], override: 'Full Name' | null }, or null for empty input
  function parse(raw) {
    if (typeof raw !== 'string' || !raw.trim()) return null;
    const i = raw.indexOf(',');
    const lastRaw = i < 0 ? raw : raw.slice(0, i);
    const firstRaw = i < 0 ? '' : raw.slice(i + 1);
    const first = caseWords(firstRaw);
    let last = caseWords(lastRaw);
    const key = normalizeKey(raw);
    const override = Object.prototype.hasOwnProperty.call(OVERRIDES, key) ? OVERRIDES[key] : null;
    if (override) {
      // The surname is whatever follows the first name in the override (keeps short/surname right).
      const prefix = first.join(' ');
      if (prefix && override.toLowerCase().startsWith(prefix.toLowerCase() + ' ')) {
        last = [override.slice(prefix.length + 1)];
      }
    }
    return { first, last, override };
  }

  function full(raw) {
    const p = parse(raw);
    if (!p) return '';
    return p.override || p.first.concat(p.last).join(' ');
  }

  function surname(raw) {
    const p = parse(raw);
    return p ? p.last.join(' ') : '';
  }

  function short(raw) {
    const p = parse(raw);
    if (!p) return '';
    const f = p.first[0];
    if (!f) return p.last.join(' ');
    const initial = f.includes('.') ? f : f.charAt(0).toUpperCase() + '.';
    return initial + ' ' + p.last.join(' ');
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  function responsiveHtml(raw) {
    const f = full(raw);
    if (!f) return '';
    return '<span class="pn-full">' + escapeHtml(f) + '</span><span class="pn-short">' + escapeHtml(short(raw)) + '</span>';
  }

  // Surname per player; short form for players whose surnames collide within the set.
  function chartLabels(raws) {
    const counts = new Map();
    for (const r of raws) {
      const k = surname(r).toLowerCase();
      counts.set(k, (counts.get(k) || 0) + 1);
    }
    return raws.map(r => (counts.get(surname(r).toLowerCase()) > 1 ? short(r) : surname(r)));
  }

  // Every query token is a prefix of some token of the raw or the full name.
  function matches(raw, query) {
    const q = searchTokens(query == null ? '' : query);
    if (!q.length) return true;
    const t = searchTokens(raw == null ? '' : raw).concat(searchTokens(full(raw)));
    return q.every(w => t.some(x => x.startsWith(w)));
  }

  const api = { full, short, surname, responsiveHtml, chartLabels, matches, OVERRIDES };
  if (typeof window !== 'undefined') window.PlayerNames = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})();
