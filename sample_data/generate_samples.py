#!/usr/bin/env python3
from __future__ import annotations

"""Generate sample Excel workbooks for REMO_OX Analytics demos and tests.

Run from the project root::

    python sample_data/generate_samples.py

All generated files use a fixed random seed (42) for reproducibility.
The script produces six Excel files in the ``sample_data/`` directory:

- ``sales_ar.xlsx``   — Arabic messy sales file (500 rows)
- ``sales_en.xlsx``   — English clean sales file (300 rows)
- ``inventory.xlsx``  — Inventory / stock file (100 SKUs)
- ``receivables.xlsx``— Accounts receivable (150 invoices)
- ``expenses.xlsx``   — Expense breakdown (200 rows)
- ``multi_sheet.xlsx``— Multi-sheet workbook (Sales + Inventory + Expenses)
"""

import random
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).parent
random.seed(42)

# ---------------------------------------------------------------------------
# Realistic data pools
# ---------------------------------------------------------------------------

AR_PRODUCTS: list[tuple[str, str]] = [
    ("تلفزيون سمارت 55 بوصة", "إلكترونيات"),
    ("لابتوب Dell", "إلكترونيات"),
    ("هاتف ذكي Samsung", "إلكترونيات"),
    ("شاشة كمبيوتر 27 بوصة", "إلكترونيات"),
    ("طابعة ليزر", "إلكترونيات"),
    ("راوتر واي فاي", "إلكترونيات"),
    ("سماعات لاسلكية", "إلكترونيات"),
    ("غسالة ملابس اتوماتيك", "أجهزة منزلية"),
    ("ثلاجة نوفروست", "أجهزة منزلية"),
    ("مكيف سبليت 1.5 حصان", "أجهزة منزلية"),
    ("مروحة شوبان", "أجهزة منزلية"),
    ("ميكروويف 30 لتر", "أجهزة منزلية"),
    ("خلاط كهربائي", "أجهزة منزلية"),
    ("كرسي مكتب مريح", "أثاث"),
    ("مكتب خشبي", "أثاث"),
    ("رف كتب", "أثاث"),
    ("كنبة ثلاثية", "أثاث"),
    ("خزانة ملابس 4 أبواب", "أثاث"),
    ("طاولة طعام", "أثاث"),
    ("قميص قطن رجالي", "ملابس"),
    ("بنطلون جينز", "ملابس"),
    ("حذاء جلد رجالي", "ملابس"),
    ("فستان سهرة", "ملابس"),
    ("مشروبات غازية كرتون", "مواد غذائية"),
    ("زيت طعام 5 لتر", "مواد غذائية"),
    ("أرز بسمتي 10 كجم", "مواد غذائية"),
    ("سكر ناعم 5 كجم", "مواد غذائية"),
    ("لوازم مكتبية متنوعة", "مستلزمات مكتب"),
    ("أقلام حبر جاف", "مستلزمات مكتب"),
    ("ورق A4 رزمة", "مستلزمات مكتب"),
]

AR_CUSTOMERS: list[str] = [
    "شركة النيل للتجارة",
    "مجموعة الأهرام التجارية",
    "مؤسسة الفجر للاستيراد",
    "شركة الدلتا للتوريدات",
    "مصنع الصقر",
    "شركة هيلتون للتسويق",
    "مجموعة القاهرة الحديثة",
    "شركة الشرق للحلول التقنية",
    "مؤسسة سيناء التجارية",
    "شركة الوادي للتجارة والتوريد",
    "مجموعة رمسيس التجارية",
    "شركة ميدكو للتوزيع",
    "مؤسسة الإسكندرية للاستيراد",
    "شركة فاروق وشركاه",
    "مجموعة المنار للمقاولات",
    "شركة الأمل للمستلزمات",
    "مؤسسة الخليج العربي",
]

EN_CATEGORIES: list[str] = [
    "Electronics",
    "Furniture",
    "Clothing",
    "Food & Beverage",
    "Office Supplies",
]

