"""Unit tests for the period_from/period_to XOR guard in get_transactions (fix 4)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from drebedengi import DrebedengiAPI


@pytest.fixture
def api() -> DrebedengiAPI:
    a = DrebedengiAPI.__new__(DrebedengiAPI)
    a.api_key = "k"
    a.login = "l"
    a.password = "p"
    a.soap_url = "fake"
    a.strict = True
    a.client = MagicMock()
    return a


def test_only_period_from_raises(api: DrebedengiAPI) -> None:
    """Passing only period_from (without period_to) must raise ValueError."""
    with pytest.raises(ValueError, match="period_to"):
        api.get_transactions(period_from=datetime(2026, 1, 1))


def test_only_period_to_raises(api: DrebedengiAPI) -> None:
    """Passing only period_to (without period_from) must raise ValueError."""
    with pytest.raises(ValueError, match="period_from"):
        api.get_transactions(period_to=datetime(2026, 1, 31))


_EMPTY_RECORD_LIST_RESPONSE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<SOAP-ENV:Envelope'
    b' xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:ns1="urn:ddengi"'
    b' xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    b' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
    b"<SOAP-ENV:Body>"
    b"<ns1:getRecordListResponse>"
    b'<getRecordListReturn SOAP-ENC:arrayType="ns2:Map[0]" xsi:type="SOAP-ENC:Array"/>'
    b"</ns1:getRecordListResponse>"
    b"</SOAP-ENV:Body>"
    b"</SOAP-ENV:Envelope>"
)


def _patch_api_client(api: DrebedengiAPI, content: bytes) -> None:
    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status_code = 200
    fake_response.content = content
    api.client.service.getRecordList.return_value = fake_response
    api.client.settings.return_value.__enter__ = lambda self: None
    api.client.settings.return_value.__exit__ = lambda *args: None


def test_both_none_does_not_raise(api: DrebedengiAPI) -> None:
    """Both None is valid (uses default report_period) — must not raise before the SOAP call."""
    _patch_api_client(api, _EMPTY_RECORD_LIST_RESPONSE)
    result = api.get_transactions()
    assert result == []


def test_both_supplied_does_not_raise(api: DrebedengiAPI) -> None:
    """Both period_from and period_to supplied is valid — must not raise before the SOAP call."""
    _patch_api_client(api, _EMPTY_RECORD_LIST_RESPONSE)
    result = api.get_transactions(
        period_from=datetime(2026, 1, 1), period_to=datetime(2026, 1, 31)
    )
    assert result == []
