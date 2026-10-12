# Responsive Nav + Layout Overflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every nav link is reachable at every screen width, and no page scrolls sideways; the standings cutoff labels are always visible.

**Architecture:** CSS-first. Below 1366px the `.site-nav` links collapse behind a "☰ Menu" button (inline `onclick` toggles a `nav-open` class, so no shared script is needed — three pages don't load constants.js). The menu panel lists every link including the "More" ones. Desktop ≥1366px is unchanged. Separate small CSS fixes for the Playmaking grid, the standings cutoff labels, the H2H team selector and the Shot Lab zone table.

**Tech Stack:** HTML, CSS (`docs/style.css` + page `<style>` blocks), Playwright for verification.

**Spec:** Site audit 2026-10-12 finding #9 (clipped cutoff labels, nav running off-screen at ~1000px, Playmaking page scrolls sideways). Investigation: `.site-nav` uses `overflow-x: clip`, so links past the edge are unreachable at every width < ~1366px (nav content is 1165–1334px wide); page-level overflow at 375px on h2h.html (team selector row), shots.html (zone table, +11px), network.html (league tables), and at 1024px on network.html; the cutoff labels are right-aligned to the far end of a horizontally scrolling standings table. User chose: "Menu button" for the nav.

## Global Constraints

- Branch `fix/responsive-nav`.
- Breakpoint: menu button for `max-width: 1365px`; ≥1366px the nav looks and works exactly as today (including the hover "More ▾" dropdown).
- Same nav on all 19 pages; keep each page's existing link list and `active` class.
- No new JS files; the toggle is an inline `onclick` on the button.
- Keep line endings; dark theme tokens from style.css (`--bg-secondary`, `--border`, `--text-*`).
- Accessible: the button is a `<button type="button">` with `aria-expanded` and `aria-controls`, visible focus style (existing `.nav-link:focus-visible` pattern).

## Review Focus

1. At 1366px+ nothing changes (no button visible; More dropdown on hover/focus still works).
2. With the menu open on a phone, every link (including Playmaking, Replay, Records, Game Control, GCI History, Title Race, Lineups, About) is visible and tappable, and the panel scrolls if taller than the screen.
3. Sticky nav stays one row tall when the menu is closed.
4. No page has `documentElement.scrollWidth > clientWidth` at 375 / 768 / 1024 / 1280 / 1366 / 1440.
5. Cutoff labels ("Top 4 cutoff", "Playoff cutoff (Top 6)", "Play-in cutoff (Top 10)") are fully visible at 1024px and 375px.

---

### Task 1: Nav menu button (style.css + 19 pages)

**Files:** `docs/style.css` (nav section ~lines 636–720 and the responsive section), and every `docs/*.html` containing `class="site-nav"` (19 files).

- [ ] **Step 1: Branch** — `git checkout -b fix/responsive-nav`

- [ ] **Step 2: Markup** — in each of the 19 pages, give the `<nav class="site-nav">` an `id="site-nav"` and insert directly after the `<span class="site-nav-brand">…</span>` line (same indentation as that line):

```html
<button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav" onclick="const n=this.parentElement;const o=n.classList.toggle('nav-open');this.setAttribute('aria-expanded',o)">☰ Menu</button>
```

Do it with a script that edits all files in one pass and prints the count of files changed (expect 19); verify with `grep -c 'class="nav-toggle"' docs/*.html | grep -v ':0' | wc -l` → 19 and `grep -c 'id="site-nav"'` likewise.

- [ ] **Step 3: CSS** — in `docs/style.css`, after the `.nav-more-dropdown .nav-link { … }` rule, add:

```css
/* ── Compact nav: menu button below 1366px ──────────────── */
.nav-toggle {
    display: none;
    margin-left: auto;
    background: var(--bg-card);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.35rem 0.8rem;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 600;
    line-height: 1.2;
    cursor: pointer;
}
.nav-toggle:focus-visible { outline: 2px solid var(--accent-purple); outline-offset: 2px; }

@media (max-width: 1365px) {
    .site-nav { flex-wrap: wrap; overflow: visible; }
    .nav-toggle { display: inline-flex; align-items: center; gap: 0.35rem; }
    .site-nav-brand { margin-right: 0; }
    .site-nav > .nav-link,
    .site-nav > .nav-more { display: none; }
    .site-nav.nav-open {
        max-height: 100vh;
        overflow-y: auto;
    }
    .site-nav.nav-open > .nav-link,
    .site-nav.nav-open > .nav-more {
        display: block;
        width: 100%;
    }
    .site-nav.nav-open > .nav-link { padding: 0.55rem 0.8rem; }
    .site-nav.nav-open .nav-more-btn { display: none; }
    .site-nav.nav-open .nav-more-dropdown {
        display: flex;
        position: static;
        min-width: 0;
        padding: 0;
        border: none;
        box-shadow: none;
        background: transparent;
    }
    .site-nav.nav-open .nav-more-dropdown .nav-link { padding: 0.55rem 0.8rem; }
}
```

Then check the existing `@media (max-width: 480px)` / `768px` nav rules don't fight these (they only change padding/font sizes — keep them). Keep `overflow-x: clip` on the base `.site-nav` rule (desktop) unchanged.

- [ ] **Step 4: Commit** — `git add docs/style.css docs/*.html && git commit -m "fix: menu button nav below 1366px so every page link is reachable"`

---

### Task 2: Page overflow fixes

**Files:** `docs/network.html` (`<style>` block ~line 192), `docs/style.css` (`.cutoff-label` ~line 941), `docs/h2h.html` (`<style>` ~lines 20–60), `docs/shots.html` (`<style>` ~line 69 and the zone-table markup/JS that renders `.zone-tbl`)

- [ ] **Step 1: Playmaking grid** — in `docs/network.html` after `.league-tables { … }` add `.league-tables > * { min-width: 0; }` (grid items otherwise refuse to shrink below their table's width, so `.league-table-wrap { overflow-x: auto; }` never kicks in).

- [ ] **Step 2: Cutoff labels** — in `docs/style.css` change `.cutoff-label` so it pins to the visible left edge of the scrolling table: replace `display: block; text-align: right;` with `display: inline-block; position: sticky; left: 0; text-align: left;` (keep the other declarations).

- [ ] **Step 3: H2H selector** — in `docs/h2h.html` add a `@media (max-width: 600px)` rule that stacks the selector: the container holding the two `.control-group`s and `.h2h-vs` (find its class, e.g. `.h2h-selector`) gets `flex-direction: column; align-items: stretch;`, `.h2h-vs` is centred (`align-self: center`), and `.control-group` / its `select` get `width: 100%; min-width: 0;`.

- [ ] **Step 4: Shot Lab zone table** — make the element that wraps `.zone-tbl` scroll horizontally when narrow: if a wrapper exists, give it `overflow-x: auto;`; if the table is rendered directly into a card, wrap it in `<div class="zone-tbl-wrap" style="overflow-x:auto">…</div>` where it's rendered (JS template in shots.js or the HTML). Don't change the table's columns.

- [ ] **Step 5: Commit** — `git add docs/network.html docs/style.css docs/h2h.html docs/shots.html docs/shots.js && git commit -m "fix: no sideways scroll on Playmaking, H2H, Shot Lab; cutoff labels always visible"` (only the files you changed).

---

### Task 3: Verify across widths

- [ ] **Step 1:** Serve `docs/` on 8765 (background). With Playwright, for widths 375, 768, 1024, 1280, 1366, 1440 and every `docs/*.html` page: assert `document.documentElement.scrollWidth <= clientWidth + 1`; with the menu closed assert `.site-nav` height ≤ 70px; at ≤1365px assert `.nav-toggle` is visible and the `.site-nav > .nav-link` elements are hidden; at ≥1366px assert `.nav-toggle` hidden and the nav not clipped (`nav.scrollWidth <= nav.clientWidth + 1`). Report any failures as page + width.
- [ ] **Step 2:** At 375px on index.html click "☰ Menu": every `a.nav-link` inside the nav is visible (non-zero box, inside the viewport after scrolling the panel), `aria-expanded="true"`; click it again → closed. At 1440px hover "More ▾" → dropdown appears.
- [ ] **Step 3:** At 1024px and 375px on index.html, each `.cutoff-label` is fully inside its scroll container's visible area (`getBoundingClientRect` within the container's rect).
- [ ] **Step 4:** Screenshots under `.playwright-mcp/`: index at 375 (menu closed + open), network at 1024, h2h at 375. No console errors besides Cloudflare analytics / favicon on localhost. Stop the server. `.venv/Scripts/python.exe -m pytest tests/ -q`.