EN_PRODUCTS: dict[str, list[str]] = {
    "Electronics": [
        "Smart TV 55\"",
        "Laptop Dell XPS",
        "Samsung Smartphone",
        "27\" Monitor",
        "Laser Printer",
        "Wireless Router",
        "Bluetooth Headphones",
    ],
    "Furniture": [
        "Executive Chair",
        "Wooden Desk",
        "Bookshelf",
        "3-Seat Sofa",
        "Dining Table",
    ],
    "Clothing": [
        "Men's Cotton Shirt",
        "Denim Jeans",
        "Leather Shoes",
        "Evening Dress",
    ],
    "Food & Beverage": [
        "Soft Drinks Carton",
        "Cooking Oil 5L",
        "Basmati Rice 10kg",
    ],
    "Office Supplies": [
        "Assorted Stationery",
        "Ballpoint Pens Set",
        "A4 Paper Ream",
    ],
}

EN_CUSTOMERS: list[str] = [
    "Nile Trading Co.",
    "Cairo Modern Group",
    "Delta Supplies LLC",
    "Sphinx Imports",
    "Eastern Tech Solutions",
    "Sinai Commercial Est.",
    "Ramses Trading Group",
    "Medco Distribution",
    "Alexandria Imports",
    "Farouk & Partners",
    "Manar Contracting",
    "Al-Amal Supplies",
    "Gulf Arab Est.",
    "Horizon Marketing",
    "Delta River Corp.",
]

EXPENSE_CATEGORIES: list[tuple[str, str]] = [
    ("إيجار", "Rent"),
    ("رواتب", "Salaries"),
    ("تسويق", "Marketing"),
    ("كهرباء ومياه", "Utilities"),
    ("صيانة", "Maintenance"),
    ("أخرى", "Other"),
]

EXPENSE_DESCRIPTIONS: dict[str, list[str]] = {
    "إيجار": ["إيجار المقر الرئيسي", "إيجار المستودع", "إيجار فرع الإسكندرية"],
    "رواتب": ["رواتب شهر يناير", "رواتب شهر فبراير", "مكافآت الموظفين", "بدل نقل"],
    "تسويق": ["إعلانات سوشيال ميديا", "مطبوعات دعائية", "رعاية فعاليات", "إعلانات جوجل"],
    "كهرباء ومياه": ["فاتورة الكهرباء", "فاتورة المياه", "فاتورة الغاز"],
    "صيانة": ["صيانة المعدات", "صيانة السيارات", "تصليح التكييف", "صيانة الحاسوب"],
    "أخرى": ["مصاريف متنوعة", "أدوات مكتبية", "ضيافة", "انترنت وخطوط", "تأمين"],
}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

START_DATE = date(2023, 1, 1)
END_DATE = date(2024, 12, 31)
DATE_RANGE_DAYS = (END_DATE - START_DATE).days


def rand_date(start: date = START_DATE, days: int = DATE_RANGE_DAYS) -> date:
    """Return a random :class:`date` within the given range.

    Args:
        start: First day of the range (inclusive).
        days: Number of days to offset from *start*.

    Returns:
        A randomly chosen date.
    """
    return start + timedelta(days=random.randint(0, days))


def rand_date_str_mixed(d: date) -> str:
    """Return a date string in one of three messy formats.

    Formats chosen randomly:

    - ``YYYY-MM-DD``
    - ``DD/MM/YYYY``
    - ``D/M/YY``

    Args:
        d: The date to format.

    Returns:
        Formatted date string.
    """
    fmt = random.choice(["iso", "dmy", "short"])
    if fmt == "iso":
        return d.strftime("%Y-%m-%d")
    if fmt == "dmy":
        return d.strftime("%d/%m/%Y")
    return f"{d.day}/{d.month}/{str(d.year)[2:]}"


_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def to_arabic_digits(n: int | float) -> str:
    """Convert a number to a string using Arabic-Indic digit glyphs.

    Args:
        n: Integer or float to convert.

    Returns:
        String with Arabic-Indic digit characters.
    """
    return str(int(n)).translate(_ARABIC_DIGITS)


def rand_quantity() -> str | int:
    """Return a quantity value, sometimes as Arabic-Indic digits.

    Returns:
        An integer or an Arabic-Indic digit string.
    """
    qty = random.randint(1, 100)
    if random.random() < 0.35:
        return to_arabic_digits(qty)
    return qty


