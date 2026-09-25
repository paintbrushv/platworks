"""Drift gate for the checked-in landing asset.

The rendered landing page is checked in at ``docs/index.html`` so it can
be served statically (e.g. GitHub Pages). A checked-in render can go
stale when the catalog changes; this test forces it to be re-rendered:
the file on disk must be byte-identical to a fresh
``landing_page.build_html()``.
"""

import os

from platworks import landing_page

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = os.path.join(ROOT, "docs", "index.html")


def test_checked_in_landing_asset_is_fresh():
    assert os.path.isfile(ASSET), (
        "docs/index.html is missing — run `platworks landing docs/index.html --force`"
    )
    with open(ASSET) as fh:
        checked_in = fh.read()
    fresh = landing_page.build_html()
    assert checked_in == fresh, (
        "docs/index.html is stale — it does not match the current catalog; "
        "re-render it with `platworks landing docs/index.html --force`"
    )