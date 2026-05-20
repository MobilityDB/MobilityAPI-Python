"""Unit tests for mobilityapi.dispatcher.Dispatcher.

These tests run against the vendored MEOS-API catalog (a real
``vendor/meos-api/meos-idl.json``) but with a stub resolver, so PyMEOS is
NOT required to run them. The dispatcher's contract — catalog load,
function lookup, parameter validation, resolver invocation — is verifiable
independently of any actual MEOS runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobilityapi.dispatcher import Dispatcher, FunctionSignature


REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_CATALOG = REPO_ROOT / "vendor" / "meos-api" / "meos-idl.json"


# --- catalog load ------------------------------------------------------------

def test_default_path_loads_vendored_catalog():
    """The default Dispatcher() reads vendor/meos-api/meos-idl.json."""
    d = Dispatcher()
    assert len(d) > 0
    # Sanity: a known MEOS function should be present.
    assert d.has("temporal_as_mfjson")


def test_explicit_path_overrides_default(tmp_path: Path):
    """A custom catalog path is honoured."""
    custom = tmp_path / "fake-idl.json"
    custom.write_text(json.dumps({
        "functions": [
            {"name": "my_fn", "category": "demo", "params": [], "return_type": "int"}
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
    entry = {
        "name": "temporal_as_mfjson",
        "category": "io",
        "params": [{"name": "temp", "cType": "const Temporal *"}],
        "return_type": "char *",
        "doc": "Convert to MF-JSON.",
    }
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.name == "temporal_as_mfjson"
    assert sig.category == "io"
    assert sig.return_type == "char *"
    assert sig.description == "Convert to MF-JSON."
    assert len(sig.params) == 1


def test_signature_reads_enriched_wire_metadata_when_present():
    entry = {
        "name": "tpoint_speed",
        "category": "tpoint",
        "params": [{"name": "tpoint", "cType": "const Temporal *"}],
        "return_type": "Temporal *",
        "network": {"exposable": True},
        "wire": {
            "params": [{"name": "tpoint", "kind": "serialized",
                        "cType": "Temporal", "decode": "from_hex_wkb"}],
            "result": {"kind": "serialized", "cType": "Temporal",
                       "encode": "as_hex_wkb"},
        },
    }
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.decode_per_param == {"tpoint": "from_hex_wkb"}
    assert sig.encode_return == "as_hex_wkb"


def test_signature_without_wire_falls_back_to_defaults():
    entry = {"name": "fn", "category": "demo", "params": [], "return_type": "int"}
    sig = FunctionSignature.from_catalog_entry(entry)
    assert sig.decode_per_param == {}
    assert sig.encode_return is None


def test_non_exposable_functions_are_excluded(tmp_path: Path):
    custom = tmp_path / "idl.json"
    custom.write_text(json.dumps({
        "functions": [
            {"name": "exposed_fn", "category": "x", "params": [], "return_type": "int",
             "network": {"exposable": True}},
            {"name": "internal_fn", "category": "x", "params": [], "return_type": "int",
             "network": {"exposable": False}},
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
            {"name": "tpoint_speed", "category": "tpoint",
             "params": [{"name": "tpoint", "cType": "const Temporal *"}],
             "return_type": "Temporal *"}
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
            {"name": "fn", "category": "x",
             "params": [{"name": "a"}, {"name": "b"}],
             "return_type": "int"}
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
            {"name": "fn", "category": "x", "params": [], "return_type": "int"}
        ]
    }))
    d = Dispatcher(catalog_path=custom)  # no resolver supplied
    with pytest.raises(NotImplementedError, match="no resolver wired in"):
        d.dispatch("fn", {})


# --- integration sanity ------------------------------------------------------

@pytest.mark.skipif(not VENDOR_CATALOG.exists(),
                    reason="vendored catalog not present in this checkout")
def test_real_catalog_has_the_5_movfeat_dispatch_candidates():
    """Sanity-check that the catalog contains the 5 MEOS functions named in
    docs/MEOS_API_INGESTION_PLAN.md as the candidates for the REPLACE step."""
    d = Dispatcher()
    candidates = [
        "temporal_as_mfjson",        # /collections/{c}/items/{f}/tgsequence
        "temporal_from_mfjson",      # POST /collections/{c}/items
        "tpoint_speed",              # /tgsequence/velocity
        "tpoint_cumulative_length",  # /tgsequence/distance
        "temporal_derivative",       # /tgsequence/acceleration
    ]
    missing = [c for c in candidates if not d.has(c)]
    assert not missing, (
        f"vendored catalog is missing MEOS functions the dispatcher plan "
        f"needs: {missing}"
    )
