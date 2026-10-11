'use strict';

const DASHBOARD_URL = 'data/current/dashboard.json';

function teamColor(code) {
  return (typeof TEAM_COLORS !== 'undefined' && TEAM_COLORS[code]) || '#6b7280';
}

function teamName(code) {
  return (typeof TEAM_NAMES !== 'undefined' && TEAM_NAMES[code]) || code;
}

function renderHero(checkpoints) {
  const latest     = checkpoints[checkpoints.length - 1];
  const prePlayoff = checkpoints[0];

  // Current leader (highest current odds)
  const [leaderCode, leaderPct] = Object.entries(latest.odds)
    .sort((a, b) => b[1] - a[1])[0];

  // Biggest gainer among alive teams (vs pre-playoff)
  const [gainerCode, gainerDelta] = Object.entries(latest.odds)
    .filter(([, v]) => v > 0)
    .map(([t, v]) => [t, v - (prePlayoff.odds[t] || 0)])
    .sort((a, b) => b[1] - a[1])[0];

  // Eliminated count
  const eliminatedCount = Object.values(latest.odds).filter(v => v === 0).length;

  const leaderColor = teamColor(leaderCode);
  const gainerColor = '#22c55e';
  const elimColor   = '#f59e0b';

  document.getElementById('chase-hero').innerHTML = `
    <div class="chase-hero-card" style="--card-accent:${leaderColor}">
      <div class="chase-hero-label">Current Leader</div>
      <div class="chase-hero-value" style="color:${leaderColor}">${leaderCode}</div>
      <div class="chase-hero-sub">${teamName(leaderCode)} · <strong style="color:var(--text-primary)">${leaderPct.toFixed(1)}%</strong></div>
    </div>
    <div class="chase-hero-card" style="--card-accent:${gainerColor}">
      <div class="chase-hero-label">Biggest Gainer</div>
      <div class="chase-hero-value" style="color:${gainerColor}">${gainerCode}</div>
      <div class="chase-hero-sub">${teamName(gainerCode)} · <strong style="color:${gainerColor}">${gainerDelta >= 0 ? '+' : ''}${gainerDelta.toFixed(1)}pp</strong> since pre-playoff</div>
    </div>
    <div class="chase-hero-card" style="--card-accent:${elimColor}">
      <div class="chase-hero-label">Eliminated</div>
      <div class="chase-hero-value" style="color:${elimColor}">${eliminatedCount}</div>
      <div class="chase-hero-sub">teams at 0% title odds</div>
    </div>
  `;
}

document.addEventListener('DOMContentLoaded', async () => {
  let dashboard;
  try {
    const r = await loadPlayoffDashboard();
    dashboard = r.dash;
    const season = r.archived ? r.archivedSeason : dashboardSeason(dashboard);
    document.getElementById('chase-title').textContent = `🏆 ${seasonLabel(season)} Championship Chase`;
    document.getElementById('chase-banner').innerHTML = seasonBannerHTML(r);
  } catch {
    document.getElementById('chase-hero').innerHTML =
      '<p style="color:var(--text-muted);padding:40px;text-align:center">Could not load data.</p>';
    return;
  }

  const checkpoints = dashboard.championship_odds_history || [];
  if (checkpoints.length === 0) {
    document.getElementById('chase-hero').innerHTML =
      '<p style="color:var(--text-muted);padding:40px;text-align:center">No championship odds data available.</p>';
    return;
  }

  renderHero(checkpoints);
  renderChart(checkpoints);
  renderTable(checkpoints);
});

