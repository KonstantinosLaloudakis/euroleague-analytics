/**
 * pace.js — Pace page
 * Headline cards, league trend, team dumbbell (raw / adjusted), regular season vs
 * playoffs, pace vs winning, slowest and fastest games. All figures come from
 * data/current/pace.json; no number in the copy is hardcoded.
 */
'use strict';

const PHASE_NAMES = { RS: 'Regular season', TS: 'Top 16', PO: 'Playoffs', FF: 'Final Four', PI: 'Play-in' };
const EARLY_ROUND = 10;
const GREY = '#6b7280';
const GOLD = '#f59e0b';

let _pace = null;
let _latest = null;
let _mode = 'raw';

document.addEventListener('DOMContentLoaded', () => {
    fetchJSON('data/current/pace.json')
        .then(data => {
            _pace = data;
            _latest = PaceCore.latestSeason(data.teams);
            if (_latest === null || !data.league.length) throw new Error('pace.json has no data');
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('content').classList.remove('hidden');
            setTitle();
            renderCards();
            renderTrend();
            initTeams();
            renderPlayoffs();
            renderWinning();
            renderExtremes();
        })
        .catch(err => {
            console.error('Failed to load pace data:', err);
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('load-error').classList.remove('hidden');
        });
});

/* ── Helpers ───────────────────────────────────────────────────────────── */
function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function teamName(code) { return TEAM_NAMES[code] || code; }
function f1(v) { return v.toFixed(1); }
function signed(v, d) { return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d); }
function leagueRow(season) { return _pace.league.find(r => r.season === season) || null; }
function setHTML(id, html) { document.getElementById(id).innerHTML = html; }
function median(arr) {
    const a = [...arr].sort((x, y) => x - y);
    const n = a.length;
    if (!n) return null;
    return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2;
}
function plural(n, one, many) { return n === 1 ? one : many; }

function layoutBase(extra) {
    const base = JSON.parse(JSON.stringify(PLOTLY_THEME));
    return Object.assign(base, extra || {});
}

/* Pace of the seasons before the current climb began. */
function priorBand() {
    const { base, streak } = PaceCore.paceStreak(_pace.league);
    if (!base || streak < 3) return null;
    const rows = _pace.league.filter(r => r.season <= base.season);
    if (!rows.length) return null;
    const paces = rows.map(r => r.pace);
    return { rows, min: Math.min(...paces), max: Math.max(...paces), base };
}

/* ── 1. Header and cards ───────────────────────────────────────────────── */
function setTitle() {
    const lg = _pace.league;
    const cur = leagueRow(_latest);
    const faster = cur && lg.every(r => r.pace <= cur.pace);
    setHTML('pace-title', faster ? 'Euroleague is playing faster than ever' : 'Euroleague pace, season by season');
}

function renderCards() {
    const lbl = seasonLabel(_latest);
    const cur = leagueRow(_latest);
    const prev = leagueRow(_latest - 1);
    const st = PaceCore.paceStreak(_pace.league);
    const band = priorBand();

    let lede = '';
    if (cur) lede = `Teams average <strong>${f1(cur.pace)}</strong> possessions per 40 minutes in ${esc(lbl)}.`;
    if (band) {
        lede += ` For ${band.rows.length} seasons the league sat between <strong>${f1(band.min)}</strong> and <strong>${f1(band.max)}</strong>.`;
    }
    setHTML('pace-lede', lede);

    const cards = [];
    if (cur) {
        const delta = prev ? cur.pace - prev.pace : null;
        const deltaTxt = delta === null ? 'First season on record'
            : `${signed(delta, 1)} vs ${esc(prev.season_label)}`;
        const through = cur.last_round ? ` · through round ${cur.last_round}` : '';
        cards.push({ label: `League pace, ${esc(lbl)}`, value: f1(cur.pace), sub: deltaTxt + through });
    }
    if (st.latest) {
        cards.push({
            label: 'Seasons in a row pace has risen',
            value: String(st.streak),
            sub: st.streak > 0 ? `Up from ${f1(st.base.pace)} in ${esc(st.base.season_label)}` : 'Pace did not rise last season',
        });
    }
    const rows = PaceCore.seasonTeams(_pace.teams, _latest, 'pace');
    if (rows.length) {
        const slow = rows[rows.length - 1];
        cards.push({
            label: `Slowest team, ${esc(lbl)}`,
            value: esc(teamName(slow.team)),
            sub: `${f1(slow.pace)} possessions per 40 · ${slow.gp} ${plural(slow.gp, 'game', 'games')}`,
        });
    }
    setHTML('hero-grid', cards.map(c => `<div class="hero-card">
        <div class="hero-card-label">${c.label}</div>
        <div class="hero-card-value" ${c.value.length > 12 ? 'style="font-size:1.4rem;padding:0.35rem 0"' : ''}>${c.value}</div>
        <div class="hero-card-sub">${c.sub}</div></div>`).join(''));
}

