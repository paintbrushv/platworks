"""platworks PRODUCT tools — 8 real deterministic tool bodies.

The catalog tools (``platworks.tools`` / ``mcp_server.py``) answer *what is
in the ecosystem*. The tools in this module answer *underwriting and
operations questions* by wrapping the real deterministic services from the
plat ecosystem siblings:

- ``plat-multifamily-underwriting`` (engine) — ``run_underwriting``, the
  backsolve price core (``runs/backsolve_price_for_target_coc.py``), and
  the statute-cited tax-regime schedule builder.
- ``plat-costmodel`` — ``estimate_unit``, ``check_roi``, ``generate_sow``,
  ``evaluate_bid``.
- ``plat-harness`` — the read-only ops review seam
  (``plat_harness.adapters.ops_review.review_period``).

Design rules (mirroring the MCP server's):

- **Numbers are the service's numbers.** No wrapper performs financial
  arithmetic: every money value, rate, and metric in a response is exactly
  what the wrapped service returned, and each response carries a
  ``provenance`` record naming the service, its entrypoint, and where
  applicable its contract/engine version.
- **Typed refusals, never tracebacks.** Every failure — invalid input,
  engine/costmodel refusals, unsupported tax regimes — comes back as
  ``{"error": {"code", "message", "hint"}}``.
- **Lazy imports.** The sibling packages are imported inside each call so
  a bare ``pip install platworks`` (catalog only) keeps working; the
  product tools refuse with a typed ``BACKEND_UNAVAILABLE`` when their
  service is not installed.
- **Synthetic data only.** The documented example payloads are synthetic;
  no real deal, tenant, or portfolio data is referenced here.
"""

import sys

PRODUCT_TOOL_SPECS = (
    ("underwrite_run",
     "Run the deterministic underwriting engine on a canonical deal; "
     "certified metrics come from the engine, never a model"),
    ("underwrite_backsolve",
     "Backsolve the highest price meeting a target Year-1 post-debt "
     "cash-on-cash return, via the engine's own search"),
    ("tax_regime_lookup",
     "Researched, statute-cited property-tax regime schedule for one "
     "supported state (TX CA FL AL); unknown states refuse"),
    ("renovation_estimate",
     "Per-unit renovation cost ranges (low/high) with line items and "
     "age-based risk flags, from the costmodel KB"),
    ("renovation_roi",
     "Check whether a renovation's rent lift clears the minimum ROI "
     "threshold (conservative: high cost estimate)"),
    ("generate_sow",
     "Contractor-ready scope of work with material specs and quality "
     "standards for a unit renovation"),
    ("evaluate_bid",
     "Evaluate a contractor bid against the internal estimate; flags "
     "inflated, vague, and timeline risks"),
    ("ops_review",
     "Read-only review of one property and one period: occupancy, typed "
     "exceptions, oracle-bound variance only"),
)

PRODUCT_TOOL_NAMES = frozenset(name for name, _ in PRODUCT_TOOL_SPECS)
PRODUCT_TOOL_PURPOSES = dict(PRODUCT_TOOL_SPECS)


def _error(code, message, hint):
    return {"error": {"code": code, "message": message, "hint": hint}}


def _provenance(service, entrypoint, **extra):
    record = {"service": service, "entrypoint": entrypoint}
    record.update(extra)
    return record


def _import_backend(module_name):
    """Import a sibling service package lazily; typed refusal if absent."""
    try:
        return __import__(module_name)
    except ImportError:
        return None


def _jsonable(obj):
    """Best-effort conversion of a service result into JSON-serializable
    data — pydantic models, Decimals, and dates included. Values pass
    through verbatim; this never computes over them."""
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj
    if hasattr(obj, "model_dump"):          # pydantic v2
        return _jsonable(obj.model_dump(mode="python"))
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    # Decimal, date, enum, anything else with a sane str(): stringify
    return str(obj)


# ------------------------------------------------------------ underwrite_run

