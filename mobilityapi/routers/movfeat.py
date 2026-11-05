"""OGC API – Moving Features read routes generated over the MEOS dispatcher.

The "pure MEOS round-trip" resources — the temporal-geometry sequence and its
derived velocity / distance queries, and a stored temporal property — are
served by dispatching the matching MEOS function from the MEOS-API catalog
through the ``Dispatcher`` + ``WireCodec``, then shaping the MF-JSON result as
the OGC envelope. The collection / feature lifecycle, persistence and the
GeoJSON envelope have no MEOS equivalent and stay hand-written.

OGC resource → MEOS catalog function (the alignment map):

    tgsequence (export)        → temporal_as_mfjson
    tgsequence/{tg}/velocity   → tpoint_speed
    tgsequence/{tg}/distance   → tpoint_cumulative_length
    tproperties/{name}         → temporal_as_mfjson

``acceleration`` returns 501: with linearly interpolated position the speed is
piecewise-constant, so its derivative is zero within each segment and undefined
at the vertices; the value is not approximated.

A ``FeatureStore`` port abstracts the database read so the routes are testable
with stubs; production wires it to PyMEOS + psycopg2. Writes (sub-trajectory
append, temporal-property creation) remain on the hand-written path until the
catalog's input-function shapes are confirmed against a live MEOS.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, HTTPException, Request

#: OGC derived measure → the MEOS catalog function that computes it.
DERIVED_FN = {"velocity": "tpoint_speed", "distance": "tpoint_cumulative_length"}
#: MEOS serialiser used to export a temporal value as MF-JSON.
EXPORT_FN = "temporal_as_mfjson"


@runtime_checkable
class FeatureStore(Protocol):
    """Database port. Values are MF-JSON (the wire shape the codec decodes).

    Production wires this to PyMEOS + psycopg2; tests pass a stub.
    """

    def get_trajectory(self, cid: str, fid: str) -> Any | None: ...
    def get_property(self, cid: str, fid: str, name: str) -> Any | None: ...


router = APIRouter()


def _ctx(request: Request):
    state = request.app.state
    store = getattr(state, "feature_store", None)
    if store is None:
        raise HTTPException(501, "no FeatureStore is wired into the app")
    return state.dispatcher, state.codec, store


def _dispatch_unary(dispatcher, codec, fn: str, value_mfjson: Any) -> Any:
    """Decode an MF-JSON temporal value, dispatch a single-temporal-argument
    MEOS function, and re-encode the result as MF-JSON."""
    if not dispatcher.has(fn):
        raise HTTPException(501, f"MEOS function `{fn}` is not in the MEOS-API catalog")
    sig = dispatcher.signature(fn)
    if not sig.params:
        raise HTTPException(500, f"MEOS function `{fn}` has no parameters to dispatch")
    pname = sig.params[0]["name"]
    arg = codec.decode("mfjson", value_mfjson)
    result = dispatcher.dispatch(fn, {pname: arg})
    return codec.encode("mfjson", result)


def _temporal_property(name: str, type_token: str, mfjson: Any, self_href: str) -> dict:
    """Shape a MEOS MF-JSON temporal value as an OGC ``temporalProperty``."""
    seq = mfjson if isinstance(mfjson, list) else [mfjson]
    return {
        "name": name,
        "type": type_token,
        "valueSequence": seq,
        "links": [{"rel": "self", "href": self_href}],
    }


@router.get("/collections/{cid}/items/{fid}/tgsequence", summary="Temporal geometry (MF-JSON)")
def get_tgsequence(cid: str, fid: str, request: Request) -> Any:
    dispatcher, codec, store = _ctx(request)
    trip = store.get_trajectory(cid, fid)
    if trip is None:
        raise HTTPException(404, "feature not found")
    return _dispatch_unary(dispatcher, codec, EXPORT_FN, trip)


@router.get(
    "/collections/{cid}/items/{fid}/tgsequence/{tg}/{measure}",
    summary="Derived temporal-geometry query: velocity | distance (acceleration → 501)",
)
def get_derived(cid: str, fid: str, tg: str, measure: str, request: Request) -> dict:
    if measure == "acceleration":
        raise HTTPException(
            501,
            "acceleration is not derivable: linearly interpolated position gives a "
            "piecewise-constant speed, whose derivative is zero within each segment "
            "and undefined at the vertices",
        )
    fn = DERIVED_FN.get(measure)
    if fn is None:
        raise HTTPException(404, f"unknown temporal-geometry query: {measure}")
    dispatcher, codec, store = _ctx(request)
    trip = store.get_trajectory(cid, fid)
    if trip is None:
        raise HTTPException(404, "feature not found")
    out = _dispatch_unary(dispatcher, codec, fn, trip)
    return _temporal_property(measure, "TReal", out, request.url.path)


@router.get(
    "/collections/{cid}/items/{fid}/tproperties/{name}",
    summary="A stored temporal property as an OGC temporalProperty",
)
def get_tproperty(cid: str, fid: str, name: str, request: Request) -> dict:
    dispatcher, codec, store = _ctx(request)
    value = store.get_property(cid, fid, name)
    if value is None:
        raise HTTPException(404, f"unknown temporal property: {name}")
    out = _dispatch_unary(dispatcher, codec, EXPORT_FN, value)
    return _temporal_property(name, "TReal", out, request.url.path)
