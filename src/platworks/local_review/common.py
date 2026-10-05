"""Bounded data and integrity helpers shared by the local review flow."""

import hashlib
import json
import re
from datetime import datetime, timezone

MAX_FILE = 2 * 1024 * 1024
MAX_BODY = 12 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}")


class ReviewError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


def refuse(code, message):
    raise ReviewError(code, message)


def encode(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(value):
    return digest(encode(value))


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                refuse("DUPLICATE_FIELD", "Duplicate JSON fields require source correction.")
            result[key] = value
        return result

    def invalid(_):
        refuse("INVALID_INPUT", "Non-finite JSON numbers are not supported.")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        encode(result)  # also rejects finite-looking JSON numbers that overflow
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        refuse("INVALID_INPUT", "Supply valid finite JSON within the documented layout.")


def text(value, field, *, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        refuse("INVALID_INPUT", f"Provide {field} (up to {limit} characters).")
    return value.strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def finding(code, message, *, path=""):
    return {"code": code, "message": message, "path": path}