/* ── 2. League trend ───────────────────────────────────────────────────── */
function renderTrend() {
    const lg = [..._pace.league].sort((a, b) => a.season - b.season);
    const band = priorBand();
    const st = PaceCore.paceStreak(_pace.league);
    const xs = lg.map(r => r.season_label);
    const ys = lg.map(r => r.pace);
    const last = lg.length - 1;

    const first = lg[0];
    const lastRow = lg[last];
    setHTML('trend-title', band
        ? `${band.rows.length} flat seasons, then a ${st.streak}-${plural(st.streak, 'season', 'season')} climb`
        : 'League pace by season');
    setHTML('trend-note', band
        ? `The shaded band is the range of the pre-climb seasons (${esc(first.season_label)} to ${esc(band.base.season_label)}), ${f1(band.min)} to ${f1(band.max)}. Pace is possessions per team per 40 minutes, regular season only.`
        : 'Possessions per team per 40 minutes, regular season only.');

    const shapes = [];
    if (band) {
        const baseIdx = lg.findIndex(r => r.season === band.base.season);
        shapes.push({
            type: 'rect', xref: 'x', yref: 'y',
            x0: -0.5, x1: baseIdx + 0.5, y0: band.min, y1: band.max,
            fillcolor: 'rgba(168,85,247,0.15)', line: { width: 0 }, layer: 'below',
        });
    }
    const text = ys.map((v, i) => (i === last ? f1(v) : ''));
    const trace = {
        x: xs, y: ys, type: 'scatter', mode: 'lines+markers+text',
        line: { color: '#a855f7', width: 2.5 }, marker: { size: 6, color: '#a855f7' },
        text, textposition: 'top left', textfont: { color: '#f0f0f5', size: 13 },
        customdata: lg.map(r => r.games),
        hovertemplate: '<b>%{x}</b><br>Pace %{y:.1f}<br>%{customdata} games<extra></extra>',
    };
    const lo = Math.min(...ys, band ? band.min : Infinity);
    const hi = Math.max(...ys);
    const layout = layoutBase({
        margin: { t: 20, r: 24, b: 56, l: 48 },
        shapes,
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, { tickangle: -45, type: 'category', automargin: true }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, { title: { text: 'Possessions per 40 min' }, range: [Math.floor(lo - 1), Math.ceil(hi + 1)] }),
        showlegend: false,
    });
    Plotly.newPlot('trend-chart', [trace], layout, PLOTLY_CONFIG);
}

/* ── 3. Team dumbbell ──────────────────────────────────────────────────── */
function initTeams() {
    const lbl = seasonLabel(_latest);
    setHTML('teams-title', `Every team, ${esc(lbl)} vs last season`);
    const cur = leagueRow(_latest);
    if (cur && cur.last_round != null && cur.last_round < EARLY_ROUND) {
        const el = document.getElementById('teams-early');
        el.textContent = `Early season: only ${cur.last_round} ${plural(cur.last_round, 'round', 'rounds')} played, so team rankings can still move a lot.`;
        el.classList.remove('hidden');
    }
    const set = mode => {
        _mode = mode;
        const raw = mode === 'raw';
        document.getElementById('pace-mode-raw').classList.toggle('active', raw);
        document.getElementById('pace-mode-adj').classList.toggle('active', !raw);
        document.getElementById('pace-mode-raw').setAttribute('aria-pressed', String(raw));
        document.getElementById('pace-mode-adj').setAttribute('aria-pressed', String(!raw));
        renderTeams();
    };
    document.getElementById('pace-mode-raw').addEventListener('click', () => set('raw'));
    document.getElementById('pace-mode-adj').addEventListener('click', () => set('adj'));
    renderTeams();
}

