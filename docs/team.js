/* ── team.js — Team Deep-Dive ─────────────────────────────────────────── */

let _data        = null;
let _playerStats = [];
let _selected    = null;

// ── Boot ──────────────────────────────────────────────────────────────────
fetchJSON('data/current/dashboard.json')
    .then(data => {
        _data        = data;
        _playerStats = data.player_stats || [];

        if (data.updated) {
            const el = document.getElementById('last-updated');
            const d  = new Date(data.updated);
            el.textContent = `Updated ${d.toLocaleDateString('en-GB', {day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})} ${d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'})} UTC`;
            el.style.display = '';
        }

        renderSelector(data.teams || []);

        // Restore from URL param
        const params = new URLSearchParams(location.search);
        const team   = params.get('team');
        if (team) selectTeam(team);
    })
    .catch(err => {
        document.getElementById('team-selector-grid').innerHTML =
            `<p style="color:var(--accent-red);padding:1rem">Failed to load data: ${err}</p>`;
    });

// ── Selector grid ─────────────────────────────────────────────────────────
function renderSelector(teams) {
    const grid = document.getElementById('team-selector-grid');
    grid.innerHTML = teams.map(t => {
        const name  = TEAM_NAMES[t.team]  || t.team;
        return `<div class="team-chip" id="chip-${t.team}"
                    onclick="selectTeam('${t.team}')"
                    style="border-top: 3px solid ${teamInk(t.team)}99">
            <span class="team-chip-code" style="color:${teamInk(t.team)}">${name}</span>
            <span class="team-chip-record">${t.wins}–${t.losses}</span>
        </div>`;
    }).join('');
}

