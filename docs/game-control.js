/**
 * game-control.js — Game Control Index page
 * Storylines, scatter plot, leaderboard, team deep-dive, superlatives
 */
'use strict';

/* ── Global state ──────────────────────────────────────────────────────── */
let _data = null;
let _gc   = null;
let _selectedTeam = null;
let _sortCol = 'gci';
let _sortAsc = false;

/* ── Column definitions for leaderboard ────────────────────────────────── */
const COLS = [
    { key: 'gci',           label: 'GCI',       fmt: v => v.toFixed(1) },
    { key: 'dominance_avg', label: 'Dominance',  fmt: v => v.toFixed(3) },
    { key: 'control_pct',   label: 'Control%',   fmt: v => (v * 100).toFixed(0) + '%' },
    { key: 'drama_avg',     label: 'Drama',      fmt: v => v.toFixed(2) },
    { key: 'crunch_swing_avg', label: 'Crunch',  fmt: v => { const s = v >= 0 ? '+' : ''; const c = v >= 0 ? '#4ecdc4' : '#ff6b6b'; return `<span style="color:${c}">${s}${v.toFixed(3)}</span>`; } },
    { key: 'killer_instinct',  label: 'Killer',  fmt: v => v.toFixed(3) },
    { key: 'comeback_count',   label: 'Comebacks', fmt: v => v },
];

/* ── Boot ──────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    fetchJSON('data/current/dashboard.json')
        .then(data => {
            _data = data;
            _gc = data.game_control;
            if (isEmptyData(_gc)) {
                // Early season: no Game Control data yet — show empty state
                document.getElementById('loading').classList.add('hidden');
                const le = document.getElementById('load-error');
                le.querySelector('p').textContent = 'Game Control data will appear once this season has enough games.';
                le.classList.remove('hidden');
                return;
            }
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('content').classList.remove('hidden');
            renderStorylines();
            renderGameOfRound();
            renderScatter();
            renderLeaderboard();
            renderTeamGrid();
            renderSuperlatives();
            restoreFromURL();
        })
        .catch(err => {
            console.error('Failed to load GCI data:', err);
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('load-error').classList.remove('hidden');
        });
});

/* ── URL restore ───────────────────────────────────────────────────────── */
function restoreFromURL() {
    const params = new URLSearchParams(window.location.search);
    const team = params.get('team');
    if (team && _gc.teams[team]) {
        selectTeam(team);
    } else {
        // default to top GCI team
        const sorted = Object.entries(_gc.teams)
            .sort((a, b) => b[1].gci - a[1].gci);
        if (sorted.length) selectTeam(sorted[0][0]);
    }
}

/* ── 1. Storylines ─────────────────────────────────────────────────────── */
function renderStorylines() {
    const wrap = document.getElementById('storylines');
    if (!_gc.storylines || !_gc.storylines.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted)">No storylines available.</p>';
        return;
    }
    wrap.innerHTML = _gc.storylines.map(s => {
        const name = TEAM_NAMES[s.team] || s.team;
        const color = teamInk(s.team);
        const badges = [s.stat_label, s.stat_sub].filter(Boolean).map(b =>
            `<span class="storyline-badge" style="background:${color}22;color:${color}">${b}</span>`
        ).join('');
        return `<div class="storyline-card" style="border-left-color:${color}" onclick="selectTeam('${s.team}')">
            <div class="storyline-label" style="color:${color}">${s.label || 'Storyline'}</div>
            <div class="storyline-team">${name}</div>
            <div class="storyline-text">${s.text}</div>
            <div class="storyline-badges">${badges}</div>
        </div>`;
    }).join('');
}