def rand_price_str(price: float) -> str | float:
    """Return a price value, sometimes with a currency prefix.

    Args:
        price: The raw price float.

    Returns:
        The bare float or a prefixed string like ``'LE 1,234.50'``.
    """
    if random.random() < 0.25:
        prefix = random.choice(["LE ", "ج.م "])
        return f"{prefix}{price:,.2f}"
    return price


def _apply_header_style(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    row: int,
    num_cols: int,
    fill_color: str = "1B4F72",
    font_color: str = "FFFFFF",
) -> None:
    """Apply bold, centered, coloured header styling to a worksheet row.

    Args:
        ws: The target worksheet.
        row: 1-based row index of the header.
        num_cols: Number of columns to style.
        fill_color: Hex ARGB background colour (without leading ``#``).
        font_color: Hex ARGB font colour (without leading ``#``).
    """
    fill = PatternFill(fill_type="solid", fgColor=fill_color)
    font = Font(bold=True, color=font_color)
    align = Alignment(horizontal="center", vertical="center")
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = fill
        cell.font = font
        cell.alignment = align


def _set_col_widths(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    widths: list[int],
) -> None:
    """Set column widths in a worksheet.

    Args:
        ws: The target worksheet.
        widths: Sequence of column widths; index 0 → column A.
    """
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width


# ---------------------------------------------------------------------------
# Generator: sales_ar.xlsx
# ---------------------------------------------------------------------------

def generate_sales_ar(path: Path) -> None:
    """Generate the Arabic messy sales workbook (``sales_ar.xlsx``).

    Layout:
    - Rows 1-3: blank (leading blank rows)
    - Row 4: header (styled)
    - Rows 5-504: data rows (~500), including scattered blanks and missing values
    - Rows 505-506: totals rows

    Args:
        path: Absolute path where the ``.xlsx`` file will be saved.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "المبيعات"

    headers = [
        "تاريخ",
        "الصنف",
        "الفئة",
        "العميل",
        "الكمية",
        "سعر الوحدة",
        "إجمالي المبيعات",
    ]

    # Rows 1-3 blank
    for _ in range(3):
        ws.append([])

    # Row 4: header
    ws.append(headers)
    _apply_header_style(ws, 4, len(headers))

    # Build 500 data rows with scattered blanks and missing values
    blank_positions = set(random.sample(range(5, 505), 8))
    missing_positions = set(random.sample(range(5, 505), 4))

    total_qty: int = 0
    total_rev: float = 0.0

    data_row = 5
    inserted = 0
    while inserted < 500:
        if data_row in blank_positions:
            ws.append([])
            data_row += 1
            continue

        if data_row in missing_positions:
            # Row with some missing values
            d = rand_date()
            product_name, category = random.choice(AR_PRODUCTS)
            ws.append([
                rand_date_str_mixed(d),
                product_name,
                category,
                None,   # missing customer
                None,   # missing qty
                None,   # missing price
                None,   # missing revenue
            ])
            data_row += 1
            inserted += 1
            continue

        d = rand_date()
        product_name, category = random.choice(AR_PRODUCTS)
        customer = random.choice(AR_CUSTOMERS)
        qty_raw = random.randint(1, 100)
        unit_price = round(random.uniform(50.0, 15000.0), 2)
        revenue = round(qty_raw * unit_price, 2)

        total_qty += qty_raw
        total_rev += revenue

        qty_cell = rand_quantity()
        price_cell = rand_price_str(unit_price)

        ws.append([
            rand_date_str_mixed(d),
            product_name,
            category,
            customer,
            qty_cell,
            price_cell,
            revenue,
        ])
        data_row += 1
        inserted += 1

    # Totals rows
    totals_fill = PatternFill(fill_type="solid", fgColor="D5E8D4")
    totals_font = Font(bold=True)

    total_row_1 = ["الإجمالي", "", "", "", total_qty, "", total_rev]
    ws.append(total_row_1)
    last_data = ws.max_row
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=last_data, column=col_idx)
        cell.fill = totals_fill
        cell.font = totals_font

    total_row_2 = ["المجموع الكلي", "", "", "", "", "", total_rev]
    ws.append(total_row_2)
    last_row = ws.max_row
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=last_row, column=col_idx)
        cell.fill = totals_fill
        cell.font = totals_font

    _set_col_widths(ws, [16, 28, 18, 28, 12, 16, 20])
    ws.sheet_view.rightToLeft = True

    wb.save(path)


# ---------------------------------------------------------------------------
# Generator: sales_en.xlsx
# ---------------------------------------------------------------------------

def generate_sales_en(path: Path) -> None:
    """Generate the clean English sales workbook (``sales_en.xlsx``).

    Contains 300 rows with standard formatting, no messy data.
    Used as a baseline for automated tests.

    Args:
        path: Absolute path where the ``.xlsx`` file will be saved.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"

    headers = ["Date", "Product", "Category", "Customer", "Quantity", "Unit Price", "Revenue"]
    ws.append(headers)
    _apply_header_style(ws, 1, len(headers))

    for _ in range(300):
        d = rand_date()
        category = random.choice(EN_CATEGORIES)
        product = random.choice(EN_PRODUCTS[category])
        customer = random.choice(EN_CUSTOMERS)
        qty = random.randint(1, 80)
        unit_price = round(random.uniform(10.0, 5000.0), 2)
        revenue = round(qty * unit_price, 2)
        ws.append([d.isoformat(), product, category, customer, qty, unit_price, revenue])

    _set_col_widths(ws, [14, 26, 18, 24, 10, 12, 14])
    wb.save(path)


