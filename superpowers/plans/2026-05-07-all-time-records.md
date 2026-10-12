# All-Time Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `records.html` — a page showing all-time Euroleague career leaders and single-season records across 5 stat categories, driven entirely by the existing `player_career_stats.json`.

**Architecture:** All data is already in `docs/data/current/player_career_stats.json` (1,148 players, 19 seasons). `records.js` loads that JSON once, computes career totals and single-season rankings client-side, and renders two-column tables per category tab. No backend changes needed.

**Tech Stack:** Vanilla JS, inline SVG-free, existing `style.css` CSS variables, no new dependencies.

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `docs/records.html` | Page shell, nav (active), inline CSS |
| Create | `docs/records.js` | All computation + rendering logic |
| Modify | All 15 `docs/*.html` | Add "All-Time Records" nav link |
| Modify | `docs/about.html` | Add methodology section |

---

## Task 1: `records.html` + `records.js`

**Files:**
- Create: `docs/records.html`
- Create: `docs/records.js`

- [ ] **Step 1: Create `docs/records.html`**

Copy the nav from `docs/player.html` (lines 129–148), change the active link, and add the "All-Time Records" link. Full file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#0f1117">
  <title>All-Time Records — Euroleague Analytics</title>
  <meta name="description" content="Euroleague all-time career leaders and single-season records across 19 seasons.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Outfit:wght@700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
  <style>
    .records-page { max-width: 1020px; margin: 0 auto; padding: 24px 16px; }

    .page-header { margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; font-weight: 800; color: var(--text-primary); margin-bottom: 4px; }
    .page-header p  { font-size: 13px; color: var(--text-muted); }

    /* Category tabs */
    .cat-tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
    .cat-tab {
      padding: 6px 16px; border-radius: 8px; font-size: 12px; font-weight: 600;
      cursor: pointer; border: 1px solid transparent; color: var(--text-muted);
      background: transparent; transition: var(--transition);
    }
    .cat-tab.active { background: var(--bg-secondary); color: var(--text-primary); border-color: var(--border); }
    .cat-tab:hover:not(.active) { color: var(--text-secondary); }

    /* Filter row */
    .filter-row { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; font-size: 12px; color: var(--text-muted); flex-wrap: wrap; }
    .filter-row select {
      background: var(--bg-secondary); border: 1px solid var(--border); color: var(--text-secondary);
      border-radius: 6px; padding: 3px 8px; font-size: 11px; font-family: inherit; cursor: pointer;
    }
    .filter-legend { font-size: 11px; color: #334155; }

    /* Two-column grid */
    .records-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 680px) { .records-grid { grid-template-columns: 1fr; } }

    /* Record card */
    .record-card { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    .record-card-header {
      padding: 12px 16px; border-bottom: 1px solid var(--border);
      display: flex; align-items: baseline; justify-content: space-between;
    }
    .rch-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
    .rch-title.career { color: var(--accent-gold); }
    .rch-title.season { color: var(--accent-green); }
    .rch-sub { font-size: 10px; color: var(--text-muted); }

    /* Leaderboard table */
    .lb-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .lb-table thead th {
      padding: 6px 12px; font-size: 9px; font-weight: 600; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: .06em;
      background: var(--bg-primary); text-align: right; white-space: nowrap;
    }
    .lb-table thead th:nth-child(1) { text-align: center; width: 28px; }
    .lb-table thead th:nth-child(2) { text-align: left; }
    .lb-table tbody tr { border-bottom: 1px solid #0f1929; transition: background .12s; }
    .lb-table tbody tr:hover { background: #1a2744; }
    .lb-table tbody tr:last-child { border-bottom: none; }
    .lb-table tbody tr.hidden { display: none; }
    .lb-table td { padding: 8px 12px; text-align: right; color: var(--text-secondary); }
    .lb-table td:nth-child(1) { text-align: center; font-weight: 700; font-size: 11px; }
    .lb-table td:nth-child(2) { text-align: left; }

    .rank-1 { color: var(--accent-gold); }
    .rank-2 { color: #94a3b8; }
    .rank-3 { color: #cd7c2f; }

    .p-name { color: var(--text-primary); font-weight: 600; font-size: 12px; }
    .p-name a { color: var(--text-primary); text-decoration: none; }
    .p-name a:hover { color: var(--accent-blue); }
    .p-meta { font-size: 10px; color: var(--text-muted); display: block; margin-top: 1px; }

    .val-career { color: var(--accent-gold); font-weight: 700; }
    .val-season { color: var(--accent-green); font-weight: 700; }

    /* Show-more toggle */
    .show-more-btn {
      width: 100%; padding: 8px 16px; font-size: 11px; color: var(--text-muted);
      text-align: center; cursor: pointer; border-top: 1px solid var(--border);
      background: transparent; border-left: none; border-right: none; border-bottom: none;
      font-family: inherit; transition: color .15s;
    }
    .show-more-btn:hover { color: var(--accent-blue); }

    .error-msg { color: var(--text-muted); text-align: center; padding: 60px; }
  </style>
</head>
<body>

  <nav class="site-nav">
    <span class="site-nav-brand">🏀 Euroleague Analytics</span>
    <a href="index.html" class="nav-link">Season Hub</a>
    <a href="team.html" class="nav-link">Team Deep-Dive</a>
    <a href="players.html" class="nav-link">Player Stats</a>
    <a href="player.html" class="nav-link">Careers</a>
    <a href="h2h.html" class="nav-link">Head-to-Head</a>
    <a href="recap.html" class="nav-link">Game Recap</a>
    <a href="shots.html" class="nav-link">Shot Lab</a>
    <a href="network.html" class="nav-link">Playmaking</a>
    <a href="replay.html" class="nav-link">Game Replay</a>
    <a href="records.html" class="nav-link active">All-Time Records</a>
    <a href="playoffs.html" class="nav-link">Playoffs</a>
    <a href="mvp.html" class="nav-link">MVP Race</a>
    <a href="game-control.html" class="nav-link">Game Control</a>
    <a href="gci-history.html" class="nav-link">GCI History</a>
    <a href="about.html" class="nav-link">About</a>
  </nav>

  <main class="records-page">
    <div class="page-header">
      <h1>🏆 All-Time Records</h1>
      <p>19 seasons · 2007–08 to 2025–26 · Euroleague only</p>
    </div>
    <div id="records-content">
      <p class="error-msg">Loading…</p>
    </div>
  </main>

  <script src="records.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `docs/records.js`**

```javascript
// records.js
const DATA_URL = 'data/current/player_career_stats.json';
const MIN_GP_SEASON = 15;
const TOP_INITIAL   = 10;
const TOP_EXTENDED  = 25;

let _rankings = null; // cached after first compute

const TABS = [
    { key: 'scoring',    label: 'Scoring',    careerLabel: 'Career Points',   careerSub: 'Accumulated total',    seasonLabel: 'Best Season PPG', seasonSub: 'Per-game average',    fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'playmaking', label: 'Playmaking', careerLabel: 'Career Assists',  careerSub: 'Accumulated total',    seasonLabel: 'Best Season APG', seasonSub: 'Per-game average',    fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'rebounding', label: 'Rebounding', careerLabel: 'Career Rebounds', careerSub: 'Accumulated total',    seasonLabel: 'Best Season RPG', seasonSub: 'Per-game average',    fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'defense',    label: 'Defense',    careerLabel: 'Career Steals',   careerSub: 'Accumulated total',    seasonLabel: 'Best Season SPG', seasonSub: 'Per-game average',    fmtC: v => Math.round(v).toLocaleString(), fmtS: v => v.toFixed(1) },
    { key: 'efficiency', label: 'Efficiency', careerLabel: 'Career Avg PIR',  careerSub: 'GP-weighted average',  seasonLabel: 'Best Season PIR', seasonSub: 'Per-game average',    fmtC: v => v.toFixed(1),                   fmtS: v => v.toFixed(1) },
];

let _activeTab    = 'scoring';
let _minGpCareer  = 100;

// ── Entry point ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    let data;
    try {
        data = await fetch(DATA_URL).then(r => r.json());
    } catch {
        document.getElementById('records-content').innerHTML =
            '<p class="error-msg">Could not load player data. Run the data pipeline first.</p>';
        return;
    }

    document.title = `All-Time Records — EL Analytics`;
    _rankings = computeRankings(data, _minGpCareer);
    renderPage();
});

// ── Compute all rankings ───────────────────────────────────────────────────────
function computeRankings(data, minGpCareer) {
    const players = Object.entries(data.players);

    const careerPts = [], careerAst = [], careerReb = [], careerStl = [], careerPIR = [];
    const szPPG = [], szAPG = [], szRPG = [], szSPG = [], szPIR = [];

    for (const [code, p] of players) {
        const totalGp = p.career?.gp || 0;
        if (totalGp >= minGpCareer) {
            let pts = 0, ast = 0, reb = 0, stl = 0;
            for (const s of p.seasons) {
                if (!s.gp) continue;
                pts += (s.ppg || 0) * s.gp;
                ast += (s.apg || 0) * s.gp;
                reb += (s.rpg || 0) * s.gp;
                stl += (s.spg || 0) * s.gp;
            }
            const base = { code, name: p.name, image: p.image, seasons: p.seasons.length, gp: totalGp };
            careerPts.push({ ...base, value: Math.round(pts) });
            careerAst.push({ ...base, value: Math.round(ast) });
            careerReb.push({ ...base, value: Math.round(reb) });
            careerStl.push({ ...base, value: Math.round(stl) });
            if (p.career.pir != null) careerPIR.push({ ...base, value: p.career.pir });
        }

        for (const s of p.seasons) {
            if (!s.gp || s.gp < MIN_GP_SEASON) continue;
            const base = { code, name: p.name, image: p.image, season: s.season, team_code: s.team_code, gp: s.gp };
            if (s.ppg != null) szPPG.push({ ...base, value: s.ppg });
            if (s.apg != null) szAPG.push({ ...base, value: s.apg });
            if (s.rpg != null) szRPG.push({ ...base, value: s.rpg });
            if (s.spg != null) szSPG.push({ ...base, value: s.spg });
            if (s.pir != null) szPIR.push({ ...base, value: s.pir });
        }
    }

    const top = arr => arr.sort((a, b) => b.value - a.value).slice(0, TOP_EXTENDED);
    return {
        scoring:    { career: top(careerPts), season: top(szPPG) },
        playmaking: { career: top(careerAst), season: top(szAPG) },
        rebounding: { career: top(careerReb), season: top(szRPG) },
        defense:    { career: top(careerStl), season: top(szSPG) },
        efficiency: { career: top(careerPIR), season: top(szPIR) },
    };
}

// ── Render full page ──────────────────────────────────────────────────────────
function renderPage() {
    const tabButtons = TABS.map(t =>
        `<button class="cat-tab${t.key === _activeTab ? ' active' : ''}" data-tab="${t.key}">${t.label}</button>`
    ).join('');

    const filterHtml = `
    <div class="filter-row">
      <span>Career minimum:</span>
      <select id="min-gp-select">
        <option value="50"${_minGpCareer === 50  ? ' selected' : ''}>50 GP</option>
        <option value="100"${_minGpCareer === 100 ? ' selected' : ''}>100 GP</option>
        <option value="200"${_minGpCareer === 200 ? ' selected' : ''}>200 GP</option>
        <option value="0"${_minGpCareer === 0   ? ' selected' : ''}>No minimum</option>
      </select>
      <span class="filter-legend">· Career = accumulated totals &nbsp;·&nbsp; Single season = per-game averages &nbsp;·&nbsp; Season minimum: ${MIN_GP_SEASON} GP</span>
    </div>`;

    const tab = TABS.find(t => t.key === _activeTab);
    const data = _rankings[_activeTab];

    document.getElementById('records-content').innerHTML = `
    <div class="cat-tabs">${tabButtons}</div>
    ${filterHtml}
    <div class="records-grid">
      ${renderCard(data.career, tab.careerLabel, tab.careerSub, 'career', tab.fmtC, true)}
      ${renderCard(data.season, tab.seasonLabel, tab.seasonSub, 'season', tab.fmtS, false)}
    </div>`;

    // Attach events
    document.querySelectorAll('.cat-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            _activeTab = btn.dataset.tab;
            renderPage();
        });
    });

    document.getElementById('min-gp-select').addEventListener('change', e => {
        _minGpCareer = Number(e.target.value);
        // Recompute with new threshold — need original data
        fetch(DATA_URL).then(r => r.json()).then(data => {
            _rankings = computeRankings(data, _minGpCareer);
            renderPage();
        });
    });

    document.querySelectorAll('.show-more-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const card = btn.closest('.record-card');
            card.querySelectorAll('tr.hidden').forEach(tr => tr.classList.remove('hidden'));
            btn.remove();
        });
    });
}

// ── Render one record card ─────────────────────────────────────────────────────
function renderCard(rows, title, sub, type, fmt, isCareer) {
    const rankClass = i => i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : '';
    const valClass  = isCareer ? 'val-career' : 'val-season';
    const titleClass = isCareer ? 'career' : 'season';

    const thead = isCareer
        ? `<tr><th>#</th><th>Player</th><th>Seasons</th><th>GP</th><th>${title.split(' ').pop()}</th></tr>`
        : `<tr><th>#</th><th>Player · Season</th><th>Team</th><th>GP</th><th>${title.split(' ').pop()}</th></tr>`;

    const trows = rows.map((r, i) => {
        const hidden = i >= TOP_INITIAL ? ' hidden' : '';
        const meta   = isCareer
            ? `${r.seasons} season${r.seasons !== 1 ? 's' : ''}`
            : r.season;
        const col3   = isCareer ? r.seasons : (r.team_code || '—');
        return `<tr class="${rankClass(i)}${hidden}">
          <td class="${rankClass(i)}">${i + 1}</td>
          <td>
            <span class="p-name"><a href="player.html?code=${r.code}">${r.name}</a></span>
            <span class="p-meta">${meta}</span>
          </td>
          <td>${col3}</td>
          <td>${r.gp}</td>
          <td class="${valClass}">${fmt(r.value)}</td>
        </tr>`;
    }).join('');

    const showMore = rows.length > TOP_INITIAL
        ? `<button class="show-more-btn">Show top ${Math.min(rows.length, TOP_EXTENDED)} ↓</button>`
        : '';

    return `
    <div class="record-card">
      <div class="record-card-header">
        <span class="rch-title ${titleClass}">${title}</span>
        <span class="rch-sub">${sub}</span>
      </div>
      <table class="lb-table">
        <thead>${thead}</thead>
        <tbody>${trows}</tbody>
      </table>
      ${showMore}
    </div>`;
}
```

- [ ] **Step 3: Verify in browser**

Open `docs/records.html` in a browser. Verify:
- Header shows "🏆 All-Time Records" with subtitle
- 5 category tabs render (Scoring active by default)
- Two record cards appear side by side — Career Points (left) + Best Season PPG (right)
- Top 10 rows visible, "Show top 25 ↓" button present
- Clicking show-more reveals rows 11–25
- Clicking Playmaking/Rebounding/Defense/Efficiency tabs re-renders with correct data
- Changing the Min GP dropdown recomputes rankings
- Clicking a player name navigates to their career page

Get a player code to verify the link:
```
.venv/Scripts/python.exe -c "
import json
d = json.load(open('docs/data/current/player_career_stats.json'))
# Find Spanoulis
span = next(p for k, p in d['players'].items() if 'SPANOULIS' in p['name'])
print(span['name'], '— should appear near top of Career Points')
"
```

- [ ] **Step 4: Commit**

```bash
git add docs/records.html docs/records.js
git commit -m "feat: add all-time records page with career leaders and single-season records"
```

---

## Task 2: Add "All-Time Records" Nav Link to All Existing Pages

**Files:**
- Modify: `docs/about.html`, `docs/game-control.html`, `docs/gci-history.html`, `docs/h2h.html`, `docs/index.html`, `docs/mvp.html`, `docs/network.html`, `docs/player.html`, `docs/players.html`, `docs/playoffs.html`, `docs/recap.html`, `docs/replay.html`, `docs/series.html`, `docs/shots.html`, `docs/team.html`

- [ ] **Step 1: Insert nav link in all 15 pages using sed**

The new link goes between `replay.html` and `playoffs.html`. Run from the project root:

```bash
for f in docs/about.html docs/game-control.html docs/gci-history.html docs/h2h.html docs/index.html docs/mvp.html docs/network.html docs/player.html docs/players.html docs/playoffs.html docs/recap.html docs/replay.html docs/series.html docs/shots.html docs/team.html; do
  sed -i 's|<a href="playoffs.html" class="nav-link active">Playoffs</a>|<a href="records.html" class="nav-link">All-Time Records</a>\n        <a href="playoffs.html" class="nav-link active">Playoffs</a>|g' "$f"
  sed -i 's|<a href="playoffs.html" class="nav-link">Playoffs</a>|<a href="records.html" class="nav-link">All-Time Records</a>\n        <a href="playoffs.html" class="nav-link">Playoffs</a>|g' "$f"
done && echo "done"
```

- [ ] **Step 2: Verify the link was added**

```bash
grep -c 'records.html' docs/players.html docs/index.html docs/team.html
```

Expected: each file shows `1` (one occurrence of `records.html`).

Also verify `records.html` itself has `active` on the correct link (it was written directly in Task 1 with the correct markup — confirm):

```bash
grep 'records.html' docs/records.html
```

Expected: `<a href="records.html" class="nav-link active">All-Time Records</a>`

- [ ] **Step 3: Commit**

```bash
git add docs/about.html docs/game-control.html docs/gci-history.html docs/h2h.html docs/index.html docs/mvp.html docs/network.html docs/player.html docs/players.html docs/playoffs.html docs/recap.html docs/replay.html docs/series.html docs/shots.html docs/team.html
git commit -m "feat: add All-Time Records nav link to all pages"
```

---

## Task 3: Update `docs/about.html`

**Files:**
- Modify: `docs/about.html`

- [ ] **Step 1: Add the All-Time Records methodology section**

Read `docs/about.html` to find the existing section structure (class names, heading levels). Add a new section after the "Player Career Pages" section (which was added in the previous feature). Match the exact class names used by surrounding sections.

Content to add:

```
Section heading: "All-Time Records"

Paragraph:
The All-Time Records page ranks every player across all 19 Euroleague seasons (2007–08 to 2025–26) for career leaders and single-season bests. Data comes from player_career_stats.json, which is refreshed weekly.

Sub-heading: "Career Leaders"

Paragraph:
Counting stats (points, assists, rebounds, steals) are accumulated totals computed as Σ(per_game_average × games_played) across all seasons. This rewards longevity alongside production. A minimum of 100 GP (adjustable) filters out very short careers. PIR is shown as a GP-weighted career average rather than a total.

Sub-heading: "Single-Season Records"

Paragraph:
Each season entry for every player is ranked independently. A minimum of 15 GP per season filters out statistical anomalies from injury-shortened appearances.
```

- [ ] **Step 2: Verify**

Open `docs/about.html` in a browser. Confirm the section renders with correct styling.

- [ ] **Step 3: Commit**

```bash
git add docs/about.html
git commit -m "docs: add all-time records methodology to about page"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `records.html` page shell with nav active | Task 1 |
| `records.js` loads `player_career_stats.json` | Task 1 |
| Career totals via `Σ(stat × gp)` | Task 1 (computeRankings) |
| Single-season records scan all season entries | Task 1 (computeRankings) |
| 5 category tabs: Scoring, Playmaking, Rebounding, Defense, Efficiency | Task 1 (TABS array) |
| Career min GP filter (default 100), user-adjustable | Task 1 (filter-row + select) |
| Season min GP = 15 | Task 1 (MIN_GP_SEASON constant) |
| Top 10 shown, "Show top 25" expander (DOM toggle, no fetch) | Task 1 (hidden class + show-more-btn) |
| Gold/green value highlighting | Task 1 (val-career/val-season CSS) |
| Player names link to `player.html?code=XXX` | Task 1 (renderCard) |
| Nav link added to all 15 pages | Task 2 |
| `records.html` marks link active | Task 1 (nav markup) |
| `about.html` methodology section | Task 3 |
| Mobile: grid stacks to 1 column | Task 1 (CSS media query) |

All requirements covered.

**Placeholder scan:** No TBDs or incomplete steps. All code blocks are complete.

**Type consistency:** `computeRankings` returns `{ scoring, playmaking, rebounding, defense, efficiency }` each with `{ career[], season[] }`. `renderPage` accesses `_rankings[_activeTab]` and passes `data.career` / `data.season` to `renderCard`. `renderCard` uses `r.code`, `r.name`, `r.seasons`, `r.gp`, `r.value`, `r.season`, `r.team_code` — all set in the `base` spread inside `computeRankings`. Consistent throughout.

**One known gap to handle at implementation time:** The min-GP filter change re-fetches `player_career_stats.json` from the network each time. Since the file is already cached by the browser after the first load, this is instantaneous — but the implementer should confirm by testing the dropdown change. If the file is not cached (e.g., on a slow connection), consider storing `data` in a module-level variable instead of re-fetching. The implementer should make this judgement call and fix if needed.
