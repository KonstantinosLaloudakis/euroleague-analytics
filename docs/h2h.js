/* ── h2h.js — Head-to-Head Matchup Tool ─────────────────────────────────── */

let _data        = null;
let _playerStats = [];
let _backtest    = [];

// ── Boot ──────────────────────────────────────────────────────────────────
Promise.all([
    fetchJSON('data/current/dashboard.json'),
    fetchJSON('data/current/oracle_backtest_predictions.json'),
]).then(([data, backtest]) => {
    _data        = data;
    _playerStats = data.player_stats || [];
    _backtest    = backtest || [];

    if (data.updated) {
        const el = document.getElementById('last-updated');
        const d  = new Date(data.updated);
        el.textContent = `Updated ${d.toLocaleDateString('en-GB', {day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})} ${d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'})} UTC`;
        el.style.display = '';
    }

    populateDropdowns(data.teams || []);

    // Restore from URL params
    const params = new URLSearchParams(location.search);
    const a = params.get('a'), b = params.get('b');
    if (a) document.getElementById('sel-a').value = a;
    if (b) document.getElementById('sel-b').value = b;
    if (a && b) onSelectionChange();
}).catch(err => {
    document.getElementById('h2h-stat-bars').innerHTML =
        `<p style="color:var(--accent-red);padding:1rem">Failed to load data: ${err}</p>`;
});

// ── Dropdowns ─────────────────────────────────────────────────────────────
function populateDropdowns(teams) {
    const sorted = teams.slice().sort((a, b) =>
        (TEAM_NAMES[a.team] || a.team).localeCompare(TEAM_NAMES[b.team] || b.team)
    );
    const options = sorted.map(t =>
        `<option value="${t.team}">${TEAM_NAMES[t.team] || t.team} (${t.wins}-${t.losses})</option>`
    ).join('');

    document.getElementById('sel-a').innerHTML = '<option value="">— Choose —</option>' + options;
    document.getElementById('sel-b').innerHTML = '<option value="">— Choose —</option>' + options;
}

