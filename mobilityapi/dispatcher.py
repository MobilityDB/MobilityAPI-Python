"""Catalog-driven dispatcher for MEOS functions.

Reads the MEOS functions of ``mobilityapi/catalog_gen.py``, the table
``tools/codegen.py`` generates from the MEOS-API catalog, and exposes a
single ``dispatch(function_name, params) -> Any`` entry point.  A
``meos-idl.json`` passed as ``catalog_path`` is read instead, with the same
reader.

Every catalog function carries ``name``, ``category``, ``params``,
``returnType`` (``{"c", "canonical"}``) and the enrichment fields
``network`` and ``wire``; the dispatcher reads each of them by that exact
key and raises ``KeyError`` when one is absent, so a renamed catalog key
fails at load rather than reading as empty.  ``doc`` is the one optional
key.

The dispatcher does NOT invoke PyMEOS directly inside its core logic —
PyMEOS is injected as a *resolver* callable so the same dispatcher can be
unit-tested with stubs.  In production, the resolver is
``getattr(pymeos.functions, name)`` (PyMEOS's flat function module mirrors
the MEOS C API one-for-one).

"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FunctionSignature:
    """One MEOS function from the catalog, normalised for dispatch."""

    name: str
    category: str
    params: list[dict] = field(default_factory=list)
    return_type: str = ""
    exposable: bool = True
    decode_per_param: dict[str, str] = field(default_factory=dict)
    encode_return: str | None = None
    description: str = ""

    @classmethod
    def from_catalog_entry(cls, entry: dict) -> FunctionSignature:
        """Normalise one ``functions[]`` entry of the catalog.

        Mirrors #_load, which reads ``functions`` by its exact key: every
        required catalog key is read by its exact spelling and an absent
        one raises ``KeyError``.  ``return_type`` is the C spelling
        ``returnType.c``.
        """
        network = entry["network"]
        wire = entry["wire"]

        decode_per_param: dict[str, str] = {}
        for p in wire["params"]:
            if p["kind"] == "serialized":
                decode_per_param[p["name"]] = p["decode"]
            elif p["kind"] == "array" and p["element"]["kind"] == "serialized":
                decode_per_param[p["name"]] = p["element"]["decode"]

        result = wire["result"]
        encode_return: str | None = (
            result["encode"] if result["kind"] == "serialized" else None
        )

        return cls(
            name=entry["name"],
            category=entry["category"],
            params=entry["params"],
            return_type=entry["returnType"]["c"],
            exposable=bool(network["exposable"]),
            decode_per_param=decode_per_param,
            encode_return=encode_return,
            description=entry.get("doc") or "",
        )


class Dispatcher:
    """Catalog-driven MEOS function dispatcher."""

    def __init__(
        self,
        catalog_path: Path | str | None = None,
        resolver: Callable[[str], Callable[..., Any]] | None = None,
    ) -> None:
        """Construct a dispatcher.

        :param catalog_path: Path to a ``meos-idl.json`` to read; by default
            the dispatcher reads the generated table
            ``mobilityapi/catalog_gen.py``.
        :param resolver: Callable mapping a MEOS function name to the
            Python callable that implements it.  In production this is
            ``lambda n: getattr(pymeos.functions, n)``.  In unit tests it
            can be a stub registry.  Defaults to a stub that raises
            ``NotImplementedError`` — the caller must supply a real
            resolver before ``dispatch`` is called.
        """
        self._signatures: dict[str, FunctionSignature] = {}
        self._load(self._entries(catalog_path))
        self._resolver = resolver or self._stub_resolver

    # -- catalog ----------------------------------------------------------------

    @staticmethod
    def _entries(catalog_path: Path | str | None) -> Iterable[dict]:
        """The catalog functions to read: the generated table, or the
        ``functions`` of the ``meos-idl.json`` at ``catalog_path``.

        This module has no other source of catalog entries; both sources
        yield entries in the catalog's own shape, which #from_catalog_entry
        reads, so the table and a catalog file pass through the one reader.
        """
        if catalog_path is None:
            from mobilityapi.catalog_gen import FUNCTIONS
            return FUNCTIONS
        path = Path(catalog_path)
        if not path.exists():
            raise FileNotFoundError(f"MEOS-API catalog not found at {path}")
        with path.open() as f:
            return json.load(f)["functions"]

    def _load(self, entries: Iterable[dict]) -> None:
        """Keep each exposable entry, read through #from_catalog_entry."""
        for entry in entries:
            sig = FunctionSignature.from_catalog_entry(entry)
            if sig.exposable:
                self._signatures[sig.name] = sig

    def signature(self, name: str) -> FunctionSignature:
        try:
            return self._signatures[name]
        except KeyError:
            raise KeyError(
                f"Unknown MEOS function `{name}` — either it does not exist "
                f"in the MEOS-API catalog or it is not exposable."
            )

    def signatures(self) -> Iterable[FunctionSignature]:
        return self._signatures.values()

    def has(self, name: str) -> bool:
        return name in self._signatures

    def __len__(self) -> int:
        return len(self._signatures)

    # -- dispatch ---------------------------------------------------------------

    @staticmethod
    def _stub_resolver(name: str) -> Callable[..., Any]:
        def _raise(*_a, **_kw):  # pragma: no cover - intentional stub
            raise NotImplementedError(
                f"Dispatcher has no resolver wired in for `{name}`. Pass a "
                f"resolver= argument to Dispatcher(...)."
            )
        return _raise

    def dispatch(self, function_name: str, params: dict) -> Any:
        """Invoke the MEOS function named ``function_name`` with ``params``.

        ``params`` is a JSON-like dict whose keys match the function's
        parameter names (per the catalog).  Each parameter is passed through
        unchanged to the resolver-returned callable; the caller is
        responsible for decoding opaque types (e.g. constructing
        ``pymeos.TGeomPoint`` from MF-JSON) before calling ``dispatch``.

        Encoding the return value is also left to the caller — the
        dispatcher returns whatever the resolver-returned callable returns.

        The catalog signature is used only for validation:

        * unknown function name → ``KeyError``
        * mismatched parameter set → ``TypeError`` with a helpful message
        """
        sig = self.signature(function_name)
        self._validate_params(sig, params)
        fn = self._resolver(function_name)
        return fn(**params)

    @staticmethod
    def _validate_params(sig: FunctionSignature, params: dict) -> None:
        expected = {p["name"] for p in sig.params}
        provided = set(params.keys())
        missing = expected - provided
        unexpected = provided - expected
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing: {sorted(missing)}")
            if unexpected:
                details.append(f"unexpected: {sorted(unexpected)}")
            raise TypeError(
                f"`{sig.name}` parameter set mismatch — "
                + "; ".join(details)
                + f". Expected: {sorted(expected)}"
            )
