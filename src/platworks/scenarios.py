"""Bounded, unapproved scenario calls to the existing financial producers."""

import asyncio
import inspect
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from importlib.metadata import PackageNotFoundError, version

from platworks import wrappers
from platworks.library import canonical, sha256

MAX_INPUT = 2 * 1024 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
DEADLINE = 60
SCENARIO_TOOLS = wrappers.PRODUCT_TOOL_NAMES - {"ops_review"} | {"preview_operations"}
ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "MISSING_INPUT",
        "BACKEND_UNAVAILABLE",
        "ENGINE_REFUSAL",
        "UNSUPPORTED_TAX_REGIME",
        "TAX_REGIME_REFUSAL",
        "COSTMODEL_REFUSAL",
        "TOOL_FAILURE",
        "INPUT_LIMIT",
        "MONEY_PRECISION",
        "MONEY_OVERFLOW",
        "EXCESS_PRECISION",
        "ACCOUNT_MAPPING_CONFLICT",
        "INVALID_MAPPING",
        "PRODUCER_REFUSAL",
        "MISSING_SNAPSHOT",
        "INVALID_SNAPSHOT",
        "INVALID_PERIOD",
        "INVALID_CONTRACT",
    }
)


def refusal(code):
    messages = {
        "BUSY": "Both calculation slots are occupied. Retry later.",
        "TIMEOUT": "Calculation exceeded 60 seconds and was terminated.",
        "INPUT_LIMIT": "Input exceeds the size, depth, row or analysis-period limit.",
        "OUTPUT_LIMIT": "Calculation output exceeds 8 MiB. Reduce the scenario size.",
        "BACKEND_UNAVAILABLE": "Install the analysis profile to use financial tools.",
        "UNKNOWN_TOOL": "This tool is not available in this server profile.",
    }
    return {
        "error": {
            "code": code,
            "message": messages.get(
                code,
                "The scenario was refused. Check required inputs, units, tax policy and coverage.",
            ),
            "hint": "Use get_synthetic_example and the tool schema. Tax regimes: TX CA FL AL. "
            "Resolve conflicting or missing facts before retrying.",
        }
    }


def validate_request(name, arguments):
    if name not in SCENARIO_TOOLS or not isinstance(arguments, dict):
        raise ValueError("UNKNOWN_TOOL")
    # No file/URL operations are accepted. Citation URLs inside canonical data
    # remain inert strings and are never fetched.
    if name == "preview_operations":
        allowed = {"inputs"}
    elif name == "tax_regime_lookup":
        allowed = {
            "state",
            "tax_year",
            "unit_count",
            "just_value",
            "prior_assessed_value",
            "ownership_change_or_qualifying_improvement",
            "non_school_millage",
            "school_millage",
        }
    else:
        allowed = set(inspect.signature(wrappers.PRODUCT_TOOL_IMPLEMENTATIONS[name]).parameters)
    if arguments.keys() - allowed:
        raise ValueError("INVALID_INPUT")
    count = 0

    def walk(value, depth=0):
        nonlocal count
        count += 1
        if depth > 32 or count > 100000:
            raise ValueError("INPUT_LIMIT")
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > 256:
                    raise ValueError("INVALID_INPUT")
                walk(child, depth + 1)
        elif isinstance(value, list):
            if len(value) > 10000:
                raise ValueError("INPUT_LIMIT")
            for child in value:
                walk(child, depth + 1)
        elif isinstance(value, str) and len(value) > 16000:
            raise ValueError("INPUT_LIMIT")

    walk(arguments)
    if len(canonical(arguments)) > MAX_INPUT:
        raise ValueError("INPUT_LIMIT")
    if name.startswith("underwrite") and isinstance(arguments.get("inputs"), dict):
        inputs = arguments["inputs"]
        grid = inputs.get("time_grid", {})
        if isinstance(grid, dict):
            first, last = grid.get("analysis_start_date"), grid.get("analysis_end_date")
            if all(
                isinstance(v, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v)
                for v in (first, last)
            ):
                months = (int(last[:4]) - int(first[:4])) * 12 + int(last[5:]) - int(first[5:]) + 1
                if not 1 <= months <= 600:
                    raise ValueError("INPUT_LIMIT")
        cohorts = inputs.get("unit_cohorts", [])
        if isinstance(cohorts, list) and len(cohorts) > 1000:
            raise ValueError("INPUT_LIMIT")
    if name == "underwrite_backsolve":
        iterations = arguments.get("max_iterations", 40)
        if type(iterations) is not int or not 1 <= iterations <= 80:
            raise ValueError("INPUT_LIMIT")


