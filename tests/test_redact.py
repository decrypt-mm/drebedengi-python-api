"""Unit tests for the _redact helper (fix 5 — 152-FZ credential masking)."""

from __future__ import annotations

import pytest

from drebedengi.api import _redact


@pytest.mark.parametrize(
    "input_text, should_not_contain",
    [
        # f-string debug form with quotes: login='myuser'
        ("Initialized DrebedengiAPI for login='myuser'. SOAP URL: x. Strict: True", "myuser"),
        # SOAP XML element form
        ("<login>myuser@example.com</login>", "myuser@example.com"),
        ("<password>s3cr3t!</password>", "s3cr3t!"),
        ("<api_key>ABCDEF123456</api_key>", "ABCDEF123456"),
        ("<apiKey>ABCDEF123456</apiKey>", "ABCDEF123456"),
        # f-string without quotes
        ("login=mylogin SOAP URL: x", "mylogin"),
        ("password=topsecret!", "topsecret!"),
    ],
)
def test_redact_removes_sensitive_value(input_text: str, should_not_contain: str) -> None:
    result = _redact(input_text)
    assert should_not_contain not in result
    assert "***" in result


def test_redact_preserves_non_sensitive_content() -> None:
    text = "Getting transactions with params: period_from=2026-01-01"
    result = _redact(text)
    assert "period_from=2026-01-01" in result


def test_redact_empty_string() -> None:
    assert _redact("") == ""


def test_redact_soap_fault_body() -> None:
    """Simulate a raw SOAP Fault body that echoes credentials — all must be masked."""
    body = (
        '<?xml version="1.0"?><SOAP-ENV:Envelope>'
        "<SOAP-ENV:Body><SOAP-ENV:Fault>"
        "<faultstring>Auth failed</faultstring>"
        "<detail><login>john@example.com</login><password>badpass</password></detail>"
        "</SOAP-ENV:Fault></SOAP-ENV:Body></SOAP-ENV:Envelope>"
    )
    result = _redact(body)
    assert "john@example.com" not in result
    assert "badpass" not in result
    assert "Auth failed" in result  # non-sensitive content preserved
