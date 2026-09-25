"""Tests for the platworks component catalog.

The catalog is the umbrella's single source of truth for ecosystem
components. Every public claim (repo URL, description, license) was
verified against the GitHub API on 2026-09-24; private components make
no public claims at all.
"""

import pytest

from platworks import catalog

PUBLIC_NAMES = [
    "plat-multifamily-underwriting",
    "plat-harness",
    "plat-market-study-agent",
    "plat-operations",
    "geostack",
]

PRIVATE_NAMES = [
    "plat-agent",
    "plat-costmodel",
    "plat-submarket-atlas",
    "plat-supply-demand",
]


def test_list_components_covers_all_public_repos():
    names = {c["name"] for c in catalog.list_components()}
    for name in PUBLIC_NAMES:
        assert name in names, f"expected public component {name!r} in catalog"


def test_list_components_covers_all_private_components():
    names = {c["name"] for c in catalog.list_components()}
    for name in PRIVATE_NAMES:
        assert name in names, f"expected private component {name!r} in catalog"


def test_public_components_carry_verified_fields():
    for name in PUBLIC_NAMES:
        c = catalog.get_component(name)
        assert c["public"] is True, name
        assert c["repo"].startswith("https://github.com/paintbrushv/"), name
        assert c["repo"] == f"https://github.com/paintbrushv/{name}", name
        assert isinstance(c["description"], str) and len(c["description"]) > 10, name
        assert c["category"] in catalog.CATEGORIES, name
        assert c["license"] == "Apache-2.0", name
        assert c["language"] in catalog.LANGUAGES, name


def test_private_components_make_no_public_claims():
    for name in PRIVATE_NAMES:
        c = catalog.get_component(name)
        assert c["public"] is False, name
        assert c["repo"] is None, f"{name} must not claim a public repo URL"
        assert c["description"] is None, f"{name} must not ship an unverified description"


def test_no_private_uplift_remotes_leak_into_public_urls():
    for c in catalog.list_components():
        if c["repo"] is not None:
            assert "-uplift" not in c["repo"], c["name"]


def test_unknown_component_is_a_typed_error():
    with pytest.raises(catalog.UnknownComponentError) as excinfo:
        catalog.get_component("definitely-not-a-component")
    assert "definitely-not-a-component" in str(excinfo.value)


def test_unknown_component_error_lists_no_known_names_by_default():
    err = catalog.UnknownComponentError("nope")
    assert "nope" in str(err)


def test_find_components_filters_by_category():
    engines = catalog.find_components(category="underwriting_engine")
    assert any(c["name"] == "plat-multifamily-underwriting" for c in engines)
    for c in engines:
        assert c["category"] == "underwriting_engine"


def test_find_components_unknown_category_is_typed_error():
    with pytest.raises(catalog.UnknownCategoryError):
        catalog.find_components(category="not-a-category")


def test_results_are_isolated_deep_copies():
    first = catalog.get_component("geostack")
    first["description"] = "TAMPERED"
    first["tags"].append("tamper-tag")
    second = catalog.get_component("geostack")
    assert second["description"] != "TAMPERED"
    assert "tamper-tag" not in second["tags"]


def test_list_results_are_isolated_deep_copies():
    first = catalog.list_components()
    first[0]["tags"].append("tamper-tag")
    first[0]["name"] = "tampered-name"
    second = catalog.list_components()
    assert "tamper-tag" not in second[0]["tags"]
    assert second[0]["name"] != "tampered-name"


def test_catalog_has_no_local_paths_or_private_data():
    text = repr(catalog.list_components())
    assert "/home/" not in text
    assert "-uplift" not in text


def test_component_records_carry_honest_status_vocabulary():
    for c in catalog.list_components():
        assert c["status"] in catalog.STATUSES, c["name"]