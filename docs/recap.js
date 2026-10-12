/* recap.js — Game Recap page */

let _recaps = null;
let _rounds = [];      // sorted list of available round numbers
let _currentRound = 0;
let _isInitialLoad = true;  // only auto-expand game on first load

let _playerCodeMap = null;
async function _getPlayerCodeMap() {
    if (_playerCodeMap) return _playerCodeMap;
    try {
        _playerCodeMap = await fetch('data/current/player_index.json').then(r => r.json());
    } catch { _playerCodeMap = {}; }
    return _playerCodeMap;
}

// ── Boot ──────────────────────────────────────────────────────────────────
fetchJSON('data/current/game_recaps.json')
    .then(data => {
        _recaps = data;
        _rounds = Object.keys(data.rounds).map(Number).sort((a, b) => a - b);

        // Determine starting round from URL or default to latest
        const params = new URLSearchParams(location.search);
        const urlRound = parseInt(params.get('round'));
        if (urlRound && _rounds.includes(urlRound)) {
            _currentRound = urlRound;
        } else {
            _currentRound = _rounds[_rounds.length - 1];
        }

        buildRoundPills();
        renderRound();

        // Show last-updated timestamp
        if (data.updated) {
            const el = document.getElementById('last-updated');
            el.textContent = `Last updated: ${new Date(data.updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}`;
            el.style.display = '';
        }
    })
    .catch(err => {
        document.getElementById('game-grid').innerHTML =
            `<p style="color:var(--accent-red)">Failed to load game recaps. ${err.message}</p>`;
    });

// ── Round navigation ─────────────────────────────────────────────────────
function buildRoundPills() {
    const wrap = document.getElementById('round-jump');
    wrap.innerHTML = _rounds.map(r =>
        `<span class="round-pill${r === _currentRound ? ' active' : ''}" onclick="goToRound(${r})">${r}</span>`
    ).join('');
}

function goToRound(r) {
    _currentRound = r;
    renderRound();
    buildRoundPills();
    history.replaceState(null, '', `?round=${r}`);  // clears any game param
}

function changeRound(delta) {
    const idx = _rounds.indexOf(_currentRound);
    const next = idx + delta;
    if (next >= 0 && next < _rounds.length) {
        goToRound(_rounds[next]);
    }
}