# ---------------------------------------------------------------------------
# Generator: inventory.xlsx
# ---------------------------------------------------------------------------

def generate_inventory(path: Path) -> None:
    """Generate the inventory workbook (``inventory.xlsx``).

    100 SKUs are generated with:
    - 15 slow-moving items (last movement > 90 days ago).
    - 5 zero-stock items.

    Args:
        path: Absolute path where the ``.xlsx`` file will be saved.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventory"

    headers = ["Product", "Category", "Stock Qty", "Unit Cost", "Last Movement Date"]
    ws.append(headers)
    _apply_header_style(ws, 1, len(headers))

    today = date(2024, 12, 31)

    # Choose slow-mover indices (15) and zero-stock indices (5)
    all_indices = list(range(100))
    slow_indices = set(random.sample(all_indices, 15))
    zero_stock_indices = set(random.sample(list(set(all_indices) - slow_indices), 5))

    for i in range(100):
        product_name, category = random.choice(AR_PRODUCTS + [
            (p, c)
            for c, prods in EN_PRODUCTS.items()
            for p in prods
        ])
        unit_cost = round(random.uniform(20.0, 8000.0), 2)

        if i in zero_stock_indices:
            stock_qty = 0
            days_ago = random.randint(5, 60)
        elif i in slow_indices:
            stock_qty = random.randint(1, 30)
            days_ago = random.randint(91, 365)
        else:
            stock_qty = random.randint(10, 500)
            days_ago = random.randint(0, 89)

        last_movement = today - timedelta(days=days_ago)
        ws.append([product_name, category, stock_qty, unit_cost, last_movement.isoformat()])

    _set_col_widths(ws, [30, 20, 12, 12, 22])
    wb.save(path)


# ---------------------------------------------------------------------------
# Generator: receivables.xlsx
# ---------------------------------------------------------------------------

def generate_receivables(path: Path) -> None:
    """Generate the accounts-receivable workbook (``receivables.xlsx``).

    150 invoice rows spread across aging buckets:
    - Current (not yet due)
    - 1-30 days overdue
    - 31-60 days overdue
    - 61-90 days overdue
    - 90+ days overdue

    10 customers have multiple invoices. Total outstanding ≈ 250,000 EGP.

    Args:
        path: Absolute path where the ``.xlsx`` file will be saved.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Receivables"

    headers = ["Customer", "Invoice Date", "Due Date", "Invoice Amount", "Paid Amount"]
    ws.append(headers)
    _apply_header_style(ws, 1, len(headers))

    # 10 multi-invoice customers, rest get single invoices
    multi_customers = random.sample(AR_CUSTOMERS, 10)
    single_customers = [c for c in AR_CUSTOMERS if c not in multi_customers]

    # Aging bucket distribution for 150 rows
    aging_buckets = (
        ["current"] * 40
        + ["1-30"] * 35
        + ["31-60"] * 30
        + ["61-90"] * 25
        + ["90+"] * 20
    )
    random.shuffle(aging_buckets)

    reference_date = date(2024, 12, 31)

    # Build customer list for 150 rows (multi-invoice customers appear multiple times)
    customer_pool: list[str] = []
    for c in multi_customers:
        count = random.randint(3, 8)
        customer_pool.extend([c] * count)
    while len(customer_pool) < 150:
        customer_pool.append(random.choice(single_customers or AR_CUSTOMERS))
    customer_pool = customer_pool[:150]
    random.shuffle(customer_pool)

    target_outstanding = 250_000.0
    total_generated = 0.0
    rows: list[tuple] = []

    for idx, customer in enumerate(customer_pool):
        bucket = aging_buckets[idx % len(aging_buckets)]
        invoice_amount = round(random.uniform(500.0, 12000.0), 2)
        total_generated += invoice_amount

        # Determine invoice date offset based on bucket
        if bucket == "current":
            days_overdue = -random.randint(1, 29)  # not yet due
            due_date_offset = random.randint(0, 29)
        elif bucket == "1-30":
            days_overdue = random.randint(1, 30)
            due_date_offset = 30
        elif bucket == "31-60":
            days_overdue = random.randint(31, 60)
            due_date_offset = 30
        elif bucket == "61-90":
            days_overdue = random.randint(61, 90)
            due_date_offset = 30
        else:  # 90+
            days_overdue = random.randint(91, 365)
            due_date_offset = 30

        due_date = reference_date - timedelta(days=max(0, days_overdue))
        invoice_date = due_date - timedelta(days=due_date_offset + random.randint(0, 15))

        # Partially paid invoices
        paid_frac = random.choice([0.0, 0.0, 0.0, 0.25, 0.5, 0.75, 1.0])
        paid_amount = round(invoice_amount * paid_frac, 2)

        rows.append((
            customer,
            invoice_date.isoformat(),
            due_date.isoformat(),
            invoice_amount,
            paid_amount,
        ))

    # Scale amounts so total outstanding ≈ 250,000
    total_outstanding = sum(r[3] - r[4] for r in rows)
    if total_outstanding > 0:
        scale = target_outstanding / total_outstanding
        rows = [
            (r[0], r[1], r[2], round(r[3] * scale, 2), round(r[4] * scale, 2))
            for r in rows
        ]

    for row in rows:
        ws.append(list(row))

    _set_col_widths(ws, [28, 14, 14, 16, 16])
    wb.save(path)


