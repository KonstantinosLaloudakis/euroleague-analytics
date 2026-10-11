let _dashSeason = 2025;
const VALID_SLOTS = ['qf1', 'qf2', 'qf3', 'qf4', 'sf1', 'sf2', 'final'];

function getSlotId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('id');
}

function teamName(code) {
  return (typeof TEAM_NAMES !== 'undefined' && TEAM_NAMES[code]) || code;
}

function renderError(root, msg) {
  root.innerHTML = `<div class="series-error"><h1>Series not found</h1><p>${msg}</p></div>`;
}

function renderIndex(root, series) {
  const items = VALID_SLOTS.map(id => {
    const s = series[id] || {};
    const teams = s.high_seed && s.low_seed
      ? `${s.high_seed.team} vs ${s.low_seed.team}`
      : 'TBD';
    return `<li><a href="series.html?id=${id}">${s.label || id} — ${teams}</a></li>`;
  }).join('');
  root.innerHTML = `<h1>All series</h1><ul class="series-index">${items}</ul>`;
}

async function main() {
  const root = document.getElementById('series-root');
  const slotId = getSlotId();

  let dashboard, banner = '';
  try {
    const r = await loadPlayoffDashboard();
    dashboard = r.dash;
    banner = seasonBannerHTML(r);
    _dashSeason = dashboardSeason(dashboard);
  } catch (err) {
    renderError(root, 'Could not load dashboard data.');
    return;
  }

  const series = dashboard.series || {};
  if (!slotId) {
    renderIndex(root, series);
    root.insertAdjacentHTML('afterbegin', banner);
    return;
  }
  if (!VALID_SLOTS.includes(slotId)) {
    renderError(root, `Invalid series id: "${slotId}". Valid ids: ${VALID_SLOTS.join(', ')}.`);
    return;
  }

  const entry = series[slotId];
  if (!entry) {
    renderError(root, `No data available for "${slotId}".`);
    return;
  }

  renderSeries(root, entry, dashboard);
  root.insertAdjacentHTML('afterbegin', banner);
}

function renderSeries(root, entry, dashboard) {
  root.innerHTML = `
    <section id="series-hero" class="series-section"></section>
    <section id="series-tale" class="series-section"></section>
    <section id="series-momentum" class="series-section"></section>
    <section id="series-simulate" class="series-section"></section>
    <section id="series-timeline" class="series-section"></section>
    <section id="series-h2h" class="series-section"></section>
    <section id="series-recaps" class="series-section"></section>
  `;
  renderHero(document.getElementById('series-hero'), entry);
  renderTaleOfTheTape(document.getElementById('series-tale'), entry);
  renderMomentum(document.getElementById('series-momentum'), entry);
  renderSimulate(document.getElementById('series-simulate'), entry, dashboard);
  renderTimeline(document.getElementById('series-timeline'), entry);
  renderH2H(document.getElementById('series-h2h'), entry);
  renderRecaps(document.getElementById('series-recaps'), entry, dashboard);
}

// ── Hero ────────────────────────────────────────────────────────────────

function teamColor(code) {
  return (typeof TEAM_COLORS !== 'undefined' && TEAM_COLORS[code]) || '#6b7280';
}

