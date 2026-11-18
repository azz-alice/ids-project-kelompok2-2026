from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = ("token", "secret", "api_key", "apikey", "password", "authorization")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if any(word in str(key).lower() for word in SENSITIVE_KEYS):
                continue
            clean[key] = sanitize(item)
        return clean
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value
