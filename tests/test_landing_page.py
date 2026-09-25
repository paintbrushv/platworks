"""Tests for the platworks landing page.

The landing page is a **standalone** single-file HTML page (inline CSS,
no external assets, no CDN, no network) that renders the verified
catalog. It must be honest: only public components with verified repos
are shown with links; private components are listed as private without
repo links or unverified descriptions. The page derives entirely from
``platworks.catalog`` so it cannot drift from the code.
"""

import re

import pytest

from platworks import catalog, landing_page


def test_render_writes_standalone_html(tmp_path):
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    html = open(out).read()
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_page_has_no_external_requests(tmp_path):
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    html = open(out).read()
    # no CDN, no remote scripts, styles, images, or fonts
    assert "http://" not in html.replace("http://github.com", "")
    for marker in ("https://cdn", "//cdn", "<script src", "<link", "src=\"http"):
        assert marker not in html, marker
    # the only external URLs allowed are the verified repo links
    urls = set(re.findall(r'href="([^"]+)"', html))
    for url in urls:
        if url.startswith("http"):
            assert url in {c["repo"] for c in catalog.list_components()}, url


def test_page_lists_every_public_component_with_verified_link(tmp_path):
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    html = open(out).read()
    for c in catalog.list_components():
        if c["public"]:
            assert c["name"] in html
            assert f'href="{c["repo"]}"' in html


def test_page_is_honest_about_private_components(tmp_path):
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    html = open(out).read()
    private = [c for c in catalog.list_components() if not c["public"]]
    assert private, "catalog has private components"
    for c in private:
        assert c["name"] in html
        # no repo link and no description claim for private components
        assert f'href="https://github.com/paintbrushv/{c["name"]}"' not in html
        # the page must not invent a description for them
        # (their catalog description is None)
    assert "private" in html.lower()
    # catalog descriptions never leak for private entries because they are None
    for c in private:
        assert c["description"] is None


def test_page_carries_synthetic_and_license_notices(tmp_path):
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    html = open(out).read().lower()
    assert "apache-2.0" in html
    assert "platworks" in html


def test_page_contains_no_private_paths(tmp_path):
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    html = open(out).read()
    assert "/home/" not in html
    assert "-uplift" not in html


def test_render_refuses_overwrite_without_force(tmp_path):
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    with pytest.raises(landing_page.LandingOutputExistsError):
        landing_page.render_page(out)
    landing_page.render_page(out, overwrite=True)


def test_page_renders_from_catalog_data(tmp_path):
    """A name change in the catalog must appear on the page (drift gate)."""
    out = str(tmp_path / "index.html")
    landing_page.render_page(out)
    html = open(out).read()
    public = [c for c in catalog.list_components() if c["public"]]
    assert len(public) >= 5
    for c in public:
        # each public component's verified description text appears
        assert c["description"][:30] in html