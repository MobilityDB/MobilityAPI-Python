"""MobilityAPI catalog-driven dispatcher package.

The MobilityAPI ingestion plan (docs/MEOS_API_INGESTION_PLAN.md) calls for
replacing the hand-written MEOS-dispatching endpoint modules with thin
dispatchers driven by the vendored MEOS-API catalog. This package is the
foundation: a `Dispatcher` class that loads the vendored catalog and exposes
``dispatch(function_name, params) -> Any`` for every stateless-exposable
MEOS function. Existing hand-written endpoints remain unchanged until they
are migrated module-by-module in follow-up PRs.
"""

from .dispatcher import Dispatcher, FunctionSignature

__all__ = ["Dispatcher", "FunctionSignature"]
