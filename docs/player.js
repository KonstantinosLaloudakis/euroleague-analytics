// player.js
const DATA_URL = 'data/current/player_career_stats.json';
let CURRENT_SEASON_CODE = 'E2025';  // overwritten from dashboard.json season

// Season of the live dashboard (pre-2026 dashboards had no field -> 2025).
async function loadCurrentSeasonCode() {
    try {
        const dash = await fetch('data/current/dashboard.json').then(r => r.json());
        CURRENT_SEASON_CODE = 'E' + (dash.season || 2025);
    } catch { /* keep default */ }
}

let careerData = null;

document.addEventListener('DOMContentLoaded', async () => {
    const code = new URLSearchParams(window.location.search).get('code');
    if (!code) { await showWelcome(); return; }

    await loadCurrentSeasonCode();
    try {
        careerData = await fetch(DATA_URL).then(r => r.json());
    } catch (e) {
        showError('Could not load player data. Run the data pipeline first.'); return;
    }

    const player = careerData.players[code];
    if (!player) { showError(`Player not found: ${code}`); return; }

    document.title = `${player.name} — EL Analytics`;

    const el = document.getElementById('player-content');
    el.innerHTML = renderHero(player) + renderChart(player.seasons) + renderTableSection(player);
    setupTabs(player);
    setupSort(player);
});

// ── Hero card ──────────────────────────────────────────────────────────────────
function renderHero(player) {
    const initials = player.name.split(/\s+/).map(w => w[0]).filter(Boolean).slice(0, 2).join('');
    const current  = player.seasons[0];
    const first    = player.seasons[player.seasons.length - 1];
    const span     = (first && current && first !== current)
        ? `${first.season.slice(0, 4)}–${current.season.slice(5)}`
        : (current ? current.season : '');
    const seasonLbl = current ? current.season : '—';
    const fmt = (v) => (v != null ? v.toFixed(1) : '—');

    const avatarHtml = player.image
        ? `<img class="hero-avatar" src="${player.image}" alt="${player.name}" onerror="this.outerHTML='<div class=\\'hero-avatar\\'>${initials}</div>'">`
        : `<div class="hero-avatar">${initials}</div>`;

    return `
    <div class="hero-card">
      ${avatarHtml}
      <div>
        <div class="hero-name">${player.name}</div>
        <div class="hero-meta">${[player.position, player.nationality].filter(Boolean).join(' · ')}</div>
        <div class="hero-tags">
          ${current ? `<span class="tag tag-team">${current.team_name || current.team_code}</span>` : ''}
          <span class="tag tag-span">${player.seasons.length} season${player.seasons.length !== 1 ? 's' : ''}${span ? ' · ' + span : ''}</span>
        </div>
      </div>
      <div>
        <div class="season-label">${seasonLbl}</div>
        <div class="hero-stats-grid">
          <div class="hero-stat"><div class="val gold">${fmt(current?.ppg)}</div><div class="lbl">PPG</div></div>
          <div class="hero-stat"><div class="val">${fmt(current?.rpg)}</div><div class="lbl">RPG</div></div>
          <div class="hero-stat"><div class="val">${fmt(current?.apg)}</div><div class="lbl">APG</div></div>
          <div class="hero-stat"><div class="val green">${fmt(current?.pir)}</div><div class="lbl">PIR</div></div>
        </div>
      </div>
    </div>`;
}

