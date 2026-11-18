/* Shared helper that turns player names into links to the career page
   (player.html?code=<code>). Resolves a career code from an explicit id or from
   the normalized "LAST, FIRST" name via data/current/player_index.json.
   Unlike nav.js this deliberately defines one browser global, PlayerLinks.
   Until the index loads (or if it fails) url() is null and link() is plain
   escaped text. In Node only createPlayerLinks is exported. */

(function () {
  'use strict';

  const INDEX_URL = 'data/current/player_index.json';

  // Mirrors normalize_name in fetch_player_career_stats.py.
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

    function link(name, label, ids) {
      const text = escapeHtml(label === undefined || label === null ? name : label);
      const href = url(name, ids);
      return href ? '<a class="player-link" href="' + href + '">' + text + '</a>' : text;
    }

    return { url, link };
  }

  if (typeof window !== 'undefined' && typeof fetch === 'function') {
    let current = createPlayerLinks(null);
    window.PlayerLinks = {
      ready: fetch(INDEX_URL)
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => { current = createPlayerLinks(data); }, () => {}),
      url: (name, ids) => current.url(name, ids),
      link: (name, label, ids) => current.link(name, label, ids),
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { createPlayerLinks };
})();
