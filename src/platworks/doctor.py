"""Local installation diagnostics. Never report host paths or private data."""

import importlib
import importlib.metadata as metadata
import platform
import sys
from importlib.resources import files

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from platworks import __version__

ANALYSIS_VERSIONS = {
    "plat-multifamily-underwriting": "0.1.2",
    "plat-costmodel": "0.1.1",
    "plat-harness": "0.1.1",
    "plat-operations": "0.1.1",
}


def dependency_problems(analysis=False):
    """Check the installed dependency graph, including requested extras."""
    queue = [("platworks", frozenset({"analysis"}) if analysis else frozenset())]
    seen, problems = set(), set()
    environment = default_environment()
    while queue:
        name, extras = queue.pop()
        identity = (canonicalize_name(name), extras)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            requirements = metadata.requires(name) or []
        except metadata.PackageNotFoundError:
            problems.add(f"{name}: missing")
            continue
        for text in requirements:
            requirement = Requirement(text)
            if requirement.marker and not any(
                requirement.marker.evaluate({**environment, "extra": extra})
                for extra in extras | {""}
            ):
                continue
            try:
                version = metadata.version(requirement.name)
            except metadata.PackageNotFoundError:
                problems.add(f"{requirement.name}: missing")
                continue
            if not requirement.specifier.contains(version, prereleases=True):
                problems.add(f"{requirement.name}: incompatible version")
            queue.append((requirement.name, frozenset(requirement.extras)))
    return sorted(problems)


def diagnose(analysis=False):
    checks = []

    def check(name, operation, hint):
        try:
            details = operation()
        except Exception:
            # Diagnostics do not expose raw exceptions, configured paths, or
            # environment values. Detailed local debugging stays opt-in.
            checks.append({"name": name, "status": "failed", "hint": hint})
        else:
            checks.append({"name": name, "status": "passed", **(details or {})})

    def versions():
        expected = {"platworks": __version__, **(ANALYSIS_VERSIONS if analysis else {})}
        actual = {name: metadata.version(name) for name in expected}
        if actual != expected or metadata.version("mcp").split(".")[0] != "2":
            raise ValueError("incompatible installation")
        return {"packages": actual, "mcp": metadata.version("mcp")}

    install = "Install the candidate wheels with platworks[analysis]==0.1.4."
    check("versions", versions, install if analysis else "Reinstall platworks==0.1.4 with MCP 2.")

    def dependencies():
        problems = dependency_problems(analysis)
        if problems:
            return {
                "status": "failed",
                "problems": problems,
                "hint": "Reinstall with the tested dependency lock; run pip check.",
            }

    check("dependencies", dependencies, "Repair package metadata and run pip check.")
    check(
        "catalog_mcp",
        lambda: importlib.import_module("platworks.mcp_server") and {},
        "Reinstall platworks and its MCP 2 dependencies.",
    )
    if analysis:

        def resources():
            resources = {
                "engine": "schemas/deal_schema_v0_1.json",
                "plat_costmodel": "data/knowledge_base.yaml",
                "plat_harness": "samples_data/ops_snapshot.sqlite",
            }
            for package, resource in resources.items():
                if not files(package).joinpath(resource).is_file():
                    raise ValueError("missing packaged resource")
            from engine.version import ENGINE_VERSION
            from plat_harness.adapters.ops_review import CONTRACT_VERSION, ORACLE_OWNER

            if (
                ENGINE_VERSION != ANALYSIS_VERSIONS["plat-multifamily-underwriting"]
                or CONTRACT_VERSION != "ops-review/2.0.0"
                or ORACLE_OWNER != "boxscore::exact::variance"
            ):
                raise ValueError("incompatible contracts")
            return {"ops_review": CONTRACT_VERSION}

        check("resources_and_contracts", resources, install)
        for module in ("engine.mcp_server", "plat_costmodel.server"):
            check(module, lambda module=module: importlib.import_module(module) and {}, install)

        def operating_producer():
            from platworks.ops_oracle import calculate

            row = {
                "account_code": "4000",
                "account_name": "Synthetic rent",
                "category": "rental income",
                "amount": "0.10",
            }
            result = calculate([row, {**row, "amount": "0.20"}], [{**row, "amount": "0.29"}])
            bridge = result["result"]["noi_bridge"]
            if (
                bridge["actual_noi"] != "0.30"
                or bridge["noi_variance"] != "0.01"
                or result["producer"]["version"] != ANALYSIS_VERSIONS["plat-operations"]
            ):
                raise ValueError("producer mismatch")
            return {
                "contract": result["contract_version"],
                "version": result["producer"]["version"],
                "binary_sha256": result["producer"]["binary_sha256"],
            }

        check(
            "operating_producer",
            operating_producer,
            "Install the matching plat-operations wheel; verify any producer override/hash "
            "and that temporary executable files are allowed.",
        )
    tested_python = sys.version_info[:2] in {(3, 11), (3, 12)}
    if not tested_python:
        checks.append(
            {
                "name": "python_matrix",
                "status": "warning",
                "hint": "Use Python 3.11 or 3.12 for the verified release matrix.",
            }
        )
    status = (
        "incomplete"
        if any(c["status"] == "failed" for c in checks)
        else ("ready" if tested_python else "ready_with_warnings")
    )
    return {
        "contract_version": "plat.doctor/1",
        "profile": "analysis" if analysis else "catalog",
        "status": status,
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine().lower()}",
        "checks": checks,
    }
