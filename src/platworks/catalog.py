"""Verified catalog of platworks ecosystem components.

Single source of truth for what exists in the ecosystem and what may be
claimed publicly. Rules:

- Every public component entry was verified against the GitHub API
  (``https://api.github.com/repos/paintbrushv/<name>``) on 2026-09-24;
  descriptions below are copied from the verified GitHub descriptions.
- Private components (repositories named ``*-uplift`` or not yet
  published) carry ``public: False`` and make **no** public claims:
  ``repo`` and ``description`` are ``None``.
- All returned records are deep copies; mutating a result can never
  leak into the module-level registry (see the isolation tests).
"""

import copy

CATEGORIES = (
    "underwriting_engine",
    "control_plane",
    "market_study",
    "asset_operations",
    "geospatial",
    "orchestration",
    "cost_modeling",
)

LANGUAGES = (
    "Python",
    "Rust",
)

#: Closed status vocabulary. Every component records one of these.
STATUSES = (
    "public",
    "private",
)

_ORG = "https://github.com/paintbrushv"

# Fields: name, category, language, license, public, repo, description,
# status, tags. Public descriptions are verbatim from the GitHub API.
# Private entries deliberately omit repo/description: no unverified claims.
_REGISTRY = [
    {
        "name": "plat-multifamily-underwriting",
        "category": "underwriting_engine",
        "language": "Python",
        "license": "Apache-2.0",
        "public": True,
        "repo": f"{_ORG}/plat-multifamily-underwriting",
        "description": (
            "Deterministic multifamily underwriting engine. Numbers come "
            "from the engine, never from a model."
        ),
        "status": "public",
        "tags": ["underwriting", "deterministic", "cashflow", "engine"],
    },
    {
        "name": "plat-harness",
        "category": "control_plane",
        "language": "Python",
        "license": "Apache-2.0",
        "public": True,
        "repo": f"{_ORG}/plat-harness",
        "description": (
            "Agent-agnostic control plane for multifamily underwriting and "
            "asset operations. The model is rented; certified numbers come "
            "from tools."
        ),
        "status": "public",
        "tags": ["control-plane", "acceptance", "mcp", "agents"],
    },
    {
        "name": "plat-market-study-agent",
        "category": "market_study",
        "language": "Python",
        "license": "Apache-2.0",
        "public": True,
        "repo": f"{_ORG}/plat-market-study-agent",
        "description": (
            "Market Study Agent: expert-level multifamily market studies "
            "with strict public-vs-licensed data separation. "
            "Synthetic/config-driven validation only."
        ),
        "status": "public",
        "tags": ["market-study", "comps", "citations"],
    },
    {
        "name": "plat-operations",
        "category": "asset_operations",
        "language": "Rust",
        "license": "Apache-2.0",
        "public": True,
        "repo": f"{_ORG}/plat-operations",
        "description": (
            "Local-first multifamily NOI variance intelligence harness "
            "(BOXSCORE). Numbers come from the deterministic engine; "
            "synthetic sample data only."
        ),
        "status": "public",
        "tags": ["operations", "noi", "variance", "boxscore"],
    },
    {
        "name": "geostack",
        "category": "geospatial",
        "language": "Python",
        "license": "Apache-2.0",
        "public": True,
        "repo": f"{_ORG}/geostack",
        "description": (
            "PostGIS/GIS utility layer for multifamily market analytics. "
            "Synthetic fixtures only."
        ),
        "status": "public",
        "tags": ["postgis", "gis", "h3", "census"],
    },
    {
        "name": "plat-agent",
        "category": "orchestration",
        "language": "Python",
        "license": "Apache-2.0",
        "public": False,
        "repo": None,
        "description": None,
        "status": "private",
        "tags": ["orchestration", "mcp"],
    },
    {
        "name": "plat-costmodel",
        "category": "cost_modeling",
        "language": "Python",
        "license": "Apache-2.0",
        "public": False,
        "repo": None,
        "description": None,
        "status": "private",
        "tags": ["cost-modeling", "capex"],
    },
    {
        "name": "plat-submarket-atlas",
        "category": "geospatial",
        "language": "Python",
        "license": "Apache-2.0",
        "public": False,
        "repo": None,
        "description": None,
        "status": "private",
        "tags": ["submarkets", "atlas"],
    },
    {
        "name": "plat-supply-demand",
        "category": "market_study",
        "language": "Python",
        "license": "Apache-2.0",
        "public": False,
        "repo": None,
        "description": None,
        "status": "private",
        "tags": ["supply", "demand", "pipeline"],
    },
]

_INDEX = {entry["name"]: entry for entry in _REGISTRY}


class UnknownComponentError(KeyError):
    """Raised when a component name is not in the catalog."""


class UnknownCategoryError(ValueError):
    """Raised when a category is not in the closed category vocabulary."""


def _isolated(entry):
    return copy.deepcopy(entry)


def list_components(category=None):
    """Return isolated copies of all catalog entries, optionally filtered."""
    if category is not None and category not in CATEGORIES:
        raise UnknownCategoryError(f"unknown category: {category}")
    return [
        _isolated(entry)
        for entry in _REGISTRY
        if category is None or entry["category"] == category
    ]


def get_component(name):
    """Return an isolated copy of one catalog entry by exact name."""
    if name not in _INDEX:
        raise UnknownComponentError(f"unknown component: {name}")
    return _isolated(_INDEX[name])


def find_components(category=None):
    """Return isolated catalog entries filtered by category."""
    return list_components(category=category)


def search_components(query):
    """Return isolated entries matching a case-insensitive substring.

    Matching fields: name, category, language, tags, and description
    (descriptions are only searched where they exist — private entries
    carry ``None`` and never match on description).
    """
    q = query.strip().lower()
    matches = []
    for entry in _REGISTRY:
        haystack = " ".join(
            [
                entry["name"],
                entry["category"],
                entry["language"],
                entry["description"] or "",
                " ".join(entry["tags"]),
            ]
        )
        if q in haystack.lower():
            matches.append(_isolated(entry))
    return matches


def category_counts():
    """Return an ordered list of {category, public, private, total} dicts.

    The order follows CATEGORIES; categories with no entries are still
    reported (total 0) so the closed vocabulary is always complete.
    """
    counts = []
    for category in CATEGORIES:
        entries = [e for e in _REGISTRY if e["category"] == category]
        counts.append(
            {
                "category": category,
                "public": sum(1 for e in entries if e["public"]),
                "private": sum(1 for e in entries if not e["public"]),
                "total": len(entries),
            }
        )
    return counts


def counts():
    """Return headline catalog counts: public, private, and total."""
    return {
        "public": sum(1 for e in _REGISTRY if e["public"]),
        "private": sum(1 for e in _REGISTRY if not e["public"]),
        "total": len(_REGISTRY),
    }