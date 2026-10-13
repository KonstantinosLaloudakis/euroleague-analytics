// records.js
const DATA_URL      = 'data/current/player_career_stats.json';
const MIN_GP_SEASON = 15;
const TOP_INITIAL   = 10;
const TOP_EXTENDED  = 25;
const LAZY_URLS     = {
    comebacks: 'data/current/comebacks.json',
    highs:     'data/current/game_highs.json',
    winners:   'data/current/game_winners.json',
};
const PHASE_LABEL   = { RS: 'RS', TS: 'Top 16', PO: 'Playoffs', PI: 'Play-In', FF: 'Final Four' };

let _data        = null; // cached raw JSON — reused on filter changes, no re-fetch
let _rankings    = null; // cached computed rankings
let _activeTab   = 'scoring';
let _minGpCareer = 100;
let _lazy        = {};   // tab key -> JSON (or {error:true}), loaded on first tab click

const TABS = [
    { key: 'scoring',    label: 'Scoring',    careerLabel: 'Career Points',   careerSub: 'Accumulated total',   avgLabel: 'Career Avg PPG', avgSub: 'GP-weighted average', avgStat: 'ppg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season PPG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'playmaking', label: 'Playmaking', careerLabel: 'Career Assists',  careerSub: 'Accumulated total',   avgLabel: 'Career Avg APG', avgSub: 'GP-weighted average', avgStat: 'apg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season APG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'rebounding', label: 'Rebounding', careerLabel: 'Career Rebounds', careerSub: 'Accumulated total',   avgLabel: 'Career Avg RPG', avgSub: 'GP-weighted average', avgStat: 'rpg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season RPG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'defense',    label: 'Defense',    careerLabel: 'Career Steals',   careerSub: 'Accumulated total',   avgLabel: 'Career Avg SPG', avgSub: 'GP-weighted average', avgStat: 'spg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season SPG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'efficiency', label: 'Efficiency', careerLabel: 'Career Avg PIR',  careerSub: 'GP-weighted average', avgLabel: 'Career Avg 2P%', avgSub: 'GP-weighted average', avgStat: 'fg2_pct', avgFmt: v => v.toFixed(1) + '%', seasonLabel: 'Best Season PIR', seasonSub: 'Per-game average',   fmtC: v => v.toFixed(1),                   fmtS: v => v.toFixed(1) },
    { key: 'comebacks',  label: 'Comebacks' },
    { key: 'highs',      label: 'Game Highs' },
    { key: 'winners',    label: 'Game-Winners' },
];

// ── Entry point ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    try {
        _data = await fetch(DATA_URL).then(r => r.json());
    } catch {
        document.getElementById('records-content').innerHTML =
            '<p class="error-msg">Could not load player data. Run the data pipeline first.</p>';
        return;
    }
    document.title = 'All-Time Records — EL Analytics';
    _rankings = computeRankings(_data, _minGpCareer);
    renderPage();
});

