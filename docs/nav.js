/* Site navigation: menu data, pure search helpers, and (in a browser) the
   rendering of <nav id="site-nav"> plus the player/team search box.
   Every page includes it right after its empty <nav> placeholder, so the bar is
   built synchronously before the rest of the page renders.
   Wrapped in an IIFE so it defines no browser globals (other pages declare
   names like formatPlayerName); loads as a classic script or a CommonJS module,
   where the DOM part is skipped. */

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
    let last = String(pathname).split('/').pop();
    if (last === '') return 'index.html';
    if (!last.includes('.')) last += '.html'; // GitHub Pages serves /team for team.html
    return last === 'series.html' ? 'playoffs.html' : last;
  }

  const FOLD = { 'đ': 'dj', 'Đ': 'dj', 'ł': 'l', 'Ł': 'l', 'ø': 'o', 'Ø': 'o',
    'ß': 'ss', 'ı': 'i', 'İ': 'i' };

  function normalizeText(s) {
    // NFD can't decompose these, so fold them by hand (data is transliterated: Đorđević -> DJORDJEVIC).
    const folded = String(s).replace(/[đĐłŁøØßıİ]/g, c => FOLD[c]);
    return folded.normalize('NFD').replace(/[̀-ͯ]/g, '')
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

  const TEAM_ACRONYMS = new Set(['LDLC', 'ASVEL', 'IBI']);

  function formatTeamName(raw) {
    return raw.split(/\s+/).filter(Boolean).map(w =>
      (w.length <= 2 || /\d/.test(w) || TEAM_ACRONYMS.has(w.toUpperCase()))
        ? w.toUpperCase() : w.split('-').map(capitalizePart).join('-')).join(' ');
  }

  function matchesAll(queryTokens, nameTokens) {
    return queryTokens.every(q => nameTokens.some(t => t.startsWith(q)));
  }

  function search(index, query, limit = 8) {
    const q = tokens(query);
    if (!q.length) return [];
    const teams = (index.teams || [])
      .filter(t => matchesAll(q, tokens(t.n).concat(tokens(t.c))))
      .map(t => ({ type: 'team', href: 'team.html?team=' + encodeURIComponent(t.c), label: formatTeamName(t.n), detail: 'Team' }));

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
      href: 'player.html?code=' + encodeURIComponent(p.c),
      label: formatPlayerName(p.n),
      detail: p.t + ' · ' + (p.f === p.l ? p.f : p.f + '–' + p.l),
    }));
    return teams.concat(players).slice(0, limit);
  }

  /* ── DOM: rendering ─────────────────────────────────────────────── */

  const SEARCH_INDEX_URL = 'data/current/search_index.json';
  const SEARCH_ICON = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="7"/>' +
    '<path d="m20 20-4-4"/></svg>';

  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    el.append(...children);
    return el;
  }

  function navLink(link, page) {
    const a = h('a', { href: link.href, class: 'nav-link' }, link.text);
    if (link.href === page) {
      a.classList.add('active');
      a.setAttribute('aria-current', 'page');
    }
    return a;
  }

  function renderGroup(group, i, page) {
    const menuId = 'nav-menu-' + i;
    const isActive = group.links.some(l => l.href === page);
    const btn = h('button', {
      type: 'button', class: 'nav-link nav-more-btn' + (isActive ? ' active' : ''),
      'aria-expanded': 'false', 'aria-controls': menuId,
    }, group.label + ' ', h('span', { 'aria-hidden': 'true' }, '▾'));
    const heading = h('span', { class: 'nav-group-label' }, group.label);
    const menu = h('div', { class: 'nav-more-dropdown', id: menuId },
      ...group.links.map(l => navLink(l, page)));
    return h('div', { class: 'nav-more' }, btn, heading, menu);
  }

  function renderSearchBox() {
    const input = h('input', {
      type: 'search', id: 'nav-search-input', class: 'nav-search-input',
      placeholder: 'Search players, teams', 'aria-label': 'Search players and teams',
      role: 'combobox', 'aria-autocomplete': 'list', 'aria-expanded': 'false',
      'aria-controls': 'nav-search-listbox', autocomplete: 'off', spellcheck: 'false',
    });
    const list = h('ul', { class: 'nav-search-list', id: 'nav-search-listbox', role: 'listbox',
      'aria-label': 'Search results' });
    // The live region lives outside the panel (never hidden) so its text changes are
    // announced; the panel keeps a visible copy of the message for sighted users.
    const status = h('p', { class: 'nav-search-sr', role: 'status' });
    const message = h('p', { class: 'nav-search-status', 'aria-hidden': 'true' });
    const panel = h('div', { class: 'nav-search-panel', hidden: '' }, list, message);
    const box = h('div', { class: 'nav-search', id: 'nav-search' }, input, panel, status);
    return { box, input, list, status, message, panel };
  }

  function renderNav(nav, page) {
    const searchBtn = h('button', {
      type: 'button', class: 'nav-toggle nav-search-btn', 'aria-label': 'Search',
      'aria-expanded': 'false', 'aria-controls': 'nav-search',
    });
    searchBtn.innerHTML = SEARCH_ICON;
    const toggle = h('button', {
      type: 'button', class: 'nav-toggle nav-menu-btn', 'aria-expanded': 'false', 'aria-controls': 'site-nav',
    }, h('span', { 'aria-hidden': 'true' }, '☰'), ' Menu');
    const search = renderSearchBox();
    nav.replaceChildren(
      h('a', { href: 'index.html', class: 'site-nav-brand' }, '🏀 Euroleague Analytics'),
      searchBtn,
      toggle,
      ...NAV_GROUPS.map((g, i) => renderGroup(g, i, page)),
      navLink(NAV_ABOUT, page),
      search.box,
    );
    return Object.assign({ nav, searchBtn, toggle }, search);
  }

  /* ── DOM: menu behavior ─────────────────────────────────────────── */

  function setupMenus(ui) {
    const groups = Array.from(ui.nav.querySelectorAll('.nav-more'));
    function setOpen(group, open) {
      group.classList.toggle('open', open);
      group.querySelector('.nav-more-btn').setAttribute('aria-expanded', String(open));
    }
    for (const group of groups) {
      const btn = group.querySelector('.nav-more-btn');
      btn.addEventListener('click', () => {
        const open = !group.classList.contains('open');
        for (const g of groups) setOpen(g, g === group && open);
      });
      group.addEventListener('keydown', e => {
        if (e.key === 'Escape' && group.classList.contains('open')) {
          setOpen(group, false);
          btn.focus();
        }
      });
      group.addEventListener('focusout', e => {
        if (!group.contains(e.relatedTarget)) setOpen(group, false);
      });
    }
    document.addEventListener('click', e => {
      for (const g of groups) if (!g.contains(e.target)) setOpen(g, false);
    });
  }

  // Compact bar (narrow screens): "☰ Menu" and the search button each reveal
  // one panel under the bar; opening one closes the other.
  function setupCompactBar(ui) {
    function show(panel) {
      ui.nav.classList.toggle('nav-open', panel === 'menu');
      ui.nav.classList.toggle('search-open', panel === 'search');
      ui.toggle.setAttribute('aria-expanded', String(panel === 'menu'));
      ui.searchBtn.setAttribute('aria-expanded', String(panel === 'search'));
    }
    ui.toggle.addEventListener('click', () => {
      show(ui.nav.classList.contains('nav-open') ? null : 'menu');
    });
    ui.searchBtn.addEventListener('click', () => {
      const opening = !ui.nav.classList.contains('search-open');
      show(opening ? 'search' : null);
      if (opening) ui.input.focus();
    });
    return {
      revealSearch() {
        const compact = ui.searchBtn.offsetParent !== null;
        if (compact && !ui.nav.classList.contains('search-open')) show('search');
      },
    };
  }

  /* ── DOM: search UI ─────────────────────────────────────────────── */

  function isTextField(el) {
    return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
  }

  function setupSearch(ui, bar) {
    const { input, list, status, message, panel } = ui;
    let index = null;
    let failed = false;
    let pending = null;
    let results = [];
    let active = -1;

    // Fetched on first use only; if the user typed meanwhile, their current
    // query runs when the index lands.
    function loadIndex() {
      if (index || pending) return;
      pending = fetch(SEARCH_INDEX_URL)
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => { index = data; failed = false; }, () => { failed = true; })
        .then(() => { pending = null; if (document.activeElement === input || !panel.hidden) update(); });
    }

    function close() {
      panel.hidden = true;
      list.replaceChildren();
      status.textContent = '';
      message.textContent = '';
      results = [];
      active = -1;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
    }

    function showMessage(text) {
      close();
      status.textContent = text;
      message.textContent = text;
      panel.hidden = false;
    }

    function setActive(i) {
      const options = list.children;
      if (options[active]) options[active].setAttribute('aria-selected', 'false');
      active = i;
      options[i].setAttribute('aria-selected', 'true');
      options[i].scrollIntoView({ block: 'nearest' });
      input.setAttribute('aria-activedescendant', options[i].id);
    }

    function showResults(items) {
      close();
      results = items;
      list.append(...items.map((r, i) => h('li', {
        role: 'option', id: 'nav-search-opt-' + i, class: 'nav-search-option',
        'aria-selected': 'false', 'data-i': String(i),
      }, h('span', { class: 'nav-search-label' }, r.label),
         h('span', { class: 'nav-search-detail' }, r.detail))));
      panel.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      setActive(0);
      status.textContent = items.length + (items.length === 1 ? ' result' : ' results');
    }

    function update() {
      const q = input.value.trim();
      if (!q) return close();
      if (failed) return showMessage('Search is unavailable right now.');
      if (!index) { loadIndex(); return showMessage('Loading…'); }
      const items = search(index, q);
      if (!items.length) return showMessage('No players or teams match "' + q + '"');
      showResults(items);
    }

    function open(result, newTab) {
      if (!result) return;
      if (newTab) window.open(result.href, '_blank', 'noopener');
      else window.location.href = result.href;
    }

    // Phone: the results must survive the on-screen keyboard being dismissed (a blur),
    // so in the open mobile search row they close on outside tap / Escape / the buttons.
    const isCompact = () => ui.searchBtn.offsetParent !== null && ui.nav.classList.contains('search-open');

    input.addEventListener('focus', () => { loadIndex(); update(); });
    input.addEventListener('input', update);
    input.addEventListener('keydown', e => {
      const n = results.length;
      if (e.key === 'ArrowDown' && n) {
        e.preventDefault();
        setActive((active + 1) % n);
      } else if (e.key === 'ArrowUp' && n) {
        e.preventDefault();
        setActive((active - 1 + n) % n);
      } else if (e.key === 'Enter' && n) {
        e.preventDefault();
        open(results[active], e.ctrlKey || e.metaKey);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        input.value = '';
        close();
      }
    });
    input.addEventListener('blur', () => { if (!isCompact()) close(); });
    document.addEventListener('pointerdown', e => {
      if (isCompact() && !ui.box.contains(e.target) && !ui.searchBtn.contains(e.target)) close();
    });
    ui.searchBtn.addEventListener('click', close);
    ui.toggle.addEventListener('click', close);
    // Keep focus in the input while clicking a result, so blur doesn't close it first.
    panel.addEventListener('mousedown', e => e.preventDefault());
    list.addEventListener('click', e => {
      const option = e.target.closest('[role="option"]');
      if (option) open(results[Number(option.dataset.i)], e.ctrlKey || e.metaKey);
    });
    list.addEventListener('auxclick', e => {
      const option = e.target.closest('[role="option"]');
      if (option && e.button === 1) {
        e.preventDefault();
        open(results[Number(option.dataset.i)], true);
      }
    });

    document.addEventListener('keydown', e => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      if (isTextField(e.target)) return;
      e.preventDefault();
      bar.revealSearch();
      input.focus();
    });
  }

  function initNav() {
    const nav = document.getElementById('site-nav');
    if (!nav) return;
    const ui = renderNav(nav, currentPage(window.location.pathname));
    setupMenus(ui);
    setupSearch(ui, setupCompactBar(ui));
  }

  if (typeof document !== 'undefined') initNav();

  if (typeof module === 'object' && module.exports) {
    module.exports = {
      NAV_GROUPS, NAV_ABOUT, currentPage, normalizeText, tokens,
      formatPlayerName, formatTeamName, search,
    };
  }
})();