function renderTeams() {
    const raw = _mode === 'raw';
    const metric = raw ? 'pace' : 'adj_rel';
    const rows = PaceCore.seasonTeams(_pace.teams, _latest, metric);
    const cur = leagueRow(_latest);
    const small = window.innerWidth < 640;
    const label = r => (small ? r.team : teamName(r.team));
    const cats = rows.map(label);

    setHTML('teams-note', raw
        ? 'Possessions per 40 minutes. Filled dot is this season, hollow dot is last season. Teams are ordered fastest to slowest.'
        : 'Adjusted pace is how much faster or slower a team\'s games run than its opponents\' usual pace, which corrects for who a team has played so far. 0 means an average game for that schedule.');

    // Connectors: one trace, gaps between teams.
    const lx = [], ly = [];
    rows.forEach(r => {
        if (r.prev !== null) { lx.push(r.prev, r[metric], null); ly.push(label(r), label(r), null); }
    });
    const connectors = { x: lx, y: ly, type: 'scatter', mode: 'lines', line: { color: '#4b5563', width: 2 }, hoverinfo: 'skip', showlegend: false };

    const withPrev = rows.filter(r => r.prev !== null);
    const prevTrace = {
        x: withPrev.map(r => r.prev), y: withPrev.map(label), type: 'scatter', mode: 'markers',
        marker: { size: 10, color: 'rgba(0,0,0,0)', line: { color: '#9ca3af', width: 2 } },
        hoverinfo: 'skip', name: 'Last season', showlegend: false,
    };

    const dec = raw ? 1 : 2;
    const hover = rows.map(r => {
        const rank = raw ? r.rank : r.adj_rank;
        const pre = raw ? '' : `Adjusted ${signed(r.adj_rel, 2)}<br>`;
        return `<b>${esc(teamName(r.team))}</b><br>` + pre
            + `Pace ${f1(r.pace)}<br>`
            + (r.prev !== null ? `Last season ${raw ? f1(r.prev) : signed(r.prev, 2)}<br>` : 'No games last season<br>')
            + `${raw ? 'Pace' : 'Adjusted'} rank ${rank} of ${r.teams} (1 = fastest)<br>`
            + `${r.wins}–${r.gp - r.wins} · net ${signed(r.net, 1)}`
            + (CAN_HOVER ? '<br><i>Click for team page</i>' : '');
    });
    const curTrace = {
        x: rows.map(r => r[metric]), y: cats, type: 'scatter', mode: 'markers',
        marker: { size: 12, color: rows.map(r => teamInk(r.team)), line: { color: '#0f1117', width: 1 } },
        text: hover, hovertemplate: '%{text}<extra></extra>', showlegend: false,
        customdata: rows.map(r => r.team),
    };

    const refX = raw ? (cur ? cur.pace : 0) : 0;
    const all = rows.flatMap(r => (r.prev !== null ? [r[metric], r.prev] : [r[metric]])).concat([refX]);
    const pad = raw ? 0.6 : 0.3;
    const layout = layoutBase({
        margin: { t: 34, r: 20, b: 52, l: small ? 44 : 150 },
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, {
            title: { text: raw ? 'Possessions per 40 min' : 'Faster (+) or slower (−) than opponents\' usual pace' },
            range: [Math.min(...all) - pad, Math.max(...all) + pad],
            tickformat: raw ? '.0f' : '+.1f',
        }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, { type: 'category', categoryorder: 'array', categoryarray: cats, autorange: 'reversed', showgrid: false, automargin: true, tickfont: { size: small ? 11 : 12 } }),
        shapes: [{ type: 'line', xref: 'x', yref: 'paper', x0: refX, x1: refX, y0: 0, y1: 1, line: { color: '#e5e7eb', width: 1, dash: 'dot' } }],
        annotations: [{ xref: 'x', yref: 'paper', x: refX, y: 1, yanchor: 'bottom', showarrow: false, font: { size: 11, color: '#e5e7eb' }, text: raw ? `League ${f1(refX)}` : 'Average schedule' }],
        showlegend: false,
        hovermode: 'closest',
    });
    Plotly.react('teams-chart', [connectors, prevTrace, curTrace], layout, PLOTLY_CONFIG);
    bindTeamChartClicks();
}

