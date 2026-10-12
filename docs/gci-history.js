/**
 * gci-history.js — GCI History page
 * Hero trend cards, team comparison chart, era breakdown, historical superlatives
 */
'use strict';

/* ── Global state ──────────────────────────────────────────────────────── */
let _hist = null;          // merged historical data
let _activePills = new Set();
let _activeMetric = 'gci';

/* ── Legacy teams shown by default ────────────────────────────────────── */
const LEGACY_TEAMS = ['OLY', 'BAR', 'MAD', 'PAN', 'TEL', 'IST', 'ULK', 'BAS', 'MIL', 'ZAL'];

/* ── Boot ──────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    Promise.all([
        fetchJSON('gci_historical.json'),
        fetchJSON('data/current/dashboard.json'),
    ])
        .then(([hist, dashboard]) => {
            _hist = mergeCurrentSeason(hist, dashboard);
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('content').classList.remove('hidden');
            renderHero();
            initTeamPills();
            renderComparison();
            renderEras();
            renderSuperlatives();
        })
        .catch(err => {
            console.error('Failed to load GCI history:', err);
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('load-error').classList.remove('hidden');
        });
});

/* ── Merge live-season data from dashboard.json into historical ──────────────── */
function mergeCurrentSeason(hist, dashboard) {
    const yr = dashboardSeason(dashboard);
    // Historical file may already include the live season (guards double counting)
    if (hist.league_trends.seasons.includes(yr)) return hist;
    const gc = dashboard.game_control || {};
    // No live-season data yet (early season): don't add an all-zero point
    if (!Object.keys(gc.teams || {}).length) return hist;
    const teamsStandings = dashboard.teams || [];  // array with win_pct

    // Build win_pct lookup from standings array
    const winPctMap = {};
    if (Array.isArray(teamsStandings)) {
        teamsStandings.forEach(t => {
            if (t.team) winPctMap[t.team] = (t.win_pct || 0) / 100;
        });
    }

    // Append live season to league_trends
    const gcTeams = gc.teams || {};
    const gcArr = Object.values(gcTeams);
    const avg_drama_cur = gcArr.length
        ? gcArr.reduce((s, t) => s + (t.drama_avg || 0), 0) / gcArr.length
        : 0;
    const comeback_count_cur = gcArr.reduce((s, t) => s + (t.comeback_count || 0), 0);
    const gcis = gcArr.map(t => t.gci || 0).filter(v => v > 0);
    const avg_gci_spread_cur = gcis.length > 1
        ? Math.max(...gcis) - Math.min(...gcis)
        : 0;
    const game_count_cur = gcArr.length > 0
        ? Math.max(...gcArr.map(t => (t.game_log || []).length))
        : 0;

    hist.league_trends.seasons.push(yr);
    hist.league_trends.avg_drama.push(parseFloat(avg_drama_cur.toFixed(4)));
    hist.league_trends.comeback_count.push(comeback_count_cur);
    hist.league_trends.avg_gci_spread.push(parseFloat(avg_gci_spread_cur.toFixed(1)));
    hist.league_trends.game_count.push(game_count_cur);

    // Append live season to each team's trend if they exist in the current season
    Object.entries(gcTeams).forEach(([code, t]) => {
        const winPct = winPctMap[code] !== undefined ? winPctMap[code] : null;
        if (hist.team_trends[code]) {
            hist.team_trends[code].seasons.push(yr);
            hist.team_trends[code].gci.push(parseFloat((t.gci || 0).toFixed(1)));
            hist.team_trends[code].win_pct.push(winPct !== null ? parseFloat(winPct.toFixed(4)) : null);
            hist.team_trends[code].avg_drama.push(parseFloat((t.drama_avg || 0).toFixed(4)));
            hist.team_trends[code].dominance_avg.push(parseFloat((t.dominance_avg || 0).toFixed(4)));
            hist.team_trends[code].killer_instinct.push(parseFloat((t.killer_instinct || 0).toFixed(4)));
            hist.team_trends[code].comeback_count.push(t.comeback_count || 0);
        } else {
            // New team not in historical data
            hist.team_trends[code] = {
                seasons: [yr],
                gci: [parseFloat((t.gci || 0).toFixed(1))],
                win_pct: [winPct !== null ? parseFloat(winPct.toFixed(4)) : null],
                avg_drama: [parseFloat((t.drama_avg || 0).toFixed(4))],
                dominance_avg: [parseFloat((t.dominance_avg || 0).toFixed(4))],
                killer_instinct: [parseFloat((t.killer_instinct || 0).toFixed(4))],
                comeback_count: [t.comeback_count || 0],
            };
        }
    });

    // Update total games
    hist.total_games = (hist.total_games || 0) + game_count_cur;

    // Update era: extend Modern Era end to the live season
    const modernEra = hist.eras.find(e => e.name === 'Modern Era');
    if (modernEra) {
        modernEra.end = yr;
        modernEra.seasons_included = (modernEra.seasons_included || 5) + 1;
        modernEra.total_games = (modernEra.total_games || 0) + game_count_cur;
        // Recompute avg drama for modern era
        const modernSeasons = hist.league_trends.seasons
            .map((y, i) => ({ year: y, drama: hist.league_trends.avg_drama[i] }))
            .filter(s => s.year >= modernEra.start && s.year <= yr);
        if (modernSeasons.length) {
            modernEra.avg_drama = modernSeasons.reduce((s, x) => s + x.drama, 0) / modernSeasons.length;
        }
    }

    return hist;
}