/* ── 2. Game of the Round ──────────────────────────────────────────────── */
function renderGameOfRound() {
    const wrap = document.getElementById('game-of-round');
    const g = _gc.game_of_round;
    if (!g) {
        wrap.innerHTML = '<p style="color:var(--text-muted)">No game of the round data.</p>';
        return;
    }

    const homeColor = teamInk(g.home);
    const awayColor = teamInk(g.away);
    const homeName = TEAM_NAMES[g.home] || g.home;
    const awayName = TEAM_NAMES[g.away] || g.away;

    // Build mini WP SVG polyline
    let wpSvg = '';
    if (g.wp_curve && g.wp_curve.length > 1) {
        const pts = g.wp_curve;
        const w = 300, h = 70;
        const step = w / (pts.length - 1);
        const coords = pts.map((v, i) => `${(i * step).toFixed(1)},${(h - v[1] * h).toFixed(1)}`).join(' ');
        wpSvg = `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:70px;" preserveAspectRatio="none">
            <line x1="0" y1="${h / 2}" x2="${w}" y2="${h / 2}" stroke="#4b5563" stroke-width="0.5" stroke-dasharray="4"/>
            <polyline points="${coords}" fill="none" stroke="#4ecdc4" stroke-width="2"/>
        </svg>`;
    }

    // Metric tags
    let tagsHtml = '';
    tagsHtml += `<span class="gor-tag" style="background:rgba(255,107,107,0.15);color:#ff6b6b">Drama: ${g.drama.toFixed(2)}</span>`;
    if (g.comeback > 0.5) {
        tagsHtml += `<span class="gor-tag" style="background:rgba(255,215,0,0.12);color:#ffd700">Comeback: ${(g.comeback * 100).toFixed(0)}%</span>`;
    }
    tagsHtml += `<span class="gor-tag" style="background:rgba(78,205,196,0.12);color:#4ecdc4">Crunch: ${g.crunch_home > 0 ? '+' : ''}${g.crunch_home.toFixed(2)}</span>`;

    const replayLink = g.gamecode
        ? `<a href="replay.html?season=${dashboardSeason(_data)}&game=${g.gamecode}"
              style="display:inline-block;margin-top:0.8rem;padding:0.5rem 1.2rem;background:linear-gradient(135deg,#4ecdc4,#45b7aa);color:#0f1117;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.78rem;transition:opacity 0.2s;"
              onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">
              ▶ Watch Full WP Replay</a>`
        : '';

    wrap.innerHTML = `<div class="gor-card">
        <div class="gor-header">
            <span style="font-size:0.75rem;color:var(--text-muted);font-weight:600;">Round ${g.round || ''}</span>
        </div>
        <div class="gor-body">
            <div class="gor-score">
                <div class="gor-team-code" style="color:${homeColor}">${homeName}</div>
                <div class="gor-pts">${g.home_score ?? '—'}</div>
                <div class="gor-venue">HOME</div>
            </div>
            <div class="gor-wp-wrap">
                ${wpSvg || '<div style="text-align:center;color:var(--text-muted);font-size:0.75rem;">No WP curve</div>'}
            </div>
            <div class="gor-score">
                <div class="gor-team-code" style="color:${awayColor}">${awayName}</div>
                <div class="gor-pts">${g.away_score ?? '—'}</div>
                <div class="gor-venue">AWAY</div>
            </div>
        </div>
        <div class="gor-tags">${tagsHtml}</div>
        ${replayLink}
    </div>`;
}

/* ── 3. Scatter Plot ───────────────────────────────────────────────────── */
function renderScatter() {
    const teams = _gc.teams;
    const codes = Object.keys(teams);
    const x = codes.map(c => teams[c].gci);
    const y = codes.map(c => teams[c].drama_avg);
    const colors = codes.map(c => teamInk(c));
    const names = codes.map(c => TEAM_NAMES[c] || c);

    const trace = {
        x, y,
        mode: 'markers+text',
        type: 'scatter',
        text: names,
        textposition: 'top center',
        textfont: { size: 9, color: '#9ca3af' },
        marker: { size: 12, color: colors, line: { width: 1, color: '#1a1b26' } },
        customdata: codes,
        hovertemplate: '%{text}<br>GCI: %{x:.1f}<br>Drama: %{y:.1f}<extra></extra>',
    };

    const xMid = (Math.min(...x) + Math.max(...x)) / 2;
    const yMid = (Math.min(...y) + Math.max(...y)) / 2;

    const layout = Object.assign({}, PLOTLY_THEME, {
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, { title: 'GCI Rating' }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, { title: 'Drama Index' }),
        margin: { t: 20, r: 20, b: 50, l: 55 },
        annotations: [
            { x: Math.max(...x) * 0.95, y: Math.max(...y) * 0.95, text: 'High Control<br>High Drama', showarrow: false, font: { size: 9, color: '#6b7280' } },
            { x: Math.min(...x) * 1.05 || xMid * 0.5, y: Math.max(...y) * 0.95, text: 'Low Control<br>High Drama', showarrow: false, font: { size: 9, color: '#6b7280' } },
            { x: Math.max(...x) * 0.95, y: Math.min(...y) * 1.05 || yMid * 0.5, text: 'High Control<br>Low Drama', showarrow: false, font: { size: 9, color: '#6b7280' } },
            { x: Math.min(...x) * 1.05 || xMid * 0.5, y: Math.min(...y) * 1.05 || yMid * 0.5, text: 'Low Control<br>Low Drama', showarrow: false, font: { size: 9, color: '#6b7280' } },
        ],
    });

    Plotly.newPlot('scatter-plot', [trace], layout, PLOTLY_CONFIG);

    // Click handler
    document.getElementById('scatter-plot').on('plotly_click', ev => {
        if (ev.points && ev.points.length) {
            selectTeam(ev.points[0].customdata);
        }
    });
}

