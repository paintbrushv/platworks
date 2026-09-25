"""Tests for the platworks MCP server (mcp 2.x MCPServer).

The server exposes the verified catalog as MCP tools. Tool calls are
exercised through the real ``MCPServer.call_tool`` path; typed refusals
are returned as payloads (never swallowed, never leaking internals).
An end-to-end stdio round-trip proves a real MCP client can drive it.
"""

import asyncio
import json
import sys

import pytest

from platworks import catalog
from platworks.mcp_server import build_server


def _run(coro):
    return asyncio.run(coro)


def _payload(result):
    """Decode the JSON text content of a CallToolResult."""
    assert result.content, "tool returned no content"
    text = result.content[0].text
    return json.loads(text)


def test_server_identity_and_instructions():
    server = build_server()
    assert server.name == "platworks"
    assert server.version
    assert server.description
    assert "plat" in (server.description or "").lower()
    assert server.instructions


def test_list_tools_exposes_catalog_tools():
    tools = _run(build_server().list_tools())
    names = {t.name for t in tools}
    assert "list_components" in names
    assert "get_component" in names
    assert "find_components" in names
    for t in tools:
        assert t.description, f"tool {t.name} lacks a description"
        assert t.input_schema.get("type") == "object", t.name


def test_tool_list_categories_reports_closed_vocabulary():
    result = _run(build_server().call_tool("list_categories", {}))
    payload = _payload(result)
    assert [c["category"] for c in payload["categories"]] == list(catalog.CATEGORIES)
    for c in payload["categories"]:
        assert c["total"] == c["public"] + c["private"]
    assert sum(c["total"] for c in payload["categories"]) == len(
        catalog.list_components()
    )


def test_tool_list_public_components_only_public():
    result = _run(build_server().call_tool("list_public_components", {}))
    payload = _payload(result)
    assert payload["count"] == sum(1 for c in catalog.list_components() if c["public"])
    for c in payload["components"]:
        assert c["public"] is True
        assert c["repo"].startswith("https://github.com/")


def test_tool_list_private_components_make_no_claims():
    result = _run(build_server().call_tool("list_private_components", {}))
    payload = _payload(result)
    assert payload["count"] == sum(
        1 for c in catalog.list_components() if not c["public"]
    )
    for c in payload["components"]:
        assert c["public"] is False
        assert c["repo"] is None
        assert c["description"] is None
    assert "no public claims" in payload["notice"]


def test_tool_search_components_finds_by_tag_and_description():
    by_tag = _run(
        build_server().call_tool("search_components", {"query": "boxscore"})
    )
    payload = _payload(by_tag)
    names = {c["name"] for c in payload["components"]}
    assert "plat-operations" in names
    assert payload["query"] == "boxscore"

    by_desc = _run(
        build_server().call_tool("search_components", {"query": "deterministic"})
    )
    names2 = {c["name"] for c in _payload(by_desc)["components"]}
    assert "plat-multifamily-underwriting" in names2


def test_tool_search_components_is_case_insensitive():
    lower = _run(build_server().call_tool("search_components", {"query": "noi"}))
    upper = _run(build_server().call_tool("search_components", {"query": "NOI"}))
    assert _payload(lower)["components"] == _payload(upper)["components"]


def test_tool_search_components_empty_result_is_count_zero_not_error():
    result = _run(
        build_server().call_tool("search_components", {"query": "zzz-no-match"})
    )
    payload = _payload(result)
    assert "error" not in payload
    assert payload["count"] == 0
    assert payload["components"] == []


def test_tool_search_components_missing_query_is_typed_refusal():
    result = _run(build_server().call_tool("search_components", {}))
    payload = _payload(result)
    assert payload["error"]["type"] == "missing_argument"
    assert "query" in payload["error"]["message"]


def test_tool_get_ecosystem_overview_matches_catalog():
    result = _run(build_server().call_tool("get_ecosystem_overview", {}))
    payload = _payload(result)
    c = catalog.counts()
    assert payload["counts"] == c
    assert payload["principle"]
    assert payload["synthetic_data_only"] is True
    assert set(payload["public_components"]) == {
        e["name"] for e in catalog.list_components() if e["public"]
    }
    assert set(payload["private_components"]) == {
        e["name"] for e in catalog.list_components() if not e["public"]
    }
    assert payload["mcp_tools"], "overview must list the tool surface"


def test_tool_get_install_instructions_actionable():
    result = _run(build_server().call_tool("get_install_instructions", {}))
    payload = _payload(result)
    assert "pip install" in payload["install"]
    assert "platworks-mcp" in payload["mcp_client_config"]
    assert "mcpServers" in payload["mcp_client_config"]
    assert payload["cli_quickstart"]


def test_tool_get_demo_portfolio_is_synthetic():
    result = _run(build_server().call_tool("get_demo_portfolio", {}))
    payload = _payload(result)
    assert payload["synthetic"] is True
    assert payload["data_license"] == "synthetic-fabricated-demo-data"
    assert len(payload["properties"]) >= 3
    for prop in payload["properties"]:
        for comp in prop["components"]:
            catalog.get_component(comp)


