/**
 * playoffs.js — Interactive Euroleague Playoff Bracket Simulator
 *
 * Format:
 *   Play-In:
 *     Game A: 7 vs 8 — winner = 7th place (→ QF vs seed 2)
 *     Game B: 9 vs 10
 *     Game C: Loser(A) vs Winner(B) — winner = 8th place (→ QF vs seed 1)
 *   Quarterfinals: 1v8, 2v7, 3v6, 4v5 (best-of-5, higher seed home court)
 *   Final Four:    SF1 vs SF2, then Final (single game, neutral venue)
 *   Champion
 */

'use strict';

const ELO_HCA = 50;
const MC_ITERATIONS = 10000;

// Map (round, idx) -> series slot id used by series.html
function _seriesSlotId(round, idx) {
    if (round === 'quarters') return `qf${idx + 1}`;
    if (round === 'semis') return `sf${idx + 1}`;
    if (round === 'final') return 'final';
    return null;
}

function _slotIdForRecapRound(recap) {
    const label = (recap.series_label || recap.round || '').toLowerCase();
    if (!label) return null;
    if (label.includes('semi-final 1') || label.includes('semifinal 1') || label === 'sf1') return 'sf1';
    if (label.includes('semi-final 2') || label.includes('semifinal 2') || label === 'sf2') return 'sf2';
    if (label.includes('1v8')) return 'qf1';
    if (label.includes('2v7')) return 'qf2';
    if (label.includes('3v6')) return 'qf3';
    if (label.includes('4v5')) return 'qf4';
    if (label.includes('final') && !label.includes('semi') && !label.includes('quarter')) return 'final';
    return null;
}

// State
let _teams = [];
let _seeded = [];    // top 10 teams by seed
let _bracket = {};   // round → matchup index → { a, b, winner }
let _champion = null;
let _matchupProbs = {};  // pre-computed pairwise probabilities from backend
let _realResults = null;  // locked playoff results from backend
let _serverOdds = null;   // server-computed championship odds (authoritative initial view)
let _seriesWinProbs = {}; // live series win probs from backend, keyed by slot id (qf1..qf4 etc)
let _hasUserInteracted = false;  // set true on bracket click — switches MC to live sim
let _dashSeason = 2025;
let _currentRound = 0;           // current season round, used to invalidate stale localStorage brackets

// ── Elo win probability (fallback) ──────────────────────────────────────
function eloWinProb(eloA, eloB, neutral = false) {
    const hca = neutral ? 0 : ELO_HCA;
    return 1 / (1 + Math.pow(10, (eloB - eloA - hca) / 400));
}

// ── Pre-computed matchup probability lookup ─────────────────────────────
// venue: 'home' (A is home), 'away' (B is home), 'neutral'
function matchupProb(teamA, teamB, venue) {
    const entry = (_matchupProbs[teamA.team] || {})[teamB.team];
    if (entry) return entry[venue];
    // Fallback to Elo
    return eloWinProb(teamA.elo, teamB.elo, venue === 'neutral');
}

// Best-of-N series probability with alternating home court (2-2-1 pattern)
// Higher seed (team A) is home for games 1, 2, 5; away for games 3, 4
function seriesProbHCA(teamA, teamB, n) {
    const need = Math.ceil(n / 2);
    const homePattern = [true, true, false, false, true];

    // Per-game win probability for team A
    const gameProbs = [];
    for (let g = 0; g < n; g++) {
        gameProbs.push(homePattern[g]
            ? matchupProb(teamA, teamB, 'home')
            : matchupProb(teamA, teamB, 'away'));
    }

    // DP: walk through games, tracking P(winsA, winsB) states
    let states = new Map();
    states.set('0,0', 1.0);
    let probA = 0;

    for (let g = 0; g < n; g++) {
        const p = gameProbs[g];
        const next = new Map();

        for (const [key, prob] of states) {
            const [a, b] = key.split(',').map(Number);

            // A wins game g
            const a1 = a + 1;
            if (a1 >= need) {
                probA += prob * p;                       // A clinches
            } else {
                const k = `${a1},${b}`;
                next.set(k, (next.get(k) || 0) + prob * p);
            }

            // B wins game g
            const b1 = b + 1;
            if (b1 < need) {
                const k = `${a},${b1}`;
                next.set(k, (next.get(k) || 0) + prob * (1 - p));
            }
            // else: B clinches — not counted for A
        }

        states = next;
    }

    return probA;
}

// Compute probability of each possible series outcome (e.g. 3-0, 3-1, 3-2, 0-3, ...)
// startWinsA / startWinsB let us resume from the current series score.
function seriesOutcomeProbs(teamA, teamB, n, startWinsA = 0, startWinsB = 0) {
    const need = Math.ceil(n / 2);
    const homePattern = [true, true, false, false, true];

    // Only simulate games that haven't been played yet.
    const startGame = startWinsA + startWinsB;
    const gameProbs = [];
    for (let g = startGame; g < n; g++) {
        gameProbs.push(homePattern[g]
            ? matchupProb(teamA, teamB, 'home')
            : matchupProb(teamA, teamB, 'away'));
    }

    let states = new Map();
    states.set(`${startWinsA},${startWinsB}`, 1.0);
    const outcomes = {};           // "3-1" → probability

    for (let g = 0; g < gameProbs.length; g++) {
        const p = gameProbs[g];
        const next = new Map();

        for (const [key, prob] of states) {
            const [a, b] = key.split(',').map(Number);

            const a1 = a + 1;
            if (a1 >= need) {
                const k = `${a1}-${b}`;
                outcomes[k] = (outcomes[k] || 0) + prob * p;
            } else {
                const k = `${a1},${b}`;
                next.set(k, (next.get(k) || 0) + prob * p);
            }

            const b1 = b + 1;
            if (b1 >= need) {
                const k = `${a}-${b1}`;
                outcomes[k] = (outcomes[k] || 0) + prob * (1 - p);
            } else {
                const k = `${a},${b1}`;
                next.set(k, (next.get(k) || 0) + prob * (1 - p));
            }
        }

        states = next;
    }

    return outcomes;
}