// ── Compute all rankings ───────────────────────────────────────────────────────
function computeRankings(data, minGpCareer) {
    const players = Object.entries(data.players);
    const careerPts = [], careerAst = [], careerReb = [], careerStl = [], careerPIR = [];
    const avgPPG = [], avgAPG = [], avgRPG = [], avgSPG = [], avgFg2 = [];
    const szPPG = [], szAPG = [], szRPG = [], szSPG = [], szPIR = [];

    for (const [code, p] of players) {
        const totalGp = p.career?.gp || 0;

        if (totalGp >= minGpCareer) {
            const base = { code, name: p.name, image: p.image, seasons: p.seasons.length, gp: totalGp };
            // Use pre-computed totals from the JSON (exact, not re-derived from rounded per-game)
            if (p.career.total_pts != null) careerPts.push({ ...base, value: Math.round(p.career.total_pts) });
            if (p.career.total_ast != null) careerAst.push({ ...base, value: Math.round(p.career.total_ast) });
            if (p.career.total_reb != null) careerReb.push({ ...base, value: Math.round(p.career.total_reb) });
            if (p.career.total_stl != null) careerStl.push({ ...base, value: Math.round(p.career.total_stl) });
            if (p.career.pir       != null) careerPIR.push({ ...base, value: p.career.pir });
            if (p.career.ppg    != null) avgPPG.push({ ...base, value: p.career.ppg });
            if (p.career.apg    != null) avgAPG.push({ ...base, value: p.career.apg });
            if (p.career.rpg    != null) avgRPG.push({ ...base, value: p.career.rpg });
            if (p.career.spg    != null) avgSPG.push({ ...base, value: p.career.spg });
            if (p.career.fg2_pct != null) avgFg2.push({ ...base, value: p.career.fg2_pct });
        }

        for (const s of p.seasons) {
            if (!s.gp || s.gp < MIN_GP_SEASON) continue;
            const base = { code, name: p.name, image: p.image, season: s.season, team_code: s.team_code, team_name: s.team_name, gp: s.gp };
            if (s.ppg != null) szPPG.push({ ...base, value: s.ppg });
            if (s.apg != null) szAPG.push({ ...base, value: s.apg });
            if (s.rpg != null) szRPG.push({ ...base, value: s.rpg });
            if (s.spg != null) szSPG.push({ ...base, value: s.spg });
            if (s.pir != null) szPIR.push({ ...base, value: s.pir });
        }
    }

    const top = arr => arr.sort((a, b) => b.value - a.value).slice(0, TOP_EXTENDED);
    return {
        scoring:    { career: top(careerPts), avg: top(avgPPG), season: top(szPPG) },
        playmaking: { career: top(careerAst), avg: top(avgAPG), season: top(szAPG) },
        rebounding: { career: top(careerReb), avg: top(avgRPG), season: top(szRPG) },
        defense:    { career: top(careerStl), avg: top(avgSPG), season: top(szSPG) },
        efficiency: { career: top(careerPIR), avg: top(avgFg2), season: top(szPIR) },
    };
}

// ── Render full page ───────────────────────────────────────────────────────────
function renderPage() {
    const tabButtons = TABS.map(t =>
        `<button class="cat-tab${t.key === _activeTab ? ' active' : ''}" data-tab="${t.key}">${t.label}</button>`
    ).join('');
    const content = document.getElementById('records-content');

    const lazyRender = { comebacks: renderComebacks, highs: renderHighs, winners: renderWinners }[_activeTab];
    if (lazyRender) {
        content.innerHTML = `<div class="cat-tabs">${tabButtons}</div>${lazyRender(_lazy[_activeTab])}`;
    } else {
        const filterHtml = `
    <div class="filter-row">
      <span>Career minimum:</span>
      <select id="min-gp-select">
        <option value="50"${_minGpCareer ===  50 ? ' selected' : ''}>50 GP</option>
        <option value="100"${_minGpCareer === 100 ? ' selected' : ''}>100 GP</option>
        <option value="200"${_minGpCareer === 200 ? ' selected' : ''}>200 GP</option>
        <option value="0"${_minGpCareer ===   0 ? ' selected' : ''}>No minimum</option>
      </select>
      <span class="filter-legend">· Career totals = Σ(stat × GP) &nbsp;·&nbsp; Career averages = GP-weighted &nbsp;·&nbsp; Season min: ${MIN_GP_SEASON} GP</span>
    </div>`;

        const tab  = TABS.find(t => t.key === _activeTab);
        const data = _rankings[_activeTab];

        content.innerHTML = `
    <div class="cat-tabs">${tabButtons}</div>
    ${filterHtml}
    <div class="records-grid">
      ${renderCard(data.career, tab.careerLabel, tab.careerSub, 'career', tab.fmtC)}
      ${renderCard(data.avg,    tab.avgLabel,    tab.avgSub,    'avg',    tab.avgFmt)}
      ${renderCard(data.season, tab.seasonLabel, tab.seasonSub, 'season', tab.fmtS)}
    </div>`;

        document.getElementById('min-gp-select').addEventListener('change', e => {
            _minGpCareer = Number(e.target.value);
            _rankings = computeRankings(_data, _minGpCareer); // reuse cached _data, no re-fetch
            renderPage();
        });
    }

    document.querySelectorAll('.cat-tab').forEach(btn => {
        btn.addEventListener('click', async () => {
            const key = btn.dataset.tab;
            if (LAZY_URLS[key] && !_lazy[key]) _lazy[key] = await loadJson(LAZY_URLS[key]);
            _activeTab = key;
            renderPage();
        });
    });

    document.querySelectorAll('.show-more-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.record-card').querySelectorAll('tr.hidden').forEach(tr => tr.classList.remove('hidden'));
            btn.remove();
        });
    });
}

