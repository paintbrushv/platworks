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
| [plat-agent](https://github.com/paintbrushv/plat-agent) | Orchestration through MCP tool composition |
| [plat-costmodel](https://github.com/paintbrushv/plat-costmodel) | Cost estimates, renovation ROI, scopes of work, and bid evaluation |
| [plat-submarket-atlas](https://github.com/paintbrushv/plat-submarket-atlas) | Parcel-based submarket scoring; requires PostGIS and geostack |
| [plat-supply-demand](https://github.com/paintbrushv/plat-supply-demand) | Supply pipeline and absorption analytics (MIT license) |

All nine catalogued repositories are public as of 2026-10-03. Public visibility
is separate from installation, financial acceptance, and assistant-host support.
The [catalog evidence](docs/catalog-evidence.json) records verified metadata;
[baseline status](docs/v0.1-baseline.md) lists the remaining release work.

## Install the packaging candidate

The candidate is `platworks==0.1.4`; these versions have not been uploaded to PyPI.
Use the reviewed wheel artifacts and [clean-install guide](docs/installation.md).
The analysis profile pins underwriting 0.1.2 and costmodel, harness, and operations
0.1.1. It includes the native `boxscore-exact` executable and MCP 2.3–2.x.

With all candidate wheels in `wheelhouse/`:

```bash
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install --only-binary=:all: --find-links wheelhouse 'platworks[analysis]==0.1.4'
platworks doctor --analysis --json
python -I -m platworks.verify_install
```

The hashed dependency locks and CI verification commands are in the install guide.
A catalog-only install omits the `analysis` extra. `platworks doctor` checks that
lighter profile. Financial tools require the analysis producers; see
[financial contracts](docs/financial-core.md).

## Review acquisition and operating files

The analysis candidate includes a local browser workflow:

```bash
platworks review ./my-review-workspace
```

Review source mappings and assumptions, authorize acquisition base/downside
calculations, and separately freeze the original thesis. For operations, review
the exact-cent NOI bridge and issue an immutable report; later corrections link
to that report and retain its history. Each decision binds the exact files,
policy, mappings and producer identities. No MCP tool grants approval.

See [supported file layouts and walkthroughs](docs/local-review.md). Initial
support covers canonical JSON and standardized CSV/XLSX. Synthetic browser checks pass; independent-user pilots remain pending.
This is an unpublished candidate.

## The MCP server

The `platworks-mcp` console script (or `python -m platworks.mcp_server`) runs an MCP
stdio server exposing the verified catalog and the package's own product surface as
eleven catalog tools:

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
| `underwrite_run` | Run the deterministic underwriting engine on a canonical deal; unverified scenario metrics verbatim |
| `underwrite_backsolve` | Backsolve the highest purchase price meeting a target Year-1 post-debt CoC |
| `tax_regime_lookup` | Researched, statute-cited property-tax regime schedules (TX CA FL AL; unknown states refuse) |
| `renovation_estimate` | Per-unit renovation cost ranges with line items and age-based risk flags |
| `renovation_roi` | ROI threshold check (conservative: high cost estimate) |
| `generate_sow` | Contractor-ready scope of work with material specs |
| `evaluate_bid` | Contractor bid evaluation against the internal estimate |
| `ops_review` | Read-only one-property/one-period ops review; variance only through a bound oracle |

The product tools import their sibling services lazily: the catalog server keeps
working without them installed, and each product tool refuses with a typed
`BACKEND_UNAVAILABLE` payload when analysis dependencies are missing.

Failures are typed refusals inside the payload
(`{"error": {"type": ..., "message": ...}}`) naming the valid options, never opaque
crashes. The catalog registry, product registry and library tools define the server.

Six additional tools provide `search_library`, `get_reference`,
`get_synthetic_example`, `preview_operations`, `list_local_sources` and
`read_local_source`. This gives **25 local tools**. The **22-tool public profile**
excludes `ops_review` and both local source tools. All scenario results identify
unverified inputs, producer versions and hashes; no MCP tool grants approval.

The [reference library](docs/reference-library.md) packages 15 original references
with dated source checks; independent domain review is pending. See
[assistant setup and attachment acceptance](docs/assistant-integrations.md) for
ChatGPT, Claude, Grok.com and Muse.ai status, and [deployment files](deploy/README.md)
for the stateless HTTP container. Hosting will be chosen later; no public endpoint
or working consumer-host integration is claimed yet.

Wire the installed local server into an MCP client:

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
platworks review ./review         # open the local human review workspace
```

Exit codes are stable: `0` success, `2` typed refusal (unknown component/category)
with an actionable message on stderr.

## The demo (synthetic only)

```bash
platworks demo ./demo && python demo/run_demo.py
```

The demo writes a **synthetic** three-property portfolio (fabricated names, cities,
and numbers) and an executable script that starts the real MCP server over stdio,
connects as a genuine MCP client, and exercises all eleven catalog tools end to end:
ecosystem overview, category vocabulary, catalog browsing, keyword search, the
install instructions, the served portfolio, the landing page, and each asset's
component mapping resolved against the verified catalog.

## The landing page

`platworks landing` renders a single self-contained HTML file — inline CSS, no CDN,
no scripts, no tracking — from the live catalog and tool registry: public components
with their verified repository links, private components honestly marked private,
the eleven catalog tools, and copy-paste install instructions.

## Honest scope

- **Catalog claims are verified.** Public repository URLs and descriptions were
  verified against the GitHub API on 2026-10-03 and are copied verbatim; drift-gate
  tests fail the suite if a doc or generated page claims an unverified URL.
- **Synthetic data only.** No real deal, tenant, owner, or portfolio data ships in
  this package or its demo.
- **Private components make no public claims.** No repo URLs, no descriptions —
  for private entries the catalog returns `null` and says so.
- **Local execution.** The catalog and financial tools use packaged resources and
  installed producers. The review UI uses loopback HTTP and keeps files locally.

## Layout

```
src/platworks/    catalog, MCP server, CLI, demo + landing generators
tests/            pytest suite (drift gates included; slow marks for stdio e2e)
```

## License

Apache-2.0 for this umbrella — see [LICENSE](LICENSE). Component licenses are
listed separately in the catalog; `plat-supply-demand` is MIT. Demo data is synthetic.
