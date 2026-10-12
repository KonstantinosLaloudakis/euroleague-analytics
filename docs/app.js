/**
 * Euroleague Win Probability Replay — Client-side app
 * Loads pre-computed game data from JSON and renders interactive Plotly charts.
 */

const DATA_BASE = 'data';

// ── State ────────────────────────────────────────────────
let seasonsData = [];
let currentGames = [];
let _gc = null;  // current game context, used for chart mode toggling

// ── DOM Elements ─────────────────────────────────────────
const seasonSelect = document.getElementById('season-select');
const teamFilter = document.getElementById('team-filter');
const gameSelect = document.getElementById('game-select');
const chartDiv = document.getElementById('wp-chart');
const placeholder = document.getElementById('placeholder');
const keyPlaysSection = document.getElementById('key-plays');
const keyPlaysList = document.getElementById('key-plays-list');
const gameSummary = document.getElementById('game-summary');
const summaryContent = document.getElementById('summary-content');

// ── Helpers ───────────────────────────────────────────────
const fmtTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
};

// ── Initialize ───────────────────────────────────────────
async function init() {
    try {
        const resp = await fetch(`${DATA_BASE}/seasons.json`);
        seasonsData = await resp.json();

        seasonSelect.innerHTML = '<option value="">— Select Season —</option>';
        seasonsData.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.season;
            opt.textContent = `${s.label} (${s.count} games)`;
            seasonSelect.appendChild(opt);
        });
        seasonSelect.disabled = false;

        // Auto-select from URL params (e.g. ?season=2023&game=170).
        // Accept both ?game= and ?gamecode= since callers across the site
        // use both (playoffs.js, series.js use gamecode; game-control.js,
        // gci-history.js use game).
        const params = new URLSearchParams(window.location.search);
        const urlSeason = params.get('season');
        const urlGame = params.get('game') || params.get('gamecode');
        if (urlSeason && seasonSelect.querySelector(`option[value="${urlSeason}"]`)) {
            seasonSelect.value = urlSeason;
            seasonSelect.dispatchEvent(new Event('change'));
            if (urlGame) {
                // Wait for the season change handler to load games, then select
                const waitForGames = setInterval(() => {
                    if (gameSelect.querySelector(`option[value="${urlGame}"]`)) {
                        clearInterval(waitForGames);
                        gameSelect.value = urlGame;
                        gameSelect.dispatchEvent(new Event('change'));
                    }
                }, 50);
                // Safety timeout: stop polling after 5s
                setTimeout(() => clearInterval(waitForGames), 5000);
            }
        }
    } catch (err) {
        seasonSelect.innerHTML = '<option value="">Error loading seasons</option>';
        console.error('Failed to load seasons:', err);
    }
}

// ── Season Changed ───────────────────────────────────────
seasonSelect.addEventListener('change', async () => {
    const season = seasonSelect.value;
    if (!season) {
        resetDownstream();
        return;
    }

    gameSelect.innerHTML = '<option value=""><span class="loading-spinner"></span>Loading games...</option>';
    gameSelect.disabled = true;
    teamFilter.disabled = true;

    try {
        const resp = await fetch(`${DATA_BASE}/${season}/games.json`);
        currentGames = await resp.json();

        const teamMap = new Map();
        currentGames.forEach(g => {
            teamMap.set(g.ta, g.ta_name);
            teamMap.set(g.tb, g.tb_name);
        });

        const sortedTeams = Array.from(teamMap.keys()).sort((a, b) => teamMap.get(a).localeCompare(teamMap.get(b)));

        teamFilter.innerHTML = '<option value="">All Teams</option>';
        sortedTeams.forEach(code => {
            const opt = document.createElement('option');
            opt.value = code;
            opt.textContent = `${teamMap.get(code)} (${code})`;
            teamFilter.appendChild(opt);
        });
        teamFilter.disabled = false;

        populateGames();
    } catch (err) {
        gameSelect.innerHTML = '<option value="">Error loading games</option>';
        console.error('Failed to load games:', err);
    }
});

// ── Team Filter Changed ──────────────────────────────────
teamFilter.addEventListener('change', populateGames);

function populateGames() {
    const filterTeam = teamFilter.value;
    let games = currentGames;

    if (filterTeam) {
        games = games.filter(g => g.ta === filterTeam || g.tb === filterTeam);
    }

    gameSelect.innerHTML = '<option value="">— Select Game —</option>';
    games.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.gc;
        opt.dataset.taName = g.ta_name;
        opt.dataset.tbName = g.tb_name;
        const winner = g.sa > g.sb ? g.ta : g.tb;
        const marker = winner === g.ta ? '✦ ' : '';
        const marker2 = winner === g.tb ? ' ✦' : '';

        let roundStr = g.rnd;
        if (typeof roundStr === 'number') roundStr = `Round ${roundStr}`;

        opt.textContent = `[${roundStr}] ${marker}${g.ta_name} ${g.sa} - ${g.sb} ${g.tb_name}${marker2}`;
        gameSelect.appendChild(opt);
    });
    gameSelect.disabled = false;
}