/* ── Section 1: Hero Cards ─────────────────────────────────────────────── */
function renderHero() {
    const lt = _hist.league_trends;
    const seasons = lt.seasons;
    const n = seasons.length;

    const metrics = [
        {
            label: 'Avg Drama Index',
            data: lt.avg_drama,
            color: '#e74c3c',
            format: v => v.toFixed(2),
            unit: '',
        },
        {
            label: 'Comebacks per Season',
            data: lt.comeback_count,
            color: '#f1c40f',
            format: v => Math.round(v),
            unit: '',
        },
        {
            label: 'GCI Spread',
            data: lt.avg_gci_spread,
            color: '#2ecc71',
            format: v => v.toFixed(1),
            unit: '',
        },
    ];

    const container = document.getElementById('hero-cards');
    container.innerHTML = metrics.map(m => {
        const first = m.data[0];
        const last = m.data[n - 1];
        const pctChange = first !== 0 ? ((last - first) / first) * 100 : 0;
        const sign = pctChange >= 0 ? '+' : '';
        const bigVal = `${sign}${pctChange.toFixed(0)}%`;
        const sub = `${m.format(first)} (${seasonLabel(seasons[0])}) → ${m.format(last)} (${seasonLabel(seasons[n - 1])})`;
        const sparkSvg = buildSparkline(m.data, m.color, 200, 40);

        return `<div class="hero-card">
            <div class="hero-card-label">${m.label}</div>
            <div class="hero-card-value" style="color:${m.color}">${bigVal}</div>
            <div class="hero-card-sub">${sub}</div>
            ${sparkSvg}
        </div>`;
    }).join('');

    // Summary banner
    document.getElementById('hero-banner').innerHTML =
        `<strong>${_hist.league_trends.seasons.length} Seasons · ${_hist.total_games.toLocaleString()}+ Games · Every Play Analyzed</strong>`;
}

/* ── Sparkline SVG ─────────────────────────────────────────────────────── */
function buildSparkline(data, color, w, h) {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const step = w / (data.length - 1);
    const pts = data.map((v, i) =>
        `${(i * step).toFixed(1)},${(h - ((v - min) / range) * (h * 0.85) - h * 0.075).toFixed(1)}`
    ).join(' ');

    return `<svg class="hero-sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
        <circle cx="${((data.length - 1) * step).toFixed(1)}" cy="${(h - ((data[data.length - 1] - min) / range) * (h * 0.85) - h * 0.075).toFixed(1)}" r="3" fill="${color}"/>
    </svg>`;
}

/* ── Section 2: Team Comparison ────────────────────────────────────────── */
function initTeamPills() {
    const allTeams = Object.keys(_hist.team_trends).sort((a, b) => {
        const na = TEAM_NAMES[a] || a;
        const nb = TEAM_NAMES[b] || b;
        return na.localeCompare(nb);
    });

    // Default selection: 5 legacy teams with distinct trajectories
    const DEFAULT_SELECTED = ['OLY', 'BAR', 'MAD', 'PAN', 'ULK'];
    DEFAULT_SELECTED.forEach(code => {
        if (_hist.team_trends[code]) _activePills.add(code);
    });

    const pillRow = document.getElementById('pill-row');
    let showAllVisible = false;

    function buildPills() {
        pillRow.innerHTML = '';
        allTeams.forEach(code => {
            const isLegacy = LEGACY_TEAMS.includes(code);
            const isActive = _activePills.has(code);
            const color = teamInk(code);
            const name = TEAM_NAMES[code] || code;
            const hidden = !isLegacy && !showAllVisible && !isActive ? ' hidden-pill' : '';

            const pill = document.createElement('button');
            pill.className = `team-pill${isActive ? ' active' : ''}${hidden}`;
            pill.setAttribute('data-code', code);
            if (isActive) {
                pill.style.color = color;
                pill.style.borderColor = color;
                pill.style.background = `${color}18`;
            }
            pill.textContent = name;
            pill.title = code;
            pill.onclick = () => togglePill(code);
            pillRow.appendChild(pill);
        });

        // Show more / Show less button
        const showBtn = document.createElement('button');
        showBtn.className = 'pill-showmore';
        showBtn.textContent = showAllVisible ? 'Show less' : `+${allTeams.length - LEGACY_TEAMS.length} more`;
        showBtn.onclick = () => {
            showAllVisible = !showAllVisible;
            buildPills();
        };
        pillRow.appendChild(showBtn);
    }

    buildPills();

    // Store rebuild function for use in togglePill
    window._rebuildPills = buildPills;
}

