/* Pure helpers for the Pace page and the Team page pace panel, over the
   league and teams arrays of data/current/pace.json. Defines one browser
   global, PaceCore; in Node it is exported via module.exports. */

(function () {
  'use strict';

  function latestSeason(teams) {
    let best = null;
    for (const r of teams || []) if (best === null || r.season > best) best = r.season;
    return best;
  }

  // Trailing run of consecutive season-on-season pace increases.
  function paceStreak(league) {
    const rows = [...(league || [])].sort((a, b) => a.season - b.season);
    if (!rows.length) return { streak: 0, base: null, latest: null };
    let streak = 0;
    for (let i = rows.length - 1; i > 0 && rows[i].pace > rows[i - 1].pace; i--) streak++;
    return { streak, base: rows[rows.length - 1 - streak], latest: rows[rows.length - 1] };
  }

  function seasonTeams(teams, season, metric) {
    const prevByTeam = new Map();
    for (const r of teams || []) if (r.season === season - 1) prevByTeam.set(r.team, r[metric]);
    return (teams || [])
      .filter(r => r.season === season)
      .map(r => Object.assign({}, r, { prev: prevByTeam.has(r.team) ? prevByTeam.get(r.team) : null }))
      .sort((a, b) => b[metric] - a[metric]);
  }

  function teamHistory(teams, league, team) {
    const leagueBySeason = new Map((league || []).map(r => [r.season, r.pace]));
    return (teams || [])
      .filter(r => r.team === team)
      .sort((a, b) => a.season - b.season)
      .map(r => ({ season: r.season, pace: r.pace, league: leagueBySeason.has(r.season) ? leagueBySeason.get(r.season) : null }));
  }

  const api = { latestSeason, paceStreak, seasonTeams, teamHistory };
  if (typeof window !== 'undefined') window.PaceCore = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})();
