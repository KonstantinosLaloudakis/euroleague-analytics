# Landing Page First-Impression Improvements

**Date:** 2026-04-14
**Goal:** Make the landing page immediately understandable and impressive to first-time visitors (especially LinkedIn traffic) without degrading the experience for returning users.

## Context

The project gained traction via a LinkedIn post (~1000 impressions, 40 engagements). New visitors land on index.html and see a standings table with no context about what the platform is, who built it, or why it's impressive. The credibility stats ("19 seasons · 7,000+ games") are buried in the footer.

## Changes

### 1. Hero intro paragraph

**Location:** Between the existing `.subtitle` and the new stat cards, inside the `<header>` element.

**Content:**
> An independent analytics platform covering 19 seasons of Euroleague basketball — advanced ratings, win probability models, and game-level insights, built from scratch with Python and vanilla JS.

**Styling:**
- `color: var(--text-secondary)` (#9ca3af)
- `font-size: 0.95rem`, `line-height: 1.6`
- `max-width: 600px`, `margin: 0 auto`
- Class: `.hero-intro`

### 2. Credibility stat cards

**Location:** Below the intro paragraph, still inside `<header>`, above the `#last-updated` line.

**Structure:** Three cards in a horizontal flex row, centered.

| Number | Label |
|--------|-------|
| 19 | Seasons |
| 7,000+ | Games |
| 2M+ | Play-by-Play Events |

**Styling:**
- Container: `.hero-stats` — `display: flex; gap: 1rem; justify-content: center; margin-top: 1.25rem`
- Each card: `.hero-stat` — `background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.875rem 1.5rem; text-align: center`
- Number: `.hero-stat-number` — Outfit font, `font-size: 1.75rem`, `font-weight: 800`, same gradient as h1 (purple→blue)
- Label: `.hero-stat-label` — `color: var(--text-secondary); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em`

**Mobile (max-width 600px):** Cards shrink padding, number font-size reduces to 1.3rem. Flex row stays (cards are narrow enough).

**Footer change:** Remove "19 seasons · 7,000+ games · Updated daily" from footer. Replace with just "Updated daily".

### 3. Feature highlights grid

**Location:** Between `</main>` closing tag and the `<footer>` element. Not inside `<main>` — it's a standalone section.

**Structure:**
```html
<section class="explore-section">
  <h2>Explore the Platform</h2>
  <p class="explore-subtitle">13 interactive dashboards covering every angle of Euroleague basketball</p>
  <div class="explore-grid">
    <!-- 5 cards, 3 in first row, 2 in second row centered -->
  </div>
</section>
```

**Cards (each links to its page):**

| Emoji | Title | Description | Link |
|-------|-------|-------------|------|
| 🎯 | Shot Lab | Shot charts & hot zones for every team | shots.html |
| 📈 | Game Replay | Win probability curves for every game | replay.html |
| 🏅 | MVP Race | Composite rankings & predictions | mvp.html |
| 🕸️ | Playmaking | Assist network visualizations | network.html |
| 🎮 | Game Control | Dominance, drama & comeback metrics | game-control.html |

**Styling:**
- `.explore-section` — `max-width: 700px; margin: 0 auto; padding: 2rem 1rem; border-top: 1px solid var(--border)`
- `.explore-grid` — `display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem` for first 3, then a second row with `repeat(2, 1fr)` centered via max-width
- Each `.explore-card` — Same visual treatment as `.stat-card` but smaller: `background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem 0.75rem; text-align: center; cursor: pointer; text-decoration: none; color: inherit; transition: border-color var(--transition)`
- Hover: `border-color: var(--accent-purple)`
- Emoji: `font-size: 1.5rem`
- Title: `font-size: 0.85rem; font-weight: 600; color: var(--text-primary)`
- Description: `font-size: 0.75rem; color: var(--text-muted); line-height: 1.3`

**Mobile (max-width 600px):** Grid collapses to `repeat(2, 1fr)` with the 5th card spanning full width, or single column.

## Files modified

- `docs/index.html` — Add hero intro, stat cards, feature highlights section; simplify footer
- `docs/style.css` — Add `.hero-intro`, `.hero-stats`, `.hero-stat`, `.hero-stat-number`, `.hero-stat-label`, `.explore-section`, `.explore-grid`, `.explore-card` styles and responsive rules

## What stays unchanged

- Nav bar, tab bar, all existing main content (standings table, power scatter, MVP chart, schedule difficulty, standings race, oracle forecast)
- All other pages (team.html, players.html, etc.)
- season.js, constants.js — no JS changes needed
