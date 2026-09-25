"""MCP server exposing the platworks product surface (mcp 2.x).

Eleven read-only tools over the verified catalog and the package's own
generators. Design rules:

- The tool set is declared once in ``platworks.tools`` (name + purpose);
  this module registers exactly those tools, and each tool docstring
  opens with its registry purpose verbatim — so the description an MCP
  client sees and the one-liner the landing page shows are the same
  string. No drift in either direction.
- Tools return JSON-serializable dicts; the MCP layer serializes them
  into text content for clients.
- Typed refusals are returned as payloads —
  ``{"error": {"type": ..., "message": ...}}`` — never raised as bare
  exceptions: mcp 2.x swallows unexpected tool exceptions into
  ``"Error executing tool <name>"``, hiding the reason from the client.
  A payload refusal keeps the failure typed, visible, and actionable.
- The server only reads the packaged catalog and this package's own
  generators; it makes no network calls and carries no private paths
  or data.
"""

from mcp.server.mcpserver import MCPServer

from platworks import __version__, catalog, landing_page, tools, wrappers
from platworks import demo as demo_module

_ERROR_UNKNOWN_CATEGORY = "unknown_category"
_ERROR_UNKNOWN_COMPONENT = "unknown_component"
_ERROR_MISSING_ARGUMENT = "missing_argument"

_INSTALL_SNIPPET = (
    "pip install platworks\n"
    "\n"
    "MCP client config (stdio):\n"
    "{\n"
    "  \"mcpServers\": {\n"
    "    \"platworks\": {\n"
    "      \"command\": \"platworks-mcp\"\n"
    "    }\n"
    "  }\n"
    "}"
)


def _error(error_type, message):
    return {"error": {"type": error_type, "message": message}}


def _unknown_category_error(category):
    return _error(
        _ERROR_UNKNOWN_CATEGORY,
        f"unknown category: {category}; valid categories: "
        + ", ".join(catalog.CATEGORIES),
    )


