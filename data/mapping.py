from __future__ import annotations

"""Column role mapping for REMO_OX Analytics.

Maps raw Excel column headers to semantic roles (e.g. ``"quantity"``,
``"revenue"``) using bilingual (Arabic + English) synonym dictionaries and
rapidfuzz fuzzy matching.  Derived roles (computed from other mapped columns)
are detected automatically.

Typical usage::

    result = auto_map_roles(df.columns.tolist())
    df = apply_mapping(df, result)
"""


import pandas as pd
from rapidfuzz import fuzz, process

from analytics.schemas import (
    DatasetMapping,
    MappingResult,
    MappingSuggestion,
)
from core.logging_setup import get_logger
from data.ingest import _normalize_arabic_for_matching

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Confidence thresholds
# ---------------------------------------------------------------------------

_AUTO_ASSIGN_THRESHOLD: float = 80.0   # score ≥ this → auto-confirm
_SUGGEST_THRESHOLD: float = 50.0       # score ≥ this → offer as suggestion

# ---------------------------------------------------------------------------
# Synonym dictionary — bilingual Arabic + English
# ---------------------------------------------------------------------------

ROLE_SYNONYMS: dict[str, list[str]] = {
    "date": [
        "date", "تاريخ", "التاريخ", "تاريخ البيع", "تاريخ الفاتورة",
        "يوم", "الشهر", "السنة", "period", "month", "day", "year",
        "order date", "sale date", "transaction date",
    ],
    "product": [
        "product", "item", "منتج", "المنتج", "صنف", "الصنف", "البضاعة",
        "اسم الصنف", "اسم المنتج", "product name", "item name", "description",
        "الوصف", "بضاعة", "سلعة",
        # Services & Consulting synonyms
        "خدمة", "الخدمة", "اسم الخدمة", "نوع الخدمة", "الاستشارة", "نوع الاستشارة",
        "المهمة", "المشروع", "الباقة", "service", "services", "service name",
        "consultation", "job", "task", "project", "package",
    ],
    "category": [
        "category", "فئة", "الفئة", "تصنيف", "التصنيف", "نوع", "النوع",
        "قسم", "القسم", "group", "type", "class",
        "نوع الخدمة", "قسم الخدمات", "service category", "service type",
    ],
    "customer": [
        "customer", "client", "عميل", "العميل", "زبون", "الزبون",
        "اسم العميل", "customer name", "account", "buyer",
        "متلقي الخدمة", "الجهة المستفيدة", "client name",
    ],
    "quantity": [
        "quantity", "qty", "كمية", "الكمية", "عدد", "العدد",
        "pieces", "units", "وحدات", "الوحدات",
        # Services: hours / sessions / counts
        "ساعات", "الساعات", "ساعات العمل", "عدد الساعات", "الجلسات",
        "عدد الجلسات", "عدد المرات", "hours", "billable hours", "sessions", "times",
    ],
    "unit_price": [
        "unit price", "price", "سعر", "السعر", "سعر الوحدة",
        "unit cost", "price per unit", "سعر البيع", "selling price",
        # Services: rate / fee
        "سعر الخدمة", "أجر الساعة", "أتعاب الخدمة", "hourly rate", "fee", "rate", "service fee",
    ],
    "revenue": [
        "revenue", "sales", "amount", "total", "إيراد", "الإيراد", "إيرادات", "الإيرادات",
        "مبيعات", "المبيعات", "الإجمالي", "إجمالي الإيرادات", "إجمالي المبيعات",
        "اجمالي الايرادات", "اجمالي المبيعات", "قيمة المبيعات", "المبلغ",
        "income", "turnover", "proceeds",
        # Services: fees / service revenue
        "إيراد الخدمات", "ايراد الخدمات", "إيرادات الخدمات", "ايرادات الخدمات",
        "أتعاب", "الأتعاب", "أتعاب الاستشارة", "قيمة الخدمة", "رسوم", "الرسوم",
        "fees", "service revenue", "consulting revenue",
    ],
    "unit_cost": [
        "unit cost", "cost per unit", "تكلفة الوحدة", "تكلفة", "التكلفة",
        "cost price", "purchase price", "cogs", "تكلفة الخدمة",
    ],
    "cost": [
        "cost", "costs", "total cost", "تكلفة", "التكلفة", "إجمالي التكلفة",
        "تكلفة المبيعات", "cogs", "cost of goods sold", "تكلفة تقديم الخدمة",
    ],
    "expense_amount": [
        "expense", "expenses", "مصروف", "المصروف", "مصاريف", "المصاريف",
        "تكاليف", "التكاليف", "spending", "expenditure",
    ],
    "stock_qty": [
        "stock qty", "stock quantity", "stock", "inventory", "مخزون", "المخزون", "رصيد", "الرصيد",
        "qty on hand", "on hand", "balance", "رصيد المخزون", "كمية المخزون",
    ],
    "last_movement_date": [
        "last movement date", "last movement", "last sale", "آخر حركة", "تاريخ آخر حركة",
        "last transaction", "last activity", "آخر بيع",
    ],
    "invoice_amount": [
        "invoice amount", "invoice total", "مبلغ الفاتورة", "قيمة الفاتورة",
        "فاتورة", "الفاتورة", "invoice value",
    ],
    "paid_amount": [
        "paid", "payment", "مدفوع", "المدفوع", "المبلغ المدفوع",
        "amount paid", "paid amount", "collected",
    ],
    "due_date": [
        "due date", "maturity", "تاريخ الاستحقاق", "الاستحقاق",
        "expiry date", "payment due", "موعد السداد",
    ],
    "invoice_date": [
        "invoice date", "تاريخ الفاتورة", "issue date", "تاريخ الإصدار",
    ],
}

