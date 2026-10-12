/* network.js — Assist / Playmaking Network */

let _data = null;       // full JSON
let _selected = null;   // current team code
let _pinned = null;     // pinned player id

// ── Boot ─────────────────────────────────────────────────────────────────────
fetchJSON('data/current/assist_network.json')
    .then(data => {
        _data = data;
        renderTeamGrid();
        renderCombosTable(data.top_combos);
        renderPlaymakersTable(data.top_playmakers);
        restoreFromURL();
    })
    .catch(err => {
        console.error('Failed to load assist network:', err);
        document.getElementById('load-error').classList.remove('hidden');
    });

// ── URL state ────────────────────────────────────────────────────────────────
function restoreFromURL() {
    const params = new URLSearchParams(location.search);
    const team = params.get('team');
    if (team && _data.teams[team]) {
        selectTeam(team);
    } else {
        // Default: first team alphabetically
        const first = Object.keys(_data.teams).sort()[0];
        if (first) selectTeam(first);
    }
}

function updateURL(teamCode) {
    const url = new URL(location);
    url.searchParams.set('team', teamCode);
    history.replaceState(null, '', url);
}

// ── Team grid ────────────────────────────────────────────────────────────────
function renderTeamGrid() {
    const grid = document.getElementById('team-grid');
    const codes = Object.keys(_data.teams).sort((a, b) => {
        const na = TEAM_NAMES[a] || a;
        const nb = TEAM_NAMES[b] || b;
        return na.localeCompare(nb);
    });
    grid.innerHTML = codes.map(code => {
        const color = teamInk(code);
        const name = TEAM_NAMES[code] || code;
        return `<div class="team-chip" id="chip-${code}"
                     onclick="selectTeam('${code}')"
                     style="border-top:3px solid ${color}99">
            <span class="team-chip-name" style="color:${color}">${name}</span>
        </div>`;
    }).join('');
}

function selectTeam(code) {
    if (!_data || !_data.teams[code]) return;
    _selected = code;
    _pinned = null;

    // Highlight chip
    document.querySelectorAll('.team-chip').forEach(c => c.classList.remove('selected'));
    const chip = document.getElementById('chip-' + code);
    if (chip) chip.classList.add('selected');

    // Show chord card
    document.getElementById('chord-card').style.display = '';
    document.getElementById('chord-title').textContent =
        (TEAM_NAMES[code] || code) + ' — Assist Network';

    // Hide player detail
    document.getElementById('player-detail').classList.remove('visible');

    updateURL(code);
    renderChord(_data.teams[code], code);
}

// ── Chord diagram rendering ──────────────────────────────────────────────────