// ── PIR trend chart ────────────────────────────────────────────────────────────
function renderChart(seasons) {
    if (!seasons.length) return '';
    const pirs   = seasons.map(s => s.pir || 0);
    const maxPIR = Math.max(...pirs, 1);
    const peak   = Math.max(...pirs);
    const peakSzn = seasons.find(s => s.pir === peak);
    const H = 64, W_BAR = 18, GAP = 4;
    const totalW = seasons.length * (W_BAR + GAP);

    const bars = [...seasons].reverse().map((s, i) => {
        const h    = Math.max(2, Math.round((s.pir || 0) / maxPIR * H));
        const x    = i * (W_BAR + GAP);
        const y    = H - h;
        const isCurrent = s.season_code === CURRENT_SEASON_CODE;
        const isPeak    = s.pir === peak && peak > 0;
        const fill  = isCurrent ? '#38bdf8' : isPeak ? '#818cf8' : '#2563eb';
        const lbl   = s.season.slice(2, 4) + '-' + s.season.slice(5, 7);
        return `<rect x="${x}" y="${y}" width="${W_BAR}" height="${h}" fill="${fill}" rx="2"/>
                <text x="${x + W_BAR / 2}" y="${H + 14}" text-anchor="middle" fill="#475569" font-size="7">${lbl}</text>`;
    }).join('');

    return `
    <div class="card">
      <div class="chart-header">
        <div>
          <div class="card-title">Career PIR Trend</div>
          <div class="card-sub">Performance Index Rating per game · all Euroleague seasons</div>
        </div>
        ${peakSzn ? `<div class="chart-peak">Peak: ${peak.toFixed(1)} (${peakSzn.season})</div>` : ''}
      </div>
      <div class="pir-chart">
        <svg viewBox="0 0 ${totalW} ${H + 20}" style="width:100%;min-width:${Math.min(totalW, 300)}px;height:90px">
          ${bars}
        </svg>
      </div>
      <div class="chart-legend">
        <div class="legend-item"><div class="legend-dot" style="background:#2563eb"></div>Past</div>
        <div class="legend-item"><div class="legend-dot" style="background:#818cf8"></div>Career peak</div>
        <div class="legend-item"><div class="legend-dot" style="background:#38bdf8"></div>Current season</div>
      </div>
    </div>`;
}

// ── Stat table ─────────────────────────────────────────────────────────────────
const TABS = {
    scoring:    { label: 'Scoring',    cols: ['ppg','rpg','apg','spg','bpg','tpg','pir'] },
    shooting:   { label: 'Shooting',   cols: ['ppg','fg2_pct','fg3_pct','ft_pct'] },
    rebounding: { label: 'Rebounding', cols: ['rpg','oreb','dreb','bpg'] },
    all:        { label: 'All Stats',  cols: ['ppg','rpg','oreb','dreb','apg','spg','bpg','tpg','fg2_pct','fg3_pct','ft_pct','pir'] },
};
const COL_LABELS = {
    ppg:'PPG', rpg:'RPG', oreb:'OREB', dreb:'DREB',
    apg:'APG', spg:'SPG', bpg:'BPG', tpg:'TPG',
    fg2_pct:'2P%', fg3_pct:'3P%', ft_pct:'FT%', pir:'PIR',
};

function renderTableSection(player) {
    const tabs = Object.entries(TABS).map(([k, t]) =>
        `<button class="tab-btn${k === 'scoring' ? ' active' : ''}" data-tab="${k}">${t.label}</button>`
    ).join('');
    return `
    <div class="card" style="padding:0;margin-bottom:0">
      <div class="tab-bar">${tabs}</div>
      <div id="table-wrap" style="overflow-x:auto;padding:12px 0 0">${buildTable(player, 'scoring')}</div>
    </div>`;
}

function buildTable(player, tabKey) {
    const cols = TABS[tabKey].cols;
    const fmt  = (v) => (v != null ? v.toFixed(1) : '<span style="color:var(--text-muted)">—</span>');
    const hl   = c => c === 'ppg' ? 'val-gold' : c === 'pir' ? 'val-green' : '';

    const head = `<tr><th>Season</th><th>Team</th><th style="text-align:right">GP</th>${
        cols.map(c => `<th data-col="${c}">${COL_LABELS[c]}</th>`).join('')}</tr>`;

    const rows = player.seasons.map(s => {
        const isCur = s.season_code === CURRENT_SEASON_CODE;
        const cells = cols.map(c => `<td class="${hl(c)}">${fmt(s[c])}</td>`).join('');
        return `<tr class="${isCur ? 'current-szn' : ''}">
          <td><span class="szn-link">${s.season}</span></td>
          <td>${s.team_name || s.team_code}</td>
          <td style="text-align:right">${s.gp ?? '—'}</td>${cells}</tr>`;
    }).join('');

    const car = player.career;
    const carCells = cols.map(c => `<td class="${hl(c)}">${fmt(car[c])}</td>`).join('');
    const carRow = `<tr class="career-row">
      <td>Career</td><td style="color:var(--text-muted)">—</td>
      <td style="text-align:right">${car.gp}</td>${carCells}</tr>`;

    return `<table class="stat-table"><thead>${head}</thead><tbody>${rows}${carRow}</tbody></table>`;
}