// ── Game Selected ────────────────────────────────────────
gameSelect.addEventListener('change', async () => {
    const gc = gameSelect.value;
    const season = seasonSelect.value;
    if (!gc || !season) return;

    placeholder.classList.add('hidden');

    try {
        const resp = await fetch(`${DATA_BASE}/${season}/${gc}.json`);
        const data = await resp.json();
        const option = gameSelect.options[gameSelect.selectedIndex];
        renderChart(data, option.dataset.taName, option.dataset.tbName);
    } catch (err) {
        console.error('Failed to load game data:', err);
    }
});

// ── WP Chart Builder ─────────────────────────────────────
function _buildWPChart(full, ta, tb, taName, tbName) {
    const elapsed = full.map(p => p.e / 60);
    const wpPct = full.map(p => p.w * 100);

    const hoverText = full.map(p =>
        `<b>${p.d}</b><br>` +
        `Score: ${taName} ${p.a} - ${p.b} ${tbName}<br>` +
        `WP (${taName}): ${(p.w * 100).toFixed(1)}%<br>` +
        `Q${p.p} — ${fmtTime(p.s)} remaining`
    );

    const shifts = full.map((p, i) => ({
        ...p,
        shift: i > 0 ? (p.w - full[i - 1].w) * 100 : 0,
        idx: i,
    }));
    const keyPlays = [...shifts]
        .sort((a, b) => Math.abs(b.shift) - Math.abs(a.shift))
        .filter(p => Math.abs(p.shift) >= 3 && p.d !== 'Tip-Off')
        .slice(0, 8);

    const traces = [];
    traces.push({
        x: elapsed, y: wpPct,
        fill: 'tozeroy', fillcolor: 'rgba(59,130,246,0.1)',
        line: { width: 0 }, showlegend: false, hoverinfo: 'skip',
    });
    traces.push({
        x: elapsed, y: wpPct,
        fill: 'tonexty', fillcolor: 'rgba(239,68,68,0.08)',
        line: { width: 0 }, showlegend: false, hoverinfo: 'skip', yaxis: 'y',
    });
    traces.push({
        x: elapsed, y: wpPct,
        mode: 'lines',
        line: { color: 'rgba(255,255,255,0.9)', width: 2.5 },
        text: hoverText, hoverinfo: 'text', showlegend: false,
    });

    keyPlays.forEach(kp => {
        const color = kp.shift > 0 ? '#22c55e' : '#ef4444';
        traces.push({
            x: [kp.e / 60], y: [kp.w * 100],
            mode: 'markers',
            marker: { size: 9, color, symbol: 'circle', line: { color: 'white', width: 1 } },
            showlegend: false,
            hovertext: `<b>${kp.d}</b><br>WP: ${(kp.w * 100).toFixed(1)}%<br>Shift: ${kp.shift > 0 ? '+' : ''}${kp.shift.toFixed(1)}%<br>Score: ${taName} ${kp.a} - ${kp.b} ${tbName}<br>Q${kp.p} — ${fmtTime(kp.s)} remaining`,
            hoverinfo: 'text',
        });
    });

    const finalScore = full[full.length - 1];
    const layout = {
        title: {
            text: `${taName} ${finalScore.a} - ${finalScore.b} ${tbName}`,
            font: { size: 22, color: 'white', family: 'Outfit, sans-serif' },
            x: 0.5, xanchor: 'center',
        },
        xaxis: {
            title: { text: 'Game Time (Minutes)', font: { color: '#9ca3af' } },
            range: [0, 40],
            tickvals: [0, 5, 10, 15, 20, 25, 30, 35, 40],
            color: '#9ca3af', gridcolor: '#2d2e3a', zeroline: false,
        },
        yaxis: {
            title: { text: 'Win Probability (%)', font: { color: '#9ca3af' } },
            range: [0, 100],
            tickvals: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            color: '#9ca3af', gridcolor: '#2d2e3a', zeroline: false,
        },
        plot_bgcolor: '#0f1117', paper_bgcolor: '#1f2029',
        font: { color: 'white' }, showlegend: false,
        hovermode: 'closest',
        margin: { l: 55, r: 20, t: 60, b: 50 },
        shapes: [
            { type: 'line', x0: 0, x1: 40, y0: 50, y1: 50, line: { color: '#4b5563', width: 1, dash: 'dash' } },
            ...[10, 20, 30].map(x => ({
                type: 'line', x0: x, x1: x, y0: 0, y1: 100,
                line: { color: '#374151', width: 1, dash: 'dot' },
            })),
        ],
        annotations: [
            { x: 0.5, y: 97, text: `<b>${ta}</b>`, showarrow: false, font: { size: 14, color: '#ef4444' }, xref: 'x', yref: 'y', xanchor: 'left' },
            { x: 0.5, y: 3, text: `<b>${tb}</b>`, showarrow: false, font: { size: 14, color: '#3b82f6' }, xref: 'x', yref: 'y', xanchor: 'left' },
            ...[1, 2, 3, 4].map((q, i) => ({
                x: 5 + i * 10, y: 96, text: `Q${q}`, showarrow: false,
                font: { size: 10, color: '#6b7280' }, xref: 'x', yref: 'y',
            })),
        ],
    };

    return { traces, layout, keyPlays };
}

