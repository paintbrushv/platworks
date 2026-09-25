"""Tests for the 8 platworks PRODUCT tools (``platworks.wrappers``).

Each tool wraps a real deterministic service from the plat ecosystem —
the underwriting engine, its tax-regime schedule builder, its backsolve
core, the costmodel services, and the harness ops review — and returns
JSON-serializable dicts. The contract under test:

- **Provenance on every response**: each tool result carries a
  ``provenance`` object naming the wrapped service and its contract
  version, plus ``engine-owned`` arithmetic notes where relevant.
- **Typed refusals, never tracebacks**: failures come back as
  ``{"error": {"code": ..., "message": ..., "hint": ...}}`` payloads.
- **Numbers are the service's numbers**: no wrapper arithmetic over
  financial values anywhere (money strings pass through verbatim).
- **Synthetic fixtures only**: the canonical deal input, the FL tax
  scenario, the costmodel example, and the harness sample snapshot are
  all synthetic (the snapshot ships in the public harness tree).

Import boundary: the wrappers import the sibling services lazily inside
each call so that importing ``platworks.wrappers`` (and hence the MCP
server) never requires the engine/costmodel/harness packages to be
installed until a product tool is actually invoked.
"""

import asyncio
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Synthetic ground-truth fixtures (schema-compliant engine canonical v0.1,
# mirrored from plat-multifamily-underwriting tests/conftest.py
# minimal_deal_inputs — the engine's own working invocation shape).
# ---------------------------------------------------------------------------

START = "2026-07"
END = "2031-06"

SYNTHETIC_CANONICAL = {
    "schema_version": "0.1",
    "metadata": {
        "deal_id": "PW-SYN-001",
        "run_id": "pw-test-001",
        "as_of_date": "2026-04-16",
        "analyst": "Synthetic Test",
        "purpose": "platworks product-tool fixture",
        "property_summary": {
            "property_tax_policy": {
                "millage_rate_mills": 25.0,
                "assessment_ratio": 1.0,
                "source": "analyst",
                "source_locator": "tests:minimum_deal_inputs",
                "analyst_override": False,
            }
        },
    },
    "time_grid": {"analysis_start_date": START, "analysis_end_date": END},
    "unit_cohorts": [
        {"cohort_id": "1BR", "unit_type": "1BR", "unit_count": 50,
         "initial_inplace_rent": 1200},
        {"cohort_id": "2BR", "unit_type": "2BR", "unit_count": 50,
         "initial_inplace_rent": 1500},
    ],
    "market_rent_curve": [
        {"cohort_id": "1BR", "start_period": START, "end_period": END,
         "market_rent": 1250},
        {"cohort_id": "2BR", "start_period": START, "end_period": END,
         "market_rent": 1550},
    ],
    "loss_to_lease": [
        {"cohort_id": "1BR", "start_period": START, "end_period": END,
         "ltl_percent": 0.03},
        {"cohort_id": "2BR", "start_period": START, "end_period": END,
         "ltl_percent": 0.03},
    ],
    "physical_vacancy_curve": [
        {"cohort_id": "1BR", "start_period": START, "end_period": END,
         "vacancy_rate": 0.05},
        {"cohort_id": "2BR", "start_period": START, "end_period": END,
         "vacancy_rate": 0.05},
    ],
    "collection_loss_curve": [
        {"applies_to": "ALL", "start_period": START, "end_period": END,
         "loss_rate": 0.01},
    ],
    "revenue_programs": [
        {
            "program_id": "RUBS",
            "program_name": "RUBS Utility Recovery",
            "program_type": "recovery",
            "pricing_type": "$/unit",
            "price_value": 50,
            "eligible_units": "ALL",
            "start_period": START,
        },
    ],
    "program_adoption_curve": [
        {"program_id": "RUBS", "start_period": START, "end_period": END,
         "adoption_rate": 0.90},
    ],
    "utility_recovery_rules": [
        {
            "utility_category": "ALL",
            "recovery_basis": "percent_of_expense",
            "recovery_rate": 1.0,
            "lag_months": 0,
        }
    ],
    "opex_table": [
        {"category_name": "Real Estate Taxes", "calculation_type": "fixed_annual",
         "base_value": 337500, "growth_rate": 0.02, "recoverable_flag": False},
        {"category_name": "Insurance", "calculation_type": "fixed_annual",
         "base_value": 60000, "growth_rate": 0.03, "recoverable_flag": False},
        {"category_name": "R&M", "calculation_type": "per_unit",
         "base_value": 750, "growth_rate": 0.03, "recoverable_flag": False},
        {"category_name": "Management Fee", "calculation_type": "percent_egr",
         "base_value": 0.04, "growth_rate": 0.0, "recoverable_flag": False},
        {"category_name": "Utilities", "calculation_type": "per_unit_monthly",
         "base_value": 85, "growth_rate": 0.03, "recoverable_flag": True},
    ],
    "purchase_assumptions": {
        "purchase_price": 13500000,
        "closing_costs": 150000,
        "equity_contribution": 4725000,
        "total_equity_basis": 4875000,
    },
    "debt_terms": {
        "commitment": 8775000,
        "rate": 0.0575,
        "amort_years": 30,
        "io_months": 12,
    },
    "exit_assumptions": {
        "exit_cap_rate": 0.055,
        "sale_cost_percent": 0.02,
        "exit_month": END,
    },
    "fund_assumptions": {
        "sponsor_equity_pct": 0.05,
        "lp_equity_pct": 0.95,
        "preferred_return": 0.08,
        "acquisition_fee_pct": 0.01,
        "asset_management_fee_pct": 0.01,
        "disposition_fee_pct": 0.01,
        "annual_partnership_expenses": 25000,
        "partnership_closing_costs": 50000,
        "promote_splits": [
            {"tier": "Pref", "hurdle_irr": 0.08, "lp_share": 1.0, "gp_share": 0.0},
            {"tier": "Promote", "hurdle_irr": 0.0, "lp_share": 0.70,
             "gp_share": 0.30},
        ],
    },
    "growth_assumptions": {
        "growth_type": "annual_compound",
        "annual_growth_rate": 0.03,
    },
    "replacement_reserves": [
        {"start_period": START, "end_period": END, "annual_amount": 25000},
    ],
}

# FL tax-regime scenario mirrored from the engine's own test suite
# (test_tax_regimes.py _fl_inputs; expected values computed independently
# with Decimal arithmetic by the parent: non-school 244200.00 on the capped
# 13.2M value, school 116145.00 on just value).
FL_TAX_INPUTS = {
    "state": "FL",
    "tax_year": 2026,
    "unit_count": 220,
    "just_value": "15000000",
    "prior_assessed_value": "12000000",
    "ownership_change_or_qualifying_improvement": False,
    "non_school_millage": "18.5",
    "school_millage": "7.7430",
}

# Costmodel example verified by the parent: 16.0% ROI vs the 15% gate.
COSTMODEL_UNIT = {
    "unit_sqft": 850,
    "bedrooms": 2,
    "bathrooms": 1,
    "scope_level": "standard_value_add",
    "finish_tier": "basic",
    "year_built": 1978,
    "property_class": "C",
    "market": "dallas",
    "unit_id": "PW-SYN-101",
}


def _run(coro):
    return asyncio.run(coro)


def _payload(result):
    assert result.content, "tool returned no content"
    return json.loads(result.content[0].text)


def _server():
    from platworks.mcp_server import build_server

    return build_server()


def _call(tool, args):
    return _payload(_run(_server().call_tool(tool, args)))


def _assert_no_error(payload):
    assert "error" not in payload, f"unexpected refusal: {payload['error']}"
    return payload


def _assert_error(payload, code):
    assert "error" in payload, f"expected typed refusal, got: {payload}"
    assert payload["error"]["code"] == code, payload["error"]
    assert payload["error"]["message"], "refusal message must be actionable"
    assert payload["error"].get("hint"), "refusal must carry a hint"
    return payload


# ------------------------------------------------- module + registry wiring

def test_wrappers_module_exposes_eight_product_tools():
    from platworks import wrappers

    expected = {
        "underwrite_run", "underwrite_backsolve", "tax_regime_lookup",
        "renovation_estimate", "renovation_roi", "generate_sow",
        "evaluate_bid", "ops_review",
    }
    assert wrappers.PRODUCT_TOOL_NAMES == expected
    assert len(wrappers.PRODUCT_TOOL_SPECS) == 8
    # every product tool name is distinct from the catalog tools
    from platworks import tools

    assert not (expected & set(tools.TOOL_NAMES))


def test_registry_and_server_agree_on_nineteen_tools():
    from platworks import tools, wrappers

    assert tools.TOOL_COUNT == 11
    assert len(wrappers.PRODUCT_TOOL_NAMES) == 8
    registered = _run(_server().list_tools())
    names = {t.name for t in registered}
    assert names == set(tools.TOOL_NAMES) | wrappers.PRODUCT_TOOL_NAMES
    assert len(registered) == len(names) == 19


def test_product_tool_purposes_surface_in_descriptions():
    """Product-tool docstrings open with their registry purpose, so the
    description an MCP client sees and the wrappers' declared purposes
    cannot drift (mirrors the catalog drift gate)."""
    from platworks import wrappers

    registered = {
        t.name: (t.description or "") for t in _run(_server().list_tools())
    }
    for name, purpose in wrappers.PRODUCT_TOOL_SPECS:
        assert name in registered, name
        # the description is docstring-derived; the purpose's first chunk
        # must appear in it (docstrings may wrap across lines)
        flattened = " ".join(registered[name].split())
        assert purpose[:25] in flattened, (
            f"tool {name} description does not carry its registry purpose"
        )


def test_product_tools_are_importable_without_sibling_packages():
    """Importing wrappers must not require engine/costmodel/harness.

    The sibling services are imported lazily inside each tool call, so
    ``import platworks.wrappers`` succeeds on a bare install (the catalog
    server keeps working without the product backends).
    """
    import subprocess

    probe = (
        "import sys\n"
        "blocked = ('engine', 'plat_costmodel', 'plat_harness')\n"
        "for name in blocked:\n"
        "    sys.modules[name] = None\n"
        "import platworks.wrappers as w\n"
        "assert len(w.PRODUCT_TOOL_NAMES) == 8\n"
        "print('lazy-import-ok')\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(REPO_ROOT, "src")
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe],
        capture_output=True, text=True, env=env, cwd="/tmp",
    )
    assert result.returncode == 0, result.stderr
    assert "lazy-import-ok" in result.stdout


