"""Test-path bootstrap: make the src/ layout importable without an install."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


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