// ── Margin Chart Builder ─────────────────────────────────
function _buildMarginChart(full, ta, tb, taName, tbName) {
    const elapsed = full.map(p => p.e / 60);
    const margin = full.map(p => p.a - p.b);

    const hoverText = full.map(p => {
        const m = p.a - p.b;
        return `<b>${p.d}</b><br>` +
            `Score: ${taName} ${p.a} - ${p.b} ${tbName}<br>` +
            `Margin: ${m > 0 ? '+' : ''}${m}<br>` +
            `Q${p.p} — ${fmtTime(p.s)} remaining`;
    });

    const finalScore = full[full.length - 1];
    const traces = [
        // Red fill — team A leading
        {
            x: elapsed, y: margin.map(m => Math.max(0, m)),
            fill: 'tozeroy', fillcolor: 'rgba(239,68,68,0.15)',
            line: { width: 0 }, showlegend: false, hoverinfo: 'skip',
        },
        // Blue fill — team B leading
        {
            x: elapsed, y: margin.map(m => Math.min(0, m)),
            fill: 'tozeroy', fillcolor: 'rgba(59,130,246,0.15)',
            line: { width: 0 }, showlegend: false, hoverinfo: 'skip',
        },
        // Main line
        {
            x: elapsed, y: margin,
            mode: 'lines',
            line: { color: 'rgba(255,255,255,0.9)', width: 2.5 },
            text: hoverText, hoverinfo: 'text', showlegend: false,
        },
    ];

    const absMax = Math.max(15, ...margin.map(Math.abs));
    const yPad = Math.ceil(absMax * 1.2);

    const layout = {
        title: {
            text: `${taName} ${finalScore.a} - ${finalScore.b} ${tbName}`,
            font: { size: 22, color: 'white', family: 'Outfit, sans-serif' },
            x: 0.5, xanchor: 'center',
        },
        xaxis: {
            title: { text: 'Game Time (Minutes)', font: { color: '#9ca3af' } },
            range: [0, 40],
            tickvals: [0, 5, 10, 15, 20, 25, 30, 35, 40],
            color: '#9ca3af', gridcolor: '#2d2e3a', zeroline: false,
        },
        yaxis: {
            title: { text: `Score Margin (${ta} +/-)`, font: { color: '#9ca3af' } },
            range: [-yPad, yPad],
            color: '#9ca3af', gridcolor: '#2d2e3a',
            zeroline: true, zerolinecolor: '#4b5563', zerolinewidth: 2,
        },
        plot_bgcolor: '#0f1117', paper_bgcolor: '#1f2029',
        font: { color: 'white' }, showlegend: false,
        hovermode: 'closest',
        margin: { l: 55, r: 20, t: 60, b: 50 },
        shapes: [
            ...[10, 20, 30].map(x => ({
                type: 'line', x0: x, x1: x, y0: -yPad, y1: yPad,
                line: { color: '#374151', width: 1, dash: 'dot' },
            })),
        ],
        annotations: [
            { x: 0.5, y: 0.96, text: `▲ ${taName} leading`, showarrow: false, font: { size: 11, color: '#ef4444' }, xref: 'x', yref: 'paper', xanchor: 'left', opacity: 0.7 },
            { x: 0.5, y: 0.04, text: `▼ ${tbName} leading`, showarrow: false, font: { size: 11, color: '#3b82f6' }, xref: 'x', yref: 'paper', xanchor: 'left', opacity: 0.7 },
            ...[1, 2, 3, 4].map((q, i) => ({
                x: 5 + i * 10, y: 0.99, text: `Q${q}`, showarrow: false,
                font: { size: 10, color: '#6b7280' }, xref: 'x', yref: 'paper',
            })),
        ],
    };

    return { traces, layout };
}

// ── Refresh Main Chart ────────────────────────────────────
function _refreshMainChart(mode) {
    if (!_gc) return;
    const { full, ta, tb, taName, tbName } = _gc;
    const { traces, layout } = mode === 'margin'
        ? _buildMarginChart(full, ta, tb, taName, tbName)
        : _buildWPChart(full, ta, tb, taName, tbName);
    Plotly.react(chartDiv, traces, layout, { responsive: true, displayModeBar: false });
}

// ── In-Game WPA ───────────────────────────────────────────
function computeInGameWPA(full, ta) {
    const wpaMap = {};
    for (let i = 1; i < full.length; i++) {
        const play = full[i];
        const wpShift = play.w - full[i - 1].w;  // positive = team A probability rose

        // Parse "LASTNAME, FIRSTNAME (TEAM) → action" format
        const match = play.d.match(/^(.+?)\s*\(([A-Z]{2,4})\)/);
        if (!match) continue;

        const playerName = match[1].trim();
        const teamCode = match[2];
        if (teamCode === 'UNK') continue;

        // WPA from the player's own team's perspective
        const teamWPA = teamCode === ta ? wpShift : -wpShift;

        const key = `${playerName}|${teamCode}`;
        if (!wpaMap[key]) wpaMap[key] = { name: playerName, team: teamCode, wpa: 0 };
        wpaMap[key].wpa += teamWPA;
    }

    return Object.values(wpaMap)
        .sort((a, b) => b.wpa - a.wpa);
}