# ------------------------------------------------------------- underwrite_run

def test_underwrite_run_returns_engine_numbers_with_provenance():
    payload = _assert_no_error(_call("underwrite_run", {"inputs": SYNTHETIC_CANONICAL}))
    # the engine's own numbers, passed through verbatim
    assert payload["metrics"]["coc"]["cash_on_cash_year_1"] == pytest.approx(0.0917)
    assert payload["metrics"]["noi"]["year_1_noi"] == pytest.approx(1050154.8)
    assert payload["engine_version"], "engine version must be reported"
    prov = payload["provenance"]
    assert prov["service"] == "plat-multifamily-underwriting"
    assert prov["entrypoint"] == "engine.engine.run_underwriting"
    assert prov["engine_version"] == payload["engine_version"]


def test_underwrite_run_without_tax_policy_is_typed_refusal():
    """The engine refuses a canonical without property_tax_policy —
    that refusal must reach the client typed, not as a traceback."""
    inputs = json.loads(json.dumps(SYNTHETIC_CANONICAL))
    del inputs["metadata"]["property_summary"]["property_tax_policy"]
    payload = _assert_error(_call("underwrite_run", {"inputs": inputs}), "ENGINE_REFUSAL")
    assert "millage" in payload["error"]["message"].lower() or \
           "tax" in payload["error"]["message"].lower()