// ── Render one record card ─────────────────────────────────────────────────────
function renderCard(rows, title, sub, type, fmt) {
    const rankCls  = i => i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : '';
    const valCls   = type === 'season' ? 'val-season' : type === 'avg' ? 'val-avg' : 'val-career';
    const titleCls = type; // 'career' | 'avg' | 'season'
    const isCareer = type !== 'season';
    const statWord = title.split(' ').pop();

    const thead = isCareer
        ? `<tr><th>#</th><th>Player</th><th>Seasons</th><th>GP</th><th>${statWord}</th></tr>`
        : `<tr><th>#</th><th>Player · Season</th><th>Team</th><th>GP</th><th>${statWord}</th></tr>`;

    const trows = rows.map((r, i) => {
        const cls = [rankCls(i), i >= TOP_INITIAL ? 'hidden' : ''].filter(Boolean).join(' ');
        const meta   = isCareer ? `${r.seasons} season${r.seasons !== 1 ? 's' : ''}` : r.season;
        const col3   = isCareer ? r.seasons : (r.team_name || r.team_code || '—');
        return `<tr class="${cls}">
          <td class="${rankCls(i)}">${i + 1}</td>
          <td>
            <span class="p-name"><a href="player.html?code=${r.code}">${r.name}</a></span>
            <span class="p-meta">${meta}</span>
          </td>
          <td>${col3}</td>
          <td>${r.gp}</td>
          <td class="${valCls}">${fmt(r.value)}</td>
        </tr>`;
    }).join('');

    const showMore = rows.length > TOP_INITIAL
        ? `<button class="show-more-btn">Show top ${Math.min(rows.length, TOP_EXTENDED)} ↓</button>`
        : '';

    return `
    <div class="record-card">
      <div class="record-card-header">
        <span class="rch-title ${titleCls}">${title}</span>
        <span class="rch-sub">${sub}</span>
      </div>
      <table class="lb-table">
        <thead>${thead}</thead>
        <tbody>${trows}</tbody>
      </table>
      ${showMore}
    </div>`;
}


// ── Lazy-loaded game-record tabs ───────────────────────────────────────────────
async function loadJson(url) {
    try {
        const r = await fetch(url);
        if (!r.ok) throw new Error(r.status);
        return await r.json();
    } catch {
        return { error: true };
    }
}

function errorMsg(what)     { return `<p class="error-msg">Could not load ${what} data. Run the data pipeline first.</p>`; }
function legend(html)       { return `<div class="filter-row"><span class="filter-legend">${html}</span></div>`; }
function sinceLabel(d)      { return d.seasons && d.seasons.length ? seasonLbl(d.seasons[0]) : ''; }
function rankCls(r)         { return r.rank === 1 ? 'rank-1' : r.rank === 2 ? 'rank-2' : r.rank === 3 ? 'rank-3' : ''; }
function rowCls(r, i)       { return [r.rank ? rankCls(r) : '', i >= TOP_INITIAL ? 'hidden' : ''].filter(Boolean).join(' '); }
function rankCell(r)        { return `<td class="${rankCls(r)}">${r.tied ? 'T-' : ''}${r.rank}</td>`; }
function newTag(season, cur){ return season === cur ? '<span class="cb-new">NEW</span>' : ''; }
function emptyRow(cols)     { return `<tr><td colspan="${cols}" class="p-meta">No qualifying games yet</td></tr>`; }

function replayLink(r, label, title) {
    return r.has_replay
        ? `<a href="replay.html?season=${r.season}&game=${r.gamecode}" title="${title} · open replay">${label}</a>`
        : `<span title="${title}">${label}</span>`;
}

function playerLink(r) {
    const name = esc(r.player_name || r.player || '—');
    return r.player && _data && _data.players && _data.players[r.player] ? `<a href="player.html?code=${encodeURIComponent(r.player)}">${name}</a>` : name;
}

