""" Supporting utilities for working with XML & SOAP """

from __future__ import annotations

import typing
from attrs import NOTHING, fields_dict, has
from lxml import etree
from zeep import xsd
from zeep.helpers import guess_xsd_type

from typing import TYPE_CHECKING, Any, List, Type, TypeVar, Union, get_args, get_origin

if TYPE_CHECKING:
    from .model import Transaction

T = TypeVar("T")

# Cache resolved type hints per model class so we don't call get_type_hints() on every parse.
_resolved_hints_cache: dict[type, dict[str, type]] = {}


def _is_optional_type(resolved_type: type) -> bool:
    """Return True if *resolved_type* is ``X | None`` / ``Optional[X]`` (i.e. includes NoneType).

    Works correctly with both PEP-604 union syntax (``str | None``) and
    ``typing.Optional[str]`` / ``typing.Union[str, None]``.
    """
    origin = get_origin(resolved_type)
    if origin is Union:
        return type(None) in get_args(resolved_type)
    # Python 3.10+ ``types.UnionType`` (``str | None`` at runtime without __future__)
    import types as _types
    if isinstance(resolved_type, _types.UnionType):
        return type(None) in get_args(resolved_type)
    return False


def _get_optional_fields(model_type: type) -> frozenset[str]:
    """Return the set of field names whose resolved type includes NoneType."""
    if model_type not in _resolved_hints_cache:
        try:
            hints = typing.get_type_hints(model_type)
        except Exception:
            hints = {}
        _resolved_hints_cache[model_type] = hints
    hints = _resolved_hints_cache[model_type]
    return frozenset(name for name, t in hints.items() if _is_optional_type(t))

_get_xmlmap_value_by_key = etree.XPath("item/key[text() = $key]/../value/text()")
""" Gets value by key from an XML ns2:Map. """


def xmlmap_to_model(xmlmap: etree.Element, model_type: Type[T], *, strict: bool = True) -> T:
    """Converts XML ns2:Map to a model of type `model_type`.

    Args:
        xmlmap (etree.Element): xml subtree (ns2:Map) representing a model
        model_type (Type[T]): model type to map data into
        strict (bool, optional): fail if the returned data doesn't match the model. Defaults to True.

    Raises:
        ValueError: if `strict` is True and the returned data doesn't match the model.
        ValueError: if the model_type is not an attrs-based model.

    Returns:
        T: generated model instance
    """
    if not has(model_type):
        raise ValueError(f"{model_type} is not a model")

    model_fields = fields_dict(model_type)  # type: ignore # (until https://github.com/python-attrs/attrs/pull/997)
    optional_fields = _get_optional_fields(model_type)

    vals = {}
    for name, field in model_fields.items():
        # If a name is defined in the metadata => it has a different xml key, otherwise just use model field name
        key = field.metadata.get("xml", {}).get("name", name)
        value = _get_xmlmap_value_by_key(xmlmap, key=key)
        if value:
            vals[name] = value[0]
        elif field.default is not NOTHING:
            # Field has an explicit default — leave it to attrs (do not error out, even in strict mode).
            continue
        elif strict and name not in optional_fields:
            # Use resolved type hints (not field.type string) to detect optional fields.
            # Under `from __future__ import annotations`, field.type is a string annotation
            # like 'str | None', so isinstance(None, field.type) would raise TypeError.
            raise ValueError(
                f"Key <{name}> was not found in the element {etree.tostring(xmlmap, pretty_print=True)}"
            )

    try:
        ret = model_type(**vals)
    except (ValueError, TypeError) as exc:
        xml_repr = etree.tostring(xmlmap, pretty_print=True).decode(errors="replace")
        raise ValueError(f"Could not convert values from {xml_repr} to {model_type}") from exc

    return ret


def xmlmap_to_dict(xmlmap: etree.Element) -> dict[str, str]:
    """Converts an XML ns2:Map element to a flat ``{key: value}`` dict.

    Unlike :func:`xmlmap_to_model`, this does not coerce values into a typed model — it just
    returns raw strings keyed by the XML ``<key>`` elements. Useful for write-method responses
    where the server returns ad-hoc maps such as ``{server_id: ..., client_id: ...}``.
    """
    out: dict[str, str] = {}
    for item in xmlmap.findall("item"):
        key = item.findtext("key") or ""
        value = item.findtext("value") or ""
        out[key] = value
    return out


def generate_xml_array(values: List[Any]) -> xsd.ComplexType:
    """Generates a SOAP Array from a list of values.

    Args:
        values (List[Any]): a list of values to be converted to an XML SOAP Encoded Array.

    Returns:
        xsd.ComplexType: zeep XML ComplexType representing an XML SOAP Encoded Array.
    """
    Array = xsd.ComplexType(
        xsd.Sequence([xsd.Element("item", xsd.AnyType(), min_occurs=1, max_occurs="unbounded")]),  # type: ignore
        qname=etree.QName("{http://schemas.xmlsoap.org/soap/encoding/}Array"),
    )

    return Array(item=[xsd.AnyObject(guess_xsd_type(value), value) for value in values])  # type: ignore


def generate_xml_map_array(maps: List[Any]) -> xsd.ComplexType:
    """Generates a SOAP Array whose elements are already typed values (typically pre-built
    ns2:Map's from :func:`zeep.helpers.create_xml_soap_map`).

    Unlike :func:`generate_xml_array`, this does NOT wrap items into ``xsd.AnyObject`` — that
    extra wrapping double-encodes Maps and the server then receives them as Python repr
    strings instead of well-formed XML maps.
    """
    Array = xsd.ComplexType(
        xsd.Sequence([xsd.Element("item", xsd.AnyType(), min_occurs=1, max_occurs="unbounded")]),  # type: ignore
        qname=etree.QName("{http://schemas.xmlsoap.org/soap/encoding/}Array"),
    )
    return Array(item=maps)  # type: ignore


def check_same_transfer_transactions(tr1: Transaction, tr2: Transaction) -> bool:
    """Return True if *tr1* and *tr2* look like the two legs of the same transfer.

    Comment-matching semantics: comments are compared only when BOTH transactions
    carry a non-None comment.  When either comment is None the constraint is skipped —
    this avoids a false-positive where two unrelated commentless transfers would
    spuriously match simply because ``None == None``.  Transfer pairs created by
    drebedengi are always symmetric: if the user set a comment, both legs carry it;
    if not, both are None — so skipping the check when either side is absent is safe.
    """
    comments_match = (
        tr1.comment == tr2.comment
        if tr1.comment is not None and tr2.comment is not None
        else True
    )
    return (
        tr1.amount == -tr2.amount
        and tr1.budget_family_id == tr2.budget_family_id
        and comments_match
        and tr1.currency_id == tr2.currency_id
        and tr1.operation_date == tr2.operation_date
        and tr1.user_nuid == tr2.user_nuid
    )