def test_underwrite_run_non_dict_inputs_is_typed_refusal():
    _assert_error(_call("underwrite_run", {"inputs": "not-a-dict"}),
                  "INVALID_INPUT")
    _assert_error(_call("underwrite_run", {"inputs": None}), "INVALID_INPUT")


# -------------------------------------------------------- underwrite_backsolve

def test_backsolve_finds_price_meeting_target_coc():
    args = {
        "inputs": SYNTHETIC_CANONICAL,
        "target_coc_pct": 7.0,
        "year_built": 1984,
        "benchmark_5yr_treasury_pct": 3.91,
        "agency_spread_pct": 1.5,
        "max_iterations": 14,
    }
    payload = _assert_no_error(_call("underwrite_backsolve", args))
    assert payload["solved_price"] > 0
    assert payload["achieved_coc_pct"] >= 7.0
    assert payload["iterations_run"] >= 1
    # the engine ran inside the solved case: metrics present, verbatim
    assert "metrics" in payload["case_results"]
    prov = payload["provenance"]
    assert prov["service"] == "plat-multifamily-underwriting"
    assert "backsolve" in prov["entrypoint"]


def test_backsolve_missing_tax_policy_is_typed_refusal():
    inputs = json.loads(json.dumps(SYNTHETIC_CANONICAL))
    del inputs["metadata"]["property_summary"]["property_tax_policy"]
    _assert_error(
        _call("underwrite_backsolve", {"inputs": inputs, "target_coc_pct": 7.0}),
        "ENGINE_REFUSAL",
    )