function renderWPALeaderboard(wpaData, ta, tb, taName, tbName) {
    const el = document.getElementById('wpa-ingame-chart');
    if (!el || wpaData.length === 0) return;

    // Top 8 + bottom 3 contributors (most interesting slice)
    const top = wpaData.slice(0, 8);
    const bottom = wpaData.filter(p => p.wpa < 0).slice(-3);
    const combined = [...bottom, ...top].filter((v, i, a) =>
        a.findIndex(x => x.name === v.name && x.team === v.team) === i
    );
    combined.sort((a, b) => a.wpa - b.wpa);

    const labels = combined.map(p => {
        const short = p.name.split(',')[0];
        return `${short} <span style="color:#6b7280">(${p.team})</span>`;
    });
    const values = combined.map(p => parseFloat(p.wpa.toFixed(3)));
    const colors = combined.map(p =>
        p.team === ta
            ? (p.wpa >= 0 ? '#ef4444' : '#fca5a5')
            : (p.wpa >= 0 ? '#3b82f6' : '#93c5fd')
    );
    const hoverText = combined.map(p => {
        const teamName = p.team === ta ? taName : tbName;
        return `<b>${p.name}</b><br>${teamName}<br>WPA: ${p.wpa >= 0 ? '+' : ''}${p.wpa.toFixed(3)}`;
    });

    const trace = {
        type: 'bar',
        orientation: 'h',
        x: values,
        y: labels,
        marker: { color: colors },
        text: values.map(v => `${v >= 0 ? '+' : ''}${v.toFixed(3)}`),
        textposition: 'outside',
        textfont: { size: 11, color: '#9ca3af' },
        hoverinfo: 'text',
        hovertext: hoverText,
        cliponaxis: false,
    };

    const absMax = Math.max(...values.map(Math.abs), 0.05);
    const layout = {
        xaxis: {
            title: { text: 'Win Probability Added (team perspective)', font: { color: '#9ca3af' }, standoff: 8 },
            range: [-(absMax * 1.35), absMax * 1.35],
            color: '#9ca3af', gridcolor: '#2d2e3a',
            zeroline: true, zerolinecolor: '#4b5563', zerolinewidth: 2,
        },
        yaxis: { color: '#9ca3af', automargin: true },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: '#9ca3af', size: 12 },
        margin: { l: 130, r: 60, t: 10, b: 50 },
        showlegend: false,
        annotations: [
            { x: absMax * 1.3, y: 1, xref: 'x', yref: 'paper', text: `${taName} →`, showarrow: false, font: { color: '#ef4444', size: 10 }, xanchor: 'right' },
            { x: -(absMax * 1.3), y: 1, xref: 'x', yref: 'paper', text: `← ${tbName}`, showarrow: false, font: { color: '#3b82f6', size: 10 }, xanchor: 'left' },
        ],
    };

    Plotly.newPlot(el, [trace], layout, { displayModeBar: false, responsive: true });
}

