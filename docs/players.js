/* ── players.js — Player Stats Hub ─────────────────────────────────────── */

// ── State ─────────────────────────────────────────────────────────────────
let _players = [];
let _mvpList  = [];
let _rapmData = [];
let _lbSort    = { key: 'avg_pir', dir: 'desc' };
let _rapmSort  = { key: 'RAPM', dir: 'desc' };
let _posFilter = '';
let _rapmPosFilter = '';
let _lbShowAll = false;
let _rapmShowAll = false;
let _cmpPlayerA = null;
let _cmpPlayerB = null;
let _round = 0;

// ── Tab config ────────────────────────────────────────────────────────────
const PLAYER_TABS = ['tab-leaderboards', 'tab-mvp', 'tab-rapm', 'tab-compare'];

// ── Boot ──────────────────────────────────────────────────────────────────
fetchJSON('data/current/dashboard.json')
    .then(data => {
        _players = data.player_stats || [];
        _mvpList  = data.mvp || [];
        _rapmData = data.rapm || [];
        _round = data.round || 0;

        // Early season the export only has players with < 5 games: default
        // the GP filter to the export's threshold so the table isn't empty.
        const minSel = document.getElementById('lb-mingp');
        const minGP0 = defaultMinGP(_round);
        if (minSel && minGP0 < 5) {
            const o = document.createElement('option');
            o.value = String(minGP0);
            o.textContent = `Min ${minGP0} GP`;
            minSel.insertBefore(o, minSel.firstChild);
            minSel.value = String(minGP0);
        }

        // Last-updated stamp
        if (data.updated) {
            const el = document.getElementById('last-updated');
            const d  = new Date(data.updated);
            el.textContent = `Updated ${d.toLocaleDateString('en-GB', {day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})} ${d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'})} UTC`;
            el.style.display = '';
        }

        // Populate team dropdowns (show full name, store code as value)
        const teams = [...new Set(_players.map(p => p.team))].sort((a, b) =>
            (TEAM_NAMES[a] || a).localeCompare(TEAM_NAMES[b] || b));
        const sel   = document.getElementById('lb-team');
        teams.forEach(t => {
            const o = document.createElement('option');
            o.value = t; o.textContent = TEAM_NAMES[t] || t;
            sel.appendChild(o);
        });

        const rapmTeams = [...new Set(_rapmData.map(p => p.team))].sort((a, b) =>
            (TEAM_NAMES[a] || a).localeCompare(TEAM_NAMES[b] || b));
        const rapmSel   = document.getElementById('rapm-team');
        if (rapmSel) {
            rapmTeams.forEach(t => {
                const o = document.createElement('option');
                o.value = t; o.textContent = TEAM_NAMES[t] || t;
                rapmSel.appendChild(o);
            });
        }

        // Enrich RAPM data with positions from player_stats
        const posLookup = {};
        _players.forEach(p => { posLookup[p.name] = p.position || ''; });
        _rapmData.forEach(r => { r.position = posLookup[r.player] || ''; });

        _renderLeaderboard();
        renderMvpRace(_mvpList, _players);
        _renderRapm();
        _initCompare();

        // Restore tab from hash
        const hash = location.hash.replace('#','');
        if (hash && document.getElementById(hash)) switchTab(hash, PLAYER_TABS);
    })
    .catch(err => {
        document.getElementById('leaderboard-table').innerHTML =
            `<p style="color:var(--accent-red);padding:1rem">Failed to load data: ${err}</p>`;
    });

// ── Leaderboard ───────────────────────────────────────────────────────────
const LB_COLS = [
    { key: 'avg_pts',  label: 'PTS',  title: 'Points per game' },
    { key: 'avg_reb',  label: 'REB',  title: 'Rebounds per game' },
    { key: 'avg_ast',  label: 'AST',  title: 'Assists per game' },
    { key: 'avg_stl',  label: 'STL',  title: 'Steals per game' },
    { key: 'avg_blk',  label: 'BLK',  title: 'Blocks per game' },
    { key: 'avg_to',   label: 'TO',   title: 'Turnovers per game' },
    { key: 'avg_pir',  label: 'PIR',  title: 'Performance Index Rating per game' },
    { key: 'fg_pct',   label: 'FG%',  title: 'Field goal percentage' },
    { key: 'fg3_pct',  label: '3P%',  title: 'Three-point percentage' },
    { key: 'ft_pct',   label: 'FT%',  title: 'Free throw percentage' },
    { key: 'gp',       label: 'GP',   title: 'Games played' },
];

