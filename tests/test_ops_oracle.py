"""Tests for the ported ``boxscore::variance`` ops owner (platworks.ops_oracle).

The ops-review seam (``plat_harness.adapters.ops_review``) implements no
variance arithmetic: numbers come only through a host-bound oracle pinned
to ``boxscore::variance`` — the pure Rust functions in
``plat-operations/boxscore/src/variance.rs``. ``platworks.ops_oracle`` is
that owner, ported verbatim, so the MCP server can bind the pinned oracle
by default (an MCP stdio client can never pass a callable across the wire).

These tests pin the port against two independent ground truths:

1. **Rust-expected values.** The constants below are the actual output of
   the real Rust ``compute_account_variances`` + ``compute_noi_bridge``
   executed over the synthetic walkthrough snapshot's 2026-04 GL rows
   (via ``boxscore/examples/ops_oracle_expected.rs``, same crate, same
   functions the frozen owner exports). Drift between the port and the
   Rust owner fails here rather than fabricating numbers.
2. **The frozen harness oracle contract.** The same pinned values the
   harness's own suite asserts for the stub oracle over identical seeded
   rows (``test_ops_review.py``:
   ``noi_variance == '499.50'``, ``actual_noi == '3799.50'``).
"""

from platworks import ops_oracle

# ------------------------------------------------- Rust-expected ground truth
# Actual output of the real Rust boxscore::variance owner functions
# (plat-operations/boxscore/src/variance.rs) over the synthetic walkthrough
# snapshot rows for 2026-04:
#   gl_actuals: 4000 Rental Income 5000.0; 6100 Repairs & Maintenance 1200.5
#   gl_budgets: 4000 Rental Income 4400.0; 6100 Repairs & Maintenance 1100.0
# (amounts here use the seam's shortest round-trip decimal strings)
RUST_EXPECTED_BY_ACCOUNT = [
    {
        "account_code": "4000", "account_name": "Rental Income",
        "category": "rental income",
        "actual": "5000.00", "budget": "4400.00", "variance": "600.00",
    },
    {
        "account_code": "6100", "account_name": "Repairs & Maintenance",
        "category": "repairs & maintenance",
        "actual": "1200.50", "budget": "1100.00", "variance": "100.50",
    },
]

RUST_EXPECTED_NOI_BRIDGE = {
    "actual_revenue": "5000.00", "budget_revenue": "4400.00",
    "revenue_variance": "600.00",
    "actual_expenses": "1200.50", "budget_expenses": "1100.00",
    "expense_variance": "100.50",
    "actual_noi": "3799.50", "budget_noi": "3300.00",
    "noi_variance": "499.50",
    "unmapped_actual": "0.00", "unmapped_budget": "0.00",
}

# Rows exactly as the ops-review seam hands them to a bound oracle
# (ORACLE_ROW_KEYS: decimal-string amounts, deterministic sort).
SNAPSHOT_ACTUALS = [
    {"account_code": "4000", "account_name": "Rental Income",
     "category": "rental income", "amount": "5000.0"},
    {"account_code": "6100", "account_name": "Repairs & Maintenance",
     "category": "repairs & maintenance", "amount": "1200.5"},
]
SNAPSHOT_BUDGETS = [
    {"account_code": "4000", "account_name": "Rental Income",
     "category": "rental income", "amount": "4400.0"},
    {"account_code": "6100", "account_name": "Repairs & Maintenance",
     "category": "repairs & maintenance", "amount": "1100.0"},
]


def test_oracle_pins_the_boxscore_owner_label():
    assert ops_oracle.ORACLE_OWNER == "boxscore::variance"
    assert ops_oracle.ORACLE_FUNCTIONS == (
        "compute_account_variances", "compute_noi_bridge")
    assert ops_oracle.ORACLE_ROW_KEYS == frozenset(
        {"account_code", "account_name", "category", "amount"})


def test_compute_account_variances_matches_rust_expected():
    rows = ops_oracle.compute_account_variances(
        SNAPSHOT_ACTUALS, SNAPSHOT_BUDGETS)
    assert rows == RUST_EXPECTED_BY_ACCOUNT


