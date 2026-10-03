"""Bounded client for the authoritative Rust ``boxscore-exact`` producer.

The host installs the binary and may pin its SHA-256. Requests contain only
GL rows; tool inputs cannot choose an executable, arguments, or file paths.
There is no Python financial fallback.
"""

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

CONTRACT_VERSION = "plat.ops/1"
ORACLE_OWNER = "boxscore::exact::variance"
ORACLE_FUNCTIONS = ("compute",)
ORACLE_ROW_KEYS = frozenset({"account_code", "account_name", "category", "amount"})
BY_ACCOUNT_KEYS = frozenset({"account_code", "account_name", "category",
                             "actual", "budget", "variance"})
NOI_BRIDGE_KEYS = frozenset({"actual_revenue", "budget_revenue", "revenue_variance",
                            "actual_expenses", "budget_expenses", "expense_variance",
                            "actual_noi", "budget_noi", "noi_variance",
                            "unmapped_actual", "unmapped_budget"})
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 60
_MONEY = re.compile(r"-?(0|[1-9][0-9]{0,16})\.[0-9]{2}\Z")


class OpsProducerError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _fail(code, message):
    raise OpsProducerError(code, message)


def _money(value):
    if not isinstance(value, str) or not _MONEY.fullmatch(value):
        _fail("INVALID_CONTRACT", "Operating producer returned invalid money.")
    # Validate the integer boundary; this performs no financial calculation.
    if abs(int(value.replace(".", ""))) > 9223372036854775807:
        _fail("INVALID_CONTRACT", "Operating producer exceeded the cent range.")


def producer_path():
    """Find the host override, installed wheel binary, or PATH executable."""
    configured = os.environ.get("PLAT_BOXSCORE_EXACT_BIN")
    if configured:
        binary = shutil.which(configured)
        if binary is None:
            _fail("BACKEND_UNAVAILABLE", "Configured boxscore-exact executable is unavailable.")
        return Path(binary)
    try:
        distribution = importlib.metadata.distribution("plat-operations")
    except importlib.metadata.PackageNotFoundError:
        distribution = None
    if distribution:
        name = "boxscore-exact.exe" if os.name == "nt" else "boxscore-exact"
        for item in distribution.files or ():
            if item.name == name:
                binary = Path(distribution.locate_file(item))
                if binary.is_file() and os.access(binary, os.X_OK):
                    return binary.resolve()
        _fail("BACKEND_UNAVAILABLE", "Reinstall plat-operations: its native executable is missing.")
    binary = shutil.which("boxscore-exact")
    if binary is None:
        _fail("BACKEND_UNAVAILABLE", "Install platworks[analysis] or configure boxscore-exact.")
    return Path(binary)


def _run_bounded(args, request, *, timeout):
    """Drain both pipes with bounded memory and terminate on excess output."""
    deadline = time.monotonic() + timeout
    output = bytearray()
    failed = threading.Event()
    # A private, automatically removed input file avoids blocking on stdin
    # while a malfunctioning producer fills one of its output pipes.
    with tempfile.TemporaryFile() as source:
        source.write(request)
        source.seek(0)
        with subprocess.Popen(args, stdin=source, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, bufsize=0) as process:
            def drain(stream, retain):
                total = 0
                try:
                    while chunk := stream.read(65536):
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            failed.set()
                            return
                        if retain:
                            output.extend(chunk)
                except (OSError, ValueError):
                    failed.set()

            readers = [threading.Thread(target=drain, args=(stream, retain), daemon=True)
                       for stream, retain in ((process.stdout, True), (process.stderr, False))]
            for reader in readers:
                reader.start()
            try:
                while True:
                    if failed.is_set():
                        _fail("INVALID_CONTRACT", "Operating producer output exceeded its "
                              "limit or could not be read.")
                    if process.poll() is not None and not any(r.is_alive() for r in readers):
                        return subprocess.CompletedProcess(args, process.returncode, bytes(output))
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(args, timeout)
                    failed.wait(min(remaining, 0.01))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                for reader in readers:
                    reader.join(timeout=1)


@contextmanager
def _verified_binary(binary):
    """Execute a private copy of the exact bytes whose digest is reported."""
    with tempfile.TemporaryDirectory(prefix="plat-producer-") as directory:
        executable = Path(directory) / ("boxscore-exact.exe" if os.name == "nt"
                                        else "boxscore-exact")
        digest = hashlib.sha256()
        with Path(binary).open("rb") as source, executable.open("xb") as target:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                target.write(chunk)
        executable.chmod(0o500)
        fingerprint = digest.hexdigest()
        expected = os.environ.get("PLAT_BOXSCORE_EXACT_SHA256")
        if expected and expected != fingerprint:
            _fail("PRODUCER_MISMATCH", "Operating producer does not match its configured hash.")
        yield executable, fingerprint