// ── Initialize ───────────────────────────────────────────────────────────
async function init() {
    try {
        const resp = await fetch('data/current/dashboard.json');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        _teams = (data.teams || []).sort((a, b) =>
            b.wins - a.wins || b.adj_net - a.adj_net
        );

        if (data.updated) {
            const el = document.getElementById('last-updated');
            if (el) {
                const d = new Date(data.updated);
                el.textContent = `Data as of Round ${data.round || ''} · Updated ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;
                el.style.display = '';
            }
        }

        _matchupProbs = data.playoff_matchup_probs || {};
        _realResults = data.playoff_results || null;
        _serverOdds = data.championship_odds || null;
        _currentRound = data.round || 0;
        _dashSeason = dashboardSeason(data);
        const _ph = document.getElementById('playoffs-heading');
        if (_ph) _ph.textContent = `${seasonLabel(_dashSeason)} Euroleague Playoffs`;

        // Extract per-slot series win probabilities from series hub data.
        // These are computed by the backend accounting for games already played.
        _seriesWinProbs = {};
        const seriesData = data.series || {};
        for (const [slotId, entry] of Object.entries(seriesData)) {
            if (entry && entry.series_win_prob) {
                _seriesWinProbs[slotId] = entry.series_win_prob;
            }
        }

        // Top 10 teams seeded 1-10
        _seeded = _teams.slice(0, 10).map((t, i) => ({
            ...t,
            seed: i + 1,
        }));

        resetBracket();
        if (_realResults) {
            applyRealResults();
        }
        if (_realResults) {
            const h1 = document.querySelector('header h1');
            const sub = document.querySelector('header .subtitle');
            if (h1) h1.textContent = '\u{1F3C6} Playoff Bracket';
            if (sub) sub.textContent = 'Live results are locked. Click unplayed matchups to simulate forward.';
        }
        loadFromURL();
        runMonteCarlo();
        renderChampionshipOdds(data.championship_odds_history || []);
        renderPlayoffRecaps(data.playoff_recaps || []);
        renderPathToTitle(data.path_to_title || []);
        renderPlayoffPlayerStats(data.playoff_player_stats || []);
        renderChampionshipFinals(data.championship_finals_history || []);
    } catch (err) {
        document.getElementById('bracket').innerHTML =
            `<p style="color:var(--accent-red);padding:1rem">Failed to load data: ${err}</p>`;
    }
}

function resetBracket() {
    resetBracketSilent();
    if (_realResults) {
        applyRealResults();
    } else {
        renderBracket();
    }
    _hasUserInteracted = false;
    runMonteCarlo();
    updateURL();
}

// ── Render ────────────────────────────────────────────────────────────────
function renderBracket() {
    if (document.startViewTransition) {
        document.startViewTransition(_doRenderBracket);
    } else {
        _doRenderBracket();
    }
}

function _doRenderBracket() {
    const container = document.getElementById('bracket');

    container.innerHTML = `
        <div class="bracket-round" data-round="playin">
            <div class="bracket-round-title">Play-In</div>
            ${renderMatchup('playin', 0, 1, false, 'Game A · 7th place')}
            ${renderMatchup('playin', 1, 1, false, 'Game B')}
            ${renderMatchup('playin', 2, 1, false, 'Game C · 8th place')}
        </div>
        <div class="bracket-round" data-round="quarters">
            <div class="bracket-round-title">Quarterfinals</div>
            ${renderMatchup('quarters', 0, 5, false)}
            ${renderMatchup('quarters', 1, 5, false)}
            ${renderMatchup('quarters', 2, 5, false)}
            ${renderMatchup('quarters', 3, 5, false)}
        </div>
        <div class="bracket-round" data-round="semis">
            <div class="bracket-round-title">Final Four — Semis</div>
            ${renderMatchup('semis', 0, 1, true)}
            ${renderMatchup('semis', 1, 1, true)}
        </div>
        <div class="bracket-round" data-round="final">
            <div class="bracket-round-title">Final</div>
            ${renderMatchup('final', 0, 1, true)}
        </div>
        <div>
            ${renderChampion()}
        </div>
    `;

    drawConnectors();
}

function renderMatchup(round, idx, seriesLen, neutral, label) {
    const m = _bracket[round][idx];
    const teamA = m.a;
    const teamB = m.b;

    let probA = null, probB = null;
    if (teamA && teamB) {
        if (seriesLen > 1) {
            // For in-progress (live) series that haven't been decided yet,
            // prefer the backend's series win probability which accounts for
            // games already played (e.g. a 2-0 lead drastically shifts odds).
            // Fall back to the from-scratch DP only if no live data is available.
            const slotId = _seriesSlotId(round, idx);
            const liveProbs = slotId && !m.locked && m.seriesScore &&
                              (m.seriesScore[0] > 0 || m.seriesScore[1] > 0)
                              ? _seriesWinProbs[slotId] : null;
            if (liveProbs && liveProbs.high != null && liveProbs.low != null) {
                // Backend uses high_seed/low_seed ordering; teamA is the higher seed (a)
                probA = liveProbs.high / 100;
            } else {
                // No live backend probs — compute from the current series score so the
                // % badge stays consistent with the In-3/4/5 length distribution chart.
                const [wA, wB] = (m.seriesScore && !m.locked) ? m.seriesScore : [0, 0];
                if (wA > 0 || wB > 0) {
                    const need = Math.ceil(seriesLen / 2);
                    const outcomes = seriesOutcomeProbs(teamA, teamB, seriesLen, wA, wB);
                    probA = Object.entries(outcomes).reduce((sum, [k, p]) =>
                        sum + (Number(k.split('-')[0]) >= need ? p : 0), 0);
                } else {
                    probA = seriesProbHCA(teamA, teamB, seriesLen);
                }
            }
        } else {
            probA = matchupProb(teamA, teamB, neutral ? 'neutral' : 'home');
        }
        probB = 1 - probA;
    }

    const sideA = renderSide(teamA, probA, m.winner, round, idx, 'a');
    const sideB = renderSide(teamB, probB, m.winner, round, idx, 'b');

    let badgeHTML = '';
    const matchupData = _bracket[round][idx];
    if (label) {
        if (matchupData && matchupData.locked && matchupData.score) {
            badgeHTML = `<div class="series-badge">${label}<div class="locked-score">${matchupData.score.home} - ${matchupData.score.away}</div></div>`;
        } else {
            badgeHTML = `<div class="series-badge">${label}</div>`;
        }
    } else if (seriesLen > 1 && teamA && teamB) {
        if (matchupData && matchupData.seriesScore && (matchupData.seriesScore[0] > 0 || matchupData.seriesScore[1] > 0)) {
            const [hW, lW] = matchupData.seriesScore;
            const nameA = teamA.name.split(' ').pop();
            const nameB = teamB.name.split(' ').pop();
            const scoreText = `${nameA} ${hW} - ${lW} ${nameB}`;
            const prediction = matchupData.locked ? '' : getPredictedScore(teamA, teamB, seriesLen, hW, lW);

            // Clinch probability: chance the series ends in the very next game
            let clinchHTML = '';
            if (!matchupData.locked && teamA && teamB) {
                const need = Math.ceil(seriesLen / 2);
                const nextIdx = hW + lW;
                const qfHomePattern = [true, true, false, false, true]; // high seed home: G1,G2,G5
                const highIsHome = nextIdx < qfHomePattern.length ? qfHomePattern[nextIdx] : true;
                const venue = neutral ? 'neutral' : (highIsHome ? 'home' : 'away');
                const pHigh = matchupProb(teamA, teamB, venue);
                const aCanClinch = hW === need - 1;
                const bCanClinch = lW === need - 1;
                if (aCanClinch || bCanClinch) {
                    let clinchP = aCanClinch && bCanClinch ? 1 : aCanClinch ? pHigh : 1 - pHigh;
                    clinchHTML = `<div class="clinch-prob">🏁 Clinch next: ${(clinchP * 100).toFixed(0)}%</div>`;
                }
            }

            badgeHTML = `<div class="series-badge">Best of ${seriesLen} · ${scoreText}${clinchHTML}${prediction}</div>`;
        } else {
            const prediction = getPredictedScore(teamA, teamB, seriesLen);
            badgeHTML = `<div class="series-badge">Best of ${seriesLen} · HCA 2-2-1<div class="series-prediction">${prediction}</div></div>`;
        }
    } else if (seriesLen > 1) {
        badgeHTML = `<div class="series-badge">Best of ${seriesLen} · HCA 2-2-1</div>`;
    } else {
        if (matchupData && matchupData.locked && matchupData.score) {
            badgeHTML = `<div class="series-badge">Single game<div class="locked-score">${matchupData.score.home} - ${matchupData.score.away}</div></div>`;
        } else {
            badgeHTML = `<div class="series-badge">Single game</div>`;
        }
    }

    const slotId = _seriesSlotId(round, idx);
    const hubLink = (slotId && teamA && teamB)
        ? `<a class="series-hub-link" href="series.html?id=${slotId}" title="Open Series Hub" onclick="event.stopPropagation()">→</a>`
        : '';

    return `<div class="matchup" data-round="${round}" data-idx="${idx}">${sideA}${sideB}${badgeHTML}${hubLink}</div>`;
}

function renderSide(team, prob, winner, round, idx, side) {
    if (!team) {
        return `<div class="matchup-seed waiting locked">
            <div class="seed-num">?</div>
            <div class="seed-color" style="background:var(--border)"></div>
            <div class="seed-info"><div class="seed-name">Waiting...</div></div>
        </div>`;
    }

    const color = TEAM_COLORS[team.team] || '#555';
    const isWinner = winner && winner.team === team.team;
    const isLoser = winner && winner.team !== team.team;
    const isUpset = isWinner && prob < 0.5;
    const cls = (isWinner ? ' winner' : isLoser ? ' loser' : '') + (isUpset ? ' upset' : '');
    const locked = (winner && !isWinner) ? ' locked' : '';
    const check = isWinner ? '<div class="seed-check">✓</div>' : '<div class="seed-check"></div>';

    const probText = prob !== null
        ? `<div class="seed-prob" style="color:${probColor(prob)}">${(prob * 100).toFixed(0)}%</div>`
        : '';

    // Winner can be clicked to undo (unless locked by real results); non-winner side locked when winner is set
    let onclick = '';
    const matchup = _bracket[round][idx];
    const isLocked = matchup && matchup.locked;
    if (isWinner && !isLocked) {
        onclick = `onclick="undoPick('${round}',${idx})"`;
    } else if (!winner && !isLocked) {
        onclick = `onclick="pickWinner('${round}',${idx},'${side}')"`;
    }

    const hoverEvents = `onmouseenter="highlightPath('${team.team}')" onmouseleave="highlightPath(null)"`;

    return `<div class="matchup-seed${cls}${locked}" ${onclick} ${hoverEvents}>
        <div class="seed-num">#${team.seed}</div>
        <div class="seed-color" style="background:${color}"></div>
        <div class="seed-info">
            <div class="seed-name">${team.name}</div>
            <div class="seed-record">${team.wins}-${team.losses} · Elo ${team.elo.toFixed(0)}</div>
        </div>
        ${probText}
        ${check}
    </div>`;
}

function probColor(p) {
    if (p >= 0.65) return '#22c55e';
    if (p >= 0.50) return '#a3e635';
    if (p >= 0.35) return '#fbbf24';
    return '#f87171';
}

// Series length distribution: mini bar chart showing P(in 3), P(in 4), P(in 5)
// winsA / winsB: games already won by each side (to resume from current series state)
function getPredictedScore(teamA, teamB, seriesLen, winsA = 0, winsB = 0) {
    const outcomes = seriesOutcomeProbs(teamA, teamB, seriesLen, winsA, winsB);
    const need = Math.ceil(seriesLen / 2);

    // Group by total series length (combine both winners)
    const lengthProbs = {};
    for (const [key, prob] of Object.entries(outcomes)) {
        const [wA, wB] = key.split('-').map(Number);
        const total = wA + wB;
        lengthProbs[total] = (lengthProbs[total] || 0) + prob;
    }

    // Find most likely length
    let bestLen = 0, bestProb = 0;
    for (const [len, prob] of Object.entries(lengthProbs)) {
        if (prob > bestProb) { bestLen = Number(len); bestProb = prob; }
    }

    // Build mini bar chart — only show lengths still possible from current state
    const minLen = Math.max(need, winsA + winsB + 1);
    const maxProb = Math.max(...Object.values(lengthProbs), 1e-9);
    let html = '<div class="series-len-dist">';
    for (let g = minLen; g <= seriesLen; g++) {
        const p = lengthProbs[g] || 0;
        const pct = (p * 100).toFixed(0);
        const w = (p / maxProb) * 100;
        const best = g === bestLen ? ' best' : '';
        html += `<div class="len-row${best}">` +
            `<span class="len-label">In ${g}</span>` +
            `<div class="len-track"><div class="len-fill" style="width:${w}%"></div></div>` +
            `<span class="len-pct">${pct}%</span>` +
            `</div>`;
    }
    html += '</div>';
    return html;
}

function renderChampion() {
    if (!_champion) {
        return `<div class="champion-card empty">
            <div class="champion-trophy">🏆</div>
            <div class="champion-label">Champion</div>
            <div class="champion-name" style="color:var(--text-muted)">TBD</div>
        </div>`;
    }
    const color = TEAM_COLORS[_champion.team] || '#555';
    const path = computeChampionPath();
    return `<div class="champion-card">
        <div class="champion-trophy">🏆</div>
        <div class="champion-label">Champion</div>
        <div class="champion-name" style="color:${color}">${_champion.name}</div>
        <div class="champion-prob">Path probability: ${(path * 100).toFixed(1)}%</div>
    </div>`;
}

// ── Pick winner ──────────────────────────────────────────────────────────
function pickWinner(round, idx, side) {
    const m = _bracket[round][idx];
    if (!m.a || !m.b || m.winner) return;

    const winner = side === 'a' ? m.a : m.b;
    m.winner = winner;

    // Cascade: feed winner into next round
    cascadeForward(round, idx, side);

    _hasUserInteracted = true;
    renderBracket();
    runMonteCarlo();
    updateURL();
}

function cascadeForward(round, idx, side) {
    const m = _bracket[round][idx];
    const winner = m.winner;

    if (round === 'playin') {
        const loser = side === 'a' ? m.b : m.a;
        if (idx === 0) {
            // Game A decided: winner gets 7th place → QF vs seed 2
            _bracket.quarters[1].b = winner;
            // Loser goes to Game C as side A
            _bracket.playin[2].a = loser;
        }
        if (idx === 1) {
            // Game B decided: winner goes to Game C as side B
            _bracket.playin[2].b = winner;
        }
        if (idx === 2) {
            // Game C decided: winner gets 8th place → QF vs seed 1
            _bracket.quarters[0].b = winner;
        }
    } else if (round === 'quarters') {
        if (idx === 0) _bracket.semis[0].a = winner;
        if (idx === 3) _bracket.semis[0].b = winner;
        if (idx === 1) _bracket.semis[1].a = winner;
        if (idx === 2) _bracket.semis[1].b = winner;
    } else if (round === 'semis') {
        if (idx === 0) _bracket.final[0].a = winner;
        if (idx === 1) _bracket.final[0].b = winner;
    } else if (round === 'final') {
        _champion = winner;
    }
}

// ── Undo pick ────────────────────────────────────────────────────────────
function undoPick(round, idx) {
    const m = _bracket[round][idx];
    if (!m.winner) return;

    m.winner = null;

    // Clear all downstream picks that depended on this winner
    if (round === 'playin') {
        if (idx === 0) {
            // Game A undone: clear QF1 opponent, clear Game C side A + its downstream
            _bracket.quarters[1].b = null;
            clearMatchup('quarters', 1);
            _bracket.playin[2].a = null;
            clearMatchup('playin', 2);
        }
        if (idx === 1) {
            // Game B undone: clear Game C side B + its downstream
            _bracket.playin[2].b = null;
            clearMatchup('playin', 2);
        }
        if (idx === 2) {
            // Game C undone: clear QF0 opponent
            _bracket.quarters[0].b = null;
            clearMatchup('quarters', 0);
        }
    } else if (round === 'quarters') {
        if (idx === 0) { _bracket.semis[0].a = null; clearMatchup('semis', 0); }
        if (idx === 3) { _bracket.semis[0].b = null; clearMatchup('semis', 0); }
        if (idx === 1) { _bracket.semis[1].a = null; clearMatchup('semis', 1); }
        if (idx === 2) { _bracket.semis[1].b = null; clearMatchup('semis', 1); }
    } else if (round === 'semis') {
        if (idx === 0) { _bracket.final[0].a = null; clearMatchup('final', 0); }
        if (idx === 1) { _bracket.final[0].b = null; clearMatchup('final', 0); }
    } else if (round === 'final') {
        _champion = null;
    }

    _hasUserInteracted = true;
    renderBracket();
    runMonteCarlo();
    updateURL();
}

// Recursively clear a matchup and its downstream effects
function clearMatchup(round, idx) {
    const m = _bracket[round][idx];
    if (m.winner) {
        m.winner = null;

        if (round === 'playin' && idx === 2) {
            _bracket.quarters[0].b = null;
            clearMatchup('quarters', 0);
        } else if (round === 'quarters') {
            if (idx === 0) { _bracket.semis[0].a = null; clearMatchup('semis', 0); }
            if (idx === 3) { _bracket.semis[0].b = null; clearMatchup('semis', 0); }
            if (idx === 1) { _bracket.semis[1].a = null; clearMatchup('semis', 1); }
            if (idx === 2) { _bracket.semis[1].b = null; clearMatchup('semis', 1); }
        } else if (round === 'semis') {
            if (idx === 0) { _bracket.final[0].a = null; clearMatchup('final', 0); }
            if (idx === 1) { _bracket.final[0].b = null; clearMatchup('final', 0); }
        } else if (round === 'final') {
            _champion = null;
        }
    }
}

// ── Auto-fill by favorites ───────────────────────────────────────────────
function autoFill() {
    _hasUserInteracted = true;
    resetBracket();

    // Walk through each round in order, picking the higher-probability side
    const roundOrder = [
        { round: 'playin', indices: [0, 1, 2], seriesLen: 1, neutral: false },
        { round: 'quarters', indices: [0, 1, 2, 3], seriesLen: 5, neutral: false },
        { round: 'semis', indices: [0, 1], seriesLen: 1, neutral: true },
        { round: 'final', indices: [0], seriesLen: 1, neutral: true },
    ];

    for (const { round, indices, seriesLen, neutral } of roundOrder) {
        for (const idx of indices) {
            const m = _bracket[round][idx];
            if (!m.a || !m.b || m.winner) continue;
            const pA = seriesLen > 1
                ? seriesProbHCA(m.a, m.b, seriesLen)
                : matchupProb(m.a, m.b, neutral ? 'neutral' : 'home');
            const side = pA >= 0.5 ? 'a' : 'b';
            m.winner = side === 'a' ? m.a : m.b;
            cascadeForward(round, idx, side);
        }
    }

    renderBracket();
    runMonteCarlo();
    updateURL();
}

// ── Monte Carlo simulation ───────────────────────────────────────────────
function runMonteCarlo() {
    if (_seeded.length < 10) return;

    // Until the user interacts, show the authoritative server-side odds so
    // the MC chart and Path to Title table match exactly on initial load.
    if (!_hasUserInteracted && _serverOdds && Object.keys(_serverOdds).length) {
        const counts = {};
        for (const t of _seeded) {
            counts[t.team] = ((_serverOdds[t.team] || 0) / 100) * MC_ITERATIONS;
        }
        renderMonteCarloChart(counts);
        return;
    }

    const counts = {};
    for (const t of _seeded) counts[t.team] = 0;

    for (let i = 0; i < MC_ITERATIONS; i++) {
        const champ = simulateOnce();
        if (champ) counts[champ.team] = (counts[champ.team] || 0) + 1;
    }

    renderMonteCarloChart(counts);
}

function simulateOnce() {
    const s = _seeded;

    // Play-In Game A: 7 vs 8
    let gameAWinner, gameALoser;
    if (_bracket.playin[0].winner) {
        gameAWinner = _bracket.playin[0].winner;
        gameALoser = gameAWinner.team === s[6].team ? s[7] : s[6];
    } else {
        const pA = matchupProb(s[6], s[7], 'home');
        gameAWinner = Math.random() < pA ? s[6] : s[7];
        gameALoser = gameAWinner === s[6] ? s[7] : s[6];
    }

    // Play-In Game B: 9 vs 10
    const gameBWinner = _bracket.playin[1].winner
        || (Math.random() < matchupProb(s[8], s[9], 'home') ? s[8] : s[9]);

    // Play-In Game C: Loser(A) vs Winner(B)
    const gameCWinner = _bracket.playin[2].winner
        || (Math.random() < matchupProb(gameALoser, gameBWinner, 'home') ? gameALoser : gameBWinner);

    const seed7 = gameAWinner;  // → QF vs seed 2
    const seed8 = gameCWinner;  // → QF vs seed 1

    // Quarterfinals (best-of-5)
    const qfPairs = [[s[0], seed8], [s[1], seed7], [s[2], s[5]], [s[3], s[4]]];
    const qf = qfPairs.map((pair, i) =>
        _bracket.quarters[i].winner || simSeries(pair[0], pair[1], 5)
    );

    // Final Four — Semis (neutral)
    const sf1 = _bracket.semis[0].winner || simGame(qf[0], qf[3], true);
    const sf2 = _bracket.semis[1].winner || simGame(qf[1], qf[2], true);

    // Final (neutral)
    return _bracket.final[0].winner || simGame(sf1, sf2, true);
}

function simGame(a, b, neutral) {
    const p = matchupProb(a, b, neutral ? 'neutral' : 'home');
    return Math.random() < p ? a : b;
}

function simSeries(a, b, n) {
    const need = Math.ceil(n / 2);
    // 2-2-1 home court pattern: higher seed (a) home for games 1, 2, 5
    const homePattern = [true, true, false, false, true];
    let wA = 0, wB = 0, game = 0;
    while (wA < need && wB < need) {
        const p = homePattern[game]
            ? matchupProb(a, b, 'home')
            : matchupProb(a, b, 'away');
        if (Math.random() < p) wA++; else wB++;
        game++;
    }
    return wA >= need ? a : b;
}

function renderMonteCarloChart(counts) {
    const container = document.getElementById('mc-chart');
    if (!container) return;

    const entries = _seeded.map(t => ({
        team: t.team,
        name: t.name,
        pct: (counts[t.team] / MC_ITERATIONS) * 100,
        color: TEAM_COLORS[t.team] || '#555',
    })).sort((a, b) => b.pct - a.pct);

    const maxPct = Math.max(...entries.map(e => e.pct), 1);

    let html = '';
    for (const e of entries) {
        const w = (e.pct / maxPct) * 100;
        html += `<div class="mc-bar-row">
            <div class="mc-bar-label">${e.name}</div>
            <div class="mc-bar-track">
                <div class="mc-bar-fill" style="width:${w}%;background:${e.color}"></div>
            </div>
            <div class="mc-bar-pct">${e.pct.toFixed(1)}%</div>
        </div>`;
    }

    container.innerHTML = html;
}

// ── Path probability ─────────────────────────────────────────────────────
function computeChampionPath() {
    if (!_champion) return 0;
    let prob = 1;

    const rounds = ['playin', 'quarters', 'semis', 'final'];
    const seriesLens = { playin: 1, quarters: 5, semis: 1, final: 1 };
    const neutrals = { playin: false, quarters: false, semis: true, final: true };

    for (const round of rounds) {
        for (const m of _bracket[round]) {
            if (m.winner && m.winner.team === _champion.team && m.a && m.b) {
                const len = seriesLens[round];
                const pA = len > 1
                    ? seriesProbHCA(m.a, m.b, len)
                    : matchupProb(m.a, m.b, neutrals[round] ? 'neutral' : 'home');
                const side = m.winner.team === m.a.team ? pA : 1 - pA;
                prob *= side;
            }
        }
    }
    return prob;
}

// ── SVG Connector Lines ──────────────────────────────────────────────────
function drawConnectors() {
    const old = document.getElementById('bracket-connectors');
    if (old) old.remove();

    const bracketEl = document.getElementById('bracket');
    const rect = bracketEl.getBoundingClientRect();

    // Resolve CSS custom property for stroke color
    const strokeColor = getComputedStyle(document.documentElement)
        .getPropertyValue('--border').trim() || '#2a2a3a';

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = 'bracket-connectors';
    svg.setAttribute('width', rect.width);
    svg.setAttribute('height', rect.height);
    svg.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;overflow:visible;';
    bracketEl.appendChild(svg);

    // Cross-round connections only (same-column play-in links are implicit)
    const connections = [
        // Play-In → Quarters
        { from: { round: 'playin', idx: 0 }, to: { round: 'quarters', idx: 1 } },
        { from: { round: 'playin', idx: 2 }, to: { round: 'quarters', idx: 0 } },
        // Quarters → Semis
        { from: { round: 'quarters', idx: 0 }, to: { round: 'semis', idx: 0 } },
        { from: { round: 'quarters', idx: 3 }, to: { round: 'semis', idx: 0 } },
        { from: { round: 'quarters', idx: 1 }, to: { round: 'semis', idx: 1 } },
        { from: { round: 'quarters', idx: 2 }, to: { round: 'semis', idx: 1 } },
        // Semis → Final
        { from: { round: 'semis', idx: 0 }, to: { round: 'final', idx: 0 } },
        { from: { round: 'semis', idx: 1 }, to: { round: 'final', idx: 0 } },
    ];

    for (const conn of connections) {
        const fromEl = bracketEl.querySelector(`.matchup[data-round="${conn.from.round}"][data-idx="${conn.from.idx}"]`);
        const toEl = bracketEl.querySelector(`.matchup[data-round="${conn.to.round}"][data-idx="${conn.to.idx}"]`);
        if (!fromEl || !toEl) continue;

        const fromRect = fromEl.getBoundingClientRect();
        const toRect = toEl.getBoundingClientRect();

        const x1 = fromRect.right - rect.left;
        const y1 = fromRect.top + fromRect.height / 2 - rect.top;
        const x2 = toRect.left - rect.left;
        const y2 = toRect.top + toRect.height / 2 - rect.top;
        const midX = (x1 + x2) / 2;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', `M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', strokeColor);
        path.setAttribute('stroke-width', '1.5');
        path.setAttribute('opacity', '0.4');
        path.style.transition = 'opacity 0.2s, stroke-width 0.2s, stroke 0.2s';
        
        const m = _bracket[conn.from.round][conn.from.idx];
        if (m && m.winner) {
            path.setAttribute('data-team', m.winner.team);
        }

        svg.appendChild(path);
    }
}

function highlightPath(teamId) {
    const svg = document.getElementById('bracket-connectors');
    if (!svg) return;
    
    if (teamId) {
        svg.classList.add('hovering');
        svg.querySelectorAll('path').forEach(p => {
            if (p.getAttribute('data-team') === teamId) {
                p.classList.add('active-path');
            } else {
                p.classList.remove('active-path');
            }
        });
    } else {
        svg.classList.remove('hovering');
        svg.querySelectorAll('path').forEach(p => p.classList.remove('active-path'));
    }
}

// ── Share via URL ────────────────────────────────────────────────────────
function encodeBracket() {
    // Encode each pick as side letter (a/b) or dash for unpicked, per matchup
    const rounds = [
        { key: 'playin', count: 3 },
        { key: 'quarters', count: 4 },
        { key: 'semis', count: 2 },
        { key: 'final', count: 1 },
    ];
    let code = '';
    for (const { key, count } of rounds) {
        for (let i = 0; i < count; i++) {
            const m = _bracket[key][i];
            if (!m.winner) {
                code += '-';
            } else if (m.a && m.winner.team === m.a.team) {
                code += 'a';
            } else {
                code += 'b';
            }
        }
    }
    return code;
}

function updateURL() {
    const code = encodeBracket();
    const hasPicks = code.replace(/-/g, '').length > 0;
    
    // Update URL
    const url = new URL(window.location);
    if (hasPicks) {
        url.searchParams.set('b', code);
    } else {
        url.searchParams.delete('b');
    }
    history.replaceState(null, '', url);

    // Update LocalStorage — store bracket alongside the current round so stale
    // picks from a previous round are never silently applied to a new bracket.
    try {
        if (hasPicks) {
            localStorage.setItem('euroleague_bracket', code);
            localStorage.setItem('euroleague_bracket_round', String(_currentRound || 0));
        } else {
            localStorage.removeItem('euroleague_bracket');
            localStorage.removeItem('euroleague_bracket_round');
        }
    } catch (e) {
        // Ignore errors if localStorage is blocked (e.g. incognito)
    }
}

function loadFromURL() {
    const params = new URLSearchParams(window.location.search);
    let code = params.get('b');
    
    if (!code) {
        try {
            const storedRound = localStorage.getItem('euroleague_bracket_round');
            // Invalidate if the stored bracket is from a different round
            if (storedRound != null && String(_currentRound || 0) !== storedRound) {
                localStorage.removeItem('euroleague_bracket');
                localStorage.removeItem('euroleague_bracket_round');
            } else {
                code = localStorage.getItem('euroleague_bracket');
            }
        } catch (e) {}
    }

    if (!code) return;

    // Reset first to get clean state, then re-apply real results so
    // seriesScore (used for live odds) is preserved before user picks are applied.
    resetBracketSilent();
    if (_realResults) applyRealResults();

    const rounds = [
        { key: 'playin', count: 3 },
        { key: 'quarters', count: 4 },
        { key: 'semis', count: 2 },
        { key: 'final', count: 1 },
    ];

    let pos = 0;
    let anyPicked = false;
    for (const { key, count } of rounds) {
        for (let i = 0; i < count; i++) {
            if (pos >= code.length) break;
            const ch = code[pos++];
            if (ch === '-') continue;
            const m = _bracket[key][i];
            if (!m.a || !m.b) continue;
            const side = ch === 'a' ? 'a' : 'b';
            m.winner = side === 'a' ? m.a : m.b;
            cascadeForward(key, i, side);
            anyPicked = true;
        }
    }

    if (anyPicked) _hasUserInteracted = true;
    renderBracket();
}

// Same as resetBracket but without rendering or URL update
function resetBracketSilent() {
    _bracket = {
        playin: [
            { a: null, b: null, winner: null },
            { a: null, b: null, winner: null },
            { a: null, b: null, winner: null },
        ],
        quarters: [
            { a: null, b: null, winner: null },
            { a: null, b: null, winner: null },
            { a: null, b: null, winner: null },
            { a: null, b: null, winner: null },
        ],
        semis: [
            { a: null, b: null, winner: null },
            { a: null, b: null, winner: null },
        ],
        final: [
            { a: null, b: null, winner: null },
        ],
    };
    _champion = null;

    _bracket.playin[0].a = _seeded[6];
    _bracket.playin[0].b = _seeded[7];
    _bracket.playin[1].a = _seeded[8];
    _bracket.playin[1].b = _seeded[9];

    _bracket.quarters[0].a = _seeded[0];
    _bracket.quarters[1].a = _seeded[1];
    _bracket.quarters[2].a = _seeded[2];
    _bracket.quarters[2].b = _seeded[5];
    _bracket.quarters[3].a = _seeded[3];
    _bracket.quarters[3].b = _seeded[4];
}

function applyRealResults() {
    if (!_realResults) return;

    const teamByCode = {};
    for (const t of _seeded) teamByCode[t.team] = t;

    // --- Play-In ---
    const pi = _realResults.play_in || {};

    if (pi.game_a && pi.game_a.winner) {
        const m = _bracket.playin[0];
        m.winner = teamByCode[pi.game_a.winner];
        m.score = { home: pi.game_a.home_score, away: pi.game_a.away_score };
        m.locked = true;
        const side = m.winner.team === m.a.team ? 'a' : 'b';
        cascadeForward('playin', 0, side);
    }

    if (pi.game_b && pi.game_b.winner) {
        const m = _bracket.playin[1];
        m.winner = teamByCode[pi.game_b.winner];
        m.score = { home: pi.game_b.home_score, away: pi.game_b.away_score };
        m.locked = true;
        const side = m.winner.team === m.a.team ? 'a' : 'b';
        cascadeForward('playin', 1, side);
    }

    if (pi.game_c && pi.game_c.winner) {
        const m = _bracket.playin[2];
        m.winner = teamByCode[pi.game_c.winner];
        m.score = { home: pi.game_c.home_score, away: pi.game_c.away_score };
        m.locked = true;
        const side = m.winner.team === m.a.team ? 'a' : 'b';
        cascadeForward('playin', 2, side);
    }

    // --- Quarterfinals ---
    const qf = _realResults.qf || {};
    const qfOrder = ['1v8', '2v7', '3v6', '4v5'];
    qfOrder.forEach((label, idx) => {
        const entry = qf[label];
        if (!entry) return;

        const m = _bracket.quarters[idx];
        m.seriesScore = entry.series || [0, 0];
        m.seriesGames = entry.games || [];

        if (entry.winner) {
            m.winner = teamByCode[entry.winner];
            m.locked = true;
            const side = m.winner.team === m.a.team ? 'a' : 'b';
            cascadeForward('quarters', idx, side);
        }
    });

    // --- Semi-Finals ---
    const sf = _realResults.sf || {};
    if (sf.sf1 && sf.sf1.winner) {
        const m = _bracket.semis[0];
        m.winner = teamByCode[sf.sf1.winner];
        m.score = { home: sf.sf1.home_score, away: sf.sf1.away_score };
        m.locked = true;
        cascadeForward('semis', 0, m.winner.team === m.a.team ? 'a' : 'b');
    }
    if (sf.sf2 && sf.sf2.winner) {
        const m = _bracket.semis[1];
        m.winner = teamByCode[sf.sf2.winner];
        m.score = { home: sf.sf2.home_score, away: sf.sf2.away_score };
        m.locked = true;
        cascadeForward('semis', 1, m.winner.team === m.a.team ? 'a' : 'b');
    }

    // --- Final ---
    const fin = _realResults.final || {};
    if (fin.game && fin.winner) {
        const m = _bracket.final[0];
        m.winner = teamByCode[fin.winner];
        m.score = { home: fin.game.home_score, away: fin.game.away_score };
        m.locked = true;
        _champion = m.winner;
    }

    renderBracket();
}

function copyBracketLink() {
    const url = window.location.href;
    navigator.clipboard.writeText(url).then(() => {
        const btn = document.getElementById('share-btn');
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = orig; }, 1500);
    }).catch(() => {
        // Fallback for older browsers
        prompt('Copy this link to share your bracket:', url);
    });
}