function renderHero(container, entry) {
  const { high_seed, low_seed, wins, status, winner, series_win_prob, label, format } = entry;
  const isAwaiting = status === 'awaiting_teams';
  const isCompleted = status === 'completed';
  const isNotStarted = status === 'not_started';

  const teamPanel = (s, side) => {
    if (!s) {
      return `<div class="series-team-panel series-team-pending">
        <div class="series-team-logo-wrap"><div class="series-team-logo-placeholder">?</div></div>
        <div class="series-team-info">
          <div class="series-team-seed">TBD</div>
          <div class="series-team-name">Awaiting opponent</div>
        </div>
      </div>`;
    }
    const color = teamColor(s.team);
    const seed = s.seed != null ? `Seed #${s.seed}` : '';
    const prob = series_win_prob && series_win_prob[side] != null ? series_win_prob[side] : null;
    const showProb = !isAwaiting && !isCompleted && prob != null;
    const isWinner = isCompleted && winner === s.team;
    return `<div class="series-team-panel${isWinner ? ' series-team-panel-winner' : ''}" style="--team-color:${color}">
      <div class="series-team-logo-wrap">
        <img class="series-team-logo" src="logos/${s.team}.png" alt="${s.team}" onerror="this.style.display='none'">
      </div>
      <div class="series-team-info">
        <div class="series-team-seed">${seed}</div>
        <div class="series-team-name">${teamName(s.team)}</div>
        ${showProb ? `<div class="series-team-prob">${prob.toFixed(1)}%</div>` : ''}
        ${isWinner ? '<div class="series-team-winner-tag">🏆 Winner</div>' : ''}
      </div>
    </div>`;
  };

  const statusChip = () => {
    if (isAwaiting) return '<span class="series-status-chip awaiting">Matchup pending</span>';
    if (isNotStarted) return '<span class="series-status-chip not-started">Series not started</span>';
    if (isCompleted) return `<span class="series-status-chip completed">Final · ${teamName(winner)}</span>`;
    const leaderCode = wins.high > wins.low ? (high_seed && high_seed.team) : (low_seed && low_seed.team);
    return `<span class="series-status-chip live">Live · ${Math.max(wins.high, wins.low)}-${Math.min(wins.high, wins.low)} ${leaderCode || ''}</span>`;
  };

  const fmtLine = () => {
    if (format === 'best_of_5') return 'Best-of-5 · 2-2-1 home pattern';
    if (format === 'single_game') return 'Final Four · Single game, neutral venue';
    return format;
  };

  const probBar = () => {
    if (isCompleted || isAwaiting) return '';
    const h = (series_win_prob && series_win_prob.high) || 0;
    const l = (series_win_prob && series_win_prob.low) || 0;
    const hColor = teamColor(high_seed && high_seed.team);
    const lColor = teamColor(low_seed && low_seed.team);
    return `
      <div class="series-prob-bar">
        <div class="series-prob-fill" style="width:${h}%;background:${hColor}"></div>
        <div class="series-prob-fill" style="width:${l}%;background:${lColor}"></div>
      </div>
    `;
  };

  container.innerHTML = `
    <div class="series-hero">
      <div class="series-hero-top">
        <h1 class="series-title">${label}</h1>
        <div class="series-hero-meta">
          ${statusChip()}
          <span class="series-format-chip">${fmtLine()}</span>
        </div>
      </div>
      <div class="series-teams">
        ${teamPanel(high_seed, 'high')}
        <div class="series-vs">VS</div>
        ${teamPanel(low_seed, 'low')}
      </div>
      ${probBar()}
    </div>
  `;
}

// ── Timeline ────────────────────────────────────────────────────────────

function renderTimeline(container, entry) {
  const games = entry.games || [];
  const visible = games.filter(g => g.status !== 'unnecessary');
  if (visible.length === 0) {
    container.innerHTML = '';
    return;
  }
  const title = entry.format === 'single_game' ? 'Game' : 'Game-by-game';
  const boxes = visible.map(g => renderGameBox(g, entry)).join('');
  container.innerHTML = `
    <h2 class="series-section-title">${title}</h2>
    <div class="series-timeline">${boxes}</div>
  `;
  startCountdowns(container);
}

