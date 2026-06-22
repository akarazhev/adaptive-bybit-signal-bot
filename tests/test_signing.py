from __future__ import annotations

import hashlib
import hmac

from adaptive_bybit_bot.exchange.signing import canonical_query, sign_get_request


def test_canonical_query_sorts_keys() -> None:
    assert canonical_query({"symbol": "BTCUSDT", "category": "spot", "limit": 50}) == (
        "category=spot&limit=50&symbol=BTCUSDT"
    )


def test_sign_get_request_matches_hmac_sha256() -> None:
    params = {"accountType": "UNIFIED", "coin": "BTC,USDT"}
    expected_payload = "123456key5000" + canonical_query(params)
    expected = hmac.new(b"secret", expected_payload.encode(), hashlib.sha256).hexdigest()
    actual = sign_get_request(
        timestamp_ms=123456,
        api_key="key",
        secret="secret",
        recv_window=5000,
        params=params,
    )
    assert actual == expected