// ── Championship Odds History Chart ─────────────────────────────────────
function renderChampionshipOdds(history) {
    const section = document.getElementById('championship-odds-section');
    const container = document.getElementById('championship-odds-chart');
    if (!section || !container || !history || history.length < 2) return;

    section.style.display = '';

    // Deduplicate by label: keep the last entry for each label so each
    // phase appears as a single point on the x-axis (no zigzag).
    const seen = new Map();
    for (const h of history) {
        seen.set(h.label || h.date, h);
    }
    const deduped = Array.from(seen.values());

    const allTeams = new Set();
    for (const entry of deduped) {
        for (const code of Object.keys(entry.odds || {})) allTeams.add(code);
    }

    const traces = [];
    for (const code of allTeams) {
        const xs = deduped.map(h => h.label || h.date);
        const ys = deduped.map(h => (h.odds || {})[code] || 0);
        const color = TEAM_COLORS[code] || '#555';
        const name = (_seeded.find(t => t.team === code) || {}).name || code;
        const isEliminated = ys[ys.length - 1] === 0 && ys.some(v => v > 0);

        traces.push({
            x: xs,
            y: ys,
            name: name,
            mode: 'lines+markers',
            line: {
                color: isEliminated ? '#555' : color,
                width: isEliminated ? 1 : 2.5,
                dash: isEliminated ? 'dot' : 'solid',
            },
            marker: { size: 5 },
            hovertemplate: `<b>${name}</b><br>%{x}<br>%{y:.1f}%<extra></extra>`,
            opacity: isEliminated ? 0.4 : 1,
        });
    }

    traces.sort((a, b) => {
        const aLast = a.y[a.y.length - 1];
        const bLast = b.y[b.y.length - 1];
        if (aLast === 0 && bLast > 0) return 1;
        if (bLast === 0 && aLast > 0) return -1;
        return bLast - aLast;
    });

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: '#0f1117',
        font: { color: '#9ca3af', family: 'Inter' },
        margin: { t: 10, b: 50, l: 50, r: 10 },
        height: 400,
        xaxis: {
            gridcolor: '#2d2e3a',
            tickfont: { size: 11 },
        },
        yaxis: {
            title: 'Championship Probability (%)',
            gridcolor: '#2d2e3a',
            ticksuffix: '%',
            tickfont: { size: 11 },
            rangemode: 'tozero',
        },
        legend: {
            orientation: 'h',
            y: -0.25,
            x: 0.5,
            xanchor: 'center',
            font: { size: 10 },
        },
        hovermode: 'x unified',
    };

    Plotly.newPlot('championship-odds-chart', traces, layout, {
        displayModeBar: false,
        responsive: true,
    });
}