def test_backsolve_invalid_target_coc_is_typed_refusal():
    _assert_error(
        _call("underwrite_backsolve",
              {"inputs": SYNTHETIC_CANONICAL, "target_coc_pct": 0}),
        "INVALID_INPUT",
    )


# --------------------------------------------------------- tax_regime_lookup

def test_tax_regime_lookup_fl_returns_researched_schedule():
    payload = _assert_no_error(_call("tax_regime_lookup", FL_TAX_INPUTS))
    assert payload["contract_version"] == "engine-tax-regimes/1.0.0"
    assert payload["regime_id"] == "fl_nonhomestead_10pct_cap"
    # expected values computed independently with Decimal by the parent:
    # capped 13.2M x 18.5/1000 = 244200.00; school 15M x 7.7430/1000 = 116145.00
    levies = {c["basis"]: c["tax"] for c in payload["levy_components"]}
    assert levies["capped_non_school"] == 244200.0
    assert levies["just_value_school"] == 116145.0
    assert payload["annual_total_tax"] == 360345.0
    assert payload["citations"], "statute citations must be present"
    assert payload["requires_competent_human_review"] is True
    prov = payload["provenance"]
    assert prov["service"] == "plat-multifamily-underwriting"
    assert prov["entrypoint"] == "engine.tax_regimes.build_tax_regime_schedule"


def test_tax_regime_lookup_unsupported_state_is_typed_refusal():
    inputs = dict(FL_TAX_INPUTS, state="NY")
    payload = _assert_error(_call("tax_regime_lookup", inputs), "UNSUPPORTED_TAX_REGIME")
    # the refusal names the supported regimes in the hint
    for regime in ("FL", "TX"):
        assert regime in payload["error"]["message"] or \
               regime in payload["error"]["hint"]


def test_tax_regime_lookup_missing_state_is_typed_refusal():
    _assert_error(_call("tax_regime_lookup", {"tax_year": 2026}),
                            "MISSING_INPUT")


# -------------------------------------------------------- renovation_estimate

def test_renovation_estimate_returns_costmodel_numbers():
    payload = _assert_no_error(_call("renovation_estimate", COSTMODEL_UNIT))
    assert payload["total_low"] == 8970.0
    assert payload["total_high"] == 12880.0
    assert len(payload["line_items"]) == 6
    assert payload["risk_flags"], "1978 build must carry risk flags"
    assert payload["size_category"] == "medium"
    prov = payload["provenance"]
    assert prov["service"] == "plat-costmodel"
    assert prov["entrypoint"] == "plat_costmodel.estimator.estimate_unit"


