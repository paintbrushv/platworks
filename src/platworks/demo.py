"""Synthetic demo for the platworks umbrella.

Writes a self-contained demo directory:

- ``portfolio.json`` — a small **synthetic** fictional multifamily
  portfolio, each asset mapped to the ecosystem components that would
  underwrite / operate / study it.
- ``run_demo.py`` — an executable end-to-end script that starts the real
  platworks MCP server over stdio, drives it with a real MCP client
  session, and prints the catalog answers for the portfolio.
- ``README.md`` — usage and the synthetic-data notice.

All data is fabricated. No real deals, tenants, or portfolio data.
"""

import copy
import json
import os


class DemoOutputExistsError(FileExistsError):
    """Raised when the demo output directory exists and overwrite=False."""


def synthetic_portfolio():
    """Return an isolated copy of the synthetic portfolio payload.

    The MCP server's ``get_demo_portfolio`` tool serves this; returning a
    deep copy keeps the demo's on-disk fixture and the served payload
    consistent while protecting the module-level constant from mutation.
    """
    return copy.deepcopy(_SYNTHETIC_PORTFOLIO)

_DEMO_FILES = ("portfolio.json", "run_demo.py", "README.md")

_SYNTHETIC_PORTFOLIO = {
    "synthetic": True,
    "data_license": "synthetic-fabricated-demo-data",
    "notice": (
        "All properties, numbers, and names in this portfolio are "
        "fabricated for demonstration. They illustrate how the plat "
        "ecosystem components compose; they are not real assets."
    ),
    "properties": [
        {
            "name": "Bluebonnet Ridge",
            "city": "Round Rock, TX",
            "units": 248,
            "year_built": 2016,
            "story": (
                "Stabilized garden-style asset; underwrite the rent roll "
                "and T12 deterministically, then keep NOI variance honest "
                "month over month."
            ),
            "components": [
                "plat-multifamily-underwriting",
                "plat-harness",
                "plat-operations",
                "geostack",
            ],
        },
        {
            "name": "Copper Creek Flats",
            "city": "Fort Worth, TX",
            "units": 132,
            "year_built": 2009,
            "story": (
                "Value-add mid-rise in a supply-heavy submarket; market "
                "study and submarket analytics lead, underwriting follows."
            ),
            "components": [
                "plat-market-study-agent",
                "plat-multifamily-underwriting",
                "geostack",
            ],
        },
        {
            "name": "Harborlight Gardens",
            "city": "Tampa, FL",
            "units": 96,
            "year_built": 1998,
            "story": (
                "Older asset in lease-up; NOI variance and collections "
                "focus first, market study second."
            ),
            "components": [
                "plat-operations",
                "plat-market-study-agent",
                "plat-harness",
            ],
        },
    ],
}

