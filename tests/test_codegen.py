"""Unit tests for tools/codegen.py, the generator of mobilityapi/catalog_gen.py.

They build catalogs in the catalog's shape with #_fn of tests/test_dispatcher.py,
run the generator on them, and read the table it writes back through the
Dispatcher, so the table is proven to be what the dispatcher reads.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from mobilityapi.dispatcher import Dispatcher, FunctionSignature

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from test_dispatcher import _fn

_spec = importlib.util.spec_from_file_location("codegen", ROOT / "tools" / "codegen.py")
codegen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(codegen)


def _write(tmp_path: Path, functions: list[dict]) -> Path:
    """A catalog file holding these functions, the file
    #test_explicit_path_overrides_default writes."""
    path = tmp_path / "meos-idl.json"
    path.write_text(json.dumps({"functions": functions}))
    return path


def test_the_table_holds_the_exposable_entries_with_the_keys_the_dispatcher_reads(tmp_path):
    """The generator's counterpart of #test_explicit_path_overrides_default:
    the table keeps the exposable entry, drops a key the dispatcher does not
    read, and reads back to the same #FunctionSignature as the catalog."""
    shown = _fn("tfloat_abs", "transformation", [("temp", "const Temporal *")],
                "Temporal *", doc="Return the absolute value")
    shown["file"] = "meos.h"
    hidden = _fn("tfloat_secret", "transformation", [], "int", exposable=False)
    out = tmp_path / "catalog_gen.py"
    assert codegen.main(["-catalog", str(_write(tmp_path, [shown, hidden])),
                         "-o", str(out)]) == 0

    spec = importlib.util.spec_from_file_location("catalog_gen", out)
    table = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(table)
    assert [e["name"] for e in table.FUNCTIONS] == ["tfloat_abs"]
    assert "file" not in table.FUNCTIONS[0]
    assert (FunctionSignature.from_catalog_entry(table.FUNCTIONS[0])
            == FunctionSignature.from_catalog_entry(shown))


def test_an_entry_without_a_key_the_dispatcher_reads_stops_the_generator(tmp_path, capsys):
    """The generator's counterpart of the KeyError #from_catalog_entry raises
    on an absent required key: no table is written."""
    entry = _fn("tfloat_abs", "transformation", [], "Temporal *")
    del entry["wire"]
    out = tmp_path / "catalog_gen.py"
    assert codegen.main(["-catalog", str(_write(tmp_path, [entry])), "-o", str(out)]) == 1
    assert "tfloat_abs" in capsys.readouterr().err
    assert not out.exists()


def test_a_catalog_without_an_exposable_function_stops_the_generator(tmp_path, capsys):
    """A catalog parsed without the MobilityDB sources states no function as
    exposable, and the generator refuses it rather than writing an empty table
    #test_default_loads_the_generated_table would read."""
    entry = _fn("tfloat_abs", "transformation", [], "Temporal *", exposable=False)
    out = tmp_path / "catalog_gen.py"
    assert codegen.main(["-catalog", str(_write(tmp_path, [entry])), "-o", str(out)]) == 1
    assert "no function as exposable" in capsys.readouterr().err
    assert not out.exists()


def test_the_dispatcher_serves_every_function_of_the_committed_table():
    """Extends #test_default_loads_the_generated_table: the dispatcher serves
    exactly the table's functions, and none the catalog states as internal."""
    from mobilityapi.catalog_gen import FUNCTIONS
    d = Dispatcher()
    assert sorted(s.name for s in d.signatures()) == [e["name"] for e in FUNCTIONS]
    with pytest.raises(KeyError):
        d.signature("temporal_from_mfjson")