// ── Select team ───────────────────────────────────────────────────────────
function selectTeam(code) {
    const team = (_data.teams || []).find(t => t.team === code);
    if (!team) return;

    // Update chip highlight
    document.querySelectorAll('.team-chip').forEach(c => c.classList.remove('selected'));
    document.getElementById('chip-' + code)?.classList.add('selected');

    _selected = code;
    history.replaceState(null, '', '?team=' + code);

    renderDeepDive(team);
    document.getElementById('deep-dive').style.display = 'block';
    document.getElementById('deep-dive').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Deep-dive ─────────────────────────────────────────────────────────────
function renderDeepDive(team) {
    const color    = getTeamColor(team.team);
    const allTeams = _data.teams || [];
    const rank     = allTeams.findIndex(t => t.team === team.team) + 1;

    // Pre-compute league ranks
    const offRank    = allTeams.slice().sort((a,b) => b.adj_off  - a.adj_off).findIndex(t => t.team === team.team) + 1;
    const defRank    = allTeams.slice().sort((a,b) => a.adj_def  - b.adj_def).findIndex(t => t.team === team.team) + 1;
    const eloRank    = allTeams.slice().sort((a,b) => b.elo      - a.elo    ).findIndex(t => t.team === team.team) + 1;
    const wpRank     = allTeams.slice().sort((a,b) => b.win_pct  - a.win_pct).findIndex(t => t.team === team.team) + 1;

    // Header — fix 3: add last5 form dots
    const formDots = (team.last5 || []).map(r =>
        `<span class="form-dot ${r === 'W' ? 'form-w' : 'form-l'}">${r}</span>`
    ).join('');
    document.getElementById('dd-color-bar').style.background = teamInk(team.team);
    document.getElementById('dd-name').textContent    = TEAM_NAMES[team.team] || team.team;
    document.getElementById('dd-name').style.color    = teamInk(team.team);
    document.getElementById('dd-record').innerHTML    = `${team.wins}W – ${team.losses}L &nbsp;${formDots}`;
    document.getElementById('dd-rank').textContent    = `#${rank} in standings`;
    const netSign = team.adj_net >= 0 ? '+' : '';
    document.getElementById('dd-net').textContent     = `Net Rtg ${netSign}${team.adj_net}`;
    document.getElementById('dd-net').style.color     = team.adj_net >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

    // KPIs — fix 1: add league rank sub-label
    document.getElementById('kpi-adjoff').textContent  = team.adj_off;
    document.getElementById('kpi-adjoff').style.color  = offRank <= 5 ? 'var(--accent-green)' : offRank >= 15 ? 'var(--accent-red)' : 'var(--text-primary)';
    document.getElementById('kpi-adjoff').nextElementSibling.innerHTML = `Adj Offensive Rating<br><span style="color:var(--accent-blue);font-size:0.7rem">#${offRank} in league</span>`;

    document.getElementById('kpi-adjdef').textContent  = team.adj_def;
    document.getElementById('kpi-adjdef').style.color  = defRank <= 5 ? 'var(--accent-green)' : defRank >= 15 ? 'var(--accent-red)' : 'var(--text-primary)';
    document.getElementById('kpi-adjdef').nextElementSibling.innerHTML = `Adj Defensive Rating<br><span style="color:var(--accent-blue);font-size:0.7rem">#${defRank} in league</span>`;

    document.getElementById('kpi-elo').textContent     = Math.round(team.elo);
    document.getElementById('kpi-elo').nextElementSibling.innerHTML = `Elo Rating<br><span style="color:var(--accent-blue);font-size:0.7rem">#${eloRank} in league</span>`;

    document.getElementById('kpi-winpct').textContent  = `${team.win_pct}%`;
    document.getElementById('kpi-winpct').nextElementSibling.innerHTML = `Win %<br><span style="color:var(--accent-blue);font-size:0.7rem">#${wpRank} in league</span>`;

    // Splits
    renderSplit('dd-home-rec', 'dd-home-bar', team.home_record || {W:0,L:0}, color);
    renderSplit('dd-away-rec', 'dd-away-bar', team.away_record || {W:0,L:0}, color);

    // Rolling form chart
    renderFormChart(team);

    // Top contributors
    renderContributors(team.team);

    // Next fixtures
    renderFixtures(team, allTeams);

    // Playoff odds
    renderPlayoffOdds(team, color);
}

function renderSplit(recId, barId, rec, color) {
    const w = rec.W || 0, l = rec.L || 0;
    const pct = (w + l) > 0 ? w / (w + l) : 0;
    document.getElementById(recId).textContent    = `${w}–${l}`;
    document.getElementById(recId).style.color    = w > l ? 'var(--accent-green)' : w < l ? 'var(--accent-red)' : 'var(--text-primary)';
    const bar = document.getElementById(barId);
    bar.style.width      = `${Math.round(pct * 100)}%`;
    bar.style.background = w > l ? 'var(--accent-green)' : w < l ? 'var(--accent-red)' : '#6b7280';
}

// ── Rolling form chart ────────────────────────────────────────────────────
function renderFormChart(team) {
    const results = team.round_results || [];
    if (!results.length) {
        document.getElementById('form-chart').innerHTML =
            '<p style="color:var(--text-muted);padding:1rem">No game data available.</p>';
        return;
    }

    const rounds  = results.map(r => r.round);
    const wins    = results.map(r => r.result === 'W' ? 1 : 0);
    const colors  = results.map(r => r.result === 'W' ? 'rgba(34,197,94,0.8)' : 'rgba(239,68,68,0.7)');

    // 5-game rolling win%
    const rolling = wins.map((_, i) => {
        const window = wins.slice(Math.max(0, i - 4), i + 1);
        return Math.round((window.reduce((a, b) => a + b, 0) / window.length) * 100);
    });

    const traces = [
        {
            type: 'bar',
            x: rounds,
            y: wins,
            marker: { color: colors },
            name: 'W / L',
            hovertemplate: rounds.map((r, i) => {
                const g = results[i];
                return `Round ${r}: ${g.result} vs ${g.opp}${g.home ? ' (H)' : ' (A)'}<extra></extra>`;
            }),
            yaxis: 'y',
        },
        {
            type: 'scatter',
            mode: 'lines+markers',
            x: rounds,
            y: rolling,
            name: '5-game win%',
            line: { color: '#a855f7', width: 2 },
            marker: { size: 5, color: '#a855f7' },
            text: rolling.map((v, i) => `Round ${rounds[i]}: ${v}% rolling win%`),
            hovertemplate: '%{text}<extra></extra>',
            yaxis: 'y2',
        },
    ];

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor:  'transparent',
        height: 220,
        margin: { t: 10, r: 55, b: 35, l: 35 },
        bargap: 0.15,
        xaxis: {
            tickfont: { color: '#6b7280', size: 11 },
            gridcolor: '#2d2e3a',
            tickmode: 'linear',
            tick0: 1,
            dtick: rounds.length > 20 ? 4 : 2,
            title: { text: 'Round', font: { color: '#6b7280', size: 11 } },
        },
        yaxis: {
            tickvals: [0, 1], ticktext: ['L', 'W'],
            tickfont: { color: '#6b7280', size: 11 },
            gridcolor: '#2d2e3a',
            range: [-0.2, 1.4],
        },
        yaxis2: {
            overlaying: 'y',
            side: 'right',
            range: [0, 110],
            tickfont: { color: '#a855f7', size: 11 },
            tickformat: '%',
            tickvals: [0, 25, 50, 75, 100],
            ticktext: ['0%','25%','50%','75%','100%'],
            showgrid: false,
        },
        legend: {
            font: { color: '#9ca3af', size: 11 },
            bgcolor: 'transparent',
            orientation: 'h',
            x: 0, y: 1.1,
        },
        font: { family: 'Inter, sans-serif' },
    };

    document.getElementById('form-chart').innerHTML = '';
    Plotly.newPlot('form-chart', traces, layout, { displayModeBar: false, responsive: true });
}