function onSelectionChange() {
    const a = document.getElementById('sel-a').value;
    const b = document.getElementById('sel-b').value;

    if (!a || !b || a === b) {
        document.getElementById('h2h-panel').style.display = 'none';
        return;
    }

    history.replaceState(null, '', `?a=${a}&b=${b}`);

    const teamA = (_data.teams || []).find(t => t.team === a);
    const teamB = (_data.teams || []).find(t => t.team === b);
    if (!teamA || !teamB) return;

    renderH2H(teamA, teamB);
    document.getElementById('h2h-panel').style.display = 'block';
    document.getElementById('h2h-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Render all ────────────────────────────────────────────────────────────
function renderH2H(a, b) {
    renderHeader(a, b);
    renderStatBars(a, b);
    renderMatchupHistory(a.team, b.team);
    renderPlayerComparison(a.team, b.team);
    renderOraclePrediction(a.team, b.team);
    renderRadarChart(a, b);
}

// ── VS header ─────────────────────────────────────────────────────────────
function renderHeader(a, b) {
    const colA = teamInk(a.team);
    const colB = teamInk(b.team);
    const formDots = team => (team.last5 || []).map(r =>
        `<span class="form-dot ${r === 'W' ? 'form-w' : 'form-l'}">${r}</span>`
    ).join('');

    document.getElementById('h2h-header').innerHTML = `
        <div style="text-align:center;flex:1">
            <div class="h2h-team-title" style="color:${colA}">${TEAM_NAMES[a.team] || a.team}</div>
            <div class="h2h-team-record">${a.wins}W – ${a.losses}L &nbsp;${formDots(a)}</div>
        </div>
        <div class="h2h-vs-big">VS</div>
        <div style="text-align:center;flex:1">
            <div class="h2h-team-title" style="color:${colB}">${TEAM_NAMES[b.team] || b.team}</div>
            <div class="h2h-team-record">${b.wins}W – ${b.losses}L &nbsp;${formDots(b)}</div>
        </div>`;
}

// ── Stat comparison bars ──────────────────────────────────────────────────
function renderStatBars(a, b) {
    const allTeams = _data.teams || [];
    const rankOf = (team, key, lower) => {
        const sorted = allTeams.slice().sort((x, y) => lower ? x[key] - y[key] : y[key] - x[key]);
        return sorted.findIndex(t => t.team === team) + 1;
    };

    const colA = teamInk(a.team);
    const colB = teamInk(b.team);

    const stats = [
        { label: 'Win %',            valA: a.win_pct,  valB: b.win_pct,  fmtA: a.win_pct + '%', fmtB: b.win_pct + '%' },
        { label: 'Adj Off Rating',   valA: a.adj_off,  valB: b.adj_off,  fmtA: a.adj_off,       fmtB: b.adj_off },
        { label: 'Adj Def Rating',   valA: a.adj_def,  valB: b.adj_def,  fmtA: a.adj_def,       fmtB: b.adj_def,  lowerBetter: true },
        { label: 'Adj Net Rating',   valA: a.adj_net,  valB: b.adj_net,  fmtA: (a.adj_net >= 0 ? '+' : '') + a.adj_net, fmtB: (b.adj_net >= 0 ? '+' : '') + b.adj_net },
        { label: 'Elo Rating',       valA: a.elo,      valB: b.elo,      fmtA: Math.round(a.elo), fmtB: Math.round(b.elo) },
        { label: 'Home Record',      valA: (a.home_record||{}).W||0, valB: (b.home_record||{}).W||0,
          fmtA: `${(a.home_record||{}).W||0}-${(a.home_record||{}).L||0}`,
          fmtB: `${(b.home_record||{}).W||0}-${(b.home_record||{}).L||0}` },
        { label: 'Away Record',      valA: (a.away_record||{}).W||0, valB: (b.away_record||{}).W||0,
          fmtA: `${(a.away_record||{}).W||0}-${(a.away_record||{}).L||0}`,
          fmtB: `${(b.away_record||{}).W||0}-${(b.away_record||{}).L||0}` },
        { label: 'SOS (Strength)',    valA: a.sos,      valB: b.sos,      fmtA: a.sos,           fmtB: b.sos },
    ];

    const el = document.getElementById('h2h-stat-bars');
    el.innerHTML = stats.map(s => {
        // For lower-is-better, invert advantage logic
        const aWins = s.lowerBetter ? s.valA < s.valB : s.valA > s.valB;
        const tie   = s.valA === s.valB;

        // Bar proportions — for lowerBetter, invert so the "better" team gets more bar
        let pctA, pctB;
        if (s.lowerBetter) {
            // Invert: lower value = bigger bar share
            const invA = s.valB, invB = s.valA;
            const total = invA + invB;
            pctA = total > 0 ? Math.round((invA / total) * 100) : 50;
            pctB = 100 - pctA;
        } else {
            const total = Math.abs(s.valA) + Math.abs(s.valB);
            pctA = total > 0 ? Math.round((Math.abs(s.valA) / total) * 100) : 50;
            pctB = 100 - pctA;
        }

        const advA = !tie && aWins  ? ' compare-advantage' : '';
        const advB = !tie && !aWins ? ' compare-advantage' : '';

        return `<div class="compare-row">
            <span class="compare-val compare-val-left${advA}" style="${advA ? `color:${colA}` : ''}">${s.fmtA}</span>
            <div class="compare-bar-wrap">
                <div class="compare-bar-a" style="width:${pctA}%;background:${colA}${aWins || tie ? '' : '60'}"></div>
                <div class="compare-bar-b" style="width:${pctB}%;background:${colB}${!aWins || tie ? '' : '60'}"></div>
            </div>
            <span class="compare-label">${s.label}</span>
            <span class="compare-val compare-val-right${advB}" style="${advB ? `color:${colB}` : ''}">${s.fmtB}</span>
        </div>`;
    }).join('');
}

// ── Matchup history ───────────────────────────────────────────────────────
function renderMatchupHistory(codeA, codeB) {
    const games = _backtest.filter(g =>
        (g.Home === codeA && g.Away === codeB) ||
        (g.Home === codeB && g.Away === codeA)
    ).sort((a, b) => a.Round - b.Round);

    const el = document.getElementById('h2h-history');
    if (!games.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:0.5rem 0">No direct matchups this season yet.</p>';
        return;
    }

    const colA = teamInk(codeA);
    const colB = teamInk(codeB);

    // H2H record
    const winsA = games.filter(g => g.ActualWinner === codeA).length;
    const winsB = games.filter(g => g.ActualWinner === codeB).length;
    const recColor = winsA > winsB ? colA : winsB > winsA ? colB : 'var(--text-muted)';

    el.innerHTML = `
        <p style="font-size:0.85rem;margin-bottom:0.6rem;color:var(--text-secondary)">
            Season record: <strong style="color:${recColor}">${winsA}–${winsB}</strong>
        </p>
        <table class="h2h-history-table">
            <thead><tr>
                <th>Round</th><th>Home</th><th>Away</th><th>Winner</th><th>Oracle</th>
            </tr></thead>
            <tbody>${games.map(g => {
                const winColor = teamInk(g.ActualWinner);
                const oracleOk = g.Correct;
                return `<tr>
                    <td>R${g.Round}</td>
                    <td style="color:${teamInk(g.Home)};font-weight:600">${g.Home}</td>
                    <td style="color:${teamInk(g.Away)};font-weight:600">${g.Away}</td>
                    <td><span class="h2h-winner-badge" style="color:${winColor};background:${winColor}18;border:1px solid ${winColor}99">${TEAM_NAMES[g.ActualWinner] || g.ActualWinner}</span></td>
                    <td><span class="${oracleOk ? 'h2h-oracle-correct' : 'h2h-oracle-wrong'}">${oracleOk ? 'Correct' : 'Wrong'}</span></td>
                </tr>`;
            }).join('')}</tbody>
        </table>`;
}

// ── Oracle prediction ─────────────────────────────────────────────────────
function renderOraclePrediction(codeA, codeB) {
    const preds = (_data.oracle || {}).predictions || [];
    const match = preds.find(p =>
        (p.Local === codeA && p.Road === codeB) ||
        (p.Local === codeB && p.Road === codeA)
    );

    const el = document.getElementById('h2h-oracle');
    if (!match) {
        el.innerHTML = `<div class="h2h-oracle-card">
            <p style="color:var(--text-muted)">These teams do not play next round.</p>
        </div>`;
        return;
    }

    const winnerCode  = match.Winner;
    const winnerColor = teamInk(winnerCode);
    const winnerName  = TEAM_NAMES[winnerCode] || winnerCode;
    const conf        = match.Conf;
    const margin      = Math.abs(match.Margin).toFixed(1);
    const homeProb    = match.HomeWinProb;
    const isHome      = match.Local === winnerCode;
    const coinFlip    = Math.abs(match.Margin) <= 3;

    el.innerHTML = `
        <div class="h2h-oracle-card" style="border-top:3px solid ${winnerColor}">
            <div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:0.5rem">
                Round ${(_data.oracle || {}).round || '?'} Prediction
            </div>
            <div class="h2h-oracle-winner" style="color:${winnerColor}">
                ${winnerName} ${coinFlip ? '<span style="color:var(--text-muted);font-size:0.75rem;font-weight:400">(Coin flip)</span>' : ''}
            </div>
            <div class="h2h-oracle-detail">
                ${isHome ? 'Home' : 'Away'} win · ${conf}% confidence · ${margin}pt predicted margin
            </div>
            <div style="display:flex;gap:0.5rem;justify-content:center;margin-top:0.6rem">
                <span style="font-size:0.78rem;color:${teamInk(match.Local)};font-weight:600">
                    ${match.Local} ${homeProb}%
                </span>
                <span style="font-size:0.78rem;color:var(--text-muted)">–</span>
                <span style="font-size:0.78rem;color:${teamInk(match.Road)};font-weight:600">
                    ${match.Road} ${(100 - homeProb).toFixed(1)}%
                </span>
            </div>
        </div>`;
}

// ── Player comparison ─────────────────────────────────────────────────────
function renderPlayerComparison(codeA, codeB) {
    const getTop = code => _playerStats
        .filter(p => p.team === code)
        .sort((a, b) => b.avg_pir - a.avg_pir)
        .slice(0, 3);

    const colA = teamInk(codeA);
    const colB = teamInk(codeB);

    const renderSide = (players, color, name) => {
        if (!players.length) return `<p style="color:var(--text-muted)">No player data.</p>`;
        return `
            <div class="pc-side-title" style="color:${color};border-color:${color}">${name}</div>
            ${players.map(p => `
                <div class="pc-player">
                    <div>
                        <div class="pc-name">${p.name}</div>
                        <div class="pc-meta">${p.position || ''} · ${p.gp} GP</div>
                    </div>
                    <div class="pc-stats">
                        <div><div class="pc-stat-val">${p.avg_pir}</div><div class="pc-stat-lbl">PIR</div></div>
                        <div><div class="pc-stat-val">${p.avg_pts}</div><div class="pc-stat-lbl">PTS</div></div>
                        <div><div class="pc-stat-val">${p.avg_ast}</div><div class="pc-stat-lbl">AST</div></div>
                        <div><div class="pc-stat-val">${p.avg_reb}</div><div class="pc-stat-lbl">REB</div></div>
                    </div>
                </div>`).join('')}`;
    };

    document.getElementById('h2h-players').innerHTML =
        `<div>${renderSide(getTop(codeA), colA, TEAM_NAMES[codeA] || codeA)}</div>
         <div>${renderSide(getTop(codeB), colB, TEAM_NAMES[codeB] || codeB)}</div>`;
}

// ── Radar chart ───────────────────────────────────────────────────────────
function renderRadarChart(a, b) {
    const allTeams = _data.teams || [];

    // Percentile rank (0-100) across all teams for a given key
    const pctRank = (team, key, lower) => {
        const vals = allTeams.map(t => t[key]).sort((x, y) => lower ? x - y : y - x);
        const idx  = vals.indexOf(team[key]);
        return Math.round(((allTeams.length - 1 - idx) / (allTeams.length - 1)) * 100);
    };

    // For defense, lower is better — invert so higher bar = better
    const categories = ['Offense', 'Defense', 'Elo', 'Win %', 'SOS'];
    const valsA = [
        pctRank(a, 'adj_off', false),
        pctRank(a, 'adj_def', true),
        pctRank(a, 'elo', false),
        pctRank(a, 'win_pct', false),
        pctRank(a, 'sos', false),
    ];
    const valsB = [
        pctRank(b, 'adj_off', false),
        pctRank(b, 'adj_def', true),
        pctRank(b, 'elo', false),
        pctRank(b, 'win_pct', false),
        pctRank(b, 'sos', false),
    ];

    const colA = teamInk(a.team);
    const colB = teamInk(b.team);

    const traces = [
        {
            type: 'scatterpolar',
            r: [...valsA, valsA[0]],
            theta: [...categories, categories[0]],
            fill: 'toself',
            fillcolor: colA + '30',
            line: { color: colA, width: 3 },
            name: TEAM_NAMES[a.team] || a.team,
        },
        {
            type: 'scatterpolar',
            r: [...valsB, valsB[0]],
            theta: [...categories, categories[0]],
            fill: 'toself',
            fillcolor: colB + '30',
            line: { color: colB, width: 3 },
            name: TEAM_NAMES[b.team] || b.team,
        },
    ];

    const layout = {
        polar: {
            bgcolor: 'transparent',
            radialaxis: {
                visible: true,
                range: [0, 100],
                tickfont: { color: '#4b5563', size: 10 },
                gridcolor: '#2d2e3a',
                linecolor: '#2d2e3a',
            },
            angularaxis: {
                tickfont: { color: '#9ca3af', size: 12 },
                gridcolor: '#2d2e3a',
                linecolor: '#2d2e3a',
            },
        },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        height: 350,
        margin: { t: 30, r: 50, b: 30, l: 50 },
        legend: {
            font: { color: '#9ca3af', size: 12 },
            bgcolor: 'transparent',
            orientation: 'h',
            x: 0.5, xanchor: 'center', y: -0.05,
        },
        font: { family: 'Inter, sans-serif' },
        hoverlabel: { font: { color: '#111111' } },
    };

    document.getElementById('h2h-radar').innerHTML = '';
    Plotly.newPlot('h2h-radar', traces, layout, { displayModeBar: false, responsive: true });
}