function renderChord(teamData, teamCode) {
    const svg = document.getElementById('chord-svg');
    svg.innerHTML = '';

    const cx = 270, cy = 270, outerR = 240, innerR = 220;
    const teamColor = getTeamColor(teamCode);

    // Top 8 by assist involvement
    const players = teamData.players
        .map(p => ({ ...p, involvement: p.ast_given + p.ast_received }))
        .sort((a, b) => b.involvement - a.involvement)
        .slice(0, 8);

    const playerIds = new Set(players.map(p => p.id));

    // Filter edges to only include top-8 players on both sides
    const edges = teamData.edges.filter(e => playerIds.has(e.from) && playerIds.has(e.to));

    const totalInvolvement = players.reduce((s, p) => s + p.involvement, 0);
    if (totalInvolvement === 0) {
        svg.innerHTML = '<text x="270" y="270" text-anchor="middle" fill="#6b7280" font-size="14">No assist data</text>';
        return;
    }

    // ── Compute arc angles ───────────────────────────────────────────────────
    const GAP_DEG = 3;
    const totalGap = GAP_DEG * players.length;
    const availableDeg = 360 - totalGap;

    let angle = 0;
    const arcs = players.map(p => {
        const span = (p.involvement / totalInvolvement) * availableDeg;
        const start = angle;
        const end = angle + span;
        angle = end + GAP_DEG;
        return { ...p, startDeg: start, endDeg: end, midDeg: (start + end) / 2 };
    });

    // Player color: HSL rotation from team base hue
    const baseHue = getHue(teamColor);
    arcs.forEach((a, i) => {
        const hueOffset = (i * 37) % 360; // golden-angle-ish spread
        a.color = `hsl(${(baseHue + hueOffset) % 360}, 65%, 55%)`;
    });

    const arcById = {};
    arcs.forEach(a => { arcById[a.id] = a; });

    // ── Draw outer arcs ──────────────────────────────────────────────────────
    const arcGroup = svgEl('g', { class: 'chord-arcs' });
    arcs.forEach(a => {
        const path = describeArc(cx, cy, outerR, innerR, a.startDeg, a.endDeg);
        const el = svgEl('path', {
            d: path,
            fill: a.color,
            class: 'chord-arc',
            'data-player': a.id,
        });
        el.addEventListener('mouseenter', () => highlightPlayer(a.id, false));
        el.addEventListener('mouseleave', () => { if (_pinned !== a.id) clearHighlight(); });
        el.addEventListener('click', () => pinPlayer(a.id));
        arcGroup.appendChild(el);
    });
    svg.appendChild(arcGroup);

    // ── Draw ribbons ─────────────────────────────────────────────────────────
    const ribbonGroup = svgEl('g', { class: 'chord-ribbons' });

    // Pre-compute sub-arc positions: each edge eats a portion of the player's arc
    const arcUsed = {};
    arcs.forEach(a => { arcUsed[a.id] = a.startDeg; });

    // Sort edges by count descending so larger ribbons draw first (behind)
    const sortedEdges = [...edges].sort((a, b) => b.count - a.count);

    sortedEdges.forEach(e => {
        const fromArc = arcById[e.from];
        const toArc = arcById[e.to];
        if (!fromArc || !toArc) return;

        // Width on passer side: proportional to count / passer involvement
        const fromSpan = ((e.count / fromArc.involvement) * (fromArc.endDeg - fromArc.startDeg));
        const fromStart = arcUsed[e.from];
        const fromEnd = fromStart + fromSpan;
        arcUsed[e.from] = fromEnd;

        // Width on scorer side
        const toSpan = ((e.count / toArc.involvement) * (toArc.endDeg - toArc.startDeg));
        const toStart = arcUsed[e.to];
        const toEnd = toStart + toSpan;
        arcUsed[e.to] = toEnd;

        const d = describeRibbon(cx, cy, innerR, fromStart, fromEnd, toStart, toEnd);
        const ribbon = svgEl('path', {
            d: d,
            fill: fromArc.color,
            'fill-opacity': '0.35',
            stroke: fromArc.color,
            'stroke-width': '0.5',
            class: 'chord-ribbon',
            'data-from': e.from,
            'data-to': e.to,
        });
        ribbon.addEventListener('mouseenter', (evt) => showTooltip(e, fromArc, toArc, evt));
        ribbon.addEventListener('mousemove', (evt) => moveTooltip(evt));
        ribbon.addEventListener('mouseleave', hideTooltip);
        ribbonGroup.appendChild(ribbon);
    });
    svg.appendChild(ribbonGroup);

    // ── Draw labels ──────────────────────────────────────────────────────────
    const labelGroup = svgEl('g', { class: 'chord-labels' });
    arcs.forEach(a => {
        const labelR = outerR + 14;
        const midRad = degToRad(a.midDeg);
        const x = cx + labelR * Math.cos(midRad);
        const y = cy + labelR * Math.sin(midRad);
        const anchor = (a.midDeg > 90 && a.midDeg < 270) ? 'end' : 'start';

        // Format name: "LAST, F." → "Last"
        const display = formatPlayerName(a.name);
        const rot = (a.midDeg > 90 && a.midDeg < 270) ? a.midDeg + 180 : a.midDeg;

        const label = svgEl('text', {
            x: x, y: y,
            'text-anchor': anchor,
            'dominant-baseline': 'central',
            transform: `rotate(${rot},${x},${y})`,
            class: 'chord-label',
            'data-player': a.id,
            fill: a.color,
        });
        label.textContent = display;
        label.addEventListener('mouseenter', () => highlightPlayer(a.id, false));
        label.addEventListener('mouseleave', () => { if (_pinned !== a.id) clearHighlight(); });
        label.addEventListener('click', () => pinPlayer(a.id));
        labelGroup.appendChild(label);
    });
    svg.appendChild(labelGroup);
}

// ── SVG geometry helpers ─────────────────────────────────────────────────────

function degToRad(deg) { return (deg - 90) * Math.PI / 180; }

