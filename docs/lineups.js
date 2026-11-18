'use strict';

const LINEUPS_URL   = 'data/current/lineups.json';
const MIN_POSS_5    = 75;
const MIN_POSS_2    = 150;

let lineupData  = null;
let activeTab   = 'fiveman';
let activeSeason = null;
let activeTeam  = 'ALL';
let sortCol     = 'netrtg';
let sortAsc     = false;

document.addEventListener('DOMContentLoaded', async () => {
  try {
    [lineupData] = await Promise.all([fetchJSON(LINEUPS_URL), PlayerLinks.ready]);
  } catch (e) {
    document.getElementById('lineups-table-container').innerHTML =
      '<p style="color:var(--text-muted);padding:40px;text-align:center">Could not load lineup data.</p>';
    return;
  }

  activeSeason = Math.max(...lineupData.seasons);
  buildSeasonSelector();
  buildTeamFilter();
  document.getElementById('team-select').addEventListener('change', () => {
    activeTeam = document.getElementById('team-select').value;
    renderTable();
  });
  bindTabButtons();
  renderTable();
});

function buildSeasonSelector() {
  const sel = document.getElementById('season-select');
  lineupData.seasons.slice().reverse().forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = `${s}-${String(s + 1).slice(-2)}`;
    if (s === activeSeason) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.addEventListener('change', () => {
    activeSeason = parseInt(sel.value, 10);
    activeTeam = 'ALL';
    buildTeamFilter();
    renderTable();
  });
}

function buildTeamFilter() {
  const sel = document.getElementById('team-select');
  sel.innerHTML = '<option value="ALL">All Teams</option>';
  const rows = lineupData[activeTab].filter(r => r.season === activeSeason);
  const teams = [...new Set(rows.map(r => r.team))].sort();
  teams.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = (typeof TEAM_NAMES !== 'undefined' && TEAM_NAMES[t]) || t;
    if (t === activeTeam) opt.selected = true;
    sel.appendChild(opt);
  });
}

function bindTabButtons() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      activeTab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeTeam = 'ALL';
      document.getElementById('team-select').value = 'ALL';
      buildTeamFilter();
      renderTable();
    });
  });
}

function renderTable() {
  let rows = lineupData[activeTab]
    .filter(r => r.season === activeSeason)
    .filter(r => activeTeam === 'ALL' || r.team === activeTeam);

  rows.sort((a, b) => {
    const av = a[sortCol], bv = b[sortCol];
    const aStr = Array.isArray(av) ? av.join(', ') : av;
    const bStr = Array.isArray(bv) ? bv.join(', ') : bv;
    if (typeof aStr === 'string') return sortAsc ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
    return sortAsc ? aStr - bStr : bStr - aStr;
  });

  const minPoss = activeTab === 'fiveman' ? MIN_POSS_5 : MIN_POSS_2;
  const label   = activeTab === 'fiveman' ? 'lineups' : 'pairs';
  const container = document.getElementById('lineups-table-container');

  if (rows.length === 0) {
    container.innerHTML = `<p style="color:var(--text-muted);padding:40px;text-align:center">No ${label} meeting the minimum ${minPoss} possessions threshold.</p>`;
    document.getElementById('lineups-count').textContent = '';
    return;
  }

  const cols = [
    { key: 'players', label: 'Players',  align: 'left'  },
    { key: 'team',    label: 'Team',     align: 'left'  },
    { key: 'gp',      label: 'GP',       align: 'right' },
    { key: 'poss',    label: 'Poss',     align: 'right' },
    { key: 'ortg',    label: 'ORtg',     align: 'right' },
    { key: 'drtg',    label: 'DRtg',     align: 'right' },
    { key: 'netrtg',  label: 'Net',      align: 'right' },
  ];

  const thead = cols.map(c => {
    const arrow = c.key === sortCol ? (sortAsc ? ' ↑' : ' ↓') : '';
    return `<th class="sortable${c.align === 'right' ? ' text-right' : ''}" data-col="${c.key}">${c.label}${arrow}</th>`;
  }).join('');

  const tbody = rows.map(r => {
    const net      = r.netrtg;
    const netColor = net > 0 ? 'var(--accent-green)' : net < 0 ? 'var(--accent-red)' : 'var(--text-muted)';
    const netStr   = (net > 0 ? '+' : '') + net.toFixed(1);
    const names    = Array.isArray(r.players) ? r.players : [r.players];
    const players  = names.map(n => PlayerLinks.link(n)).join(', ');
    return `<tr>
      <td class="text-left players-cell">${players}</td>
      <td class="text-left">${r.team}</td>
      <td class="text-right">${r.gp}</td>
      <td class="text-right">${r.poss}</td>
      <td class="text-right">${r.ortg.toFixed(1)}</td>
      <td class="text-right">${r.drtg.toFixed(1)}</td>
      <td class="text-right" style="color:${netColor};font-weight:700">${netStr}</td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <table class="lineups-table">
      <thead><tr>${thead}</tr></thead>
      <tbody>${tbody}</tbody>
    </table>`;

  container.querySelectorAll('th.sortable').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      if (sortCol === th.dataset.col) {
        sortAsc = !sortAsc;
      } else {
        sortCol = th.dataset.col;
        sortAsc = false;
      }
      renderTable();
    });
  });

  document.getElementById('lineups-count').textContent =
    `Showing ${rows.length} ${label} (min. ${minPoss} possessions)`;
}
