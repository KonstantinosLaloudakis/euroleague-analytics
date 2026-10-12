# Assist/Playmaking Network — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new "Playmaking" page with per-team chord diagrams showing assist relationships, plus league-wide leaderboard tables for top combos and top playmakers.

**Architecture:** Python backend reads `data_cache/pbp_2025.csv`, links assist events to made field goals via consecutive `NUMBEROFPLAY`, aggregates passer→scorer edges per team, and exports to `docs/data/current/assist_network.json`. Frontend renders an interactive SVG chord diagram per team with hover/click interactions, a player detail card, and two sortable league-wide tables.

**Tech Stack:** Python 3 (csv, collections, json), vanilla JS, inline SVG, existing `constants.js` utilities (TEAM_COLORS, TEAM_NAMES, fetchJSON, switchTab).

**Spec:** `docs/superpowers/specs/2026-04-08-assist-network-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `export_dashboard_data.py` | Modify | Add `build_assist_network()` function + export call in `main()` |
| `docs/data/current/assist_network.json` | Create (generated) | JSON output consumed by frontend |
| `docs/network.html` | Create | Page shell: nav, header, team chips, SVG container, detail card, tables |
| `docs/network.js` | Create | Data loading, chord rendering, interactions, tables |
| `docs/index.html` | Modify | Add "Playmaking" nav link |
| `docs/team.html` | Modify | Add "Playmaking" nav link |
| `docs/players.html` | Modify | Add "Playmaking" nav link |
| `docs/h2h.html` | Modify | Add "Playmaking" nav link |
| `docs/recap.html` | Modify | Add "Playmaking" nav link |
| `docs/shots.html` | Modify | Add "Playmaking" nav link |
| `docs/replay.html` | Modify | Add "Playmaking" nav link |
| `docs/playoffs.html` | Modify | Add "Playmaking" nav link |
| `docs/mvp.html` | Modify | Add "Playmaking" nav link |
| `docs/about.html` | Modify | Add "Playmaking" nav link |
| `CLAUDE.md` | Modify | Add network.html to pages list |

---

## Task 1: Backend — `build_assist_network()`

**Files:**
- Modify: `export_dashboard_data.py` (add function after `build_paint_profiles()`, around line 533)

This function reads PBP data, links assists to made shots, aggregates edges, and returns the full JSON structure.

- [ ] **Step 1: Add the `build_assist_network()` function**

Add this function after `build_paint_profiles()` (before `build_game_recaps()`), around line 533 in `export_dashboard_data.py`:

```python
def build_assist_network():
    """Build passer→scorer assist network from play-by-play data."""
    import csv
    from collections import defaultdict

    pbp_file = 'data_cache/pbp_2025.csv'
    if not os.path.exists(pbp_file):
        print("  No PBP data found — skipping assist network.")
        return None

    print(f"\n--- Building assist network from {pbp_file} ---")

    # ── Phase 1: Read PBP, link assists to made field goals ──────────────────
    rows = []
    with open(pbp_file, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # Track GP per player (unique gamecodes where they appear)
    player_games = defaultdict(set)
    for row in rows:
        pid = row.get('PLAYER_ID', '').strip()
        gc = row.get('Gamecode', '').strip()
        if pid and gc:
            player_games[pid].add(gc)

    # Link assists: AS row follows a 2FGM/3FGM row with consecutive NUMBEROFPLAY
    edges_raw = []  # list of (passer_id, passer_name, scorer_id, scorer_name, team, shot_type, gamecode)
    for i, row in enumerate(rows):
        if row.get('PLAYTYPE') != 'AS':
            continue
        if i == 0:
            continue
        prev = rows[i - 1]
        if prev.get('Gamecode') != row.get('Gamecode'):
            continue
        if prev.get('PLAYTYPE') not in ('2FGM', '3FGM'):
            continue
        # Verify consecutive NUMBEROFPLAY
        try:
            nop_cur = int(row.get('NUMBEROFPLAY', 0))
            nop_prev = int(prev.get('NUMBEROFPLAY', 0))
        except (ValueError, TypeError):
            continue
        if nop_cur != nop_prev + 1:
            continue

        passer_id = row.get('PLAYER_ID', '').strip()
        passer_name = row.get('PLAYER', '').strip()
        scorer_id = prev.get('PLAYER_ID', '').strip()
        scorer_name = prev.get('PLAYER', '').strip()
        team = row.get('CODETEAM', '').strip()
        shot_type = prev.get('PLAYTYPE')  # '2FGM' or '3FGM'
        gamecode = row.get('Gamecode', '').strip()

        if passer_id and scorer_id and team:
            edges_raw.append((passer_id, passer_name, scorer_id, scorer_name, team, shot_type, gamecode))

    print(f"  Linked assists: {len(edges_raw)}")

    # ── Phase 2: Aggregate edges ─────────────────────────────────────────────
    # Edge key: (passer_id, scorer_id)
    edge_agg = defaultdict(lambda: {'count': 0, 'fg2': 0, 'fg3': 0, 'team': '', 'passer_name': '', 'scorer_name': ''})
    # Per-player totals
    player_ast_given = defaultdict(lambda: {'name': '', 'team': '', 'count': 0, 'targets': set()})
    player_ast_received = defaultdict(lambda: {'name': '', 'team': '', 'count': 0, 'feeders': set()})

    for passer_id, passer_name, scorer_id, scorer_name, team, shot_type, gamecode in edges_raw:
        key = (passer_id, scorer_id)
        e = edge_agg[key]
        e['count'] += 1
        e['team'] = team
        e['passer_name'] = passer_name
        e['scorer_name'] = scorer_name
        if shot_type == '2FGM':
            e['fg2'] += 1
        else:
            e['fg3'] += 1

        g = player_ast_given[passer_id]
        g['name'] = passer_name
        g['team'] = team
        g['count'] += 1
        g['targets'].add(scorer_id)

        r = player_ast_received[scorer_id]
        r['name'] = scorer_name
        r['team'] = team
        r['count'] += 1
        r['feeders'].add(passer_id)

    # ── Phase 3: Build per-team structures ───────────────────────────────────
    team_players = defaultdict(dict)  # team -> {player_id: {info}}
    team_edges = defaultdict(list)    # team -> [edge dicts]

    for (passer_id, scorer_id), e in edge_agg.items():
        team = e['team']
        team_edges[team].append({
            'from': passer_id,
            'to': scorer_id,
            'count': e['count'],
            'fg2': e['fg2'],
            'fg3': e['fg3'],
        })

        # Ensure both players exist in the team's player dict
        for pid, pname in [(passer_id, e['passer_name']), (scorer_id, e['scorer_name'])]:
            if pid not in team_players[team]:
                gp = len(player_games.get(pid, set()))
                ast_g = player_ast_given.get(pid, {}).get('count', 0)
                ast_r = player_ast_received.get(pid, {}).get('count', 0)
                targets = len(player_ast_given.get(pid, {}).get('targets', set()))
                team_players[team][pid] = {
                    'id': pid,
                    'name': pname,
                    'ast_given': ast_g,
                    'ast_received': ast_r,
                    'gp': gp,
                    'ast_per_game': round(ast_g / gp, 1) if gp > 0 else 0.0,
                    'unique_targets': targets,
                }

    # Assemble teams dict
    teams_out = {}
    for team_code in sorted(team_players.keys()):
        players_list = sorted(team_players[team_code].values(), key=lambda p: p['ast_given'] + p['ast_received'], reverse=True)
        teams_out[team_code] = {
            'players': players_list,
            'edges': team_edges[team_code],
        }

    # ── Phase 4: Build league-wide tables ────────────────────────────────────
    # Top 20 assist combos
    all_combos = []
    for (passer_id, scorer_id), e in edge_agg.items():
        passer_gp = len(player_games.get(passer_id, set()))
        all_combos.append({
            'passer': e['passer_name'],
            'passer_id': passer_id,
            'scorer': e['scorer_name'],
            'scorer_id': scorer_id,
            'team': e['team'],
            'count': e['count'],
            'fg2': e['fg2'],
            'fg3': e['fg3'],
            'per_game': round(e['count'] / passer_gp, 2) if passer_gp > 0 else 0.0,
        })
    all_combos.sort(key=lambda x: x['count'], reverse=True)
    top_combos = all_combos[:20]

    # Top 20 playmakers
    all_playmakers = []
    for pid, info in player_ast_given.items():
        if info['count'] < 5:
            continue  # skip very low-volume
        gp = len(player_games.get(pid, set()))
        # Find top target
        best_target = ''
        best_target_count = 0
        for (p_id, s_id), e in edge_agg.items():
            if p_id == pid and e['count'] > best_target_count:
                best_target_count = e['count']
                best_target = e['scorer_name']
        all_playmakers.append({
            'player': info['name'],
            'player_id': pid,
            'team': info['team'],
            'ast': info['count'],
            'per_game': round(info['count'] / gp, 1) if gp > 0 else 0.0,
            'unique_targets': len(info['targets']),
            'top_target': best_target,
            'top_target_count': best_target_count,
        })
    all_playmakers.sort(key=lambda x: x['ast'], reverse=True)
    top_playmakers = all_playmakers[:20]

    print(f"  Teams: {len(teams_out)}")
    print(f"  Total edges: {sum(len(t['edges']) for t in teams_out.values())}")
    print(f"  Top combo: {top_combos[0]['passer']} → {top_combos[0]['scorer']} ({top_combos[0]['count']})" if top_combos else "  No combos")

    return {
        'teams': teams_out,
        'top_combos': top_combos,
        'top_playmakers': top_playmakers,
    }
```

- [ ] **Step 2: Add the export call in `main()`**

In `main()`, add the assist network export after the paint profiles export block (after line 992). Follow the exact same pattern as the shot stats and paint profiles exports:

```python
    # ── Assist network export ─────────────────────────────────────────────
    print("\n--- Building assist network ---")
    assist_network = build_assist_network()
    if assist_network:
        assist_path = os.path.join(out_dir, 'assist_network.json')
        with open(assist_path, 'w', encoding='utf-8') as f:
            json.dump(assist_network, f, ensure_ascii=False, indent=2)
        n_teams = len(assist_network.get('teams', {}))
        n_combos = len(assist_network.get('top_combos', []))
        print(f"  Assist network: {n_teams} teams, {n_combos} top combos -> {assist_path}")
```

- [ ] **Step 3: Run the export and verify output**

Run: `.venv/Scripts/python.exe export_dashboard_data.py`

Expected: The script prints assist network stats (teams, edges, top combo) and creates `docs/data/current/assist_network.json`.

Verify the JSON structure:
```bash
.venv/Scripts/python.exe -c "import json; d=json.load(open('docs/data/current/assist_network.json',encoding='utf-8')); print('Teams:', list(d['teams'].keys())[:5]); print('Top combo:', d['top_combos'][0]); print('Top playmaker:', d['top_playmakers'][0])"
```

Expected: Prints 20 team codes, a top combo dict with passer/scorer/count/fg2/fg3/per_game, and a top playmaker dict.

- [ ] **Step 4: Commit**

```bash
git add export_dashboard_data.py docs/data/current/assist_network.json
git commit -m "feat(assists): add build_assist_network() backend + JSON export"
```

---

## Task 2: Frontend HTML — Page Shell (`network.html`)

**Files:**
- Create: `docs/network.html`

The page follows the exact structure of existing pages (shots.html, team.html): nav, header, main with stat-cards, footer. Team chip selector reuses the CSS pattern from team.html.

- [ ] **Step 1: Create `docs/network.html`**

```html
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Playmaking Network — Euroleague Analytics</title>
    <meta name="description"
        content="Interactive assist network visualization for all 20 Euroleague teams. Chord diagrams, top assist combos, and playmaker leaders.">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Outfit:wght@700;800&display=swap"
        rel="stylesheet">
    <link rel="stylesheet" href="style.css">
    <style>
        /* ── Team selector grid (reused pattern from team.html) ── */
        .team-selector-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 0.5rem;
            margin-bottom: 1.5rem;
        }

        @media (max-width: 900px) { .team-selector-grid { grid-template-columns: repeat(4, 1fr); } }
        @media (max-width: 600px) { .team-selector-grid { grid-template-columns: repeat(2, 1fr); } }

        .team-chip {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.45rem 0.4rem;
            text-align: center;
            cursor: pointer;
            transition: var(--transition);
        }

        .team-chip:hover { border-color: #4b5563; background: var(--bg-card); }

        .team-chip.selected {
            border-color: var(--accent-purple);
            background: rgba(168, 85, 247, 0.08);
        }

        .team-chip-name {
            font-weight: 700;
            font-size: 0.82rem;
            display: block;
        }

        /* ── Chord diagram container ─────────────────────────── */
        .chord-wrap {
            display: flex;
            justify-content: center;
            padding: 1rem 0;
        }

        #chord-svg {
            max-width: 540px;
            width: 100%;
            height: auto;
        }

        /* ── Chord interactions ───────────────────────────────── */
        .chord-ribbon {
            transition: opacity 0.2s ease;
            cursor: pointer;
        }

        .chord-arc {
            cursor: pointer;
            transition: opacity 0.2s ease;
        }

        .chord-label {
            font-family: 'Inter', sans-serif;
            fill: var(--text-secondary);
            font-size: 11px;
            font-weight: 600;
        }

        /* ── Tooltip ──────────────────────────────────────────── */
        .chord-tooltip {
            position: fixed;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            font-size: 0.8rem;
            color: var(--text-primary);
            pointer-events: none;
            z-index: 200;
            display: none;
            max-width: 260px;
            line-height: 1.5;
            box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        }

        .chord-tooltip .tt-title {
            font-weight: 700;
            margin-bottom: 0.3rem;
            font-size: 0.85rem;
        }

        .chord-tooltip .tt-row {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
        }

        .chord-tooltip .tt-label { color: var(--text-muted); }
        .chord-tooltip .tt-value { font-weight: 600; }

        /* ── Player detail card ───────────────────────────────── */
        #player-detail {
            display: none;
            margin-top: 1rem;
        }

        #player-detail.visible { display: block; }

        .pd-header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }

        .pd-name {
            font-family: 'Outfit', sans-serif;
            font-size: 1.3rem;
            font-weight: 800;
        }

        .pd-team-badge {
            font-size: 0.75rem;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-weight: 600;
        }

        .pd-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        @media (max-width: 600px) { .pd-grid { grid-template-columns: 1fr; } }

        .pd-section h4 {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .pd-stat-row {
            display: flex;
            justify-content: space-between;
            padding: 0.3rem 0;
            border-bottom: 1px solid var(--border);
            font-size: 0.82rem;
        }

        .pd-stat-row:last-child { border-bottom: none; }

        .pd-stat-label { color: var(--text-secondary); }
        .pd-stat-value { font-weight: 600; }

        .pd-target-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .pd-target-list li {
            display: flex;
            justify-content: space-between;
            padding: 0.25rem 0;
            font-size: 0.82rem;
            border-bottom: 1px solid var(--border);
        }

        .pd-target-list li:last-child { border-bottom: none; }

        /* ── League tables ────────────────────────────────────── */
        .league-tables {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-top: 1.5rem;
        }

        @media (max-width: 768px) { .league-tables { grid-template-columns: 1fr; } }

        .league-table-wrap { overflow-x: auto; }

        .assist-tbl {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.8rem;
            white-space: nowrap;
        }

        .assist-tbl th {
            background: var(--bg-secondary);
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.68rem;
            padding: 0.55rem 0.6rem;
            border-bottom: 2px solid var(--border);
            cursor: pointer;
            user-select: none;
        }

        .assist-tbl th:hover { color: var(--text-primary); }

        .assist-tbl td {
            padding: 0.45rem 0.6rem;
            border-bottom: 1px solid var(--border);
            color: var(--text-primary);
        }

        .assist-tbl tbody tr {
            cursor: pointer;
            transition: background var(--transition);
        }

        .assist-tbl tbody tr:hover {
            background: rgba(168, 85, 247, 0.07);
        }

        .tbl-team-badge {
            display: inline-block;
            padding: 0.1rem 0.4rem;
            border-radius: 3px;
            font-size: 0.7rem;
            font-weight: 600;
        }
    </style>
</head>

<body>

    <nav class="site-nav">
        <span class="site-nav-brand">🏀 Euroleague Analytics</span>
        <a href="index.html" class="nav-link">Season Hub</a>
        <a href="team.html" class="nav-link">Team Deep-Dive</a>
        <a href="players.html" class="nav-link">Player Stats</a>
        <a href="h2h.html" class="nav-link">Head-to-Head</a>
        <a href="recap.html" class="nav-link">Game Recap</a>
        <a href="shots.html" class="nav-link">Shot Lab</a>
        <a href="network.html" class="nav-link active">Playmaking</a>
        <a href="replay.html" class="nav-link">Game Replay</a>
        <a href="playoffs.html" class="nav-link">Playoffs</a>
        <a href="mvp.html" class="nav-link">MVP Race</a>
        <a href="about.html" class="nav-link">About</a>
    </nav>

    <header>
        <h1>🎯 Playmaking Network</h1>
        <p class="subtitle">Assist relationships · Chord diagrams · Top combos · Playmaker leaders</p>
    </header>

    <main>
        <!-- Team selector -->
        <div class="stat-card">
            <h3>Select a Team</h3>
            <div id="team-grid" class="team-selector-grid">
                <div class="loading-placeholder"><span class="loading-spinner"></span> Loading teams…</div>
            </div>
        </div>

        <!-- Chord diagram -->
        <div class="stat-card" id="chord-card" style="display:none">
            <h3 id="chord-title">Assist Network</h3>
            <p style="color:var(--text-muted);font-size:0.8rem;margin-bottom:0.5rem;">
                Top 8 players by assist involvement. Hover a ribbon for details, click a player arc to pin.
            </p>
            <div class="chord-wrap">
                <svg id="chord-svg" viewBox="0 0 540 540"></svg>
            </div>

            <!-- Player detail card -->
            <div id="player-detail" class="stat-card" style="background:var(--bg-secondary);">
                <div class="pd-header">
                    <span class="pd-name" id="pd-name"></span>
                    <span class="pd-team-badge" id="pd-badge"></span>
                </div>
                <div class="pd-grid">
                    <div class="pd-section">
                        <h4>Assists Given</h4>
                        <div id="pd-given"></div>
                    </div>
                    <div class="pd-section">
                        <h4>Assists Received</h4>
                        <div id="pd-received"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- League-wide tables -->
        <div class="league-tables">
            <div class="stat-card">
                <h3>Top 20 Assist Combos</h3>
                <div class="league-table-wrap">
                    <table class="assist-tbl" id="combos-table">
                        <thead></thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
            <div class="stat-card">
                <h3>Top 20 Playmakers</h3>
                <div class="league-table-wrap">
                    <table class="assist-tbl" id="playmakers-table">
                        <thead></thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Error -->
        <div id="load-error" class="hidden" style="text-align:center;padding:3rem 1rem;">
            <div style="font-size:3rem;margin-bottom:1rem;">⚠️</div>
            <p style="color:var(--text-muted);font-size:1rem;">
                Could not load assist network data. Run
                <code>python export_dashboard_data.py</code> to generate it.
            </p>
        </div>
    </main>

    <footer class="site-footer">
        <div class="footer-links">
            <a href="about.html">About & Methodology</a>
            <span class="footer-sep">·</span>
            <a href="https://github.com/giasemidis/euroleague_api" target="_blank" rel="noopener">Data: Euroleague API</a>
            <span class="footer-sep">·</span>
            <a href="https://github.com/KonstantinosLaloudakis" target="_blank" rel="noopener">GitHub</a>
        </div>
        <div>19 seasons · 7,000+ games · Updated daily</div>
    </footer>

    <!-- Tooltip (positioned via JS) -->
    <div class="chord-tooltip" id="chord-tooltip"></div>

    <script src="constants.js"></script>
    <script src="network.js"></script>
</body>

</html>
```

- [ ] **Step 2: Commit**

```bash
git add docs/network.html
git commit -m "feat(assists): add network.html page shell"
```

---

## Task 3: Frontend JS — Data Loading & Team Selector (`network.js`)

**Files:**
- Create: `docs/network.js`

This task covers the data fetch, team chip rendering, team selection with URL param sync, and skeleton function stubs.

- [ ] **Step 1: Create `docs/network.js` with data loading and team selector**

```javascript
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
        const color = TEAM_COLORS[code] || '#6b7280';
        const name = TEAM_NAMES[code] || code;
        return `<div class="team-chip" id="chip-${code}"
                     onclick="selectTeam('${code}')"
                     style="border-top:3px solid ${color}40">
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/network.js
git commit -m "feat(assists): add network.js with data loading and team selector"
```

---

## Task 4: Frontend JS — Chord Diagram SVG Rendering

**Files:**
- Modify: `docs/network.js` (append chord rendering logic)

The chord diagram is built entirely with SVG path elements: arcs on the outer ring per player, and bezier ribbons connecting passer to scorer.

- [ ] **Step 1: Add the `renderChord()` function**

Append to `docs/network.js`:

```javascript
// ── Chord diagram rendering ──────────────────────────────────────────────────

function renderChord(teamData, teamCode) {
    const svg = document.getElementById('chord-svg');
    svg.innerHTML = '';

    const cx = 270, cy = 270, outerR = 240, innerR = 220;
    const teamColor = TEAM_COLORS[teamCode] || '#6b7280';

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
    // proportional to its count relative to the player's total involvement
    const arcUsed = {}; // player_id -> current angle offset within their arc
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
```

- [ ] **Step 2: Verify the page renders**

Open `docs/network.html` in a browser (via local server or file). You should see:
- 20 team chips sorted alphabetically by team name
- First team's chord diagram rendering with colored arcs and ribbons
- Labels around the outside of the circle

- [ ] **Step 3: Commit**

```bash
git add docs/network.js
git commit -m "feat(assists): add chord diagram SVG rendering"
```

---

## Task 5: Frontend JS — Interactions (Hover, Click, Tooltip)

**Files:**
- Modify: `docs/network.js` (append interaction logic)

- [ ] **Step 1: Add highlight, tooltip, and pin functions**

Append to `docs/network.js`:

```javascript
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
        <div class="tt-row"><span class="tt-label">% of ${scorer}'s baskets</span><span class="tt-value">${scorerPct}%</span></div>
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
```

- [ ] **Step 2: Verify interactions**

Open the page in a browser:
- Hover over a player arc → only that player's ribbons stay bright, others fade
- Hover over a ribbon → rich tooltip appears with count, 2PT/3PT, per game, percentages
- Click a player arc → highlight pins, detail card appears
- Click same player again → unpin, everything returns to normal

- [ ] **Step 3: Commit**

```bash
git add docs/network.js
git commit -m "feat(assists): add hover/click/tooltip interactions"
```

---

## Task 6: Frontend JS — Player Detail Card

**Files:**
- Modify: `docs/network.js` (append player detail logic)

- [ ] **Step 1: Add `showPlayerDetail()` function**

Append to `docs/network.js`:

```javascript
// ── Player detail card ───────────────────────────────────────────────────────

function showPlayerDetail(playerId) {
    if (!_data || !_selected) return;
    const team = _data.teams[_selected];
    const player = team.players.find(p => p.id === playerId);
    if (!player) return;

    const color = TEAM_COLORS[_selected] || '#6b7280';
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
```

- [ ] **Step 2: Verify the player detail card**

Open the page, click a player arc:
- Card appears below the chord diagram
- Shows player name + team badge
- "Assists Given" section: total, per game, unique targets, top 5 targets with counts and shot type split
- "Assists Received" section: total assisted baskets, top 5 feeders
- Click again to unpin and hide

- [ ] **Step 3: Commit**

```bash
git add docs/network.js
git commit -m "feat(assists): add player detail card on arc click"
```

---

## Task 7: Frontend JS — League-Wide Tables

**Files:**
- Modify: `docs/network.js` (append table rendering)

Both tables are sortable. Clicking a combo row navigates to that team's chord diagram.

- [ ] **Step 1: Add table rendering functions**

Append to `docs/network.js`:

```javascript
// ── League-wide tables ───────────────────────────────────────────────────────

const COMBO_COLS = [
    { key: '#',        label: '#',       fmt: (_, i) => i + 1 },
    { key: 'passer',   label: 'Passer',  fmt: v => formatPlayerName(v) },
    { key: 'scorer',   label: 'Scorer',  fmt: v => formatPlayerName(v) },
    { key: 'team',     label: 'Team',    fmt: v => `<span class="tbl-team-badge" style="background:${(TEAM_COLORS[v]||'#555')}22;color:${TEAM_COLORS[v]||'#999'}">${v}</span>` },
    { key: 'count',    label: 'AST',     fmt: v => v },
    { key: 'fg2',      label: '2PT',     fmt: v => v },
    { key: 'fg3',      label: '3PT',     fmt: v => v },
    { key: 'per_game', label: '/Game',   fmt: v => v.toFixed(2) },
];

const PLAYMAKER_COLS = [
    { key: '#',              label: '#',          fmt: (_, i) => i + 1 },
    { key: 'player',         label: 'Player',     fmt: v => formatPlayerName(v) },
    { key: 'team',           label: 'Team',       fmt: v => `<span class="tbl-team-badge" style="background:${(TEAM_COLORS[v]||'#555')}22;color:${TEAM_COLORS[v]||'#999'}">${v}</span>` },
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
```

- [ ] **Step 2: Verify tables**

Open the page:
- Two tables appear side by side below the chord diagram
- "Top 20 Assist Combos" shows passer, scorer, team badge, AST, 2PT, 3PT, /Game
- "Top 20 Playmakers" shows player, team, AST, /Game, Targets, Top Target
- Click a column header → table re-sorts (ascending/descending toggle)
- Click a row → scrolls up and switches to that team's chord diagram

- [ ] **Step 3: Commit**

```bash
git add docs/network.js
git commit -m "feat(assists): add sortable league-wide tables"
```

---

## Task 8: Nav Integration — Add "Playmaking" Link to All Pages

**Files:**
- Modify: All 10 existing HTML files in `docs/`

Add `<a href="network.html" class="nav-link">Playmaking</a>` after the "Shot Lab" link in the nav bar of every page.

- [ ] **Step 1: Add the nav link to all 10 pages**

In each of these files, find the line:
```html
        <a href="shots.html" class="nav-link">Shot Lab</a>
```

And insert immediately after it:
```html
        <a href="network.html" class="nav-link">Playmaking</a>
```

Files to modify (all in `docs/`):
1. `index.html`
2. `team.html`
3. `players.html`
4. `h2h.html`
5. `recap.html`
6. `shots.html`
7. `replay.html`
8. `playoffs.html`
9. `mvp.html`
10. `about.html`

- [ ] **Step 2: Verify nav**

Open any page and confirm "Playmaking" appears in the nav bar between "Shot Lab" and "Game Replay".

- [ ] **Step 3: Commit**

```bash
git add docs/index.html docs/team.html docs/players.html docs/h2h.html docs/recap.html docs/shots.html docs/replay.html docs/playoffs.html docs/mvp.html docs/about.html
git commit -m "feat(assists): add Playmaking nav link to all pages"
```

---

## Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the pages list**

In `CLAUDE.md`, find the line:
```
**Pages:** index.html (Season Hub), team.html, players.html, h2h.html, recap.html, shots.html, replay.html, playoffs.html, mvp.html, about.html
```

Replace with:
```
**Pages:** index.html (Season Hub), team.html, players.html, h2h.html, recap.html, shots.html, network.html (Playmaking), replay.html, playoffs.html, mvp.html, about.html
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add network.html to CLAUDE.md pages list"
```

---

## Task 10: End-to-End Verification

- [ ] **Step 1: Run the full export pipeline**

```bash
.venv/Scripts/python.exe export_dashboard_data.py
```

Verify: `docs/data/current/assist_network.json` is created with valid JSON containing `teams`, `top_combos`, `top_playmakers`.

- [ ] **Step 2: Test the page end-to-end**

Open `docs/network.html` in a browser (via a local server for fetch to work):
```bash
cd docs && python -m http.server 8000
```

Then open `http://localhost:8000/network.html` and verify:
1. Team chips render with team colors
2. Default team selected and chord diagram shows
3. Click different team chip → diagram re-renders
4. Hover player arc → ribbons highlight
5. Hover ribbon → tooltip with rich stats
6. Click player arc → detail card appears
7. Tables render with sorting
8. Click table row → navigates to that team
9. URL updates with `?team=XXX`
10. Direct link `?team=OLY` loads correctly

- [ ] **Step 3: Verify nav across pages**

Open `index.html`, `shots.html`, `mvp.html` — confirm "Playmaking" link appears and navigates to `network.html`.

- [ ] **Step 4: Final commit (if any fixes needed)**

If any issues were found and fixed during verification, commit those fixes.
