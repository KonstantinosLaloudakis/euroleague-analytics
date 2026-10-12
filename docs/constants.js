/**
 * constants.js — Shared constants and utilities for Euroleague Analytics
 * Single source of truth: include via <script src="constants.js"> before page JS.
 */
'use strict';

// ── Team lookup tables ───────────────────────────────────────────────────
const TEAM_COLORS = {
    // Current season
    IST:'#E30613', BAS:'#B50031',
    RED:'#CC0000', MIL:'#C8102E', BAR:'#004D98', MUN:'#0066B2',
    ULK:'#003366', ASV:'#222222', TEL:'#F6C300', OLY:'#E2001A',
    PAN:'#007F3D', PAR:'#333333', PRS:'#1a1a2e', MAD:'#6d4c94',
    PAM:'#EB7622', VIR:'#1a1a1a', ZAL:'#006233', DUB:'#555555',
    HTA:'#cc0000', BES:'#d9d9d9',
    // Historical
    BER:'#005CA9', MCO:'#D4AF37',
    BAM:'#8B0000', CED:'#F47B20', CIB:'#003DA5', CSK:'#CC0000',
    DAR:'#00843D', DYR:'#0047AB', GAL:'#FF6600', KHI:'#FFCC00',
    LIE:'#1A5C2A', LJU:'#00843D', MAL:'#007848', ROM:'#FFD700',
    SIE:'#003399', SOP:'#004F9E', UNK:'#00573F',
};

const TEAM_NAMES = {
    // Current season
    IST:'Anadolu Efes', BAS:'Baskonia',
    RED:'Crvena Zvezda', MIL:'EA7 Milan', BAR:'FC Barcelona', MUN:'Bayern Munich',
    ULK:'Fenerbahce', ASV:'ASVEL', TEL:'Maccabi Tel Aviv', OLY:'Olympiacos',
    PAN:'Panathinaikos', PAR:'Partizan', PRS:'Paris Basketball', MAD:'Real Madrid',
    PAM:'Valencia Basket', VIR:'Virtus Bologna', ZAL:'Zalgiris', DUB:'Dubai Basketball',
    HTA:'Hapoel Tel Aviv', BES:'Besiktas Istanbul',
    // Historical
    BER:'ALBA Berlin', MCO:'AS Monaco',
    BAM:'Brose Bamberg', CED:'Cedevita Zagreb', CIB:'Cibona Zagreb', CSK:'CSKA Moscow',
    DAR:'Darussafaka', DYR:'Zenit St Petersburg', GAL:'Galatasaray', KHI:'Khimki',
    LIE:'Lietuvos Rytas', LJU:'Olimpija Ljubljana', MAL:'Unicaja Malaga', ROM:'Virtus Roma',
    SIE:'Montepaschi Siena', SOP:'Asseco Prokom', UNK:'UNICS Kazan',
};

// ── Team home-arena timezones (IANA) ────────────────────────────────────
// Used to convert Schedule API tip-off times (CET/CEST) into arena-local
// time on the Series Hub. HTA is mapped to Europe/Sofia for the 2025
// season because their home games are being played in Botevgrad, Bulgaria.
const TEAM_TIMEZONES = {
    BER:'Europe/Berlin', IST:'Europe/Istanbul', MCO:'Europe/Monaco', BAS:'Europe/Madrid',
    RED:'Europe/Belgrade', MIL:'Europe/Rome', BAR:'Europe/Madrid', MUN:'Europe/Berlin',
    ULK:'Europe/Istanbul', ASV:'Europe/Paris', TEL:'Asia/Jerusalem', OLY:'Europe/Athens',
    PAN:'Europe/Athens', PAR:'Europe/Belgrade', PRS:'Europe/Paris', MAD:'Europe/Madrid',
    PAM:'Europe/Madrid', VIR:'Europe/Rome', ZAL:'Europe/Vilnius', DUB:'Asia/Dubai',
    HTA:'Europe/Sofia',
};

// ── Shared tab switching ─────────────────────────────────────────────────
/**
 * switchTab(tabId, tabIds, opts)
 *   tabId  — id of the tab panel to show
 *   tabIds — ordered array of all tab panel ids in this group
 *   opts.scope    — CSS selector to scope .tab-btn search (default: document)
 *   opts.hash     — persist tabId in URL hash (default: true)
 *   opts.onSwitch — callback(tabId) after switching
 */
function switchTab(tabId, tabIds, opts = {}) {
    tabIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.toggle('hidden', id !== tabId);
            el.setAttribute('role', 'tabpanel');
        }
    });
    const scope = opts.scope ? document.querySelector(opts.scope) : document;
    const buttons = scope ? scope.querySelectorAll('.tab-btn') : [];
    const idx = tabIds.indexOf(tabId);
    buttons.forEach((btn, i) => {
        const isActive = i === idx;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-selected', isActive);
        btn.setAttribute('tabindex', isActive ? '0' : '-1');
    });
    if (opts.hash !== false) {
        history.replaceState(null, '', '#' + tabId);
    }
    if (opts.onSwitch) opts.onSwitch(tabId);
}

