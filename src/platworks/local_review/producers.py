"""Bounded calls to the installed financial owners, bound to reviewed code."""

import importlib
import importlib.metadata
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from platworks.ops_oracle import (
    OpsProducerError,
    _run_bounded,
    _verified_binary,
    producer_path,
)

from .common import decode, digest, encode, identity, refuse


def producer_identity():
    """Content identities work for installed wheels and explicitly local development."""
    packages = {}
    for name, distribution in (
        ("platworks", "platworks"),
        ("engine", "plat-multifamily-underwriting"),
        ("plat_harness", "plat-harness"),
    ):
        module = importlib.import_module(name)
        root = Path(module.__file__).resolve().parent
        contents = {}
        for path in sorted(root.rglob("*")):
            if path.suffix in {".py", ".json", ".html", ".js", ".css"} and path.is_file():
                contents[str(path.relative_to(root))] = digest(path.read_bytes())
        packages[name] = {
            "version": importlib.metadata.version(distribution),
            "content_sha256": identity(contents),
        }
    packages["boxscore-exact"] = {
        "version": importlib.metadata.version("plat-operations"),
        "binary_sha256": digest(producer_path().read_bytes()),
    }
    packages["runtime"] = {
        "python": platform.python_version(),
        "executable_sha256": digest(Path(sys.executable).read_bytes()),
        "jsonschema": importlib.metadata.version("jsonschema"),
    }
    return packages


def ensure_identity(expected):
    if producer_identity() != expected:
        refuse("STALE_PRODUCER", "Installed code changed. Prepare and review a new draft.")


def acquisition_run(inputs, policy, expected):
    ensure_identity(expected)
    request = encode({"inputs": inputs, "downside": policy["downside"], "identity": expected})
    try:
        completed = _run_bounded(
            [sys.executable, "-I", "-m", "platworks.local_review.worker"], request, timeout=60
        )
    except subprocess.TimeoutExpired:
        refuse("ENGINE_TIMEOUT", "The engine exceeded 60 seconds; no report was issued.")
    except (OSError, OpsProducerError):
        refuse("ENGINE_FAILED", "Cannot run the installed engine within the local limits.")
    response = decode(completed.stdout)
    if completed.returncode or response.get("status") != "calculated":
        refuse(
            response.get("code", "ENGINE_FAILED"),
            "The engine refused these assumptions. Correct the input or downside policy.",
        )
    ensure_identity(expected)
    if response.get("identity") != expected:
        refuse("STALE_PRODUCER", "Worker identity differs from the reviewed code.")
    return response["result"]


def _native(executable, *args):
    try:
        completed = _run_bounded([str(executable), *map(str, args)], b"", timeout=60)
    except subprocess.TimeoutExpired:
        refuse("PRODUCER_TIMEOUT", "The operating producer exceeded 60 seconds.")
    except (OSError, OpsProducerError):
        refuse("PRODUCER_FAILED", "The installed operating producer could not complete.")
    result = decode(completed.stdout)
    if completed.returncode:
        code = result.get("error", {}).get("code", "PRODUCER_REFUSAL")
        refuse(
            code,
            "The operating producer refused the supplied period. Check its layout, "
            "money precision, unit counts, mapping and correction identity.",
        )
    if result.get("contract_version") != "plat.ops/1":
        refuse("PRODUCER_CONTRACT", "The operating producer returned a different contract.")
    return result


def operations_preview(data, expected, *, parent_database=None, parent_revision=None, reason=""):
    ensure_identity(expected)
    with tempfile.TemporaryDirectory(prefix="plat-local-review-") as folder:
        work = Path(folder)
        database, inputs = work / "period.sqlite", work / "inputs.json"
        inputs.write_bytes(encode(data))
        with _verified_binary(producer_path()) as (executable, fingerprint):
            if fingerprint != expected["boxscore-exact"]["binary_sha256"]:
                refuse("STALE_PRODUCER", "The installed Rust producer changed.")
            if parent_database is None:
                _native(executable, "init", "--database", database)
            else:
                database.write_bytes(parent_database)
            args = ["import", "--database", database, "--input", inputs]
            if parent_revision:
                args.extend(["--supersedes", parent_revision, "--reason", reason])
            revision = _native(executable, *args)["revision_id"]
            result = _native(executable, "review", "--database", database, "--revision", revision)
        raw = database.read_bytes()
    ensure_identity(expected)
    return result, raw


def operations_issue(raw, preview, expected):
    ensure_identity(expected)
    with tempfile.TemporaryDirectory(prefix="plat-local-issue-") as folder:
        database = Path(folder) / "period.sqlite"
        database.write_bytes(raw)
        with _verified_binary(producer_path()) as (executable, fingerprint):
            if fingerprint != expected["boxscore-exact"]["binary_sha256"]:
                refuse("STALE_PRODUCER", "The installed Rust producer changed.")
            current = _native(
                executable, "review", "--database", database, "--revision", preview["revision_id"]
            )
            if current != preview:
                refuse("STALE_REVIEW", "The operating result differs from the reviewed result.")
            issued = _native(
                executable, "issue", "--database", database, "--revision", preview["revision_id"]
            )
        output = database.read_bytes()
    ensure_identity(expected)
    return issued, output