// ── Playoff Recap Cards ──────────────────────────────────────────────────
function renderPlayoffRecaps(recaps) {
    const section = document.getElementById('playoff-recaps-section');
    const container = document.getElementById('playoff-recaps');
    if (!section || !container || !recaps || !recaps.length) return;

    section.style.display = '';

    const teamName = code => {
        const t = _seeded.find(s => s.team === code);
        return t ? t.name : code;
    };

    let html = '<div class="recap-cards">';

    for (const r of recaps) {
        const homeColor = TEAM_COLORS[r.home] || '#555';
        const awayColor = TEAM_COLORS[r.away] || '#555';
        const isHomeWinner = r.winner === r.home;
        const upsetClass = r.is_upset ? ' upset' : '';

        let oddsHTML = '';
        if (r.championship_odds_before && r.championship_odds_after) {
            const teams = [r.home, r.away];
            const deltas = teams.map(t => {
                const before = r.championship_odds_before[t] || 0;
                const after = r.championship_odds_after[t] || 0;
                const diff = after - before;
                const cls = diff >= 0 ? 'positive' : 'negative';
                const sign = diff >= 0 ? '+' : '';
                return `<span class="recap-odds-delta">${teamName(t)}: ${after.toFixed(1)}% (<span class="${cls}">${sign}${diff.toFixed(1)}</span>)</span>`;
            });
            oddsHTML = deltas.join(' &middot; ');
        }

        const slotId = _slotIdForRecapRound(r);
        const replayHTML = r.gamecode
            ? `<a class="recap-replay-link" href="replay.html?season=${_dashSeason}&gamecode=${r.gamecode}" onclick="event.stopPropagation()">▶ Replay</a>`
            : '';
        const cardInner = `<div class="recap-card${upsetClass}">
            <div class="recap-team${isHomeWinner ? '' : ' loser'}">
                <div class="recap-team-color" style="width:4px;height:28px;border-radius:2px;background:${homeColor}"></div>
                <div>
                    <div class="recap-team-name">${teamName(r.home)}</div>
                    <div style="font-size:0.7rem;color:var(--text-muted)">Home</div>
                </div>
            </div>
            <div class="recap-score">${r.home_score} - ${r.away_score}</div>
            <div class="recap-team away${isHomeWinner ? ' loser' : ''}">
                <div>
                    <div class="recap-team-name">${teamName(r.away)}</div>
                    <div style="font-size:0.7rem;color:var(--text-muted)">Away</div>
                </div>
                <div class="recap-team-color" style="width:4px;height:28px;border-radius:2px;background:${awayColor}"></div>
            </div>
            <div class="recap-meta">
                <span class="recap-badge round-badge">${r.round}</span>
                ${r.series_label ? `<span>${r.series_label}</span>` : ''}
                ${r.is_upset ? '<span class="recap-badge upset-badge">UPSET</span>' : ''}
                ${r.pre_game_win_prob != null ? `<span>Win prob: ${r.pre_game_win_prob.toFixed(0)}%</span>` : ''}
                ${r.date ? `<span>${r.date}</span>` : ''}
                ${replayHTML}
                ${oddsHTML ? `<span style="margin-left:auto">${oddsHTML}</span>` : ''}
            </div>
        </div>`;
        html += slotId
            ? `<a class="recap-card-link" href="series.html?id=${slotId}">${cardInner}</a>`
            : cardInner;
    }

    html += '</div>';
    container.innerHTML = html;
}

