"""platworks — umbrella package for the plat commercial-real-estate ecosystem.

Exposes a verified component catalog and an MCP server that serves it.

All data in this package is public metadata about sibling repositories
(verified against the GitHub API on 2026-09-24) or synthetic demo data.
No deal, tenant, or portfolio data ships in this package.
"""

__version__ = "0.1.0"

from platworks import catalog
from platworks.catalog import (
    UnknownCategoryError,
    UnknownComponentError,
    find_components,
    get_component,
    list_components,
)

__all__ = [
    "__version__",
    "catalog",
    "find_components",
    "get_component",
    "list_components",
    "UnknownCategoryError",
    "UnknownComponentError",
]