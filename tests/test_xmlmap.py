"""Unit tests for xmlmap_to_model and models that hit XML edge cases."""

from __future__ import annotations

import pytest
from lxml import etree

from drebedengi.model import Currency, Transaction
from drebedengi.utils import check_same_transfer_transactions, xmlmap_to_model


NS = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema"'


def _make_currency_xml(*, with_code: str | None) -> etree.Element:
    code_tag = (
        f'<value xsi:type="xsd:string">{with_code}</value>'
        if with_code is not None
        else '<value xsi:type="xsd:string"/>'
    )
    src = f"""<item {NS}>
        <item><key>id</key><value xsi:type="xsd:string">42</value></item>
        <item><key>name</key><value xsi:type="xsd:string">руб</value></item>
        <item><key>course</key><value xsi:type="xsd:string">1</value></item>
        <item><key>code</key>{code_tag}</item>
        <item><key>family_id</key><value xsi:type="xsd:string">283054</value></item>
        <item><key>is_default</key><value xsi:type="xsd:string">t</value></item>
        <item><key>is_autoupdate</key><value xsi:type="xsd:string">f</value></item>
        <item><key>is_hidden</key><value xsi:type="xsd:string">f</value></item>
    </item>"""
    return etree.fromstring(src)


# ---------------------------------------------------------------------------
# Minimal Transaction XML — omits all optional fields (comment, oper_timestamp,
# group_id) to exercise the optional-field path in xmlmap_to_model.
# Under the unfixed code this would raise TypeError (isinstance(None, 'str | None'))
# for every absent optional field when strict=True.
# ---------------------------------------------------------------------------

_TRANSACTION_XML_MINIMAL = f"""<item {NS}>
    <item><key>id</key><value xsi:type="xsd:string">1001</value></item>
    <item><key>budget_object_id</key><value xsi:type="xsd:string">10</value></item>
    <item><key>user_nuid</key><value xsi:type="xsd:string">5</value></item>
    <item><key>budget_family_id</key><value xsi:type="xsd:string">283054</value></item>
    <item><key>is_duty</key><value xsi:type="xsd:string">f</value></item>
    <item><key>operation_date</key><value xsi:type="xsd:string">2026-01-15 12:00:00</value></item>
    <item><key>currency_id</key><value xsi:type="xsd:string">1</value></item>
    <item><key>operation_type</key><value xsi:type="xsd:string">3</value></item>
    <item><key>place_id</key><value xsi:type="xsd:string">7</value></item>
    <item><key>sum</key><value xsi:type="xsd:string">-50000</value></item>
</item>"""


@pytest.fixture
def transaction_minimal_xml() -> etree.Element:
    """Transaction XML with all optional fields absent (comment, oper_timestamp, group_id)."""
    return etree.fromstring(_TRANSACTION_XML_MINIMAL)


def test_currency_with_iso_code():
    xml = _make_currency_xml(with_code="USD")
    cur = xmlmap_to_model(xml, Currency, strict=True)
    assert cur.id == 42
    assert cur.user_name == "руб"
    assert cur.currency_code == "USD"
    assert cur.is_default is True


def test_currency_without_iso_code_does_not_crash():
    """Regression: user-defined currencies (e.g. RUB nicknamed 'руб') may have an empty <code>.
    The model must tolerate this and set currency_code=None instead of raising ValueError.
    """
    xml = _make_currency_xml(with_code=None)
    cur = xmlmap_to_model(xml, Currency, strict=True)
    assert cur.id == 42
    assert cur.user_name == "руб"
    assert cur.currency_code is None


# ---------------------------------------------------------------------------
# Fix 1 regression: optional-field detection must not raise TypeError under
# `from __future__ import annotations` when field.type is a string annotation.
# Fix 2 regression: Transaction.comment must be None (not "None") when absent.
# ---------------------------------------------------------------------------

