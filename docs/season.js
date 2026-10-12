/**
 * season.js — Euroleague Season Hub
 * Renders standings, power scatter, MVP race, playoff grid,
 * oracle predictions, player forecasts, and accuracy stats.
 */

'use strict';

let _seasonRound = 0;

// ── Sort state ────────────────────────────────────────────────────────────
let sortState = { col: 'wins', asc: false };

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
    try {
        const resp = await fetch('data/current/dashboard.json');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        renderStandings(data.teams || []);
        renderPowerScatter(data.teams || []);
        _seasonRound = data.round || 0;
        renderMVPRace(data.mvp || []);
        renderScheduleDifficulty(data.teams || []);
        renderStandingsTimeline(data.teams || []);
        renderOracleHeader(data);
        renderOracleCards(data.oracle);
        renderPlayerForecasts(
            (data.oracle && data.oracle.player_forecasts) ? data.oracle.player_forecasts : [],
            data.teams || []
        );
        renderAccuracyStats(data.accuracy);

        // Last updated stamp
        if (data.updated) {
            const el = document.getElementById('last-updated');
            if (el) {
                const d = new Date(data.updated);
                el.textContent = `Data as of Round ${data.round} · Updated ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;
                el.style.display = '';
            }
        }

        // Restore tab from URL hash
        const hash = location.hash.replace('#', '');
        if (hash === 'tab-oracle' || hash === 'tab-standings') {
            switchTab(hash, SEASON_TABS, SEASON_TAB_OPTS);
        }

    } catch (err) {
        console.error('Dashboard load error:', err);
        document.getElementById('load-error').classList.remove('hidden');
        // Hide loading placeholders
        document.querySelectorAll('.loading-placeholder').forEach(el => {
            el.textContent = 'Failed to load data.';
        });
    }
}

// ── Tab config ────────────────────────────────────────────────────────────
const SEASON_TABS = ['tab-standings', 'tab-oracle'];
const SEASON_TAB_OPTS = {
    onSwitch(tabId) {
        if (tabId === 'tab-oracle') {
            setTimeout(() => {
                const calibEl = document.getElementById('calibration-chart');
                if (calibEl && calibEl._plotly) Plotly.Plots.resize(calibEl);
            }, 50);
        }
    }
};

// ── Standings table ───────────────────────────────────────────────────────
function renderStandings(teams) {
    const container = document.getElementById('standings-table');
    if (!teams.length) {
        container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:1rem;">No standings data available.</p>';
        return;
    }

    // First render only: default to the official standings order when the export provides it
    if (!renderStandings._init) {
        renderStandings._init = true;
        if (teams.every(t => typeof t.position === 'number')) sortState = { col: 'position', asc: true };
    }

    const PLAYOFF_CUTOFFS = { 4: 'cutoff-top4', 6: 'cutoff-top6', 10: 'cutoff-top10' };

    const cols = [
        { key: '#',        label: '#',        sortKey: null,       align: 'center' },
        { key: 'name',     label: 'Team',     sortKey: 'name',     align: 'left' },
        { key: 'wl',       label: 'W-L',      sortKey: 'wins',     align: 'center' },
        { key: 'last5',    label: 'Last 5',   sortKey: null,       align: 'center' },
        { key: 'elo',      label: 'Elo',      sortKey: 'elo',      align: 'right' },
        { key: 'adj_net',  label: 'Adj Net',  sortKey: 'adj_net',  align: 'right' },
        { key: 'adj_off',  label: 'Adj Off',  sortKey: 'adj_off',  align: 'right' },
        { key: 'adj_def',  label: 'Adj Def',  sortKey: 'adj_def',  align: 'right' },
        { key: 'avg_wins', label: 'xWins',    sortKey: 'avg_wins', align: 'right' },
        { key: 'top4_pct', label: 'Top 4%',   sortKey: 'top4_pct', align: 'right' },
        { key: 'top6_pct', label: 'Top 6%',   sortKey: 'top6_pct', align: 'right' },
        { key: 'top10_pct',label: 'Top 10%',  sortKey: 'top10_pct',align: 'right' },
    ];

    function buildTable(sorted) {
        let html = '<div class="standings-table-wrap"><table class="standings-tbl"><thead><tr>';
        cols.forEach(c => {
            const sortable = c.sortKey ? 'sortable' : '';
            const active = sortState.col === c.sortKey ? 'sort-active' : '';
            const arrow = sortState.col === c.sortKey ? (sortState.asc ? ' ▲' : ' ▼') : '';
            const onclick = c.sortKey ? `onclick="sortStandings('${c.sortKey}')"` : '';
            html += `<th class="${sortable} ${active}" ${onclick} style="text-align:${c.align}">${c.label}${arrow}</th>`;
        });
        html += '</tr></thead><tbody>';

        sorted.forEach((t, i) => {
            const rank = i + 1;
            const badgeColor = TEAM_COLORS[t.team] || '#555';
            const badge = `<span class="team-badge" style="background:${badgeColor};color:${teamOnColor(t.team)}">${t.team.substring(0,3)}</span>`;
            const netColor = t.adj_net >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            const netStr = (t.adj_net >= 0 ? '+' : '') + t.adj_net.toFixed(2);

            // Last 5 form dots
            const last5 = (t.last5 || []);
            const formDots = last5.map(r =>
                `<span class="form-dot form-${r === 'W' ? 'w' : 'l'}">${r}</span>`
            ).join('');

            // Cutoff divider row — insert BEFORE rank 5, 7, 11
            let divider = '';
            if (PLAYOFF_CUTOFFS[rank - 1]) {
                const label = rank - 1 === 4 ? 'Top 4 cutoff' : rank - 1 === 6 ? 'Playoff cutoff (Top 6)' : 'Play-in cutoff (Top 10)';
                const colorMap = { 'cutoff-top4': '#a855f7', 'cutoff-top6': '#22c55e', 'cutoff-top10': '#3b82f6' };
                const col = colorMap[PLAYOFF_CUTOFFS[rank - 1]];
                divider = `<tr class="cutoff-row ${PLAYOFF_CUTOFFS[rank - 1]}">
                    <td colspan="${cols.length}" style="border-top:2px solid ${col}40;padding:0">
                        <span class="cutoff-label" style="color:${col}">${label}</span>
                    </td>
                </tr>`;
            }

            html += divider + `<tr>
                <td style="text-align:center;color:var(--text-muted);font-size:0.8rem">${rank}</td>
                <td style="text-align:left">${badge} <span style="font-weight:600">${t.name}</span></td>
                <td style="text-align:center;font-weight:700">${t.wins}-${t.losses}</td>
                <td style="text-align:center"><div class="form-dots">${formDots}</div></td>
                <td style="text-align:right">${t.elo.toFixed(0)}</td>
                <td style="text-align:right;color:${netColor};font-weight:700">${netStr}</td>
                <td style="text-align:right">${t.adj_off.toFixed(1)}</td>
                <td style="text-align:right">${t.adj_def.toFixed(1)}</td>
                <td style="text-align:right">${t.avg_wins.toFixed(1)}</td>
                <td style="text-align:right">${pctCell(t.top4_pct, '#a855f7')}</td>
                <td style="text-align:right">${pctCell(t.top6_pct, '#22c55e')}</td>
                <td style="text-align:right">${pctCell(t.top10_pct, '#3b82f6')}</td>
            </tr>`;
        });

        html += '</tbody></table></div>';
        return html;
    }

    function pctCell(val, color) {
        const opacity = Math.min(val / 100, 1) * 0.6;
        const bg = hexToRgba(color, opacity);
        const textColor = opacity > 0.3 ? '#fff' : 'var(--text-primary)';
        return `<span class="pct-cell" style="background:${bg};color:${textColor}">${val.toFixed(1)}%</span>`;
    }

    function getSorted() {
        return [...teams].sort((a, b) => {
            let va = a[sortState.col], vb = b[sortState.col];
            if (typeof va === 'string') va = va.toLowerCase();
            if (typeof vb === 'string') vb = vb.toLowerCase();
            if (va < vb) return sortState.asc ? -1 : 1;
            if (va > vb) return sortState.asc ? 1 : -1;
            return 0;
        });
    }

    window.sortStandings = function (col) {
        if (sortState.col === col) {
            sortState.asc = !sortState.asc;
        } else {
            sortState.col = col;
            sortState.asc = false;
        }
        container.innerHTML = buildTable(getSorted());
    };

    container.innerHTML = buildTable(getSorted());
}

// ── Power Scatter ─────────────────────────────────────────────────────────
function renderPowerScatter(teams) {
    if (!teams.length) return;

    const meanOff = teams.reduce((s, t) => s + t.adj_off, 0) / teams.length;
    const meanDef = teams.reduce((s, t) => s + t.adj_def, 0) / teams.length;

    const x = teams.map(t => t.adj_off);
    const y = teams.map(t => t.adj_def);
    const text = teams.map(t => t.team);
    const colors = teams.map(t => t.adj_net);
    const hoverText = teams.map(t =>
        `<b>${t.name} (${t.team})</b><br>Adj Off: ${t.adj_off.toFixed(1)}<br>Adj Def: ${t.adj_def.toFixed(1)}<br>Adj Net: ${t.adj_net >= 0 ? '+' : ''}${t.adj_net.toFixed(2)}`
    );

    const xMin = Math.min(...x) - 2, xMax = Math.max(...x) + 2;
    const yMin = Math.min(...y) - 2, yMax = Math.max(...y) + 2;

    // Quadrant label positions
    const quadrants = [
        { x: xMax - 0.5, y: yMin + 0.5, text: 'Elite', xanchor: 'right', yanchor: 'bottom' },
        { x: xMin + 0.5, y: yMin + 0.5, text: 'Offensive', xanchor: 'left', yanchor: 'bottom' },
        { x: xMax - 0.5, y: yMax - 0.5, text: 'Defensive', xanchor: 'right', yanchor: 'top' },
        { x: xMin + 0.5, y: yMax - 0.5, text: 'Weak', xanchor: 'left', yanchor: 'top' },
    ];

    const annotations = quadrants.map(q => ({
        x: q.x, y: q.y,
        text: q.text,
        xanchor: q.xanchor,
        yanchor: q.yanchor,
        showarrow: false,
        font: { color: 'rgba(156,163,175,0.35)', size: 13, family: 'Outfit' },
    }));

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: '#0f1117',
        font: { color: '#9ca3af', family: 'Inter' },
        margin: { t: 10, b: 50, l: 55, r: 10 },
        xaxis: {
            title: 'Adj. Offensive Rating',
            gridcolor: '#2d2e3a',
            zerolinecolor: '#2d2e3a',
            tickfont: { size: 11 },
        },
        yaxis: {
            title: 'Adj. Defensive Rating',
            autorange: 'reversed',
            gridcolor: '#2d2e3a',
            zerolinecolor: '#2d2e3a',
            tickfont: { size: 11 },
        },
        shapes: [
            // Vertical mean line
            { type: 'line', x0: meanOff, x1: meanOff, y0: yMin, y1: yMax,
              line: { color: 'rgba(156,163,175,0.3)', width: 1, dash: 'dot' } },
            // Horizontal mean line
            { type: 'line', x0: xMin, x1: xMax, y0: meanDef, y1: meanDef,
              line: { color: 'rgba(156,163,175,0.3)', width: 1, dash: 'dot' } },
        ],
        annotations,
        showlegend: false,
        coloraxis: { showscale: false },
        hovermode: 'closest',
    };

    const trace = {
        type: 'scatter',
        mode: 'markers',
        x, y,
        text,
        hovertext: hoverText,
        hoverinfo: 'text',
        textposition: 'top center',
        textfont: { color: '#f0f0f5', size: 10, family: 'Inter' },
        marker: {
            size: 14,
            color: colors,
            colorscale: [
                [0, '#ef4444'],
                [0.5, '#f59e0b'],
                [1, '#22c55e'],
            ],
            cmin: Math.min(...colors),
            cmax: Math.max(...colors),
            line: { color: '#1f2029', width: 1.5 },
        },
    };

    Plotly.newPlot('power-scatter', [trace], layout, { displayModeBar: false, responsive: true });
}

let _scatterLabelsOn = false;
function toggleScatterLabels() {
    _scatterLabelsOn = !_scatterLabelsOn;
    Plotly.restyle('power-scatter', { mode: _scatterLabelsOn ? 'markers+text' : 'markers' });
    const btn = document.getElementById('scatter-label-btn');
    if (btn) btn.textContent = _scatterLabelsOn ? 'Hide Labels' : 'Show Labels';
}

// ── MVP Race bar chart ────────────────────────────────────────────────────
function renderMVPRace(mvp) {
    if (!mvp.length) {
        const el = document.getElementById('mvp-chart');
        if (el) { el.style.height = 'auto'; el.innerHTML = mvpPendingHTML(_seasonRound); }
        return;
    }

    const top10 = mvp.slice(0, 10);
    // Last name only
    const names = top10.map(p => {
        const parts = p.player.split(',');
        return parts.length > 1 ? parts[0].trim() : p.player;
    });
    const scores = top10.map(p => p.mvp_score);
    const barColors = top10.map(p => teamInk(p.team));
    const hoverText = top10.map(p =>
        `<b>${p.player}</b><br>Team: ${p.team}<br>MVP Score: ${p.mvp_score.toFixed(1)}<br>Avg PIR: ${p.avg_pir.toFixed(1)}<br>GP: ${p.gp}`
    );

    const trace = {
        type: 'bar',
        orientation: 'h',
        x: scores,
        y: names,
        text: scores.map(s => s.toFixed(1)),
        textposition: 'inside',
        insidetextanchor: 'end',
        textfont: { color: '#111', size: 11 },
        hovertext: hoverText,
        hoverinfo: 'text',
        marker: {
            color: barColors,
            line: { color: '#1f2029', width: 1 },
        },
    };

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: '#0f1117',
        font: { color: '#9ca3af', family: 'Inter' },
        margin: { t: 10, b: 40, l: 110, r: 10 },
        xaxis: {
            title: 'MVP Score',
            gridcolor: '#2d2e3a',
            zerolinecolor: '#2d2e3a',
            tickfont: { size: 11 },
        },
        yaxis: {
            autorange: 'reversed',
            gridcolor: '#2d2e3a',
            tickfont: { size: 12, color: '#f0f0f5' },
        },
        showlegend: false,
        hoverlabel: { font: { color: '#111111' } },
        hovermode: 'closest',
    };

    Plotly.newPlot('mvp-chart', [trace], layout, { displayModeBar: false, responsive: true });
}

// ── Playoff probability grid ──────────────────────────────────────────────
// ── Remaining Schedule Difficulty ─────────────────────────────────────────
function renderScheduleDifficulty(teams) {
    const container = document.getElementById('schedule-difficulty');
    if (!teams.length) return;
    container.innerHTML = '';

    // Only show teams that still have remaining games
    const withGames = teams.filter(t => (t.remaining || 0) > 0);
    if (!withGames.length) {
        container.closest('.stat-card').style.display = 'none';
        return;
    }

    // Sort by current standing — official position from the export, else wins desc then adj_net desc
    const sorted = [...withGames].sort((a, b) =>
        (a.position != null && b.position != null)
            ? a.position - b.position
            : (b.wins - a.wins || b.adj_net - a.adj_net));

    const names     = sorted.map(t => t.name);
    const sos       = sorted.map(t => t.remaining_sos || 0);
    const remaining = sorted.map(t => t.remaining || 0);
    const homeGames = sorted.map(t => t.home_games || 0);
    const awayGames = sorted.map(t => t.away_games || 0);
    const colors    = sorted.map(t => TEAM_COLORS[t.team] || '#555');

    const meanSOS = sos.reduce((s, v) => s + v, 0) / sos.length;

    const hoverText = sorted.map((t, i) =>
        `<b>${t.name}</b><br>` +
        `Remaining: ${remaining[i]} games (${homeGames[i]}H / ${awayGames[i]}A)<br>` +
        `Opp Avg Win%: ${sos[i].toFixed(1)}%<br>` +
        `League avg: ${meanSOS.toFixed(1)}%`
    );

    // Difficulty label: colour bar by SOS vs mean
    const barColors = sos.map(s => {
        const diff = s - meanSOS;
        if (diff > 3)  return 'rgba(239,68,68,0.75)';   // tough
        if (diff < -3) return 'rgba(34,197,94,0.75)';   // easy
        return 'rgba(245,158,11,0.65)';                  // average
    });

    const traces = [
        {
            type: 'bar',
            orientation: 'h',
            y: names,
            x: sos,
            text: sorted.map((t, i) => `${sos[i].toFixed(1)}%  (${homeGames[i]}H/${awayGames[i]}A)`),
            textposition: 'outside',
            textfont: { color: '#9ca3af', size: 10 },
            hovertext: hoverText,
            hoverinfo: 'text',
            marker: { color: barColors, line: { color: '#1f2029', width: 1 } },
        },
        // Mean reference line (shape is cleaner but annotations work for legend)
    ];

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: '#0f1117',
        font: { color: '#9ca3af', family: 'Inter' },
        margin: { t: 10, b: 50, l: 160, r: 90 },
        height: Math.max(250, sorted.length * 28 + 80),
        xaxis: {
            title: 'Opponents Avg Win% (higher = harder schedule)',
            gridcolor: '#2d2e3a',
            zerolinecolor: '#2d2e3a',
            ticksuffix: '%',
            tickfont: { size: 11 },
            range: [Math.min(...sos) - 5, Math.max(...sos) + 8],
        },
        yaxis: {
            autorange: 'reversed',   // rank 1 at top
            gridcolor: '#2d2e3a',
            tickfont: { size: 11, color: '#f0f0f5' },
        },
        shapes: [{
            type: 'line',
            x0: meanSOS, x1: meanSOS,
            y0: -0.5, y1: names.length - 0.5,
            line: { color: 'rgba(156,163,175,0.5)', width: 1.5, dash: 'dot' },
        }],
        annotations: [{
            x: meanSOS, y: -0.5,
            text: `Avg ${meanSOS.toFixed(1)}%`,
            showarrow: false,
            yanchor: 'top',
            font: { color: 'rgba(156,163,175,0.7)', size: 10 },
        }],
        showlegend: false,
        hovermode: 'closest',
    };

    Plotly.newPlot('schedule-difficulty', traces, layout, { displayModeBar: false, responsive: true });
}

// ── Oracle header ─────────────────────────────────────────────────────────
function renderOracleHeader(data) {
    const el = document.getElementById('oracle-header');
    const round = data.oracle ? data.oracle.round : null;
    const hasPreds = !!(data.oracle && data.oracle.predictions && data.oracle.predictions.length);
    const acc = data.accuracy ? data.accuracy.accuracy : null;

    let html = '<div class="oracle-header-content">';
    if (hasPreds) {
        html += `<div class="oracle-round-badge">Round ${round || data.round || '?'} Forecast</div>`;
    } else {
        html += '<div class="oracle-round-badge">Final Accuracy</div>';
    }
    if (acc !== null) {
        html += `<div class="oracle-acc-badge">Model Accuracy: <strong>${acc.toFixed(1)}%</strong></div>`;
    }
    html += '</div>';
    el.innerHTML = html;
}

// ── Oracle game cards ─────────────────────────────────────────────────────
function parseInsight(raw) {
    if (!raw) return { headline: '', pills: [], keyPlayers: '' };
    const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);

    // Line 0: emoji + headline
    const headline = lines[0] ? lines[0].replace(/[\u2600-\u27BF\uD83C-\uDBFF\uDC00-\uDFFF]+/gu, '').trim() : '';

    // Line 1: "Adj Net: X v Y  |  Elo: X v Y"
    const pills = [];
    if (lines[1]) {
        lines[1].split('|').forEach(seg => {
            const s = seg.trim();
            if (s) pills.push(s);
        });
    }
    // Line 2: "L5: X-Y v X-Y  |  H: X-Y v A: X-Y"
    if (lines[2]) {
        lines[2].split('|').forEach(seg => {
            const s = seg.trim();
            if (s) pills.push(s);
        });
    }

    // Line 3: "Key players — H: Player  |  A: Player"
    let keyPlayers = '';
    if (lines[3]) {
        keyPlayers = lines[3].replace('Key players —', '').trim();
    }

    return { headline, pills, keyPlayers };
}

function renderOracleCards(oracle) {
    const container = document.getElementById('oracle-cards');
    if (!oracle || !oracle.predictions || !oracle.predictions.length) {
        container.innerHTML = '<div class="oracle-placeholder">'
            + '<p><strong>Regular season complete.</strong> The Oracle forecasts upcoming regular-season games — '
            + 'with no more on the schedule, there\'s nothing to predict.</p>'
            + '<p style="margin-top:0.5rem">Head to the <a href="playoffs.html">Playoffs page</a> for the bracket and play-in results.</p>'
            + '</div>';
        return;
    }

    // Sort by confidence descending — highest confidence picks first
    const preds = [...oracle.predictions].sort((a, b) => (b.Conf || 0) - (a.Conf || 0));
    let html = '<div class="oracle-cards-grid">';

    preds.forEach(p => {
        const homeWP = p.HomeWinProb || 50;
        const awayWP = 100 - homeWP;
        const isHomeWinner = p.Winner === p.Local;
        const margin = p.Margin ? Math.abs(p.Margin).toFixed(1) : '?';
        const conf = p.Conf ? p.Conf.toFixed(1) : '?';
        const homeGlow = isHomeWinner ? ' winner-glow' : '';
        const awayGlow = !isHomeWinner ? ' winner-glow' : '';
        const homeColor = TEAM_COLORS[p.Local] || '#ef4444';
        const awayColor = TEAM_COLORS[p.Road] || '#3b82f6';
        const winnerName = p.WinnerName || (isHomeWinner ? p.LocalName : p.RoadName) || p.Winner;

        const confNum = parseFloat(conf);
        // Confidence color: green ≥70%, gold 60-70%, grey <60%
        const confBadgeClass = confNum >= 70 ? 'conf-high' : confNum >= 60 ? 'conf-med' : 'conf-low';
        const isCoinFlip = p.Margin !== undefined && p.Margin !== null && Math.abs(p.Margin) <= 3;

        // Favorite bar gets brighter color + border; underdog bar stays muted
        const homeBarStyle = isHomeWinner
            ? `width:${homeWP}%;color:${teamOnColor(p.Local)};background:${homeColor}cc;box-shadow:0 0 8px ${homeColor}55;border:1px solid ${homeColor}`
            : `width:${homeWP}%;background:${homeColor}40`;
        const awayBarStyle = !isHomeWinner
            ? `width:${awayWP}%;color:${teamOnColor(p.Road)};background:${awayColor}cc;box-shadow:0 0 8px ${awayColor}55;border:1px solid ${awayColor}`
            : `width:${awayWP}%;background:${awayColor}40`;

        const { headline, pills, keyPlayers } = parseInsight(p.Insight);

        const pillsHtml = pills.map(pill => `<span class="insight-pill">${pill}</span>`).join('');
        const keyHtml = keyPlayers ? `<div class="insight-key-players">${keyPlayers}</div>` : '';

        // Format date: "Sep 30, 2025" → "Tue Sep 30"
        let dateStr = '';
        if (p.Date) {
            try {
                const dt = new Date(p.Date);
                dateStr = dt.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
            } catch (_) { dateStr = p.Date; }
        }
        const timeStr = p.Time ? p.Time.substring(0, 5) : '';

        html += `<div class="oracle-card" style="border-top:2px solid ${teamInk(isHomeWinner ? p.Local : p.Road)}99">
            ${dateStr ? `<div class="oracle-game-date">${dateStr}${timeStr ? ' · ' + timeStr : ''}</div>` : ''}
            <div class="oracle-matchup">
                <div class="oracle-team home-team${homeGlow}">
                    <span class="team-badge" style="background:${homeColor};color:${teamOnColor(p.Local)}">${(p.Local||'').substring(0,3)}</span>
                    <span class="oracle-team-name">${p.LocalName || p.Local}</span>
                    <span class="ha-badge ha-home">HOME</span>
                </div>
                <div class="oracle-vs">vs</div>
                <div class="oracle-team away-team${awayGlow}">
                    <span class="ha-badge ha-away">AWAY</span>
                    <span class="oracle-team-name">${p.RoadName || p.Road}</span>
                    <span class="team-badge" style="background:${awayColor};color:${teamOnColor(p.Road)}">${(p.Road||'').substring(0,3)}</span>
                </div>
            </div>
            <div class="wp-bar-wrap">
                <div class="wp-bar wp-home" style="${homeBarStyle}">
                    ${homeWP.toFixed(0)}%
                </div>
                <div class="wp-bar wp-away" style="${awayBarStyle}">
                    ${awayWP.toFixed(0)}%
                </div>
            </div>
            <div class="oracle-predicted">
                ${isCoinFlip ? '<span class="coin-flip-badge">🪙 Coin flip</span>' : ''}
                ${!isHomeWinner && !isCoinFlip ? `<span class="coin-flip-badge" style="background:${awayColor}22;color:${teamInk(p.Road)};border-color:${awayColor}55">📡 Away pick</span>` : ''}
                Predicted: <strong style="color:${teamInk(isHomeWinner ? p.Local : p.Road)}">${winnerName}</strong>
                <span class="oracle-conf ${confBadgeClass}">${conf}% conf · ±${margin} pts</span>
            </div>
            ${headline ? `<div class="oracle-headline">${headline}</div>` : ''}
            ${pillsHtml ? `<div class="insight-pills">${pillsHtml}</div>` : ''}
            ${keyHtml}
        </div>`;
    });

    html += '</div>';
    container.innerHTML = html;
}

// ── Player forecasts table ────────────────────────────────────────────────
let _forecastsAll = [];
let _forecastShowAll = false;
let _forecastTeamFilter = '';
let _forecastSort = { col: 'PredictedPIR', asc: false };
let _forecastTeamNames = {}; // code → full name

function renderPlayerForecasts(forecasts, teams) {
    _forecastsAll = forecasts || [];
    // Build code → name lookup from teams list
    _forecastTeamNames = {};
    (teams || []).forEach(t => { _forecastTeamNames[t.team] = t.name; });

    const container = document.getElementById('player-forecast-table');
    if (!_forecastsAll.length) {
        container.innerHTML = '<p style="color:var(--text-muted);padding:1rem">No upcoming games — player forecasts return next season.</p>';
        return;
    }

    // Build dropdown options sorted by team name
    const forecastTeams = [...new Set(_forecastsAll.map(p => p.Team))].sort((a, b) => {
        const na = _forecastTeamNames[a] || a, nb = _forecastTeamNames[b] || b;
        return na.localeCompare(nb);
    });

    const controls = `<div class="forecast-controls">
        <select id="forecast-team-filter" onchange="_forecastTeamFilter=this.value;_renderForecastTable()">
            <option value="">All Teams</option>
            ${forecastTeams.map(t => `<option value="${t}">${_forecastTeamNames[t] || t}</option>`).join('')}
        </select>
        <button class="forecast-toggle-btn" id="forecast-toggle-btn"
            onclick="_forecastShowAll=!_forecastShowAll;document.getElementById('forecast-toggle-btn').textContent=_forecastShowAll?'Show Top 15':'Show All';_renderForecastTable()">
            Show All
        </button>
    </div>`;

    container.innerHTML = controls + '<div id="forecast-table-body"></div>';
    _renderForecastTable();
}

function _forecastSortBy(col) {
    if (_forecastSort.col === col) {
        _forecastSort.asc = !_forecastSort.asc;
    } else {
        _forecastSort.col = col;
        _forecastSort.asc = false;
    }
    _renderForecastTable();
}

function _renderForecastTable() {
    let data = [..._forecastsAll];

    // Apply team filter
    if (_forecastTeamFilter) data = data.filter(p => p.Team === _forecastTeamFilter);

    // Apply sort
    const { col, asc } = _forecastSort;
    data.sort((a, b) => {
        const va = a[col] ?? 0, vb = b[col] ?? 0;
        return asc ? va - vb : vb - va;
    });

    const rows = _forecastShowAll || _forecastTeamFilter ? data : data.slice(0, 15);

    const sortable = (col, label) => {
        const active = _forecastSort.col === col;
        const arrow = active ? (_forecastSort.asc ? ' ▲' : ' ▼') : '';
        return `<th class="fc-sortable${active ? ' fc-sort-active' : ''}" onclick="_forecastSortBy('${col}')" style="text-align:right;cursor:pointer">${label}${arrow}</th>`;
    };

    let html = '<table class="forecast-tbl">';
    html += `<thead><tr>
        <th>#</th>
        <th style="text-align:left">Player</th>
        <th>Team</th>
        <th>vs</th>
        <th>H/A</th>
        ${sortable('AvgPIR', 'AvgPIR')}
        <th>Form</th>
        <th>WinP%</th>
        ${sortable('PredictedPIR', 'PredPIR')}
        ${sortable('PredictedPTS', 'PredPTS')}
    </tr></thead><tbody>`;

    rows.forEach((p, i) => {
        const rowBg = i % 2 === 0 ? 'background:rgba(255,255,255,0.02)' : '';
        const pirHighlight = p.PredictedPIR >= 20 ? 'color:var(--accent-gold);font-weight:700' : '';
        const ha = p.IsHome ? 'H' : 'A';
        const haColor = p.IsHome ? 'var(--accent-green)' : 'var(--accent-blue)';
        const teamColor = TEAM_COLORS[p.Team] || '#555';
        const teamName = _forecastTeamNames[p.Team] || p.Team;
        const lastName = (p.Player || '').split(',')[0].trim();
        const formPct = p.FormFactor ? ((p.FormFactor - 1) * 100).toFixed(0) : '0';
        const formColor = p.FormFactor >= 1 ? 'var(--accent-green)' : 'var(--accent-red)';
        const formStr = (p.FormFactor >= 1 ? '+' : '') + formPct + '%';
        const globalRank = _forecastsAll.indexOf(p) + 1;

        html += `<tr style="${rowBg}">
            <td style="color:var(--text-muted);text-align:center">${globalRank}</td>
            <td style="text-align:left;font-weight:600">${lastName}</td>
            <td><span class="team-badge sm" style="background:${teamColor};color:${teamOnColor(p.Team)}" title="${teamName}">${p.Team}</span></td>
            <td>${p.Opponent ? `<span class="team-badge sm" style="background:${TEAM_COLORS[p.Opponent]||'#555'};color:${teamOnColor(p.Opponent)}" title="${_forecastTeamNames[p.Opponent]||p.Opponent}">${p.Opponent}</span>` : ''}</td>
            <td style="color:${haColor};font-weight:700;text-align:center">${ha}</td>
            <td style="text-align:right">${(p.AvgPIR || 0).toFixed(1)}</td>
            <td style="text-align:right;color:${formColor}">${formStr}</td>
            <td style="text-align:right">${(p.WinProb || 0).toFixed(0)}%</td>
            <td style="text-align:right;${pirHighlight}">${(p.PredictedPIR || 0).toFixed(1)}</td>
            <td style="text-align:right">${(p.PredictedPTS || 0).toFixed(1)}</td>
        </tr>`;
    });

    const filteredCount = _forecastTeamFilter ? _forecastsAll.filter(p => p.Team === _forecastTeamFilter).length : _forecastsAll.length;
    const filterLabel = _forecastTeamFilter ? ` · ${filteredCount} on ${_forecastTeamNames[_forecastTeamFilter] || _forecastTeamFilter}` : '';
    const total = `${rows.length} of ${filteredCount} players${filterLabel ? '' : ` (${filteredCount} total)`}`;

    html += `</tbody></table><div class="forecast-count">${rows.length} of ${filteredCount} players${filterLabel}</div>`;
    document.getElementById('forecast-table-body').innerHTML = html;
}

// ── Accuracy stats ────────────────────────────────────────────────────────
function renderAccuracyStats(accuracy) {
    const container = document.getElementById('accuracy-stats');
    if (!accuracy) {
        container.innerHTML = '<p style="color:var(--text-muted);padding:1rem">No accuracy data available.</p>';
        return;
    }

    const acc = accuracy.accuracy || 0;
    const brier = accuracy.brier_score || 0;
    const logloss = accuracy.log_loss || 0;
    const n = accuracy.n_games || 0;
    const calibration = accuracy.calibration || [];

    let html = `<div class="accuracy-stat-row">
        <div class="acc-stat-box">
            <div class="acc-val" style="color:var(--accent-green)">${acc.toFixed(1)}%</div>
            <div class="acc-label">Accuracy</div>
        </div>
        <div class="acc-stat-box">
            <div class="acc-val">${brier.toFixed(4)}</div>
            <div class="acc-label">Brier Score</div>
        </div>
        <div class="acc-stat-box">
            <div class="acc-val">${logloss.toFixed(4)}</div>
            <div class="acc-label">Log-Loss</div>
        </div>
        <div class="acc-stat-box">
            <div class="acc-val">${n}</div>
            <div class="acc-label">Games</div>
        </div>
    </div>`;

    container.innerHTML = html;

    // Calibration chart
    if (calibration.length) {
        const calibDiv = document.createElement('div');
        calibDiv.id = 'calibration-chart';
        calibDiv.style.height = '220px';
        calibDiv.style.marginTop = '1rem';
        container.appendChild(calibDiv);

        const buckets = calibration.map(c => c.Bucket);
        const accVals = calibration.map(c => c.Accuracy);
        const confVals = calibration.map(c => c.AvgConfidence);

        // Color each bar by calibration error: |actual - confidence|
        const barColors = calibration.map(c => {
            const err = Math.abs(c.Accuracy - c.AvgConfidence);
            if (err <= 5)  return 'rgba(34,197,94,0.85)';   // well-calibrated
            if (err <= 10) return 'rgba(245,158,11,0.85)';  // slight miss
            return 'rgba(239,68,68,0.85)';                   // significant miss
        });

        const traces = [
            {
                type: 'bar',
                name: 'Actual Accuracy %',
                x: buckets,
                y: accVals,
                marker: { color: barColors },
                hovertemplate: '%{x}: %{y:.1f}% actual (conf %{customdata:.1f}%)<extra></extra>',
                customdata: confVals,
            },
            {
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Avg Confidence %',
                x: buckets,
                y: confVals,
                line: { color: '#a855f7', width: 2 },
                marker: { color: '#a855f7', size: 8 },
                hovertemplate: '%{x}: %{y:.1f}%<extra>Confidence</extra>',
            },
        ];

        const layout = {
            paper_bgcolor: 'transparent',
            plot_bgcolor: '#0f1117',
            font: { color: '#9ca3af', family: 'Inter', size: 10 },
            margin: { t: 5, b: 45, l: 40, r: 10 },
            xaxis: { gridcolor: '#2d2e3a', tickfont: { size: 10 } },
            yaxis: { gridcolor: '#2d2e3a', tickfont: { size: 10 }, title: '%' },
            legend: { font: { size: 10 }, bgcolor: 'transparent', x: 0, y: 1.1, orientation: 'h' },
            showlegend: true,
        };

        Plotly.newPlot('calibration-chart', traces, layout, { displayModeBar: false, responsive: true });
    }

    // Per-round accuracy trend
    const perRound = accuracy.per_round || [];
    if (perRound.length) {
        const trendDiv = document.createElement('div');
        trendDiv.id = 'accuracy-trend-chart';
        trendDiv.style.height = '200px';
        trendDiv.style.marginTop = '1.25rem';
        container.appendChild(trendDiv);

        const rounds = perRound.map(r => r.Round);
        const accByRound = perRound.map(r => r.Accuracy);
        const avgAcc = accByRound.reduce((s, v) => s + v, 0) / accByRound.length;

        const trendTraces = [
            {
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Round accuracy',
                x: rounds,
                y: accByRound,
                line: { color: '#6366f1', width: 2 },
                marker: { color: accByRound.map(v => v >= 70 ? '#22c55e' : v >= 50 ? '#f59e0b' : '#ef4444'), size: 7 },
                hovertemplate: 'Round %{x}: %{y:.1f}%<extra></extra>',
            },
            {
                type: 'scatter',
                mode: 'lines',
                name: `Season avg ${avgAcc.toFixed(1)}%`,
                x: [rounds[0], rounds[rounds.length - 1]],
                y: [avgAcc, avgAcc],
                line: { color: 'rgba(156,163,175,0.45)', width: 1.5, dash: 'dot' },
                hoverinfo: 'skip',
            },
        ];

        const trendLayout = {
            paper_bgcolor: 'transparent',
            plot_bgcolor: '#0f1117',
            font: { color: '#9ca3af', family: 'Inter', size: 10 },
            margin: { t: 10, b: 35, l: 40, r: 10 },
            xaxis: { title: 'Round', gridcolor: '#2d2e3a', tickfont: { size: 10 }, dtick: 5 },
            yaxis: { gridcolor: '#2d2e3a', tickfont: { size: 10 }, ticksuffix: '%', range: [0, 110] },
            legend: { font: { size: 10 }, bgcolor: 'transparent', x: 0, y: 1.15, orientation: 'h' },
            showlegend: true,
        };

        Plotly.newPlot('accuracy-trend-chart', trendTraces, trendLayout, { displayModeBar: false, responsive: true });
    }
}

// ── Standings Timeline (Bump Chart) ──────────────────────────────────────
function renderStandingsTimeline(teams) {
    const container = document.getElementById('standings-timeline');
    if (!container || !teams.length) return;

    // Find max round played
    let maxRound = Math.max(...teams.map(t => (t.round_results || []).length));
    if (maxRound < 1) { container.innerHTML = '<p style="color:var(--text-muted)">No round data available.</p>'; return; }

    // Build cumulative wins for each team at each round
    const teamData = teams.map(t => {
        const results = t.round_results || [];
        const cumWins = [];
        let wins = 0;
        for (let i = 0; i < results.length; i++) {
            if (results[i].result === 'W') wins++;
            cumWins.push(wins);
        }
        return { team: t.team, name: t.name, cumWins, gamesPlayed: results.length, results };
    });

    // The export provides official ranks per round (rank_history); use them when every team has
    // an equal-length history. Otherwise fall back to computing rank from cumulative wins
    // (1 = best, ties broken by losses then team name) for old dashboards.
    const ranks = []; // ranks[round][teamCode] = position
    const histLen = (teams[0].rank_history || []).length;
    const useHistory = histLen > 0 && teams.every(t => Array.isArray(t.rank_history) && t.rank_history.length === histLen);
    if (useHistory) {
        maxRound = histLen;
        for (let r = 0; r < maxRound; r++) {
            const roundRanks = {};
            teams.forEach(t => { roundRanks[t.team] = t.rank_history[r]; });
            ranks.push(roundRanks);
        }
    }
    for (let r = 0; !useHistory && r < maxRound; r++) {
        // For teams that haven't played round r+1 yet, use their last known wins
        const snapshot = teamData.map(td => ({
            team: td.team,
            wins: r < td.cumWins.length ? td.cumWins[r] : (td.cumWins.length ? td.cumWins[td.cumWins.length - 1] : 0),
            losses: (r < td.gamesPlayed ? r + 1 : td.gamesPlayed) - (r < td.cumWins.length ? td.cumWins[r] : (td.cumWins.length ? td.cumWins[td.cumWins.length - 1] : 0)),
        }));

        // Sort: more wins first, fewer losses as tiebreak, then alphabetical
        snapshot.sort((a, b) => b.wins - a.wins || a.losses - b.losses || a.team.localeCompare(b.team));

        const roundRanks = {};
        snapshot.forEach((s, i) => { roundRanks[s.team] = i + 1; });
        ranks.push(roundRanks);
    }

    // Sort teams by final rank for legend ordering
    const finalRanks = ranks[ranks.length - 1];
    const sortedTeams = [...teamData].sort((a, b) => finalRanks[a.team] - finalRanks[b.team]);

    // Top 8 visible by default, rest hidden (legendonly)
    const top8 = new Set(sortedTeams.slice(0, 8).map(t => t.team));

    // Build Plotly traces
    const rounds = Array.from({ length: maxRound }, (_, i) => i + 1);

    const traces = sortedTeams.map(td => {
        const color = teamInk(td.team);
        const y = rounds.map((_, i) => ranks[i][td.team]);
        const hoverText = rounds.map((r, i) => {
            const w = i < td.cumWins.length ? td.cumWins[i] : td.cumWins[td.cumWins.length - 1] || 0;
            const g = Math.min(r, td.gamesPlayed);
            const l = g - w;
            return `<b>${td.name}</b><br>Round ${r}: Rank #${ranks[i][td.team]}<br>Record: ${w}-${l}`;
        });

        return {
            x: rounds,
            y: y,
            mode: 'lines+markers',
            name: td.name,
            line: { color, width: 2.5, shape: 'linear' },
            marker: { color, size: 4 },
            hovertemplate: '%{customdata}<extra></extra>',
            customdata: hoverText,
            visible: top8.has(td.team) ? true : 'legendonly',
        };
    });

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        height: 500,
        margin: { t: 10, r: 20, b: 50, l: 50 },
        xaxis: {
            title: { text: 'Round', font: { color: '#9ca3af', size: 12 } },
            tickfont: { color: '#6b7280', size: 11 },
            gridcolor: '#2d2e3a',
            linecolor: '#2d2e3a',
            dtick: 1,
            tick0: 1,
            range: [0.5, maxRound + 0.5],
        },
        yaxis: {
            title: { text: 'Standings Position', font: { color: '#9ca3af', size: 12 } },
            tickfont: { color: '#6b7280', size: 11 },
            gridcolor: '#2d2e3a',
            linecolor: '#2d2e3a',
            autorange: 'reversed', // 1st place at top
            dtick: 1,
            range: [0.5, teams.length + 0.5],
        },
        legend: {
            font: { color: '#9ca3af', size: 11 },
            bgcolor: 'transparent',
            orientation: 'h',
            x: 0.5, xanchor: 'center', y: -0.15,
        },
        font: { family: 'Inter, sans-serif' },
        hoverlabel: { font: { color: '#111111' } },
        hovermode: 'closest',
    };

    container.innerHTML = '';
    Plotly.newPlot(container, traces, layout, { displayModeBar: false, responsive: true });
}

// ── Utility: hex to rgba ──────────────────────────────────────────────────
function hexToRgba(hex, alpha) {
    const h = hex.replace('#', '');
    const len = h.length === 3 ? 1 : 2;
    const r = parseInt(h.substring(0, len).padEnd(2, h[0]), 16);
    const g = parseInt(h.substring(len, len * 2).padEnd(2, h[len]), 16);
    const b = parseInt(h.substring(len * 2, len * 3).padEnd(2, h[len * 2]), 16);
    return `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
}

// ── Boot ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
