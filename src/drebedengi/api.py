import logging
import re
from datetime import datetime

import zeep
from lxml import etree
from requests.models import Response
from zeep.client import Client
from zeep.transports import Transport

from .model import (
    Account,
    ChangeRecord,
    Check,
    CheckToRecord,
    Currency,
    ExpenseCategory,
    IncomeSource,
    ReportFilterType,
    ReportGrouping,
    ReportPeriod,
    Tag,
    Transaction,
    TransactionType,
)
from .utils import generate_xml_array, generate_xml_map_array, xmlmap_to_dict, xmlmap_to_model

from typing import Any, Dict, List, Literal

DeletableObjectType = Literal[
    "waste", "income", "move", "change", "object", "currency", "tag", "accum"
]

logger = logging.getLogger(__name__)

# Patterns that identify credential/PII values in log messages and SOAP body text.
# Each pattern targets a key=value or XML-element form.  Replacements use '***'.
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # SOAP XML elements: <login>value</login>, <password>…</password>, <apiKey>…</apiKey>
    (re.compile(r"(<(?:login|password|api[_-]?key)>)[^<]*(</)", re.IGNORECASE), r"\1***\2"),
    # f-string debug forms: login='value', password='value', api_key='value'
    (re.compile(r"((?:login|password|api[_-]?key)=')[^']*(')", re.IGNORECASE), r"\1***\2"),
    # f-string debug forms without quotes: login=value (word boundary)
    (re.compile(r"((?:login|password|api[_-]?key)=)\S+", re.IGNORECASE), r"\1***"),
]


def _redact(text: str) -> str:
    """Mask credential/PII substrings in *text* before writing to logs or exceptions.

    Applies a set of regex replacements targeting api_key/login/password in both
    SOAP XML form and Python f-string debug form.  Does not alter structure — only
    replaces the value portion with ``***``.
    """
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

DREBEDENGI_DEFAULT_SOAP_URL = "https://www.drebedengi.ru/soap/dd.wsdl"
DREBEDENGI_DEFAULT_TIMEOUTS = (60, 300)


class DrebedengiAPIError(Exception):
    """Drebedengi API error class."""

    def __init__(
        self, message: str, status_code: int, response_text: str, fault_code: str | None = None
    ) -> None:
        """Initialize."""
        self.status_code = status_code
        self.response_text = response_text
        self.fault_code = fault_code
        super().__init__(message, fault_code)

    @classmethod
    def check_and_raise(cls, response: Response) -> None:
        """
        Check if response is an API error and immediatelly raise it.
        """
        if not response.ok:
            raise cls("Network error", response.status_code, _redact(response.text))

        root = etree.fromstring(response.content)
        fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
        if fault is not None:
            raise cls(
                fault.findtext(".//faultstring"),
                response.status_code,
                _redact(response.text),
                fault.findtext(".//faultcode"),
            )


