import re
from pathlib import Path


DOCS = Path(__file__).resolve().parent.parent / "docs"
NAV_PLACEHOLDER = '<nav class="site-nav" id="site-nav" aria-label="Main"></nav>'
NAMES_BEFORE_NAV = re.compile(
    re.escape(NAV_PLACEHOLDER) + r'\s*<script src="names.js"></script>\s*<script src="nav.js"></script>'
)


def test_names_js_loads_before_nav_js_on_every_page():
    pages = [p for p in sorted(DOCS.glob("*.html")) if NAV_PLACEHOLDER in p.read_text(encoding="utf-8")]
    assert pages
    for p in pages:
        text = p.read_text(encoding="utf-8")
        assert len(NAMES_BEFORE_NAV.findall(text)) == 1, p.name
        assert text.count('<script src="names.js"></script>') == 1, p.name


def test_no_local_name_formatters():
    pat = re.compile(r"function\s+(formatName|formatPlayerName|_cleanName)\b|\b_cleanName\s*[=(:]")
    offenders = []
    for p in sorted(DOCS.glob("*.js")):
        if p.name == "names.js":
            continue
        if pat.search(p.read_text(encoding="utf-8")):
            offenders.append(p.name)
    assert not offenders, offenders
