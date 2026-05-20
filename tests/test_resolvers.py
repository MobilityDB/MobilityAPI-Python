"""Unit tests for mobilityapi.resolvers."""

import pytest

from mobilityapi.resolvers import (
    stub_resolver, pymeos_resolver, default_resolver,
)


def test_stub_resolver_returns_registered_callable():
    fn = lambda **kw: "ok"
    r = stub_resolver({"my_fn": fn})
    assert r("my_fn") is fn


def test_stub_resolver_raises_on_unknown_name():
    r = stub_resolver({"my_fn": lambda: None})
    with pytest.raises(NotImplementedError, match="has no entry for `other`"):
        r("other")


def test_stub_resolver_lists_known_names_in_error():
    r = stub_resolver({"a": lambda: None, "b": lambda: None})
    with pytest.raises(NotImplementedError, match="\\['a', 'b'\\]"):
        r("c")


def test_pymeos_resolver_returns_callable_factory():
    """The factory itself constructs without PyMEOS installed; the import
    fires only when the returned resolver is *called*."""
    r = pymeos_resolver()
    assert callable(r)


def test_pymeos_resolver_raises_importerror_on_call_when_pymeos_missing(monkeypatch):
    """Simulate PyMEOS being absent: the resolver call raises ImportError
    with an actionable message."""
    import sys
    # Force the lazy import to fail by hiding the module.
    monkeypatch.setitem(sys.modules, "pymeos", None)
    monkeypatch.setitem(sys.modules, "pymeos.functions", None)
    r = pymeos_resolver()
    with pytest.raises(ImportError, match="pymeos is not installed"):
        r("any_fn")


def test_default_resolver_falls_back_to_stub_when_pymeos_missing(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pymeos", None)
    monkeypatch.setitem(sys.modules, "pymeos.functions", None)
    r = default_resolver(prefer_pymeos=True)
    # The fallback raises NotImplementedError when called, not at construction.
    callable_for_fn = r("some_fn")
    with pytest.raises(NotImplementedError, match="No production resolver"):
        callable_for_fn(temp="x")


def test_default_resolver_with_prefer_pymeos_false_skips_probe(monkeypatch):
    """If prefer_pymeos=False, default_resolver does not attempt PyMEOS
    even if it's available, and uses the stub path immediately."""
    r = default_resolver(prefer_pymeos=False)
    callable_for_fn = r("some_fn")
    with pytest.raises(NotImplementedError, match="No production resolver"):
        callable_for_fn()