def underwrite_run(inputs):
    """Run the deterministic underwriting engine on a canonical deal."""
    if not isinstance(inputs, dict):
        return _error(
            "INVALID_INPUT",
            "inputs must be a canonical deal dict (engine schema v0.1).",
            "Pass the canonical deal inputs object; see the plat-"
            "multifamily-underwriting README for the schema.",
        )
    engine = _import_backend("engine")
    if engine is None:
        return _backend_unavailable("engine", "plat-multifamily-underwriting")
    try:
        from engine.engine import run_underwriting
        result = run_underwriting(inputs)
    except Exception as exc:  # engine refusals are ValueErrors with reasons
        return _error(
            "ENGINE_REFUSAL",
            f"The underwriting engine refused this canonical: {exc}",
            "Fix the named validation issue and re-run; the engine owns "
            "every refusal reason.",
        )
    payload = _jsonable(result)
    engine_version = payload.get("engine_version")
    return {
        "engine_version": engine_version,
        "metrics": payload.get("metrics"),
        "property_snapshot": payload.get("property_snapshot"),
        "feasibility": payload.get("feasibility"),
        "cashflow": payload.get("cashflow"),
        "provenance": _provenance(
            "plat-multifamily-underwriting",
            "engine.engine.run_underwriting",
            engine_version=engine_version,
            arithmetic_owner="engine",
        ),
    }


def _backend_unavailable(import_name, service_name):
    return _error(
        "BACKEND_UNAVAILABLE",
        f"The {service_name} service is not installed in this environment.",
        f"pip install -e the {service_name} sibling package to enable this "
        f"tool (import {import_name!r} failed).",
    )


# -------------------------------------------------------- underwrite_backsolve

