"""Python port of the pinned ``boxscore::variance`` ops owner (plat-operations).

The ops-review contract (``plat_harness.adapters.ops_review``) refuses to
compute variance itself: variance comes only through a host-bound oracle
pinned to ``boxscore::variance`` — the pure Rust functions
``compute_account_variances`` and ``compute_noi_bridge`` in
``plat-operations/boxscore/src/variance.rs``. This module is that owner,
ported verbatim so the platworks MCP server can bind the pinned oracle
by default (an MCP stdio client can never pass a callable across the
wire) while every number stays owned by the ops owner, not the wrapper.

Ported semantics (mirrored line-for-line from variance.rs / ontology.rs):

- Per-(account_code, account_name, category) totals; rows sorted by the
  tuple key (Rust's BTreeMap iteration order), variance = actual - budget.
- Account classification is the Rust ``ontology::account_class``: category
  trimmed and lowercased; ``rental income`` / ``concessions`` / ``bad debt``
  / ``other income`` are Revenue, ``unmapped`` is Unmapped, everything else
  is Expense.
- Expenses keep their natural positive sign (the standardized Yardi
  budget_comparison convention); contra-revenue (concessions, bad debt)
  stays negative inside the revenue total; NOI = revenue - expenses.
- Unmapped accounts are excluded from the bridge and disclosed separately
  (``unmapped_actual`` / ``unmapped_budget``), never silently dropped.

The oracle input contract is the closed ``ORACLE_ROW_KEYS`` set
(``account_code``, ``account_name``, ``category``, ``amount`` — decimal
strings); output values are two-decimal money strings, exactly the shape
the ops-review seam validates (``BY_ACCOUNT_KEYS`` / ``NOI_BRIDGE_KEYS``).

The port is pinned by ``tests/test_ops_oracle.py`` against the actual Rust
functions executed on the same synthetic snapshot rows (see the test's
Rust-expected values), so drift between this port and the Rust owner
fails CI rather than fabricating numbers.
"""

from decimal import Decimal

# ontology.rs::account_class — the exact Rust revenue/unmapped sets.
REVENUE_CATEGORIES = frozenset(
    {"rental income", "concessions", "bad debt", "other income"})
UNMAPPED_CATEGORIES = frozenset({"unmapped"})

# ops_review.py::ORACLE_OWNER / ORACLE_FUNCTIONS — the pinned owner label.
ORACLE_OWNER = "boxscore::variance"
ORACLE_FUNCTIONS = ("compute_account_variances", "compute_noi_bridge")
ORACLE_ROW_KEYS = frozenset(
    {"account_code", "account_name", "category", "amount"})

BY_ACCOUNT_KEYS = frozenset(
    {"account_code", "account_name", "category", "actual", "budget",
     "variance"})
NOI_BRIDGE_KEYS = frozenset(
    {"actual_revenue", "budget_revenue", "revenue_variance",
     "actual_expenses", "budget_expenses", "expense_variance",
     "actual_noi", "budget_noi", "noi_variance", "unmapped_actual",
     "unmapped_budget"})


def _fmt(value):
    """Two-decimal money string — the owner's rendered contract shape."""
    return f"{value:.2f}"


def _classify(category):
    """ontology.rs::account_class — trim + lowercase match."""
    key = str(category).strip().lower()
    if key in REVENUE_CATEGORIES:
        return "revenue"
    if key in UNMAPPED_CATEGORIES:
        return "unmapped"
    return "expense"


def _totals(actuals, budgets):
    """Per-(code, name, category) sums — variance.rs's BTreeMap totals."""
    totals = {}
    for rows, index in ((actuals, 0), (budgets, 1)):
        for row in rows:
            key = (row["account_code"], row["account_name"], row["category"])
            totals.setdefault(key, [Decimal("0"), Decimal("0")])[index] += Decimal(
                row["amount"])
    return totals


def compute_account_variances(actuals, budgets):
    """Port of variance.rs::compute_account_variances (sorted BTreeMap)."""
    rows = []
    for (code, name, category), (actual, budget) in sorted(_totals(actuals, budgets).items()):
        rows.append({
            "account_code": code,
            "account_name": name,
            "category": category,
            "actual": _fmt(actual),
            "budget": _fmt(budget),
            "variance": _fmt(actual - budget),
        })
    return rows


def compute_noi_bridge(actuals, budgets):
    """Port of variance.rs::compute_noi_bridge over the account rows."""
    rev_a = rev_b = exp_a = exp_b = Decimal("0")
    unm_a = unm_b = Decimal("0")
    for row in compute_account_variances(actuals, budgets):
        actual, budget = Decimal(row["actual"]), Decimal(row["budget"])
        kind = _classify(row["category"])
        if kind == "revenue":
            rev_a += actual
            rev_b += budget
        elif kind == "unmapped":
            unm_a += actual
            unm_b += budget
        else:
            exp_a += actual
            exp_b += budget
    return {
        "actual_revenue": _fmt(rev_a),
        "budget_revenue": _fmt(rev_b),
        "revenue_variance": _fmt(rev_a - rev_b),
        "actual_expenses": _fmt(exp_a),
        "budget_expenses": _fmt(exp_b),
        "expense_variance": _fmt(exp_a - exp_b),
        "actual_noi": _fmt(rev_a - exp_a),
        "budget_noi": _fmt(rev_b - exp_b),
        "noi_variance": _fmt((rev_a - exp_a) - (rev_b - exp_b)),
        "unmapped_actual": _fmt(unm_a),
        "unmapped_budget": _fmt(unm_b),
    }


def variance_oracle(actuals, budgets):
    """The bound-oracle adapter shape the ops-review seam expects.

    Returns exactly the closed ``{'by_account', 'noi_bridge'}`` contract
    the seam validates; amounts are the owner's two-decimal strings.
    """
    return {
        "by_account": compute_account_variances(actuals, budgets),
        "noi_bridge": compute_noi_bridge(actuals, budgets),
    }