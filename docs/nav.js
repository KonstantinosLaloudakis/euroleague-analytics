/* Navigation menu data and pure search helpers (no DOM access).
   Wrapped in an IIFE so it defines no browser globals (other pages declare
   names like formatPlayerName); loads as a classic script or a CommonJS module. */

(function () {
  'use strict';

  const NAV_GROUPS = [
    { label: 'Season', links: [
      { href: 'index.html', text: 'Season Hub' },
      { href: 'recap.html', text: 'Game Recap' },
      { href: 'mvp.html', text: 'MVP Race' },
      { href: 'playoffs.html', text: 'Playoffs' },
      { href: 'title-race.html', text: 'Title Race' },
    ] },
    { label: 'Teams', links: [
      { href: 'team.html', text: 'Team Deep-Dive' },
      { href: 'h2h.html', text: 'Head-to-Head' },
      { href: 'game-control.html', text: 'Game Control' },
      { href: 'lineups.html', text: 'Lineups' },
      { href: 'network.html', text: 'Playmaking' },
    ] },
    { label: 'Players', links: [
      { href: 'players.html', text: 'Player Stats' },
      { href: 'player.html', text: 'Careers' },
      { href: 'compare.html', text: 'Compare' },
      { href: 'shots.html', text: 'Shot Lab' },
    ] },
    { label: 'History', links: [
      { href: 'records.html', text: 'All-Time Records' },
      { href: 'gci-history.html', text: 'GCI History' },
      { href: 'replay.html', text: 'Game Replay' },
    ] },
  ];

  const NAV_ABOUT = { href: 'about.html', text: 'About' };

  function currentPage(pathname) {
    const last = String(pathname).split('/').pop();
    if (last === '') return 'index.html';
    return last === 'series.html' ? 'playoffs.html' : last;
  }

  function normalizeText(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/['’]/g, '');
  }

  function tokens(s) {
    return normalizeText(s).split(/[^a-z0-9]+/).filter(Boolean);
  }

  const ROMAN_NUMERALS = ['II', 'III', 'IV', 'V'];

  function capitalizePart(part) {
    return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
  }

  function capitalizeName(word) {
    if (ROMAN_NUMERALS.includes(word.toUpperCase())) return word.toUpperCase();
    return word.split(/([-'])/).map(p => (p === '-' || p === "'") ? p : capitalizePart(p)).join('');
  }

  function formatPlayerName(raw) {
    const i = raw.indexOf(',');
    const last = i < 0 ? raw : raw.slice(0, i);
    const first = i < 0 ? '' : raw.slice(i + 1);
    return (first + ' ' + last).split(/\s+/).filter(Boolean).map(capitalizeName).join(' ');
  }

  function formatTeamName(raw) {
    return raw.split(/\s+/).filter(Boolean).map(w =>
      (w.length <= 2 || /\d/.test(w)) ? w.toUpperCase() : capitalizePart(w)).join(' ');
  }

  function matchesAll(queryTokens, nameTokens) {
    return queryTokens.every(q => nameTokens.some(t => t.startsWith(q)));
  }

  function search(index, query, limit = 8) {
    const q = tokens(query);
    if (!q.length) return [];
    const teams = (index.teams || [])
      .filter(t => matchesAll(q, tokens(t.n).concat(tokens(t.c))))
      .map(t => ({ type: 'team', href: 'team.html?team=' + t.c, label: formatTeamName(t.n), detail: 'Team' }));

    const scored = [];
    for (const p of index.players || []) {
      if (!matchesAll(q, tokens(p.n))) continue;
      const surname = tokens(p.n.split(',')[0]);
      scored.push({
        surnameHit: surname.some(t => t.startsWith(q[0])),
        active: p.l === index.season,
        p,
      });
    }
    scored.sort((a, b) =>
      (b.surnameHit - a.surnameHit) || (b.active - a.active) ||
      (b.p.s - a.p.s) || a.p.n.localeCompare(b.p.n));
    const players = scored.map(({ p }) => ({
      type: 'player',
      href: 'player.html?code=' + p.c,
      label: formatPlayerName(p.n),
      detail: p.t + ' · ' + (p.f === p.l ? p.f : p.f + '–' + p.l),
    }));
    return teams.concat(players).slice(0, limit);
  }

  // Task 3: DOM rendering goes here, inside this IIFE.

  if (typeof module === 'object' && module.exports) {
    module.exports = {
      NAV_GROUPS, NAV_ABOUT, currentPage, normalizeText, tokens,
      formatPlayerName, formatTeamName, search,
    };
  }
})();
