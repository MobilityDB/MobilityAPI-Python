"""Resolvers — bridge ``Dispatcher`` to a concrete MEOS-function implementation.

A *resolver* is a callable ``name -> Python callable`` that the
``Dispatcher`` uses to look up the MEOS function to invoke for a given
catalog name. The resolver is the only place that knows *how* the
binding actually calls into MEOS:

- **production** — ``pymeos_resolver()`` returns a resolver that looks
  up the function in ``pymeos.functions``; each call decodes the
  request's serialised parameters into PyMEOS objects, invokes the
  function, and returns the result.
- **stub / test** — ``stub_resolver(registry)`` builds a resolver from
  an explicit ``{name: callable}`` mapping, so unit tests can verify
  the dispatch contract without a PyMEOS runtime.

The resolver layer is deliberately thin: every decode / encode decision
that depends on the catalog's ``x-meos-decode`` / ``x-meos-encode``
metadata lives in ``mobilityapi.wire``, not here. Resolvers just hand
off the function pointer; ``wire`` does the actual byte-shuffling.
"""

from __future__ import annotations

from typing import Any, Callable


def stub_resolver(registry: dict[str, Callable[..., Any]]) -> Callable[[str], Callable[..., Any]]:
    """Build a resolver from an explicit name→callable registry.

    Intended for unit tests:

        resolver = stub_resolver({"tpoint_speed": lambda *, temp: ...})
        dispatcher = Dispatcher(resolver=resolver)
    """
    def _resolve(name: str) -> Callable[..., Any]:
        if name not in registry:
            raise NotImplementedError(
                f"stub_resolver has no entry for `{name}`. "
                f"Available: {sorted(registry)}"
            )
        return registry[name]
    return _resolve


def pymeos_resolver() -> Callable[[str], Callable[..., Any]]:
    """Build a resolver that dispatches to ``pymeos.functions``.

    Lazy-imports PyMEOS so MobilityAPI can be installed without it
    available (the import only fires the first time the resolver is
    actually called). Raises ``ImportError`` at call time if PyMEOS is
    not installed.

    PyMEOS exposes the MEOS C API as a flat module of Python functions
    one-for-one with the C names — ``pymeos.functions.tpoint_speed``
    maps to ``tpoint_speed(temp: Temporal) -> Temporal`` in MEOS.
    """
    def _resolve(name: str) -> Callable[..., Any]:
        try:
            import pymeos.functions as pmf  # noqa: WPS433 - lazy import on purpose
        except ImportError as e:
            raise ImportError(
                "pymeos is not installed. MobilityAPI's pymeos_resolver "
                "requires the `pymeos` package on the Python path. "
                "Either add `pymeos>=1.4` to requirements.txt and pip "
                "install it, or use stub_resolver() for development."
            ) from e
        try:
            return getattr(pmf, name)
        except AttributeError as e:
            raise AttributeError(
                f"pymeos.functions has no attribute `{name}`. "
                f"Either the catalog references a function not exposed "
                f"by the installed PyMEOS version, or PyMEOS is out of "
                f"sync with the vendored catalog (run `make vendor-meos-api` "
                f"and check requirements.txt's pymeos version)."
            ) from e
    return _resolve


def default_resolver(prefer_pymeos: bool = True) -> Callable[[str], Callable[..., Any]]:
    """Pick the appropriate resolver based on what's actually available.

    Tries PyMEOS first (production), then falls back to a stub resolver
    that explicitly raises ``NotImplementedError`` for every name. Useful
    as a Dispatcher default in production code that wants to fail fast
    if PyMEOS is missing, but doesn't want to import-error at startup.
    """
    if prefer_pymeos:
        try:
            import pymeos.functions  # noqa: F401 - probe
            return pymeos_resolver()
        except ImportError:
            pass

    def _stub(name: str) -> Callable[..., Any]:
        def _raise(*_a, **_kw):
            raise NotImplementedError(
                f"No production resolver is wired in for `{name}`. "
                f"Either install pymeos, or supply an explicit "
                f"resolver=... to Dispatcher(...)."
            )
        return _raise
    return _stub