/* ── 4. Leaderboard ────────────────────────────────────────────────────── */
function renderLeaderboard() {
    const table = document.getElementById('leaderboard');
    const teams = _gc.teams;
    const codes = Object.keys(teams);

    // Sort
    codes.sort((a, b) => {
        const va = teams[a][_sortCol] ?? 0;
        const vb = teams[b][_sortCol] ?? 0;
        return _sortAsc ? va - vb : vb - va;
    });

    // Header
    const thCells = ['#', 'Team'].concat(COLS.map(c => {
        let cls = '';
        if (c.key === _sortCol) cls = _sortAsc ? 'sorted-asc' : 'sorted-desc';
        return `<th class="${cls}" onclick="sortLeaderboard('${c.key}')">${c.label}</th>`;
    }));
    table.querySelector('thead').innerHTML = '<tr>' + thCells.map((h, i) =>
        i < 2 ? `<th>${h}</th>` : h
    ).join('') + '</tr>';

    // Body
    table.querySelector('tbody').innerHTML = codes.map((code, i) => {
        const t = teams[code];
        const name = TEAM_NAMES[code] || code;
        const color = teamInk(code);
        const sel = code === _selectedTeam ? ' selected' : '';
        const cells = COLS.map(c => `<td>${c.fmt(t[c.key] ?? 0)}</td>`).join('');
        return `<tr class="${sel}" onclick="selectTeam('${code}')">
            <td>${i + 1}</td>
            <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px;vertical-align:middle;"></span>${name}</td>
            ${cells}
        </tr>`;
    }).join('');
}

function sortLeaderboard(col) {
    if (_sortCol === col) {
        _sortAsc = !_sortAsc;
    } else {
        _sortCol = col;
        _sortAsc = false;
    }
    renderLeaderboard();
}

/* ── 5. Team Grid ──────────────────────────────────────────────────────── */
function renderTeamGrid() {
    const grid = document.getElementById('team-grid');
    const codes = Object.keys(_gc.teams).sort((a, b) => {
        const na = TEAM_NAMES[a] || a;
        const nb = TEAM_NAMES[b] || b;
        return na.localeCompare(nb);
    });
    grid.innerHTML = codes.map(code => {
        const name = TEAM_NAMES[code] || code;
        const color = teamInk(code);
        const sel = code === _selectedTeam ? ' selected' : '';
        return `<div class="team-chip${sel}" id="chip-${code}" onclick="selectTeam('${code}')">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:4px;vertical-align:middle;"></span>
            <span class="team-chip-name">${name}</span>
        </div>`;
    }).join('');
}

