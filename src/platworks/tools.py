"""platworks MCP tool registry — the public product surface.

Single source of truth for the names and one-line purposes of the tools
the platworks MCP server exposes. The server registers exactly these
tools (see the drift test in ``tests/test_tools.py``); the landing page
and README list them from here so docs can never advertise a tool the
server lacks, and the server can never ship a tool the docs hide.

Every tool is read-only over the packaged catalog and generators: no
network calls, no filesystem reads, no private data.
"""

TOOL_SPECS = (
    (
        "list_components",
        "List ecosystem components, optionally filtered by category",
    ),
    (
        "get_component",
        "Get one component by exact name, with its verified repo or an honest private marker",
    ),
    (
        "find_components",
        "Find all components in one category (closed vocabulary)",
    ),
    (
        "list_categories",
        "List the closed category vocabulary with component counts",
    ),
    (
        "list_public_components",
        "List only public components that carry verified repository links",
    ),
    (
        "list_private_components",
        "List private components (names only — no repo, no description claims)",
    ),
    (
        "search_components",
        "Search components by substring across name, category, tags, and verified descriptions",
    ),
    (
        "get_ecosystem_overview",
        "Get the ecosystem at a glance: counts, principle, and package facts",
    ),
    (
        "get_install_instructions",
        "Get install commands and the MCP client config for wiring platworks in",
    ),
    (
        "get_demo_portfolio",
        "Get the synthetic demo portfolio (fabricated data, clearly labeled)",
    ),
    (
        "get_landing_page",
        "Get the standalone product landing page as HTML (self-contained, no external assets)",
    ),
)

TOOL_NAMES = tuple(name for name, _ in TOOL_SPECS)
TOOL_PURPOSES = {name: purpose for name, purpose in TOOL_SPECS}
TOOL_COUNT = len(TOOL_SPECS)

PRINCIPLE = (
    "Numbers come from deterministic engines, never from a model."
)