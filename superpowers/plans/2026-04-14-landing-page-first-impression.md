# Landing Page First-Impression Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hero intro, credibility stat cards, and feature highlights to the landing page so first-time visitors immediately understand and are impressed by the platform.

**Architecture:** Pure HTML/CSS changes to two files. Hero intro + stat cards go inside the existing `<header>`. Feature highlights section is a new `<section>` between `</main>` and `<footer>`. Footer stats line is simplified. No JS changes.

**Tech Stack:** HTML, CSS (existing vanilla stack, no build step)

**Spec:** `docs/superpowers/specs/2026-04-14-landing-page-first-impression-design.md`

---

### Task 1: Add hero intro and stat cards CSS to style.css

**Files:**
- Modify: `docs/style.css:57-60` (after `.subtitle` rule)
- Modify: `docs/style.css:1377` (inside `@media (max-width: 480px)` block)

- [ ] **Step 1: Add hero intro and stat card styles after the `.subtitle` rule (line 60)**

Insert after the `.subtitle` block (after line 60, before the `/* ── Controls */` comment):

```css
.hero-intro {
    color: var(--text-secondary);
    font-size: 0.95rem;
    line-height: 1.6;
    max-width: 600px;
    margin: 0.75rem auto 0;
}

.hero-stats {
    display: flex;
    gap: 1rem;
    justify-content: center;
    margin-top: 1.25rem;
}

.hero-stat {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.875rem 1.5rem;
    text-align: center;
}

.hero-stat-number {
    font-family: 'Outfit', sans-serif;
    font-size: 1.75rem;
    font-weight: 800;
    background: linear-gradient(135deg, #a855f7, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.hero-stat-label {
    color: var(--text-secondary);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
```

- [ ] **Step 2: Add mobile responsive rules for hero styles**

Inside the existing `@media (max-width: 480px)` block (line 1377), add at the end (before the closing `}`):

```css
    .hero-intro {
        font-size: 0.85rem;
    }

    .hero-stats {
        gap: 0.6rem;
    }

    .hero-stat {
        padding: 0.6rem 0.8rem;
    }

    .hero-stat-number {
        font-size: 1.3rem;
    }
```

- [ ] **Step 3: Verify CSS syntax**

Run: `cd /c/Users/klalo/PycharmProjects/pythonProject && python -c "print(open('docs/style.css').read().count('{'), open('docs/style.css').read().count('}'))"`

Expected: Both counts should be equal (balanced braces).

- [ ] **Step 4: Commit**

```bash
git add docs/style.css
git commit -m "style: add hero intro and stat card CSS for landing page"
```

---

### Task 2: Add hero intro and stat cards HTML to index.html

**Files:**
- Modify: `docs/index.html:43-47` (header section)

- [ ] **Step 1: Insert hero intro paragraph and stat cards into header**

In `docs/index.html`, between the `.subtitle` line (line 45) and the `#last-updated` line (line 46), insert:

```html
        <p class="hero-intro">
            An independent analytics platform covering 19 seasons of Euroleague basketball
            — advanced ratings, win probability models, and game-level insights, built from
            scratch with Python and vanilla JS.
        </p>
        <div class="hero-stats">
            <div class="hero-stat">
                <div class="hero-stat-number">19</div>
                <div class="hero-stat-label">Seasons</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-number">7,000+</div>
                <div class="hero-stat-label">Games</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-number">2M+</div>
                <div class="hero-stat-label">Play-by-Play Events</div>
            </div>
        </div>
```

The header should now read: `h1` → `.subtitle` → `.hero-intro` → `.hero-stats` → `#last-updated`.

- [ ] **Step 2: Verify HTML structure**

Run: `cd /c/Users/klalo/PycharmProjects/pythonProject && python -c "from html.parser import HTMLParser; HTMLParser().feed(open('docs/index.html').read()); print('HTML parsed OK')"`

Expected: `HTML parsed OK` (no errors).

- [ ] **Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add hero intro paragraph and credibility stat cards"
```

---

### Task 3: Add feature highlights CSS to style.css

**Files:**
- Modify: `docs/style.css` (after `.site-footer` block, before the end of file — or between the footer rules and end of file)

- [ ] **Step 1: Add explore section styles after the `.footer-sep` rule (after line 1458)**

Append after the `.footer-sep` rule at the end of `docs/style.css`:

```css

/* ── Explore Section ──────────────────────────────────────── */
.explore-section {
    max-width: 700px;
    margin: 0 auto;
    padding: 2rem 1rem;
    border-top: 1px solid var(--border);
    text-align: center;
}

.explore-section h2 {
    font-family: 'Outfit', sans-serif;
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 0.25rem;
}

.explore-subtitle {
    color: var(--text-muted);
    font-size: 0.85rem;
    margin-bottom: 1.25rem;
}

.explore-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
}

.explore-grid-bottom {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
    max-width: 66.666%;
    margin: 0.75rem auto 0;
}