function renderChart(checkpoints) {
  // Deduplicate: keep only the LAST checkpoint per unique label.
  // Multiple checkpoints share the same label (e.g. "QF Round 2" × 4);
  // the last one has the most up-to-date odds for that round.
  const labelMap = new Map();
  checkpoints.forEach(c => labelMap.set(c.label, c));
  // Preserve original label order
  const seenOrder = [];
  checkpoints.forEach(c => {
    if (!seenOrder.includes(c.label)) seenOrder.push(c.label);
  });
  const dedupedCheckpoints = seenOrder.map(l => labelMap.get(l));

  const labels = dedupedCheckpoints.map(c => c.label);
  const latest = checkpoints[checkpoints.length - 1];

  const allTeams = Object.entries(latest.odds)
    .sort((a, b) => b[1] - a[1])
    .map(([code]) => code);

  const traces = allTeams.map(code => {
    const isEliminated = latest.odds[code] === 0;
    const color        = teamColor(code);
    const yValues      = dedupedCheckpoints.map(c => c.odds[code] ?? 0);

    return {
      x: labels,
      y: yValues,
      name: teamName(code),
      type: 'scatter',
      mode: 'lines+markers',
      line:   { color, width: isEliminated ? 1.5 : 2.5, dash: isEliminated ? 'dash' : 'solid' },
      marker: { color, size: isEliminated ? 3 : 5 },
      opacity: isEliminated ? 0.4 : 1.0,
      // Eliminated teams hidden by default — togglable via legend click
      visible: isEliminated ? 'legendonly' : true,
      hovertemplate: `<b>${teamName(code)}</b><br>%{y:.1f}%<extra></extra>`,
    };
  });

  const layout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'transparent',
    font:  { color: '#9ca3af', family: 'Inter, sans-serif', size: 11 },
    xaxis: {
      gridcolor:  '#2d2e3a',
      tickangle:  -20,
      automargin: true,
    },
    yaxis: {
      title:      { text: 'Title Probability (%)', font: { size: 11 } },
      gridcolor:  '#2d2e3a',
      ticksuffix: '%',
      rangemode:  'tozero',
      automargin: true,
    },
    legend: {
      bgcolor:     'rgba(26,27,35,0.85)',
      bordercolor: '#2d2e3a',
      borderwidth: 1,
      font:        { size: 11 },
    },
    margin: { t: 16, r: 16, b: 80, l: 60 },
    shapes: [],
    annotations: [],
  };

  Plotly.newPlot('chase-chart', traces, layout, { displayModeBar: false, responsive: true });
}

function renderTable(checkpoints) {
  const latest     = checkpoints[checkpoints.length - 1];
  const prePlayoff = checkpoints[0];

  // Deduplicate same as chart: keep last checkpoint per unique label
  const labelMap = new Map();
  checkpoints.forEach(c => labelMap.set(c.label, c));
  const seenOrder = [];
  checkpoints.forEach(c => { if (!seenOrder.includes(c.label)) seenOrder.push(c.label); });
  const dedupedCheckpoints = seenOrder.map(l => labelMap.get(l));

  const allTeams = Object.entries(latest.odds)
    .sort((a, b) => b[1] - a[1])
    .map(([code]) => code);

  const headerCells = dedupedCheckpoints.map(c =>
    `<th>${c.label}</th>`
  ).join('');

  const rows = allTeams.map(code => {
    const isEliminated = latest.odds[code] === 0;
    const delta        = (latest.odds[code] ?? 0) - (prePlayoff.odds[code] || 0);
    const deltaClass   = delta > 0.05 ? 'delta-pos' : delta < -0.05 ? 'delta-neg' : 'delta-zero';
    const deltaStr     = delta > 0.05 ? `+${delta.toFixed(1)}pp` : delta < -0.05 ? `${delta.toFixed(1)}pp` : '—';
    const color        = teamColor(code);

    const cells = dedupedCheckpoints.map(c => {
      const v = c.odds[code] ?? 0;
      return `<td>${v === 0 ? '—' : v.toFixed(1) + '%'}</td>`;
    }).join('');

    return `
      <tr class="${isEliminated ? 'eliminated' : ''}">
        <td style="color:${isEliminated ? 'var(--text-muted)' : color}">${code}</td>
        ${cells}
        <td class="${deltaClass}">${deltaStr}</td>
      </tr>`;
  }).join('');

  document.getElementById('chase-table').innerHTML = `
    <table class="chase-table">
      <thead>
        <tr>
          <th>Team</th>
          ${headerCells}
          <th>Δ</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}