def test_compute_noi_bridge_matches_rust_expected():
    bridge = ops_oracle.compute_noi_bridge(SNAPSHOT_ACTUALS, SNAPSHOT_BUDGETS)
    assert bridge == RUST_EXPECTED_NOI_BRIDGE
    # The two independent ground truths agree: the harness's own frozen
    # oracle contract pins these same values (noi_variance 499.50,
    # actual_noi 3799.50) over identically seeded rows.
    assert bridge["noi_variance"] == "499.50"
    assert bridge["actual_noi"] == "3799.50"


def test_variance_oracle_returns_the_closed_seam_contract():
    out = ops_oracle.variance_oracle(SNAPSHOT_ACTUALS, SNAPSHOT_BUDGETS)
    assert set(out) == {"by_account", "noi_bridge"}
    assert out["by_account"] == RUST_EXPECTED_BY_ACCOUNT
    assert out["noi_bridge"] == RUST_EXPECTED_NOI_BRIDGE


# ------------------------------------------------- ported Rust unit semantics
# Mirrors of variance.rs's own #[cfg(test)] cases (same inputs, same
# expected signs) so the port cannot drift from the owner's conventions.

def _rows(pairs):
    return [
        {"account_code": code, "account_name": code,
         "category": category, "amount": f"{amount:.2f}"}
        for code, category, amount in pairs
    ]


def test_expense_overrun_lowers_noi_like_the_rust_owner():
    # variance.rs: computes_noi_variance_from_revenue_and_expense_lines
    actuals = _rows([("4000", "rental income", 100.0),
                     ("5200", "repairs & maintenance", 30.0)])
    budgets = _rows([("4000", "rental income", 110.0),
                     ("5200", "repairs & maintenance", 20.0)])
    bridge = ops_oracle.compute_noi_bridge(actuals, budgets)
    assert bridge["actual_noi"] == "70.00"
    assert bridge["budget_noi"] == "90.00"
    assert bridge["noi_variance"] == "-20.00"
    # Expense overrun of $10 shows as +10 raw variance but -10 NOI impact.
    assert bridge["expense_variance"] == "10.00"


def test_unmapped_accounts_are_excluded_but_disclosed():
    # variance.rs: unmapped_accounts_are_excluded_from_noi_but_disclosed
    actuals = _rows([("4000", "rental income", 100.0),
                     ("3000", "unmapped", 500_000.0)])
    budgets = _rows([("4000", "rental income", 90.0)])
    bridge = ops_oracle.compute_noi_bridge(actuals, budgets)
    assert bridge["actual_noi"] == "100.00"
    assert bridge["actual_expenses"] == "0.00"
    assert bridge["unmapped_actual"] == "500000.00"
    # And the unmapped row carries no NOI impact:
    assert bridge["budget_noi"] == "90.00"


def test_contra_revenue_concessions_growth_is_unfavorable():
    # variance.rs: contra_revenue_concessions_growth_is_unfavorable
    actuals = _rows([("4990", "concessions", -50.0)])
    budgets = _rows([("4990", "concessions", -20.0)])
    bridge = ops_oracle.compute_noi_bridge(actuals, budgets)
    # More concessions than budget -> revenue variance is negative.
    assert bridge["revenue_variance"] == "-30.00"
    assert bridge["noi_variance"] == "-30.00"


def test_classification_is_trim_and_lowercase_like_the_rust_ontology():
    actuals = _rows([("4000", "Rental Income", 100.0)])
    budgets = _rows([("4000", "Rental Income", 90.0)])
    bridge = ops_oracle.compute_noi_bridge(actuals, budgets)
    assert bridge["actual_revenue"] == "100.00"
    assert ops_oracle._classify("  Rental Income ") == "revenue"
    assert ops_oracle._classify("BAD DEBT") == "revenue"
    assert ops_oracle._classify("Payroll") == "expense"
    assert ops_oracle._classify("Unmapped") == "unmapped"


def test_duplicate_rows_sum_like_the_rust_btreemap_totals():
    # The Rust owner sums per (code, name, category) before variance;
    # the port must aggregate duplicates identically.
    actuals = SNAPSHOT_ACTUALS + [dict(SNAPSHOT_ACTUALS[0])]
    budgets = SNAPSHOT_BUDGETS
    rows = ops_oracle.compute_account_variances(actuals, budgets)
    first = next(r for r in rows if r["account_code"] == "4000")
    assert first["actual"] == "10000.00"
    assert first["variance"] == "5600.00"