// ── Top contributors ──────────────────────────────────────────────────────
function renderContributors(teamCode) {
    const players = _playerStats
        .filter(p => p.team === teamCode)
        .sort((a, b) => b.avg_pir - a.avg_pir)
        .slice(0, 5);

    const el = document.getElementById('dd-contributors');
    if (!players.length) {
        el.innerHTML = '<p style="color:var(--text-muted)">No player data.</p>';
        return;
    }

    el.innerHTML = players.map(p => `
        <div class="contributor-row">
            <div>
                <div class="contributor-name">${p.code ? `<a href="player.html?code=${p.code}" style="text-decoration:none;color:inherit">${p.name}</a>` : p.name}</div>
                <div class="contributor-pos">${p.position || ''} · ${p.gp} GP</div>
            </div>
            <div class="contributor-stats">
                <div class="contributor-stat">
                    <div class="contributor-stat-val">${p.avg_pir}</div>
                    <div class="contributor-stat-lbl">PIR</div>
                </div>
                <div class="contributor-stat">
                    <div class="contributor-stat-val">${p.avg_pts}</div>
                    <div class="contributor-stat-lbl">PTS</div>
                </div>
                <div class="contributor-stat">
                    <div class="contributor-stat-val">${p.avg_ast}</div>
                    <div class="contributor-stat-lbl">AST</div>
                </div>
                <div class="contributor-stat">
                    <div class="contributor-stat-val">${p.avg_reb}</div>
                    <div class="contributor-stat-lbl">REB</div>
                </div>
            </div>
        </div>`).join('');
}

// ── Next 5 fixtures ───────────────────────────────────────────────────────
function renderFixtures(team, allTeams) {
    const opps = (team.remaining_opponents || []).slice(0, 5);
    const teamLookup = {};
    allTeams.forEach(t => { teamLookup[t.team] = t; });

    const el = document.getElementById('dd-fixtures');
    if (!opps.length) {
        el.innerHTML = '<p style="color:var(--text-muted)">No remaining fixtures.</p>';
        return;
    }

    // Colour bars relative to league-average win%
    const allWinPcts = allTeams.map(t => t.win_pct);
    const mean = allWinPcts.reduce((a, b) => a + b, 0) / allWinPcts.length;
    const max  = Math.max(...allWinPcts);

    el.innerHTML = `<div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:0.5rem">Opponent strength by season win%</div>` +
    opps.map(raw => {
        // Support both new {team, loc} format and legacy string format
        const oppCode  = typeof raw === 'object' ? raw.team : raw;
        const loc      = typeof raw === 'object' ? raw.loc : null;
        const t        = teamLookup[oppCode];
        const wp       = t ? t.win_pct : 50;
        const isHard   = wp >= mean + 10;
        const isEasy   = wp < mean - 10;
        const color    = isHard ? 'var(--accent-red)' : isEasy ? 'var(--accent-green)' : 'var(--accent-gold)';
        const diffLabel = isHard ? 'Hard' : isEasy ? 'Easy' : 'Average';
        const barW     = Math.round((wp / max) * 100);
        const oppColor = getTeamColor(oppCode);
        const locBadge = loc === 'home' ? '<span style="font-size:0.65rem;color:var(--accent-green);margin-left:0.35rem;font-weight:600" title="Home game">H</span>'
                       : loc === 'away' ? '<span style="font-size:0.65rem;color:var(--accent-red);margin-left:0.35rem;font-weight:600" title="Away game">A</span>'
                       : '';
        return `<div class="fixture-row">
            <div>
                <div class="fixture-opp">
                    <span style="color:${teamInk(oppCode)};font-weight:700">${oppCode}</span>${locBadge}
                    <span style="font-size:0.72rem;color:${color};margin-left:0.4rem;font-weight:600">${diffLabel}</span>
                </div>
                <div class="fixture-opp-full">${TEAM_NAMES[oppCode] || oppCode}</div>
            </div>
            <div class="fixture-sos-bar-wrap">
                <div class="fixture-sos-bar" style="width:${barW}%;background:${color}"></div>
            </div>
            <div class="fixture-sos-val" style="color:${color}" title="Opponent season win%">${wp}%</div>
        </div>`;
    }).join('');
}

// ── Playoff odds ──────────────────────────────────────────────────────────
function renderPlayoffOdds(team, color) {
    const el = document.getElementById('dd-playoff-odds');
    const items = [
        { label: 'Top 4',  pct: team.top4_pct,  desc: 'Double-bye' },
        { label: 'Top 6',  pct: team.top6_pct,  desc: 'Home court' },
        { label: 'Top 10', pct: team.top10_pct, desc: 'Qualify' },
    ];

    el.innerHTML = items.map(item => {
        const pct = Math.round(item.pct || 0);
        const barColor = pct >= 70 ? 'var(--accent-green)'
                       : pct >= 40 ? 'var(--accent-gold)'
                       : 'var(--accent-red)';
        return `<div class="odds-row">
            <span class="odds-label" title="${item.desc}">${item.label}</span>
            <div class="odds-bar-wrap">
                <div class="odds-bar" style="width:${pct}%;background:${barColor}"></div>
            </div>
            <span class="odds-pct">${pct}%</span>
        </div>`;
    }).join('');

    // Projected wins
    if (team.avg_wins) {
        el.innerHTML += `<p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.75rem">
            Projected final wins: <strong style="color:var(--text-primary)">${team.avg_wins}</strong>
            (currently ${team.current_wins || team.wins}, ${team.remaining || 0} games remaining)
        </p>`;
    }
}