function polarToCart(cx, cy, r, deg) {
    const rad = degToRad(deg);
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx, cy, outerR, innerR, startDeg, endDeg) {
    const s1 = polarToCart(cx, cy, outerR, startDeg);
    const e1 = polarToCart(cx, cy, outerR, endDeg);
    const s2 = polarToCart(cx, cy, innerR, endDeg);
    const e2 = polarToCart(cx, cy, innerR, startDeg);
    const large = (endDeg - startDeg) > 180 ? 1 : 0;
    return [
        `M ${s1.x} ${s1.y}`,
        `A ${outerR} ${outerR} 0 ${large} 1 ${e1.x} ${e1.y}`,
        `L ${s2.x} ${s2.y}`,
        `A ${innerR} ${innerR} 0 ${large} 0 ${e2.x} ${e2.y}`,
        'Z',
    ].join(' ');
}

function describeRibbon(cx, cy, r, fromStart, fromEnd, toStart, toEnd) {
    const p1 = polarToCart(cx, cy, r, fromStart);
    const p2 = polarToCart(cx, cy, r, fromEnd);
    const p3 = polarToCart(cx, cy, r, toStart);
    const p4 = polarToCart(cx, cy, r, toEnd);
    return [
        `M ${p1.x} ${p1.y}`,
        `Q ${cx} ${cy} ${p3.x} ${p3.y}`,
        `A ${r} ${r} 0 0 1 ${p4.x} ${p4.y}`,
        `Q ${cx} ${cy} ${p2.x} ${p2.y}`,
        `A ${r} ${r} 0 0 1 ${p1.x} ${p1.y}`,
        'Z',
    ].join(' ');
}

function svgEl(tag, attrs) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
}

function getHue(hex) {
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0;
    if (max !== min) {
        const d = max - min;
        if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        else if (max === g) h = ((b - r) / d + 2) / 6;
        else h = ((r - g) / d + 4) / 6;
    }
    return Math.round(h * 360);
}

function formatPlayerName(raw) {
    // "SLOUKAS, KOSTAS" → "Sloukas"
    const parts = raw.split(',');
    const last = (parts[0] || '').trim();
    return last.charAt(0).toUpperCase() + last.slice(1).toLowerCase();
}

// ── Highlight / pin ──────────────────────────────────────────────────────────

function highlightPlayer(playerId, isPinned) {
    const svg = document.getElementById('chord-svg');

    // Fade all ribbons, then highlight connected ones
    svg.querySelectorAll('.chord-ribbon').forEach(r => {
        const from = r.getAttribute('data-from');
        const to = r.getAttribute('data-to');
        if (from === playerId || to === playerId) {
            r.style.opacity = '1';
            r.setAttribute('fill-opacity', '0.55');
        } else {
            r.style.opacity = '0.08';
        }
    });

    // Fade arcs not connected to this player
    const connectedIds = new Set([playerId]);
    svg.querySelectorAll('.chord-ribbon').forEach(r => {
        const from = r.getAttribute('data-from');
        const to = r.getAttribute('data-to');
        if (from === playerId) connectedIds.add(to);
        if (to === playerId) connectedIds.add(from);
    });

    svg.querySelectorAll('.chord-arc').forEach(a => {
        a.style.opacity = connectedIds.has(a.getAttribute('data-player')) ? '1' : '0.2';
    });

    svg.querySelectorAll('.chord-label').forEach(l => {
        l.style.opacity = connectedIds.has(l.getAttribute('data-player')) ? '1' : '0.2';
    });
}

function clearHighlight() {
    if (_pinned) return; // don't clear if a player is pinned
    const svg = document.getElementById('chord-svg');
    svg.querySelectorAll('.chord-ribbon').forEach(r => {
        r.style.opacity = '';
        r.setAttribute('fill-opacity', '0.35');
    });
    svg.querySelectorAll('.chord-arc').forEach(a => { a.style.opacity = ''; });
    svg.querySelectorAll('.chord-label').forEach(l => { l.style.opacity = ''; });
}

function pinPlayer(playerId) {
    if (_pinned === playerId) {
        // Unpin
        _pinned = null;
        clearHighlight();
        document.getElementById('player-detail').classList.remove('visible');
        return;
    }
    _pinned = playerId;
    highlightPlayer(playerId, true);
    showPlayerDetail(playerId);
}

// ── Tooltip ──────────────────────────────────────────────────────────────────