def test_renovation_estimate_invalid_sqft_is_typed_refusal():
    _assert_error(
        _call("renovation_estimate", dict(COSTMODEL_UNIT, unit_sqft=-5)),
        "INVALID_INPUT",
    )
    _assert_error(
        _call("renovation_estimate", dict(COSTMODEL_UNIT, unit_sqft=0)),
        "INVALID_INPUT",
    )


def test_renovation_estimate_invalid_scope_is_typed_refusal():
    _assert_error(
        _call("renovation_estimate",
              dict(COSTMODEL_UNIT, scope_level="bogus_scope")),
        "INVALID_INPUT",
    )


# ------------------------------------------------------------ renovation_roi

def test_renovation_roi_sixteen_pct_clears_fifteen_pct_gate():
    payload = _assert_no_error(_call("renovation_roi", {
        "total_cost_high": 15000,
        "current_monthly_rent": 850,
        "target_monthly_rent": 1050,
    }))
    assert payload["roi_pct"] == 16.0
    assert payload["threshold_pct"] == 15.0
    assert payload["clears_threshold"] is True
    assert payload["monthly_rent_lift"] == 200
    assert payload["annual_rent_lift"] == 2400
    prov = payload["provenance"]
    assert prov["service"] == "plat-costmodel"
    assert prov["entrypoint"] == "plat_costmodel.roi.check_roi"


def test_renovation_roi_below_gate_reports_failure_with_path():
    payload = _assert_no_error(_call("renovation_roi", {
        "total_cost_high": 30000,
        "current_monthly_rent": 850,
        "target_monthly_rent": 1050,
    }))
    assert payload["clears_threshold"] is False
    assert payload["roi_pct"] < payload["threshold_pct"]


def test_renovation_roi_zero_cost_is_typed_refusal():
    _assert_error(
        _call("renovation_roi", {"total_cost_high": 0,
                                 "current_monthly_rent": 850,
                                 "target_monthly_rent": 1050}),
        "INVALID_INPUT",
    )


def test_renovation_roi_lift_must_be_positive():
    _assert_error(
        _call("renovation_roi", {"total_cost_high": 15000,
                                 "current_monthly_rent": 1050,
                                 "target_monthly_rent": 850}),
        "INVALID_INPUT",
    )


# --------------------------------------------------------------- generate_sow

def test_generate_sow_produces_contractor_document():
    payload = _assert_no_error(_call("generate_sow", {
        "unit_sqft": 850, "bedrooms": 2, "bathrooms": 1,
        "scope_level": "standard_value_add", "finish_tier": "basic",
        "property_address": "123 Synthetic Way, Dallas, TX",
        "unit_id": "PW-SYN-101",
    }))
    assert len(payload["line_items"]) >= 5
    assert "Contractor responsible" in payload["general_conditions"]
    assert payload["unit_id"] == "PW-SYN-101"
    for item in payload["line_items"]:
        assert item["category"]
        assert item["material_spec"] or item["description"]
    prov = payload["provenance"]
    assert prov["service"] == "plat-costmodel"
    assert prov["entrypoint"] == "plat_costmodel.sow.generate_sow"


def test_generate_sow_invalid_scope_is_typed_refusal():
    _assert_error(
        _call("generate_sow", {"unit_sqft": 850, "bedrooms": 2, "bathrooms": 1,
                               "scope_level": "mansion_gut"}),
        "INVALID_INPUT",
    )


# --------------------------------------------------------------- evaluate_bid