// ── Path to Title ──────────────────────────────────────────────────────────

let _pttExpanded = null; // currently-expanded team code
let _pathData = null;

function renderPathToTitle(pathData) {
    const section = document.getElementById('path-to-title-section');
    const tbody = document.getElementById('ptt-tbody');
    if (!section || !tbody || !pathData || !pathData.length) return;
    _pathData = pathData;

    section.style.display = '';

    let html = '';
    for (const entry of pathData) {
        html += buildPathRow(entry);
        html += `<tr class="ptt-detail-row" id="ptt-detail-${entry.team}"><td colspan="7"></td></tr>`;
    }
    tbody.innerHTML = html;

    // Wire up click handlers
    tbody.querySelectorAll('.ptt-row').forEach(row => {
        row.addEventListener('click', () => {
            const teamCode = row.dataset.team;
            if (row.classList.contains('ptt-row-eliminated')) return;
            togglePathDetail(teamCode);
        });
    });
}

function buildPathRow(entry) {
    const teamName = (() => {
        const t = _seeded.find(s => s.team === entry.team);
        return t ? t.name : entry.team;
    })();
    const teamColor = TEAM_COLORS[entry.team] || '#555';

    const rowCls = [
        'ptt-row',
        entry.status === 'eliminated' ? 'ptt-row-eliminated' : '',
        entry.status === 'champion' ? 'ptt-row-champion' : '',
    ].filter(Boolean).join(' ');

    const byRound = {};
    for (const r of entry.rounds) byRound[r.round] = r;

    const piCell = pathPlayInCell(byRound['play_in_1'], byRound['play_in_2']);
    const cells = piCell + ['qf', 'sf', 'final'].map(rk => pathRoundCell(byRound[rk])).join('');

    const champPctCls = pathPctCls(entry.championship_odds);
    const hint = entry.status === 'alive' ? '<span class="ptt-expand-hint"></span>' : '';
    const statusTitle = entry.status.charAt(0).toUpperCase() + entry.status.slice(1);

    return `<tr class="${rowCls}" data-team="${entry.team}">
        <td class="ptt-td-team">
            <div class="ptt-team-wrap">
                <div class="ptt-status-dot ${entry.status}" title="${statusTitle}"></div>
                <div class="ptt-team-color" style="background:${teamColor}"></div>
                <span class="ptt-team-name">${teamName}</span>
            </div>
        </td>
        ${cells}
        <td class="ptt-cell-champ ${champPctCls}">${entry.championship_odds.toFixed(1)}%</td>
        <td>${hint}</td>
    </tr>`;
}

