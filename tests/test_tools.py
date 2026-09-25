"""Drift gates for the platworks MCP tool registry.

The tool registry (``platworks.tools``) is the single source of truth
for the product surface: the server must register exactly those tools,
with those purposes surfaced as descriptions, and the landing page /
README must list them from the registry. These tests make drift
impossible in either direction.
"""

import asyncio
import json

from platworks import catalog, tools
from platworks.mcp_server import build_server


def _run(coro):
    return asyncio.run(coro)


def _payload(result):
    assert result.content, "tool returned no content"
    return json.loads(result.content[0].text)


def test_registry_declares_eleven_tools():
    assert tools.TOOL_COUNT == 11
    assert len(tools.TOOL_NAMES) == 11
    assert len(set(tools.TOOL_NAMES)) == 11, "tool names must be unique"


def test_server_registers_exactly_the_registry_tools():
    from platworks import wrappers
    registered = _run(build_server().list_tools())
    assert {t.name for t in registered} == set(tools.TOOL_NAMES) | set(wrappers.PRODUCT_TOOL_NAMES)
    assert len(registered) == 19


def test_every_registered_tool_is_described():
    registered = _run(build_server().list_tools())
    for t in registered:
        assert t.description, f"tool {t.name} lacks a description"
        assert t.input_schema.get("type") == "object", t.name


def test_registry_purposes_are_substrings_of_tool_descriptions():
    """The registry's one-line purposes must surface in the tool docs."""
    registered = {
        t.name: t.description or "" for t in _run(build_server().list_tools())
    }
    for name, purpose in tools.TOOL_SPECS:
        assert purpose[:20] in registered[name], (
            f"tool {name} docstring does not carry its registry purpose"
        )


def test_landing_page_lists_every_tool_from_the_registry():
    from platworks import landing_page

    html = landing_page.build_html()
    for name in tools.TOOL_NAMES:
        assert name in html, f"landing page does not list tool {name}"
    assert f"{tools.TOOL_COUNT} MCP tools" in html


def test_tool_results_carry_no_private_paths():
    server = build_server()
    result = _run(server.call_tool("get_landing_page", {}))
    html = _payload(result)["html"]
    assert "/home/" not in html
    assert "-uplift" not in html


def test_catalog_accessors_backing_the_tools():
    counts = catalog.counts()
    assert counts["total"] == counts["public"] + counts["private"]
    assert counts["total"] == len(catalog.list_components())

    cat_counts = catalog.category_counts()
    assert [c["category"] for c in cat_counts] == list(catalog.CATEGORIES)
    assert sum(c["total"] for c in cat_counts) == counts["total"]

    assert catalog.search_components("NOI") == catalog.search_components("noi")
    assert all(
        c["name"] == "plat-operations" for c in catalog.search_components("boxscore")
    )
    assert catalog.search_components("definitely-not-a-thing") == []