function renderGameBox(g, entry) {
  const isSingle = entry && entry.format === 'single_game';
  const num = isSingle ? 'Final Four' : `G${g.game_num}`;
  const homeColor = g.home ? teamColor(g.home) : '#6b7280';
  const neutralStyle = 'style="--home-color:#9fb7d9"';
  const homeStyle = `style="--home-color:${homeColor}"`;

  if (g.status === 'completed') {
    const winnerCls = g.winner === g.home ? 'home-win' : 'away-win';
    const link = g.gamecode
      ? `replay.html?season=${_dashSeason}&gamecode=${g.gamecode}`
      : null;
    const inner = `
      <div class="series-game-num">${num}</div>
      <div class="series-game-score ${winnerCls}">
        <span class="${g.winner === g.home ? 'winner' : ''}">${g.home} ${g.home_score}</span>
        <span class="${g.winner === g.away ? 'winner' : ''}">${g.away} ${g.away_score}</span>
      </div>
      <div class="series-game-date">${formatDate(g.date)}</div>
      <div class="series-game-status">Final</div>
    `;
    return link
      ? `<a class="series-game-box completed" ${homeStyle} href="${link}">${inner}</a>`
      : `<div class="series-game-box completed" ${homeStyle}>${inner}</div>`;
  }

  if (g.neutral || isSingle) {
    const highTeam = entry && entry.high_seed && entry.high_seed.team;
    const lowTeam = entry && entry.low_seed && entry.low_seed.team;
    const highWp = g.pregame_wp && g.pregame_wp.high;
    const lowWp = g.pregame_wp && g.pregame_wp.low;
    const wpLine = (highTeam && lowTeam && highWp != null)
      ? `<div class="series-game-wp">${highTeam} ${highWp.toFixed(0)}% / ${lowTeam} ${lowWp.toFixed(0)}%</div>`
      : '';
    return `
      <div class="series-game-box upcoming" ${neutralStyle}>
        <div class="series-game-num">${num}</div>
        <div class="series-game-venue">Neutral venue</div>
        <div class="series-game-date">${formatUpcoming(g)}</div>
        <div class="series-game-countdown" data-tipoff-iso="${buildTipoffISO(g) || ''}"></div>
        ${wpLine}
      </div>
    `;
  }

  const homeWp = g.pregame_wp && g.pregame_wp.home;
  const awayWp = g.pregame_wp && g.pregame_wp.away;
  const venue = g.home ? `@ ${g.home}` : 'TBD';
  return `
    <div class="series-game-box upcoming" ${homeStyle}>
      <div class="series-game-num">${num}</div>
      <div class="series-game-venue">${venue}</div>
      <div class="series-game-date">${formatUpcoming(g)}</div>
      <div class="series-game-countdown" data-tipoff-iso="${buildTipoffISO(g) || ''}"></div>
      ${homeWp != null ? `<div class="series-game-wp">${g.home} ${homeWp.toFixed(0)}% / ${g.away} ${awayWp.toFixed(0)}%</div>` : ''}
    </div>
  `;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Schedule API serves CET/CEST. Playoffs run late Apr–May, always in CEST (UTC+2).
const _MONTHS_3 = { Jan:'01', Feb:'02', Mar:'03', Apr:'04', May:'05', Jun:'06',
                    Jul:'07', Aug:'08', Sep:'09', Oct:'10', Nov:'11', Dec:'12' };

function _parseScheduleDate(str) {
  const m = str && str.match(/^(\w{3})\s+(\d{1,2}),\s+(\d{4})$/);
  if (!m) return null;
  const mm = _MONTHS_3[m[1]];
  if (!mm) return null;
  return { yyyy: m[3], mm, dd: m[2].padStart(2, '0') };
}

// Build an ISO-8601 instant from a game's date + tipoff, treating it as CEST (+02:00).
// Returns null if the data is missing or unconfirmed.
function buildTipoffISO(g) {
  if (!g || !g.date) return null;
  const confirmed = g.tipoff_confirmed !== false;
  const tipoff = g.tipoff;
  if (!confirmed || !tipoff || tipoff === '00:00') return null;
  const parts = _parseScheduleDate(g.date);
  if (!parts) return null;
  return `${parts.yyyy}-${parts.mm}-${parts.dd}T${tipoff}:00+02:00`;
}

// ── Countdown timers ────────────────────────────────────────────────────────
function _formatCountdown(isoStr) {
  if (!isoStr) return '';
  const target = new Date(isoStr);
  if (isNaN(target.getTime())) return '';
  const now = Date.now();
  const diff = target.getTime() - now;
  if (diff <= 0) return diff > -3600000 ? '⏱ Starting soon' : ''; // hide after 1h past
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(mins / 60);
  const days  = Math.floor(hours / 24);
  if (days >= 2) return `⏳ ${days}d ${hours % 24}h`;
  if (days === 1) return `⏳ Tomorrow`;
  if (hours >= 1) return `⏳ Today · ${hours}h ${mins % 60}m`;
  return `⏳ ${mins}m`;
}

function startCountdowns(scope) {
  const root = scope || document;
  const tick = () => {
    root.querySelectorAll('.series-game-countdown[data-tipoff-iso]').forEach(el => {
      el.textContent = _formatCountdown(el.dataset.tipoffIso);
    });
  };
  tick();
  // Update every minute; store interval id on the root element to avoid duplicates
  if (root._countdownTimer) clearInterval(root._countdownTimer);
  root._countdownTimer = setInterval(tick, 60000);
}

function formatUpcoming(g) {
  if (!g || !g.date) return 'TBD';
  const confirmed = g.tipoff_confirmed !== false;
  const tipoff = g.tipoff;
  const hasUsableTime = confirmed && tipoff && tipoff !== '00:00';

  // Date-only fallback: no usable tip-off, render in CET (no TZ shift needed for date).
  if (!hasUsableTime) {
    const d = new Date(g.date);
    return isNaN(d.getTime())
      ? g.date
      : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  }

  // Build a real instant by treating "MMM DD, YYYY" + "HH:MM" as CEST (+02:00).
  const parts = _parseScheduleDate(g.date);
  if (!parts) return `${g.date} · ${tipoff}`;
  const iso = `${parts.yyyy}-${parts.mm}-${parts.dd}T${tipoff}:00+02:00`;
  const dt = new Date(iso);
  if (isNaN(dt.getTime())) return `${g.date} · ${tipoff}`;

  // 2025 Final Four venue: Barclays Arena, Hamburg — UTC+2 (CEST)
  // Update this constant each season to reflect the host city's timezone.
  const F4_VENUE_TIMEZONE = 'Europe/Berlin';

  // Format in the home arena's local timezone; neutral/F4 games use venue timezone.
  const tz = (typeof TEAM_TIMEZONES !== 'undefined' && TEAM_TIMEZONES[g.home])
             || F4_VENUE_TIMEZONE;
  const dateLabel = dt.toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', timeZone: tz,
  });
  const timeLabel = dt.toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
  });
  return `${dateLabel} · ${timeLabel}`;
}

