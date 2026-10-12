/**
 * mvp.js — MVP Race Tracker
 */
'use strict';

// MVP component config: key → { label, color, weight }
const COMPONENTS = [
    { key: 'pir',         label: 'PIR',        color: '#3b82f6', weight: 0.45 },
    { key: 'wpa',         label: 'WPA',        color: '#22c55e', weight: 0.25 },
    { key: 'team_win',    label: 'Team Win%',   color: '#f59e0b', weight: 0.15 },
    { key: 'clutch',      label: 'Clutch',      color: '#ef4444', weight: 0.10 },
    { key: 'consistency', label: 'Consistency',  color: '#a855f7', weight: 0.05 },
];

let _mvpData = [];
let _raceData = [];
let _round = 0;
let _selectedIdx = null;
let _mvpSort = { key: 'mvp_score', dir: 'desc' };

async function init() {
    try {
        const resp = await fetch('data/current/dashboard.json');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        _mvpData = data.mvp || [];
        _raceData = data.mvp_race || [];
        _round = data.round || 0;

        if (data.updated) {
            const el = document.getElementById('last-updated');
            if (el) {
                const d = new Date(data.updated);
                el.textContent = `Data as of Round ${data.round || ''} · Updated ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;
                el.style.display = '';
            }
        }

        renderLadder();
        renderLegend();
        renderRaceChart();
    } catch (err) {
        document.getElementById('mvp-tbody').innerHTML =
            `<tr><td colspan="7" style="color:var(--accent-red);padding:1rem">Failed to load data: ${err}</td></tr>`;
    }
}

// ── Compute component percentiles for breakdown bars ─────────────────────
function computePercentiles() {
    // For each raw field, compute rank-based percentiles across the 15 candidates
    const fields = ['avg_pir', 'wpa', 'team_win_pct', 'clutch_eff', 'consistency'];
    const pctls = _mvpData.map(() => ({}));

    for (const f of fields) {
        const vals = _mvpData.map(m => m[f] || 0);
        const sorted = [...vals].sort((a, b) => a - b);
        for (let i = 0; i < vals.length; i++) {
            const rank = sorted.indexOf(vals[i]);
            pctls[i][f] = ((rank + 1) / sorted.length);
        }
    }
    return pctls;
}

// ── Render MVP ladder ────────────────────────────────────────────────────
const MVP_COLS = [
    { key: null, label: '#' },
    { key: 'player', label: 'Player' },
    { key: null, label: 'Team' },
    { key: 'mvp_score', label: 'Score', cls: 'num' },
    { key: null, label: 'Breakdown' },
    { key: 'avg_pir', label: 'PIR', cls: 'num' },
    { key: 'gp', label: 'GP', cls: 'num' },
];

function renderLadder() {
    if (!_mvpData.length) {
        document.querySelector('#mvp-table thead').innerHTML = '';
        document.getElementById('mvp-tbody').innerHTML =
            `<tr><td colspan="${MVP_COLS.length}">${mvpPendingHTML(_round)}</td></tr>`;
        return;
    }
    const pctls = computePercentiles();
    const pctlMap = {
        pir: 'avg_pir', wpa: 'wpa', team_win: 'team_win_pct',
        clutch: 'clutch_eff', consistency: 'consistency',
    };

    // Sort data (keep original indices for percentiles)
    const indexed = _mvpData.map((m, i) => ({ m, i }));
    indexed.sort((a, b) => {
        let va = a.m[_mvpSort.key], vb = b.m[_mvpSort.key];
        if (typeof va === 'string') { va = va.toLowerCase(); vb = vb.toLowerCase(); }
        return _mvpSort.dir === 'desc' ? (vb > va ? 1 : vb < va ? -1 : 0) : (va > vb ? 1 : va < vb ? -1 : 0);
    });

    // Build sortable header
    let thead = '<tr>';
    for (const col of MVP_COLS) {
        const active = col.key && _mvpSort.key === col.key;
        const arrow = active ? (_mvpSort.dir === 'desc' ? ' ▼' : ' ▲') : '';
        const cls = [col.cls || '', active ? 'sort-active' : '', col.key ? 'sortable-th' : ''].filter(Boolean).join(' ');
        const onclick = col.key ? ` onclick="sortMvp('${col.key}')" style="cursor:pointer"` : '';
        thead += `<th class="${cls}"${onclick}>${col.label}${arrow}</th>`;
    }
    thead += '</tr>';
    document.querySelector('#mvp-table thead').innerHTML = thead;

    // Build rows
    let html = '';
    for (const { m, i } of indexed) {
        const color = TEAM_COLORS[m.team] || '#555';
        const rankCls = m.rank === 1 ? 'top1' : m.rank <= 3 ? 'top3' : '';

        let barHtml = '';
        for (const comp of COMPONENTS) {
            const pctl = pctls[i][pctlMap[comp.key]] || 0;
            const w = pctl * comp.weight * 100;
            barHtml += `<div class="mvp-bar-seg" style="width:${w}%;background:${comp.color}" title="${comp.label}: ${(pctl * 100).toFixed(0)}th pctl"></div>`;
        }

        html += `<tr onclick="selectPlayer(${i})" class="${_selectedIdx === i ? 'selected' : ''}">
            <td class="mvp-rank-cell ${rankCls}">${m.rank}</td>
            <td class="mvp-player-cell">${formatName(m.player)}</td>
            <td><span class="mvp-team-badge" style="background:${teamInk(m.team)}"></span>${m.team}</td>
            <td class="num mvp-score-cell">${m.mvp_score.toFixed(1)}</td>
            <td><div class="mvp-bar-wrap"><div class="mvp-bar-track">${barHtml}</div></div></td>
            <td class="num">${m.avg_pir.toFixed(1)}</td>
            <td class="num">${m.gp}</td>
        </tr>`;
    }
    document.getElementById('mvp-tbody').innerHTML = html;
}

function sortMvp(key) {
    if (_mvpSort.key === key) {
        _mvpSort.dir = _mvpSort.dir === 'desc' ? 'asc' : 'desc';
    } else {
        _mvpSort.key = key;
        _mvpSort.dir = 'desc';
    }
    renderLadder();
}

function renderLegend() {
    const el = document.getElementById('mvp-legend');
    if (!_mvpData.length) { el.style.display = 'none'; return; }
    el.innerHTML = COMPONENTS.map(c =>
        `<div class="mvp-legend-item">
            <div class="mvp-legend-swatch" style="background:${c.color}"></div>
            ${c.label} (${(c.weight * 100).toFixed(0)}%)
        </div>`
    ).join('');
}

// ── Player detail card ───────────────────────────────────────────────────
function selectPlayer(idx) {
    _selectedIdx = _selectedIdx === idx ? null : idx;
    renderLadder();

    const detail = document.getElementById('mvp-detail');
    if (_selectedIdx === null) {
        detail.classList.remove('visible');
        return;
    }

    const m = _mvpData[_selectedIdx];
    const color = teamInk(m.team);
    const pctls = computePercentiles();
    const p = pctls[_selectedIdx];

    const pctlMap = {
        pir: 'avg_pir',
        wpa: 'wpa',
        team_win: 'team_win_pct',
        clutch: 'clutch_eff',
        consistency: 'consistency',
    };

    // Raw values for display
    const rawVals = {
        pir: m.avg_pir.toFixed(1),
        wpa: m.wpa.toFixed(0),
        team_win: m.team_win_pct.toFixed(0) + '%',
        clutch: m.clutch_eff.toFixed(3),
        consistency: m.consistency.toFixed(3),
    };

    let barsHtml = '';
    for (const comp of COMPONENTS) {
        const pctl = p[pctlMap[comp.key]] || 0;
        const pctW = (pctl * 100).toFixed(0);
        barsHtml += `<div class="comp-row">
            <div class="comp-label">${comp.label}</div>
            <div class="comp-bar-track">
                <div class="comp-bar-fill" style="width:${pctW}%;background:${comp.color}"></div>
            </div>
            <div class="comp-val">${rawVals[comp.key]}</div>
        </div>`;
    }

    // Build SVG radar chart
    const radarSvg = buildRadar(p, pctlMap, color);

    detail.innerHTML = `
        <div class="mvp-detail-header">
            <div>
                <div class="mvp-detail-name" style="color:${color}">#${m.rank} ${formatName(m.player)}</div>
                <div class="mvp-detail-sub">${TEAM_NAMES[m.team] || m.team} · ${m.gp} GP · MVP Score: ${m.mvp_score.toFixed(1)}</div>
            </div>
        </div>
        <div class="mvp-detail-grid">
            <div>
                <h4 style="font-size:0.82rem;margin:0 0 0.5rem;color:var(--text-muted)">Component Percentiles</h4>
                ${barsHtml}
            </div>
            <div style="display:flex;align-items:center;justify-content:center">
                ${radarSvg}
            </div>
        </div>
    `;
    detail.classList.add('visible');
}

// ── SVG Radar chart ──────────────────────────────────────────────────────
function buildRadar(pctls, pctlMap, color) {
    const size = 240;
    const cx = size / 2, cy = size / 2;
    const r = 90;
    const axes = COMPONENTS;
    const n = axes.length;

    function polar(i, val) {
        const angle = (2 * Math.PI * i / n) - Math.PI / 2;
        return {
            x: cx + r * val * Math.cos(angle),
            y: cy + r * val * Math.sin(angle),
        };
    }

    // Grid rings
    let gridHtml = '';
    for (const ring of [0.25, 0.5, 0.75, 1.0]) {
        const pts = [];
        for (let i = 0; i < n; i++) {
            const p = polar(i, ring);
            pts.push(`${p.x},${p.y}`);
        }
        gridHtml += `<polygon points="${pts.join(' ')}" fill="none" stroke="#2a2a3a" stroke-width="0.8"/>`;
    }

    // Axis lines + labels
    let axesHtml = '';
    for (let i = 0; i < n; i++) {
        const p = polar(i, 1.0);
        axesHtml += `<line x1="${cx}" y1="${cy}" x2="${p.x}" y2="${p.y}" stroke="#2a2a3a" stroke-width="0.8"/>`;
        const lp = polar(i, 1.22);
        axesHtml += `<text x="${lp.x}" y="${lp.y}" text-anchor="middle" dominant-baseline="central" fill="#888" font-size="10" font-weight="600">${axes[i].label}</text>`;
    }

    // Data polygon
    const dataPts = [];
    for (let i = 0; i < n; i++) {
        const val = pctls[pctlMap[axes[i].key]] || 0;
        const p = polar(i, val);
        dataPts.push(`${p.x},${p.y}`);
    }
    const dataHtml = `<polygon points="${dataPts.join(' ')}" fill="${color}" fill-opacity="0.15" stroke="${color}" stroke-width="2"/>`;

    // Data points
    let dotsHtml = '';
    for (let i = 0; i < n; i++) {
        const val = pctls[pctlMap[axes[i].key]] || 0;
        const p = polar(i, val);
        dotsHtml += `<circle cx="${p.x}" cy="${p.y}" r="4" fill="${color}" stroke="#0f1117" stroke-width="1.5"/>`;
    }

    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="max-width:100%">
        ${gridHtml}${axesHtml}${dataHtml}${dotsHtml}
    </svg>`;
}

// ── Race Timeline chart (Plotly) ─────────────────────────────────────────
function renderRaceChart() {
    const container = document.getElementById('race-chart');
    if (!_raceData.length) {
        if (_mvpData.length) {
            container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:2rem">No historical snapshots available.</p>';
        } else {
            container.style.height = 'auto';
            container.innerHTML = mvpPendingHTML(_round);
        }
        return;
    }

    // Group by player
    const byPlayer = {};
    for (const r of _raceData) {
        if (!byPlayer[r.player]) byPlayer[r.player] = { team: r.team, rounds: [], scores: [] };
        byPlayer[r.player].rounds.push(r.round);
        byPlayer[r.player].scores.push(r.score);
    }

    const traces = [];
    // Sort players by their latest score descending
    const players = Object.entries(byPlayer).sort((a, b) => {
        const aLast = a[1].scores[a[1].scores.length - 1];
        const bLast = b[1].scores[b[1].scores.length - 1];
        return bLast - aLast;
    });

    for (const [name, data] of players) {
        const color = teamInk(data.team);
        traces.push({
            x: data.rounds.map(r => `R${r}`),
            y: data.scores,
            name: formatName(name),
            mode: 'lines+markers',
            line: { color, width: 2.5, shape: 'spline' },
            marker: { size: 6, color },
            hovertemplate: `<b>${formatName(name)}</b><br>Round %{x}<br>Score: %{y:.1f}<extra></extra>`,
        });
    }

    const layout = {
        ...PLOTLY_THEME,
        margin: { t: 20, r: 20, b: 50, l: 50 },
        xaxis: { ...PLOTLY_THEME.xaxis, title: 'Round' },
        yaxis: { ...PLOTLY_THEME.yaxis, title: 'MVP Score' },
        legend: {
            orientation: 'h',
            y: -0.18,
            x: 0.5,
            xanchor: 'center',
            font: { size: 11 },
        },
        hovermode: 'closest',
    };

    Plotly.newPlot(container, traces, layout, PLOTLY_CONFIG);
}

// ── Utility ──────────────────────────────────────────────────────────────
function formatName(allCaps) {
    // "VEZENKOV, SASHA" → "S. Vezenkov"
    const parts = allCaps.split(', ');
    if (parts.length < 2) return allCaps;
    const last = parts[0].charAt(0) + parts[0].slice(1).toLowerCase();
    const first = parts[1].charAt(0) + '.';
    return `${first} ${last}`;
}

document.addEventListener('DOMContentLoaded', init);
