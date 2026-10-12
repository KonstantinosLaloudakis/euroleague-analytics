'use strict';

const COMPARE_DATA_URL = 'data/current/player_career_stats.json';

const TOT_STATS = [
  { key: 'ppg',     label: 'PPG',  pct: false },
  { key: 'rpg',     label: 'RPG',  pct: false },
  { key: 'apg',     label: 'APG',  pct: false },
  { key: 'spg',     label: 'SPG',  pct: false },
  { key: 'bpg',     label: 'BPG',  pct: false },
  { key: 'pir',     label: 'PIR',  pct: false },
  { key: 'fg2_pct', label: 'FG2%', pct: true  },
  { key: 'fg3_pct', label: '3P%',  pct: true  },
  { key: 'ft_pct',  label: 'FT%',  pct: true  },
];

const TABLE_COLS = [
  { key: 'ppg',     label: 'PPG',  dec: 1 },
  { key: 'rpg',     label: 'RPG',  dec: 1 },
  { key: 'apg',     label: 'APG',  dec: 1 },
  { key: 'spg',     label: 'SPG',  dec: 1 },
  { key: 'pir',     label: 'PIR',  dec: 1 },
  { key: 'fg2_pct', label: 'FG2%', dec: 1 },
  { key: 'fg3_pct', label: '3P%',  dec: 1 },
];

let _lookup = {};   // code → player object
let _index  = [];   // [{code, name, current_team, seasons}]
let _slotA  = null; // enriched player object (with _code) or null
let _slotB  = null; // enriched player object (with _code) or null

function buildLookup(data) {
  _index = data.index || [];
  _lookup = {};
  Object.entries(data.players || {}).forEach(([code, player]) => {
    _lookup[code] = player;
  });
}

function getParams() {
  const p = new URLSearchParams(window.location.search);
  return { a: p.get('a'), b: p.get('b') };
}

function updateURL() {
  const p = new URLSearchParams();
  if (_slotA) p.set('a', _slotA._code);
  if (_slotB) p.set('b', _slotB._code);
  const qs = p.toString();
  history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
}

function lastTeamCode(player) {
  return player.seasons && player.seasons[0] && player.seasons[0].team_code;
}

// Raw brand colour: solid fills that carry text (pair with lastTeamOn)
function lastTeamColor(player) {
  const code = lastTeamCode(player);
  return (code && typeof TEAM_COLORS !== 'undefined' && TEAM_COLORS[code]) || '#1d4ed8';
}

// Readable-on-dark colour for text, accent stripes and small bars
function lastTeamInk(player) {
  const code = lastTeamCode(player);
  return (code && typeof TEAM_COLORS !== 'undefined' && TEAM_COLORS[code]) ? teamInk(code) : '#1d4ed8';
}

// Text colour for use on a solid lastTeamColor background
function lastTeamOn(player) {
  const code = lastTeamCode(player);
  return (code && typeof TEAM_COLORS !== 'undefined' && TEAM_COLORS[code]) ? teamOnColor(code) : '#ffffff';
}

function playerInitials(player) {
  return player.name.split(/[\s,]+/).filter(Boolean).map(w => w[0]).slice(0, 2).join('');
}

function fmt(v, dec = 1) {
  return (v != null && !isNaN(v)) ? Number(v).toFixed(dec) : '—';
}

function syncInputs() {
  document.getElementById('input-a').value = _slotA ? _slotA.name : '';
  document.getElementById('input-b').value = _slotB ? _slotB.name : '';
}

function renderAll() {
  renderHeroCards();
  renderToT();
  renderSeasonTables();
}