def build_server():
    """Build the platworks MCP server (stdio transport by default)."""
    server = MCPServer(
        name="platworks",
        title="platworks",
        description=(
            "Umbrella MCP server for the plat commercial-real-estate "
            "ecosystem: a verified catalog of sibling components, install "
            "guidance, the synthetic demo, and the product landing page."
        ),
        instructions=(
            "Tools to browse and use the platworks ecosystem. Start with "
            "get_ecosystem_overview for the map, list_components to browse, "
            "search_components to find by keyword, get_component for one "
            "entry, get_install_instructions to wire platworks into an MCP "
            "client, and get_demo_portfolio / get_landing_page to see the "
            "product end to end. Public entries carry verified GitHub "
            "repository URLs; private entries make no public claims."
        ),
        version=__version__,
    )

    @server.tool()
    def list_components(category: str | None = None) -> dict:
        """List ecosystem components, optionally filtered by category.

        Categories are a closed vocabulary; an unknown category is
        returned as a typed unknown_category refusal naming the valid
        categories.
        """
        try:
            components = catalog.list_components(category=category)
        except catalog.UnknownCategoryError:
            return _unknown_category_error(category)
        return {
            "count": len(components),
            "categories": list(catalog.CATEGORIES),
            "components": components,
        }

    @server.tool()
    def get_component(name: str) -> dict:
        """Get one component by exact name, with its verified repo or an honest private marker.

        Unknown names are returned as a typed unknown_component refusal.
        Private components return public=False with no repo/description.
        """
        try:
            component = catalog.get_component(name)
        except catalog.UnknownComponentError:
            return _error(
                _ERROR_UNKNOWN_COMPONENT,
                f"unknown component: {name}",
            )
        return {"component": component}

    @server.tool()
    def find_components(category: str | None = None) -> dict:
        """Find all components in one category (closed vocabulary).

        A missing category is returned as a typed missing_argument
        refusal; an unknown category as unknown_category. (The argument
        is declared optional so the refusal reaches the client as a
        payload instead of a framework-level validation crash.)
        """
        if not category:
            return _error(
                _ERROR_MISSING_ARGUMENT,
                "missing required argument: category",
            )
        try:
            components = catalog.find_components(category=category)
        except catalog.UnknownCategoryError:
            return _unknown_category_error(category)
        return {"count": len(components), "components": components}

    @server.tool()
    def list_categories() -> dict:
        """List the closed category vocabulary with component counts.

        The order is stable and every category appears exactly once.
        """
        return {"categories": catalog.category_counts()}

    @server.tool()
    def list_public_components() -> dict:
        """List only public components that carry verified repository links.

        These are the repositories a user can actually clone today.
        """
        components = [c for c in catalog.list_components() if c["public"]]
        return {"count": len(components), "components": components}

    @server.tool()
    def list_private_components() -> dict:
        """List private components (names only — no repo, no description claims).

        Private entries make no public claims: no repo URL and no
        description, by design.
        """
        components = [c for c in catalog.list_components() if not c["public"]]
        return {
            "count": len(components),
            "notice": (
                "Private components are not yet published; they make no "
                "public claims: no repository URL, no description."
            ),
            "components": components,
        }

    @server.tool()
    def search_components(query: str | None = None) -> dict:
        """Search components by substring across name, category, tags, and verified descriptions.

        Matching is case-insensitive. A missing query is returned as a
        typed missing_argument refusal; an empty result is reported as
        count 0, not an error. (The argument is declared optional so
        the refusal reaches the client as a payload instead of a
        framework-level validation crash.)
        """
        if not query or not query.strip():
            return _error(
                _ERROR_MISSING_ARGUMENT,
                "missing required argument: query (a non-empty substring)",
            )
        matches = catalog.search_components(query)
        return {"query": query, "count": len(matches), "components": matches}

    @server.tool()
    def get_ecosystem_overview() -> dict:
        """Get the ecosystem at a glance: counts, principle, and package facts.

        Headline counts, the ecosystem principle, the category map, and
        the package facts a new user needs before anything else.
        """
        c = catalog.counts()
        return {
            "ecosystem": "plat",
            "principle": tools.PRINCIPLE,
            "package": "platworks",
            "version": __version__,
            "counts": c,
            "categories": catalog.category_counts(),
            "public_components": [
                c_["name"] for c_ in catalog.list_components() if c_["public"]
            ],
            "private_components": [
                c_["name"]
                for c_ in catalog.list_components()
                if not c_["public"]
            ],
            "mcp_tools": list(tools.TOOL_NAMES),
            "synthetic_data_only": True,
        }

    @server.tool()
    def get_install_instructions() -> dict:
        """Get install commands and the MCP client config for wiring platworks in.

        Copy-pasteable: a pip install line and the mcpServers JSON for
        any MCP-capable editor or client.
        """
        return {
            "install": "pip install platworks",
            "console_scripts": ["platworks", "platworks-mcp"],
            "mcp_client_config": _INSTALL_SNIPPET,
            "cli_quickstart": [
                "platworks catalog",
                "platworks get plat-harness",
                "platworks demo",
                "platworks landing",
                "platworks mcp",
            ],
        }

    @server.tool()
    def get_demo_portfolio() -> dict:
        """Get the synthetic demo portfolio (fabricated data, clearly labeled).

        The portfolio demonstrates how the ecosystem components compose
        per asset. All data is synthetic; the payload says so.
        """
        return dict(demo_module.synthetic_portfolio())

    @server.tool()
    def get_landing_page() -> dict:
        """Get the standalone product landing page as HTML (self-contained, no external assets).

        The HTML renders from the same verified catalog as every other
        tool: inline CSS, no CDN, no scripts, no tracking.
        """
        return {
            "filename": "landing.html",
            "generator": "platworks landing <output-path>",
            "html": landing_page.build_html(),
        }

    # --------------------------------------------------- 8 product tools
    # Real deterministic tool bodies wrapping the engine, costmodel, and
    # harness services. Every financial number in a response is exactly
    # what the wrapped service returned; every response carries a
    # provenance record; every failure is a typed payload refusal.

    @server.tool()
    def underwrite_run(inputs: object = None) -> dict:
        """Run the deterministic underwriting engine on a canonical
        deal; certified metrics come from the engine, never a model.

        Pass the full canonical deal inputs (engine schema v0.1) —
        cohorts, market rent curves, opex table, purchase/debt/exit/fund
        assumptions, and a property tax policy. Returns the engine's own
        certified metrics (NOI, CoC, DSCR, IRR, equity multiple, yields)
        verbatim, with the engine version on every response. A canonical
        missing its tax policy is refused typed — the engine never guesses.
        (The argument is declared optional so a missing-input refusal
        reaches the client as a payload instead of a validation crash.)
        """
        return wrappers.call_product_tool("underwrite_run", {"inputs": inputs})

    @server.tool()
    def underwrite_backsolve(inputs: object = None,
                             target_coc_pct: float | None = None,
                             year_built: int | None = None,
                             benchmark_5yr_treasury_pct: float = 3.91,
                             agency_spread_pct: float = 1.5,
                             min_price: float = 1000000,
                             max_price: float = 100000000,
                             max_iterations: int = 40) -> dict:
        """Backsolve the highest price meeting a target Year-1
        post-debt cash-on-cash return, via the engine's own search.

        The engine re-prices debt, tax, and equity for every candidate
        price (bisection over full underwriting runs); the response
        reports the solved price, the achieved CoC, the iteration count,
        and the solved case's engine metrics. No price outside a proven
        bracket is ever returned. (The core arguments are declared
        optional so missing-input refusals reach the client as payloads
        instead of validation crashes.)
        """
        return wrappers.call_product_tool("underwrite_backsolve", {
            "inputs": inputs, "target_coc_pct": target_coc_pct,
            "year_built": year_built,
            "benchmark_5yr_treasury_pct": benchmark_5yr_treasury_pct,
            "agency_spread_pct": agency_spread_pct,
            "min_price": min_price, "max_price": max_price,
            "max_iterations": max_iterations,
        })

    @server.tool()
    def tax_regime_lookup(state: str | None = None, tax_year: int | None = None,
                          unit_count: int | None = None,
                          just_value: str | None = None,
                          prior_assessed_value: str | None = None,
                          ownership_change_or_qualifying_improvement:
                          bool | None = None,
                          non_school_millage: str | None = None,
                          school_millage: str | None = None) -> dict:
        """Researched, statute-cited property-tax regime schedule
        for one supported state (TX CA FL AL); unknown states refuse.

        Returns the regime's assessed-value computation and levy
        components as decimal strings, every statute citation, and
        requires_competent_human_review=true — statutory research is
        research, not law. Unknown jurisdictions refuse typed rather
        than shipping a plausible default. (The argument is declared
        optional so a missing-state refusal reaches the client as a
        payload instead of a validation crash.)
        """
        scenario = {
            "tax_year": tax_year, "unit_count": unit_count,
            "just_value": just_value,
            "prior_assessed_value": prior_assessed_value,
            "ownership_change_or_qualifying_improvement":
                ownership_change_or_qualifying_improvement,
            "non_school_millage": non_school_millage,
            "school_millage": school_millage,
        }
        scenario = {k: v for k, v in scenario.items() if v is not None}
        return wrappers.call_product_tool(
            "tax_regime_lookup", {"state": state, **scenario})

    @server.tool()
    def renovation_estimate(unit_sqft: float | None = None,
                            bedrooms: int | None = None,
                            bathrooms: float | None = None,
                            scope_level: str | None = None,
                            finish_tier: str = "basic",
                            year_built: int | None = None,
                            property_class: str | None = None,
                            market: str | None = None,
                            unit_id: str = "") -> dict:
        """Per-unit renovation cost ranges (low/high) with line
        items and age-based risk flags, from the costmodel KB.

        The costmodel's own knowledge base produces low/high ranges per
        line item (paint, flooring, cabinets, appliances, …) scaled by
        unit size and finish tier; a 1978-or-older build carries lead
        paint / asbestos / galvanized pipe risk flags. The estimate is a
        range, never a single invented number. (The core arguments are
        declared optional so missing-input refusals reach the client as
        payloads instead of validation crashes.)
        """
        return wrappers.call_product_tool("renovation_estimate", {
            "unit_sqft": unit_sqft, "bedrooms": bedrooms,
            "bathrooms": bathrooms, "scope_level": scope_level,
            "finish_tier": finish_tier, "year_built": year_built,
            "property_class": property_class, "market": market,
            "unit_id": unit_id,
        })

    @server.tool()
    def renovation_roi(total_cost_high: float | None = None,
                       current_monthly_rent: float | None = None,
                       target_monthly_rent: float | None = None,
                       threshold_pct: float | None = None) -> dict:
        """Check whether a renovation's rent lift clears
        the minimum ROI threshold (conservative: high cost).

        Always tests the HIGH end of the cost range: ROI = (annual rent
        lift / total cost high) x 100 against the 15% default gate. On a
        failure the result explains by how much it missed; it never
        silently rounds a miss into a pass. (The core arguments are
        declared optional so missing-input refusals reach the client as
        payloads instead of validation crashes.)
        """
        return wrappers.call_product_tool("renovation_roi", {
            "total_cost_high": total_cost_high,
            "current_monthly_rent": current_monthly_rent,
            "target_monthly_rent": target_monthly_rent,
            "threshold_pct": threshold_pct,
        })

    @server.tool()
    def generate_sow(unit_sqft: float | None = None,
                     bedrooms: int | None = None,
                     bathrooms: float | None = None,
                     scope_level: str | None = None,
                     finish_tier: str = "basic",
                     property_address: str = "", unit_id: str = "") -> dict:
        """Contractor-ready scope of work with material
        specs and quality standards for a unit renovation.

        Produces line items with material specifications, quantity notes,
        and quality standards plus general conditions (permits, cleanup,
        warranty) — the document to hand a bidding contractor, generated
        deterministically from the same knowledge base as the estimate.
        (The core arguments are declared optional so missing-input
        refusals reach the client as payloads instead of validation
        crashes.)
        """
        return wrappers.call_product_tool("generate_sow", {
            "unit_sqft": unit_sqft, "bedrooms": bedrooms,
            "bathrooms": bathrooms, "scope_level": scope_level,
            "finish_tier": finish_tier,
            "property_address": property_address, "unit_id": unit_id,
        })

    @server.tool()
    def evaluate_bid(bid: object = None,
                     estimate: object = None) -> dict:
        """Evaluate a contractor bid against the internal
        estimate; flags inflated, vague, and timeline risks.

        Line items 30%+ above the internal high estimate flag inflated;
        unmatched descriptions flag vague; short timelines flag
        change-order risk. The overall assessment (reasonable / concerns
        / reject) is the costmodel's deterministic verdict. (The
        arguments are declared optional so missing-input refusals reach
        the client as payloads instead of validation crashes.)
        """
        return wrappers.call_product_tool("evaluate_bid", {
            "bid": bid, "estimate": estimate,
        })

    @server.tool()
    def ops_review(asset_id: str | None = None, period: str | None = None,
                   materiality: object = None,
                   as_of_date: str | None = None, db_path: str | None = None,
                   variance_oracle_callable=None) -> dict:
        """Read-only review of one property and one period:
        occupancy, typed exceptions, oracle-bound variance only.

        The harness review reports occupancy change, feed freshness, and
        typed material exceptions with evidence citations. Missing budget
        is a blocker, never zero; without a bound variance oracle the
        review returns an honest VARIANCE_NOT_IMPLEMENTED blocked
        status, never a fabricated variance. Refuses wildcard or
        aggregate asset ids structurally. (The core arguments are
        declared optional so missing-input refusals reach the client as
        payloads instead of validation crashes.)
        """
        return wrappers.call_product_tool("ops_review", {
            "asset_id": asset_id, "period": period,
            "materiality": materiality, "as_of_date": as_of_date,
            "db_path": db_path,
            "variance_oracle_callable": variance_oracle_callable,
        })

    return server


def main():
    """Run the platworks MCP server over stdio (console entrypoint)."""
    build_server().run("stdio")


if __name__ == "__main__":
    main()