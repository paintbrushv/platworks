"""Test fixtures and an explicit installed-wheel acceptance guard."""

import json
from importlib.metadata import distribution
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--require-installed-wheel", action="store_true",
                     help="Refuse tests importing platworks from checkout/editable source")


def pytest_sessionstart(session):
    if not session.config.getoption("--require-installed-wheel"):
        return
    import platworks

    installed = distribution("platworks")
    actual = Path(platworks.__file__).resolve()
    expected = Path(installed.locate_file("platworks/__init__.py")).resolve()
    direct_url = json.loads(installed.read_text("direct_url.json") or "{}")
    if actual != expected or direct_url.get("dir_info", {}).get("editable"):
        raise pytest.UsageError("Installed-wheel suite imported checkout/editable source")
    print(f"Installed-wheel suite imports: {actual}")


@pytest.fixture
def private_component(monkeypatch):
    """Keep private-entry guards covered after the real components go public."""
    from platworks import catalog

    entry = {
        "name": "synthetic-private-component", "category": "orchestration",
        "language": "Python", "license": "Apache-2.0", "public": False,
        "repo": None, "description": None, "status": "private", "tags": [],
    }
    monkeypatch.setattr(catalog, "_REGISTRY", [*catalog._REGISTRY, entry])
    monkeypatch.setitem(catalog._INDEX, entry["name"], entry)
    return entry["name"]
