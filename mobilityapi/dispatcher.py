"""Catalog-driven dispatcher for MEOS functions.

Reads the vendored MEOS-API catalog (``vendor/meos-api/meos-idl.json``,
produced by the MEOS-API ``run.py`` against MobilityDB master headers) and
exposes a single ``dispatch(function_name, params) -> Any`` entry point.

When a MEOS-API enriched catalog (with ``network``/``wire``/``api`` fields,
authored by ``parser/enrich.py`` on MEOS-API PR #4) is the source, the
dispatcher uses the richer per-parameter decode/encode metadata.  When only
the bare catalog is available, it falls back to the function signature
itself.

The dispatcher does NOT invoke PyMEOS directly inside its core logic —
PyMEOS is injected as a *resolver* callable so the same dispatcher can be
unit-tested with stubs.  In production, the resolver is
``getattr(pymeos.functions, name)`` (PyMEOS's flat function module mirrors
the MEOS C API one-for-one).

Foundation only: this PR ships the loader, the signature model, and the
dispatch entry point with stub-resolver unit tests.  The follow-up PRs swap
each of the 5 hand-written ``resource/*`` modules listed in
``docs/MEOS_API_INGESTION_PLAN.md`` (§\"Replace candidates\") to call
``Dispatcher.dispatch`` instead of psycopg2 SQL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable


# Default vendored catalog path, resolved relative to the repository root.
_DEFAULT_CATALOG = (
    Path(__file__).resolve().parent.parent
    / "vendor" / "meos-api" / "meos-idl.json"
)


@dataclass(frozen=True)
class FunctionSignature:
    """One MEOS function from the catalog, normalised for dispatch."""

    name: str
    category: str
    params: list[dict] = field(default_factory=list)
    return_type: str = ""
    # Network / wire enrichment (optional; only present on enriched catalog).
    exposable: bool = True
    decode_per_param: dict[str, str] = field(default_factory=dict)
    encode_return: str | None = None
    description: str = ""

    @classmethod
    def from_catalog_entry(cls, entry: dict) -> "FunctionSignature":
        network = entry.get("network", {})
        wire = entry.get("wire", {})

        decode_per_param: dict[str, str] = {}
        if wire.get("params"):
            for p in wire["params"]:
                if p.get("kind") == "serialized" and p.get("decode"):
                    decode_per_param[p["name"]] = p["decode"]
                elif p.get("kind") == "array" and p.get("element", {}).get("decode"):
                    decode_per_param[p["name"]] = p["element"]["decode"]

        encode_return: str | None = None
        if wire.get("result", {}).get("kind") == "serialized":
            encode_return = wire["result"].get("encode")

        return cls(
            name=entry["name"],
            category=entry.get("category", "uncategorised"),
            params=entry.get("params", []),
            return_type=entry.get("return_type", ""),
            exposable=bool(network.get("exposable", True)),
            decode_per_param=decode_per_param,
            encode_return=encode_return,
            description=entry.get("doc", "") or entry.get("description", ""),
        )


class Dispatcher:
    """Catalog-driven MEOS function dispatcher."""

    def __init__(
        self,
        catalog_path: Path | str | None = None,
        resolver: Callable[[str], Callable[..., Any]] | None = None,
    ) -> None:
        """Construct a dispatcher.

        :param catalog_path: Path to ``meos-idl.json``; defaults to the
            vendored copy at ``vendor/meos-api/meos-idl.json``.
        :param resolver: Callable mapping a MEOS function name to the
            Python callable that implements it.  In production this is
            ``lambda n: getattr(pymeos.functions, n)``.  In unit tests it
            can be a stub registry.  Defaults to a stub that raises
            ``NotImplementedError`` — the caller must supply a real
            resolver before ``dispatch`` is called.
        """
        path = Path(catalog_path) if catalog_path else _DEFAULT_CATALOG
        self._catalog_path = path
        self._signatures: dict[str, FunctionSignature] = {}
        self._load(path)
        self._resolver = resolver or self._stub_resolver

    # -- catalog ----------------------------------------------------------------

    def _load(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"MEOS-API catalog not found at {path}. Run "
                f"`make vendor-meos-api` to (re-)populate vendor/meos-api/."
            )
        with path.open() as f:
            catalog = json.load(f)

        for entry in catalog.get("functions", []):
            sig = FunctionSignature.from_catalog_entry(entry)
            if sig.exposable:
                self._signatures[sig.name] = sig

    def signature(self, name: str) -> FunctionSignature:
        try:
            return self._signatures[name]
        except KeyError:
            raise KeyError(
                f"Unknown MEOS function `{name}` — either it does not exist "
                f"in the vendored catalog or it is not exposable."
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