// Mouse users click a team's dot to open Team Deep-Dive. On touch screens a tap only shows the
// tooltip (navigating on the first tap would hide it before it can be read).
const CAN_HOVER = window.matchMedia('(hover: hover)').matches;
let _teamClicksBound = false;
function bindTeamChartClicks() {
    if (_teamClicksBound || !CAN_HOVER) return;   // Plotly.react keeps handlers; bind once
    const el = document.getElementById('teams-chart');
    const drag = () => el.querySelector('.nsewdrag');
    el.on('plotly_click', ev => {
        const code = ev.points && ev.points[0] && ev.points[0].customdata;
        if (code) location.href = 'team.html?team=' + encodeURIComponent(code);
    });
    el.on('plotly_hover', ev => { const d = drag(); if (d) d.style.cursor = ev.points[0].customdata ? 'pointer' : ''; });
    el.on('plotly_unhover', () => { const d = drag(); if (d) d.style.cursor = ''; });
    _teamClicksBound = true;
}

/* ── 4. Regular season vs playoffs ─────────────────────────────────────── */
function renderPlayoffs() {
    const rows = _pace.playoffs.filter(r => r.regular != null && r.playoffs != null).sort((a, b) => a.season - b.season);
    if (!rows.length) { setHTML('playoffs-note', 'No playoff games on record yet.'); return; }
    const slower = rows.filter(r => r.playoffs < r.regular);
    const gap = slower.length ? slower.reduce((s, r) => s + (r.regular - r.playoffs), 0) / slower.length : 0;
    setHTML('playoffs-note', `Playoff series were slower than the regular season in <strong>${slower.length} of ${rows.length}</strong> seasons`
        + (slower.length ? `, by an average of <strong>${gap.toFixed(1)}</strong> possessions per 40 minutes in those seasons.` : '.')
        + ' The Final Four and play-in games are not counted as playoffs here.');

    const xs = rows.map(r => r.season_label);
    const lx = [], ly = [];
    rows.forEach(r => { lx.push(r.season_label, r.season_label, null); ly.push(r.regular, r.playoffs, null); });
    const traces = [
        { x: lx, y: ly, type: 'scatter', mode: 'lines', line: { color: '#4b5563', width: 2 }, hoverinfo: 'skip', showlegend: false },
        {
            x: xs, y: rows.map(r => r.regular), type: 'scatter', mode: 'markers', name: 'Regular season',
            marker: { size: 9, color: '#a855f7' },
            hovertemplate: '<b>%{x}</b><br>Regular season %{y:.1f}<extra></extra>',
        },
        {
            x: xs, y: rows.map(r => r.playoffs), type: 'scatter', mode: 'markers', name: 'Playoff series',
            marker: { size: 9, color: GOLD },
            customdata: rows.map(r => r.diff),
            hovertemplate: '<b>%{x}</b><br>Playoff series %{y:.1f}<br>Difference %{customdata:+.1f}<extra></extra>',
        },
    ];
    const ys = rows.flatMap(r => [r.regular, r.playoffs]);
    const layout = layoutBase({
        margin: { t: 20, r: 24, b: 56, l: 48 },
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, { type: 'category', tickangle: -45, automargin: true }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, { title: { text: 'Possessions per 40 min' }, range: [Math.floor(Math.min(...ys) - 1), Math.ceil(Math.max(...ys) + 1)] }),
        legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: 1.1, font: { color: '#9ca3af' } },
        hovermode: 'closest',
    });
    Plotly.newPlot('playoffs-chart', traces, layout, PLOTLY_CONFIG);
}