# Build a flat lookup: synonym_text → role (for O(1) exact-match fast path)
_SYNONYM_TO_ROLE: dict[str, str] = {}
for _role, _synonyms in ROLE_SYNONYMS.items():
    for _syn in _synonyms:
        # Store both raw and normalised forms
        _SYNONYM_TO_ROLE[_syn.lower()] = _role
        _SYNONYM_TO_ROLE[_normalize_arabic_for_matching(_syn.lower())] = _role

# Flat list of all synonyms for rapidfuzz corpus building
_ALL_SYNONYMS: list[str] = [
    syn for synonyms in ROLE_SYNONYMS.values() for syn in synonyms
]

# Roles whose negatives are suspicious (used in quality checks)
SUSPICIOUS_NEGATIVE_ROLES: frozenset[str] = frozenset(
    ["quantity", "unit_price", "revenue", "stock_qty", "unit_cost", "cost", "invoice_amount"]
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def auto_map_roles(
    columns: list[str],
    dayfirst: bool = False,
) -> MappingResult:
    """Automatically map column names to semantic roles using fuzzy matching.

    Algorithm:

    1. **Exact-match fast path** — check if the normalised column name
       (lower-cased + Arabic variant collapse) is a known synonym.
    2. **Fuzzy fallback** — use :func:`rapidfuzz.fuzz.token_set_ratio` against
       the full synonym corpus.  The best-matching synonym's role is used.
    3. **Auto-assign** if the best score ≥ :data:`_AUTO_ASSIGN_THRESHOLD`.
    4. **Suggest** if the best score ≥ :data:`_SUGGEST_THRESHOLD`.
    5. **Derive** — if ``revenue`` is not directly mapped but both ``quantity``
       and ``unit_price`` are, a derived ``revenue`` column is flagged.

    A role can be assigned to **at most one column** per call.  If two columns
    match the same role, the higher-scoring column wins; the other is marked
    as ``unresolved``.

    Args:
        columns: List of raw column name strings from the DataFrame.
        dayfirst: Reserved for future date-hint integration; currently unused.

    Returns:
        A :class:`~analytics.schemas.MappingResult` with confirmed assignments,
        suggestions, unresolved columns, and derived role flags.
    """
    confirmed: list[DatasetMapping] = []
    suggestions: dict[str, list[MappingSuggestion]] = {}
    unresolved: list[str] = []
    derived: list[DatasetMapping] = []

    # Track which roles have already been assigned to avoid duplicates.
    assigned_roles: dict[str, tuple[str, float]] = {}  # role → (column, score)
    # Track columns that won a role vs those that lost a conflict.
    column_role_map: dict[str, tuple[str, float]] = {}  # column → (role, score)

    for col in columns:
        norm_col = _normalize_arabic_for_matching(col.lower().strip())

        # --- Exact-match fast path ---
        exact_role = _SYNONYM_TO_ROLE.get(norm_col)
        if exact_role is None:
            # also try without spaces
            exact_role = _SYNONYM_TO_ROLE.get(norm_col.replace(" ", "_"))

        if exact_role is not None:
            score = 100.0
        else:
            # --- Fuzzy match ---
            best = _best_fuzzy_match(norm_col)
            if best is None:
                unresolved.append(col)
                continue
            exact_role, score = best

        column_role_map[col] = (exact_role, score)

    # Resolve conflicts: for each role, keep the highest-scoring column.
    # First pass — build role → best column mapping.
    role_to_best: dict[str, tuple[str, float]] = {}
    for col, (role, score) in column_role_map.items():
        if role not in role_to_best or score > role_to_best[role][1]:
            role_to_best[role] = (col, score)

    # Second pass — emit confirmed/suggestions/unresolved.
    for col, (role, score) in column_role_map.items():
        best_col, _best_score = role_to_best[role]

        if col == best_col:
            # This column wins the role.
            if score >= _AUTO_ASSIGN_THRESHOLD:
                confirmed.append(
                    DatasetMapping(column=col, role=role, is_derived=False, derived_from=[])
                )
                assigned_roles[role] = (col, score)
            elif score >= _SUGGEST_THRESHOLD:
                suggestions.setdefault(col, []).append(
                    MappingSuggestion(role=role, confidence=round(score / 100.0, 3), source="fuzzy")
                )
            else:
                unresolved.append(col)
        else:
            # Lost conflict — treat as unresolved or suggestion at lower priority.
            if score >= _SUGGEST_THRESHOLD:
                suggestions.setdefault(col, []).append(
                    MappingSuggestion(role=role, confidence=round(score / 100.0, 3), source="fuzzy")
                )
            else:
                unresolved.append(col)

    # --- Derived field detection ---
    confirmed_roles = {dm.role for dm in confirmed}
    if "revenue" not in confirmed_roles and "quantity" in confirmed_roles and "unit_price" in confirmed_roles:
        qty_col = next(dm.column for dm in confirmed if dm.role == "quantity")
        price_col = next(dm.column for dm in confirmed if dm.role == "unit_price")
        derived.append(
            DatasetMapping(
                column="revenue_derived",
                role="revenue",
                is_derived=True,
                derived_from=[qty_col, price_col],
            )
        )
        logger.info(
            "Derived 'revenue' will be computed from '%s' × '%s'.",
            qty_col,
            price_col,
        )

    return MappingResult(
        confirmed=confirmed,
        suggestions=suggestions,
        unresolved=unresolved,
        derived=derived,
    )


def apply_mapping(df: pd.DataFrame, mapping: MappingResult | dict[str, str]) -> pd.DataFrame:
    """Apply a MappingResult or role->column dict to a DataFrame.

    For each confirmed mapping the column is retained as-is. For each derived
    mapping (or quantity & unit_price in dict mode without revenue), a new
    column is computed and appended.

    Args:
        df: Cleaned source DataFrame.
        mapping: MappingResult or dict[role, column_name].

    Returns:
        A new DataFrame with derived columns appended.
    """
    result = df.copy()

    if isinstance(mapping, dict):
        # Support dict mapping: role -> column_name
        qty_col = mapping.get("quantity")
        price_col = mapping.get("unit_price")
        rev_col = mapping.get("revenue")
        if not rev_col and qty_col and price_col and qty_col in result.columns and price_col in result.columns:
            result["_derived_revenue"] = (
                pd.to_numeric(result[qty_col], errors="coerce")
                * pd.to_numeric(result[price_col], errors="coerce")
            )
        return result

    for derived_mapping in mapping.derived:
        if derived_mapping.role == "revenue" and len(derived_mapping.derived_from) == 2:
            qty_col, price_col = derived_mapping.derived_from
            if qty_col in result.columns and price_col in result.columns:
                try:
                    result[derived_mapping.column] = (
                        pd.to_numeric(result[qty_col], errors="coerce")
                        * pd.to_numeric(result[price_col], errors="coerce")
                    )
                    logger.info(
                        "Computed derived column '%s' = '%s' × '%s'.",
                        derived_mapping.column,
                        qty_col,
                        price_col,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to compute derived column '%s': %s",
                        derived_mapping.column,
                        exc,
                    )
            else:
                missing = [c for c in derived_mapping.derived_from if c not in result.columns]
                logger.warning(
                    "Cannot compute derived column '%s': source columns %s not found.",
                    derived_mapping.column,
                    missing,
                )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _best_fuzzy_match(norm_col: str) -> tuple[str, float] | None:
    """Return the best-matching (role, score) for a normalised column name.

    Uses :func:`rapidfuzz.fuzz.token_set_ratio` against the full synonym
    corpus.  Returns ``None`` if no synonym scores above
    :data:`_SUGGEST_THRESHOLD`.

    Args:
        norm_col: Normalised (lower-cased + Arabic-collapsed) column name.

    Returns:
        A ``(role, score)`` tuple where *score* is in ``[0, 100]``, or
        ``None`` if no match reaches the suggestion threshold.
    """
    # rapidfuzz.process.extractOne returns (match, score, index) or None
    result = process.extractOne(
        norm_col,
        _ALL_SYNONYMS,
        scorer=fuzz.token_set_ratio,
        score_cutoff=_SUGGEST_THRESHOLD,
    )
    if result is None:
        return None

    matched_synonym: str = result[0]
    score: float = result[1]

    # Look up the role for the matched synonym
    norm_syn = _normalize_arabic_for_matching(matched_synonym.lower())
    role = _SYNONYM_TO_ROLE.get(norm_syn) or _SYNONYM_TO_ROLE.get(matched_synonym.lower())
    if role is None:
        return None

    return role, score
