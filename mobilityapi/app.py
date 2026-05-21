"""FastAPI application factory for the MobilityAPI Dispatcher framework.

Exposes the catalog-driven Dispatcher + WireCodec foundation (steps 3 / 4
of the ingestion plan) as HTTP routes. Two router groups:

- ``/catalog/*``    — read-only introspection (list functions, fetch one).
- ``/functions/*``  — invoke a MEOS function from a JSON request body.

The app is built by :func:`create_app`, which takes injected
``Dispatcher`` and ``WireCodec`` instances. Production wires both to
PyMEOS; tests pass stubs.  No global singletons; every dependency is
explicit, which keeps the request-time hot path resolver-agnostic and
the test surface fast.
"""

from __future__ import annotations

from fastapi import FastAPI

from .dispatcher import Dispatcher
from .routers import catalog, functions
from .wire import WireCodec


def create_app(
    dispatcher: Dispatcher,
    codec: WireCodec,
    *,
    title: str = "MobilityAPI",
    version: str = "0.1.0",
) -> FastAPI:
    """Build the FastAPI app from the injected dispatcher + codec.

    :param dispatcher: ``Dispatcher`` instance bound to a resolver
        (``stub_resolver`` for tests, ``pymeos_resolver`` for prod).
    :param codec: ``WireCodec`` mapping the catalog's per-parameter
        encoding labels (``mfjson`` / ``text`` / ``wkb`` / ``hexwkb``)
        to Python factory + serialiser callables.

    The dispatcher and codec are exposed to routers via
    ``app.state.dispatcher`` and ``app.state.codec`` so router
    dependencies can read them without a global.
    """
    app = FastAPI(
        title=title,
        version=version,
        description=(
            "Catalog-driven dispatcher for MEOS functions, exposed over "
            "HTTP. Every route delegates to the MobilityAPI Dispatcher; "
            "no MEOS C code is invoked outside the dispatcher resolver."
        ),
    )
    app.state.dispatcher = dispatcher
    app.state.codec = codec

    app.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
    app.include_router(functions.router, prefix="/functions", tags=["functions"])

    return app