/* ── 5. Pace vs winning ────────────────────────────────────────────────── */
function renderWinning() {
    const champSeasons = new Set(_pace.teams.filter(r => r.champion).map(r => r.season));
    const done = _pace.teams.filter(r => r.season < _latest || champSeasons.has(r.season));
    if (!done.length) { setHTML('winning-note', 'Needs at least one completed season.'); return; }
    const champs = done.filter(r => r.champion);
    const others = done.filter(r => !r.champion);
    const slowChamps = champs.filter(r => r.pace_rel < 0);
    const med = median(champs.map(r => r.rank));
    setHTML('winning-note', champs.length
        ? `Of the last ${champs.length} champions, <strong>${slowChamps.length}</strong> played slower than the league average. The median champion ranked <strong>${med % 1 ? med.toFixed(1) : med}</strong> on pace in its season (1 = fastest).`
        : 'Champions are marked once a season has completed.');

    const hov = r => `<b>${esc(teamName(r.team))}</b> ${esc(seasonLabel(r.season))}<br>Pace ${f1(r.pace)} (${signed(r.pace_rel, 1)} vs league)<br>Pace rank ${r.rank} of ${r.teams}<br>Net rating ${signed(r.net, 1)}`;
    const traces = [
        {
            x: others.map(r => r.pace_rel), y: others.map(r => r.net), type: 'scatter', mode: 'markers', name: 'Team season',
            marker: { size: 7, color: 'rgba(156,163,175,0.45)' },
            text: others.map(hov), hovertemplate: '%{text}<extra></extra>',
        },
        {
            x: champs.map(r => r.pace_rel), y: champs.map(r => r.net), type: 'scatter', mode: 'markers', name: 'Champion',
            marker: { size: 11, color: GOLD, line: { color: '#0f1117', width: 1 } },
            text: champs.map(r => '🏆 ' + hov(r)), hovertemplate: '%{text}<extra></extra>',
        },
    ];
    const layout = layoutBase({
        margin: { t: 20, r: 24, b: 56, l: 52 },
        // Shorter title on phones: the full one is wider than the plot and gets clipped.
        xaxis: Object.assign({}, PLOTLY_THEME.xaxis, { title: { text: window.innerWidth < 640 ? 'Pace vs league avg (per 40)' : 'Pace vs league average (possessions per 40)' }, zeroline: true, zerolinecolor: '#4b5563', tickformat: '+.0f' }),
        yaxis: Object.assign({}, PLOTLY_THEME.yaxis, { title: { text: 'Net rating (per 100 possessions)' }, zeroline: true, zerolinecolor: '#4b5563' }),
        legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: 1.1, font: { color: '#9ca3af' } },
        hovermode: 'closest',
    });
    Plotly.newPlot('winning-chart', traces, layout, PLOTLY_CONFIG);
}

/* ── 6. Extremes ───────────────────────────────────────────────────────── */
function gameCell(r) {
    const sep = '–';
    const label = `${esc(r.home)} ${r.home_pts}${sep}${r.away_pts} ${esc(r.away)}`;
    const title = esc(`${teamName(r.home)} vs ${teamName(r.away)}`);
    // Full club names under the score: the codes (CSK, LJU…) mean little to most readers and the
    // title tooltip doesn't work on phones.
    const names = `<span class="stage">${title}</span>`;
    return (r.has_replay
        ? `<a href="replay.html?season=${r.season}&game=${r.gamecode}" title="${title} · open replay">${label}</a>`
        : `<span title="${title}">${label}</span>`) + names;
}

function extremesTable(title, rows) {
    const body = (rows || []).map(r => `<tr>
        <td>${esc(r.season_label)}<span class="stage">${esc(PHASE_NAMES[r.phase] || r.phase || '')}</span></td>
        <td class="game">${gameCell(r)}</td>
        <td class="num">${f1(r.pace40)}</td>
        <td class="num">${f1(r.poss)}</td>
        <td class="num">${r.ot ? (r.ot > 1 ? r.ot + 'OT' : 'OT') : ''}</td></tr>`).join('');
    return `<div class="table-wrap"><h4>${title}</h4><table class="pace-table">
        <thead><tr><th>Season</th><th>Game</th><th class="num">Per 40</th><th class="num">Poss.</th><th class="num">OT</th></tr></thead>
        <tbody>${body}</tbody></table></div>`;
}

function renderExtremes() {
    const ex = _pace.extremes || {};
    setHTML('extremes-grid', extremesTable('Slowest games', ex.slowest) + extremesTable('Fastest games', ex.fastest));
}

/* Re-fit the dumbbell labels when crossing the mobile breakpoint. */
let _wasSmall = window.innerWidth < 640;
window.addEventListener('resize', () => {
    const small = window.innerWidth < 640;
    if (small !== _wasSmall && _pace) { _wasSmall = small; renderTeams(); }
});