function setupSearch(slot) {
  const input    = document.getElementById(`input-${slot}`);
  const dropdown = document.getElementById(`dropdown-${slot}`);
  let activeIdx  = -1;

  function hideDropdown() {
    dropdown.style.display = 'none';
    dropdown.innerHTML = '';
    activeIdx = -1;
  }

  function selectItem(code) {
    const player = _lookup[code];
    if (!player) return;
    if (slot === 'a') _slotA = Object.assign({ _code: code }, player);
    else              _slotB = Object.assign({ _code: code }, player);
    updateURL();
    syncInputs();
    hideDropdown();
    renderAll();
  }

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 1) { hideDropdown(); return; }

    const matches = _index
      .filter(p => p.name.toLowerCase().includes(q))
      .slice(0, 12);

    if (matches.length === 0) { hideDropdown(); return; }

    dropdown.innerHTML = matches.map((p, i) => `
      <div class="autocomplete-item" data-code="${p.code}" data-idx="${i}">
        <span>${p.name}</span>
        <span class="autocomplete-item-meta">${p.current_team || ''} · ${p.seasons} szn${p.seasons !== 1 ? 's' : ''}</span>
      </div>
    `).join('');
    dropdown.style.display = 'block';
    activeIdx = -1;
  });

  dropdown.addEventListener('mousedown', e => {
    const item = e.target.closest('.autocomplete-item');
    if (item) selectItem(item.dataset.code);
  });

  input.addEventListener('keydown', e => {
    const items = dropdown.querySelectorAll('.autocomplete-item');
    if (!items.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
      items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const active = dropdown.querySelector('.autocomplete-item.active');
      if (active) selectItem(active.dataset.code);
      else if (items.length === 1) selectItem(items[0].dataset.code);
    } else if (e.key === 'Escape') {
      hideDropdown();
    }
  });

  input.addEventListener('blur', () => setTimeout(hideDropdown, 150));
}

function renderHeroCard(player) {
  const color    = lastTeamColor(player);
  const ink      = lastTeamInk(player);
  const onColor  = lastTeamOn(player);
  const initials = playerInitials(player);
  const current  = player.seasons && player.seasons[0];
  const first    = player.seasons && player.seasons[player.seasons.length - 1];
  const span = (first && current && first !== current)
    ? `${first.season.slice(0, 4)}–${current.season.slice(5)}`
    : (current ? current.season : '');

  const teams = [];
  const seen  = new Set();
  (player.seasons || []).forEach(s => {
    if (s.team_name && !seen.has(s.team_code)) {
      seen.add(s.team_code);
      teams.push(s.team_name);
    }
  });

  const avatarHtml = player.image
    ? `<img class="compare-avatar" src="${player.image}" alt="${player.name}"
           style="--team-color:${color}"
           onerror="this.outerHTML='<div class=\\'compare-avatar\\' style=\\'--team-color:${color};color:${onColor}\\'>${initials}</div>'">`
    : `<div class="compare-avatar" style="--team-color:${color};color:${onColor}">${initials}</div>`;

  return `
    <div class="compare-hero-card" style="--team-color:${ink}">
      ${avatarHtml}
      <div>
        <div class="compare-hero-name">${player.name}</div>
        <div class="compare-hero-meta">${[player.position, player.nationality].filter(Boolean).join(' · ')}</div>
        <div class="compare-hero-tags">
          ${current ? `<span class="tag tag-team">${current.team_name || current.team_code}</span>` : ''}
          <span class="tag tag-span">${player.seasons.length} season${player.seasons.length !== 1 ? 's' : ''}${span ? ' · ' + span : ''}</span>
        </div>
      </div>
    </div>`;
}

function renderHeroCards() {
  const el = document.getElementById('compare-heroes');
  if (!_slotA && !_slotB) { el.innerHTML = ''; return; }

  if (_slotA && _slotB) {
    el.innerHTML = `
      <div class="compare-heroes">
        ${renderHeroCard(_slotA)}
        <div class="compare-vs">VS</div>
        ${renderHeroCard(_slotB)}
      </div>`;
  } else {
    const player = _slotA || _slotB;
    el.innerHTML = `
      <div class="compare-heroes" style="grid-template-columns:1fr">
        ${renderHeroCard(player)}
        <p class="compare-hero-prompt">Search a second player to compare</p>
      </div>`;
  }
}

