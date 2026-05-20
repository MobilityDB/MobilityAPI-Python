"""Wire-layer codec — decode HTTP request bodies to PyMEOS objects, encode
PyMEOS results back to HTTP response payloads.

The catalog (``vendor/meos-api/meos-idl.json``, after the enrichment pass)
labels each parameter and the result with one of the supported encodings:

- ``mfjson`` — Moving Features JSON (the OGC API – Moving Features
  standard wire format for temporal trajectories).
- ``text``   — EWKT (Extended Well-Known Text), the human-readable form.
- ``wkb``    — EWKB (Extended Well-Known Binary), the wire-compact form.

``Wire`` resolves a per-parameter or per-result *encoding name* to the
right PyMEOS factory / serialiser. It does not pick the encoding: that
decision is made by the catalog at generation time and surfaced via the
``x-meos-{decode,encode}`` extensions on the OpenAPI spec.

The module is split so that the encoding/decoding logic is *resolver-
agnostic*. Production runs against PyMEOS; the tests use a stub
``WireCodec`` whose factory map is explicit.
"""

from __future__ import annotations

from typing import Any, Callable


# Canonical encoding names appearing on catalog `wire.params[].decode`
# and `wire.result.encode` fields.
ENCODING_MFJSON = "mfjson"
ENCODING_TEXT = "text"
ENCODING_WKB = "wkb"
ENCODING_HEXWKB = "hexwkb"


class WireCodec:
    """Codec keyed by encoding name (``mfjson``, ``text``, ``wkb``, …).

    The decode map turns an inbound wire value (str / bytes) into a
    PyMEOS object. The encode map turns a PyMEOS object back into a
    wire value. Each map is keyed by the *encoding name* the catalog
    labels the parameter / result with.

    Stub-mode construction supplies the maps explicitly. Production
    construction asks PyMEOS for the factories.
    """

    def __init__(
        self,
        decoders: dict[str, Callable[[Any], Any]],
        encoders: dict[str, Callable[[Any], Any]],
    ) -> None:
        self._decoders = decoders
        self._encoders = encoders

    def decode(self, encoding: str, wire_value: Any) -> Any:
        """Apply the decoder for ``encoding`` to ``wire_value``."""
        try:
            return self._decoders[encoding](wire_value)
        except KeyError:
            raise KeyError(
                f"WireCodec has no decoder for encoding `{encoding}`. "
                f"Known: {sorted(self._decoders)}"
            )

    def encode(self, encoding: str, value: Any) -> Any:
        """Apply the encoder for ``encoding`` to ``value``."""
        try:
            return self._encoders[encoding](value)
        except KeyError:
            raise KeyError(
                f"WireCodec has no encoder for encoding `{encoding}`. "
                f"Known: {sorted(self._encoders)}"
            )

    def has_decoder(self, encoding: str) -> bool:
        return encoding in self._decoders

    def has_encoder(self, encoding: str) -> bool:
        return encoding in self._encoders


def stub_codec(
    decoders: dict[str, Callable[[Any], Any]] | None = None,
    encoders: dict[str, Callable[[Any], Any]] | None = None,
) -> WireCodec:
    """Build a stub WireCodec from explicit maps (for tests)."""
    return WireCodec(
        decoders=decoders or {},
        encoders=encoders or {},
    )


def pymeos_codec() -> WireCodec:
    """Build the production WireCodec that bridges to PyMEOS.

    Lazy-imports PyMEOS the first time the codec is used. The decoders
    accept the PyMEOS factory entry points, and the encoders use the
    PyMEOS object's own ``__str__`` / serialisation methods.

    The factory entry points are deliberately not type-specific (e.g.,
    the catalog says ``decode = "temporal_in"`` and that's a single
    PyMEOS factory that dispatches on the input). When PyMEOS exposes
    more granular factories per temporal subtype, this map grows.
    """
    try:
        import pymeos  # noqa: WPS433 - lazy import on purpose
    except ImportError as e:
        raise ImportError(
            "pymeos is not installed. WireCodec.pymeos_codec() requires "
            "the `pymeos` package on the Python path."
        ) from e

    def _from_mfjson(s):
        # PyMEOS exposes Temporal.from_mfjson on the family root class.
        # The dispatch by base type happens inside PyMEOS.
        return pymeos.TPoint.from_mfjson(s) if isinstance(s, str) else s

    def _from_wkb(b):
        return pymeos.TPoint.from_wkb(b)

    def _from_hexwkb(s):
        return pymeos.TPoint.from_hexwkb(s)

    def _from_text(s):
        return pymeos.TPoint(s)  # PyMEOS constructor accepts EWKT

    return WireCodec(
        decoders={
            ENCODING_MFJSON: _from_mfjson,
            ENCODING_WKB:    _from_wkb,
            ENCODING_HEXWKB: _from_hexwkb,
            ENCODING_TEXT:   _from_text,
        },
        encoders={
            ENCODING_MFJSON: lambda obj: obj.as_mfjson() if hasattr(obj, "as_mfjson") else str(obj),
            ENCODING_WKB:    lambda obj: obj.as_wkb()    if hasattr(obj, "as_wkb")    else bytes(str(obj), "utf-8"),
            ENCODING_HEXWKB: lambda obj: obj.as_hexwkb() if hasattr(obj, "as_hexwkb") else str(obj),
            ENCODING_TEXT:   str,
        },
    )
