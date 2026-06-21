"""Top-level package for Drebedengi Python API."""
__author__ = """Mike Perlov"""
__email__ = "mishamsk@gmail.com"
__version__ = "0.2.0"

from .api import (
    DrebedengiAPI,
    DrebedengiAPIError,
    DeletableObjectType,
)
from .model import (
    Account,
    ActionType,
    ChangeRecord,
    Check,
    CheckToRecord,
    Currency,
    ExpenseCategory,
    IncomeSource,
    ObjectType,
    ReportFilterType,
    ReportGrouping,
    ReportPeriod,
    Tag,
    Transaction,
    TransactionType,
)
from .utils import (
    check_same_transfer_transactions,
    generate_xml_map_array,
    xmlmap_to_dict,
)

__all__ = [
    # API layer
    "DrebedengiAPI",
    "DrebedengiAPIError",
    "DeletableObjectType",
    # Domain models
    "Account",
    "ActionType",
    "ChangeRecord",
    "Check",
    "CheckToRecord",
    "Currency",
    "ExpenseCategory",
    "IncomeSource",
    "ObjectType",
    "ReportFilterType",
    "ReportGrouping",
    "ReportPeriod",
    "Tag",
    "Transaction",
    "TransactionType",
    # Utility helpers (retained for backwards compatibility with existing consumers)
    "check_same_transfer_transactions",
    "generate_xml_map_array",
    "xmlmap_to_dict",
]