function showTooltip(edge, fromArc, toArc, evt) {
    const tip = document.getElementById('chord-tooltip');
    const passer = formatPlayerName(fromArc.name);
    const scorer = formatPlayerName(toArc.name);

    // Compute percentages
    const passerPct = fromArc.ast_given > 0 ? (edge.count / fromArc.ast_given * 100).toFixed(1) : '0.0';
    const scorerPct = toArc.ast_received > 0 ? (edge.count / toArc.ast_received * 100).toFixed(1) : '0.0';
    const passerGP = fromArc.gp || 1;
    const perGame = (edge.count / passerGP).toFixed(1);

    tip.innerHTML = `
        <div class="tt-title">${passer} → ${scorer}</div>
        <div class="tt-row"><span class="tt-label">Assists</span><span class="tt-value">${edge.count}</span></div>
        <div class="tt-row"><span class="tt-label">2PT / 3PT</span><span class="tt-value">${edge.fg2} / ${edge.fg3}</span></div>
        <div class="tt-row"><span class="tt-label">Per game</span><span class="tt-value">${perGame}</span></div>
        <div class="tt-row"><span class="tt-label">% of ${passer}'s AST</span><span class="tt-value">${passerPct}%</span></div>
        <div class="tt-row"><span class="tt-label">% of ${scorer}'s assisted FG</span><span class="tt-value">${scorerPct}%</span></div>
    `;
    tip.style.display = 'block';
    moveTooltip(evt);
}

function moveTooltip(evt) {
    const tip = document.getElementById('chord-tooltip');
    const pad = 12;
    let x = evt.clientX + pad;
    let y = evt.clientY + pad;
    // Keep on screen
    const rect = tip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth) x = evt.clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight) y = evt.clientY - rect.height - pad;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
}

function hideTooltip() {
    document.getElementById('chord-tooltip').style.display = 'none';
}

// ── Player detail card ───────────────────────────────────────────────────────

