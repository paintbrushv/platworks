"""Exercise installed acquisition and operating workflows with synthetic data.

Run with ``python -I -m platworks.verify_install`` from any directory. No source
checkout, binary override, credentials, or real files are required.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from importlib.resources import files
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from platworks.doctor import diagnose
from platworks.ops_oracle import producer_path


async def mcp_call(module, calls):
    params = StdioServerParameters(command=sys.executable, args=["-I", "-m", module])
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            available = {t.name for t in (await client.list_tools()).tools}
            for name, arguments in calls:
                assert name in available, "Required tool missing"
                result = await client.call_tool(name, arguments)
                assert not result.is_error and result.content, "MCP tool failed"
                payload = json.loads(result.content[0].text)
                assert "error" not in payload, "MCP tool refused synthetic example"
                results.append(payload)
    return results


def verify():
    if not __debug__:
        raise RuntimeError("Run installation checks without Python optimization")
    report = diagnose(analysis=True)
    assert report["status"] in {"ready", "ready_with_warnings"}, "Doctor failed"
    from engine.backsolve import backsolve_price

    from platworks.wrappers import ops_review, underwrite_backsolve, underwrite_run

    inputs = json.loads(files("platworks").joinpath("data/synthetic_acquisition.json").read_text())
    full = underwrite_run(inputs)
    assert "error" not in full and full.get("metrics"), "Acquisition calculation failed"
    policy = {"version": "plat.backsolve-policy/1", "strategy": "cashflow"}
    benchmark = {"rate": "0.04", "as_of": "2026-10-03", "source": "synthetic:install-check"}
    search = backsolve_price(inputs, target_coc="0.07", policy=policy, benchmark=benchmark)
    wrapped = underwrite_backsolve(inputs, target_coc_pct=7, policy=policy, benchmark=benchmark)
    assert "error" not in wrapped, "Backsolve wrapper refused"
    # Both surfaces expose the same authoritative search summary.
    assert wrapped["summary"] == search["summary"], "Backsolve parity mismatch"
    engine = anyio.run(
        mcp_call,
        "engine.mcp_server",
        [
            ("validate_deal_inputs", {"inputs": inputs}),
            (
                "backsolve_deal_price",
                {"inputs": inputs, "target_coc": "0.07", "policy": policy, "benchmark": benchmark},
            ),
        ],
    )
    assert engine[1]["summary"] == search["summary"], "Engine MCP parity mismatch"
    cost = anyio.run(
        mcp_call,
        "plat_costmodel.server",
        [
            ("estimate", {"unit_sqft": 750, "bedrooms": 1, "bathrooms": 1}),
        ],
    )
    assert cost[0] and "error_type" not in cost[0], "Costmodel MCP refused"
    umbrella = anyio.run(
        mcp_call,
        "platworks.mcp_server",
        [
            ("get_component", {"name": "plat-harness"}),
            (
                "underwrite_backsolve",
                {"inputs": inputs, "target_coc_pct": 7, "policy": policy, "benchmark": benchmark},
            ),
            ("ops_review", {"asset_id": "synthetic_ops", "period": "2026-04"}),
        ],
    )
    assert umbrella[1]["summary"] == search["summary"], "Umbrella MCP parity mismatch"
    assert umbrella[2]["contract_version"] == "ops-review/2.0.0"

    binary = str(producer_path())
    with tempfile.TemporaryDirectory(prefix="plat-install-synthetic-") as temporary:
        work = Path(temporary)
        database = work / "synthetic.sqlite"

        def cli(*args):
            result = subprocess.run(
                [binary, *map(str, args)], capture_output=True, timeout=30, check=True
            )
            return json.loads(result.stdout)

        actuals, budgets = work / "actual.csv", work / "budget.csv"
        header = "account_code,account_name,category,amount\n"
        actuals.write_text(header + "4000,Rent,rental income,0.10\n4000,Rent,rental income,0.20\n")
        budgets.write_text(header + "4000,Rent,rental income,0.29\n")
        cli("init", "--database", database)
        args = (
            "import-csv",
            "--database",
            database,
            "--actuals",
            actuals,
            "--budgets",
            budgets,
            "--property",
            "synthetic_ops",
            "--period",
            "2026-05",
            "--units",
            "10",
        )
        first = cli(*args)["revision_id"]
        issued = cli("issue", "--database", database, "--revision", first)
        assert issued["variance"]["noi_bridge"]["noi_variance"] == "0.01"
        with closing(sqlite3.connect(database)) as connection:
            original = connection.execute("SELECT body FROM exact_reports").fetchone()[0]
            types = connection.execute("SELECT DISTINCT typeof(amount_cents) FROM exact_gl")
            assert types.fetchall() == [("integer",)], "Money is not integer cents"
        actuals.write_text(header + "4000,Rent,rental income,0.31\n")
        second = cli(*args, "--supersedes", first, "--reason", "Synthetic installation correction")[
            "revision_id"
        ]
        corrected = cli("issue", "--database", database, "--revision", second)
        assert corrected["changes"]["actual_noi"] == "0.01"
        with closing(sqlite3.connect(database)) as connection:
            assert (
                connection.execute(
                    "SELECT body FROM exact_reports WHERE id=?", (issued["report_id"],)
                ).fetchone()[0]
                == original
            )
        reviewed = ops_review("synthetic_ops", "2026-05", db_path=str(database))
        assert "error" not in reviewed, "Harness review failed"
        assert reviewed["variance"]["noi_bridge"]["actual_noi"]["amount"] == "0.31"
        assert any(e["code"] == "UNREVIEWED_ACCOUNT_MAPPING" for e in reviewed["exceptions"])
    return {
        "contract_version": "plat.install-check/1",
        "status": "passed",
        "data_class": "synthetic",
        "doctor": report,
        "checks": [
            "acquisition",
            "backsolve_api_wrapper_mcp_parity",
            "costmodel_mcp",
            "catalog_mcp",
            "packaged_ops_snapshot",
            "integer_cent_storage",
            "immutable_reports",
            "one_cent_correction",
            "harness_review",
        ],
        "producer_sha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
        "source_overrides_present": any(
            os.environ.get(key)
            for key in (
                "PLAT_BOXSCORE_EXACT_BIN",
                "PLAT_HARNESS_ENGINE_ROOT",
                "UNDERWRITING_ENGINE_PATH",
            )
        ),
    }


def main():
    try:
        result = verify()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(2) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
