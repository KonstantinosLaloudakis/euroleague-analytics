import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
PAGES = sorted(DOCS.glob("*.html"))
PLACEHOLDER = re.compile(
    r'<nav class="site-nav" id="site-nav" aria-label="Main"></nav>\s*<script src="names.js"></script>\s*<script src="nav.js"></script>'
)


def test_every_page_uses_shared_nav():
    assert PAGES
    for p in PAGES:
        text = p.read_text(encoding="utf-8")
        assert len(PLACEHOLDER.findall(text)) == 1, p.name


def test_no_inline_nav_left():
    for p in PAGES:
        text = p.read_text(encoding="utf-8")
        for bad in ("nav-more-dropdown", "nav-toggle", 'class="nav-link'):
            assert bad not in text, f"{p.name}: {bad}"


def test_nav_targets_exist():
    js = (DOCS / "nav.js").read_text(encoding="utf-8")
    hrefs = re.findall(r"""href:\s*['"]([^'"]+\.html)['"]""", js)
    assert hrefs
    for h in hrefs:
        assert (DOCS / h).exists(), h