function pathRoundCell(round) {
    if (!round || round.status === 'unreached') {
        return '<td class="ptt-cell-dash">—</td>';
    }
    if (round.status === 'completed') {
        const cls = round.actual_result === 'won' ? 'ptt-cell-won' : 'ptt-cell-lost';
        const label = round.actual_result === 'won' ? 'WON' : 'LOST';
        const seriesStr = round.series ? `${round.series[0]}-${round.series[1]}` : '';
        return `<td class="${cls}">${label} ${seriesStr} <span style="font-weight:400;color:var(--text-muted);font-size:0.72rem">vs ${round.actual_opponent}</span></td>`;
    }
    if (round.status === 'in_progress') {
        const s = round.series ? `${round.series[0]}-${round.series[1]}` : '';
        return `<td class="ptt-cell-progress">${s} vs ${round.actual_opponent}</td>`;
    }
    // upcoming
    const pct = round.reach_prob;
    const cls = pathPctCls(pct);
    return `<td class="ptt-cell-pct ${cls}">${pct.toFixed(0)}%</td>`;
}

function pathPlayInCell(pi1, pi2) {
    const unreached = (r) => !r || r.status === 'unreached';
    if (unreached(pi1) && unreached(pi2)) {
        return '<td class="ptt-cell-dash">—</td>';
    }
    if (pi2 && pi2.status === 'completed') {
        return pathRoundCell(pi2);
    }
    if (pi1 && pi1.status === 'completed' && unreached(pi2)) {
        return pathRoundCell(pi1);
    }
    if (pi1 && pi1.status === 'completed' && pi2 && pi2.status === 'upcoming') {
        return pathRoundCell(pi2);
    }
    if (pi1 && pi1.status === 'upcoming') {
        return pathRoundCell(pi1);
    }
    return '<td class="ptt-cell-dash">—</td>';
}

function pathPctCls(pct) {
    if (pct >= 50) return 'ptt-cell-pct-high';
    if (pct >= 20) return 'ptt-cell-pct-mid';
    return 'ptt-cell-pct-low';
}