def test_evaluate_bid_flags_mismatched_contractor_bid():
    # internal estimate for the ground-truth unit, then a synthetic bid
    estimate = dict(COSTMODEL_UNIT)
    estimate_args = {"estimate": estimate}
    bid = {
        "contractor_name": "Synthetic Contracting LLC",
        "line_items": [
            {"description": "Replace all LVP flooring throughout unit", "amount": 9000},
            {"description": "Miscellaneous allowance", "amount": 600},
        ],
        "total": 9600,
        "timeline_days": 14,
    }
    payload = _assert_no_error(_call("evaluate_bid", {"bid": bid, **estimate_args}))
    assert payload["overall_assessment"] in ("reasonable", "concerns", "reject")
    assert payload["bid_total"] == 9600
    assert payload["internal_estimate_high"] == 12880.0
    assert payload["flags"], "the vague allowance line must be flagged"
    prov = payload["provenance"]
    assert prov["service"] == "plat-costmodel"
    assert prov["entrypoint"] == "plat_costmodel.bid_eval.evaluate_bid"


def test_evaluate_bid_missing_bid_is_typed_refusal():
    _assert_error(_call("evaluate_bid", {}), "MISSING_INPUT")
    _assert_error(_call("evaluate_bid", {"bid": None}), "MISSING_INPUT")


# ------------------------------------------------------------------ ops_review

def _ops_snapshot_path():
    """Locate the harness tree's synthetic walkthrough sample snapshot."""
    import plat_harness

    harness_file = os.path.abspath(plat_harness.__file__)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(harness_file))))
    path = os.path.join(repo_root, "samples", "walkthrough", "ops_snapshot.sqlite")
    if not os.path.exists(path):
        pytest.skip("harness sample snapshot not installed with this layout")
    return path


def test_ops_review_over_synthetic_snapshot():
    payload = _assert_no_error(_call("ops_review", {
        "asset_id": "synthetic_ops",
        "period": "2026-04",
        "materiality": {"variance_abs": "500.00", "currency": "USD"},
        "as_of_date": "2026-04-30",
        "db_path": _ops_snapshot_path(),
    }))
    assert payload["asset_id"] == "synthetic_ops"
    assert payload["period"] == "2026-04"
    assert payload["scope"]["properties_reviewed"] == 1
    assert payload["scope"]["periods_reviewed"] == 1
    # no variance oracle bound -> honest blocked review, never fabricated
    assert payload["status"] == "blocked"
    codes = [rec["code"] for rec in payload["exceptions"]]
    assert "VARIANCE_NOT_IMPLEMENTED" in codes
    prov = payload["provenance"]
    assert prov["service"] == "plat-harness"
    assert prov["entrypoint"] == "plat_harness.adapters.ops_review.review_period"
    assert prov["contract_version"] == "ops-review/1.0.0"


def test_ops_review_with_oracle_bound_reports_variance():
    """When the caller binds the pinned boxscore::variance oracle, the
    review reports real variance numbers (still verbatim from the seam)."""
    import decimal

    D = decimal.Decimal
    REVENUE = frozenset({"rental income", "concessions", "bad debt",
                         "other income"})
    UNMAPPED = frozenset({"unmapped"})

    def oracle(actuals, budgets):
        totals = {}
        for rows, idx in ((actuals, 0), (budgets, 1)):
            for row in rows:
                key = (row["account_code"], row["account_name"], row["category"])
                totals.setdefault(key, [D("0"), D("0")])[idx] += D(row["amount"])
        by_account = []
        rev_a = rev_b = exp_a = exp_b = unm_a = unm_b = D("0")
        for (code, name, category), (a, b) in sorted(totals.items()):
            by_account.append({
                "account_code": code, "account_name": name,
                "category": category, "actual": f"{a:.2f}",
                "budget": f"{b:.2f}", "variance": f"{a - b:.2f}"})
            if category in REVENUE:
                rev_a += a
                rev_b += b
            elif category in UNMAPPED:
                unm_a += a
                unm_b += b
            else:
                exp_a += a
                exp_b += b
        bridge = {
            "actual_revenue": f"{rev_a:.2f}", "budget_revenue": f"{rev_b:.2f}",
            "revenue_variance": f"{rev_a - rev_b:.2f}",
            "actual_expenses": f"{exp_a:.2f}", "budget_expenses": f"{exp_b:.2f}",
            "expense_variance": f"{exp_a - exp_b:.2f}",
            "actual_noi": f"{rev_a - exp_a:.2f}",
            "budget_noi": f"{rev_b - exp_b:.2f}",
            "noi_variance": f"{(rev_a - exp_a) - (rev_b - exp_b):.2f}",
            "unmapped_actual": f"{unm_a:.2f}", "unmapped_budget": f"{unm_b:.2f}",
        }
        return {"by_account": by_account, "noi_bridge": bridge}

    payload = _assert_no_error(_call("ops_review", {
        "asset_id": "synthetic_ops",
        "period": "2026-04",
        "materiality": {"variance_abs": "500.00", "currency": "USD"},
        "as_of_date": "2026-04-30",
        "db_path": _ops_snapshot_path(),
        "variance_oracle_callable": oracle,
    }))
    assert payload["status"] == "reviewed"
    variance = payload["variance"]
    assert variance["noi_bridge"]["actual_noi"]
    assert variance["oracle_owner"] == "boxscore::variance"


