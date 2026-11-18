import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
SCRIPT_SRC = re.compile(r'<script\s+src="([^"/:?]+\.js)"')


def test_pages_load_helper_before_use():
    for page in sorted(DOCS.glob("*.html")):
        srcs = SCRIPT_SRC.findall(page.read_text(encoding="utf-8"))
        for i, src in enumerate(srcs):
            f = DOCS / src
            if src == "player-links.js" or not f.exists():
                continue
            if "PlayerLinks" in f.read_text(encoding="utf-8"):
                assert "player-links.js" in srcs[:i], f"{page.name}: {src} uses PlayerLinks before player-links.js"