# ---------------------------------------------------------------------------
# Generator: expenses.xlsx
# ---------------------------------------------------------------------------

def generate_expenses(path: Path) -> None:
    """Generate the expense-breakdown workbook (``expenses.xlsx``).

    200 rows across Arabic/English expense categories.

    Args:
        path: Absolute path where the ``.xlsx`` file will be saved.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expenses"

    headers = ["Date", "Category", "Description", "Amount"]
    ws.append(headers)
    _apply_header_style(ws, 1, len(headers))

    for _ in range(200):
        d = rand_date()
        ar_cat, _en_cat = random.choice(EXPENSE_CATEGORIES)
        description = random.choice(EXPENSE_DESCRIPTIONS[ar_cat])

        # Vary amounts by category
        if ar_cat == "رواتب":
            amount = round(random.uniform(8000.0, 35000.0), 2)
        elif ar_cat == "إيجار":
            amount = round(random.uniform(5000.0, 20000.0), 2)
        elif ar_cat == "تسويق":
            amount = round(random.uniform(500.0, 8000.0), 2)
        elif ar_cat == "كهرباء ومياه":
            amount = round(random.uniform(200.0, 2000.0), 2)
        elif ar_cat == "صيانة":
            amount = round(random.uniform(300.0, 5000.0), 2)
        else:
            amount = round(random.uniform(100.0, 3000.0), 2)

        ws.append([d.isoformat(), ar_cat, description, amount])

    _set_col_widths(ws, [14, 18, 36, 14])
    wb.save(path)


# ---------------------------------------------------------------------------
# Generator: multi_sheet.xlsx
# ---------------------------------------------------------------------------

def _add_mini_sales(wb: openpyxl.Workbook) -> None:
    """Append a mini Sales sheet (50 rows) to *wb*.

    Args:
        wb: The workbook to modify in place.
    """
    ws = wb.create_sheet("Sales")
    headers = ["Date", "Product", "Category", "Customer", "Quantity", "Unit Price", "Revenue"]
    ws.append(headers)
    _apply_header_style(ws, 1, len(headers))

    for _ in range(50):
        d = rand_date()
        category = random.choice(EN_CATEGORIES)
        product = random.choice(EN_PRODUCTS[category])
        customer = random.choice(EN_CUSTOMERS)
        qty = random.randint(1, 50)
        unit_price = round(random.uniform(10.0, 3000.0), 2)
        revenue = round(qty * unit_price, 2)
        ws.append([d.isoformat(), product, category, customer, qty, unit_price, revenue])

    _set_col_widths(ws, [14, 26, 18, 24, 10, 12, 14])


def _add_mini_inventory(wb: openpyxl.Workbook) -> None:
    """Append a mini Inventory sheet (30 rows) to *wb*.

    Args:
        wb: The workbook to modify in place.
    """
    ws = wb.create_sheet("Inventory")
    headers = ["Product", "Category", "Stock Qty", "Unit Cost", "Last Movement Date"]
    ws.append(headers)
    _apply_header_style(ws, 1, len(headers))

    today = date(2024, 12, 31)
    for _ in range(30):
        product_name, category = random.choice(AR_PRODUCTS)
        stock_qty = random.randint(0, 200)
        unit_cost = round(random.uniform(20.0, 5000.0), 2)
        days_ago = random.randint(0, 200)
        last_movement = today - timedelta(days=days_ago)
        ws.append([product_name, category, stock_qty, unit_cost, last_movement.isoformat()])

    _set_col_widths(ws, [30, 20, 12, 12, 22])


def _add_mini_expenses(wb: openpyxl.Workbook) -> None:
    """Append a mini Expenses sheet (40 rows) to *wb*.

    Args:
        wb: The workbook to modify in place.
    """
    ws = wb.create_sheet("Expenses")
    headers = ["Date", "Category", "Description", "Amount"]
    ws.append(headers)
    _apply_header_style(ws, 1, len(headers))

    for _ in range(40):
        d = rand_date()
        ar_cat, _en_cat = random.choice(EXPENSE_CATEGORIES)
        description = random.choice(EXPENSE_DESCRIPTIONS[ar_cat])
        amount = round(random.uniform(100.0, 15000.0), 2)
        ws.append([d.isoformat(), ar_cat, description, amount])

    _set_col_widths(ws, [14, 18, 36, 14])


def generate_multi_sheet(path: Path) -> None:
    """Generate the multi-sheet demo workbook (``multi_sheet.xlsx``).

    Contains three sheets: Sales (50 rows), Inventory (30 rows),
    Expenses (40 rows). The default blank sheet is removed.

    Args:
        path: Absolute path where the ``.xlsx`` file will be saved.
    """
    wb = openpyxl.Workbook()
    # Remove default blank sheet
    default_sheet = wb.active
    wb.remove(default_sheet)

    _add_mini_sales(wb)
    _add_mini_inventory(wb)
    _add_mini_expenses(wb)

    wb.save(path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_all() -> None:
    """Generate all six sample Excel workbooks.

    Files are written to the ``sample_data/`` directory (the same directory
    as this script). Existing files are silently overwritten.

    Prints a summary line for each file created.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tasks: list[tuple[str, callable]] = [
        ("sales_ar.xlsx", generate_sales_ar),
        ("sales_en.xlsx", generate_sales_en),
        ("inventory.xlsx", generate_inventory),
        ("receivables.xlsx", generate_receivables),
        ("expenses.xlsx", generate_expenses),
        ("multi_sheet.xlsx", generate_multi_sheet),
    ]

    print(f"\n{'=' * 55}")
    print("  REMO_OX Analytics - Sample Data Generator")
    print(f"  Output directory: {OUTPUT_DIR.resolve()}")
    print(f"{'=' * 55}")

    for filename, generator_fn in tasks:
        target = OUTPUT_DIR / filename
        generator_fn(target)
        size_kb = target.stat().st_size / 1024
        print(f"  [OK]  {filename:<25}  ({size_kb:,.1f} KB)")

    print(f"{'=' * 55}")
    print(f"  Done - {len(tasks)} files generated.\n")


if __name__ == "__main__":
    generate_all()
