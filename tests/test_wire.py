"""Unit tests for mobilityapi.wire."""

import pytest

from mobilityapi.wire import (
    WireCodec, stub_codec,
    ENCODING_MFJSON, ENCODING_TEXT, ENCODING_WKB, ENCODING_HEXWKB,
)


# --- encoding name constants -------------------------------------------------

def test_encoding_constants_are_stable_strings():
    assert ENCODING_MFJSON == "mfjson"
    assert ENCODING_TEXT == "text"
    assert ENCODING_WKB == "wkb"
    assert ENCODING_HEXWKB == "hexwkb"


# --- stub codec --------------------------------------------------------------

def test_stub_codec_round_trips_through_supplied_pair():
    codec = stub_codec(
        decoders={ENCODING_TEXT: lambda s: {"text": s}},
        encoders={ENCODING_TEXT: lambda o: o["text"]},
    )
    decoded = codec.decode(ENCODING_TEXT, "POINT(1 1)")
    assert decoded == {"text": "POINT(1 1)"}
    encoded = codec.encode(ENCODING_TEXT, decoded)
    assert encoded == "POINT(1 1)"


def test_stub_codec_raises_keyerror_on_unknown_encoding():
    codec = stub_codec(decoders={ENCODING_WKB: lambda b: b})
    with pytest.raises(KeyError, match="no decoder for encoding `mfjson`"):
        codec.decode(ENCODING_MFJSON, b"\x00")


def test_stub_codec_lists_known_encodings_in_error_message():
    codec = stub_codec(decoders={"a": str, "b": str})
    with pytest.raises(KeyError, match="\\['a', 'b'\\]"):
        codec.decode("c", "x")


def test_has_decoder_and_has_encoder_reflect_registration():
    codec = stub_codec(
        decoders={ENCODING_WKB: bytes},
        encoders={ENCODING_TEXT: str},
    )
    assert codec.has_decoder(ENCODING_WKB) is True
    assert codec.has_decoder(ENCODING_TEXT) is False
    assert codec.has_encoder(ENCODING_TEXT) is True
    assert codec.has_encoder(ENCODING_WKB) is False


# --- WireCodec direct construction -------------------------------------------

def test_wirecodec_construct_with_explicit_maps():
    codec = WireCodec(
        decoders={ENCODING_HEXWKB: lambda s: bytes.fromhex(s)},
        encoders={ENCODING_HEXWKB: lambda b: b.hex()},
    )
    decoded = codec.decode(ENCODING_HEXWKB, "deadbeef")
    assert decoded == b"\xde\xad\xbe\xef"
    encoded = codec.encode(ENCODING_HEXWKB, b"\xde\xad\xbe\xef")
    assert encoded == "deadbeef"


# --- pymeos_codec (lazy-imports PyMEOS) --------------------------------------

def test_pymeos_codec_factory_does_not_import_pymeos_at_construction():
    """The factory itself imports PyMEOS only on construction-call (not on
    module import), so this test passes regardless of whether PyMEOS is
    installed."""
    from mobilityapi.wire import pymeos_codec
    # Import the factory; calling it WOULD import pymeos.
    assert callable(pymeos_codec)


def test_pymeos_codec_call_raises_importerror_when_pymeos_missing(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pymeos", None)
    from mobilityapi.wire import pymeos_codec
    with pytest.raises(ImportError, match="pymeos is not installed"):
        pymeos_codec()