// ── Keyboard navigation for tab bars ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tab-bar, #paint-tabs').forEach(bar => {
        bar.setAttribute('role', 'tablist');
        bar.addEventListener('keydown', e => {
            const tabs = [...bar.querySelectorAll('.tab-btn')];
            const idx = tabs.indexOf(e.target);
            if (idx === -1) return;
            let next = -1;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % tabs.length;
            else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + tabs.length) % tabs.length;
            if (next !== -1) {
                e.preventDefault();
                tabs[next].focus();
                tabs[next].click();
            }
        });
    });
});

// ── Shared Plotly theme ──────────────────────────────────────────────────
const PLOTLY_THEME = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Inter, sans-serif', color: '#9ca3af', size: 12 },
    margin: { t: 30, r: 20, b: 40, l: 50 },
    xaxis: { gridcolor: '#2d2e3a', zerolinecolor: '#2d2e3a', color: '#9ca3af' },
    yaxis: { gridcolor: '#2d2e3a', zerolinecolor: '#2d2e3a', color: '#9ca3af' },
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

// ── Team color helper ──────────────────────────────────────────────────
function getTeamColor(code) { return TEAM_COLORS[code] || '#6b7280'; }

// ── Readable team colours on the dark theme ────────────────────────────
// teamInk: brand colour lifted toward white just enough for 4.5:1 contrast
// on --bg-card (the lightest dark surface). Use for text, lines, markers.
// teamOnColor: text colour for a solid team-colour background (badges).
const INK_BG = '#1f2029';
function _rgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function _luminance(hex) {
    const [r, g, b] = _rgb(hex).map(v => {
        v /= 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrastRatio(a, b) {
    const [hi, lo] = [_luminance(a), _luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
}
function _towardWhite(hex, t) {
    return '#' + _rgb(hex)
        .map(v => Math.round(v + (255 - v) * t).toString(16).padStart(2, '0'))
        .join('');
}
const _inkCache = {};
function teamInk(code) {
    if (_inkCache[code]) return _inkCache[code];
    const base = getTeamColor(code).toLowerCase();
    let ink = base;
    for (let t = 0.05; contrastRatio(ink, INK_BG) < 4.5 && t <= 1.0001; t += 0.05) {
        ink = _towardWhite(base, Math.min(t, 1));
    }
    return (_inkCache[code] = ink);
}
function teamOnColor(code) {
    const bg = getTeamColor(code);
    return contrastRatio('#ffffff', bg) >= contrastRatio('#111111', bg) ? '#ffffff' : '#111111';
}

// ── Safe fetch with resp.ok check ───────────────────────────────────────
function fetchJSON(url) {
    return fetch(url).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status} loading ${url}`);
        return r.json();
    });
}

// ── Season helpers ──────────────────────────────────────────────────────
// Season of a dashboard.json payload (pre-2026 dashboards had no field → 2025).
function dashboardSeason(dash) { return (dash && dash.season) || 2025; }
function seasonLabel(s) { return `${s}-${String(s + 1).slice(-2)}`; }
function isEmptyData(v) {
    if (v == null) return true;
    if (Array.isArray(v)) return v.length === 0;
    if (typeof v === 'object') return Object.keys(v).length === 0;
    return false;
}
// Playoffs have started once any series has games played. Pre-playoff
// projections export every slot as 'awaiting_teams' or 'not_started'.
function playoffsStarted(dash) {
    return Object.values((dash && dash.series) || {}).some(
        s => s && s.status !== 'awaiting_teams' && s.status !== 'not_started');
}
// Playoff-only pages show last season's final playoffs until the new ones start.
async function loadPlayoffDashboard() {
    const cur = await fetchJSON('data/current/dashboard.json');
    if (playoffsStarted(cur)) return { dash: cur, archived: false };
    const prev = dashboardSeason(cur) - 1;
    try {
        const old = await fetchJSON(`data/archive/${prev}/dashboard.json`);
        return { dash: old, archived: true, archivedSeason: prev, currentSeason: dashboardSeason(cur) };
    } catch (e) {
        return { dash: cur, archived: false };
    }
}
function seasonBannerHTML(r) {
    if (!r.archived) return '';
    return `<div class="season-banner">Showing the ${seasonLabel(r.archivedSeason)} playoffs (final). The ${seasonLabel(r.currentSeason)} playoffs start in April.</div>`;
}

// MVP scores need MVP_MIN_GP games (calculate_mvp_scores.py); before that
// the MVP list is empty and pages show this message instead.
const MVP_MIN_GP = 5;
function mvpPendingHTML(round) {
    if (round >= MVP_MIN_GP) {
        return `<p class="empty-state" style="color:var(--text-muted);text-align:center;padding:2rem 1rem">` +
            `MVP rankings are temporarily unavailable — check back after the next update.</p>`;
    }
    const now = round ? ` We're at Round ${round}.` : '';
    return `<p class="empty-state" style="color:var(--text-muted);text-align:center;padding:2rem 1rem">` +
        `The MVP race opens once players have ${MVP_MIN_GP} games — after Round ${MVP_MIN_GP}.${now}</p>`;
}
// The export lists players with at least min(5, round) games; the
// leaderboard's default filter uses the same threshold.
function defaultMinGP(round) {
    return Math.min(5, Math.max(1, round || 0));
}