function showMoreBtn(n, all) {
    if (n <= TOP_INITIAL) return '';
    return `<button class="show-more-btn">${all ? `Show all ${n}` : `Show top ${Math.min(n, TOP_EXTENDED)}`} ↓</button>`;
}

function cardShell(title, sub, titleCls, tableCls, thead, trows, showMore) {
    return `
    <div class="record-card">
      <div class="record-card-header">
        <span class="rch-title ${titleCls}">${title}</span>
        <span class="rch-sub">${sub}</span>
      </div>
      <table class="lb-table ${tableCls}">
        <thead>${thead}</thead>
        <tbody>${trows}</tbody>
      </table>
      ${showMore}
    </div>`;
}

// ── Comebacks tab ──────────────────────────────────────────────────────────────
function renderComebacks(d) {
    if (d.error) return errorMsg('comeback');
    return legend(`Largest deficit the eventual winner faced &nbsp;·&nbsp; ${d.games_scanned.toLocaleString()} games since ${sinceLabel(d)} &nbsp;·&nbsp; click a game for its replay`) + `
    <div class="records-grid game-grid">
      ${renderComebackCard(d.overall,        'Biggest Comebacks',     'Any point in the game',         'comeback', d.current_season)}
      ${renderComebackCard(d.fourth_quarter, '4th-Quarter Comebacks', 'Deficit faced in Q4 or OT',     'q4',       d.current_season)}
      ${renderComebackCard(d.postseason,     'Playoffs & Final Four', 'Playoffs, Play-In, Final Four', 'post',     d.current_season)}
    </div>`;
}

