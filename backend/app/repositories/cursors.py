from __future__ import annotations

import base64
import json
from collections.abc import Mapping


def encode_cursor(values: Mapping[str, str]) -> str:
    payload = json.dumps(values, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> dict[str, str] | None:
    if cursor is None:
        return None
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = base64.b64decode(padded_cursor, altchars=b"-_", validate=True)
        values = json.loads(payload)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid cursor.") from error
    if not isinstance(values, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in values.items()
    ):
        raise ValueError("Invalid cursor.")
    return values