.explore-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 0.75rem;
    text-align: center;
    cursor: pointer;
    text-decoration: none;
    color: inherit;
    transition: border-color var(--transition);
    display: block;
}

.explore-card:hover {
    border-color: var(--accent-purple);
}

.explore-card-emoji {
    font-size: 1.5rem;
    margin-bottom: 0.3rem;
}

.explore-card-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.2rem;
}

.explore-card-desc {
    font-size: 0.75rem;
    color: var(--text-muted);
    line-height: 1.3;
}

@media (max-width: 480px) {
    .explore-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .explore-grid-bottom {
        grid-template-columns: 1fr;
        max-width: 50%;
    }
}
```

- [ ] **Step 2: Verify CSS syntax**

Run: `cd /c/Users/klalo/PycharmProjects/pythonProject && python -c "print(open('docs/style.css').read().count('{'), open('docs/style.css').read().count('}'))"`

Expected: Both counts should be equal (balanced braces).

- [ ] **Step 3: Commit**

```bash
git add docs/style.css
git commit -m "style: add explore section CSS for feature highlights grid"
```

---

### Task 4: Add feature highlights HTML and simplify footer in index.html

**Files:**
- Modify: `docs/index.html:154-165` (between `</main>` and `<footer>`)

- [ ] **Step 1: Insert explore section between `</main>` (line 154) and `<footer>` (line 156)**

Insert after the `</main>` closing tag (line 154), before the `<footer>`:

```html

    <section class="explore-section">
        <h2>Explore the Platform</h2>
        <p class="explore-subtitle">13 interactive dashboards covering every angle of Euroleague basketball</p>
        <div class="explore-grid">
            <a href="shots.html" class="explore-card">
                <div class="explore-card-emoji">🎯</div>
                <div class="explore-card-title">Shot Lab</div>
                <div class="explore-card-desc">Shot charts & hot zones for every team</div>
            </a>
            <a href="replay.html" class="explore-card">
                <div class="explore-card-emoji">📈</div>
                <div class="explore-card-title">Game Replay</div>
                <div class="explore-card-desc">Win probability curves for every game</div>
            </a>
            <a href="mvp.html" class="explore-card">
                <div class="explore-card-emoji">🏅</div>
                <div class="explore-card-title">MVP Race</div>
                <div class="explore-card-desc">Composite rankings & predictions</div>
            </a>
        </div>
        <div class="explore-grid-bottom">
            <a href="network.html" class="explore-card">
                <div class="explore-card-emoji">🕸️</div>
                <div class="explore-card-title">Playmaking</div>
                <div class="explore-card-desc">Assist network visualizations</div>
            </a>
            <a href="game-control.html" class="explore-card">
                <div class="explore-card-emoji">🎮</div>
                <div class="explore-card-title">Game Control</div>
                <div class="explore-card-desc">Dominance, drama & comeback metrics</div>
            </a>
        </div>
    </section>
```

- [ ] **Step 2: Simplify the footer stats line**

In `docs/index.html`, replace:

```html
        <div>19 seasons · 7,000+ games · Updated daily</div>
```

with:

```html
        <div>Updated daily</div>
```

- [ ] **Step 3: Verify HTML structure**

Run: `cd /c/Users/klalo/PycharmProjects/pythonProject && python -c "from html.parser import HTMLParser; HTMLParser().feed(open('docs/index.html').read()); print('HTML parsed OK')"`

Expected: `HTML parsed OK` (no errors).

- [ ] **Step 4: Commit**

```bash
git add docs/index.html
git commit -m "feat: add feature highlights section and simplify footer"
```

---

### Task 5: Visual verification in browser

**Files:** None (read-only verification)

- [ ] **Step 1: Start a local dev server**

Run: `cd /c/Users/klalo/PycharmProjects/pythonProject/docs && python -m http.server 8000`

Open `http://localhost:8000` in a browser.

- [ ] **Step 2: Verify hero area**

Check that:
- The intro paragraph appears below the subtitle, centered, in secondary text color
- Three stat cards appear below the intro with gradient purple-to-blue numbers
- The tab bar and standings table are still visible without excessive scrolling
- `#last-updated` still displays correctly when data loads

- [ ] **Step 3: Verify feature highlights at bottom**

Scroll to the bottom and check that:
- "Explore the Platform" heading and subtitle appear above the footer
- 5 cards in a 3+2 grid layout with emoji, title, and description
- Each card links to the correct page
- Cards show purple border on hover

- [ ] **Step 4: Verify footer**

Check that footer shows "Updated daily" (not the old "19 seasons · 7,000+ games · Updated daily").

- [ ] **Step 5: Test mobile responsive**

Resize browser to ~400px width and verify:
- Stat cards shrink but stay in a row
- Feature grid collapses to 2-column layout
- No horizontal overflow or layout breakage

- [ ] **Step 6: Kill the dev server and commit (if any fixes were needed)**

Stop the server (Ctrl+C). If fixes were applied during verification, commit them:

```bash
git add docs/index.html docs/style.css
git commit -m "fix: adjust landing page layout from visual verification"
```