function renderComebackCard(rows, title, sub, titleCls, current) {
    const trows = rows.length ? rows.map((r, i) => {
        const sep  = r.home ? 'vs' : '@';
        const game = replayLink(r, `${r.winner} ${sep} ${r.loser}`, esc(`${r.winner_name} ${sep} ${r.loser_name}`));
        const meta = [r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        return `<tr class="${rowCls(r, i)}">
          ${rankCell(r)}
          <td>
            <span class="p-name">${game}${newTag(r.season, current)}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td class="val-deficit">${r.deficit}
            <span class="p-meta">trailed ${r.trailing} · ${periodLabel(r.quarter)} ${clockLabel(r.clock)}</span>
          </td>
          <td>${r.final}${r.ot ? ' OT' : ''}</td>
        </tr>`;
    }).join('') : emptyRow(4);
    return cardShell(title, sub, titleCls, 'cb-table',
        '<tr><th>#</th><th>Game</th><th>Deficit</th><th>Final</th></tr>', trows, showMoreBtn(rows.length, false));
}

// ── Game Highs tab ─────────────────────────────────────────────────────────────
const HIGH_CARDS = [
    { key: 'points',   title: 'Points',   unit: 'PTS', cls: 'career' },
    { key: 'rebounds', title: 'Rebounds', unit: 'REB', cls: 'avg' },
    { key: 'assists',  title: 'Assists',  unit: 'AST', cls: 'season' },
    { key: 'threes',   title: 'Threes',   unit: '3PM', cls: 'q4' },
    { key: 'pir',      title: 'PIR',      unit: 'PIR', cls: 'post' },
];

function renderHighs(d) {
    if (d.error) return errorMsg('game-high');
    return legend(`Single-game bests rebuilt from play-by-play &nbsp;·&nbsp; ${d.games_scanned.toLocaleString()} games since ${sinceLabel(d)} &nbsp;·&nbsp; click a game for its replay`) +
        `<div class="records-grid game-grid">${HIGH_CARDS.map(c => renderHighCard(d[c.key] || [], c, d.current_season)).join('')}</div>`;
}

function lineSummary(line, key) {
    const parts = [`${line.points} PTS`, `${line.rebounds} REB`, `${line.assists} AST`];
    if (key === 'threes') parts.push(`${line.threes} 3PM`);
    parts.push(`${line.pir} PIR`);
    return parts.join(' · ');
}

function renderHighCard(rows, c, current) {
    const trows = rows.length ? rows.map((r, i) => {
        const sep  = r.home ? 'vs' : '@';
        const game = replayLink(r, `${sep} ${r.opp}`, esc(`${r.team} ${sep} ${r.opp}`));
        const meta = [r.team, r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        return `<tr class="${rowCls(r, i)}">
          ${rankCell(r)}
          <td>
            <span class="p-name">${playerLink(r)}${newTag(r.season, current)}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td>
            <span class="p-name">${game}</span>
            <span class="p-meta">${r.won ? 'W' : 'L'} ${r.final}${r.ot ? ' OT' : ''}</span>
          </td>
          <td class="val-deficit">${r.value}
            <span class="p-meta">${lineSummary(r.line, c.key)}</span>
          </td>
        </tr>`;
    }).join('') : emptyRow(4);
    return cardShell(c.title, 'Single game', c.cls, 'gr-table',
        `<tr><th>#</th><th>Player</th><th>Game</th><th>${c.unit}</th></tr>`, trows, showMoreBtn(rows.length, false));
}

// ── Game-Winners tab ───────────────────────────────────────────────────────────
function renderWinners(d) {
    if (d.error) return errorMsg('game-winner');
    return legend(`Made field goals in the last ${d.window_seconds} seconds of the 4th quarter or OT that gave the winner the lead for good &nbsp;·&nbsp; ${d.all.length} since ${sinceLabel(d)}`) + `
    <div class="records-grid game-grid">
      ${renderShotCard(d.all,            'All Game-Winners', 'Newest first',  'comeback', d.current_season)}
      ${renderShotCard(d.buzzer_beaters, 'Buzzer-Beaters',   '0:01 or less',  'q4',       d.current_season)}
      ${renderLeadersCard(d.leaders, `Since ${sinceLabel(d)}`)}
    </div>`;
}

function renderShotCard(rows, title, sub, titleCls, current) {
    const trows = rows.length ? rows.map((r, i) => {
        const sep    = r.home ? 'vs' : '@';
        const game   = replayLink(r, `${r.team} ${sep} ${r.opp}`, esc(`${r.team} ${sep} ${r.opp}`));
        const meta   = [game, r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        const buzzer = r.buzzer ? '<span class="gw-buzzer">BUZZER</span>' : '';
        return `<tr class="${rowCls(r, i)}">
          <td>
            <span class="p-name">${playerLink(r)}${newTag(r.season, current)}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td>
            <span class="p-name">${r.shot} · ${periodLabel(r.quarter)} ${clockLabel(r.clock)}${buzzer}</span>
            <span class="p-meta">go-ahead ${r.after} · final ${r.final}${r.ot ? ' OT' : ''}</span>
          </td>
        </tr>`;
    }).join('') : emptyRow(2);
    return cardShell(title, sub, titleCls, 'gw-table',
        '<tr><th>Shooter</th><th>Shot</th></tr>', trows, showMoreBtn(rows.length, true));
}

function renderLeadersCard(rows, sub) {
    const trows = rows.length ? rows.map((r, i) => `<tr class="${rowCls(r, i)}">
          ${rankCell(r)}
          <td>
            <span class="p-name">${playerLink(r)}</span>
            <span class="p-meta">last ${r.last_season_label}</span>
          </td>
          <td class="val-deficit">${r.count}</td>
          <td>${r.buzzer_count}</td>
        </tr>`).join('') : emptyRow(4);
    return cardShell('Most Game-Winners', sub, 'post', 'gr-table',
        '<tr><th>#</th><th>Player</th><th>GW</th><th>Buzzer</th></tr>', trows, showMoreBtn(rows.length, false));
}

function seasonLbl(s)   { return `${s}-${String(s + 1).slice(-2)}`; }
function periodLabel(q) { return q == null ? '' : q <= 4 ? `Q${q}` : `OT${q - 4}`; }
function clockLabel(c)  { return c ? String(c).replace(/^0(?=\d:)/, '') : ''; }
function esc(s)         { return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }
function stageLabel(r) {
    const name = PHASE_LABEL[r.phase] || r.phase || '';
    return (r.phase === 'RS' || r.phase === 'TS') && r.round != null ? `${name} R${r.round}` : name;
}
