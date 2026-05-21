"""HTTP-surface tests for the MobilityAPI FastAPI app.

The app is exercised via Starlette's ``TestClient``. The Dispatcher is
built against a tiny in-test catalog and a stub resolver; the
WireCodec is a stub map keyed by encoding name. PyMEOS is NOT
required to run these tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mobilityapi import create_app, stub_codec
from mobilityapi.dispatcher import Dispatcher


# A minimal catalog that covers the three surface shapes the routers care
# about:
#   - A scalar-return function (no encoding).
#   - A serialised-input scalar-return function.
#   - A serialised-input serialised-return function.
_CATALOG = {
    "functions": [
        {
            "name": "double_it",
            "category": "demo",
            "params": [{"name": "x", "type": "int"}],
            "return_type": "int",
        },
        {
            "name": "trip_length",
            "category": "demo",
            "params": [{"name": "trip", "type": "Temporal *"}],
            "return_type": "double",
            "wire": {
                "params": [
                    {"name": "trip", "kind": "serialized", "decode": "mfjson"}
                ],
                "result": {"kind": "scalar"},
            },
        },
        {
            "name": "shift_trip",
            "category": "demo",
            "params": [
                {"name": "trip", "type": "Temporal *"},
                {"name": "delta", "type": "Interval *"},
            ],
            "return_type": "Temporal *",
            "wire": {
                "params": [
                    {"name": "trip", "kind": "serialized", "decode": "mfjson"},
                    {"name": "delta", "kind": "scalar"},
                ],
                "result": {"kind": "serialized", "encode": "mfjson"},
            },
        },
    ]
}


# -- fixtures ---------------------------------------------------------------


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    p = tmp_path / "test-idl.json"
    p.write_text(json.dumps(_CATALOG))
    return p


@pytest.fixture
def stub_resolver():
    """Resolver mapping every test function name to a concrete callable."""

    def _resolve(name: str):
        if name == "double_it":
            return lambda x: 2 * x
        if name == "trip_length":
            return lambda trip: trip["length"]
        if name == "shift_trip":
            return lambda trip, delta: {
                "kind": "trip",
                "length": trip["length"],
                "shifted_by": delta,
            }
        raise KeyError(name)

    return _resolve


@pytest.fixture
def client(catalog_path, stub_resolver):
    dispatcher = Dispatcher(catalog_path=catalog_path, resolver=stub_resolver)
    codec = stub_codec(
        decoders={
            "mfjson": lambda s: json.loads(s) if isinstance(s, str) else s,
        },
        encoders={
            "mfjson": lambda obj: json.dumps(obj),
        },
    )
    app = create_app(dispatcher, codec)
    return TestClient(app)


# -- /catalog ---------------------------------------------------------------


def test_catalog_list_includes_all_exposable(client):
    r = client.get("/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    names = {f["name"] for f in body["functions"]}
    assert names == {"double_it", "trip_length", "shift_trip"}


def test_catalog_list_is_sorted_by_name(client):
    r = client.get("/catalog")
    names = [f["name"] for f in r.json()["functions"]]
    assert names == sorted(names)


def test_catalog_get_returns_full_signature(client):
    r = client.get("/catalog/shift_trip")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "shift_trip"
    assert body["category"] == "demo"
    assert body["return_type"] == "Temporal *"
    assert body["decode_per_param"] == {"trip": "mfjson"}
    assert body["encode_return"] == "mfjson"


def test_catalog_get_unknown_is_404(client):
    r = client.get("/catalog/does_not_exist")
    assert r.status_code == 404
    assert "not in the dispatcher catalog" in r.json()["detail"]


# -- /functions -------------------------------------------------------------


def test_invoke_scalar_function(client):
    r = client.post("/functions/double_it", json={"params": {"x": 7}})
    assert r.status_code == 200
    body = r.json()
    assert body == {"result": 14, "encoding": None}


def test_invoke_serialised_input_scalar_output(client):
    # `trip` is an mfjson-encoded wire value; the stub decoder json-loads it.
    trip_wire = json.dumps({"kind": "trip", "length": 42})
    r = client.post(
        "/functions/trip_length",
        json={"params": {"trip": trip_wire}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"result": 42, "encoding": None}


def test_invoke_serialised_input_serialised_output(client):
    trip_wire = json.dumps({"kind": "trip", "length": 100})
    r = client.post(
        "/functions/shift_trip",
        json={"params": {"trip": trip_wire, "delta": "1 day"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["encoding"] == "mfjson"
    payload = json.loads(body["result"])
    assert payload == {"kind": "trip", "length": 100, "shifted_by": "1 day"}


def test_invoke_unknown_function_is_404(client):
    r = client.post("/functions/no_such_fn", json={"params": {}})
    assert r.status_code == 404


def test_invoke_missing_param_is_400(client):
    # `double_it` requires `x` but we send nothing.
    r = client.post("/functions/double_it", json={"params": {}})
    assert r.status_code == 400


def test_invoke_extra_param_is_400(client):
    r = client.post(
        "/functions/double_it",
        json={"params": {"x": 7, "y": 99}},
    )
    assert r.status_code == 400


def test_invoke_serialised_param_unknown_encoding_is_400(client, catalog_path, stub_resolver):
    """A codec missing the declared decoder yields a 400, not a 500."""
    dispatcher = Dispatcher(catalog_path=catalog_path, resolver=stub_resolver)
    codec = stub_codec(decoders={}, encoders={})  # no decoders at all
    app = create_app(dispatcher, codec)
    cli = TestClient(app)
    trip_wire = json.dumps({"kind": "trip", "length": 1})
    r = cli.post("/functions/trip_length", json={"params": {"trip": trip_wire}})
    assert r.status_code == 400
    assert "WireCodec has no decoder" in r.json()["detail"]
