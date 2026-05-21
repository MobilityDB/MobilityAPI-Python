"""Function invocation endpoint.

``POST /functions/{name}`` is the single entry point that converts an
HTTP request body into a Dispatcher call. The body is a JSON object whose
keys match the catalog's parameter names; opaque MEOS types (any
parameter the catalog labels with ``decode_per_param``) are decoded by
the :class:`WireCodec` before the dispatcher invokes the MEOS function,
and the return value is encoded back to a wire-friendly representation
on the way out.

The contract:

- Request body: ``{ "params": { "<arg>": <wire_value>, ... } }``
- Response body for serialised returns:
  ``{ "result": <wire_value>, "encoding": "mfjson"|"wkb"|... }``
- Response body for scalar returns:
  ``{ "result": <value>, "encoding": null }``

This is the minimal vocabulary that lets a thin HTTP client (Polars
notebook, Spark UDF, JavaScript map UI) treat every MEOS function the
same way — call by name with a JSON body, read a typed result.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class InvokeRequest(BaseModel):
    """Body of a POST /functions/{name} request."""

    params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Map of parameter name to wire value. Opaque MEOS types "
            "(Temporal*, STBox, Set, …) MUST be supplied as the encoded "
            "wire form named in the catalog's `decode_per_param`."
        ),
    )


class InvokeResponse(BaseModel):
    """Body of a POST /functions/{name} response."""

    result: Any = Field(..., description="The function return value.")
    encoding: str | None = Field(
        None,
        description=(
            "Encoding the result is delivered in. `null` for scalar "
            "(int / float / str / bool) returns; one of `mfjson` / "
            "`text` / `wkb` / `hexwkb` for serialised MEOS objects."
        ),
    )


@router.post(
    "/{name}",
    response_model=InvokeResponse,
    summary="Invoke a dispatcher-exposable MEOS function",
)
def invoke(name: str, body: InvokeRequest, request: Request) -> InvokeResponse:
    dispatcher = request.app.state.dispatcher
    codec = request.app.state.codec

    if not dispatcher.has(name):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Function `{name}` is not in the dispatcher catalog. "
                f"GET /catalog lists available functions."
            ),
        )

    sig = dispatcher.signature(name)

    # 1. Decode opaque MEOS-type parameters via the codec, leaving
    #    scalar parameters untouched.
    decoded: dict[str, Any] = {}
    for key, value in body.params.items():
        encoding = sig.decode_per_param.get(key)
        if encoding:
            try:
                decoded[key] = codec.decode(encoding, value)
            except KeyError as e:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Parameter `{key}` claims encoding `{encoding}` "
                        f"but the WireCodec has no decoder for it."
                    ),
                ) from e
        else:
            decoded[key] = value

    # 2. Dispatch — surfaces KeyError (unknown name, caught above) and
    #    TypeError (missing / extra params) as 400 errors.
    try:
        result = dispatcher.dispatch(name, decoded)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 3. Encode the result if the catalog labels it with an encoding.
    if sig.encode_return:
        try:
            wire_result = codec.encode(sig.encode_return, result)
        except KeyError as e:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Result claims encoding `{sig.encode_return}` "
                    f"but the WireCodec has no encoder for it."
                ),
            ) from e
        return InvokeResponse(result=wire_result, encoding=sig.encode_return)

    return InvokeResponse(result=result, encoding=None)
