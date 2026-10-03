"""Financial expectations executed against the real Rust exact-cent producer."""

from platworks import ops_oracle

# ------------------------------------------------- Rust-expected ground truth
# Actual output of the real Rust boxscore::exact::variance owner functions
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
    assert ops_oracle.ORACLE_OWNER == "boxscore::exact::variance"
    assert ops_oracle.ORACLE_FUNCTIONS == (
        "compute",)
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


def test_duplicate_rows_sum_like_the_rust_btreemap_totals():
    # The Rust owner sums per (code, name, category) before variance;
    # the port must aggregate duplicates identically.
    actuals = SNAPSHOT_ACTUALS + [dict(SNAPSHOT_ACTUALS[0])]
    budgets = SNAPSHOT_BUDGETS
    rows = ops_oracle.compute_account_variances(actuals, budgets)
    first = next(r for r in rows if r["account_code"] == "4000")
    assert first["actual"] == "10000.00"
    assert first["variance"] == "5600.00"


def test_real_producer_preserves_cents_and_refuses_subcent_or_overflow():
    import pytest

    actuals = _rows([("4000", "rental income", 0.10)])
    actuals.append({**actuals[0], "amount": "0.20"})
    payload = ops_oracle.calculate(actuals, [])
    assert payload["result"]["noi_bridge"]["actual_noi"] == "0.30"
    assert payload["producer"]["arithmetic"] == "checked_i64_cents"
    assert len(payload["producer"]["binary_sha256"]) == 64
    for value in ("0.001", 0.01, "NaN", "92233720368547758.08"):
        with pytest.raises(ops_oracle.OpsProducerError):
            ops_oracle.calculate([{**actuals[0], "amount": value}], [])
    with pytest.raises(ops_oracle.OpsProducerError) as exc:
        ops_oracle.calculate([{**actuals[0], "amount": "92233720368547758.07"},
                              {**actuals[0], "amount": "0.01"}], [])
    assert exc.value.code == "MONEY_OVERFLOW"


def test_bridge_cannot_drop_sign_review_flags():
    import pytest

    for helper in (ops_oracle.variance_oracle, ops_oracle.compute_account_variances,
                   ops_oracle.compute_noi_bridge, ops_oracle.BoundOracle()):
        with pytest.raises(ops_oracle.OpsProducerError) as exc:
            helper(_rows([("6000", "repairs", -1)]), [])
        assert exc.value.code == "REVIEW_REQUIRED"


def test_missing_producer_and_wrong_pin_refuse(monkeypatch):
    import pytest

    monkeypatch.setenv("PLAT_BOXSCORE_EXACT_SHA256", "0" * 64)
    with pytest.raises(ops_oracle.OpsProducerError) as exc:
        ops_oracle.calculate([], [])
    assert exc.value.code == "PRODUCER_MISMATCH"
    monkeypatch.setenv("PLAT_BOXSCORE_EXACT_BIN", "/missing/boxscore-exact")
    with pytest.raises(ops_oracle.OpsProducerError) as exc:
        ops_oracle.calculate([], [])
    assert exc.value.code == "BACKEND_UNAVAILABLE"


def test_fixed_arguments_timeout_and_invalid_responses(monkeypatch):
    import subprocess
    from types import SimpleNamespace

    import pytest

    def timeout(args, request, **kwargs):
        assert len(args) == 2 and args[1] == "protocol"
        assert kwargs["timeout"] == 60
        assert "shell" not in kwargs
        raise subprocess.TimeoutExpired(args, 60)

    monkeypatch.setattr(ops_oracle, "_run_bounded", timeout)
    with pytest.raises(ops_oracle.OpsProducerError) as exc:
        ops_oracle.calculate([], [])
    assert exc.value.code == "PRODUCER_TIMEOUT"
    for body in (b"not JSON", b"[]", b'{"contract_version":"plat.ops/0"}',
                 b'{"contract_version":"plat.ops/1","status":"calculated"}'):
        monkeypatch.setattr(ops_oracle, "_run_bounded", lambda *a, **k:
                            SimpleNamespace(returncode=0, stdout=body))
        with pytest.raises(ops_oracle.OpsProducerError) as exc:
            ops_oracle.calculate([], [])
        assert exc.value.code == "INVALID_CONTRACT"