def test_transaction_optional_fields_absent_strict(transaction_minimal_xml: etree.Element) -> None:
    """xmlmap_to_model in strict=True must NOT raise when optional fields are absent.

    Covers audit fix 1 (broken isinstance(None, field.type) under future-annotations)
    and fix 2 (comment converter must preserve None instead of producing 'None').
    """
    tr = xmlmap_to_model(transaction_minimal_xml, Transaction, strict=True)
    assert tr.id == 1001
    assert tr.amount == -50000
    # Fix 2: comment absent from XML → must be None, not the string "None"
    assert tr.comment is None
    assert tr.oper_utc_timestamp is None
    assert tr.group_id is None


_TRANSACTION_XML_WITH_COMMENT = f"""<item {NS}>
    <item><key>id</key><value xsi:type="xsd:string">1001</value></item>
    <item><key>budget_object_id</key><value xsi:type="xsd:string">10</value></item>
    <item><key>user_nuid</key><value xsi:type="xsd:string">5</value></item>
    <item><key>budget_family_id</key><value xsi:type="xsd:string">283054</value></item>
    <item><key>is_duty</key><value xsi:type="xsd:string">f</value></item>
    <item><key>operation_date</key><value xsi:type="xsd:string">2026-01-15 12:00:00</value></item>
    <item><key>currency_id</key><value xsi:type="xsd:string">1</value></item>
    <item><key>operation_type</key><value xsi:type="xsd:string">3</value></item>
    <item><key>place_id</key><value xsi:type="xsd:string">7</value></item>
    <item><key>sum</key><value xsi:type="xsd:string">-50000</value></item>
    <item><key>comment</key><value xsi:type="xsd:string">test comment</value></item>
</item>"""


def test_transaction_optional_fields_present() -> None:
    """When optional fields are present they are parsed correctly."""
    xml = etree.fromstring(_TRANSACTION_XML_WITH_COMMENT)
    tr = xmlmap_to_model(xml, Transaction, strict=True)
    assert tr.comment == "test comment"


def test_transaction_required_field_missing_raises(transaction_minimal_xml: etree.Element) -> None:
    """Removing a REQUIRED field from the XML must raise ValueError in strict mode."""
    # Strip the <id> item from the minimal XML
    src = _TRANSACTION_XML_MINIMAL.replace(
        '<item><key>id</key><value xsi:type="xsd:string">1001</value></item>\n    ', ""
    )
    xml = etree.fromstring(src)
    with pytest.raises(ValueError, match="id"):
        xmlmap_to_model(xml, Transaction, strict=True)


# ---------------------------------------------------------------------------
# Fix 3 regression: check_same_transfer_transactions with None comments.
# ---------------------------------------------------------------------------

def _make_transfer_pair(comment1: str | None, comment2: str | None):
    """Build a minimal pair of Transaction objects for transfer-match testing."""
    from datetime import datetime

    base = dict(
        budget_object_id=10,
        user_nuid=5,
        budget_family_id=283054,
        is_loan_transfer=False,
        operation_date=datetime(2026, 1, 15, 12, 0, 0),
        currency_id=1,
        operation_type=3,  # EXPENSE
        account_id=7,
    )
    tr1 = Transaction(id=1, amount=50000, comment=comment1, **base)
    tr2 = Transaction(id=2, amount=-50000, comment=comment2, **base)
    return tr1, tr2


def test_transfer_match_both_none_comments() -> None:
    """Two transfers with None comments should still match (symmetric absence is OK)."""
    tr1, tr2 = _make_transfer_pair(None, None)
    # Both None → skip comment constraint → match on other fields
    assert check_same_transfer_transactions(tr1, tr2) is True


def test_transfer_match_both_equal_comments() -> None:
    tr1, tr2 = _make_transfer_pair("rent", "rent")
    assert check_same_transfer_transactions(tr1, tr2) is True


def test_transfer_no_match_different_comments() -> None:
    tr1, tr2 = _make_transfer_pair("rent", "food")
    assert check_same_transfer_transactions(tr1, tr2) is False


def test_transfer_match_one_none_one_set() -> None:
    """One transfer has comment, the other doesn't — constraint skipped, match by other fields."""
    tr1, tr2 = _make_transfer_pair("rent", None)
    # Per fix 3 semantics: skip comment constraint when either side is None
    assert check_same_transfer_transactions(tr1, tr2) is True
