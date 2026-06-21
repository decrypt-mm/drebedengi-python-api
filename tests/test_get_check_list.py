"""Unit tests for api.get_check_list and api.get_check_to_record_list (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from drebedengi import DrebedengiAPI
from drebedengi.model import Check, CheckToRecord


# ---------------------------------------------------------------------------
# Fake SOAP responses
# ---------------------------------------------------------------------------

CHECK_LIST_RESPONSE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:ns1="urn:ddengi"'
    b' xmlns:ns2="http://xml.apache.org/xml-soap"'
    b' xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    b' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
    b"<SOAP-ENV:Body>"
    b"<ns1:getCheckListResponse>"
    b'<getCheckListReturn SOAP-ENC:arrayType="ns2:Map[2]" xsi:type="SOAP-ENC:Array">'
    # check 1 — with qr_sum and qr_date
    b'<item xsi:type="ns2:Map">'
    b'<item><key xsi:type="xsd:string">id</key><value xsi:type="xsd:string">501</value></item>'
    b'<item><key xsi:type="xsd:string">ext</key><value xsi:type="xsd:string">https://example.com/qr/1</value></item>'
    b'<item><key xsi:type="xsd:string">state</key><value xsi:type="xsd:string">done</value></item>'
    b'<item><key xsi:type="xsd:string">qr_sum</key><value xsi:type="xsd:string">150000</value></item>'
    b'<item><key xsi:type="xsd:string">qr_date</key><value xsi:type="xsd:string">2026-01-15 12:00:00</value></item>'
    b"</item>"
    # check 2 — without optional fields
    b'<item xsi:type="ns2:Map">'
    b'<item><key xsi:type="xsd:string">id</key><value xsi:type="xsd:string">502</value></item>'
    b'<item><key xsi:type="xsd:string">ext</key><value xsi:type="xsd:string">https://example.com/qr/2</value></item>'
    b'<item><key xsi:type="xsd:string">state</key><value xsi:type="xsd:string">pending</value></item>'
    b"</item>"
    b"</getCheckListReturn>"
    b"</ns1:getCheckListResponse>"
    b"</SOAP-ENV:Body>"
    b"</SOAP-ENV:Envelope>"
)

CHECK_TO_RECORD_RESPONSE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:ns1="urn:ddengi"'
    b' xmlns:ns2="http://xml.apache.org/xml-soap"'
    b' xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    b' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
    b"<SOAP-ENV:Body>"
    b"<ns1:getCheckToRecordListResponse>"
    b'<getCheckToRecordListReturn SOAP-ENC:arrayType="ns2:Map[1]" xsi:type="SOAP-ENC:Array">'
    b'<item xsi:type="ns2:Map">'
    b'<item><key xsi:type="xsd:string">id</key><value xsi:type="xsd:string">901</value></item>'
    b'<item><key xsi:type="xsd:string">check_id</key><value xsi:type="xsd:string">501</value></item>'
    b'<item><key xsi:type="xsd:string">record_id</key><value xsi:type="xsd:string">88001</value></item>'
    b"</item>"
    b"</getCheckToRecordListReturn>"
    b"</ns1:getCheckToRecordListResponse>"
    b"</SOAP-ENV:Body>"
    b"</SOAP-ENV:Envelope>"
)

EMPTY_RESPONSE_TEMPLATE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:ns1="urn:ddengi"'
    b' xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    b' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
    b"<SOAP-ENV:Body>"
    b"<ns1:%sResponse>"
    b'<%sReturn SOAP-ENC:arrayType="xsd:anyType[0]" xsi:type="SOAP-ENC:Array"/>'
    b"</ns1:%sResponse>"
    b"</SOAP-ENV:Body>"
    b"</SOAP-ENV:Envelope>"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_api_check(content: bytes = CHECK_LIST_RESPONSE) -> DrebedengiAPI:
    a = DrebedengiAPI.__new__(DrebedengiAPI)
    a.api_key, a.login, a.password = "k", "l", "p"
    a.soap_url, a.strict = "fake", True
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status_code = 200
    fake_response.content = content
    fake_client.service.getCheckList.return_value = fake_response
    fake_client.settings.return_value.__enter__ = lambda self: None
    fake_client.settings.return_value.__exit__ = lambda *args: None
    a.client = fake_client
    return a


def _mk_api_c2r(content: bytes = CHECK_TO_RECORD_RESPONSE) -> DrebedengiAPI:
    a = DrebedengiAPI.__new__(DrebedengiAPI)
    a.api_key, a.login, a.password = "k", "l", "p"
    a.soap_url, a.strict = "fake", True
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status_code = 200
    fake_response.content = content
    fake_client.service.getCheckToRecordList.return_value = fake_response
    fake_client.settings.return_value.__enter__ = lambda self: None
    fake_client.settings.return_value.__exit__ = lambda *args: None
    a.client = fake_client
    return a


# ---------------------------------------------------------------------------
# get_check_list tests
# ---------------------------------------------------------------------------

def test_get_check_list_parses_two_items() -> None:
    api = _mk_api_check()
    result = api.get_check_list()
    assert len(result) == 2
    assert all(isinstance(c, Check) for c in result)


def test_get_check_list_first_item_fields() -> None:
    api = _mk_api_check()
    checks = api.get_check_list()
    c = checks[0]
    assert c.id == 501
    assert c.ext == "https://example.com/qr/1"
    assert c.state == "done"
    assert c.qr_sum == 150000
    assert c.qr_date == "2026-01-15 12:00:00"


def test_get_check_list_optional_fields_absent() -> None:
    """Second check has no qr_sum / qr_date — defaults to None."""
    api = _mk_api_check()
    checks = api.get_check_list()
    c = checks[1]
    assert c.id == 502
    assert c.state == "pending"
    assert c.qr_sum is None
    assert c.qr_date is None


def test_get_check_list_passes_credentials() -> None:
    api = _mk_api_check()
    api.get_check_list()
    args = api.client.service.getCheckList.call_args.args
    assert args == ("k", "l", "p")


def test_get_check_list_with_id_list_passes_kwarg() -> None:
    api = _mk_api_check()
    api.get_check_list(id_list=[501])
    call_kwargs = api.client.service.getCheckList.call_args.kwargs
    assert call_kwargs.get("idList") is not None


def test_get_check_list_no_id_list_skips_kwarg() -> None:
    """Without id_list, idList must be SkipValue (not sent to server)."""
    import zeep
    api = _mk_api_check()
    api.get_check_list()
    call_kwargs = api.client.service.getCheckList.call_args.kwargs
    assert call_kwargs.get("idList") is zeep.xsd.SkipValue


# ---------------------------------------------------------------------------
# get_check_to_record_list tests
# ---------------------------------------------------------------------------

def test_get_check_to_record_list_parses_item() -> None:
    api = _mk_api_c2r()
    result = api.get_check_to_record_list()
    assert len(result) == 1
    assert isinstance(result[0], CheckToRecord)


def test_get_check_to_record_list_fields() -> None:
    api = _mk_api_c2r()
    link = api.get_check_to_record_list()[0]
    assert link.id == 901
    assert link.check_id == 501
    assert link.record_id == 88001


def test_get_check_to_record_list_passes_credentials() -> None:
    api = _mk_api_c2r()
    api.get_check_to_record_list()
    args = api.client.service.getCheckToRecordList.call_args.args
    assert args == ("k", "l", "p")


def test_get_check_to_record_list_with_id_list() -> None:
    api = _mk_api_c2r()
    api.get_check_to_record_list(id_list=[901])
    call_kwargs = api.client.service.getCheckToRecordList.call_args.kwargs
    assert call_kwargs.get("idList") is not None
