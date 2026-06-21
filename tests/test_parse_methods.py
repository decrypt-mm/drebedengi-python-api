"""Unit tests for api.parse_text_data and api.parse_push_data (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from drebedengi import DrebedengiAPI


# ---------------------------------------------------------------------------
# Fake SOAP responses
# ---------------------------------------------------------------------------

PARSE_TEXT_RESPONSE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:ns1="urn:ddengi"'
    b' xmlns:ns2="http://xml.apache.org/xml-soap"'
    b' xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    b' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
    b"<SOAP-ENV:Body>"
    b"<ns1:parseTextDataResponse>"
    b'<parseTextDataReturn SOAP-ENC:arrayType="ns2:Map[2]" xsi:type="SOAP-ENC:Array">'
    # Item 0 — matched
    b'<item xsi:type="ns2:Map">'
    b'<item><key xsi:type="xsd:string">operation_type</key><value xsi:type="xsd:string">3</value></item>'
    b'<item><key xsi:type="xsd:string">sum</key><value xsi:type="xsd:string">50000</value></item>'
    b'<item><key xsi:type="xsd:string">comment</key><value xsi:type="xsd:string">Coffee shop</value></item>'
    b"</item>"
    # Item 1 — not matched (empty map)
    b'<item xsi:type="ns2:Map">'
    b"</item>"
    b"</parseTextDataReturn>"
    b"</ns1:parseTextDataResponse>"
    b"</SOAP-ENV:Body>"
    b"</SOAP-ENV:Envelope>"
)

PARSE_PUSH_RESPONSE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:ns1="urn:ddengi"'
    b' xmlns:ns2="http://xml.apache.org/xml-soap"'
    b' xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    b' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
    b"<SOAP-ENV:Body>"
    b"<ns1:parsePushDataResponse>"
    b'<parsePushDataReturn SOAP-ENC:arrayType="ns2:Map[1]" xsi:type="SOAP-ENC:Array">'
    b'<item xsi:type="ns2:Map">'
    b'<item><key xsi:type="xsd:string">sum</key><value xsi:type="xsd:string">123400</value></item>'
    b'<item><key xsi:type="xsd:string">operation_type</key><value xsi:type="xsd:string">3</value></item>'
    b"</item>"
    b"</parsePushDataReturn>"
    b"</ns1:parsePushDataResponse>"
    b"</SOAP-ENV:Body>"
    b"</SOAP-ENV:Envelope>"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_api_text(content: bytes = PARSE_TEXT_RESPONSE) -> DrebedengiAPI:
    a = DrebedengiAPI.__new__(DrebedengiAPI)
    a.api_key, a.login, a.password = "k", "l", "p"
    a.soap_url, a.strict = "fake", True
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status_code = 200
    fake_response.content = content
    fake_client.service.parseTextData.return_value = fake_response
    fake_client.settings.return_value.__enter__ = lambda self: None
    fake_client.settings.return_value.__exit__ = lambda *args: None
    a.client = fake_client
    return a


def _mk_api_push(content: bytes = PARSE_PUSH_RESPONSE) -> DrebedengiAPI:
    a = DrebedengiAPI.__new__(DrebedengiAPI)
    a.api_key, a.login, a.password = "k", "l", "p"
    a.soap_url, a.strict = "fake", True
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status_code = 200
    fake_response.content = content
    fake_client.service.parsePushData.return_value = fake_response
    fake_client.settings.return_value.__enter__ = lambda self: None
    fake_client.settings.return_value.__exit__ = lambda *args: None
    a.client = fake_client
    return a


# ---------------------------------------------------------------------------
# parse_text_data tests
# ---------------------------------------------------------------------------

def test_parse_text_data_returns_two_dicts() -> None:
    api = _mk_api_text()
    result = api.parse_text_data(["Coffee 500r", "???"])
    assert len(result) == 2
    assert all(isinstance(r, dict) for r in result)


def test_parse_text_data_first_item_fields() -> None:
    api = _mk_api_text()
    result = api.parse_text_data(["Coffee 500r"])
    r = result[0]
    assert r["operation_type"] == "3"
    assert r["sum"] == "50000"
    assert r["comment"] == "Coffee shop"


def test_parse_text_data_unmatched_returns_empty_dict() -> None:
    api = _mk_api_text()
    result = api.parse_text_data(["Coffee 500r", "???"])
    assert result[1] == {}


def test_parse_text_data_passes_credentials() -> None:
    api = _mk_api_text()
    api.parse_text_data(["hello"])
    args = api.client.service.parseTextData.call_args.args
    assert args == ("k", "l", "p")


def test_parse_text_data_passes_default_kwargs() -> None:
    api = _mk_api_text()
    api.parse_text_data(["hello"])
    kwargs = api.client.service.parseTextData.call_args.kwargs
    assert kwargs["defPlaceFromId"] == "0"
    assert kwargs["defCatId"] == "0"
    assert kwargs["defSrcId"] == "0"
    assert kwargs["defPlaceToId"] == "0"
    assert kwargs.get("list") is not None


def test_parse_text_data_custom_defaults() -> None:
    api = _mk_api_text()
    api.parse_text_data(["x"], default_cat_id="9999", default_place_from_id="1234")
    kwargs = api.client.service.parseTextData.call_args.kwargs
    assert kwargs["defCatId"] == "9999"
    assert kwargs["defPlaceFromId"] == "1234"


# ---------------------------------------------------------------------------
# parse_push_data tests
# ---------------------------------------------------------------------------

def test_parse_push_data_returns_one_dict() -> None:
    api = _mk_api_push()
    result = api.parse_push_data(["Покупка 1234.00р Магазин"])
    assert len(result) == 1
    assert isinstance(result[0], dict)


def test_parse_push_data_fields() -> None:
    api = _mk_api_push()
    result = api.parse_push_data(["push text"])
    r = result[0]
    assert r["sum"] == "123400"
    assert r["operation_type"] == "3"


def test_parse_push_data_passes_credentials() -> None:
    api = _mk_api_push()
    api.parse_push_data(["push text"])
    args = api.client.service.parsePushData.call_args.args
    assert args == ("k", "l", "p")


def test_parse_push_data_passes_list_kwarg() -> None:
    api = _mk_api_push()
    api.parse_push_data(["push text"])
    kwargs = api.client.service.parsePushData.call_args.kwargs
    assert kwargs.get("list") is not None


def test_parse_push_data_no_default_params() -> None:
    """parsePushData must NOT send defPlaceFromId / defCatId etc (not in its WSDL signature)."""
    api = _mk_api_push()
    api.parse_push_data(["push text"])
    kwargs = api.client.service.parsePushData.call_args.kwargs
    assert "defPlaceFromId" not in kwargs
    assert "defCatId" not in kwargs
    assert "defSrcId" not in kwargs
    assert "defPlaceToId" not in kwargs