// ── Regular-Season H2H ──────────────────────────────────────────────────

function renderH2H(container, entry) {
  const meetings = entry.rs_h2h || [];
  const highTeam = entry.high_seed && entry.high_seed.team;
  const lowTeam = entry.low_seed && entry.low_seed.team;

  if (!highTeam || !lowTeam) {
    container.innerHTML = `
      <h2 class="series-section-title">Regular-season H2H</h2>
      <p class="series-empty">Waiting for both teams to be determined.</p>
    `;
    return;
  }

  if (meetings.length === 0) {
    container.innerHTML = `
      <h2 class="series-section-title">Regular-season H2H</h2>
      <p class="series-empty">No regular-season meetings.</p>
    `;
    return;
  }

  const cards = meetings.map(m => {
    const winnerColor = teamColor(m.winner);
    const homeIsWinner = m.winner === m.home;
    const awayIsWinner = m.winner === m.away;
    return `
      <div class="series-h2h-card" style="--winner-color:${winnerColor}">
        <div class="series-h2h-round">Round ${m.round} · ${m.home} home</div>
        <div class="series-h2h-teams">
          <div class="series-h2h-side${homeIsWinner ? ' winner' : ''}">
            <img class="series-h2h-logo" src="logos/${m.home}.png" alt="${m.home}" onerror="this.style.display='none'">
            <span class="series-h2h-team">${m.home}</span>
            <span class="series-h2h-score-val">${m.home_score}</span>
          </div>
          <div class="series-h2h-dash">–</div>
          <div class="series-h2h-side${awayIsWinner ? ' winner' : ''}">
            <span class="series-h2h-score-val">${m.away_score}</span>
            <span class="series-h2h-team">${m.away}</span>
            <img class="series-h2h-logo" src="logos/${m.away}.png" alt="${m.away}" onerror="this.style.display='none'">
          </div>
        </div>
      </div>
    `;
  }).join('');

  let highWins = 0, lowWins = 0, highPts = 0, lowPts = 0;
  meetings.forEach(m => {
    const highIsHome = m.home === highTeam;
    const hs = highIsHome ? m.home_score : m.away_score;
    const ls = highIsHome ? m.away_score : m.home_score;
    highPts += hs;
    lowPts += ls;
    if (m.winner === highTeam) highWins += 1;
    else lowWins += 1;
  });
  const margin = highPts - lowPts;
  const marginLeader = margin > 0 ? highTeam : (margin < 0 ? lowTeam : 'even');
  const marginStr = margin === 0 ? 'Combined margin: even' : `Combined margin: ${marginLeader} +${Math.abs(margin)}`;

  container.innerHTML = `
    <h2 class="series-section-title">Regular-season H2H</h2>
    <div class="series-h2h-cards">${cards}</div>
    <div class="series-h2h-summary">Season split: ${highTeam} ${highWins}-${lowWins} ${lowTeam} · ${marginStr}</div>
  `;
}