/* ── 6. Select Team ────────────────────────────────────────────────────── */
function selectTeam(code) {
    if (!_gc.teams[code]) return;
    _selectedTeam = code;

    // Update URL
    const url = new URL(window.location);
    url.searchParams.set('team', code);
    history.replaceState(null, '', url);

    // Highlight chips
    document.querySelectorAll('.team-chip').forEach(el => {
        el.classList.toggle('selected', el.id === `chip-${code}`);
    });

    // Re-render leaderboard to update highlight
    renderLeaderboard();

    // Render detail
    renderTeamDetail(code);

    // Scroll to deep-dive section
    const section = document.getElementById('team-section');
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ── 7. Team Detail ────────────────────────────────────────────────────── */
function renderTeamDetail(code) {
    const wrap = document.getElementById('team-detail');
    const t = _gc.teams[code];
    if (!t) { wrap.innerHTML = ''; return; }

    const name = TEAM_NAMES[code] || code;
    const color = teamInk(code);

    // Radar data: normalize each metric 0-1 across league
    const radarMetrics = [
        { key: 'dominance_avg', label: 'Dominance' },
        { key: 'control_pct',   label: 'Control' },
        { key: 'crunch_swing_avg', label: 'Crunch' },
        { key: 'killer_instinct',  label: 'Killer' },
        { key: 'drama_avg',     label: 'Drama' },
        { key: 'comeback_rating', label: 'Comeback' },
    ];

    const allTeams = Object.values(_gc.teams);
    const normalized = radarMetrics.map(m => {
        const vals = allTeams.map(x => x[m.key] ?? 0);
        const min = Math.min(...vals);
        const max = Math.max(...vals);
        const range = max - min || 1;
        return { label: m.label, value: (t[m.key] - min) / range };
    });

    const radarSvg = buildRadarSVG(normalized, color);

    // Game log (last 10)
    const gameLog = (t.game_log || []).slice(-10).reverse();
    const logRows = gameLog.map(g => {
        const opp = TEAM_NAMES[g.opponent] || g.opponent;
        const oppColor = teamInk(g.opponent);
        const result = g.is_win ? 'W' : 'L';
        const resultColor = g.is_win ? '#4ecdc4' : '#f87171';
        const prefix = g.is_home ? 'vs' : '@';
        const score = g.is_home ? `${g.home_score}-${g.away_score}` : `${g.away_score}-${g.home_score}`;
        return `<div class="game-log-row">
            <span style="color:var(--text-muted)">${prefix} <span style="color:${oppColor};font-weight:600">${opp}</span></span>
            <span><span style="color:${resultColor};font-weight:600">${result}</span> ${score} · <span style="color:var(--text-muted)">${g.dominance.toFixed(2)}</span></span>
        </div>`;
    }).join('');

    // Home vs Away GCI bar (both are 0-100 scores)
    const homeGci = t.home_gci ?? 50;
    const awayGci = t.away_gci ?? 50;
    const gciTotal = homeGci + awayGci || 1;
    const homePct = Math.max(5, Math.min(95, (homeGci / gciTotal * 100))).toFixed(0);
    const awayPct = (100 - homePct);

    wrap.innerHTML = `
        <h3 style="font-family:'Outfit',sans-serif;font-weight:800;color:${color};margin-bottom:0.75rem;">${name}</h3>
        <div class="deep-dive-grid">
            <div class="dd-panel">
                <div class="dd-panel-title">Profile Radar</div>
                ${radarSvg}
            </div>
            <div class="dd-panel">
                <div class="dd-panel-title">Win/Loss Quality</div>
                <div id="dd-histogram"></div>
            </div>
            <div class="dd-panel">
                <div class="dd-panel-title">Recent Games</div>
                ${logRows || '<p style="color:var(--text-muted);font-size:0.75rem;">No game log.</p>'}
            </div>
        </div>
        <div class="dd-panel" style="max-width:400px;">
            <div class="dd-panel-title">Home vs Away GCI</div>
            <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--text-secondary);margin-bottom:0.25rem;">
                <span>Home: ${homeGci.toFixed(1)}</span>
                <span>Away: ${awayGci.toFixed(1)}</span>
            </div>
            <div class="home-away-bar">
                <div style="width:${homePct}%;background:${color};"></div>
                <div style="width:${awayPct}%;background:#6b7280;"></div>
            </div>
        </div>
    `;

    // Render histogram with Plotly
    renderWinLossHistogram(t);
}

function renderWinLossHistogram(t) {
    const winHist = t.win_quality_hist || [0, 0, 0, 0, 0];
    const lossHist = t.loss_quality_hist || [0, 0, 0, 0, 0];
    const labels = ['Grind', 'Close', 'Solid', 'Comfort', 'Blowout'];

    const traceWin = {
        x: labels,
        y: winHist,
        type: 'bar',
        name: 'Wins',
        marker: { color: '#4ecdc4' },
        hovertemplate: '%{x}: %{y} wins<extra></extra>',
    };

    const traceLoss = {
        x: labels,
        y: lossHist.map(v => -v),
        type: 'bar',
        name: 'Losses',
        marker: { color: '#f87171' },
        hovertemplate: '%{x}: %{y} losses<extra></extra>',
    };

    const layout = Object.assign({}, PLOTLY_THEME, {
        barmode: 'relative',
        margin: { t: 10, r: 10, b: 35, l: 30 },
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, { tickfont: { size: 9 } }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, { title: '' }),
        showlegend: false,
        height: 200,
    });

    Plotly.newPlot('dd-histogram', [traceWin, traceLoss], layout, PLOTLY_CONFIG);
}