def test_tool_get_landing_page_serves_build_html():
    from platworks import landing_page

    result = _run(build_server().call_tool("get_landing_page", {}))
    payload = _payload(result)
    assert payload["html"] == landing_page.build_html()
    assert payload["html"].startswith("<!DOCTYPE html>")
    assert payload["filename"].endswith(".html")


def test_tool_list_components_returns_all_nine():
    result = _run(build_server().call_tool("list_components", {}))
    assert result.is_error is False
    payload = _payload(result)
    assert isinstance(payload, dict)
    components = payload["components"]
    assert len(components) == len(catalog.list_components())
    assert {c["name"] for c in components} == {
        c["name"] for c in catalog.list_components()
    }


def test_tool_list_components_supports_category_filter():
    result = _run(build_server().call_tool("list_components", {"category": "geospatial"}))
    payload = _payload(result)
    names = {c["name"] for c in payload["components"]}
    assert "geostack" in names
    assert all(c["category"] == "geospatial" for c in payload["components"])


def test_tool_list_components_unknown_category_is_typed_refusal():
    result = _run(
        build_server().call_tool("list_components", {"category": "not-a-category"})
    )
    payload = _payload(result)
    assert payload["error"]["type"] == "unknown_category"
    assert "not-a-category" in payload["error"]["message"]
    # The refusal names the closed vocabulary so a client can self-correct.
    for cat in catalog.CATEGORIES:
        assert cat in payload["error"]["message"]


def test_tool_get_component_returns_record():
    result = _run(build_server().call_tool("get_component", {"name": "geostack"}))
    payload = _payload(result)
    assert payload["component"]["name"] == "geostack"
    assert payload["component"]["public"] is True
    assert payload["component"]["repo"] == "https://github.com/paintbrushv/geostack"


def test_tool_get_component_unknown_is_typed_refusal():
    result = _run(build_server().call_tool("get_component", {"name": "nope"}))
    payload = _payload(result)
    assert payload["error"]["type"] == "unknown_component"
    assert "nope" in payload["error"]["message"]


def test_tool_get_component_private_makes_no_public_claims():
    result = _run(build_server().call_tool("get_component", {"name": "plat-agent"}))
    payload = _payload(result)
    comp = payload["component"]
    assert comp["public"] is False
    assert comp["repo"] is None
    assert comp["description"] is None


def test_tool_find_components_requires_category():
    server = build_server()
    result = _run(server.call_tool("find_components", {}))
    payload = _payload(result)
    assert payload["error"]["type"] == "missing_argument"


def test_tool_results_carry_no_private_paths():
    result = _run(build_server().call_tool("list_components", {}))
    text = result.content[0].text
    assert "/home/" not in text
    assert "-uplift" not in text


def test_main_module_has_stdio_entrypoint():
    from platworks import mcp_server

    assert callable(mcp_server.main)


@pytest.mark.slow
def test_stdio_end_to_end_roundtrip(tmp_path):
    """A real MCP stdio client must be able to drive the server."""
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    server_cmd = (
        f"import sys; sys.path.insert(0, {src!r}); "
        "from platworks.mcp_server import main; main()"
    )
    params = StdioServerParameters(
        command=sys.executable, args=["-B", "-c", server_cmd]
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert {"list_components", "get_component", "find_components"} <= names

                res = await session.call_tool("get_component", {"name": "plat-harness"})
                assert res.is_error is False
                payload = json.loads(res.content[0].text)
                assert payload["component"]["repo"] == (
                    "https://github.com/paintbrushv/plat-harness"
                )

                res2 = await session.call_tool("get_component", {"name": "nope"})
                payload2 = json.loads(res2.content[0].text)
                assert payload2["error"]["type"] == "unknown_component"

                # drive every one of the eleven tools end-to-end
                from platworks import tools as tool_registry
                from platworks import wrappers as product_registry

                assert len(tools.tools) == (
                    tool_registry.TOOL_COUNT
                    + len(product_registry.PRODUCT_TOOL_NAMES)
                ) == 19
                calls = {
                    "list_components": {},
                    "get_component": {"name": "geostack"},
                    "find_components": {"category": "geospatial"},
                    "list_categories": {},
                    "list_public_components": {},
                    "list_private_components": {},
                    "search_components": {"query": "noi"},
                    "get_ecosystem_overview": {},
                    "get_install_instructions": {},
                    "get_demo_portfolio": {},
                    "get_landing_page": {},
                }
                assert set(calls) == set(tool_registry.TOOL_NAMES)
                for tool_name, args in calls.items():
                    res = await session.call_tool(tool_name, args)
                    assert res.is_error is False, tool_name
                    body = json.loads(res.content[0].text)
                    assert isinstance(body, dict) and "error" not in body, tool_name

    asyncio.run(scenario())