function renderPathDetailTree(entry, container) {
    const byRound = {};
    const entryRounds = entry.rounds || [];
    for (const r of entryRounds) byRound[r.round] = r;
    const rounds = ['qf', 'sf', 'final']; // Root, then these columns, then trophy
    if (entryRounds.find(r => r.round === 'play_in_2' && r.status !== 'unreached')) {
        rounds.unshift('play_in_2');
    }
    if (entryRounds.find(r => r.round === 'play_in_1' && r.status !== 'unreached')) {
        rounds.unshift('play_in_1');
    }

    // Detect fork-active state: play_in_1 is upcoming and the team is a play-in team.
    const pi1Round = byRound['play_in_1'];
    const seedIdx = _seeded.findIndex(s => s.team === entry.team); // 0-9
    const isSeed78 = seedIdx === 6 || seedIdx === 7;
    const isSeed910 = seedIdx === 8 || seedIdx === 9;
    const forkActive = !!pi1Round && pi1Round.status === 'upcoming' && (isSeed78 || isSeed910);

    const width = rounds.length === 5 ? 1050 : 900;
    const colCount = rounds.length + 2; // team + rounds + trophy
    const colW = width / colCount;
    const rowH = 90;

    // Determine max branches per column to size vertically
    let maxBranches = 1;
    for (const rk of rounds) {
        const r = byRound[rk];
        if (!r) continue;
        if (r.status === 'upcoming' && r.branches) {
            maxBranches = Math.max(maxBranches, r.branches.length);
        }
    }
    let height = Math.max(180, maxBranches * rowH + 80);
    if (forkActive) height += 60; // extra headroom for the skip arc

    const teamColor = TEAM_COLORS[entry.team] || '#60a5fa';
    const centerY = height / 2;

    let svg = `<svg class="ptt-tree-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">`;

    // Root node (team)
    svg += nodeLabel(colW / 2, centerY, entry.team, teamColor, '', '');

    // Precompute column x-coords for fork edge targeting
    const colCx = (idx) => colW * (idx + 1) + colW / 2;
    const pi1Idx = rounds.indexOf('play_in_1');
    const pi2Idx = rounds.indexOf('play_in_2');
    const qfIdx = rounds.indexOf('qf');
    const pi1Cx = pi1Idx >= 0 ? colCx(pi1Idx) : null;
    const pi2Cx = pi2Idx >= 0 ? colCx(pi2Idx) : null;
    const qfCx = qfIdx >= 0 ? colCx(qfIdx) : null;

    const winColor = '#22c55e';
    const loseColor = '#f87171';

    // Draw each round column
    rounds.forEach((rk, idx) => {
        const r = byRound[rk];
        const cx = colW * (idx + 1) + colW / 2;
        const prevX = idx === 0 ? colW / 2 : colW * idx + colW / 2;

        if (!r || r.status === 'unreached') {
            svg += nodeLabel(cx, centerY, '—', '#334155', roundLabel(rk), '');
            svg += edge(prevX + 30, centerY, cx - 30, centerY, '#334155', 0.4);
            return;
        }

        if (r.status === 'completed' || r.status === 'in_progress') {
            const opp = r.actual_opponent;
            const color = r.actual_result === 'won' ? '#22c55e' : (r.actual_result === 'lost' ? '#f87171' : '#60a5fa');
            const topLabel = roundLabel(rk);
            const oppLabel = r.status === 'completed'
                ? `${r.actual_result === 'won' ? 'WON' : 'LOST'} ${r.series ? r.series.join('-') : ''} vs ${opp}`
                : `${r.series ? r.series.join('-') : ''} vs ${opp}`;
            svg += nodeLabel(cx, centerY, opp, color, topLabel, oppLabel);
            svg += edge(prevX + 30, centerY, cx - 30, centerY, color, 0.9);
            return;
        }

        // Upcoming — draw branches
        const branches = r.branches || [];
        const reachPct = r.reach_prob.toFixed(0);
        const winPct = r.win_prob.toFixed(0);
        if (branches.length === 0) {
            svg += nodeLabel(cx, centerY, 'TBD', '#64748b', roundLabel(rk), `${reachPct}% reach · ${winPct}% win`);
            svg += edge(prevX + 30, centerY, cx - 30, centerY, '#64748b', 0.5);
            return;
        }
        const totalH = branches.length * rowH;
        const startY = centerY - totalH / 2 + rowH / 2;

        // Fork-active edge color override:
        //   - pi1 branch edge: always neutral team color (this branch is always reached if play_in_1 happens)
        //   - pi2 branch edges: colored by win/lose for the seed group, dashed
        //   - qf branch edges: for seed 7/8, the #2-seed opponent is reached ONLY via the
        //     pi1-win skip arc (not via pi2), so suppress the default pi2→#2-seed edge.
        branches.forEach((b, bi) => {
            const by = startY + bi * rowH;
            const bColor = TEAM_COLORS[b.opponent] || '#60a5fa';

            let drawDefaultEdge = true;
            if (forkActive && rk === 'play_in_2') {
                if (isSeed78) {
                    // pi2 reached only on LOSE path of Game A → color edges red, dashed
                    svg += forkEdge(prevX + 30, centerY, cx - 30, by, loseColor, 0.85);
                    drawDefaultEdge = false;
                } else if (isSeed910) {
                    // pi2 reached only on WIN path of Game B → color edges green, dashed
                    // But draw them only if we aren't replacing them entirely — we aren't; we draw them here.
                    svg += forkEdge(prevX + 30, centerY, cx - 30, by, winColor, 0.85);
                    drawDefaultEdge = false;
                }
            }
            if (forkActive && rk === 'qf' && isSeed78 && _seeded[1] && b.opponent === _seeded[1].team) {
                // #2 seed is the pi1-win-path QF opponent — the green skip arc already
                // connects pi1 → this branch, so don't draw the default pi2→#2-seed edge.
                drawDefaultEdge = false;
            }
            if (drawDefaultEdge) {
                svg += edge(prevX + 30, centerY, cx - 30, by, bColor, 0.75);
            }
            svg += branchNode(cx, by, b.opponent, bColor,
                `${b.reach_prob_for_opp.toFixed(0)}% opp`,
                `${b.win_prob_vs.toFixed(0)}% win`);
        });
        // Round header above column — two-line so it fits in narrower columns
        svg += `<text x="${cx}" y="14" text-anchor="middle" fill="#cbd5e1" font-size="12" font-weight="800" font-family="Outfit,sans-serif">${roundLabel(rk)}</text>`;
        svg += `<text x="${cx}" y="28" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="600" font-family="Inter,sans-serif">${reachPct}% reach · ${winPct}% win</text>`;
    });

    // Fork overlay: drawn after columns so labels sit on top.
    if (forkActive && pi1Cx !== null) {
        const pi1 = pi1Round;
        const winPct = Math.round(pi1.win_prob);
        const losePct = 100 - winPct;
        // pi1 branch node is at centerY (single branch — the fixed opponent).
        const pi1RightX = pi1Cx + 30;

        if (isSeed78 && qfCx !== null && pi2Cx !== null) {
            // Win edge: skip pi2 entirely, arc over it, land on the seed-#2 QF branch node
            // (the opponent reached via pi1-win). Fall back to top of cluster if not found.
            const qfR = byRound['qf'];
            let qfTopY = centerY;
            if (qfR && qfR.status === 'upcoming' && qfR.branches && qfR.branches.length) {
                const n = qfR.branches.length;
                const qfStartY = centerY - (n * rowH) / 2 + rowH / 2;
                qfTopY = qfStartY; // default fallback = topmost branch
                const winOppCode = _seeded[1] && _seeded[1].team;
                const winQfBranchIdx = winOppCode
                    ? qfR.branches.findIndex(b => b.opponent === winOppCode)
                    : -1;
                if (winQfBranchIdx >= 0) {
                    qfTopY = qfStartY + winQfBranchIdx * rowH;
                }
            }
            const landX = qfCx - 30;
            const landY = qfTopY;
            svg += skipEdge(pi1RightX, centerY, landX, landY, winColor, 0.9);
            // Win label — near start, above
            const winLblX = pi1RightX + 20;
            const winLblY = centerY - 10;
            svg += `<text x="${winLblX}" y="${winLblY}" text-anchor="start" fill="${winColor}" font-size="10" font-weight="700" font-family="Inter,sans-serif">win ${winPct}%</text>`;
            // Lose label — near start, below (paired with the red dashed pi2 edges)
            const loseLblX = pi1RightX + 20;
            const loseLblY = centerY + 18;
            svg += `<text x="${loseLblX}" y="${loseLblY}" text-anchor="start" fill="${loseColor}" font-size="10" font-weight="700" font-family="Inter,sans-serif">lose ${losePct}%</text>`;
        } else if (isSeed910 && pi2Cx !== null) {
            // Win edge label — already drawn as green dashed pi2 edges above.
            const winLblX = pi1RightX + 20;
            const winLblY = centerY - 10;
            svg += `<text x="${winLblX}" y="${winLblY}" text-anchor="start" fill="${winColor}" font-size="10" font-weight="700" font-family="Inter,sans-serif">win ${winPct}%</text>`;
            // Lose edge: terminates at ✗ Eliminated marker near pi2 column (below).
            const elimX = pi2Cx;
            const elimY = Math.min(height - 30, centerY + Math.max(80, (maxBranches * rowH) / 2 + 30));
            svg += forkEdge(pi1RightX, centerY, elimX - 16, elimY, loseColor, 0.85);
            // Elim marker
            svg += `<circle cx="${elimX}" cy="${elimY}" r="16" fill="#334155" opacity="0.35" stroke="#64748b" stroke-width="1.5"/>`;
            svg += `<text x="${elimX}" y="${elimY + 6}" text-anchor="middle" fill="#94a3b8" font-size="18" font-weight="800" font-family="Inter,sans-serif">\u2715</text>`;
            svg += `<text x="${elimX}" y="${elimY + 30}" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="700" font-family="Inter,sans-serif">Eliminated</text>`;
            // Lose label — near start, below
            const loseLblX = pi1RightX + 20;
            const loseLblY = centerY + 18;
            svg += `<text x="${loseLblX}" y="${loseLblY}" text-anchor="start" fill="${loseColor}" font-size="10" font-weight="700" font-family="Inter,sans-serif">lose ${losePct}%</text>`;
        }
    }

    // Trophy column
    const trophyX = colW * (rounds.length + 1) + colW / 2;
    svg += edge(colW * rounds.length + colW / 2 + 30, centerY, trophyX - 30, centerY, '#fbbf24', 0.9);
    svg += `<text x="${trophyX}" y="${centerY - 10}" text-anchor="middle" font-size="28">\u{1F3C6}</text>`;
    svg += `<text x="${trophyX}" y="${centerY + 18}" text-anchor="middle" fill="#fbbf24" font-size="13" font-weight="800" font-family="Outfit,sans-serif">${entry.championship_odds.toFixed(1)}%</text>`;

    svg += '</svg>';
    container.innerHTML = svg;
}

function nodeLabel(cx, cy, code, color, topLabel, bottomLabel) {
    const r = 22;
    let s = '';
    if (topLabel) {
        s += `<text x="${cx}" y="${cy - 30}" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="600" font-family="Inter,sans-serif">${topLabel}</text>`;
    }
    s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" opacity="0.18" stroke="${color}" stroke-width="1.5"/>`;
    s += `<text x="${cx}" y="${cy + 4}" text-anchor="middle" fill="${color}" font-size="11" font-weight="800" font-family="Outfit,sans-serif">${code}</text>`;
    if (bottomLabel) {
        s += `<text x="${cx}" y="${cy + 40}" text-anchor="middle" fill="#cbd5e1" font-size="10" font-family="Inter,sans-serif">${bottomLabel}</text>`;
    }
    return s;
}

function branchNode(cx, cy, code, color, oppLine, winLine) {
    const r = 22;
    let s = '';
    s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" opacity="0.18" stroke="${color}" stroke-width="1.5"/>`;
    s += `<text x="${cx}" y="${cy + 4}" text-anchor="middle" fill="${color}" font-size="11" font-weight="800" font-family="Outfit,sans-serif">${code}</text>`;
    s += `<text x="${cx}" y="${cy + 38}" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="600" font-family="Inter,sans-serif">${oppLine}</text>`;
    s += `<text x="${cx}" y="${cy + 51}" text-anchor="middle" fill="#cbd5e1" font-size="10" font-family="Inter,sans-serif">${winLine}</text>`;
    return s;
}

