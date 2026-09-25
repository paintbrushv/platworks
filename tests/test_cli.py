"""Tests for the platworks CLI (thin click client).

Rules under test:

- The CLI is a thin client over the catalog / MCP server: it must not
  re-implement catalog logic (its results equal direct catalog calls).
- Exit codes are documented and stable: 0 success, 2 typed refusal
  (unknown component / unknown category), with an actionable message
  on stderr.
- ``--help`` works for the root command and every subcommand (doc-vs-CLI
  consistency gate).
- Console-script declarations in pyproject.toml must point at real
  importable callables (a missing entrypoint target passes source tests
  and fails only in a fresh venv — this test catches it earlier).
"""

import json
import os

import pytest
from click.testing import CliRunner

from platworks import catalog, cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def runner():
    return CliRunner()


def _invoke(runner, *args):
    result = runner.invoke(cli.main, list(args))
    return result


def test_root_help_exits_zero(runner):
    result = _invoke(runner, "--help")
    assert result.exit_code == 0
    assert "platworks" in result.output


def test_every_subcommand_has_help(runner):
    result = _invoke(runner, "--help")
    for sub in ("catalog", "get", "mcp", "demo", "landing"):
        assert sub in result.output, f"root help must advertise {sub}"
        sub_help = _invoke(runner, sub, "--help")
        assert sub_help.exit_code == 0, sub


def test_catalog_lists_all_public_components(runner):
    result = _invoke(runner, "catalog")
    assert result.exit_code == 0
    for name in ("plat-multifamily-underwriting", "plat-harness",
                 "plat-market-study-agent", "plat-operations", "geostack"):
        assert name in result.output
    assert "definitely-not-a-component" not in result.output


def test_catalog_json_matches_catalog_module_exactly(runner):
    result = _invoke(runner, "catalog", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == catalog.list_components()


def test_catalog_category_filter_matches_catalog_module(runner):
    result = _invoke(runner, "catalog", "--category", "geospatial", "--json")
    assert result.exit_code == 0
    assert json.loads(result.output) == catalog.list_components(category="geospatial")


def test_catalog_unknown_category_is_typed_refusal(runner):
    result = _invoke(runner, "catalog", "--category", "not-a-category")
    assert result.exit_code == 2
    assert "unknown category" in result.output.lower()
    for cat in catalog.CATEGORIES:
        assert cat in result.output


def test_catalog_private_components_make_no_public_claims(runner):
    result = _invoke(runner, "catalog", "--json")
    payload = json.loads(result.output)
    private = [c for c in payload if c["public"] is False]
    assert private, "catalog must include the private components"
    for c in private:
        assert c["repo"] is None
        assert c["description"] is None


def test_get_known_component_exit_zero(runner):
    result = _invoke(runner, "get", "geostack")
    assert result.exit_code == 0
    assert "https://github.com/paintbrushv/geostack" in result.output


def test_get_unknown_component_is_typed_refusal(runner):
    result = _invoke(runner, "get", "definitely-not-a-component")
    assert result.exit_code == 2
    assert "unknown component" in result.output.lower()
    assert "definitely-not-a-component" in result.output


def test_get_json_matches_catalog_module(runner):
    result = _invoke(runner, "get", "plat-harness", "--json")
    assert result.exit_code == 0
    assert json.loads(result.output) == catalog.get_component("plat-harness")


def test_mcp_command_invokes_server_main(monkeypatch, runner):
    called = {}
    from platworks import mcp_server

    monkeypatch.setattr(mcp_server, "main", lambda: called.setdefault("run", True))
    result = _invoke(runner, "mcp")
    assert result.exit_code == 0
    assert called.get("run") is True


def test_cli_output_carries_no_private_paths(runner):
    result = _invoke(runner, "catalog", "--json")
    assert "/home/" not in result.output
    assert "-uplift" not in result.output


def test_pyproject_scripts_point_at_importable_callables():
    """Console-script entrypoints must reference real modules/callables."""
    import tomllib

    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        data = tomllib.load(fh)
    scripts = data["project"]["scripts"]
    assert "platworks" in scripts
    assert "platworks-mcp" in scripts
    for entry in scripts.values():
        module_name, _, attr = entry.partition(":")
        module = __import__(module_name, fromlist=[attr])
        assert callable(getattr(module, attr)), entry


def test_declared_dependencies_cover_imports():
    """The direct imports of our modules must be declared dependencies."""
    import tomllib

    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        data = tomllib.load(fh)
    declared = {d.split(">=")[0].split("<")[0].split("[")[0].strip()
                for d in data["project"]["dependencies"]}
    declared |= {d.split(">=")[0].split("<")[0].split("[")[0].strip()
                 for d in data["project"]["optional-dependencies"]["dev"]}
    for module in (cli,):
        for name in ("click", "mcp"):
            assert name in declared, f"{name} must be declared for {module.__name__}"