// ── Recaps ──────────────────────────────────────────────────────────────

function renderRecaps(container, entry, dashboard) {
  const highTeam = entry.high_seed && entry.high_seed.team;
  const lowTeam = entry.low_seed && entry.low_seed.team;
  if (!highTeam || !lowTeam) {
    container.innerHTML = '';
    return;
  }

  const allRecaps = (dashboard && dashboard.playoff_recaps) || [];
  const pair = new Set([highTeam, lowTeam]);
  const matching = allRecaps.filter(r =>
    pair.has(r.home) && pair.has(r.away)
  );

  if (matching.length === 0) {
    container.innerHTML = '';
    return;
  }

  const cards = matching.map(r => renderRecapCard(r)).join('');
  container.innerHTML = `
    <h2 class="series-section-title">Game recaps</h2>
    <div class="series-recaps">${cards}</div>
  `;
}

function renderRecapCard(r) {
  const score = `${r.home} ${r.home_score} – ${r.away} ${r.away_score}`;
  const pre = r.pre_game_win_prob != null ? `Pre-game ${r.winner} win prob: ${r.pre_game_win_prob}%` : '';
  const upset = r.is_upset ? '<span class="recap-upset">Upset</span>' : '';
  const title = r.series_label || r.round || '';
  return `
    <div class="series-recap-card">
      <div class="recap-title">${title} ${upset}</div>
      <div class="recap-score ${r.winner === r.home ? 'home-win' : 'away-win'}">${score}</div>
      <div class="recap-pre">${pre}</div>
    </div>
  `;
}

// ── Tale of the Tape ────────────────────────────────────────────────────

function _formatTotValue(metric, value) {
  if (value == null || isNaN(value)) return '—';
  if (metric === 'ft_rate') return Number(value).toFixed(2);
  if (metric === 'pace') return Number(value).toFixed(1);
  return Number(value).toFixed(1);
}

function _suffixForMetric(metric) {
  if (metric === 'pace') return '';
  if (metric === 'ft_rate') return '';
  if (['three_pct', 'paint_pct', 'bench_share'].includes(metric)) return '%';
  return '';
}