function showPlayerDetail(playerId) {
    if (!_data || !_selected) return;
    const team = _data.teams[_selected];
    const player = team.players.find(p => p.id === playerId);
    if (!player) return;

    const color = teamInk(_selected);
    const teamName = TEAM_NAMES[_selected] || _selected;

    document.getElementById('pd-name').textContent = formatPlayerName(player.name);
    const badge = document.getElementById('pd-badge');
    badge.textContent = teamName;
    badge.style.background = color + '22';
    badge.style.color = color;

    // Assists given section
    const givenEdges = team.edges
        .filter(e => e.from === playerId)
        .sort((a, b) => b.count - a.count);

    const givenHTML = `
        <div class="pd-stat-row">
            <span class="pd-stat-label">Total</span>
            <span class="pd-stat-value">${player.ast_given}</span>
        </div>
        <div class="pd-stat-row">
            <span class="pd-stat-label">Per game</span>
            <span class="pd-stat-value">${player.ast_per_game}</span>
        </div>
        <div class="pd-stat-row">
            <span class="pd-stat-label">Unique targets</span>
            <span class="pd-stat-value">${player.unique_targets}</span>
        </div>
        <h4 style="margin-top:0.75rem;">Top Targets</h4>
        <ul class="pd-target-list">
            ${givenEdges.slice(0, 5).map(e => {
                const scorer = team.players.find(p => p.id === e.to);
                const name = scorer ? formatPlayerName(scorer.name) : '?';
                return `<li><span>${name}</span><span class="pd-stat-value">${e.count} (${e.fg2}×2PT, ${e.fg3}×3PT)</span></li>`;
            }).join('')}
        </ul>
    `;
    document.getElementById('pd-given').innerHTML = givenHTML;

    // Assists received section
    const receivedEdges = team.edges
        .filter(e => e.to === playerId)
        .sort((a, b) => b.count - a.count);

    const totalReceived = receivedEdges.reduce((s, e) => s + e.count, 0);

    const receivedHTML = `
        <div class="pd-stat-row">
            <span class="pd-stat-label">Assisted baskets</span>
            <span class="pd-stat-value">${totalReceived}</span>
        </div>
        <h4 style="margin-top:0.75rem;">Top Feeders</h4>
        <ul class="pd-target-list">
            ${receivedEdges.slice(0, 5).map(e => {
                const passer = team.players.find(p => p.id === e.from);
                const name = passer ? formatPlayerName(passer.name) : '?';
                return `<li><span>${name}</span><span class="pd-stat-value">${e.count}</span></li>`;
            }).join('')}
        </ul>
    `;
    document.getElementById('pd-received').innerHTML = receivedHTML;

    document.getElementById('player-detail').classList.add('visible');
    document.getElementById('player-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── League-wide tables ───────────────────────────────────────────────────────

const COMBO_COLS = [
    { key: '#',        label: '#',       fmt: (_, i) => i + 1 },
    { key: 'passer',   label: 'Passer',  fmt: v => formatPlayerName(v) },
    { key: 'scorer',   label: 'Scorer',  fmt: v => formatPlayerName(v) },
    { key: 'team',     label: 'Team',    fmt: v => `<span class="tbl-team-badge" style="background:${teamInk(v)}22;color:${teamInk(v)}">${v}</span>` },
    { key: 'count',    label: 'AST',     fmt: v => v },
    { key: 'fg2',      label: '2PT',     fmt: v => v },
    { key: 'fg3',      label: '3PT',     fmt: v => v },
    { key: 'per_game', label: '/Game',   fmt: v => v.toFixed(2) },
];

const PLAYMAKER_COLS = [
    { key: '#',              label: '#',          fmt: (_, i) => i + 1 },
    { key: 'player',         label: 'Player',     fmt: v => formatPlayerName(v) },
    { key: 'team',           label: 'Team',       fmt: v => `<span class="tbl-team-badge" style="background:${teamInk(v)}22;color:${teamInk(v)}">${v}</span>` },
    { key: 'ast',            label: 'AST',        fmt: v => v },
    { key: 'per_game',       label: '/Game',      fmt: v => v.toFixed(1) },
    { key: 'unique_targets', label: 'Targets',    fmt: v => v },
    { key: 'top_target',     label: 'Top Target', fmt: v => formatPlayerName(v) },
];

let _comboSort  = { key: 'count', asc: false };
let _makerSort  = { key: 'ast',   asc: false };

function renderCombosTable(data) {
    renderSortableTable('combos-table', data, COMBO_COLS, _comboSort, (newKey) => {
        if (_comboSort.key === newKey) _comboSort.asc = !_comboSort.asc;
        else { _comboSort.key = newKey; _comboSort.asc = false; }
        renderCombosTable(_data.top_combos);
    }, (row) => {
        // Click row → navigate to team and highlight passer
        selectTeam(row.team);
        window.scrollTo({ top: 0, behavior: 'smooth' });
        setTimeout(() => pinPlayer(row.passer_id), 100);
    });
}

function renderPlaymakersTable(data) {
    renderSortableTable('playmakers-table', data, PLAYMAKER_COLS, _makerSort, (newKey) => {
        if (_makerSort.key === newKey) _makerSort.asc = !_makerSort.asc;
        else { _makerSort.key = newKey; _makerSort.asc = false; }
        renderPlaymakersTable(_data.top_playmakers);
    }, (row) => {
        // Click row → navigate to team and highlight player
        selectTeam(row.team);
        window.scrollTo({ top: 0, behavior: 'smooth' });
        setTimeout(() => pinPlayer(row.player_id), 100);
    });
}

function renderSortableTable(tableId, data, cols, sortState, onSort, onRowClick) {
    const table = document.getElementById(tableId);
    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');

    // Sort data
    const sorted = [...data];
    const sk = sortState.key;
    if (sk && sk !== '#') {
        sorted.sort((a, b) => {
            const va = a[sk], vb = b[sk];
            if (typeof va === 'number') return sortState.asc ? va - vb : vb - va;
            return sortState.asc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
        });
    }

    // Render thead
    thead.innerHTML = '<tr>' + cols.map(c => {
        const active = sortState.key === c.key ? ' sort-active' : '';
        const arrow = sortState.key === c.key ? (sortState.asc ? ' ▲' : ' ▼') : '';
        if (c.key === '#') return `<th>${c.label}</th>`;
        return `<th class="sortable-th${active}" data-key="${c.key}">${c.label}${arrow}</th>`;
    }).join('') + '</tr>';

    // Attach sort listeners
    thead.querySelectorAll('.sortable-th').forEach(th => {
        th.addEventListener('click', () => onSort(th.dataset.key));
    });

    // Render tbody
    tbody.innerHTML = sorted.map((row, i) => {
        const cells = cols.map(c => `<td>${c.fmt(row[c.key], i)}</td>`).join('');
        return `<tr>${cells}</tr>`;
    }).join('');

    // Attach row click
    if (onRowClick) {
        tbody.querySelectorAll('tr').forEach((tr, i) => {
            tr.addEventListener('click', () => onRowClick(sorted[i]));
        });
    }
}
