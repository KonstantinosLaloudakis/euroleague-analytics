"""Every page declares the site icon, so browsers don't request a missing /favicon.ico."""
import glob
import os

ROOT = os.path.join(os.path.dirname(__file__), '..', 'docs')
TAG = '<link rel="icon" href="favicon.svg" type="image/svg+xml">'


def test_icon_file_exists():
    assert os.path.isfile(os.path.join(ROOT, 'favicon.svg'))


def test_every_page_links_the_icon_once():
    pages = sorted(glob.glob(os.path.join(ROOT, '*.html')))
    assert pages
    bad = [os.path.basename(p) for p in pages
           if open(p, encoding='utf-8').read().count(TAG) != 1]
    assert not bad, f'pages without exactly one favicon link: {bad}'
