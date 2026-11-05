"""Unit tests for mobilityapi.dispatcher.Dispatcher.

These tests run against the generated table ``mobilityapi/catalog_gen.py``
and catalogs built in the catalog's shape, with a stub resolver, so PyMEOS
is NOT required to run them. The dispatcher's contract — catalog load,
function lookup, parameter validation, resolver invocation — is verifiable
independently of any actual MEOS runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobilityapi.dispatcher import Dispatcher, FunctionSignature


def _fn(name, category, params, c_return, *, wire=None, exposable=True,
        doc=None):
    """One catalog entry built from ``(name, cType)`` parameter pairs.

    Builds the ``functions[]`` shape #from_catalog_entry reads, the shape
    the ``_fn`` of tests/test_movfeat.py builds; ``wire`` defaults to a
    JSON value per parameter and a JSON result.
    """
    entry = {
        "name": name,
        "category": category,
        "params": [{"name": n, "cType": t, "canonical": t} for n, t in params],
        "returnType": {"c": c_return, "canonical": c_return},
        "network": {"exposable": exposable},
        "wire": wire or {
            "params": [{"name": n, "kind": "json", "json": "string"}
                       for n, _ in params],
            "result": {"kind": "json", "json": "string"},
        },
    }
    if doc is not None:
        entry["doc"] = doc
    return entry


# --- catalog load ------------------------------------------------------------

def test_default_loads_the_generated_table():
    """The default Dispatcher() reads mobilityapi/catalog_gen.py, every
    entry of which the catalog states as exposable."""
    from mobilityapi.catalog_gen import FUNCTIONS
    d = Dispatcher()
    assert len(d) == len(FUNCTIONS)
    assert len(d) > 0
    # Sanity: a known MEOS function should be present.
    assert d.has("temporal_as_mfjson")


def test_explicit_path_overrides_default(tmp_path: Path):
    """A custom catalog path is honoured."""
    custom = tmp_path / "fake-idl.json"
    custom.write_text(json.dumps({
        "functions": [
            _fn("my_fn", "demo", [], "int")
        ]
    }))
    d = Dispatcher(catalog_path=custom)
    assert len(d) == 1
    assert d.has("my_fn")


def test_missing_catalog_path_raises_filenotfound(tmp_path: Path):
    nonexistent = tmp_path / "does-not-exist.json"
    with pytest.raises(FileNotFoundError):
        Dispatcher(catalog_path=nonexistent)


# --- signature shape ---------------------------------------------------------

def test_signature_round_trips_basic_fields():
    entry = _fn("temporal_as_mfjson", "io", [("temp", "const Temporal *")],
                "char *", doc="Convert to MF-JSON.")
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.name == "temporal_as_mfjson"
    assert sig.category == "io"
    assert sig.return_type == "char *"
    assert sig.description == "Convert to MF-JSON."
    assert len(sig.params) == 1


def test_signature_reads_enriched_wire_metadata_when_present():
    entry = _fn(
        "tpoint_speed", "tpoint", [("tpoint", "const Temporal *")],
        "Temporal *",
        wire={
            "params": [{"name": "tpoint", "kind": "serialized",
                        "cType": "Temporal", "decode": "from_hex_wkb"}],
            "result": {"kind": "serialized", "cType": "Temporal",
                       "encode": "as_hex_wkb"},
        },
    )
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.decode_per_param == {"tpoint": "from_hex_wkb"}
    assert sig.encode_return == "as_hex_wkb"


# Each test below mirrors #test_signature_round_trips_basic_fields: build one
# catalog entry with _fn, normalise it, assert one property of the result.

def test_signature_reads_return_type_from_returnType_c():
    entry = _fn("fn", "demo", [], "Temporal *")
    entry["returnType"]["canonical"] = "struct Temporal *"
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.return_type == "Temporal *"


@pytest.mark.parametrize("key", ["name", "category", "params", "returnType",
                                 "network", "wire"])
def test_signature_missing_required_key_raises(key):
    entry = _fn("fn", "demo", [], "int")
    del entry[key]
    with pytest.raises(KeyError, match=key):
        FunctionSignature.from_catalog_entry(entry)


def test_signature_rejects_the_return_type_spelling():
    entry = _fn("fn", "demo", [], "int")
    entry["return_type"] = entry.pop("returnType")["c"]
    with pytest.raises(KeyError, match="returnType"):
        FunctionSignature.from_catalog_entry(entry)


def test_signature_without_doc_has_empty_description():
    sig = FunctionSignature.from_catalog_entry(_fn("fn", "demo", [], "int"))
    assert sig.description == ""


def test_signature_reads_array_element_decode():
    entry = _fn(
        "fn", "demo", [("arr", "Temporal **"), ("count", "int")], "int",
        wire={
            "params": [
                {"name": "arr", "kind": "array", "count_param": "count",
                 "element": {"kind": "serialized", "cType": "Temporal",
                             "decode": "from_hex_wkb"}},
                {"name": "count", "kind": "json", "json": "integer"},
            ],
            "result": {"kind": "json", "json": "integer"},
        },
    )
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.decode_per_param == {"arr": "from_hex_wkb"}


def test_signature_with_json_wire_has_no_codec():
    entry = _fn("fn", "demo", [], "int")
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.decode_per_param == {}
    assert sig.encode_return is None


def test_non_exposable_functions_are_excluded(tmp_path: Path):
    custom = tmp_path / "idl.json"
    custom.write_text(json.dumps({
        "functions": [
            _fn("exposed_fn", "x", [], "int", exposable=True),
            _fn("internal_fn", "x", [], "int", exposable=False),
        ]
    }))
    d = Dispatcher(catalog_path=custom)
    assert d.has("exposed_fn")
    assert not d.has("internal_fn")


# --- dispatch contract -------------------------------------------------------

def _stub_registry(**impls):
    """Build a resolver from a name -> callable mapping."""
    def resolve(name):
        if name not in impls:
            raise NotImplementedError(name)
        return impls[name]
    return resolve


def test_dispatch_invokes_resolver_with_params(tmp_path: Path):
    custom = tmp_path / "idl.json"
    custom.write_text(json.dumps({
        "functions": [
            _fn("tpoint_speed", "tpoint", [("tpoint", "const Temporal *")],
                "Temporal *")
        ]
    }))
    seen: dict = {}

    def fake_tpoint_speed(*, tpoint):
        seen["tpoint"] = tpoint
        return "speed-result"

    d = Dispatcher(catalog_path=custom,
                   resolver=_stub_registry(tpoint_speed=fake_tpoint_speed))
    result = d.dispatch("tpoint_speed", {"tpoint": "abc"})
    assert result == "speed-result"
    assert seen == {"tpoint": "abc"}


def test_dispatch_unknown_function_raises_keyerror():
    d = Dispatcher()
    with pytest.raises(KeyError, match="Unknown MEOS function `not_a_real_function`"):
        d.dispatch("not_a_real_function", {})


def test_dispatch_missing_param_raises_typeerror(tmp_path: Path):
    custom = tmp_path / "idl.json"
    custom.write_text(json.dumps({
        "functions": [
            _fn("fn", "x", [("a", "int"), ("b", "int")], "int")
        ]
    }))
    d = Dispatcher(catalog_path=custom,
                   resolver=_stub_registry(fn=lambda **kw: 1))
    with pytest.raises(TypeError, match="parameter set mismatch"):
        d.dispatch("fn", {"a": 1})  # missing b
    with pytest.raises(TypeError, match="parameter set mismatch"):
        d.dispatch("fn", {"a": 1, "b": 2, "c": 3})  # unexpected c


def test_default_resolver_raises_notimplemented(tmp_path: Path):
    custom = tmp_path / "idl.json"
    custom.write_text(json.dumps({
        "functions": [
            _fn("fn", "x", [], "int")
        ]
    }))
    d = Dispatcher(catalog_path=custom)  # no resolver supplied
    with pytest.raises(NotImplementedError, match="no resolver wired in"):
        d.dispatch("fn", {})


# --- integration sanity ------------------------------------------------------

def test_real_catalog_has_the_5_movfeat_dispatch_candidates():
    """The generated table holds the 5 MEOS functions the Moving Features
    routes dispatch to. A feature's trajectory is a tgeompoint, so the item
    writer is the typed tgeompoint_from_mfjson, which is public, and not
    temporal_from_mfjson, which takes a MeosType and which the catalog
    states as internal."""
    d = Dispatcher()
    candidates = [
        "temporal_as_mfjson",        # /collections/{c}/items/{f}/tgsequence
        "tgeompoint_from_mfjson",    # POST /collections/{c}/items
        "tpoint_speed",              # /tgsequence/velocity
        "tpoint_cumulative_length",  # /tgsequence/distance
        "temporal_derivative",       # /tgsequence/acceleration
    ]
    missing = [c for c in candidates if not d.has(c)]
    assert not missing, (
        f"the generated table is missing MEOS functions the Moving Features routes "
        f"needs: {missing}"
    )
