# platworks

Umbrella package, MCP server, and landing assets for the **plat** commercial-real-estate
ecosystem: a verified component catalog served as MCP tools, a synthetic end-to-end
demo, and a standalone landing page — all generated from one source of truth.

The plat ecosystem's principle: **numbers come from deterministic engines, never from
a model.** This umbrella makes the ecosystem navigable — one catalog, one MCP server,
one honest landing page.

## Components (verified catalog)

| Component | What it is |
|---|---|
| [plat-multifamily-underwriting](https://github.com/paintbrushv/plat-multifamily-underwriting) | Deterministic multifamily underwriting engine |
| [plat-harness](https://github.com/paintbrushv/plat-harness) | Agent-agnostic control plane for underwriting and asset operations |
| [plat-market-study-agent](https://github.com/paintbrushv/plat-market-study-agent) | Expert-level multifamily market studies with strict data separation |
| [plat-operations](https://github.com/paintbrushv/plat-operations) | Local-first NOI variance intelligence harness (BOXSCORE, Rust) |
| [geostack](https://github.com/paintbrushv/geostack) | PostGIS/GIS utility layer for multifamily market analytics |

A further four components (orchestration, cost modeling, submarket atlas, supply/demand)
are private and not yet published; the catalog and MCP server report them as private with
no repository links.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## The MCP server

The `platworks-mcp` console script (or `python -m platworks.mcp_server`) runs an MCP
stdio server exposing the verified catalog and the package's own product surface as
eleven read-only tools:

| Tool | What it does |
|---|---|
| `get_ecosystem_overview` | The ecosystem at a glance: counts, principle, tool list |
| `list_components` | All components, optional `category` filter |
| `get_component` | One component by exact name |
| `find_components` | Components within one category |
| `list_categories` | The closed category vocabulary with counts |
| `list_public_components` | The public components that carry verified repo links |
| `list_private_components` | Private components (names only — no public claims) |
| `search_components` | Case-insensitive substring search across names, tags, descriptions |
| `get_install_instructions` | Install commands and the MCP client config snippet |
| `get_demo_portfolio` | The synthetic demo portfolio (fabricated, clearly labeled) |
| `get_landing_page` | The standalone product landing page as HTML |

Plus eight **product tools** that wrap the ecosystem's real deterministic
services — the numbers come back exactly as the wrapped engine/costmodel/harness
service computed them, with a provenance record on every response:

| Tool | What it does |
|---|---|
| `underwrite_run` | Run the deterministic underwriting engine on a canonical deal; certified metrics verbatim |
| `underwrite_backsolve` | Backsolve the highest purchase price meeting a target Year-1 post-debt CoC |
| `tax_regime_lookup` | Researched, statute-cited property-tax regime schedules (TX CA FL AL; unknown states refuse) |
| `renovation_estimate` | Per-unit renovation cost ranges with line items and age-based risk flags |
| `renovation_roi` | ROI threshold check (conservative: high cost estimate) |
| `generate_sow` | Contractor-ready scope of work with material specs |
| `evaluate_bid` | Contractor bid evaluation against the internal estimate |
| `ops_review` | Read-only one-property/one-period ops review; variance only through a bound oracle |

The product tools import their sibling services lazily: the catalog server keeps
working without them installed, and each product tool refuses with a typed
`BACKEND_UNAVAILABLE` payload naming the missing service.

Failures are typed refusals inside the payload
(`{"error": {"type": ..., "message": ...}}`) naming the valid options, never opaque
crashes. The tool list is declared once in `platworks.tools` and the server, landing
page, and tests all derive from it. Wire it into any MCP client:

```json
{
  "mcpServers": {
    "platworks": {
      "command": "platworks-mcp"
    }
  }
}
```

## CLI quickstart

```bash
platworks catalog                 # human-readable component list
platworks catalog --json          # exact catalog module output
platworks catalog --category geospatial
platworks get plat-harness        # one component
platworks demo                    # write the synthetic demo to ./platworks-demo
platworks landing                 # render landing.html (standalone, no external assets)
platworks mcp                     # run the MCP stdio server
```

Exit codes are stable: `0` success, `2` typed refusal (unknown component/category)
with an actionable message on stderr.

## The demo (synthetic only)

```bash
platworks demo ./demo && python demo/run_demo.py
```

The demo writes a **synthetic** three-property portfolio (fabricated names, cities,
and numbers) and an executable script that starts the real MCP server over stdio,
connects as a genuine MCP client, and exercises all eleven tools end to end:
ecosystem overview, category vocabulary, catalog browsing, keyword search, the
install instructions, the served portfolio, the landing page, and each asset's
component mapping resolved against the verified catalog.

## The landing page

`platworks landing` renders a single self-contained HTML file — inline CSS, no CDN,
no scripts, no tracking — from the live catalog and tool registry: public components
with their verified repository links, private components honestly marked private,
the eleven MCP tools the server ships, and copy-paste install instructions.

## Honest scope

- **Catalog claims are verified.** Public repository URLs and descriptions were
  verified against the GitHub API on 2026-09-24 and are copied verbatim; drift-gate
  tests fail the suite if a doc or generated page claims an unverified URL.
- **Synthetic data only.** No real deal, tenant, owner, or portfolio data ships in
  this package or its demo.
- **Private components make no public claims.** No repo URLs, no descriptions —
  for private entries the catalog returns `null` and says so.
- **No network calls at runtime.** The MCP server, CLI, and landing generator read
  the packaged catalog only.

## Layout

```
src/platworks/    catalog, MCP server, CLI, demo + landing generators
tests/            pytest suite (drift gates included; slow marks for stdio e2e)
```

## License

Apache-2.0 — see [LICENSE](LICENSE). Demo data is synthetic and marked as such.