def preview_operations(inputs):
    """Import and review in disposable storage; never issue or grant approval."""
    from platworks.local_review.normalize import CATEGORIES
    from platworks.local_review.producers import operations_preview, producer_identity

    required = {
        "property",
        "period",
        "currency",
        "expense_convention",
        "unit_count",
        "actuals",
        "budgets",
        "snapshot",
    }
    if not isinstance(inputs, dict) or set(inputs) != required:
        return refusal("INVALID_INPUT")
    for role in ("actuals", "budgets"):
        if not isinstance(inputs[role], list):
            return refusal("INVALID_INPUT")
        for row in inputs[role]:
            if (
                not isinstance(row, dict)
                or set(row) != {"account_code", "account_name", "category", "amount"}
                or row["category"] not in CATEGORIES
            ):
                return refusal("INVALID_MAPPING")
    expected = producer_identity()
    result, _database = operations_preview(inputs, expected)
    result["provenance"] = {
        "service": "plat-operations",
        "entrypoint": "boxscore-exact review",
        "producer": expected["boxscore-exact"],
        "arithmetic_owner": "boxscore-exact",
        "retained": False,
    }
    return result


def calculate(name, arguments):
    """Worker entry point. Errors never echo input values, paths or tracebacks."""
    try:
        validate_request(name, arguments)
        result = (
            preview_operations(arguments.get("inputs"))
            if name == "preview_operations"
            else wrappers.call_product_tool(name, arguments)
        )
        if "error" in result:
            code = result["error"].get("code")
            return refusal(code if code in ERROR_CODES else "PRODUCER_REFUSAL")
        return annotate(name, arguments, result)
    except ImportError:
        return refusal("BACKEND_UNAVAILABLE")
    except Exception as error:
        code = str(error) if type(error) is ValueError else getattr(error, "code", "TOOL_FAILURE")
        return refusal(code if code in ERROR_CODES else "PRODUCER_REFUSAL")


def annotate(name, arguments, result):
    """Add source-review status without changing any producer metric."""
    if "error" in result:
        return result
    versions = {}
    for package in (
        "platworks",
        "plat-multifamily-underwriting",
        "plat-costmodel",
        "plat-harness",
        "plat-operations",
    ):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            pass
    result["scenario"] = {
        "contract_version": "plat.scenario/1",
        "input_status": "unverified_scenario",
        "human_approval": "not_granted",
        "certified": False,
        "input_sha256": sha256({"tool": name, "arguments": arguments}),
        "result_sha256": sha256(result),
        "producer_versions": versions,
        "assumptions": result.get(
            "effective_assumptions",
            {
                "basis": "Supplied arguments and producer defaults; source facts unverified.",
                "defaults": {"renovation_roi_threshold_pct": 15}
                if name == "renovation_roi" and arguments.get("threshold_pct") is None
                else {},
            },
        ),
    }
    return result


class ScenarioExecutor:
    """Two process slots, bounded pipes, kill on timeout/cancellation, no queue."""

    def __init__(self, *, slots=2, timeout=DEADLINE):
        self.slots = threading.BoundedSemaphore(slots)
        self.timeout = timeout

    async def call(self, name, arguments):
        try:
            validate_request(name, arguments)
            request = canonical({"tool": name, "arguments": arguments})
        except (ValueError, TypeError, RecursionError) as error:
            code = str(error)
            return refusal(code if code in ERROR_CODES | {"UNKNOWN_TOOL"} else "INVALID_INPUT")
        if not self.slots.acquire(blocking=False):
            return refusal("BUSY")
        try:
            with tempfile.TemporaryDirectory(prefix="plat-scenario-") as folder:
                # Only OS essentials and private temporary storage reach workers.
                env = {
                    key: os.environ[key]
                    for key in ("SYSTEMROOT", "WINDIR", "PATH")
                    if key in os.environ
                }
                env.update(TMPDIR=folder, TEMP=folder, TMP=folder, PYTHONDONTWRITEBYTECODE="1")
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-I",
                    "-B",
                    "-m",
                    "platworks.scenario_worker",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                    cwd=folder,
                    start_new_session=os.name != "nt",
                )
                try:

                    async def exchange():
                        async def write():
                            process.stdin.write(request)
                            await process.stdin.drain()
                            process.stdin.close()

                        writer = asyncio.create_task(write())
                        output = bytearray()
                        try:
                            while chunk := await process.stdout.read(65536):
                                output.extend(chunk)
                                if len(output) > MAX_OUTPUT:
                                    raise ValueError("OUTPUT_LIMIT")
                            await writer
                            await process.wait()
                            if process.returncode:
                                return refusal("PRODUCER_REFUSAL")
                            result = json.loads(output)
                            return (
                                result if isinstance(result, dict) else refusal("PRODUCER_REFUSAL")
                            )
                        finally:
                            writer.cancel()
                            await asyncio.gather(writer, return_exceptions=True)

                    return await asyncio.wait_for(exchange(), timeout=self.timeout)
                except TimeoutError:
                    return refusal("TIMEOUT")
                except (ValueError, OSError) as error:
                    return refusal(
                        "OUTPUT_LIMIT" if str(error) == "OUTPUT_LIMIT" else "PRODUCER_REFUSAL"
                    )
                finally:
                    # Kill the whole process group, including a Rust child left
                    # behind when a Python worker fails. Cleanup survives cancellation.
                    if os.name != "nt":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    elif process.returncode is None:
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                            check=False,
                        )
                    if process.returncode is None:
                        process.kill()
                    await asyncio.shield(process.wait())
        except OSError:
            return refusal("BACKEND_UNAVAILABLE")
        finally:
            self.slots.release()