class DrebedengiAPI:
    """Drebedengi API Wrapper class."""

    def __init__(
        self,
        api_key: str,
        login: str,
        password: str,
        *,
        strict: bool = True,
        soap_url: str = DREBEDENGI_DEFAULT_SOAP_URL,
        wsdl_timeout: float = DREBEDENGI_DEFAULT_TIMEOUTS[0],
        operation_timeout: float = DREBEDENGI_DEFAULT_TIMEOUTS[1],
    ) -> None:
        """API Wrapper class

        Args:
            api_key (str): api_key (get from drebedengi via support)
            login (str): your login
            password (str): your password
            strict (bool, optional): strict mode - API calls will fail if the returned data doesn't match the model. Defaults to True.
            soap_url (str, optional): Optional alternative SOAP URL. Defaults to DREBEDENGI_DEFAULT_SOAP_URL.
            wsdl_timeout (float, optional): WSDL download timeout. Defaults to 60s.
            operation_timeout (float, optional): Operation timeout. Defaults to 300s.
        """
        self.api_key = api_key
        self.login = login
        self.password = password
        self.soap_url = soap_url
        self.strict = strict
        transport = Transport(timeout=wsdl_timeout, operation_timeout=operation_timeout)
        self.client = Client(soap_url, transport=transport)  # type: ignore

        logger.debug(
            _redact(
                f"Initialized DrebedengiAPI for {login=}. SOAP URL: {self.soap_url}. Strict: {self.strict}"
            )
        )

    def get_transactions(
        self,
        *,
        relative_date: datetime | None = None,
        period_from: datetime | None = None,
        period_to: datetime | None = None,
        account_filter: ReportFilterType = ReportFilterType.NONE,
        account_filter_ids: List[int] | None = None,
        tag_filter: ReportFilterType = ReportFilterType.NONE,
        tag_filter_ids: List[int] | None = None,
        category_filter: ReportFilterType = ReportFilterType.NONE,
        category_filter_ids: List[int] | None = None,
        include_types: TransactionType = TransactionType.ANY,
        convert_to_currency_id: int = 0,
        aggregated: bool = False,
        group_by: ReportGrouping = ReportGrouping.NONE,
        report_period: ReportPeriod = ReportPeriod.LAST_20_RECORD,
        id_list: List[int] | None = None,
    ) -> List[Transaction]:
        """
        Implements getRecordList API

        Original wsdl description:
            Retrievs record list (array of arrays) or report table by parameters; [params] => array of following parameters: 'is_report' [true|false (no default)] - retrievs data for report only or full records (waste, incomes, moves, changes) for export; 'relative_date' [YYYY-MM-DD (NOW by default)] - all data will be retrieved relative to this value, according to 'r_period' value; 'period_to', 'period_from' [YYYY-MM-DD] - custom period, if 'r_period' = 0; 'is_show_duty' [true(default)|false] - whether or not include duty record; 'r_period' [custom period = 0, this month = 1, today = 7, last month = 2, this quart = 3, this year = 4, last year = 5, all time = 6, last 20 record = 8 (default)] - period for which data will be obtained; 'r_what' [income = 2, waste = 3 (default), move = 4, change = 5, all types = 6] - type of data you want to get; 'r_who' [0 (default) - all users, int8 = user ID] - The data of the user to obtain, in the case of multiplayer mode; 'r_how' [show record list by detail = 1 (default), group incomes by source = 2, group wastes by category = 3] - Values 2 and 3 are for 'report' mode only# How to group the result record list; 'r_middle' [No average = 0 (default), Average monthly = 2592000, Average weekly = 604800, Averaged over days = 86400] - How to average the data, if r_how = 2 or 3; 'r_currency' [Original currency = 0 (default), int8 = currency ID] - Convert or not in to given currency; 'r_is_place', 'r_is_tag', 'r_is_category' [Include all = 0 (default), Include only selected = 1, All except selected = 2] - Exclude or include 'r_place', 'r_tag' or 'r_category' respectively; 'r_place', 'r_tag', 'r_category' [Array] - Array of numeric values for place ID, tag ID or category ID respectively; If parameter [idList] is given, it will be treat as ID list of objects to retrieve# this is used for synchronization;
        """

        logger.debug(
            f"Getting transactions with the following params: {relative_date=}, {period_from=}, {period_to=}, {account_filter=}, {account_filter_ids=}, {tag_filter=}, {tag_filter_ids=}, {category_filter=}, {category_filter_ids=}, {include_types=}, {convert_to_currency_id=}, {aggregated=}, {group_by=}, {report_period=}"
        )

        if not aggregated and group_by != ReportGrouping.NONE:
            raise ValueError("group_by can be used only with aggregated=True")

        if account_filter != ReportFilterType.NONE and account_filter_ids is None:
            raise ValueError("account_filter_ids must be set if account_filter is not NONE")

        if tag_filter != ReportFilterType.NONE and tag_filter_ids is None:
            raise ValueError("tag_filter_ids must be set if tag_filter is not NONE")

        if category_filter != ReportFilterType.NONE and category_filter_ids is None:
            raise ValueError("category_filter_ids must be set if category_filter is not NONE")

        pdict: Dict[str, Any] = {
            "r_period": int(report_period),
            "is_report": aggregated,
            "is_show_duty": True,  # this is a bogus param that allows to show or filter out transfers to liability accounts when only expenses are requested
            "r_how": int(group_by),
            "r_what": int(include_types),
            "r_currency": convert_to_currency_id,
            "r_is_place": int(account_filter),
            "r_is_tag": int(tag_filter),
            "r_is_category": int(category_filter),
        }

        if account_filter != ReportFilterType.NONE:
            pdict["r_place"] = account_filter_ids

        if tag_filter != ReportFilterType.NONE:
            pdict["r_tag"] = tag_filter_ids

        if category_filter != ReportFilterType.NONE:
            pdict["r_category"] = category_filter_ids

        if include_types == TransactionType.EXPENSE:
            pdict["is_show_duty"] = False

        if relative_date is None:
            relative_date = datetime.now()

        pdict["relative_date"] = relative_date.strftime("%Y-%m-%d")

        if (period_from is None) != (period_to is None):
            # Exactly one of the two boundaries was supplied — this is almost certainly a
            # caller bug: the server would silently ignore the partial specification and fall
            # back to report_period, producing a misleadingly wrong result.
            missing = "period_to" if period_to is None else "period_from"
            provided = "period_from" if period_to is None else "period_to"
            raise ValueError(
                f"Both period_from and period_to must be supplied together, "
                f"or both must be None. Got {provided} but {missing} is missing."
            )

        if period_from is not None and period_to is not None:
            pdict["period_from"] = period_from.strftime("%Y-%m-%d")
            pdict["period_to"] = period_to.strftime("%Y-%m-%d")
            pdict["r_period"] = int(ReportPeriod.CUSTOM_PERIOD)
            del pdict["relative_date"]

        params = zeep.helpers.create_xml_soap_map(pdict)  # type: ignore

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        if aggregated:
            raise NotImplementedError("aggregated is not implemented yet")

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getRecordList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
                params=params,
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getRecordListReturn/item/value")

        return [xmlmap_to_model(item, Transaction, strict=self.strict) for item in items]

    def set_record_list(self, records: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Implements setRecordList API — insert or update transactions in bulk.

        Each record is a dict with one of the ID keys (which decides the action):

            - ``server_id`` (int): existing record ID — *update* this record on the server
            - ``client_id`` (int): an arbitrary local ID — *insert* a new record;
              the server's reply will map this client_id back to the assigned server_id

        Other fields:

            - ``place_id`` (int): account ID (the "where the money was" account)
            - ``budget_object_id`` (int): category ID for waste, source ID for incomes,
              or destination place_id for transfers / currency changes
            - ``sum`` (int): absolute value in hundredths (kopecks)
            - ``operation_date`` (str): ``"YYYY-MM-DD HH:MM:SS"``
            - ``comment`` (str): UTF-8 text, up to 2048 chars
            - ``currency_id`` (int)
            - ``operation_type`` (:class:`TransactionType` or int):
              ``INCOME=2, EXPENSE=3, TRANSFER=4, EXCHANGE=5``
            - ``is_duty`` (bool, default ``False``)
            - ``server_move_id`` / ``client_move_id`` (int): for the *second* part of a transfer
            - ``server_change_id`` / ``client_change_id`` (int): for the *second* part of a
              currency exchange

        Returns the array of ``{server_id, client_id}`` maps that the server sent back.
        For inserts, ``client_id`` echoes what you passed in; for updates, ``server_id`` echoes
        what you passed in. Save these mappings to translate local IDs into authoritative ones.

        Original WSDL description:
            Insert or update record list; [list] => array (indexes must be 0,1,2...N) of arrays;
            see WSDL for the full field list. Returns the array of server IDs successfully
            changed; the client MUST save server IDs corresponded to client IDs for subsequent
            'update' and 'delete' calls.
        """
        if not records:
            return []

        # Normalize: enums → ints, TransactionType.value, etc.
        normalized: List[Dict[str, Any]] = []
        for raw in records:
            r = dict(raw)
            op_type = r.get("operation_type")
            if isinstance(op_type, TransactionType):
                r["operation_type"] = int(op_type)
            normalized.append(r)

        # SOAP wants a SOAP-encoded array of ns2:Map's, one Map per record. Use the
        # map-aware helper — generate_xml_array would double-wrap the maps and the server
        # would then receive Python repr strings.
        list_xml = generate_xml_map_array(
            [zeep.helpers.create_xml_soap_map(r) for r in normalized]  # type: ignore
        )

        with self.client.settings(raw_response=True, strict=False):
            result = self.client.service.setRecordList(
                self.api_key,
                self.login,
                self.password,
                list=list_xml,
            )
            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        # setRecordListReturn is a SOAP-encoded Array of Maps, where each Map directly contains
        # the server_id / client_id / status key-value pairs (unlike getRecordListReturn whose
        # items are key=id + value=Map).
        items: List[etree.Element] = root.findall(".//setRecordListReturn/item")
        return [xmlmap_to_dict(item) for item in items]

    def delete_object(self, *, object_id: int, object_type: DeletableObjectType) -> bool:
        """
        Implements deleteObject API — delete a single object on the server.

        Args:
            object_id: ID of the object to delete.
            object_type: one of ``"waste"``, ``"income"``, ``"move"``, ``"change"``,
                ``"object"``, ``"currency"``, ``"tag"``, ``"accum"``.
                ``"object"`` covers waste categories, income sources and accounts (places).
                For ``"move"`` and ``"change"`` records, the second part of the pair is
                deleted automatically by the server.

        Returns:
            ``True`` on success.

        Raises:
            DrebedengiAPIError: on any server-side error, including the "other object connected
                to this ID — delete them first" case (you'll need to delete dependants in the
                right order).

        Original WSDL description:
            Delete any object; [id] => ID of the object to delete; [type] => The type of the
            object, must be one of: 'waste' 'income' 'move' 'change' 'object' 'currency' 'tag'
            'accum'; 'object' is waste category, income source or place; If 'id' identifies
            'move' or 'change', both records will be deleted on the server; Returns 1 on
            success; if an error accures - generates SoapFault message; if there is other
            object connected to this ID - delete them first;
        """
        with self.client.settings(raw_response=True, strict=False):
            result = self.client.service.deleteObject(
                self.api_key,
                self.login,
                self.password,
                id=object_id,
                type=object_type,
            )
            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        ret = root.findtext(".//deleteObjectReturn")
        return ret == "1"

    def get_changes(self, *, revision: int) -> List[ChangeRecord]:
        """
        Implements getChangeList API

        Original wsdl description:
            Get all changes (array of arrays) from server relative to given revision: [revision] => the revision of the change, [action_id] => the action of the change '1' - add, '2' - update, '3' - delete'; [object_type_id] => type of the object changed '1' - any record (transction), '2' - income source, '3' - waste category, '4' - place, '5' - currency, '6' - budget_tags, '7' - budget_accum, '8' - budget_accum_order; [object_id] => ID of the object for subsequent calls getRecordList, getCategoryList etc; [date] => the date of the change; Parameter [revision] => int8 number, usually saved on the client from last successfull sync.
        """

        logger.debug(f"Getting changes with the following params: {revision=}")

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getChangeList(
                self.api_key, self.login, self.password, revision=revision
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getChangeListReturn/item")

        return [xmlmap_to_model(item, ChangeRecord, strict=self.strict) for item in items]

    def set_category_list(self, categories: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Implements setCategoryList API — insert or update expense categories in bulk.

        Each category record is a dict with one of the ID keys:

            - ``client_id`` (int): a local ID — *insert* a new category;
              the server echoes this id back alongside the assigned ``server_id``
            - ``server_id`` (int) or ``id`` (int): existing category ID — *update*

        Other fields:

            - ``parent_id`` (int): parent category ID; ``-1`` for root-level categories
            - ``type`` (int): object type; always ``3`` for expense categories
            - ``name`` (str): category name (UTF-8)
            - ``is_hidden`` (bool): **must** be a Python ``bool`` — passing ``0`` or ``"f"``
              causes the server to return error 48 ("not a boolean")
            - ``is_for_duty`` (bool): **must** be a Python ``bool``; required on SET even though
              GET does not return this field
            - ``sort`` (int): sort order within the tree level
            - ``description`` (str, optional): free-text description

        Returns the array of ``{server_id, client_id, status}`` maps that the server sent back
        (same shape as :meth:`set_record_list`).  For inserts, ``client_id`` echoes what you
        passed in; for updates, ``server_id`` echoes what you passed in.

        Original WSDL description:
            Insert or update waste category list; [list] => array of arrays: 'server_id' or
            'client_id' [int8] - server or client ID of the record# If client ID is present - try
            to insert new record, and return server2client correspondence in the result array# If
            server_id is present - try to update existing record, @see getCategoryList description
            for other detail; Returns the array of server IDs, successfully changed; The client
            MUST save server IDs corresponded to client IDs, for subsequent 'update' and 'delete'
            calls;
        """
        if not categories:
            return []

        list_xml = generate_xml_map_array(
            [zeep.helpers.create_xml_soap_map(r) for r in categories]  # type: ignore
        )

        with self.client.settings(raw_response=True, strict=False):
            result = self.client.service.setCategoryList(
                self.api_key,
                self.login,
                self.password,
                list=list_xml,
            )
            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//setCategoryListReturn/item")
        return [xmlmap_to_dict(item) for item in items]

    def get_expense_categories(
        self,
        *,
        id_list: List[int] | None = None,
    ) -> List[ExpenseCategory]:
        """
        Implements getCategoryList API

        Original wsdl description:
            Retrievs waste category list (array of arrays): [id] => Internal category ID; [parent_id] => For tree structure; [budget_family_id] => User family ID (for multiuser mode); [type] => Type of object, 3 - waste category; [name] => Category name given by user; [is_hidden] => is category hidden in user interface; [sort] => User sort of category tree; If parameter [idList] is given, it will be treat as ID list of objects to retrieve# this is used for synchronization;
        """

        logger.debug(f"Getting categories with the following params: {id_list=}")

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getCategoryList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getCategoryListReturn/item")

        return [xmlmap_to_model(item, ExpenseCategory, strict=self.strict) for item in items]

    def get_income_sources(
        self,
        *,
        id_list: List[int] | None = None,
    ) -> List[IncomeSource]:
        """
        Implements getSourceList API

        Original wsdl description:
            Retrievs income source list (array of arrays): [id] => Internal source ID; [parent_id] => For tree structure; [budget_family_id] => User family ID (for multiuser mode); [type] => Type of object, 2 - income source; [name] => Source name given by user; [is_hidden] => is income hidden in user interface; [sort] => User sort of source tree; If parameter [idList] is given, it will be treat as ID list of objects to retrieve# this is used for synchronization;
        """

        logger.debug(f"Getting income sources with the following params: {id_list=}")

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getSourceList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getSourceListReturn/item")

        return [xmlmap_to_model(item, IncomeSource, strict=self.strict) for item in items]

    def get_tags(
        self,
        *,
        id_list: List[int] | None = None,
    ) -> List[Tag]:
        """
        Implements getTagList API

        Original wsdl description:
            Retrievs tag list (array of arrays): [id] => Internal tag ID; [family_id] => User family ID (for multiuser mode); [name] => Tag name given by user; [is_hidden] => is tag hidden in user interface; [is_family] => is tag visible for all family user, or user only; [sort] => User sort of tag list; [parent_id] => For tree view; If parameter [idList] is given, it will be treat as ID list of objects to retrieve# this is used for synchronization;
        """

        logger.debug(f"Getting tags with the following params: {id_list=}")

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getTagList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getTagListReturn/item")

        return [xmlmap_to_model(item, Tag, strict=self.strict) for item in items]

    def get_currencies(
        self,
        *,
        id_list: List[int] | None = None,
    ) -> List[Currency]:
        """
        Implements getCurrencyList API

        Original wsdl description:
            Retrievs currency list (array of arrays) with codes and courses: [id] => Internal currency ID; [name] => Currency name, given by user; [course] => current course from sbrf(dot)ru; [code] => International currency code (for course autoupdating); [family_id] => User family ID (for multiuser mode); [is_default] => is default currency# There should be only one default currency; [is_autoupdate] => autoupdate course once per day, from sbrf(dot)ru; [is_hidden] => is currency hidden in user interface; If parameter [idList] is given, it will be treat as ID list of objects to retrieve# this is used for synchronization;
        """

        logger.debug(f"Getting currencies with the following params: {id_list=}")

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getCurrencyList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getCurrencyListReturn/item")

        return [xmlmap_to_model(item, Currency, strict=self.strict) for item in items]

    def get_accounts(
        self,
        *,
        id_list: List[int] | None = None,
    ) -> List[Account]:
        """
        Implements getPlaceList API

        Original wsdl description:
            Retrievs place list (array of arrays): [id] => Internal place ID; [budget_family_id] => User family ID (for multiuser mode); [type] => Type of object, 4 - places; [name] => Place name given by user; [is_hidden] => is place hidden in user interface; [is_autohide] => debts will auto hide on null balance; [is_for_duty] => Internal place for duty logic, Auto created while user adds "Waste or income duty"; [sort] => User sort of place list; [purse_of_nuid] => Not empty if place is purse of user# The value is internal user ID; [icon_id] => Place icon ID from http://www(dot)drebedengi(dot)ru/img/pl[icon_id](dot)gif; If parameter [idList] is given, it will be treat as ID list of objects to retrieve# this is used for synchronization; There is may be empty response, if user access level is limited;
        """

        logger.debug(f"Getting accounts with the following params: {id_list=}")

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getPlaceList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getPlaceListReturn/item")

        return [xmlmap_to_model(item, Account, strict=self.strict) for item in items]

    def get_check_list(
        self,
        *,
        id_list: List[int] | None = None,
    ) -> List[Check]:
        """
        Implements getCheckList API — retrieve QR-check (receipt) records.

        Only QR-submitted checks are synced via this endpoint.

        Args:
            id_list: Optional list of check IDs to retrieve.  If ``None``, all checks are
                returned (same semantics as other ``get_*`` methods).

        Returns:
            List of :class:`~drebedengi.model.Check` objects.

        Original WSDL description:
            Gets list of checks; Only QR checks is synced; Return array of arrays: [id] =>
            Internal check ID; [ext] => qr-url; [state] => the state of qr check process;
            [qr_sum] => the sum of check from QR; [qr_date] => the date of check from QR; If
            parameter [idList] is given, it will be treat as ID list of objects to retrieve# this
            is used for synchronization;
        """

        logger.debug(f"Getting check list with the following params: {id_list=}")

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        with self.client.settings(raw_response=True, strict=False):
            result = self.client.service.getCheckList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
            )
            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getCheckListReturn/item")

        return [xmlmap_to_model(item, Check, strict=self.strict) for item in items]

    def get_check_to_record_list(
        self,
        *,
        id_list: List[int] | None = None,
    ) -> List[CheckToRecord]:
        """
        Implements getCheckToRecordList API — retrieve links between QR-checks and transaction
        records.

        Args:
            id_list: Optional list of link IDs to retrieve.  If ``None``, all links are returned.

        Returns:
            List of :class:`~drebedengi.model.CheckToRecord` objects, each carrying
            ``check_id`` and ``record_id``.

        Original WSDL description:
            Gets list of check to record link; Only for QR checks; Return array of arrays: [id]
            => Internal link ID; [check_id] => ID of the check; [record_id] => ID of the record;
            If parameter [idList] is given, it will be treat as ID list of objects to retrieve#
            this is used for synchronization;
        """

        logger.debug(f"Getting check-to-record list with the following params: {id_list=}")

        if id_list is not None:
            id_list_xml = generate_xml_array(id_list)
        else:
            id_list_xml = zeep.xsd.SkipValue  # type: ignore

        with self.client.settings(raw_response=True, strict=False):
            result = self.client.service.getCheckToRecordList(
                self.api_key,
                self.login,
                self.password,
                idList=id_list_xml,
            )
            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//getCheckToRecordListReturn/item")

        return [xmlmap_to_model(item, CheckToRecord, strict=self.strict) for item in items]

    def get_current_revision(self) -> int:
        """
        Implements getCurrentRevision API

        Original wsdl description:
            Get current server revision number.
        """

        logger.debug("Getting current server revision")

        client = self.client

        with client.settings(raw_response=True, strict=False):
            result = client.service.getCurrentRevision(
                self.api_key,
                self.login,
                self.password,
            )

            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)

        revision_text = root.findtext(".//getCurrentRevisionReturn")
        if revision_text is None:
            raise ValueError("getCurrentRevisionReturn element missing from server response")
        try:
            return int(revision_text)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"getCurrentRevisionReturn is not an integer: {revision_text!r}"
            ) from exc

    def parse_text_data(
        self,
        texts: List[str],
        *,
        default_place_from_id: str = "0",
        default_cat_id: str = "0",
        default_src_id: str = "0",
        default_place_to_id: str = "0",
    ) -> List[Dict[str, str]]:
        """
        Implements parseTextData API — attempt to parse free-text strings as transaction records
        using the server-side rules configured in the user's account.

        The server applies the user's text-parsing rules (e.g. SMS templates, keyword rules) to
        each string in ``texts`` and returns a list of partially-filled record dicts.  The exact
        set of keys in the returned dicts depends on how well each string matched a rule and is
        not specified further in the WSDL.  The caller must treat the result as advisory data and
        validate / fill in missing fields before calling :meth:`set_record_list`.

        Args:
            texts: List of UTF-8 strings to parse (e.g. raw SMS or push notification text).
                The server treats the list as a 0-based indexed array.
            default_place_from_id: Account ID to use when no rule matches (``"0"`` = no default).
            default_cat_id: Expense category ID to use when no rule matches.
            default_src_id: Income source ID to use when no rule matches.
            default_place_to_id: Destination account ID for transfers when no rule matches.

        Returns:
            List of raw ``{field: value}`` dicts as returned by the server.  Each dict
            corresponds to the input string at the same index.  The server may return an empty
            dict for a string it could not parse.

        Note:
            The exact response field set is undocumented and may vary per user account
            configuration.  If you need a fully-typed result, inspect the raw dicts returned
            here and map them to :class:`~drebedengi.model.Transaction` fields manually.

        Original WSDL description:
            Try to parse text data as records; [def..] default field values if no rules
            detected; [list] => array (indexes must be 0,1,2...N) of strings to parse (UTF8);
            Returns the array of array - data for records;
        """

        logger.debug(f"Parsing text data: {len(texts)} strings")

        list_xml = generate_xml_array(texts)

        with self.client.settings(raw_response=True, strict=False):
            result = self.client.service.parseTextData(
                self.api_key,
                self.login,
                self.password,
                defPlaceFromId=default_place_from_id,
                defCatId=default_cat_id,
                defSrcId=default_src_id,
                defPlaceToId=default_place_to_id,
                list=list_xml,
            )
            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//parseTextDataReturn/item")

        return [xmlmap_to_dict(item) for item in items]

    def parse_push_data(
        self,
        texts: List[str],
    ) -> List[Dict[str, str]]:
        """
        Implements parsePushData API — attempt to parse push notification strings as transaction
        records using the server-side rules configured in the user's account.

        Functionally similar to :meth:`parse_text_data`, but designed specifically for push
        notification payloads (e.g. bank SMS/push text in the format the mobile app receives).
        Unlike :meth:`parse_text_data`, there are no ``def*`` default parameters — the server
        infers defaults from the push content itself.

        Args:
            texts: List of UTF-8 push notification strings to parse.  Indexed 0-based.

        Returns:
            List of raw ``{field: value}`` dicts as returned by the server.  Each dict
            corresponds to the input string at the same index.

        Note:
            The exact response field set is undocumented (same caveat as
            :meth:`parse_text_data`).

        Original WSDL description:
            Try to parse text data as records; [def..] default field values if no rules
            detected; [list] => array (indexes must be 0,1,2...N) of strings to parse (UTF8);
            Returns the array of array - data for records;
        """

        logger.debug(f"Parsing push data: {len(texts)} strings")

        list_xml = generate_xml_array(texts)

        with self.client.settings(raw_response=True, strict=False):
            result = self.client.service.parsePushData(
                self.api_key,
                self.login,
                self.password,
                list=list_xml,
            )
            DrebedengiAPIError.check_and_raise(result)

        root = etree.fromstring(result.content)
        items: List[etree.Element] = root.findall(".//parsePushDataReturn/item")

        return [xmlmap_to_dict(item) for item in items]