// ── Render Chart ─────────────────────────────────────────
function renderChart(data, taName, tbName) {
    const { ta, tb, timeline } = data;

    taName = taName || ta;
    tbName = tbName || tb;

    const full = [{ e: 0, s: 2400, a: 0, b: 0, w: 0.5, p: 1, d: 'Tip-Off' }, ...timeline];

    // Save context for mode toggle
    _gc = { full, ta, tb, taName, tbName };

    // Show and reset toggle buttons
    const toggleEl = document.getElementById('chart-mode-toggle');
    const btnWP = document.getElementById('btn-mode-wp');
    const btnMargin = document.getElementById('btn-mode-margin');
    toggleEl.style.display = 'flex';
    btnWP.classList.add('active');
    btnMargin.classList.remove('active');
    btnWP.onclick = () => { btnWP.classList.add('active'); btnMargin.classList.remove('active'); _refreshMainChart('wp'); };
    btnMargin.onclick = () => { btnMargin.classList.add('active'); btnWP.classList.remove('active'); _refreshMainChart('margin'); };

    // Initial WP chart render
    const { traces, layout, keyPlays } = _buildWPChart(full, ta, tb, taName, tbName);
    Plotly.react(chartDiv, traces, layout, { responsive: true, displayModeBar: false });

    // Game summary
    const finalScore = full[full.length - 1];
    const winnerName = finalScore.a > finalScore.b ? taName : tbName;
    const minWP = Math.min(...full.map(p => p.w * 100));
    const maxWP = Math.max(...full.map(p => p.w * 100));
    summaryContent.innerHTML = `
        <strong>${winnerName} wins ${finalScore.a}-${finalScore.b}</strong> ·
        ${taName} WP range: ${minWP.toFixed(1)}% — ${maxWP.toFixed(1)}% ·
        ${full.length - 2} scoring plays
    `;

    // Key plays panel
    keyPlaysList.innerHTML = '';
    const sortedByTime = [...keyPlays].sort((a, b) => a.e - b.e);
    sortedByTime.forEach(kp => {
        const card = document.createElement('div');
        const cls = kp.shift > 0 ? 'positive' : 'negative';
        card.className = `key-play-card ${cls}`;
        card.innerHTML = `
            <div class="key-play-desc">${kp.d}</div>
            <div class="key-play-meta">Q${kp.p} · ${fmtTime(kp.s)} · Score: ${taName} ${kp.a}-${kp.b} ${tbName}</div>
            <div class="key-play-shift ${cls}">WP: ${(kp.w * 100).toFixed(1)}% (${kp.shift > 0 ? '+' : ''}${kp.shift.toFixed(1)}%)</div>
        `;
        keyPlaysList.appendChild(card);
    });
    keyPlaysSection.classList.remove('hidden');
    gameSummary.classList.remove('hidden');

    // ── Advanced Stats Panel ─────────────────────────────
    const advStatsSection = document.getElementById('adv-stats');
    if (data.adv && Object.keys(data.adv).length > 0) {
        advStatsSection.classList.remove('hidden');

        // 1. Quarter Margins
        if (data.adv.q && data.adv.q.length > 0) {
            const periods = data.adv.q.map(q => q.p <= 4 ? `Q${q.p}` : `OT${q.p - 4}`);
            const margins = data.adv.q.map(q => q.a - q.b);
            const colors = margins.map(m => m >= 0 ? '#ef4444' : '#3b82f6');

            Plotly.newPlot('q-margin-chart', [{
                x: periods, y: margins, type: 'bar',
                marker: { color: colors },
                text: margins.map(m => m > 0 ? `+${m}` : m),
                textposition: 'auto', hoverinfo: 'none',
            }], {
                margin: { l: 30, r: 10, t: 10, b: 30 },
                paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                font: { color: '#9ca3af' },
                xaxis: { fixedrange: true },
                yaxis: { fixedrange: true, zerolinecolor: '#4b5563' },
            }, { displayModeBar: false });
        }

        // 2. In-Game WPA Leaderboard (new)
        const wpaData = computeInGameWPA(full, ta);
        renderWPALeaderboard(wpaData, ta, tb, taName, tbName);

        // 3. Player Impact Quadrant
        if (data.adv.i && data.adv.i.length > 0) {
            const teamA_players = data.adv.i.filter(p => p.t === ta);
            const teamB_players = data.adv.i.filter(p => p.t === tb);

            Plotly.newPlot('impact-chart', [
                {
                    x: teamA_players.map(p => p.p), y: teamA_players.map(p => p.h),
                    mode: 'markers+text', type: 'scatter', name: taName,
                    text: teamA_players.map(p => p.n), textposition: 'top center',
                    marker: { size: 12, color: '#ef4444', line: { color: 'white', width: 1 } },
                    hoverinfo: 'text',
                    hovertext: teamA_players.map(p => `<b>${p.n}</b><br>Points: ${p.p}<br>Hustle (REB+AST+STL): ${p.h}`),
                },
                {
                    x: teamB_players.map(p => p.p), y: teamB_players.map(p => p.h),
                    mode: 'markers+text', type: 'scatter', name: tbName,
                    text: teamB_players.map(p => p.n), textposition: 'top center',
                    marker: { size: 12, color: '#3b82f6', line: { color: 'white', width: 1 } },
                    hoverinfo: 'text',
                    hovertext: teamB_players.map(p => `<b>${p.n}</b><br>Points: ${p.p}<br>Hustle (REB+AST+STL): ${p.h}`),
                },
            ], {
                margin: { l: 40, r: 20, t: 20, b: 40 },
                paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                font: { color: '#9ca3af' },
                xaxis: { title: 'Offensive Production (Points)', gridcolor: '#2d2e3a' },
                yaxis: { title: 'Playmaking & Hustle', gridcolor: '#2d2e3a' },
                legend: { orientation: 'h', y: 1.1, x: 0.5, xanchor: 'center' },
                annotations: [
                    { x: 1, y: 1, xref: 'paper', yref: 'paper', text: 'High Volume / High Hustle', showarrow: false, font: { color: '#10b981', size: 10 }, xanchor: 'right', yanchor: 'top', opacity: 0.5 },
                    { x: 1, y: 0, xref: 'paper', yref: 'paper', text: 'Scoring Specialists', showarrow: false, font: { color: '#f59e0b', size: 10 }, xanchor: 'right', yanchor: 'bottom', opacity: 0.5 },
                    { x: 0, y: 1, xref: 'paper', yref: 'paper', text: 'Role Players / Glue', showarrow: false, font: { color: '#f59e0b', size: 10 }, xanchor: 'left', yanchor: 'top', opacity: 0.5 },
                ],
            }, { displayModeBar: false });
        }

        // 4. Major Scoring Runs
        const runsList = document.getElementById('runs-list');
        runsList.innerHTML = '';
        if (data.adv.r && data.adv.r.length > 0) {
            data.adv.r.forEach(run => {
                const isTeamA = run.t === ta;
                const teamName = isTeamA ? taName : tbName;
                const cls = isTeamA ? 'team-a' : 'team-b';
                const item = document.createElement('div');
                item.className = `run-item ${cls}`;
                item.innerHTML = `
                    <div class="run-score ${cls}">${run.p} - 0</div>
                    <div class="run-meta">
                        <strong>${teamName}</strong><br>
                        ${fmtTime(2400 - run.en)} to ${fmtTime(2400 - run.st)} remaining
                    </div>
                `;
                runsList.appendChild(item);
            });
        } else {
            runsList.innerHTML = '<div style="color:var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">No major runs (8+ pts) detected.</div>';
        }

        // 5. Four Factors Radar
        if (data.adv.f && data.adv.f.length > 0) {
            const getFactors = (code) => {
                const fa = data.adv.f.find(f => f.t === code) || { eFG: 0, TOV: 0, ORB: 0, FTR: 0 };
                return [fa.eFG, fa.TOV, fa.ORB, fa.FTR, fa.eFG];
            };
            const rCats = ['eFG%', 'TOV% (Lower=Better)', 'ORB%', 'FT Rate', 'eFG%'];

            Plotly.newPlot('radar-chart', [
                { type: 'scatterpolar', r: getFactors(ta), theta: rCats, fill: 'toself', name: taName, line: { color: '#ef4444' }, fillcolor: 'rgba(239,68,68,0.2)' },
                { type: 'scatterpolar', r: getFactors(tb), theta: rCats, fill: 'toself', name: tbName, line: { color: '#3b82f6' }, fillcolor: 'rgba(59,130,246,0.2)' },
            ], {
                polar: {
                    radialaxis: { visible: true, range: [0, 80], color: '#4b5563', gridcolor: '#334155' },
                    angularaxis: { color: '#9ca3af', gridcolor: '#334155' },
                    bgcolor: 'transparent',
                },
                showlegend: true,
                legend: { orientation: 'h', y: -0.2, x: 0.5, xanchor: 'center', font: { color: '#9ca3af' } },
                paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                margin: { l: 65, r: 65, t: 40, b: 50 },
            }, { displayModeBar: false });
        }

        // 6. Top Lineups
        const lineupsList = document.getElementById('lineups-list');
        lineupsList.innerHTML = '';
        if (data.adv.l && data.adv.l.length > 0) {
            data.adv.l.forEach(lu => {
                const isTeamA = lu.t === ta;
                const teamName = isTeamA ? taName : tbName;
                const cls = isTeamA ? 'team-a' : 'team-b';
                const item = document.createElement('div');
                item.className = `lineup-item ${cls}`;
                const scoreClass = lu.n > 0 ? 'positive' : (lu.n < 0 ? 'negative' : '');
                const scorePrefix = lu.n > 0 ? '+' : '';
                item.innerHTML = `
                    <div class="lineup-meta">
                        <strong>${teamName}</strong>
                        <div class="lineup-score ${scoreClass}">${scorePrefix}${lu.n}</div>
                    </div>
                    <div class="lineup-names">${lu.l}</div>
                    <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 5px;">Played: ${lu.d} mins</div>
                `;
                lineupsList.appendChild(item);
            });
        } else {
            lineupsList.innerHTML = '<div style="color:var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">No significant 5-man lineups tracked for this game.</div>';
        }

        // 7. Shot Chart with Zone Efficiency
        const shotChartCard = document.getElementById('shot-chart-card');
        if (data.adv.s && data.adv.s.length > 0) {
            if (shotChartCard) shotChartCard.style.display = '';
            const shotData = data.adv.s;

            function classifyZone(x, y) {
                const dist = Math.sqrt(x * x + y * y);
                if (Math.abs(x) >= 660 || dist >= 675) return '3PT';
                if (Math.abs(x) <= 245 && y <= 422.5) return 'Paint';
                return 'Mid';
            }

            function computeZoneStats(shots) {
                const zones = { Paint: { m: 0, a: 0 }, Mid: { m: 0, a: 0 }, '3PT': { m: 0, a: 0 } };
                shots.forEach(s => {
                    const z = classifyZone(s.x, s.y);
                    zones[z].a++;
                    if (s.m === 1) zones[z].m++;
                });
                return zones;
            }

            function getCourtShapes() {
                const c = '#555', w = 1.5;
                function arcPath(cx, cy, rx, ry, startDeg, endDeg, steps = 60) {
                    let path = '';
                    for (let i = 0; i <= steps; i++) {
                        const angle = (startDeg + (endDeg - startDeg) * i / steps) * Math.PI / 180;
                        const x = cx + rx * Math.cos(angle);
                        const y = cy + ry * Math.sin(angle);
                        path += (i === 0 ? 'M ' : 'L ') + x + ',' + y + ' ';
                    }
                    return path;
                }
                const cornerX = 660, arcR = 675;
                const interY = Math.sqrt(arcR * arcR - cornerX * cornerX);
                return [
                    { type: 'line', x0: -750, y0: -157.5, x1: 750, y1: -157.5, line: { color: c, width: w } },
                    { type: 'line', x0: -90, y0: -37.5, x1: 90, y1: -37.5, line: { color: c, width: w } },
                    { type: 'line', x0: -245, y0: -157.5, x1: -245, y1: 422.5, line: { color: c, width: w } },
                    { type: 'line', x0: 245, y0: -157.5, x1: 245, y1: 422.5, line: { color: c, width: w } },
                    { type: 'line', x0: -245, y0: 422.5, x1: 245, y1: 422.5, line: { color: c, width: w } },
                    { type: 'path', path: arcPath(0, 0, 125, 125, 0, 180), line: { color: c, width: w }, fillcolor: 'rgba(0,0,0,0)' },
                    { type: 'circle', x0: -22.5, y0: -22.5, x1: 22.5, y1: 22.5, line: { color: '#ef4444', width: 2 }, fillcolor: 'rgba(0,0,0,0)' },
                    { type: 'line', x0: cornerX, y0: -157.5, x1: cornerX, y1: interY, line: { color: c, width: w } },
                    { type: 'line', x0: -cornerX, y0: -157.5, x1: -cornerX, y1: interY, line: { color: c, width: w } },
                    {
                        type: 'path',
                        path: arcPath(0, 0, arcR, arcR,
                            Math.atan2(interY, cornerX) * 180 / Math.PI,
                            180 - Math.atan2(interY, cornerX) * 180 / Math.PI),
                        line: { color: c, width: w }, fillcolor: 'rgba(0,0,0,0)',
                    },
                ];
            }

            function buildZoneAnnotations(zones) {
                const fmt = (z) => zones[z].a > 0
                    ? `${z}\n${zones[z].m}/${zones[z].a} (${Math.round(zones[z].m / zones[z].a * 100)}%)`
                    : `${z}\n—`;

                return [
                    { x: 0, y: 130, text: fmt('Paint'), showarrow: false, font: { color: '#fbbf24', size: 11, family: 'Inter' }, xref: 'x', yref: 'y', bgcolor: 'rgba(15,17,23,0.7)', borderpad: 3 },
                    { x: 460, y: 490, text: fmt('Mid'), showarrow: false, font: { color: '#fbbf24', size: 11, family: 'Inter' }, xref: 'x', yref: 'y', bgcolor: 'rgba(15,17,23,0.7)', borderpad: 3 },
                    { x: 0, y: 810, text: fmt('3PT'), showarrow: false, font: { color: '#fbbf24', size: 11, family: 'Inter' }, xref: 'x', yref: 'y', bgcolor: 'rgba(15,17,23,0.7)', borderpad: 3 },
                ];
            }

            function renderShotChart(teamCode) {
                const teamShots = shotData.filter(s => s.t === teamCode);
                const isTeamA = teamCode === ta;
                const teamName = isTeamA ? taName : tbName;
                const makes = teamShots.filter(s => s.m === 1);
                const misses = teamShots.filter(s => s.m === 0);
                const fgPct = teamShots.length > 0 ? (makes.length / teamShots.length * 100).toFixed(1) : 0;

                const zones = computeZoneStats(teamShots);
                const zoneAnnotations = buildZoneAnnotations(zones);

                const traces = [
                    {
                        x: makes.map(s => s.x), y: makes.map(s => s.y),
                        mode: 'markers', type: 'scatter', name: 'Made',
                        marker: { size: 10, color: '#10b981', symbol: 'circle', line: { color: 'white', width: 1 }, opacity: 0.85 },
                        hoverinfo: 'text',
                        hovertext: makes.map(s => `<b>${s.n}</b><br>Made (Q${s.q})`),
                    },
                    {
                        x: misses.map(s => s.x), y: misses.map(s => s.y),
                        mode: 'markers', type: 'scatter', name: 'Missed',
                        marker: { size: 8, color: '#ef4444', symbol: 'x', line: { width: 1.5 }, opacity: 0.6 },
                        hoverinfo: 'text',
                        hovertext: misses.map(s => `<b>${s.n}</b><br>Missed (Q${s.q})`),
                    },
                ];

                Plotly.newPlot('shot-chart', traces, {
                    shapes: getCourtShapes(),
                    annotations: zoneAnnotations,
                    xaxis: { range: [-800, 800], showgrid: false, zeroline: false, showticklabels: false, fixedrange: true, scaleanchor: 'y' },
                    yaxis: { range: [-200, 1000], showgrid: false, zeroline: false, showticklabels: false, fixedrange: true },
                    paper_bgcolor: 'transparent', plot_bgcolor: '#0E1117',
                    margin: { l: 10, r: 10, t: 35, b: 10 },
                    legend: { orientation: 'h', y: 1.05, x: 0.5, xanchor: 'center', font: { color: '#9ca3af' } },
                    title: { text: `${teamName} — ${teamShots.length} Attempts | ${fgPct}% FG`, font: { color: '#9ca3af', size: 14 }, x: 0.5 },
                    dragmode: false,
                }, { displayModeBar: false, staticPlot: false });
            }

            renderShotChart(ta);

            const btnTa = document.getElementById('btn-shots-ta');
            const btnTb = document.getElementById('btn-shots-tb');
            btnTa.textContent = taName;
            btnTb.textContent = tbName;
            btnTa.onclick = () => { btnTa.classList.add('active'); btnTb.classList.remove('active'); renderShotChart(ta); };
            btnTb.onclick = () => { btnTb.classList.add('active'); btnTa.classList.remove('active'); renderShotChart(tb); };
        } else {
            if (shotChartCard) shotChartCard.style.display = 'none';
        }

        // 8. Advanced Box Score
        if (data.adv.b && data.adv.b.length > 0) {
            const boxData = data.adv.b;

            function renderBoxScore(teamCode) {
                const teamPlayers = boxData.filter(p => p.t === teamCode);
                const pct = (m, a) => a > 0 ? (m / a * 100).toFixed(1) : '-';
                const maxPts = Math.max(...teamPlayers.map(p => p.pts));

                let html = `<table class="box-score-table">
                    <thead><tr>
                        <th>Player</th><th>PTS</th><th>REB</th><th>AST</th>
                        <th>STL</th><th>BLK</th><th>TO</th>
                        <th>FG%</th><th>3P%</th><th>FT%</th><th>PIR</th>
                    </tr></thead><tbody>`;

                teamPlayers.forEach(p => {
                    const ptsCls = p.pts === maxPts && p.pts > 0 ? ' class="highlight-pts"' : '';
                    const pir = p.pts + p.reb + p.ast + p.stl + p.blk - p.to
                        - (p.fga - p.fgm) - Math.round((p.fta - p.ftm) * 0.5);
                    const pirCls = pir >= 15 ? ' style="color:var(--accent-green);font-weight:700"'
                        : pir < 0 ? ' style="color:var(--accent-red)"' : '';
                    html += `<tr>
                        <td>${p.n}</td>
                        <td${ptsCls}>${p.pts}</td>
                        <td>${p.reb}</td><td>${p.ast}</td>
                        <td>${p.stl}</td><td>${p.blk}</td><td>${p.to}</td>
                        <td>${pct(p.fgm, p.fga)} <span style="color:var(--text-muted);font-size:0.7rem">(${p.fgm}/${p.fga})</span></td>
                        <td>${pct(p.fg3m, p.fg3a)} <span style="color:var(--text-muted);font-size:0.7rem">(${p.fg3m}/${p.fg3a})</span></td>
                        <td>${pct(p.ftm, p.fta)} <span style="color:var(--text-muted);font-size:0.7rem">(${p.ftm}/${p.fta})</span></td>
                        <td${pirCls}>${pir}</td>
                    </tr>`;
                });

                const totals = teamPlayers.reduce((acc, p) => {
                    acc.pts += p.pts; acc.reb += p.reb; acc.ast += p.ast;
                    acc.stl += p.stl; acc.blk += p.blk; acc.to += p.to;
                    acc.fgm += p.fgm; acc.fga += p.fga; acc.fg3m += p.fg3m;
                    acc.fg3a += p.fg3a; acc.ftm += p.ftm; acc.fta += p.fta;
                    return acc;
                }, { pts: 0, reb: 0, ast: 0, stl: 0, blk: 0, to: 0, fgm: 0, fga: 0, fg3m: 0, fg3a: 0, ftm: 0, fta: 0 });

                const teamPIR = teamPlayers.reduce((sum, p) =>
                    sum + p.pts + p.reb + p.ast + p.stl + p.blk - p.to - (p.fga - p.fgm) - Math.round((p.fta - p.ftm) * 0.5), 0);

                html += `<tr style="border-top: 2px solid var(--border); font-weight: 700;">
                    <td>TOTAL</td>
                    <td>${totals.pts}</td><td>${totals.reb}</td><td>${totals.ast}</td>
                    <td>${totals.stl}</td><td>${totals.blk}</td><td>${totals.to}</td>
                    <td>${pct(totals.fgm, totals.fga)}</td>
                    <td>${pct(totals.fg3m, totals.fg3a)}</td>
                    <td>${pct(totals.ftm, totals.fta)}</td>
                    <td>${teamPIR}</td>
                </tr>`;
                html += '</tbody></table>';
                document.getElementById('box-score-container').innerHTML = html;
            }

            renderBoxScore(ta);

            const btnBoxTa = document.getElementById('btn-box-ta');
            const btnBoxTb = document.getElementById('btn-box-tb');
            btnBoxTa.textContent = taName;
            btnBoxTb.textContent = tbName;
            btnBoxTa.onclick = () => { btnBoxTa.classList.add('active'); btnBoxTb.classList.remove('active'); renderBoxScore(ta); };
            btnBoxTb.onclick = () => { btnBoxTb.classList.add('active'); btnBoxTa.classList.remove('active'); renderBoxScore(tb); };
        }

    } else {
        advStatsSection.classList.add('hidden');
    }
}

// ── Reset ────────────────────────────────────────────────
function resetDownstream() {
    currentGames = [];
    _gc = null;
    teamFilter.innerHTML = '<option value="">All Teams</option>';
    teamFilter.disabled = true;
    gameSelect.innerHTML = '<option value="">Select a season first</option>';
    gameSelect.disabled = true;
    placeholder.classList.remove('hidden');
    keyPlaysSection.classList.add('hidden');
    gameSummary.classList.add('hidden');
    document.getElementById('adv-stats').classList.add('hidden');
    document.getElementById('chart-mode-toggle').style.display = 'none';
    Plotly.purge(chartDiv);
}

// ── Go ───────────────────────────────────────────────────
init();
