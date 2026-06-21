"""Unit tests for api.set_category_list (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from drebedengi import DrebedengiAPI


FAKE_OK_RESPONSE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:ns1="urn:ddengi"'
    b' xmlns:ns2="http://xml.apache.org/xml-soap"'
    b' xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    b' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
    b"<SOAP-ENV:Body>"
    b"<ns1:setCategoryListResponse>"
    b'<setCategoryListReturn SOAP-ENC:arrayType="ns2:Map[1]" xsi:type="SOAP-ENC:Array">'
    b'<item xsi:type="ns2:Map">'
    b'<item><key xsi:type="xsd:string">server_id</key>'
    b'<value xsi:type="xsd:string">99001</value></item>'
    b'<item><key xsi:type="xsd:string">client_id</key>'
    b'<value xsi:type="xsd:int">1</value></item>'
    b'<item><key xsi:type="xsd:string">status</key>'
    b'<value xsi:type="xsd:string">inserted</value></item>'
    b"</item>"
    b"</setCategoryListReturn>"
    b"</ns1:setCategoryListResponse>"
    b"</SOAP-ENV:Body>"
    b"</SOAP-ENV:Envelope>"
)


def _mk_api(content: bytes = FAKE_OK_RESPONSE) -> DrebedengiAPI:
    a = DrebedengiAPI.__new__(DrebedengiAPI)
    a.api_key, a.login, a.password = "k", "l", "p"
    a.soap_url, a.strict = "fake", True
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status_code = 200
    fake_response.content = content
    fake_client.service.setCategoryList.return_value = fake_response
    fake_client.settings.return_value.__enter__ = lambda self: None
    fake_client.settings.return_value.__exit__ = lambda *args: None
    a.client = fake_client
    return a


def test_set_category_list_parses_server_response() -> None:
    api = _mk_api()
    result = api.set_category_list([
        {
            "client_id": 1,
            "parent_id": -1,
            "type": 3,
            "name": "Test Category",
            "is_hidden": False,
            "is_for_duty": False,
            "sort": 100,
        }
    ])
    assert result == [{"server_id": "99001", "client_id": "1", "status": "inserted"}]


def test_set_category_list_passes_credentials_positionally() -> None:
    api = _mk_api()
    api.set_category_list([
        {
            "client_id": 1,
            "parent_id": -1,
            "type": 3,
            "name": "Cat",
            "is_hidden": False,
            "is_for_duty": False,
            "sort": 0,
        }
    ])
    args = api.client.service.setCategoryList.call_args.args
    assert args == ("k", "l", "p")


def test_set_category_list_passes_list_kwarg() -> None:
    api = _mk_api()
    api.set_category_list([
        {
            "client_id": 5,
            "parent_id": -1,
            "type": 3,
            "name": "Another",
            "is_hidden": True,
            "is_for_duty": True,
            "sort": 10,
        }
    ])
    call_kwargs = api.client.service.setCategoryList.call_args.kwargs
    assert call_kwargs.get("list") is not None


def test_set_category_list_empty_returns_empty() -> None:
    api = _mk_api()
    assert api.set_category_list([]) == []
    api.client.service.setCategoryList.assert_not_called()


def test_set_category_list_update_uses_server_id() -> None:
    """Updating an existing category passes server_id in the record dict."""
    api = _mk_api()
    api.set_category_list([
        {
            "server_id": 99001,
            "parent_id": -1,
            "type": 3,
            "name": "Renamed",
            "is_hidden": False,
            "is_for_duty": False,
            "sort": 200,
        }
    ])
    # The call must have happened (no early-return for non-empty list)
    api.client.service.setCategoryList.assert_called_once()
