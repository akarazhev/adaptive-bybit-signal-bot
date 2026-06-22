from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from urllib.parse import urlencode


def canonical_query(params: Mapping[str, object] | None) -> str:
    if not params:
        return ""
    normalized = {key: str(value) for key, value in params.items() if value is not None}
    return urlencode(sorted(normalized.items()))


def sign_get_request(
    *,
    timestamp_ms: int,
    api_key: str,
    secret: str,
    recv_window: int,
    params: Mapping[str, object] | None,
) -> str:
    """Create a Bybit V5 HMAC SHA256 signature for GET requests.

    For GET requests Bybit signs: timestamp + api_key + recv_window + query_string.
    """

    query = canonical_query(params)
    payload = f"{timestamp_ms}{api_key}{recv_window}{query}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