function setupTabs(player) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _sortCol = null; _sortAsc = false; // reset sort state on tab switch
            document.getElementById('table-wrap').innerHTML =
                '<div style="padding:0">' + buildTable(player, btn.dataset.tab) + '</div>';
            setupSort(player);
        });
    });
}

// ── Column sort ────────────────────────────────────────────────────────────────
let _sortCol = null, _sortAsc = false;

function setupSort(player) {
    document.querySelectorAll('.stat-table thead th[data-col]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.col;
            _sortAsc = _sortCol === col ? !_sortAsc : false;
            _sortCol = col;
            const sorted = [...player.seasons].sort((a, b) => {
                const va = a[col] ?? -Infinity, vb = b[col] ?? -Infinity;
                return _sortAsc ? va - vb : vb - va;
            });
            const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab || 'scoring';
            document.getElementById('table-wrap').innerHTML =
                '<div style="padding:0">' + buildTable({...player, seasons: sorted}, activeTab) + '</div>';
            setupSort(player);
        });
    });
}

async function showWelcome() {
    document.title = 'Player Career Search — EL Analytics';
    const el = document.getElementById('player-content');
    el.innerHTML = `
    <div style="max-width:480px;margin:60px auto;text-align:center">
      <div style="font-size:36px;margin-bottom:12px">🏀</div>
      <h2 style="font-size:20px;font-weight:700;color:var(--text-primary);margin-bottom:6px">Player Career Search</h2>
      <p id="player-count" style="font-size:13px;color:var(--text-muted);margin-bottom:24px">
        Loading…
      </p>
      <div style="position:relative">
        <input id="welcome-search" type="text" placeholder="Type a player name…"
          autocomplete="off"
          style="width:100%;padding:12px 16px;font-size:15px;font-family:inherit;
                 background:var(--bg-secondary);border:1px solid var(--border);
                 border-radius:10px;color:var(--text-primary);outline:none;box-sizing:border-box">
        <div id="welcome-dropdown"
          style="display:none;position:absolute;top:calc(100% + 6px);left:0;right:0;
                 background:var(--bg-secondary);border:1px solid var(--border);
                 border-radius:10px;max-height:300px;overflow-y:auto;
                 box-shadow:0 8px 24px rgba(0,0,0,.5);z-index:10;text-align:left"></div>
      </div>
    </div>`;

    let index = [];
    try {
        const data = await fetch(DATA_URL).then(r => r.json());
        index = data.index;
        careerData = data;
        const years = new Set();
        Object.values(data.players || {}).forEach(p => (p.seasons || []).forEach(s => {
            const y = parseInt(String(s.season_code).slice(1), 10);
            if (y) years.add(y);
        }));
        const lastYear = years.size ? Math.max(...years) : 2025;
        document.getElementById('player-count').textContent =
            `${index.length.toLocaleString()} players · ${years.size} seasons · 2007–${lastYear}`;
    } catch { return; }

    const input = document.getElementById('welcome-search');
    const drop  = document.getElementById('welcome-dropdown');
    input.focus();

    input.addEventListener('input', () => {
        const q = input.value.trim().toLowerCase();
        drop.innerHTML = '';
        if (q.length < 2) { drop.style.display = 'none'; return; }
        const matches = index.filter(p => p.name.toLowerCase().includes(q)).slice(0, 12);
        if (!matches.length) { drop.style.display = 'none'; return; }
        matches.forEach(p => {
            const item = document.createElement('div');
            item.style.cssText = 'padding:10px 14px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;font-size:13px';
            item.innerHTML = `<span style="color:var(--text-primary)">${p.name}</span><span style="font-size:11px;color:var(--text-muted)">${p.current_team || ''} · ${p.seasons}s</span>`;
            item.addEventListener('mouseover', () => item.style.background = 'var(--bg-primary)');
            item.addEventListener('mouseout',  () => item.style.background = '');
            item.addEventListener('click', () => { window.location.href = `player.html?code=${encodeURIComponent(p.code)}`; });
            drop.appendChild(item);
        });
        drop.style.display = 'block';
    });
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { const first = drop.querySelector('div'); if (first) first.click(); }
    });
    document.addEventListener('click', e => {
        if (!input.contains(e.target) && !drop.contains(e.target)) drop.style.display = 'none';
    });
}

function showError(msg) {
    const el = document.getElementById('player-content');
    if (el) el.innerHTML = `<p class="error-msg">${msg}</p>`;
}