function renderToT() {
  const el = document.getElementById('compare-tot');
  if (!_slotA || !_slotB) { el.innerHTML = ''; return; }

  const careerA = _slotA.career || {};
  const careerB = _slotB.career || {};
  const colorA  = lastTeamInk(_slotA);
  const colorB  = lastTeamInk(_slotB);

  const rowsHtml = TOT_STATS.map(({ key, label, pct }) => {
    const vA = careerA[key];
    const vB = careerB[key];
    if (vA == null && vB == null) return '';

    const numA   = Number(vA) || 0;
    const numB   = Number(vB) || 0;
    const aWins  = numA >= numB;
    let pctA, pctB;
    if (pct) {
      // percentage stats: scale bars relative to 100% max so 52% vs 48% shows nearly equal bars
      pctA = Math.max(15, Math.min(85, Math.round(numA)));
      pctB = Math.max(15, Math.min(85, Math.round(numB)));
      const sumAB = pctA + pctB;
      pctA = Math.round((pctA / sumAB) * 100);
      pctB = 100 - pctA;
    } else {
      const total = numA + numB || 1;
      pctA = Math.max(15, Math.min(85, Math.round((numA / total) * 100)));
      pctB = 100 - pctA;
    }
    const suffix = pct ? '%' : '';

    return `
      <div class="tot-row-block">
        <div class="tot-row-label">${label}</div>
        <div class="tot-row">
          <div class="tot-value high ${!aWins ? 'dim' : ''}">${fmt(vA)}${suffix}</div>
          <div class="tot-bar-wrap">
            <div class="tot-bar-half high ${!aWins ? 'dim' : ''}"
                 style="width:${pctA}%;background:${colorA}"></div>
            <div class="tot-bar-half low ${aWins ? 'dim' : ''}"
                 style="width:${pctB}%;background:${colorB}"></div>
          </div>
          <div class="tot-value low ${aWins ? 'dim' : ''}">${fmt(vB)}${suffix}</div>
        </div>
      </div>`;
  }).join('');

  el.innerHTML = `
    <div class="stat-card">
      <h3>Career Averages</h3>
      <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px">
        <span style="color:${colorA};font-weight:700">${_slotA.name}</span>
        <span style="color:${colorB};font-weight:700">${_slotB.name}</span>
      </div>
      <div class="tot-rows">${rowsHtml}</div>
    </div>`;
}

function buildSeasonTable(player) {
  const color  = lastTeamColor(player);
  const career = player.career || {};

  const headerCols = TABLE_COLS.map(c => `<th>${c.label}</th>`).join('');
  const careerCols = TABLE_COLS.map(c => `<td>${fmt(career[c.key], c.dec)}</td>`).join('');

  const seasonRows = (player.seasons || []).map(s => {
    const cols = TABLE_COLS.map(c => `<td>${fmt(s[c.key], c.dec)}</td>`).join('');
    return `<tr>
      <td>${s.season}</td>
      <td>${s.team_name || s.team_code}</td>
      <td>${s.gp != null ? Math.round(s.gp) : '—'}</td>
      ${cols}
    </tr>`;
  }).join('');

  return `
    <div class="compare-table-wrap">
      <div class="compare-table-header" style="background:${color};color:${lastTeamOn(player)}">${player.name}</div>
      <table class="stat-table">
        <thead>
          <tr>
            <th style="text-align:left">Season</th>
            <th style="text-align:left">Team</th>
            <th>GP</th>
            ${headerCols}
          </tr>
        </thead>
        <tbody>
          <tr class="career-row">
            <td>Career</td>
            <td></td>
            <td>${career.gp != null ? Math.round(career.gp) : '—'}</td>
            ${careerCols}
          </tr>
          ${seasonRows}
        </tbody>
      </table>
    </div>`;
}

function renderSeasonTables() {
  const el = document.getElementById('compare-tables');
  if (!_slotA && !_slotB) { el.innerHTML = ''; return; }

  if (_slotA && _slotB) {
    el.innerHTML = `<div class="compare-tables-row">${buildSeasonTable(_slotA)}${buildSeasonTable(_slotB)}</div>`;
  } else {
    const player = _slotA || _slotB;
    el.innerHTML = `<div>${buildSeasonTable(player)}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  let data;
  try {
    data = await fetchJSON(COMPARE_DATA_URL);
  } catch {
    document.getElementById('compare-heroes').innerHTML =
      '<p class="compare-empty">Could not load player data.</p>';
    return;
  }
  buildLookup(data);

  const { a, b } = getParams();
  if (a && _lookup[a]) _slotA = Object.assign({ _code: a }, _lookup[a]);
  if (b && _lookup[b]) _slotB = Object.assign({ _code: b }, _lookup[b]);

  setupSearch('a');
  setupSearch('b');

  document.getElementById('swap-btn').addEventListener('click', () => {
    [_slotA, _slotB] = [_slotB, _slotA];
    updateURL();
    syncInputs();
    renderAll();
  });

  syncInputs();
  renderAll();
});