/* ── 8. Radar SVG ──────────────────────────────────────────────────────── */
function buildRadarSVG(data, color) {
    const cx = 100, cy = 100, r = 70;
    const n = data.length;
    const angleStep = (2 * Math.PI) / n;
    const startAngle = -Math.PI / 2; // top

    // Helper: polar to cartesian
    function polar(angle, radius) {
        return {
            x: cx + radius * Math.cos(angle),
            y: cy + radius * Math.sin(angle),
        };
    }

    // Grid rings
    let rings = '';
    [0.25, 0.5, 0.75, 1.0].forEach(frac => {
        const rr = r * frac;
        const pts = [];
        for (let i = 0; i < n; i++) {
            const a = startAngle + i * angleStep;
            const p = polar(a, rr);
            pts.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
        }
        rings += `<polygon points="${pts.join(' ')}" fill="none" stroke="#2d2e3a" stroke-width="0.5"/>`;
    });

    // Axis lines
    let axes = '';
    for (let i = 0; i < n; i++) {
        const a = startAngle + i * angleStep;
        const p = polar(a, r);
        axes += `<line x1="${cx}" y1="${cy}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}" stroke="#2d2e3a" stroke-width="0.5"/>`;
    }

    // Data polygon
    const dataPts = data.map((d, i) => {
        const a = startAngle + i * angleStep;
        const p = polar(a, r * Math.max(d.value, 0.05));
        return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    }).join(' ');

    // Labels
    let labels = '';
    data.forEach((d, i) => {
        const a = startAngle + i * angleStep;
        const p = polar(a, r + 16);
        let anchor = 'middle';
        if (p.x < cx - 5) anchor = 'end';
        else if (p.x > cx + 5) anchor = 'start';
        labels += `<text x="${p.x.toFixed(1)}" y="${p.y.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle"
            fill="#9ca3af" font-size="8" font-family="Inter, sans-serif">${d.label}</text>`;
    });

    return `<svg viewBox="0 0 200 200" style="width:100%;max-width:220px;height:auto;display:block;margin:0 auto;">
        ${rings}
        ${axes}
        <polygon points="${dataPts}" fill="${color}33" stroke="${color}" stroke-width="1.5"/>
        ${labels}
    </svg>`;
}

/* ── 9. Superlatives ───────────────────────────────────────────────────── */
function renderSuperlatives() {
    const wrap = document.getElementById('superlatives');
    const s = _gc.superlatives;
    if (!s) {
        wrap.innerHTML = '<p style="color:var(--text-muted)">No superlatives available.</p>';
        return;
    }

    const cards = [
        { icon: '\u2605', label: 'Most Dominant Game', data: s.most_dominant, color: '#4ecdc4',
          metric: d => `Dominance: ${Math.abs(d.dominance).toFixed(2)}` },
        { icon: '\u26A1', label: 'Most Dramatic Game', data: s.most_dramatic, color: '#ff6b6b',
          metric: d => `Drama: ${d.drama.toFixed(2)}` },
        { icon: '\u21BB', label: 'Biggest Comeback', data: s.biggest_comeback, color: '#ffd700',
          metric: d => `From ${((1 - d.comeback) * 100).toFixed(0)}% WP` },
    ];

    wrap.innerHTML = cards.map(c => {
        if (!c.data) return '';
        const score = (c.data.home_score != null && c.data.away_score != null)
            ? `${c.data.home_score} - ${c.data.away_score}`
            : '';
        return `<div class="superlative-card">
            <div class="superlative-icon" style="color:${c.color}">${c.icon}</div>
            <div class="superlative-label">${c.label}</div>
            <div class="superlative-matchup">${TEAM_NAMES[c.data.home] || c.data.home} ${score} ${TEAM_NAMES[c.data.away] || c.data.away}</div>
            <div style="color:${c.color};font-size:0.8rem;">${c.metric(c.data)}</div>
        </div>`;
    }).join('');
}