function edge(x1, y1, x2, y2, color, opacity) {
    // Smooth curve between columns
    const midX = (x1 + x2) / 2;
    return `<path d="M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}" stroke="${color}" stroke-width="1.5" fill="none" opacity="${opacity}"/>`;
}

function forkEdge(x1, y1, x2, y2, color, opacity) {
    // Dashed variant of edge() — used for "possible future" branching paths.
    const midX = (x1 + x2) / 2;
    return `<path d="M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}" stroke="${color}" stroke-width="1.5" fill="none" opacity="${opacity}" stroke-dasharray="4,3"/>`;
}

function skipEdge(x1, y1, x2, y2, color, opacity) {
    // Arc that peaks ABOVE both endpoints — used to "hop over" a column (e.g. pi1 → qf skipping pi2).
    const arcY = Math.min(y1, y2) - 70;
    const midX = (x1 + x2) / 2;
    return `<path d="M${x1},${y1} C${midX - 60},${arcY} ${midX + 60},${arcY} ${x2},${y2}" stroke="${color}" stroke-width="1.5" fill="none" opacity="${opacity}" stroke-dasharray="4,3"/>`;
}

function roundLabel(rk) {
    return { 'play_in_1': 'Play-In G1', 'play_in_2': 'Play-In G2', 'qf': 'QF', 'sf': 'SF', 'final': 'Final' }[rk] || rk;
}

function togglePathDetail(teamCode) {
    const tbody = document.getElementById('ptt-tbody');
    if (!tbody) return;

    // Close currently expanded
    if (_pttExpanded) {
        const prevRow = tbody.querySelector(`.ptt-row[data-team="${_pttExpanded}"]`);
        const prevDetail = document.getElementById(`ptt-detail-${_pttExpanded}`);
        if (prevRow) prevRow.classList.remove('ptt-row-expanded');
        if (prevDetail) {
            const prevTd = prevDetail.querySelector('td');
            prevTd.innerHTML = '';
            prevTd.style.borderLeft = '';
        }
    }

    // Toggle same row = close
    if (_pttExpanded === teamCode) {
        _pttExpanded = null;
        return;
    }

    // Open new row — placeholder content; Task 5 will render the SVG tree
    const row = tbody.querySelector(`.ptt-row[data-team="${teamCode}"]`);
    const detail = document.getElementById(`ptt-detail-${teamCode}`);
    if (!row || !detail) return;
    row.classList.add('ptt-row-expanded');
    const entry = (_pathData || []).find(e => e.team === teamCode);
    const td = detail.querySelector('td');
    td.style.borderLeft = `3px solid ${TEAM_COLORS[teamCode] || '#60a5fa'}`;
    if (entry) {
        renderPathDetailTree(entry, td);
    }
    _pttExpanded = teamCode;
}

// ── Championship Finals History ───────────────────────────────────────────
function renderChampionshipFinals(data) {
    const section = document.getElementById('championship-finals-section');
    const container = document.getElementById('championship-finals-list');
    if (!section || !container || !data || !data.length) return;

    section.style.display = '';

    let html = '';
    data.forEach((entry, i) => {
        const rank = i + 1;
        const winnerIsHome = entry.winner === entry.home;
        const winnerName = winnerIsHome ? entry.home_name : entry.away_name;
        const loserName  = winnerIsHome ? entry.away_name : entry.home_name;
        const winnerCode = entry.winner;
        const loserCode  = winnerIsHome ? entry.away : entry.home;
        const winScore   = winnerIsHome ? entry.home_score : entry.away_score;
        const loseScore  = winnerIsHome ? entry.away_score : entry.home_score;
        const winColor   = TEAM_COLORS[winnerCode] || '#555';
        const loseColor  = TEAM_COLORS[loserCode]  || '#555';

        const comebackPill = entry.max_deficit_overcome > 0
            ? `<span class="cf-pill cf-pill-comeback">Comeback: ${entry.max_deficit_overcome}pts</span>`
            : `<span class="cf-pill cf-pill-wire">Wire-to-wire</span>`;

        const replayLink = entry.has_replay
            ? `<a class="cf-replay" href="replay.html?season=${entry.season}&gamecode=${entry.gamecode}">▶ Replay</a>`
            : '';

        html += `<div class="cf-card">
            <div class="cf-rank">#${rank}</div>
            <div class="cf-season">${entry.season}</div>
            <div class="cf-matchup">
                <div class="cf-teams">
                    <span class="cf-winner" style="color:${winColor}">${winnerName}</span>
                    <span style="color:var(--text-muted);font-weight:400;margin:0 0.3rem">vs</span>
                    <span class="cf-loser" style="color:${loseColor}">${loserName}</span>
                    <span style="color:var(--text-muted);font-weight:400;margin-left:0.4rem">${winScore}–${loseScore}</span>
                </div>
                <div class="cf-stats">
                    <span class="cf-pill cf-pill-lead">${entry.lead_changes} lead changes</span>
                    <span class="cf-pill cf-pill-tied">${entry.times_tied} tied</span>
                    ${comebackPill}
                </div>
            </div>
            ${replayLink}
        </div>`;
    });

    container.innerHTML = html;
}

// ── Boot ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);

// Redraw connectors on resize
let _resizeTimer;
window.addEventListener('resize', () => {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(drawConnectors, 150);
});

// ── Player of the Playoffs ────────────────────────────────────────────────
let _poffAll = [];
let _poffSort = { col: 'avg_pir', asc: false };
let _poffTeamFilter = '';
let _poffShowAll = false;
const POFF_PAGE = 15;

function renderPlayoffPlayerStats(players) {
    const section = document.getElementById('playoff-players-section');
    const filter  = document.getElementById('playoff-players-team-filter');
    if (!section || !players.length) return;

    _poffAll = players;
    section.style.display = '';

    // Populate team filter dropdown
    const teams = [...new Set(players.map(p => p.team))].sort();
    teams.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t;
        filter.appendChild(opt);
    });

    _renderPoffTable();
}

function _renderPoffTable() {
    const tbody = document.getElementById('poff-tbody');
    const btn   = document.getElementById('poff-show-all-btn');
    if (!tbody) return;

    let rows = _poffAll.filter(p => !_poffTeamFilter || p.team === _poffTeamFilter);

    rows = [...rows].sort((a, b) => {
        const va = a[_poffSort.col], vb = b[_poffSort.col];
        if (typeof va === 'string') return _poffSort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
        return _poffSort.asc ? va - vb : vb - va;
    });

    const total   = rows.length;
    const visible = _poffShowAll ? rows : rows.slice(0, POFF_PAGE);

    tbody.innerHTML = visible.map((p, i) => {
        const color = TEAM_COLORS[p.team] || '#6b7280';
        return `<tr>
            <td style="color:var(--text-muted);font-size:0.78rem">${i + 1}</td>
            <td>
                <div class="poff-td-player">
                    <span class="poff-player-dot" style="background:${color}"></span>
                    <div>
                        <div class="poff-name">${p.name}</div>
                        <div class="poff-team">${p.team}</div>
                    </div>
                </div>
            </td>
            <td>${p.gp}</td>
            <td><strong>${p.avg_pir}</strong></td>
            <td>${p.avg_pts}</td>
            <td>${p.avg_reb}</td>
            <td>${p.avg_ast}</td>
            <td>${p.avg_stl}</td>
            <td>${p.avg_blk}</td>
        </tr>`;
    }).join('');

    // Show/hide expand button
    if (total > POFF_PAGE) {
        btn.style.display = '';
        btn.textContent = _poffShowAll ? `Show top ${POFF_PAGE}` : `Show all ${total} players`;
    } else {
        btn.style.display = 'none';
    }

    // Update sort indicator on headers
    const allTh = document.querySelectorAll('.poff-table thead th');
    const colMap = ['', 'name', 'gp', 'avg_pir', 'avg_pts', 'avg_reb', 'avg_ast', 'avg_stl', 'avg_blk'];
    allTh.forEach((th, i) => {
        th.classList.remove('poff-sort-active');
        th.textContent = th.textContent.replace(/ [▲▼]$/, '');
        if (colMap[i] === _poffSort.col) {
            th.classList.add('poff-sort-active');
            th.textContent += _poffSort.asc ? ' ▲' : ' ▼';
        }
    });
}

window.sortPlayoffPlayers = function(col) {
    _poffSort.asc = _poffSort.col === col ? !_poffSort.asc : col === 'name';
    _poffSort.col = col;
    _renderPoffTable();
};

window.filterPlayoffPlayers = function() {
    const el = document.getElementById('playoff-players-team-filter');
    _poffTeamFilter = el ? el.value : '';
    _poffShowAll = false;
    _renderPoffTable();
};

window.togglePlayoffPlayersAll = function() {
    _poffShowAll = !_poffShowAll;
    _renderPoffTable();
};