// ── Render round ─────────────────────────────────────────────────────────
function renderRound() {
    const games = _recaps.rounds[String(_currentRound)] || [];
    const idx = _rounds.indexOf(_currentRound);

    // Update nav
    document.getElementById('round-label').textContent = `Round ${_currentRound}`;
    document.getElementById('btn-prev').disabled = idx <= 0;
    document.getElementById('btn-next').disabled = idx >= _rounds.length - 1;

    // Show/hide jump-to-latest button
    const latestBtn = document.getElementById('btn-latest');
    if (latestBtn) {
        latestBtn.style.display = _currentRound === _rounds[_rounds.length - 1] ? 'none' : '';
    }

    // Round summary
    const oracleCorrect = games.filter(g => g.oracle.correct).length;
    const totalGames = games.length;
    const avgMargin = totalGames > 0
        ? (games.reduce((s, g) => s + Math.abs(g.homePts - g.awayPts), 0) / totalGames).toFixed(1)
        : 0;
    const homeWins = games.filter(g => g.homePts > g.awayPts).length;

    const summaryEl = document.getElementById('round-summary');
    summaryEl.innerHTML = `
        <span><strong>${totalGames}</strong> games</span>
        <span>Home wins: <strong>${homeWins}/${totalGames}</strong></span>
        <span>Avg margin: <strong>${avgMargin}</strong></span>
        <span>Oracle: <strong>${oracleCorrect}/${totalGames}</strong> correct</span>
    `;

    // Game cards
    const grid = document.getElementById('game-grid');
    if (games.length === 0) {
        grid.innerHTML = '<p style="color:var(--text-muted);text-align:center">No games for this round.</p>';
        return;
    }

    grid.innerHTML = games.map((g, i) => {
        const homeWon = g.homePts > g.awayPts;
        const margin = Math.abs(g.homePts - g.awayPts);
        const tp = g.topPerformer;

        return `
        <div class="game-card" id="game-${i}" onclick="toggleBoxScore(${i})">
            <div class="game-card-header">
                <div class="game-card-team">
                    <div class="game-card-code" style="color:${teamInk(g.home)}">${g.home}</div>
                    <div class="game-card-name">${g.homeName}</div>
                </div>
                <div class="game-card-score">
                    <span class="${homeWon ? 'winner-score' : 'loser-score'}">${g.homePts}</span>
                    <span style="color:var(--text-muted);margin:0 0.2rem">-</span>
                    <span class="${homeWon ? 'loser-score' : 'winner-score'}">${g.awayPts}</span>
                </div>
                <div class="game-card-team">
                    <div class="game-card-code" style="color:${teamInk(g.away)}">${g.away}</div>
                    <div class="game-card-name">${g.awayName}</div>
                </div>
            </div>
            ${g.date ? `<div style="text-align:center;font-size:0.68rem;color:var(--text-muted);margin-top:0.3rem">${g.date}${g.time ? ' · ' + g.time : ''}</div>` : ''}
            <div class="game-card-meta">
                <div class="game-card-oracle">
                    <span class="${g.oracle.correct ? 'oracle-correct' : 'oracle-wrong'}">
                        ${g.oracle.correct ? '&#10003;' : '&#10007;'}
                    </span>
                    Oracle: ${TEAM_NAMES[g.oracle.predictedWinner] || g.oracle.predictedWinner}
                    (${g.oracle.homeWinProb.toFixed(0)}%)
                </div>
                <span class="margin-badge">+${margin}</span>
            </div>
            ${tp ? `<div class="game-card-top-performer">MVP: <strong>${formatName(tp.name)}</strong> — ${tp.pts}p ${tp.reb}r ${tp.ast}a (PIR ${tp.pir})</div>` : ''}
            <div class="expand-chevron"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></div>

            <div class="box-score-panel" id="bs-panel-${i}">
                <div class="box-score-tabs">
                    <span class="bs-tab active" onclick="event.stopPropagation(); showTab(${i}, 'home')" id="tab-home-${i}">${g.home}</span>
                    <span class="bs-tab" onclick="event.stopPropagation(); showTab(${i}, 'away')" id="tab-away-${i}">${g.away}</span>
                </div>
                <div class="box-score-table-wrap" id="bs-content-${i}"></div>
                <div class="oracle-mini">
                    <div>
                        <div class="oracle-mini-label">Oracle Prediction</div>
                        <div class="oracle-mini-detail">
                            <strong>${TEAM_NAMES[g.oracle.predictedWinner] || g.oracle.predictedWinner}</strong> to win
                            by ${Math.abs(g.oracle.margin).toFixed(1)} pts
                            (${g.oracle.homeWinProb.toFixed(1)}% home win prob)
                            — <span class="${g.oracle.correct ? 'oracle-correct' : 'oracle-wrong'}">
                                ${g.oracle.correct ? 'Correct' : 'Wrong'}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');

    // Auto-expand game from URL only on initial page load
    if (_isInitialLoad) {
        _isInitialLoad = false;
        const urlGame = parseInt(new URLSearchParams(location.search).get('game'));
        if (!isNaN(urlGame) && urlGame >= 0 && urlGame < games.length) {
            setTimeout(() => toggleBoxScore(urlGame), 100);
        }
    }
}

// ── Toggle box score ─────────────────────────────────────────────────────
function toggleBoxScore(idx) {
    const panel = document.getElementById(`bs-panel-${idx}`);
    const card = document.getElementById(`game-${idx}`);
    const isOpen = panel.classList.contains('open');

    if (isOpen) {
        panel.classList.remove('open');
        card.classList.remove('expanded');
        // Clear game param from URL
        history.replaceState(null, '', `?round=${_currentRound}`);
        return;
    }

    panel.classList.add('open');
    card.classList.add('expanded');

    // Render home tab by default
    showTab(idx, 'home');

    // Update URL
    const params = new URLSearchParams(location.search);
    params.set('game', idx);
    history.replaceState(null, '', `?${params.toString()}`);
}

// ── Box score tab switching ──────────────────────────────────────────────
async function showTab(idx, side) {
    const games = _recaps.rounds[String(_currentRound)] || [];
    const g = games[idx];
    if (!g) return;

    // Update tab styling
    document.getElementById(`tab-home-${idx}`).className = `bs-tab${side === 'home' ? ' active' : ''}`;
    document.getElementById(`tab-away-${idx}`).className = `bs-tab${side === 'away' ? ' active' : ''}`;

    const roster = side === 'home' ? g.homeRoster : g.awayRoster;
    const totals = side === 'home' ? g.homeTotals : g.awayTotals;
    const teamCode = side === 'home' ? g.home : g.away;
    const color = teamInk(teamCode);

    await renderBoxScore(idx, roster, totals, color);
}

async function renderBoxScore(idx, roster, totals, color) {
    const container = document.getElementById(`bs-content-${idx}`);

    const starters = roster.filter(p => p.starter);
    const bench = roster.filter(p => !p.starter);

    const cols = ['MIN', 'PTS', 'REB', 'AST', 'STL', 'TO', 'BLK', 'FG', 'FG3', 'FT', 'PIR', '+/-'];
    const header = `<tr>
        <th>Player</th>
        ${cols.map(c => `<th class="num">${c}</th>`).join('')}
    </tr>`;

    const codeMap = await _getPlayerCodeMap();

    function playerRow(p, codeMap) {
        const pm = p.pm > 0 ? `+${p.pm}` : p.pm;
        const pmColor = p.pm > 0 ? 'var(--accent-green)' : p.pm < 0 ? 'var(--accent-red)' : '';
        const pirColor = p.pir >= 20 ? 'var(--accent-green)' : p.pir >= 10 ? 'var(--accent-blue)' : '';
        const displayName = formatName(p.name);
        const normName = n => n.toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
        const code = codeMap ? codeMap[normName(p.name)] : null;
        const nameHtml = code
            ? `<a href="player.html?code=${code}" style="text-decoration:none;color:inherit">${displayName}</a>`
            : displayName;
        return `<tr>
            <td>
                <span class="player-name">${nameHtml}</span>
                ${p.starter ? '<span class="starter-tag">S</span>' : ''}
            </td>
            <td class="num">${p.min}</td>
            <td class="num" style="font-weight:700">${p.pts}</td>
            <td class="num">${p.reb}</td>
            <td class="num">${p.ast}</td>
            <td class="num">${p.stl}</td>
            <td class="num">${p.to}</td>
            <td class="num">${p.blk}</td>
            <td class="num">${p.fg}</td>
            <td class="num">${p.fg3}</td>
            <td class="num">${p.ft}</td>
            <td class="num" style="font-weight:600;${pirColor ? `color:${pirColor}` : ''}">${p.pir}</td>
            <td class="num" style="${pmColor ? `color:${pmColor}` : ''}">${pm}</td>
        </tr>`;
    }

    const starterRows = starters.map(p => playerRow(p, codeMap)).join('');
    const benchRows = bench.length > 0
        ? `<tr class="bench-sep"><td colspan="${cols.length + 1}">Bench</td></tr>` + bench.map(p => playerRow(p, codeMap)).join('')
        : '';

    const totalsRow = `<tr class="totals-row">
        <td>TOTALS</td>
        <td class="num"></td>
        <td class="num">${totals.pts}</td>
        <td class="num">${totals.reb}</td>
        <td class="num">${totals.ast}</td>
        <td class="num">${totals.stl}</td>
        <td class="num">${totals.to}</td>
        <td class="num">${totals.blk}</td>
        <td class="num">${totals.fg2}</td>
        <td class="num">${totals.fg3}</td>
        <td class="num">${totals.ft}</td>
        <td class="num">${totals.pir}</td>
        <td class="num"></td>
    </tr>`;

    container.innerHTML = `
        <table class="box-score-tbl" style="border-top:3px solid ${color}">
            <thead>${header}</thead>
            <tbody>
                ${starterRows}
                ${benchRows}
                ${totalsRow}
            </tbody>
        </table>
    `;

    // Show scroll fade hint if table overflows
    requestAnimationFrame(() => {
        if (container.scrollWidth > container.clientWidth) {
            container.classList.add('has-scroll');
            container.addEventListener('scroll', function onScroll() {
                const atEnd = container.scrollLeft + container.clientWidth >= container.scrollWidth - 5;
                container.classList.toggle('has-scroll', !atEnd);
            });
        } else {
            container.classList.remove('has-scroll');
        }
    });
}

// ── Helpers ──────────────────────────────────────────────────────────────
function formatName(raw) {
    // "LASTNAME, FIRSTNAME" → "F. Lastname"
    if (!raw) return '';
    const parts = raw.split(', ');
    if (parts.length < 2) return raw;
    const last = parts[0].charAt(0) + parts[0].slice(1).toLowerCase();
    const first = parts[1].charAt(0) + '.';
    return `${first} ${last}`;
}
