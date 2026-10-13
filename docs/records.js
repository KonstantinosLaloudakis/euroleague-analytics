// records.js
const DATA_URL      = 'data/current/player_career_stats.json';
const MIN_GP_SEASON = 15;
const TOP_INITIAL   = 10;
const TOP_EXTENDED  = 25;
const COMEBACKS_URL = 'data/current/comebacks.json';
const PHASE_LABEL   = { RS: 'RS', TS: 'Top 16', PO: 'Playoffs', PI: 'Play-In', FF: 'Final Four' };

let _data        = null; // cached raw JSON — reused on filter changes, no re-fetch
let _rankings    = null; // cached computed rankings
let _activeTab   = 'scoring';
let _minGpCareer = 100;
let _comebacks   = null; // comebacks.json, loaded on first Comebacks tab click

const TABS = [
    { key: 'scoring',    label: 'Scoring',    careerLabel: 'Career Points',   careerSub: 'Accumulated total',   avgLabel: 'Career Avg PPG', avgSub: 'GP-weighted average', avgStat: 'ppg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season PPG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'playmaking', label: 'Playmaking', careerLabel: 'Career Assists',  careerSub: 'Accumulated total',   avgLabel: 'Career Avg APG', avgSub: 'GP-weighted average', avgStat: 'apg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season APG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'rebounding', label: 'Rebounding', careerLabel: 'Career Rebounds', careerSub: 'Accumulated total',   avgLabel: 'Career Avg RPG', avgSub: 'GP-weighted average', avgStat: 'rpg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season RPG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'defense',    label: 'Defense',    careerLabel: 'Career Steals',   careerSub: 'Accumulated total',   avgLabel: 'Career Avg SPG', avgSub: 'GP-weighted average', avgStat: 'spg',     avgFmt: v => v.toFixed(1), seasonLabel: 'Best Season SPG', seasonSub: 'Per-game average',   fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'efficiency', label: 'Efficiency', careerLabel: 'Career Avg PIR',  careerSub: 'GP-weighted average', avgLabel: 'Career Avg 2P%', avgSub: 'GP-weighted average', avgStat: 'fg2_pct', avgFmt: v => v.toFixed(1) + '%', seasonLabel: 'Best Season PIR', seasonSub: 'Per-game average',   fmtC: v => v.toFixed(1),                   fmtS: v => v.toFixed(1) },
    { key: 'comebacks',  label: 'Comebacks' },
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

    if (_activeTab === 'comebacks') {
        content.innerHTML = `<div class="cat-tabs">${tabButtons}</div>${renderComebacks()}`;
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
            if (btn.dataset.tab === 'comebacks' && !_comebacks) await loadComebacks();
            _activeTab = btn.dataset.tab;
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

// ── Comebacks tab ──────────────────────────────────────────────────────────────
async function loadComebacks() {
    try {
        const r = await fetch(COMEBACKS_URL);
        if (!r.ok) throw new Error(r.status);
        _comebacks = await r.json();
    } catch {
        _comebacks = { error: true };
    }
}

function renderComebacks() {
    if (_comebacks.error) {
        return '<p class="error-msg">Could not load comeback data. Run the data pipeline first.</p>';
    }
    const since = _comebacks.seasons.length ? seasonLbl(_comebacks.seasons[0]) : '';
    return `
    <div class="filter-row">
      <span class="filter-legend">Largest deficit the eventual winner faced &nbsp;·&nbsp; ${_comebacks.games_scanned.toLocaleString()} games since ${since} &nbsp;·&nbsp; click a game for its replay</span>
    </div>
    <div class="records-grid">
      ${renderComebackCard(_comebacks.overall,        'Biggest Comebacks',     'Any point in the game',         'comeback')}
      ${renderComebackCard(_comebacks.fourth_quarter, '4th-Quarter Comebacks', 'Deficit faced in Q4 or OT',     'q4')}
      ${renderComebackCard(_comebacks.postseason,     'Playoffs & Final Four', 'Playoffs, Play-In, Final Four', 'post')}
    </div>`;
}

function renderComebackCard(rows, title, sub, titleCls) {
    const rankCls = r => r.rank === 1 ? 'rank-1' : r.rank === 2 ? 'rank-2' : r.rank === 3 ? 'rank-3' : '';

    const trows = rows.length ? rows.map((r, i) => {
        const cls   = [rankCls(r), i >= TOP_INITIAL ? 'hidden' : ''].filter(Boolean).join(' ');
        const sep   = r.home ? 'vs' : '@';
        const full  = esc(`${r.winner_name} ${sep} ${r.loser_name}`);
        const label = `${r.winner} ${sep} ${r.loser}`;
        const game  = r.has_replay
            ? `<a href="replay.html?season=${r.season}&game=${r.gamecode}" title="${full} · open replay">${label}</a>`
            : `<span title="${full}">${label}</span>`;
        const isNew = r.season === _comebacks.current_season ? '<span class="cb-new">NEW</span>' : '';
        const meta  = [r.season_label, stageLabel(r)].filter(Boolean).join(' · ');
        return `<tr class="${cls}">
          <td class="${rankCls(r)}">${r.tied ? 'T-' : ''}${r.rank}</td>
          <td>
            <span class="p-name">${game}${isNew}</span>
            <span class="p-meta">${meta}</span>
          </td>
          <td class="val-deficit">${r.deficit}
            <span class="p-meta">trailed ${r.trailing} · ${periodLabel(r.quarter)} ${clockLabel(r.clock)}</span>
          </td>
          <td>${r.final}${r.ot ? ' OT' : ''}</td>
        </tr>`;
    }).join('') : '<tr><td colspan="4" class="p-meta">No qualifying games yet</td></tr>';

    const showMore = rows.length > TOP_INITIAL
        ? `<button class="show-more-btn">Show top ${Math.min(rows.length, TOP_EXTENDED)} ↓</button>`
        : '';

    return `
    <div class="record-card">
      <div class="record-card-header">
        <span class="rch-title ${titleCls}">${title}</span>
        <span class="rch-sub">${sub}</span>
      </div>
      <table class="lb-table cb-table">
        <thead><tr><th>#</th><th>Game</th><th>Deficit</th><th>Final</th></tr></thead>
        <tbody>${trows}</tbody>
      </table>
      ${showMore}
    </div>`;
}

function seasonLbl(s)   { return `${s}-${String(s + 1).slice(-2)}`; }
function periodLabel(q) { return q == null ? '' : q <= 4 ? `Q${q}` : `OT${q - 4}`; }
function clockLabel(c)  { return c ? String(c).replace(/^0(?=\d:)/, '') : ''; }
function esc(s)         { return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }
function stageLabel(r) {
    const name = PHASE_LABEL[r.phase] || r.phase || '';
    return (r.phase === 'RS' || r.phase === 'TS') && r.round != null ? `${name} R${r.round}` : name;
}