function togglePill(code) {
    if (_activePills.has(code)) {
        if (_activePills.size <= 1) return; // must have at least 1
        _activePills.delete(code);
    } else {
        if (_activePills.size >= 8) return; // max 8
        _activePills.add(code);
    }
    if (window._rebuildPills) window._rebuildPills();
    renderComparison();
}

function onMetricChange() {
    _activeMetric = document.getElementById('metric-select').value;
    renderComparison();
}

function renderComparison() {
    const metricKey = _activeMetric;
    const metricLabels = {
        gci: 'GCI Rating',
        avg_drama: 'Drama Index',
        dominance_avg: 'Dominance Score',
        killer_instinct: 'Killer Instinct',
        comeback_count: 'Comebacks',
        win_pct: 'Win %',
    };
    const yLabel = metricLabels[metricKey] || metricKey;

    const traces = [];

    _activePills.forEach(code => {
        const td = _hist.team_trends[code];
        if (!td) return;

        const color = teamInk(code);
        const name = TEAM_NAMES[code] || code;

        let rawVals = td[metricKey] || [];
        let yVals;
        if (metricKey === 'win_pct') {
            yVals = rawVals.map(v => v !== null && v !== undefined ? parseFloat((v * 100).toFixed(1)) : null);
        } else {
            yVals = rawVals.map(v => v !== null && v !== undefined ? v : null);
        }
        const xVals = td.seasons.map(seasonLabel);

        const hoverFmt = metricKey === 'comeback_count' ? '%{y:.0f}' : '%{y:.2f}';
        traces.push({
            x: xVals,
            y: yVals,
            mode: 'lines+markers',
            type: 'scatter',
            name: name,
            line: { color, width: 2 },
            marker: { color, size: 6 },
            connectgaps: false,
            hovertemplate: `<b>${name}</b><br>%{x}<br>${yLabel}: ${hoverFmt}<extra></extra>`,
        });
    });

    const yAxisTitle = metricKey === 'win_pct' ? 'Win %' : yLabel;

    const layout = Object.assign({}, PLOTLY_THEME, {
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, {
            title: '',
            type: 'category',
            tickangle: -35,
            automargin: true,
        }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, {
            title: yAxisTitle,
        }),
        margin: { t: 20, r: 20, b: 60, l: 55 },
        legend: {
            orientation: 'h',
            y: -0.18,
            font: { size: 11, color: '#9ca3af' },
            bgcolor: 'transparent',
        },
        hovermode: 'closest',
    });

    Plotly.react('comparison-chart', traces, layout, PLOTLY_CONFIG);
}

/* ── Section 3: Era Breakdown ──────────────────────────────────────────── */
function renderEras() {
    const eras = _hist.eras;
    const ERA_COLORS = ['#4ecdc4', '#f1c40f', '#e74c3c'];

    const container = document.getElementById('era-grid');
    container.innerHTML = eras.map((era, i) => {
        const color = ERA_COLORS[i] || '#9ca3af';
        const comebackPct = ((era.avg_comeback_rate || 0) * 100).toFixed(1);
        const dramaPretty = (era.avg_drama || 0).toFixed(2);
        const years = `${era.start}–${era.end}`;

        return `<div class="era-card" style="border-top-color:${color}">
            <div class="era-name" style="color:${color}">${era.name}</div>
            <div class="era-years">${years}</div>
            <div class="era-stat">
                <span class="era-stat-label">Total Games</span>
                <span class="era-stat-value">${(era.total_games || 0).toLocaleString()}</span>
            </div>
            <div class="era-stat">
                <span class="era-stat-label">Avg Drama Index</span>
                <span class="era-stat-value">${dramaPretty}</span>
            </div>
            <div class="era-stat">
                <span class="era-stat-label">Comeback Rate</span>
                <span class="era-stat-value">${comebackPct}%</span>
            </div>
            <div class="era-stat">
                <span class="era-stat-label">Seasons</span>
                <span class="era-stat-value">${era.seasons_included || '—'}</span>
            </div>
        </div>`;
    }).join('');
}

