/* Shared helper that turns player names into links to the career page
   (player.html?code=<code>). Resolves a career code from an explicit id or from
   the normalized "LAST, FIRST" name via data/current/player_index.json.
   Unlike nav.js this deliberately defines one browser global, PlayerLinks.
   Until the index loads (or if it fails) url() is null and link() is plain
   text. With no label, link() shows PlayerNames.responsiveHtml(name) when names.js is loaded. In Node only createPlayerLinks is exported. */

(function () {
  'use strict';

  const INDEX_URL = 'data/current/player_index.json';

  // Equivalent to normalize_name in fetch_player_career_stats.py.
  function normalizeName(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toUpperCase();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  function createPlayerLinks(index) {
    const idx = index || {};
    const codes = new Set(Object.values(idx));

    function url(name, ids) {
      let code = null;
      if (ids && ids.code) code = String(ids.code);
      else if (ids && ids.apiId) code = String(ids.apiId).replace(/^P/, '');
      else if (Object.prototype.hasOwnProperty.call(idx, normalizeName(name))) code = idx[normalizeName(name)];
      if (code === null || !codes.has(code)) return null;
      return 'player.html?code=' + encodeURIComponent(code);
    }

    function link(name, label, ids, extraClass) {
      let text;
      if (label !== undefined && label !== null) text = escapeHtml(label);
      else if (typeof PlayerNames !== 'undefined' && PlayerNames.responsiveHtml) text = PlayerNames.responsiveHtml(name);
      else text = escapeHtml(name);
      const href = url(name, ids);
      return href ? '<a class="player-link' + (extraClass ? ' ' + extraClass : '') + '" href="' + href + '">' + text + '</a>' : text;
    }

    return { url, link };
  }

  // Touch double-tap gate: tap(key, now) is true only for a second tap on the same
  // key within windowMs; any other tap just records the key and returns false.
  function createTapGate(windowMs) {
    let lastKey = null, lastAt = 0;
    return function tap(key, now) {
      if (lastKey === key && now - lastAt <= windowMs) { lastKey = null; return true; }
      lastKey = key; lastAt = now;
      return false;
    };
  }

  // Resolves when promise settles (either way) or when startTimer's callback fires. Never rejects.
  function raceWithTimeout(promise, startTimer, ms) {
    return new Promise(resolve => {
      startTimer(resolve, ms);
      promise.then(resolve, resolve);
    });
  }

  if (typeof window !== 'undefined' && typeof fetch === 'function') {
    let current = createPlayerLinks(null);
    const isTouch = () => typeof matchMedia === 'function' && matchMedia('(hover: none)').matches;
    window.PlayerLinks = {
      // Resolves after the index loads, fails, or 3 s pass; a late index is still used by later renders.
      ready: raceWithTimeout(
        fetch(INDEX_URL)
          .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
          .then(data => { current = createPlayerLinks(data); }, () => {}),
        setTimeout, 3000),
      url: (name, ids) => current.url(name, ids),
      link: (name, label, ids, extraClass) => current.link(name, label, ids, extraClass),
      // Hover-tooltip line for linked points (touch needs two taps, see bindChartClicks).
      chartHint: () => (isTouch() ? 'Tap again for career' : 'Click for career'),
      // container: the Plotly graph div element; each point's customdata is the raw player name.
      // Mouse: a click navigates. Touch: the first tap only shows the tooltip, a second tap on the same point navigates.
      bindChartClicks(container) {
        const drag = () => container.querySelector('.nsewdrag');
        const urlOf = ev => { const pt = ev.points && ev.points[0]; return pt ? current.url(pt.customdata) : null; };
        const gate = createTapGate(4000);
        container.on('plotly_click', ev => {
          const href = urlOf(ev);
          if (!href) return;
          const pt = ev.points[0];
          const pType = ev.event && ev.event.pointerType;
          const touch = pType ? pType === 'touch' : isTouch();
          if (touch && !gate(pt.curveNumber + ':' + pt.pointNumber, Date.now())) return;
          location.href = href;
        });
        container.on('plotly_hover', ev => { const d = drag(); if (d) d.style.cursor = urlOf(ev) ? 'pointer' : ''; });
        container.on('plotly_unhover', () => { const d = drag(); if (d) d.style.cursor = ''; });
      },
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { createPlayerLinks, createTapGate, raceWithTimeout };
})();