function _setPosFilter(btn, pos) {
    document.querySelectorAll('.pos-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _posFilter = pos;
    _lbShowAll = false;
    _renderLeaderboard();
}

function _renderLeaderboard() {
    const search  = (document.getElementById('lb-search')?.value || '').toLowerCase();
    const team    = document.getElementById('lb-team')?.value || '';
    const minGP   = parseInt(document.getElementById('lb-mingp')?.value || String(defaultMinGP(_round)), 10);

    let rows = _players.filter(p =>
        p.gp >= minGP &&
        (!team || p.team === team) &&
        (!_posFilter || (p.position || '').startsWith(_posFilter)) &&
        (!search || p.name.toLowerCase().includes(search))
    );

    // Sort
    rows.sort((a, b) => {
        const av = a[_lbSort.key] ?? 0;
        const bv = b[_lbSort.key] ?? 0;
        return _lbSort.dir === 'desc' ? bv - av : av - bv;
    });

    const container = document.getElementById('leaderboard-table');
    if (!rows.length) {
        container.innerHTML = '<p style="color:var(--text-muted);padding:1rem">No players match your filters.</p>';
        return;
    }

    const headerCols = LB_COLS.map(c => {
        let cls = '';
        if (_lbSort.key === c.key) cls = _lbSort.dir === 'desc' ? 'lb-sort-desc' : 'lb-sort-asc';
        return `<th class="${cls}" title="${c.title}" onclick="_lbSetSort('${c.key}')">${c.label}</th>`;
    }).join('');

    const displayed = _lbShowAll ? rows : rows.slice(0, 30);
    const sortColIdx = LB_COLS.findIndex(c => c.key === _lbSort.key); // 0-based among stat cols

    const bodyRows = displayed.map((p, i) => {
        const color = getTeamColor(p.team);
        const badge = `<span class="lb-team-badge" title="${TEAM_NAMES[p.team] || p.team}" style="color:${teamInk(p.team)};border-color:${color}30;background:${color}15">${p.team}</span>`;
        const statCells = LB_COLS.map((c, ci) => {
            const isActive = ci === sortColIdx;
            const style = isActive ? ' style="background:rgba(59,130,246,0.08);color:var(--text-primary);font-weight:600"' : '';
            let val = p[c.key];
            if (c.key === 'fg_pct' || c.key === 'fg3_pct' || c.key === 'ft_pct') val = val + '%';
            return `<td${style}>${val}</td>`;
        }).join('');
        return `<tr>
            <td class="lb-rank">${i + 1}</td>
            <td class="lb-player-cell">
                ${p.code ? `<a class="lb-player-name" href="player.html?code=${p.code}" style="text-decoration:none;color:inherit">${p.name}</a>` : `<span class="lb-player-name">${p.name}</span>`}
                <span class="lb-player-meta">${badge}${p.position || ''}</span>
            </td>
            ${statCells}
        </tr>`;
    }).join('');

    const showAllBtn = rows.length > 30
        ? `<button class="forecast-toggle-btn" onclick="_lbToggleShowAll()">${_lbShowAll ? 'Show Top 30' : `Show All ${rows.length}`}</button>`
        : '';

    container.innerHTML = `
        <div style="overflow-x:auto">
        <table class="leaderboard-tbl">
            <thead><tr>
                <th></th>
                <th style="text-align:left">Player</th>
                ${LB_COLS.map((c, ci) => {
                    const isActive = ci === sortColIdx;
                    let cls = '';
                    if (isActive) cls = _lbSort.dir === 'desc' ? 'lb-sort-desc' : 'lb-sort-asc';
                    const style = isActive ? 'background:rgba(59,130,246,0.12)' : '';
                    return `<th class="${cls}" title="${c.title}" style="${style}" onclick="_lbSetSort('${c.key}')">${c.label}</th>`;
                }).join('')}
            </tr></thead>
            <tbody>${bodyRows}</tbody>
        </table>
        </div>
        <div class="lb-footer" style="display:flex;justify-content:space-between;align-items:center">
            <span>${_lbShowAll ? displayed.length : Math.min(30, rows.length)} of ${rows.length} players · sorted by ${_lbSort.key.replace('avg_','').toUpperCase()} ${_lbSort.dir === 'desc' ? '↓' : '↑'}</span>
            ${showAllBtn}
        </div>`;
}

function _lbSetSort(key) {
    if (_lbSort.key === key) {
        _lbSort.dir = _lbSort.dir === 'desc' ? 'asc' : 'desc';
    } else {
        _lbSort.key = key;
        // Default: stats desc, TO asc
        _lbSort.dir = key === 'avg_to' ? 'asc' : 'desc';
    }
    _renderLeaderboard();
}

function _lbToggleShowAll() {
    _lbShowAll = !_lbShowAll;
    _renderLeaderboard();
}

// ── MVP Race ──────────────────────────────────────────────────────────────
function renderMvpRace(mvpList, playerStats) {
    if (!mvpList.length) {
        document.getElementById('mvp-podium').innerHTML = mvpPendingHTML(_round);
        const rt = document.getElementById('mvp-race-table');
        if (rt) {
            const card = rt.closest('.stat-card');
            if (card) card.style.display = 'none';
        }
        return;
    }
    // Enrich mvp entries with full stats from player_stats
    const statsLookup = {};
    playerStats.forEach(p => { statsLookup[p.name] = p; });

    const enriched = mvpList.map(m => ({
        ...m,
        ...(statsLookup[m.player] || {}),
    }));

    const maxScore = enriched[0]?.mvp_score || enriched[0]?.mvp_score || 100;

    // Podium (top 3)
    const medals = ['🥇','🥈','🥉'];
    const podiumHtml = enriched.slice(0, 3).map((m, i) => {
        const color   = getTeamColor(m.team);
        const pct     = Math.round((m.mvp_score / maxScore) * 100);
        const avgPir  = m.avg_pir ?? m.avg_pir ?? '—';
        const avgPts  = m.avg_pts ?? '—';
        const avgAst  = m.avg_ast ?? '—';
        return `<div class="mvp-card rank-${i+1}">
            <div class="mvp-medal">${medals[i]}</div>
            <div class="mvp-card-name">${m.player}</div>
            <div class="mvp-card-team">
                <span class="lb-team-badge" title="${TEAM_NAMES[m.team] || m.team}" style="color:${teamInk(m.team)};border-color:${color}30;background:${color}15">${m.team}</span>
                ${m.gp} GP
            </div>
            <div class="mvp-score-bar-wrap"><div class="mvp-score-bar" style="width:${pct}%"></div></div>
            <div class="mvp-score-label">MVP Score: ${m.mvp_score}</div>
            <div class="mvp-card-stats">
                <div class="mvp-stat"><span class="mvp-stat-val">${avgPts}</span><span class="mvp-stat-lbl">PTS</span></div>
                <div class="mvp-stat"><span class="mvp-stat-val">${avgPir}</span><span class="mvp-stat-lbl">PIR</span></div>
                <div class="mvp-stat"><span class="mvp-stat-val">${avgAst}</span><span class="mvp-stat-lbl">AST</span></div>
                <div class="mvp-stat"><span class="mvp-stat-val">${(m.wpa||0).toFixed(0)}</span><span class="mvp-stat-lbl">WPA</span></div>
            </div>
        </div>`;
    }).join('');
    document.getElementById('mvp-podium').innerHTML = `<div class="mvp-podium">${podiumHtml}</div>`;

    // Full rankings table
    const tableRows = enriched.map((m, i) => {
        const color = getTeamColor(m.team);
        const badge = `<span class="lb-team-badge" title="${TEAM_NAMES[m.team] || m.team}" style="color:${teamInk(m.team)};border-color:${color}30;background:${color}15">${m.team}</span>`;
        const avgPir  = m.avg_pir ?? '—';
        const avgPts  = m.avg_pts ?? '—';
        const consist = m.consistency ? (m.consistency * 100).toFixed(0) + '%' : '—';
        const clutch  = m.clutch_eff  ? m.clutch_eff.toFixed(2) : '—';
        return `<tr>
            <td style="color:var(--text-muted);font-weight:700">${i+1}</td>
            <td>
                <span style="font-weight:600;color:var(--text-primary)">${m.player}</span><br>
                <span style="font-size:0.75rem">${badge}${m.position || ''}</span>
            </td>
            <td><span class="mvp-score-pill">${m.mvp_score}</span></td>
            <td>${avgPir}</td>
            <td>${avgPts}</td>
            <td>${(m.wpa||0).toFixed(0)}</td>
            <td>${consist}</td>
            <td>${clutch}</td>
            <td style="color:var(--text-muted)">${m.gp}</td>
        </tr>`;
    }).join('');

    document.getElementById('mvp-race-table').innerHTML = `
        <div style="overflow-x:auto">
        <table class="mvp-race-tbl">
            <thead><tr>
                <th></th>
                <th>Player</th>
                <th title="Composite MVP Score">Score</th>
                <th title="Avg Performance Index Rating">PIR</th>
                <th title="Avg Points">PTS</th>
                <th title="Win Probability Added">WPA</th>
                <th title="Consistency (inverse CV)">Consist.</th>
                <th title="Clutch Efficiency (points-per-clutch-game × true shooting %)">Clutch</th>
                <th>GP</th>
            </tr></thead>
            <tbody>${tableRows}</tbody>
        </table>
        </div>`;
}

// ── RAPM Tab ─────────────────────────────────────────────────────────────

function _fmtRapm(val) {
    if (val == null) return { text: '—', cls: 'neutral' };
    const sign = val > 0 ? '+' : '';
    const cls = val > 0.1 ? 'positive' : val < -0.1 ? 'negative' : 'neutral';
    return { text: sign + val.toFixed(2), cls };
}

function _rapmBar(val, maxAbs) {
    if (val == null || maxAbs === 0) return '';
    const pct = Math.min(Math.abs(val) / maxAbs * 100, 100);
    const cls = val >= 0 ? 'positive' : 'negative';
    return `<span class="rapm-bar ${cls}" style="width:${pct}%"></span>`;
}

function _cleanName(raw) {
    const parts = (raw || '').split(',');
    if (parts.length !== 2) return raw;
    const first = parts[1].trim(), last = parts[0].trim();
    // Title-case each word, preserve apostrophes and hyphens
    const tc = s => s.replace(/\w\S*/g, w => {
        // Keep suffixes like III, IV, II uppercase
        if (/^(II|III|IV|V|VI|JR|SR)$/i.test(w)) return w.toUpperCase();
        return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    // Fix post-apostrophe: O'shae → O'Shae
    }).replace(/([''-])(\w)/g, (_, sep, ch) => sep + ch.toUpperCase());
    return tc(first) + ' ' + tc(last);
}

const RAPM_COLS = {
    overall: [
        { key: 'RAPM',       label: 'RAPM',    title: 'Overall impact: net points gained per 100 possessions with this player on court' },
        { key: 'ORAPM',      label: 'O-RAPM',  title: 'Offensive impact: how much better the team scores with this player on court (per 100 poss)' },
        { key: 'DRAPM',      label: 'D-RAPM',  title: 'Defensive impact: how much the team limits opponents (positive = good defender, per 100 poss)' },
        { key: 'prior',      label: 'Prior',    title: 'Box-score expectation: what traditional stats predict this player\'s RAPM should be' },
        { key: 'RAPM_basic', label: 'Basic',    title: 'Basic RAPM without box-score adjustment — compare with RAPM to see the prior\'s effect' },
    ],
    offense: [
        { key: 'ORAPM',      label: 'O-RAPM',  title: 'Offensive impact: how much better the team scores with this player on court (per 100 poss)' },
        { key: 'RAPM',       label: 'RAPM',    title: 'Overall impact: net points gained per 100 possessions' },
        { key: 'DRAPM',      label: 'D-RAPM',  title: 'Defensive impact: positive = good defender (per 100 poss)' },
    ],
    defense: [
        { key: 'DRAPM',      label: 'D-RAPM',  title: 'Defensive impact: how much the team limits opponents (positive = good defender, per 100 poss)' },
        { key: 'RAPM',       label: 'RAPM',    title: 'Overall impact: net points gained per 100 possessions' },
        { key: 'ORAPM',      label: 'O-RAPM',  title: 'Offensive impact: how much better the team scores (per 100 poss)' },
    ],
};

let _rapmView = 'overall';

function _setRapmView(btn, view) {
    document.querySelectorAll('[data-rapm-view]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _rapmView = view;
    _rapmShowAll = false;
    _renderRapm();
}

function _setRapmPos(btn, pos) {
    document.querySelectorAll('[data-rapm-pos]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _rapmPosFilter = pos;
    _rapmShowAll = false;
    _renderRapm();
}

function _renderRapmTeamSummary(team, rows) {
    const el = document.getElementById('rapm-team-summary');
    if (!el) return;

    if (!team || rows.length === 0) {
        el.innerHTML = '';
        return;
    }

    const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;
    const teamRapm  = avg(rows.map(r => r.RAPM ?? 0));
    const teamOrapm = avg(rows.map(r => r.ORAPM ?? 0));
    const teamDrapm = avg(rows.map(r => r.DRAPM ?? 0));

    // Rank among all teams
    const teamAvgs = {};
    _rapmData.forEach(p => {
        if (!teamAvgs[p.team]) teamAvgs[p.team] = [];
        teamAvgs[p.team].push(p.RAPM ?? 0);
    });
    const teamRanking = Object.entries(teamAvgs)
        .map(([t, vals]) => ({ team: t, avg: avg(vals) }))
        .sort((a, b) => b.avg - a.avg);
    const rank = teamRanking.findIndex(t => t.team === team) + 1;
    const total = teamRanking.length;

    const best = rows.reduce((a, b) => (a.RAPM ?? 0) > (b.RAPM ?? 0) ? a : b);
    const worst = rows.reduce((a, b) => (a.RAPM ?? 0) < (b.RAPM ?? 0) ? a : b);

    const fmtV = v => { const s = v > 0 ? '+' : ''; return `<span class="rapm-val ${v > 0.1 ? 'positive' : v < -0.1 ? 'negative' : 'neutral'}">${s}${v.toFixed(2)}</span>`; };

    const color = getTeamColor(team);
    el.innerHTML = `<div class="rapm-team-summary">
        <div><span class="lb-team-badge" style="color:${teamInk(team)};border-color:${color}30;background:${color}15;font-size:0.85rem">${team}</span> <strong style="color:var(--text-primary)">${TEAM_NAMES[team] || team}</strong></div>
        <div><span class="rapm-ts-label">Team Avg RAPM</span><br>${fmtV(teamRapm)}</div>
        <div><span class="rapm-ts-label">Offense</span><br>${fmtV(teamOrapm)}</div>
        <div><span class="rapm-ts-label">Defense</span><br>${fmtV(teamDrapm)}</div>
        <div><span class="rapm-ts-label">Team Rank</span><br><span class="rapm-ts-value" style="color:var(--text-primary)">${rank} of ${total}</span></div>
        <div><span class="rapm-ts-label">Best Player</span><br><span style="color:var(--text-primary);font-weight:600">${_cleanName(best.player)}</span> ${fmtV(best.RAPM)}</div>
        <div><span class="rapm-ts-label">Weakest</span><br><span style="color:var(--text-primary);font-weight:600">${_cleanName(worst.player)}</span> ${fmtV(worst.RAPM)}</div>
    </div>`;
}

function _renderRapm() {
    const container = document.getElementById('rapm-table');
    if (!container || !_rapmData.length) {
        if (container) container.innerHTML = '<p style="color:var(--text-muted);padding:1rem">No RAPM data available.</p>';
        return;
    }

    const search = (document.getElementById('rapm-search')?.value || '').toLowerCase();
    const team   = document.getElementById('rapm-team')?.value || '';
    const view   = _rapmView;
    const cols   = RAPM_COLS[view] || RAPM_COLS.overall;

    // Default sort to first column of current view
    const validKeys = cols.map(c => c.key);
    if (!validKeys.includes(_rapmSort.key)) {
        _rapmSort.key = cols[0].key;
        _rapmSort.dir = 'desc';
    }

    let rows = _rapmData.filter(p =>
        (!team || p.team === team) &&
        (!_rapmPosFilter || (p.position || '').startsWith(_rapmPosFilter)) &&
        (!search || p.player.toLowerCase().includes(search))
    );

    // Team summary
    _renderRapmTeamSummary(team, rows);

    rows.sort((a, b) => {
        const av = a[_rapmSort.key] ?? 0;
        const bv = b[_rapmSort.key] ?? 0;
        return _rapmSort.dir === 'desc' ? bv - av : av - bv;
    });

    if (!rows.length) {
        container.innerHTML = '<p style="color:var(--text-muted);padding:1rem">No players match your filters.</p>';
        return;
    }

    // Max absolute value for bar scaling
    const maxAbs = Math.max(...rows.map(r => Math.abs(r[cols[0].key] ?? 0)), 0.01);

    const displayed = _rapmShowAll ? rows : rows.slice(0, 30);
    const sortIdx = cols.findIndex(c => c.key === _rapmSort.key);

    const bodyHtml = displayed.map((p, i) => {
        const color = getTeamColor(p.team);
        const badge = `<span class="lb-team-badge" title="${TEAM_NAMES[p.team] || p.team}" style="color:${teamInk(p.team)};border-color:${color}30;background:${color}15">${p.team}</span>`;

        const cells = cols.map((c, ci) => {
            const f = _fmtRapm(p[c.key]);
            const isActive = ci === sortIdx;
            const style = isActive ? ' style="background:rgba(59,130,246,0.08)"' : '';

            // Show bar only for the primary (first) column
            if (ci === 0) {
                return `<td${style}>
                    <span class="rapm-val ${f.cls}">${f.text}</span>
                    <div style="width:80px;display:inline-block;margin-left:0.5rem">${_rapmBar(p[c.key], maxAbs)}</div>
                </td>`;
            }
            return `<td${style}><span class="rapm-val ${f.cls}">${f.text}</span></td>`;
        }).join('');

        // Prior boost badge (shown in overall view)
        let boostHtml = '';
        if (view === 'overall' && p.RAPM != null && p.RAPM_basic != null) {
            const diff = p.RAPM - p.RAPM_basic;
            if (Math.abs(diff) >= 0.05) {
                const cls = diff > 0 ? 'boost' : 'drop';
                const sign = diff > 0 ? '+' : '';
                boostHtml = `<span class="rapm-prior-badge ${cls}">${sign}${diff.toFixed(2)}</span>`;
            }
        }

        return `<tr>
            <td class="lb-rank">${i + 1}</td>
            <td class="lb-player-cell">
                <span class="lb-player-name">${_cleanName(p.player)}${boostHtml}</span>
                <span class="lb-player-meta">${badge} ${Math.round(p.est_minutes || 0)} min</span>
            </td>
            ${cells}
        </tr>`;
    }).join('');

    const showAllBtn = rows.length > 30
        ? `<button class="forecast-toggle-btn" onclick="_rapmToggleShowAll()">${_rapmShowAll ? 'Show Top 30' : `Show All ${rows.length}`}</button>`
        : '';

    container.innerHTML = `
        <div style="overflow-x:auto">
        <table class="leaderboard-tbl">
            <thead><tr>
                <th></th>
                <th style="text-align:left">Player</th>
                ${cols.map((c, ci) => {
                    const isActive = ci === sortIdx;
                    let cls = '';
                    if (isActive) cls = _rapmSort.dir === 'desc' ? 'lb-sort-desc' : 'lb-sort-asc';
                    const style = isActive ? 'background:rgba(59,130,246,0.12)' : '';
                    return `<th class="${cls}" title="${c.title}" style="${style}" onclick="_rapmSetSort('${c.key}')">${c.label}</th>`;
                }).join('')}
            </tr></thead>
            <tbody>${bodyHtml}</tbody>
        </table>
        </div>
        <div class="lb-footer" style="display:flex;justify-content:space-between;align-items:center">
            <span>${_rapmShowAll ? displayed.length : Math.min(30, rows.length)} of ${rows.length} players</span>
            ${showAllBtn}
        </div>`;
}

function _rapmSetSort(key) {
    if (_rapmSort.key === key) {
        _rapmSort.dir = _rapmSort.dir === 'desc' ? 'asc' : 'desc';
    } else {
        _rapmSort.key = key;
        _rapmSort.dir = 'desc';
    }
    _rapmShowAll = false;
    _renderRapm();
}

function _rapmToggleShowAll() {
    _rapmShowAll = !_rapmShowAll;
    _renderRapm();
}

// ═══════════════════════════════════════════════════════════════════════════
// PLAYER COMPARISON TAB
// ═══════════════════════════════════════════════════════════════════════════

const CMP_STATS = [
    { key: 'avg_pts',  label: 'PTS',  title: 'Points per game' },
    { key: 'avg_reb',  label: 'REB',  title: 'Rebounds per game' },
    { key: 'avg_ast',  label: 'AST',  title: 'Assists per game' },
    { key: 'avg_stl',  label: 'STL',  title: 'Steals per game' },
    { key: 'avg_blk',  label: 'BLK',  title: 'Blocks per game' },
    { key: 'avg_to',   label: 'TO',   title: 'Turnovers per game', invert: true },
    { key: 'avg_pir',  label: 'PIR',  title: 'Performance Index Rating' },
    { key: 'fg_pct',   label: 'FG%',  title: 'Field goal percentage' },
    { key: 'fg3_pct',  label: '3P%',  title: 'Three-point percentage' },
    { key: 'ft_pct',   label: 'FT%',  title: 'Free throw percentage' },
];

const CMP_RADAR_AXES = [
    { key: 'avg_pts', label: 'PTS' },
    { key: 'avg_reb', label: 'REB' },
    { key: 'avg_ast', label: 'AST' },
    { key: 'avg_stl', label: 'STL' },
    { key: 'avg_blk', label: 'BLK' },
    { key: 'avg_pir', label: 'PIR' },
    { key: 'fg_pct',  label: 'FG%' },
];

function _initCompare() {
    const inputA = document.getElementById('cmp-search-a');
    const inputB = document.getElementById('cmp-search-b');
    if (!inputA || !inputB) return;
    _setupCmpInput(inputA, 'cmp-dropdown-a', 'a');
    _setupCmpInput(inputB, 'cmp-dropdown-b', 'b');
    // close dropdowns on outside click
    document.addEventListener('click', e => {
        if (!e.target.closest('.cmp-picker-wrap')) {
            document.querySelectorAll('.cmp-dropdown').forEach(d => d.classList.remove('open'));
        }
    });
}

function _setupCmpInput(input, dropdownId, side) {
    const dd = document.getElementById(dropdownId);
    input.addEventListener('input', () => {
        const q = input.value.trim().toLowerCase();
        if (q.length < 2) { dd.classList.remove('open'); return; }
        const matches = _players.filter(p =>
            p.name.toLowerCase().includes(q)
        ).slice(0, 12);
        if (!matches.length) { dd.innerHTML = '<div class="cmp-dropdown-item" style="color:var(--text-muted)">No matches</div>'; dd.classList.add('open'); return; }
        dd.innerHTML = matches.map((p, i) => {
            const color = getTeamColor(p.team);
            return `<div class="cmp-dropdown-item" data-idx="${i}" onclick="_selectCmpPlayer('${side}', '${p.code}')">
                <span>${p.name}</span>
                <span class="cmp-dd-team" style="color:${teamInk(p.team)}">${TEAM_NAMES[p.team] || p.team}</span>
            </div>`;
        }).join('');
        dd.classList.add('open');
    });
    input.addEventListener('focus', () => { if (input.value.trim().length >= 2) input.dispatchEvent(new Event('input')); });
}

function _selectCmpPlayer(side, code) {
    const p = _players.find(x => x.code === code);
    if (!p) return;
    if (side === 'a') { _cmpPlayerA = p; document.getElementById('cmp-search-a').value = p.name; }
    else { _cmpPlayerB = p; document.getElementById('cmp-search-b').value = p.name; }
    document.querySelectorAll('.cmp-dropdown').forEach(d => d.classList.remove('open'));
    if (_cmpPlayerA && _cmpPlayerB) _renderComparison();
}

function _renderComparison() {
    const a = _cmpPlayerA, b = _cmpPlayerB;
    if (!a || !b) return;
    const container = document.getElementById('cmp-result');

    const colA = teamInk(a.team);
    const colB = teamInk(b.team);

    // — Player cards —
    const card = (p, col) => {
        const rapm = _rapmData.find(r => r.player === p.name);
        const rapmHtml = rapm
            ? `<div style="margin-top:0.5rem;padding-top:0.5rem;border-top:1px solid var(--border)">
                <div class="cmp-player-kpis">
                    <div><div class="cmp-kpi-val" style="color:${rapm.RAPM >= 0 ? '#39d353' : '#f85149'}">${rapm.RAPM > 0 ? '+' : ''}${rapm.RAPM.toFixed(1)}</div><div class="cmp-kpi-label">RAPM</div></div>
                    <div><div class="cmp-kpi-val">${rapm.ORAPM > 0 ? '+' : ''}${rapm.ORAPM.toFixed(1)}</div><div class="cmp-kpi-label">O-RAPM</div></div>
                    <div><div class="cmp-kpi-val">${rapm.DRAPM > 0 ? '+' : ''}${rapm.DRAPM.toFixed(1)}</div><div class="cmp-kpi-label">D-RAPM</div></div>
                </div>
               </div>`
            : '';
        return `<div class="cmp-player-card" style="border-top-color:${col}">
            <div class="cmp-player-name">${p.name}</div>
            <div class="cmp-player-meta">${TEAM_NAMES[p.team] || p.team} · ${p.position || '—'} · ${p.gp} GP</div>
            <div class="cmp-player-kpis">
                <div><div class="cmp-kpi-val">${p.avg_pts}</div><div class="cmp-kpi-label">PTS</div></div>
                <div><div class="cmp-kpi-val">${p.avg_reb}</div><div class="cmp-kpi-label">REB</div></div>
                <div><div class="cmp-kpi-val">${p.avg_ast}</div><div class="cmp-kpi-label">AST</div></div>
            </div>
            ${rapmHtml}
        </div>`;
    };

    // — Stat bars (tug-of-war: full width split proportionally) —
    const bars = CMP_STATS.map(s => {
        const va = a[s.key] ?? 0, vb = b[s.key] ?? 0;
        const total = va + vb || 1;
        const pctA = (va / total) * 100;
        const pctB = (vb / total) * 100;
        const winA = s.invert ? va < vb : va > vb;
        const winB = s.invert ? vb < va : vb > va;
        const tie  = va === vb;
        const clsA = !tie && winA ? ' cmp-bar-winner' : '';
        const clsB = !tie && winB ? ' cmp-bar-winner' : '';
        const suffix = (s.key === 'fg_pct' || s.key === 'fg3_pct' || s.key === 'ft_pct') ? '%' : '';
        return `<div class="cmp-bar-row" title="${s.title}">
            <div class="cmp-bar-val${clsA}" style="color:${!tie && winA ? colA : 'var(--text-muted)'}">${va}${suffix}</div>
            <div class="cmp-bar-track">
                <div class="cmp-bar-fill-a" style="width:${pctA}%;background:${colA}"></div>
                <div class="cmp-bar-fill-b" style="width:${pctB}%;background:${colB}"></div>
            </div>
            <div class="cmp-bar-val${clsB}" style="color:${!tie && winB ? colB : 'var(--text-muted)'}">${vb}${suffix}</div>
            <div class="cmp-bar-label">${s.label}</div>
        </div>`;
    }).join('');

    // — Radar chart (SVG) —
    const radarSvg = _buildRadarSvg(a, b, colA, colB);

    container.innerHTML = `
        <div class="cmp-grid">${card(a, colA)}${card(b, colB)}</div>
        <div class="cmp-radar-legend">
            <span><span class="cmp-legend-dot" style="background:${colA}"></span>${a.name}</span>
            <span><span class="cmp-legend-dot" style="background:${colB}"></span>${b.name}</span>
        </div>
        <div class="cmp-radar-wrap">${radarSvg}</div>
        <div class="cmp-bars">${bars}</div>
    `;
}

function _buildRadarSvg(a, b, colA, colB) {
    const axes = CMP_RADAR_AXES;
    const n    = axes.length;
    const cx   = 160, cy = 160, R = 130;
    const allVals = {};
    axes.forEach(ax => {
        const vals = _players.map(p => p[ax.key] ?? 0).sort((x, y) => x - y);
        allVals[ax.key] = vals;
    });

    // Percentile rank for a value among all players
    const pctRank = (key, val) => {
        const sorted = allVals[key];
        if (!sorted.length) return 0;
        let idx = 0;
        for (let i = 0; i < sorted.length; i++) { if (sorted[i] <= val) idx = i; }
        return (idx / (sorted.length - 1)) * 100;
    };

    const angleStep = (2 * Math.PI) / n;
    const startAngle = -Math.PI / 2; // start from top

    const point = (pct, i) => {
        const r = (pct / 100) * R;
        const angle = startAngle + i * angleStep;
        return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
    };

    // Grid rings
    let grid = '';
    for (let ring = 25; ring <= 100; ring += 25) {
        const pts = [];
        for (let i = 0; i < n; i++) pts.push(point(ring, i).join(','));
        grid += `<polygon points="${pts.join(' ')}" fill="none" stroke="#2d2e3a" stroke-width="1"/>`;
    }

    // Axis lines and labels
    let axisLines = '', labels = '';
    for (let i = 0; i < n; i++) {
        const [x, y] = point(100, i);
        axisLines += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#2d2e3a" stroke-width="1"/>`;
        const [lx, ly] = point(115, i);
        labels += `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="central" fill="#9ca3af" font-size="11" font-weight="600">${axes[i].label}</text>`;
    }

    // Player polygons
    const polyPts = (player) => {
        const pts = [];
        for (let i = 0; i < n; i++) {
            const pct = pctRank(axes[i].key, player[axes[i].key] ?? 0);
            pts.push(point(pct, i).join(','));
        }
        return pts.join(' ');
    };

    const polyA = polyPts(a), polyB = polyPts(b);

    return `<svg viewBox="0 0 320 320" width="320" height="320" style="max-width:100%">
        ${grid}
        ${axisLines}
        <polygon points="${polyA}" fill="${colA}30" stroke="${colA}" stroke-width="2.5"/>
        <polygon points="${polyB}" fill="${colB}30" stroke="${colB}" stroke-width="2.5"/>
        ${labels}
    </svg>`;
}
