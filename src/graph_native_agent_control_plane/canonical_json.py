"""Strict JSON ingestion and deterministic canonical serialization."""

from __future__ import annotations

import hashlib
import json
import math
from typing import NoReturn, cast

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None


class CanonicalJsonError(ValueError):
    """Raised when input cannot participate in deterministic JSON processing."""


def _reject_constant(value: str) -> NoReturn:
    raise CanonicalJsonError(f"non-finite JSON number is forbidden: {value}")


def _object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJsonError(f"duplicate object member: {key}")
        result[key] = value
    return result


def _validate_json_value(value: object) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJsonError("non-finite JSON number is forbidden")
        return
    if isinstance(value, list):
        for item in cast(list[object], value):
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise CanonicalJsonError("JSON object names must be strings")
            _validate_json_value(item)
        return
    raise CanonicalJsonError(f"unsupported JSON value: {type(value).__name__}")


def loads_strict(data: bytes) -> JsonValue:
    """Parse one UTF-8 JSON value while rejecting ambiguous or non-standard input."""

    if data.startswith(b"\xef\xbb\xbf"):
        raise CanonicalJsonError("UTF-8 BOM is forbidden")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CanonicalJsonError(f"invalid UTF-8 at byte {exc.start}") from None

    decoder = json.JSONDecoder(
        object_pairs_hook=_object_from_pairs,
        parse_constant=_reject_constant,
    )
    source = text.lstrip()
    try:
        raw_value, end = decoder.raw_decode(source)
    except json.JSONDecodeError as exc:
        raise CanonicalJsonError(f"invalid JSON at character {exc.pos}: {exc.msg}") from None
    if source[end:].strip():
        raise CanonicalJsonError("trailing data after JSON value")
    value = cast(object, raw_value)
    _validate_json_value(value)
    return cast(JsonValue, value)


def canonical_bytes(value: object) -> bytes:
    """Serialize a JSON value to sorted, compact UTF-8 with one trailing LF."""

    _validate_json_value(value)
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return rendered.encode("utf-8", errors="strict") + b"\n"
    except (UnicodeEncodeError, ValueError) as exc:
        raise CanonicalJsonError(f"value cannot be serialized canonically: {exc}") from None


def canonical_sha256(value: object) -> str:
    """Return the lowercase SHA-256 digest of canonical bytes."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()
