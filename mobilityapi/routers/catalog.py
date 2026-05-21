"""Catalog introspection endpoints.

The MobilityAPI ingestion pipeline (steps 1–3) lands the MEOS catalog as
``vendor/meos-api/meos-idl.json``. Step 4's :class:`Dispatcher` loads
that catalog and filters it to the *exposable* subset (functions whose
catalog entry has ``network.exposable=true`` or is missing).

This router exposes that subset over HTTP so callers can discover what
the deployed instance can dispatch. Two routes:

- ``GET /catalog``         — list function names + categories.
- ``GET /catalog/{name}``  — full signature for one function.

Both routes are read-only and never call into MEOS.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("", summary="List dispatcher-exposable MEOS function names")
def list_functions(request: Request) -> dict:
    dispatcher = request.app.state.dispatcher
    items = [
        {
            "name": sig.name,
            "category": sig.category,
            "return_type": sig.return_type,
        }
        for sig in dispatcher.signatures()
    ]
    items.sort(key=lambda x: x["name"])
    return {"count": len(items), "functions": items}


@router.get("/{name}", summary="Full signature for one MEOS function")
def get_function(name: str, request: Request) -> dict:
    dispatcher = request.app.state.dispatcher
    if not dispatcher.has(name):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Function `{name}` is not in the dispatcher catalog. "
                f"GET /catalog lists available functions."
            ),
        )
    sig = dispatcher.signature(name)
    return {
        "name": sig.name,
        "category": sig.category,
        "params": sig.params,
        "return_type": sig.return_type,
        "decode_per_param": sig.decode_per_param,
        "encode_return": sig.encode_return,
        "description": sig.description,
    }