def test_ops_review_wildcard_asset_is_typed_refusal():
    _assert_error(_call("ops_review", {
        "asset_id": "*",
        "period": "2026-04",
        "materiality": {"variance_abs": "500.00", "currency": "USD"},
        "db_path": _ops_snapshot_path(),
    }), "INVALID_INPUT")


def test_ops_review_missing_period_is_typed_refusal():
    _assert_error(_call("ops_review", {
        "asset_id": "synthetic_ops",
        "materiality": {"variance_abs": "500.00", "currency": "USD"},
        "db_path": _ops_snapshot_path(),
    }), "MISSING_INPUT")


# ------------------------------------------------------- no private data leaks

def test_product_tool_payloads_carry_no_private_paths():
    """Product tool responses must never leak host paths or campaign dirs —
    the ops snapshot path the caller supplies is echoed only as a resolved
    opaque property key, never verbatim."""
    payload = _assert_no_error(_call("ops_review", {
        "asset_id": "synthetic_ops",
        "period": "2026-04",
        "materiality": {"variance_abs": "500.00", "currency": "USD"},
        "as_of_date": "2026-04-30",
        "db_path": _ops_snapshot_path(),
    }))
    blob = json.dumps(payload)
    assert "/home/" not in blob
    assert "uplift" not in blob
    assert "PRIVATE_CANARY" not in blob


# --------------------------------------------------- stdio end-to-end (slow)

@pytest.mark.slow
def test_stdio_end_to_end_product_tools():
    """Drive underwrite_run + tax_regime_lookup + renovation_roi through a
    real MCP stdio client session — the product surface, not just in-proc."""
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-B", "-c",
                  "import sys; sys.path.insert(0, %r); "
                  "from platworks.mcp_server import main; main()"
                  % os.path.join(REPO_ROOT, "src")],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {t.name for t in listed.tools}
                assert len(names) == 19
                assert "underwrite_run" in names
                assert "tax_regime_lookup" in names
                assert "renovation_roi" in names

                res = await session.call_tool(
                    "underwrite_run", {"inputs": SYNTHETIC_CANONICAL})
                data = json.loads(res.content[0].text)
                assert "error" not in data
                assert data["metrics"]["noi"]["year_1_noi"] == pytest.approx(1050154.8)

                res = await session.call_tool("tax_regime_lookup", FL_TAX_INPUTS)
                data = json.loads(res.content[0].text)
                assert "error" not in data
                assert data["annual_total_tax"] == 360345.0

                res = await session.call_tool("renovation_roi", {
                    "total_cost_high": 15000,
                    "current_monthly_rent": 850,
                    "target_monthly_rent": 1050,
                })
                data = json.loads(res.content[0].text)
                assert "error" not in data
                assert data["roi_pct"] == 16.0

    anyio.run(scenario)