def calculate(actuals, budgets):
    """Return the verified protocol envelope, including producer provenance."""
    binary = producer_path()
    try:
        request = json.dumps({"contract_version": CONTRACT_VERSION, "operation": "variance",
                              "currency": "USD", "expense_convention": "positive_costs",
                              "actuals": actuals, "budgets": budgets},
                             allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError):
        _fail("INVALID_INPUT", "Cannot serialize the GL request.")
    if len(request) > MAX_REQUEST_BYTES:
        _fail("INPUT_LIMIT", "Operating request exceeds 2 MiB.")
    try:
        with _verified_binary(binary) as (path, fingerprint):
            completed = _run_bounded([str(path), "protocol"], request, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _fail("PRODUCER_TIMEOUT", "Operating producer exceeded its time limit.")
    except OSError:
        _fail("BACKEND_UNAVAILABLE", "Cannot execute the configured operating producer.")
    try:
        payload = json.loads(completed.stdout)
    except (ValueError, UnicodeError):
        _fail("INVALID_CONTRACT", "Operating producer returned invalid JSON.")
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        _fail("INVALID_CONTRACT", "Operating producer contract does not match.")
    if completed.returncode == 2 and payload.get("status") == "refused":
        error = payload.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        if code in {"INVALID_INPUT", "MONEY_PRECISION", "MONEY_OVERFLOW", "INPUT_LIMIT",
                    "CONTRACT_MISMATCH", "EXCESS_PRECISION", "ACCOUNT_MAPPING_CONFLICT"}:
            _fail(code, "Operating producer refused the financial input.")
        _fail("PRODUCER_REFUSAL", "Operating producer refused the request.")
    if completed.returncode != 0 or payload.get("status") not in {"calculated", "review_required"}:
        _fail("INVALID_CONTRACT", "Operating producer failed or returned an invalid status.")
    producer = payload.get("producer")
    if (not isinstance(producer, dict) or producer.get("name") != "boxscore-exact"
            or producer.get("arithmetic") != "checked_i64_cents"
            or payload.get("input_sha256") != hashlib.sha256(request).hexdigest()):
        _fail("INVALID_CONTRACT", "Operating producer provenance does not match the request.")
    result = payload.get("result")
    if (not isinstance(result, dict)
            or set(result) != {"by_account", "noi_bridge", "review_reasons"}):
        _fail("INVALID_CONTRACT", "Operating producer returned an invalid result shape.")
    rows, bridge, reasons = result["by_account"], result["noi_bridge"], result["review_reasons"]
    if (not isinstance(rows, list) or not isinstance(bridge, dict)
            or set(bridge) != NOI_BRIDGE_KEYS or not isinstance(reasons, list)
            or any(not isinstance(reason, str) for reason in reasons)):
        _fail("INVALID_CONTRACT", "Operating producer returned an invalid variance shape.")
    for row in rows:
        if not isinstance(row, dict) or set(row) != BY_ACCOUNT_KEYS:
            _fail("INVALID_CONTRACT", "Operating producer returned an invalid account shape.")
        for key in ("actual", "budget", "variance"):
            _money(row[key])
        if any(not isinstance(row[key], str) for key in ORACLE_ROW_KEYS - {"amount"}):
            _fail("INVALID_CONTRACT", "Operating producer returned an invalid account identity.")
    for value in bridge.values():
        _money(value)
    payload["producer"]["binary_sha256"] = fingerprint
    return payload


def variance_oracle(actuals, budgets):
    """Adapt the protocol to the harness's closed variance result shape."""
    result = calculate(actuals, budgets)["result"]
    if result["review_reasons"]:
        # The legacy seam cannot carry producer review flags: refuse instead
        # of silently discarding a financial ambiguity.
        _fail("REVIEW_REQUIRED", "Operating signs require review in boxscore-exact.")
    return {"by_account": result["by_account"], "noi_bridge": result["noi_bridge"]}


def compute_account_variances(actuals, budgets):
    return variance_oracle(actuals, budgets)["by_account"]


def compute_noi_bridge(actuals, budgets):
    return variance_oracle(actuals, budgets)["noi_bridge"]


class BoundOracle:
    """Per-review binding retains provenance without shared mutable state."""

    def __init__(self):
        self.provenance = None

    def __call__(self, actuals, budgets):
        payload = calculate(actuals, budgets)
        result = payload["result"]
        if result["review_reasons"]:
            _fail("REVIEW_REQUIRED", "Operating signs require review in boxscore-exact.")
        self.provenance = {"contract_version": CONTRACT_VERSION,
                           "input_sha256": payload["input_sha256"],
                           **payload["producer"]}
        return {"by_account": result["by_account"], "noi_bridge": result["noi_bridge"]}


# Explicit host module binding for plat-harness CLI --variance-module.
compute = variance_oracle
