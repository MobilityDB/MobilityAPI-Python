"""MobilityAPI catalog-driven dispatcher package.

The MobilityAPI ingestion plan (docs/MEOS_API_INGESTION_PLAN.md) calls for
replacing the hand-written MEOS-dispatching endpoint modules with thin
dispatchers driven by the vendored MEOS-API catalog. This package provides
the three foundation pieces the migrating endpoints share:

- ``Dispatcher``     — catalog-driven function lookup + invocation.
- ``resolvers``      — pick the MEOS function implementation
                       (production: PyMEOS; tests: explicit stubs).
- ``wire``           — decode HTTP wire values to PyMEOS objects;
                       encode PyMEOS results back to wire values.

Existing hand-written endpoints remain unchanged until they are migrated
module-by-module in follow-up PRs.
"""

from .dispatcher import Dispatcher, FunctionSignature
from .resolvers import stub_resolver, pymeos_resolver, default_resolver
from .wire import (
    WireCodec, stub_codec, pymeos_codec,
    ENCODING_MFJSON, ENCODING_TEXT, ENCODING_WKB, ENCODING_HEXWKB,
)

__all__ = [
    "create_app",
    "Dispatcher", "FunctionSignature",
    "stub_resolver", "pymeos_resolver", "default_resolver",
    "WireCodec", "stub_codec", "pymeos_codec",
    "ENCODING_MFJSON", "ENCODING_TEXT", "ENCODING_WKB", "ENCODING_HEXWKB",
]


# Lazy-load `create_app` (PEP 562) so importing `mobilityapi` does NOT pull
# in FastAPI/Starlette/Pydantic.  Callers that need the HTTP routes import
# `from mobilityapi import create_app` and pay the FastAPI dep then; tests
# that only exercise Dispatcher/Resolvers/WireCodec do not need it on the
# import path.
def __getattr__(name):  # noqa: D401 - module-level descriptor
    if name == "create_app":
        from .app import create_app as _create_app
        return _create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