def test_streaming_limits_terminate_noisy_producer_on_either_pipe(monkeypatch):
    import subprocess
    import sys

    import pytest

    children = []
    popen = subprocess.Popen

    def launch(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(ops_oracle.subprocess, "Popen", launch)
    monkeypatch.setattr(ops_oracle, "MAX_RESPONSE_BYTES", 65536)
    for descriptor in (1, 2):
        script = f"import os\nwhile True: os.write({descriptor}, b'x' * 8192)"
        with pytest.raises(ops_oracle.OpsProducerError) as exc:
            ops_oracle._run_bounded([sys.executable, "-c", script], b"{}", timeout=5)
        assert exc.value.code == "INVALID_CONTRACT"
        assert children[-1].poll() is not None


def test_streaming_drains_both_pipes_and_enforces_deadline():
    import subprocess
    import sys

    import pytest

    # Both streams exceed pipe capacity; neither may block the other.
    script = ("import os,sys; body=sys.stdin.buffer.read(); "
              "os.write(2, b'e' * 200000); os.write(1, body)")
    request = b"x" * 200000
    result = ops_oracle._run_bounded([sys.executable, "-c", script], request, timeout=5)
    assert result.returncode == 0 and result.stdout == request
    with pytest.raises(subprocess.TimeoutExpired):
        ops_oracle._run_bounded([sys.executable, "-c", "import time; time.sleep(10)"],
                                b"{}", timeout=0.1)


def test_producer_refuses_subtraction_outside_reversible_money_range():
    import pytest

    actual = {"account_code": "4000", "account_name": "Rent", "category": "rental income",
              "amount": "-92233720368547758.07"}
    with pytest.raises(ops_oracle.OpsProducerError) as exc:
        ops_oracle.calculate([actual], [{**actual, "amount": "0.01"}])
    assert exc.value.code == "MONEY_OVERFLOW"


def test_exact_csv_to_persistence_correction_and_harness_review(tmp_path):
    import json
    import os
    import sqlite3
    import subprocess

    from platworks.wrappers import ops_review

    binary = os.environ["PLAT_BOXSCORE_EXACT_BIN"]
    database = tmp_path / "exact.sqlite"

    def cli(*args):
        proc = subprocess.run([binary, *map(str, args)], capture_output=True,
                              text=True, timeout=30, check=True)
        return json.loads(proc.stdout)

    actuals, budgets = tmp_path / "actual.csv", tmp_path / "budget.csv"
    header = "account_code,account_name,category,amount\n"
    actuals.write_text(header + "4000,Rent,rental income,0.10\n4000,Rent,rental income,0.20\n")
    budgets.write_text(header + "4000,Rent,rental income,0.10\n")
    cli("init", "--database", database)
    first = cli("import-csv", "--database", database, "--actuals", actuals,
                "--budgets", budgets, "--property", "synthetic_ops", "--period",
                "2026-05", "--units", "10")["revision_id"]
    issued = cli("issue", "--database", database, "--revision", first)
    assert issued["variance"]["noi_bridge"]["noi_variance"] == "0.20"
    with sqlite3.connect(database) as con:
        original = con.execute("SELECT body FROM exact_reports").fetchone()[0]
        assert con.execute("SELECT sum(amount_cents) FROM exact_gl WHERE kind='actual'")\
            .fetchone()[0] == 30
    actuals.write_text(header + "4000,Rent,rental income,0.31\n")
    second = cli("import-csv", "--database", database, "--actuals", actuals,
                 "--budgets", budgets, "--property", "synthetic_ops", "--period",
                 "2026-05", "--units", "10", "--supersedes", first,
                 "--reason", "Synthetic one-cent correction")["revision_id"]
    corrected = cli("issue", "--database", database, "--revision", second)
    assert corrected["changes"]["actual_noi"] == "0.01"
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT body FROM exact_reports WHERE id=?", (issued["report_id"],))\
            .fetchone()[0] == original
    payload = ops_review("synthetic_ops", "2026-05", db_path=str(database))
    assert "error" not in payload, payload
    assert payload["contract_version"] == "ops-review/2.0.0"
    assert payload["variance"]["noi_bridge"]["actual_noi"]["amount"] == "0.31"
    assert payload["provenance"]["operating_producer"]["arithmetic"] == "checked_i64_cents"
    assert any(e["code"] == "UNREVIEWED_ACCOUNT_MAPPING" for e in payload["exceptions"])

    with sqlite3.connect(database) as con:
        con.execute("INSERT INTO exact_gl VALUES (?,?,?,?,?,?,?)",
                    (second, "actual", 99, "4000", "Rent", "rental income", 1))
    refused = ops_review("synthetic_ops", "2026-05", db_path=str(database))
    assert refused["error"]["code"] == "INVALID_CONTRACT"


def test_real_producer_matches_codes_and_preserves_mapping_failure():
    import pytest

    a = {"account_code": "4000", "account_name": "Actual rent", "category": "Rental Income",
         "amount": "100.10"}
    b = {**a, "account_name": "Budget rent", "category": " rental income ", "amount": "90.00"}
    result = ops_oracle.variance_oracle([a], [b])
    assert len(result["by_account"]) == 1
    assert result["noi_bridge"]["noi_variance"] == "10.10"
    with pytest.raises(ops_oracle.OpsProducerError) as exc:
        ops_oracle.variance_oracle([a], [{**b, "category": "repairs"}])
    assert exc.value.code == "ACCOUNT_MAPPING_CONFLICT"