function renderTaleOfTheTape(container, entry) {
  if (!container) return;
  const tot = entry && entry.tale_of_the_tape;
  if (!tot || !Array.isArray(tot.rows) || tot.rows.length === 0) {
    container.innerHTML = '';
    return;
  }

  const high = entry.high_seed && entry.high_seed.team;
  const low = entry.low_seed && entry.low_seed.team;
  const colorH = teamColor(high);
  const colorL = teamColor(low);

  const rowsHtml = tot.rows.map(r => {
    const lowerBetter = !!r.lower_is_better;
    // "Winner" (visually emphasized) is the side with the better stat.
    const hWins = lowerBetter ? r.high <= r.low : r.high >= r.low;
    const lWins = !hWins;

    // Bar widths: proportional split, floor at 15% so the loser is still visible.
    const total = (Number(r.high) || 0) + (Number(r.low) || 0);
    let hPct = 50, lPct = 50;
    if (total > 0) {
      hPct = Math.max(15, Math.min(85, Math.round((r.high / total) * 100)));
      lPct = 100 - hPct;
    }

    return `
      <div class="tot-row-block">
        <div class="tot-row-label">${r.label}</div>
        <div class="tot-row">
          <div class="tot-value high ${lWins ? 'dim' : ''}">${_formatTotValue(r.metric, r.high)}${_suffixForMetric(r.metric)}</div>
          <div class="tot-bar-wrap">
            <div class="tot-bar-half high ${lWins ? 'dim' : ''}"
                 style="width:${hPct}%; background:${colorH || 'var(--accent-blue)'}"></div>
            <div class="tot-bar-half low ${hWins ? 'dim' : ''}"
                 style="width:${lPct}%; background:${colorL || 'var(--accent-red)'}"></div>
          </div>
          <div class="tot-value low ${hWins ? 'dim' : ''}">${_formatTotValue(r.metric, r.low)}${_suffixForMetric(r.metric)}</div>
        </div>
      </div>
    `;
  }).join('');

  const edgesHtml = (tot.edges || []).map(e => {
    let dotColor = 'var(--text-muted)';
    if (e.favor === 'high') dotColor = colorH || 'var(--accent-blue)';
    if (e.favor === 'low') dotColor = colorL || 'var(--accent-red)';
    return `
      <div class="tot-edge">
        <span class="tot-edge-dot" style="background:${dotColor}"></span>
        <span>${e.text}</span>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    <div class="stat-card">
      <h3>Tale of the Tape</h3>
      <div class="tot-rows">${rowsHtml}</div>
      ${edgesHtml ? `
        <div class="tot-edges">
          <div class="tot-edges-title">Edges</div>
          ${edgesHtml}
        </div>` : ''}
    </div>
  `;
}

// ── Momentum ─────────────────────────────────────────────────────────────

function renderMomentum(container, entry) {
  if (!container) return;
  const m = entry && entry.momentum;
  if (!m || !Array.isArray(m.checkpoints) || m.checkpoints.length < 2) {
    container.innerHTML = '';
    return;
  }
  if (typeof Plotly === 'undefined') {
    container.innerHTML = '<div class="stat-card"><h3>Series Momentum</h3><p>Plotly failed to load.</p></div>';
    return;
  }

  const high = entry.high_seed && entry.high_seed.team;
  const low = entry.low_seed && entry.low_seed.team;
  const colorH = teamColor(high) || '#60a5fa';
  const colorL = teamColor(low) || '#f87171';

  container.innerHTML = `
    <div class="stat-card">
      <h3>Series Momentum</h3>
      <div id="momentum-chart" style="width:100%;height:280px"></div>
      ${_renderMomentumCallout(m.biggest_swing)}
    </div>
  `;

  const labels = m.checkpoints.map(c => c.label);
  const highVals = m.checkpoints.map(c => c.high_wp);
  const lowVals = m.checkpoints.map(c => c.low_wp);

  const traces = [
    {
      x: labels, y: highVals, mode: 'lines+markers',
      name: high || 'Higher seed',
      line: { color: colorH, width: 3 },
      marker: { size: 8, color: colorH },
    },
    {
      x: labels, y: lowVals, mode: 'lines+markers',
      name: low || 'Lower seed',
      line: { color: colorL, width: 3 },
      marker: { size: 8, color: colorL },
    },
  ];

  const layout = {
    margin: { l: 40, r: 16, t: 8, b: 36 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {
      family: 'Inter, sans-serif',
      color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary') || '#cbd5e1',
      size: 12,
    },
    xaxis: { gridcolor: 'rgba(255,255,255,0.06)', tickfont: { size: 11 } },
    yaxis: {
      title: { text: 'Series WP %', font: { size: 11 } },
      range: [0, 100], gridcolor: 'rgba(255,255,255,0.06)',
      ticksuffix: '%',
    },
    showlegend: true,
    legend: { orientation: 'h', y: -0.2, x: 0.5, xanchor: 'center' },
    hovermode: 'x unified',
  };

  Plotly.newPlot('momentum-chart', traces, layout, {
    displayModeBar: false, responsive: true,
  });
}

function _renderMomentumCallout(swing) {
  if (!swing) return '';
  const winner = swing.winner_team || (swing.shifted_to === 'high' ? 'higher seed' : 'lower seed');
  return `
    <div class="momentum-callout">
      <strong>Biggest swing:</strong>
      G${swing.game_num} — ${winner} win shifted series WP +${swing.delta_pct}%
    </div>
  `;
}

// ── Simulate From Here ─────────────────────────────────────────────────────
// Port of seriesOutcomeProbs() from playoffs.js, self-contained in series.js.
// Computes the probability of every possible final score from the current
// series state (winsHigh, winsLow) using the matchup probs from dashboard.json.

function computeOutcomeProbs(entry, matchupProbs) {
  const high = entry.high_seed && entry.high_seed.team;
  const low  = entry.low_seed  && entry.low_seed.team;
  if (!high || !low) return null;

  const fmt        = entry.format || 'best_of_5';
  const targetWins = fmt === 'single_game' ? 1 : 3;
  const pattern    = entry.home_pattern || ['high', 'high', 'low', 'low', 'high'];
  const wH = (entry.wins && entry.wins.high) || 0;
  const wL = (entry.wins && entry.wins.low)  || 0;

  const pair = ((matchupProbs || {})[high] || {})[low] || {};
  const getP = slot => {
    if (slot === 'high')    return pair.home    != null ? pair.home    : 0.5;
    if (slot === 'low')     return pair.away    != null ? pair.away    : 0.5;
    /* neutral */           return pair.neutral != null ? pair.neutral : 0.5;
  };

  const gamesPlayed = wH + wL;
  const remaining   = pattern.slice(gamesPlayed);
  const outcomes    = {};
  let   states      = new Map([[`${wH},${wL}`, 1.0]]);

  for (const slot of remaining) {
    const p    = getP(slot);
    const next = new Map();
    for (const [key, prob] of states) {
      const [a, b] = key.split(',').map(Number);

      const a1 = a + 1;
      if (a1 >= targetWins) {
        const k = `${a1}-${b}`;
        outcomes[k] = (outcomes[k] || 0) + prob * p;
      } else {
        const k = `${a1},${b}`;
        next.set(k, (next.get(k) || 0) + prob * p);
      }

      const b1 = b + 1;
      if (b1 >= targetWins) {
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

function renderSimulate(container, entry, dashboard) {
  if (!container) return;

  // Only render for in-progress series (has games played, not yet complete)
  const status = entry.status;
  if (status !== 'in_progress') return;
  const wH = (entry.wins && entry.wins.high) || 0;
  const wL = (entry.wins && entry.wins.low)  || 0;
  if (wH === 0 && wL === 0) return; // technically in_progress but no games yet

  const high    = entry.high_seed && entry.high_seed.team;
  const low     = entry.low_seed  && entry.low_seed.team;
  const colorH  = teamColor(high);
  const colorL  = teamColor(low);
  const nameH   = teamName(high);
  const nameL   = teamName(low);
  const matchupProbs = (dashboard && dashboard.playoff_matchup_probs) || {};
  const outcomes = computeOutcomeProbs(entry, matchupProbs);
  if (!outcomes || Object.keys(outcomes).length === 0) return;

  const targetWins = entry.format === 'single_game' ? 1 : 3;

  // Sort outcomes: high-seed wins first (desc prob), then low-seed wins (desc prob)
  const highWins = Object.entries(outcomes)
    .filter(([k]) => Number(k.split('-')[0]) >= targetWins)
    .sort((a, b) => b[1] - a[1]);
  const lowWins = Object.entries(outcomes)
    .filter(([k]) => Number(k.split('-')[1]) >= targetWins)
    .sort((a, b) => b[1] - a[1]);
  const sorted = [...highWins, ...lowWins];

  const maxProb = Math.max(...sorted.map(([, p]) => p), 1e-9);
  const probHighTotal = highWins.reduce((s, [, p]) => s + p, 0);

  const bars = sorted.map(([key, prob]) => {
    const [wA, wB] = key.split('-').map(Number);
    const isHighWin = wA >= targetWins;
    const color = isHighWin ? colorH : colorL;
    const winner = isHighWin ? nameH : nameL;
    const pct = (prob * 100).toFixed(1);
    const barW = (prob / maxProb * 100).toFixed(1);
    const label = isHighWin ? `${nameH} ${wA}–${wB}` : `${nameL} ${wB}–${wA}`;
    return `
      <div class="sim-bar-row">
        <div class="sim-bar-label">${label}</div>
        <div class="sim-bar-track">
          <div class="sim-bar-fill" style="width:${barW}%;background:${color}"></div>
        </div>
        <div class="sim-bar-pct">${pct}%</div>
      </div>`;
  }).join('');

  const currentScore = `${nameH} leads ${wH}–${wL}`;
  const highPctStr   = (probHighTotal * 100).toFixed(1);
  const lowPctStr    = ((1 - probHighTotal) * 100).toFixed(1);

  container.innerHTML = `
    <div class="stat-card sim-card">
      <div class="sim-header">
        <h3>🎲 Simulate From Here</h3>
        <span class="sim-subhead">From ${currentScore} · Projected outcomes</span>
      </div>
      <div class="sim-summary">
        <span style="color:${colorH}">${nameH}</span> wins series:
        <strong style="color:${colorH}">${highPctStr}%</strong>
        &nbsp;·&nbsp;
        <span style="color:${colorL}">${nameL}</span> wins series:
        <strong style="color:${colorL}">${lowPctStr}%</strong>
      </div>
      <div class="sim-bars">${bars}</div>
      <div class="sim-note">Probabilities computed from pre-series matchup model, resuming from current score.</div>
    </div>
  `;
}

main();