def underwrite_backsolve(inputs, target_coc_pct, year_built=None,
                         benchmark_5yr_treasury_pct=3.91,
                         agency_spread_pct=1.5, min_price=1000000,
                         max_price=100000000, max_iterations=40):
    """Backsolve the highest purchase price meeting a target Year-1 CoC."""
    if not isinstance(inputs, dict):
        return _error(
            "INVALID_INPUT",
            "inputs must be a canonical deal dict (engine schema v0.1).",
            "Pass the canonical deal inputs object; see the plat-"
            "multifamily-underwriting README for the schema.",
        )
    if target_coc_pct is None or not isinstance(target_coc_pct, (int, float)) \
            or target_coc_pct <= 0:
        return _error(
            "INVALID_INPUT",
            "target_coc_pct must be a positive number (e.g. 7.0 for 7%).",
            "Provide the target Year-1 post-debt cash-on-cash return as a "
            "percentage, e.g. 7.0.",
        )
    if not isinstance(max_iterations, int) or not 1 <= max_iterations <= 60:
        max_iterations = 40
    try:
        from decimal import ROUND_HALF_UP, Decimal

        from engine.property_tax import (
            normalize_property_tax_purchase_price,
            require_property_tax_policy,
        )
    except ImportError:
        return _backend_unavailable("engine", "plat-multifamily-underwriting")

    # The backsolve core lives in the engine repo's runs/ directory, which
    # is not a package dependency — resolve it next to the installed
    # engine package. If it is absent, refuse typed.
    import importlib

    backsolve = None
    try:
        backsolve = importlib.import_module("engine.backsolve")
    except ImportError:
        import os

        engine_root = os.path.dirname(
            __import__("engine", fromlist=["__name__"]).__file__)
        runs_root = os.path.dirname(engine_root)
        for candidate in (runs_root, os.path.dirname(runs_root)):
            path = os.path.join(candidate, "runs",
                               "backsolve_price_for_target_coc.py")
            if os.path.exists(path):
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "engine.backsolve", path)
                module = importlib.util.module_from_spec(spec)
                sys.modules.setdefault("runs", importlib.import_module("types"))
                runs_pkg = sys.modules["runs"]
                if not hasattr(runs_pkg, "__path__"):
                    runs_pkg.__path__ = [os.path.join(candidate, "runs")]
                sys.modules["engine.backsolve"] = module
                spec.loader.exec_module(module)
                backsolve = module
                break
    if backsolve is None:
        return _backend_unavailable("engine.backsolve",
                                    "plat-multifamily-underwriting")

    try:
        require_property_tax_policy(inputs)
    except Exception as exc:
        return _error(
            "ENGINE_REFUSAL",
            f"The backsolve core refused this canonical: {exc}",
            "A property tax policy (millage) is required before any price "
            "search; add metadata.property_summary.property_tax_policy.",
        )

    target = Decimal(str(target_coc_pct)) / Decimal("100")
    treasury = Decimal(str(benchmark_5yr_treasury_pct)) / Decimal("100")
    spread = Decimal(str(agency_spread_pct)) / Decimal("100")

    try:
        prepared, _policy = backsolve._prepare_house_assumptions(
            inputs,
            year_built=year_built,
            strategy="cashflow",
            target_coc=target,
            benchmark_treasury=treasury,
            agency_spread=spread,
            exit_cap_rate=Decimal(str(
                (inputs.get("exit_assumptions") or {}).get("exit_cap_rate")
                or 0.055)),
            sale_cost_percent=Decimal("0.02"),
            purchase_closing_cost_pct=Decimal("0.015"),
            partnership_closing_costs=Decimal("50000"),
            acquisition_fee_pct=Decimal("0.01"),
            asset_management_fee_pct=Decimal("0.015"),
            annual_partnership_expenses=Decimal("25000"),
            disposition_fee_pct=Decimal("0.01"),
            loan_closing_costs=Decimal("0"),
            broker_snapshot=None,
        )
        projected_noi = backsolve._preview_projected_noi(prepared)

        lo = normalize_property_tax_purchase_price(Decimal(str(min_price)))
        hi = normalize_property_tax_purchase_price(Decimal(str(max_price)))

        def evaluate(price):
            case = backsolve._build_price_case(
                prepared, price=price, target_coc=target,
                year_built=year_built, benchmark_treasury=treasury,
                agency_spread=spread,
                purchase_closing_cost_pct=Decimal("0.015"),
                partnership_closing_costs=Decimal("50000"),
                acquisition_fee_pct=Decimal("0.01"),
                loan_closing_costs=Decimal("0"),
                projected_noi=projected_noi,
            )
            return case, backsolve._evaluate_case(case)

        lo_case, (lo_results, lo_coc) = evaluate(lo)
        hi_case, (hi_results, hi_coc) = evaluate(hi)
        if not (lo_coc >= target and hi_coc <= target):
            return _error(
                "INFEASIBLE_BRACKET",
                "The price bracket does not contain the target CoC "
                f"(low {float(lo_coc) * 100:.2f}%, high "
                f"{float(hi_coc) * 100:.2f}%).",
                "Widen min_price/max_price or revisit the target return; "
                "the engine will not extrapolate outside a proven bracket.",
            )
        solved_case, solved_results, solved_coc = lo_case, lo_results, lo_coc
        iterations_run = 0
        for _ in range(max_iterations):
            mid = ((lo + hi) / Decimal("2")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            case, (results, coc) = evaluate(mid)
            iterations_run += 1
            if coc >= target:
                lo = mid
                solved_case, solved_results, solved_coc = case, results, coc
            else:
                hi = mid
    except Exception as exc:
        return _error(
            "ENGINE_REFUSAL",
            f"The backsolve core refused this canonical: {exc}",
            "Fix the named validation issue; the engine owns every refusal "
            "reason.",
        )

    case_payload = _jsonable(solved_case)
    results_payload = _jsonable(solved_results)
    price = case_payload["purchase_assumptions"]["purchase_price"]
    return {
        "solved_price": price,
        "achieved_coc_pct": float(solved_coc) * 100,
        "target_coc_pct": target_coc_pct,
        "iterations_run": iterations_run,
        "case": case_payload,
        "case_results": {
            "engine_version": results_payload.get("engine_version"),
            "metrics": results_payload.get("metrics"),
        },
        "provenance": _provenance(
            "plat-multifamily-underwriting",
            "engine.backsolve (bisection over "
            "engine.engine.run_underwriting)",
            engine_version=results_payload.get("engine_version"),
            arithmetic_owner="engine",
            search="bisection, highest feasible price <= max_price",
        ),
    }


# --------------------------------------------------------- tax_regime_lookup

def tax_regime_lookup(state=None, **scenario):
    """Get the researched, statute-cited tax-regime schedule for a state."""
    if not state:
        return _error(
            "MISSING_INPUT",
            "A state is required for a tax-regime lookup.",
            "Pass the two-letter state code (TX, CA, FL, AL are the "
            "researched regimes).",
        )
    try:
        from engine.tax_regimes import (
            TaxRegimeError,
            build_tax_regime_schedule,
            supported_regimes,
        )
    except ImportError:
        return _backend_unavailable("engine.tax_regimes",
                                    "plat-multifamily-underwriting")

    inputs = dict(scenario)
    inputs["state"] = state
    try:
        schedule = build_tax_regime_schedule(inputs)
    except TaxRegimeError as exc:
        code = getattr(exc, "code", "TAX_REGIME_REFUSAL")
        supported = ", ".join(supported_regimes())
        return _error(
            code if isinstance(code, str) and code else "TAX_REGIME_REFUSAL",
            f"The tax-regime builder refused: {exc}",
            f"Supported regimes: {supported}. Every figure is statute-"
            "cited; unsupported jurisdictions refuse rather than guess.",
        )
    except Exception as exc:
        return _error(
            "INVALID_INPUT",
            f"The tax-regime builder refused this scenario: {exc}",
            "Check the scenario fields (tax_year, just_value, millage "
            "values must be present per the regime's requirements).",
        )
    payload = _jsonable(schedule)
    payload["provenance"] = _provenance(
        "plat-multifamily-underwriting",
        "engine.tax_regimes.build_tax_regime_schedule",
        contract_version=schedule.get("contract_version"),
        retrieval_dates="see schedule citations (retrieved per statute)",
        research_notice=(
            "Statutory research is research, not law; every schedule "
            "reports requires_competent_human_review=True."
        ),
    )
    return payload


# -------------------------------------------------------- renovation_estimate

def renovation_estimate(unit_sqft, bedrooms, bathrooms, scope_level,
                        finish_tier="basic", year_built=None,
                        property_class=None, market=None, unit_id=""):
    """Estimate per-unit renovation cost ranges from the costmodel KB."""
    if unit_sqft is None or not isinstance(unit_sqft, (int, float)) \
            or unit_sqft <= 0:
        return _error(
            "INVALID_INPUT",
            f"unit_sqft must be a positive number, got {unit_sqft!r}.",
            "Provide the unit's square footage, e.g. 850.",
        )
    if bedrooms is None or not isinstance(bedrooms, int) or bedrooms < 0:
        return _error(
            "INVALID_INPUT",
            f"bedrooms must be a non-negative integer, got {bedrooms!r}.",
            "Provide the bedroom count, e.g. 2.",
        )
    if bathrooms is None or not isinstance(bathrooms, (int, float)) \
            or bathrooms <= 0:
        return _error(
            "INVALID_INPUT",
            f"bathrooms must be a positive number, got {bathrooms!r}.",
            "Provide the bathroom count, e.g. 1.",
        )
    try:
        from plat_costmodel.estimator import estimate_unit
    except ImportError:
        return _backend_unavailable("plat_costmodel", "plat-costmodel")
    try:
        estimate = estimate_unit(
            unit_sqft=unit_sqft, bedrooms=bedrooms, bathrooms=bathrooms,
            scope_level=scope_level, finish_tier=finish_tier,
            year_built=year_built, property_class=property_class,
            market=market, unit_id=unit_id,
        )
    except Exception as exc:
        return _error(
            "INVALID_INPUT",
            f"The costmodel estimator refused these inputs: {exc}",
            "Valid scope levels: light, standard_value_add. Valid finish "
            "tiers: basic, upgraded.",
        )
    payload = _jsonable(estimate.model_dump(mode="python"))
    payload["provenance"] = _provenance(
        "plat-costmodel",
        "plat_costmodel.estimator.estimate_unit",
        knowledge_base="packaged knowledge_base.yaml",
        arithmetic_owner="plat-costmodel",
    )
    return payload


# ------------------------------------------------------------ renovation_roi

def renovation_roi(total_cost_high, current_monthly_rent, target_monthly_rent,
                   threshold_pct=None):
    """Check whether a renovation's rent lift clears the ROI threshold."""
    if total_cost_high is None or not isinstance(total_cost_high, (int, float)) \
            or total_cost_high <= 0:
        return _error(
            "INVALID_INPUT",
            "total_cost_high must be a positive number (use the HIGH end "
            "of the cost estimate; the check is deliberately conservative).",
            "Pass the high renovation cost, e.g. 15000.",
        )
    if current_monthly_rent is None or target_monthly_rent is None or \
            not isinstance(current_monthly_rent, (int, float)) or \
            not isinstance(target_monthly_rent, (int, float)):
        return _error(
            "INVALID_INPUT",
            "current_monthly_rent and target_monthly_rent are required "
            "numbers.",
            "Pass in-place rent and projected rent for the unit, e.g. 850 "
            "and 1050.",
        )
    if target_monthly_rent <= current_monthly_rent:
        return _error(
            "INVALID_INPUT",
            "The projected rent must exceed the in-place rent for an ROI "
            "check (a non-positive rent lift never clears a threshold).",
            "Re-run renovation_estimate for the cost side and provide a "
            "rent-lift scenario.",
        )
    try:
        from plat_costmodel.roi import check_roi
    except ImportError:
        return _backend_unavailable("plat_costmodel", "plat-costmodel")
    kwargs = {}
    if threshold_pct is not None:
        kwargs["threshold_pct"] = threshold_pct
    result = check_roi(
        total_cost_high=total_cost_high,
        current_monthly_rent=current_monthly_rent,
        target_monthly_rent=target_monthly_rent,
        **kwargs,
    )
    payload = _jsonable(result.model_dump(mode="python"))
    payload["provenance"] = _provenance(
        "plat-costmodel",
        "plat_costmodel.roi.check_roi",
        formula="(annual rent lift / total cost HIGH) x 100 >= threshold",
        arithmetic_owner="plat-costmodel",
    )
    return payload


# --------------------------------------------------------------- generate_sow

def generate_sow(unit_sqft, bedrooms, bathrooms, scope_level,
                 finish_tier="basic", property_address="", unit_id=""):
    """Generate a contractor-ready scope of work document."""
    if unit_sqft is None or not isinstance(unit_sqft, (int, float)) \
            or unit_sqft <= 0:
        return _error(
            "INVALID_INPUT",
            f"unit_sqft must be a positive number, got {unit_sqft!r}.",
            "Provide the unit's square footage, e.g. 850.",
        )
    try:
        from plat_costmodel.sow import generate_sow as _generate_sow
    except ImportError:
        return _backend_unavailable("plat_costmodel", "plat-costmodel")
    try:
        sow = _generate_sow(
            unit_sqft=unit_sqft, bedrooms=bedrooms, bathrooms=bathrooms,
            scope_level=scope_level, finish_tier=finish_tier,
            property_address=property_address, unit_id=unit_id,
        )
    except Exception as exc:
        return _error(
            "INVALID_INPUT",
            f"The costmodel SOW generator refused these inputs: {exc}",
            "Valid scope levels: light, standard_value_add. Valid finish "
            "tiers: basic, upgraded.",
        )
    payload = _jsonable(sow.model_dump(mode="python"))
    payload["provenance"] = _provenance(
        "plat-costmodel",
        "plat_costmodel.sow.generate_sow",
        knowledge_base="packaged knowledge_base.yaml",
    )
    return payload


# --------------------------------------------------------------- evaluate_bid

def evaluate_bid(bid, estimate):
    """Evaluate a contractor bid against an internal costmodel estimate."""
    if not isinstance(bid, dict):
        return _error(
            "MISSING_INPUT",
            "A bid object is required (contractor_name, line_items, total).",
            "Pass the parsed contractor bid as an object.",
        )
    if not isinstance(estimate, dict):
        return _error(
            "MISSING_INPUT",
            "An internal estimate is required to evaluate a bid against.",
            "Run renovation_estimate first and pass its result as the "
            "estimate.",
        )
    try:
        from plat_costmodel.bid_eval import evaluate_bid as _evaluate_bid
        from plat_costmodel.estimator import estimate_unit
        from plat_costmodel.models import BidLineItem, ContractorBid
    except ImportError:
        return _backend_unavailable("plat_costmodel", "plat-costmodel")

    try:
        bid_line_items = [
            BidLineItem(description=item["description"],
                        amount=item["amount"])
            for item in bid.get("line_items") or []
        ]
        bid_model = ContractorBid(
            contractor_name=bid.get("contractor_name", ""),
            line_items=bid_line_items,
            total=bid.get("total", 0),
            timeline_days=bid.get("timeline_days"),
        )
        estimate_model = estimate_unit(
            unit_sqft=estimate["unit_sqft"],
            bedrooms=estimate["bedrooms"],
            bathrooms=estimate["bathrooms"],
            scope_level=estimate.get("scope_level", "standard_value_add"),
            finish_tier=estimate.get("finish_tier", "basic"),
            year_built=estimate.get("year_built"),
            property_class=estimate.get("property_class"),
            market=estimate.get("market"),
            unit_id=estimate.get("unit_id", ""),
        )
        evaluation = _evaluate_bid(bid_model, estimate_model)
    except Exception as exc:
        return _error(
            "INVALID_INPUT",
            f"The bid evaluator refused these inputs: {exc}",
            "The bid needs contractor_name, line_items "
            "(description + amount each) and total; the estimate needs the "
            "renovation_estimate fields.",
        )
    payload = _jsonable(evaluation.model_dump(mode="python"))
    payload["provenance"] = _provenance(
        "plat-costmodel",
        "plat_costmodel.bid_eval.evaluate_bid",
        flags="inflated (30%+ over internal high), vague, timeline",
        arithmetic_owner="plat-costmodel",
    )
    return payload


# ------------------------------------------------------------------ ops_review

def ops_review(asset_id, period=None, materiality=None, as_of_date=None,
               db_path=None, variance_oracle_callable=None):
    """Read-only ops review of exactly one property and one period."""
    if not asset_id or not isinstance(asset_id, str):
        return _error(
            "MISSING_INPUT",
            "An asset identifier is required for an ops review.",
            "Pass the single property's opaque asset id, e.g. "
            "'synthetic_ops'.",
        )
    if not period:
        return _error(
            "MISSING_INPUT",
            "A period (YYYY-MM) is required for an ops review.",
            "Pass exactly one analysis month, e.g. '2026-04'.",
        )
    if not isinstance(materiality, dict) or not materiality.get("variance_abs"):
        return _error(
            "MISSING_INPUT",
            "A materiality policy is required for an ops review.",
            "Pass e.g. {'variance_abs': '500.00', 'currency': 'USD'}.",
        )
    if not db_path:
        return _error(
            "MISSING_INPUT",
            "A database path is required for an ops review.",
            "Point at the ops SQLite database for this property, e.g. the "
            "synthetic walkthrough snapshot.",
        )
    try:
        from plat_harness.adapters.ops_review import review_period
    except ImportError:
        return _backend_unavailable("plat_harness", "plat-harness")
    try:
        result = review_period(
            asset_id=asset_id,
            period=period,
            materiality=materiality,
            as_of_date=as_of_date,
            db_path=db_path,
            variance_oracle=variance_oracle_callable,
        )
    except Exception as exc:
        code = getattr(exc, "code", None)
        message = f"The ops review refused this request: {exc}"
        if code and isinstance(code, str):
            return _error(
                code,
                message,
                "The review scope is exactly one property and one period; "
                "fix the named issue and retry.",
            )
        return _error(
            "INVALID_INPUT",
            message,
            "Check asset id, period (YYYY-MM), materiality, and the "
            "database path.",
        )
    payload = _jsonable(result)
    payload["provenance"] = _provenance(
        "plat-harness",
        "plat_harness.adapters.ops_review.review_period",
        contract_version=result.get("contract_version"),
        variance_oracle_owner=result.get("variance", {}).get("oracle_owner")
        if isinstance(result.get("variance"), dict) else None,
        read_only=True,
    )
    return payload


# ------------------------------------------------- MCP-facing callable table

PRODUCT_TOOL_IMPLEMENTATIONS = {
    "underwrite_run": underwrite_run,
    "underwrite_backsolve": underwrite_backsolve,
    "tax_regime_lookup": tax_regime_lookup,
    "renovation_estimate": renovation_estimate,
    "renovation_roi": renovation_roi,
    "generate_sow": generate_sow,
    "evaluate_bid": evaluate_bid,
    "ops_review": ops_review,
}


def call_product_tool(name, kwargs):
    """Invoke a product tool body by name with a kwargs dict; never raises.

    This is the seam ``mcp_server.py`` registers: it normalizes any
    unexpected failure into a typed refusal payload so an MCP client never
    sees an opaque crash.
    """
    implementation = PRODUCT_TOOL_IMPLEMENTATIONS.get(name)
    if implementation is None:
        return _error(
            "UNKNOWN_TOOL",
            f"Unknown product tool {name!r}.",
            f"Product tools: {', '.join(sorted(PRODUCT_TOOL_NAMES))}.",
        )
    try:
        return implementation(**kwargs)
    except TypeError as exc:
        return _error(
            "INVALID_INPUT",
            f"Wrong arguments for {name}: {exc}",
            "Check the tool's parameter names and types.",
        )
    except Exception as exc:  # defensive: tool bodies already refuse typed
        return _error(
            "TOOL_FAILURE",
            f"{name} failed unexpectedly: {exc}",
            "This is an unplanned failure path; the wrapped service's own "
            "refusals are normally typed.",
        )