_RUN_DEMO = r'''#!/usr/bin/env python3
"""platworks demo — drives the real MCP server over stdio.

Run from this directory:  python run_demo.py

The script connects to the platworks MCP server as a real MCP stdio
client and exercises every tool the server exposes: it asks for the
ecosystem overview, browses the catalog, searches it, resolves the
components behind each synthetic portfolio asset, fetches the install
instructions, the synthetic portfolio itself, and the product landing
page. No network access beyond the local subprocess; no real data.
"""

import asyncio
import json
import os
import sys

PORTFOLIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")


async def call(session, tool, args=None):
    result = await session.call_tool(tool, args or {})
    payload = json.loads(result.content[0].text)
    if "error" in payload:
        print(f"    [{tool}] ERROR {payload['error']['type']}: "
              f"{payload['error']['message']}")
        return None
    return payload


async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    import platworks

    # The MCP stdio launcher sanitizes the child environment (it strips
    # PYTHONPATH), so point the child explicitly at the platworks package
    # this very script imported — works both for a pip install and for a
    # source-tree run.
    src_root = os.path.dirname(os.path.dirname(os.path.abspath(platworks.__file__)))
    server_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    server_env["PYTHONPATH"] = src_root

    params = StdioServerParameters(
        command=sys.executable,
        args=["-B", "-c", "from platworks.mcp_server import main; main()"],
        env=server_env,
    )

    with open(PORTFOLIO) as fh:
        portfolio = json.load(fh)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"connected to platworks MCP server: {len(tools.tools)} tools available")

            # 1. ecosystem overview first — the map before the terrain
            overview = await call(session, "get_ecosystem_overview")
            print("\n=== overview ===")
            print(f"    principle: {overview['principle']}")
            print(f"    components: {overview['counts']['public']} public, "
                  f"{overview['counts']['private']} private")

            # 2. closed category vocabulary with counts
            cats = await call(session, "list_categories")
            print("\n=== categories ===")
            for c in cats["categories"]:
                print(f"    {c['category']}: {c['public']} public / "
                      f"{c['private']} private")

            # 3. browse: all, public-only, private-only
            all_comps = await call(session, "list_components")
            pub = await call(session, "list_public_components")
            priv = await call(session, "list_private_components")
            print("\n=== catalog ===")
            print(f"    list_components: {all_comps['count']} entries")
            print(f"    list_public_components: {pub['count']} clonable repos")
            print(f"    list_private_components: {priv['count']} "
                  "(no public claims)")

            # 4. find within one category
            geo = await call(session, "find_components", {"category": "geospatial"})
            print(f"    find_components(geospatial): "
                  f"{', '.join(c['name'] for c in geo['components'])}")

            # 5. keyword search across names, tags, and descriptions
            hits = await call(session, "search_components", {"query": "noi"})
            print(f"    search_components('noi'): "
                  f"{', '.join(c['name'] for c in hits['components'])}")

            # 6. per-asset component resolution against the catalog
            demo_pf = await call(session, "get_demo_portfolio")
            assert demo_pf["synthetic"] is True
            for prop in portfolio["properties"]:
                print(f"\n=== {prop['name']} ({prop['units']} units, "
                      f"{prop['city']}) ===")
                print(f"    {prop['story']}")
                for name in prop["components"]:
                    comp = await call(session, "get_component", {"name": name})
                    entry = comp["component"]
                    if entry["public"]:
                        print(f"    {name} -> {entry['repo']}")
                    else:
                        print(f"    {name} -> (private component, no public "
                              "repository yet)")

            # 7. wire-in instructions
            install = await call(session, "get_install_instructions")
            print("\n=== install ===")
            print(f"    {install['install']}  (console scripts: "
                  f"{', '.join(install['console_scripts'])})")

            # 8. the product landing page, served as HTML
            landing = await call(session, "get_landing_page")
            print("\n=== landing page ===")
            print(f"    {landing['filename']}: {len(landing['html'])} bytes "
                  "of self-contained HTML")

            print("\ndemo complete — every MCP tool exercised once; all data "
                  "in this demo is synthetic.")


if __name__ == "__main__":
    asyncio.run(main())'''

_README = """# platworks synthetic demo

This directory contains a small **synthetic** multifamily portfolio and
an executable demo that shows how the plat ecosystem components compose
per asset.

## Run

```bash
python run_demo.py
```

The demo starts the real `platworks` MCP server over stdio, connects as
an MCP client, and resolves each portfolio asset's component list
against the verified catalog.

## Files

- `portfolio.json` — synthetic portfolio (fabricated names, cities, and
  numbers; component mappings reference the verified catalog).
- `run_demo.py` — the end-to-end demo script (MCP stdio round-trip).

## Data notice

All data in this demo is **synthetic**. No real deal, tenant, owner, or
portfolio data is included. Synthetic data is licensed as
`synthetic-fabricated-demo-data`; reuse freely for evaluation.
"""


def write_demo(output_dir, overwrite=False):
    """Write the demo directory; return the absolute output path."""
    output_dir = os.path.abspath(output_dir)
    if os.path.exists(output_dir) and not overwrite:
        existing = [f for f in _DEMO_FILES if os.path.exists(os.path.join(output_dir, f))]
        if existing:
            raise DemoOutputExistsError(
                f"demo output already exists in {output_dir}: "
                + ", ".join(sorted(existing))
                + " (pass overwrite=True to replace)"
            )
    os.makedirs(output_dir, exist_ok=True)

    # Refuse to write over the demo's own expectations if the synthetic
    # portfolio ever drifts from the catalog (unknown component names).
    from platworks import catalog

    for prop in _SYNTHETIC_PORTFOLIO["properties"]:
        for comp in prop["components"]:
            catalog.get_component(comp)

    with open(os.path.join(output_dir, "portfolio.json"), "w") as fh:
        json.dump(_SYNTHETIC_PORTFOLIO, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(output_dir, "run_demo.py"), "w") as fh:
        fh.write(_RUN_DEMO)
    with open(os.path.join(output_dir, "README.md"), "w") as fh:
        fh.write(_README)
    return output_dir