/* ── Section 4: Historical Superlatives ────────────────────────────────── */
function renderSuperlatives() {
    const s = _hist.superlatives;
    if (!s) {
        document.getElementById('superlatives').innerHTML =
            '<p style="color:var(--text-muted)">No superlatives available.</p>';
        return;
    }

    const cards = [
        {
            icon: '\u2B50',
            label: 'Most Dominant Season',
            color: '#4ecdc4',
            buildContent: () => {
                const d = s.highest_gci;
                if (!d) return null;
                const name = TEAM_NAMES[d.team] || d.team;
                const color = teamInk(d.team);
                return {
                    matchup: `<span style="color:${color}">${name}</span>`,
                    value: `GCI ${d.gci.toFixed(1)}`,
                    season: seasonLabel(d.season),
                    link: null,
                };
            },
        },
        {
            icon: '\u26A1',
            label: 'Most Dramatic Game',
            color: '#e74c3c',
            buildContent: () => {
                const d = s.most_dramatic;
                if (!d) return null;
                const homeColor = teamInk(d.home);
                const awayColor = teamInk(d.away);
                const homeName = TEAM_NAMES[d.home] || d.home;
                const awayName = TEAM_NAMES[d.away] || d.away;
                return {
                    matchup: `<span style="color:${homeColor}">${homeName}</span> ${d.home_score}–${d.away_score} <span style="color:${awayColor}">${awayName}</span>`,
                    value: `Drama ${d.drama.toFixed(2)}`,
                    season: seasonLabel(d.season),
                    link: `replay.html?season=${d.season}&game=${d.gamecode}`,
                };
            },
        },
        {
            icon: '\u21BB',
            label: 'Biggest Comeback',
            color: '#f1c40f',
            buildContent: () => {
                const d = s.biggest_comeback;
                if (!d) return null;
                const homeColor = teamInk(d.home);
                const awayColor = teamInk(d.away);
                const homeName = TEAM_NAMES[d.home] || d.home;
                const awayName = TEAM_NAMES[d.away] || d.away;
                const winnerName = TEAM_NAMES[d.winner] || d.winner;
                const fromPct = d.comeback !== undefined
                    ? `From ${((1 - d.comeback) * 100).toFixed(0)}% WP`
                    : '';
                return {
                    matchup: `<span style="color:${homeColor}">${homeName}</span> ${d.home_score}–${d.away_score} <span style="color:${awayColor}">${awayName}</span>`,
                    value: `${winnerName} wins · ${fromPct}`,
                    season: seasonLabel(d.season),
                    link: `replay.html?season=${d.season}&game=${d.gamecode}`,
                };
            },
        },
        {
            icon: '\uD83D\uDC51',
            label: 'Most Dominant Game',
            color: '#a855f7',
            buildContent: () => {
                const d = s.most_dominant;
                if (!d) return null;
                const homeColor = teamInk(d.home);
                const awayColor = teamInk(d.away);
                const homeName = TEAM_NAMES[d.home] || d.home;
                const awayName = TEAM_NAMES[d.away] || d.away;
                return {
                    matchup: `<span style="color:${homeColor}">${homeName}</span> ${d.home_score}–${d.away_score} <span style="color:${awayColor}">${awayName}</span>`,
                    value: `Dominance ${d.dominance.toFixed(3)}`,
                    season: seasonLabel(d.season),
                    link: `replay.html?season=${d.season}&game=${d.gamecode}`,
                };
            },
        },
    ];

    const container = document.getElementById('superlatives');
    container.innerHTML = cards.map(c => {
        const content = c.buildContent();
        if (!content) return '';

        const inner = `
            <div class="superlative-icon" style="color:${c.color}">${c.icon}</div>
            <div class="superlative-label">${c.label}</div>
            <div class="superlative-matchup">${content.matchup}</div>
            <div class="superlative-value" style="color:${c.color}">${content.value}</div>
            <div class="superlative-season">${content.season}</div>`;

        const cardBody = content.link
            ? `<a class="game-link" href="${content.link}">${inner}</a>`
            : inner;

        return `<div class="superlative-card" style="border-left-color:${c.color}">${cardBody}</div>`;
    }).join('');
}
