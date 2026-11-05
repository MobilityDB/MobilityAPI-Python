"""HTTP-surface tests for the generated OGC API – Moving Features routes.

The routes are exercised via Starlette's ``TestClient`` against a tiny in-test
catalog, a stub resolver (so the "MEOS function" is a Python lambda), a stub
``WireCodec``, and a stub ``FeatureStore``. PyMEOS and a database are NOT
required — the test asserts the dispatch + OGC-shaping wiring, not a live MEOS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mobilityapi import create_app, stub_codec
from mobilityapi.dispatcher import Dispatcher


def _fn(name: str, category: str, c_return: str) -> dict:
    """One catalog entry taking a single temporal ``t``.

    Builds the ``functions[]`` shape #from_catalog_entry reads, the same
    shape the ``_CATALOG`` of tests/test_app.py spells out entry by entry.
    """
    return {
        "name": name,
        "category": category,
        "params": [{"name": "t", "cType": "const Temporal *",
                    "canonical": "const Temporal *"}],
        "returnType": {"c": c_return, "canonical": c_return},
        "network": {"exposable": True},
        "wire": {
            "params": [{"name": "t", "kind": "json", "json": "string"}],
            "result": {"kind": "json", "json": "string"},
        },
    }


# Catalog: the three MEOS functions the OGC read routes dispatch to, each a
# single-temporal-argument function named `t`.
_CATALOG = {
    "functions": [
        _fn("temporal_as_mfjson", "io", "char *"),
        _fn("tpoint_speed", "analysis", "Temporal *"),
        _fn("tpoint_cumulative_length", "analysis", "Temporal *"),
    ]
}

# Stub resolver: each "MEOS function" tags its single argument so the response
# is traceable back to the function that ran.
_RESOLVERS = {
    "temporal_as_mfjson": lambda **kw: {"mfjson_of": kw["t"]},
    "tpoint_speed": lambda **kw: {"speed_of": kw["t"]},
    "tpoint_cumulative_length": lambda **kw: {"distance_of": kw["t"]},
}


class _StubStore:
    """In-memory FeatureStore: vessel 1 exists with a trip + a `fuel` property."""

    def get_trajectory(self, cid, fid):
        return {"type": "MovingPoint", "id": fid} if fid == "1" else None

    def get_property(self, cid, fid, name):
        return {"type": "MovingFloat", "prop": name} if (fid == "1" and name == "fuel") else None


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    cat = tmp_path / "meos-idl.json"
    cat.write_text(json.dumps(_CATALOG))
    dispatcher = Dispatcher(catalog_path=cat, resolver=lambda n: _RESOLVERS[n])
    codec = stub_codec(
        decoders={"mfjson": lambda v: {"decoded": v}},
        encoders={"mfjson": lambda o: o},
    )
    return TestClient(create_app(dispatcher, codec, feature_store=_StubStore()))


def test_tgsequence_export_dispatches_as_mfjson(client):
    r = client.get("/collections/ships/items/1/tgsequence")
    assert r.status_code == 200
    assert "mfjson_of" in r.json()


def test_tgsequence_missing_feature_404(client):
    assert client.get("/collections/ships/items/999/tgsequence").status_code == 404


@pytest.mark.parametrize("measure,tag", [("velocity", "speed_of"), ("distance", "distance_of")])
def test_derived_measure_is_a_temporal_property(client, measure, tag):
    r = client.get(f"/collections/ships/items/1/tgsequence/0/{measure}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == measure
    assert body["type"] == "TReal"
    assert tag in json.dumps(body["valueSequence"])


def test_acceleration_is_501(client):
    r = client.get("/collections/ships/items/1/tgsequence/0/acceleration")
    assert r.status_code == 501
    assert "not derivable" in r.json()["detail"]


def test_unknown_measure_404(client):
    assert client.get("/collections/ships/items/1/tgsequence/0/heading").status_code == 404


def test_stored_temporal_property(client):
    r = client.get("/collections/ships/items/1/tproperties/fuel")
    assert r.status_code == 200
    assert r.json()["name"] == "fuel"


def test_unknown_temporal_property_404(client):
    assert client.get("/collections/ships/items/1/tproperties/nope").status_code == 404


def test_routes_501_without_a_feature_store(tmp_path: Path):
    cat = tmp_path / "meos-idl.json"
    cat.write_text(json.dumps(_CATALOG))
    dispatcher = Dispatcher(catalog_path=cat, resolver=lambda n: _RESOLVERS[n])
    app = create_app(dispatcher, stub_codec(), feature_store=None)
    assert TestClient(app).get("/collections/ships/items/1/tgsequence").status_code == 501
