from __future__ import annotations

"""Ready-made business report builders for REMO_OX Analytics.

All reports are deterministic and computed with pure pandas / analytics engine
functions. No LLM is required for any numbers or calculations.

Available reports:
1. sales_overview: Monthly trend, MoM growth, best/worst month.
2. top_products: Revenue ranking, Pareto 80/20 analysis, gross profit/margin.
3. slow_inventory: Inactive stock detection, capital tied up.
4. receivables_aging: Standard aging buckets (Current, 1-30, 31-60, 61-90, 90+).
5. expense_breakdown: Category share, monthly trend, top drivers.
"""

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from analytics.engine import DatasetContext, EngineError
from analytics.schemas import (
    KPICard,
    MakeChartInput,
    ReportResult,
    RunReportInput,
    ToolResult,
)
from core.logging_setup import get_logger

logger = get_logger(__name__)


def _format_currency(val: float, prefix: str = "", suffix: str = "") -> str:
    """Format numeric value nicely with thousands separators."""
    if pd.isna(val) or val is None:
        return "N/A"
    if abs(val) >= 1_000_000:
        return f"{prefix}{val / 1_000_000:,.2f}M{suffix}".strip()
    if abs(val) >= 1_000:
        return f"{prefix}{val:,.0f}{suffix}".strip()
    return f"{prefix}{val:,.2f}{suffix}".strip()


def _format_pct(val: float | None) -> str:
    """Format float percentage."""
    if val is None or pd.isna(val):
        return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"


# ---------------------------------------------------------------------------
# 1. Sales Overview Report
# ---------------------------------------------------------------------------


def sales_overview(
    ctx: DatasetContext,
    sheet_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> ReportResult:
    """Compute sales overview report with monthly totals, MoM growth, and KPIs.

    Required roles:
        date: Date column
        revenue: Revenue column OR (quantity AND unit_price)
    """
    sheet = sheet_name or ctx.first_sheet_name()
    date_col = ctx.role_column("date")
    rev_col = ctx.role_column("revenue")
    qty_col = ctx.role_column("quantity")
    price_col = ctx.role_column("unit_price")

    missing: list[str] = []
    if not date_col:
        missing.append("date")
    if not rev_col and not (qty_col and price_col):
        missing.append("revenue (or quantity + unit_price)")

    if missing:
        return ReportResult(
            report_id="sales_overview",
            missing_roles=missing,
            calculation_description="Requires date and revenue (or quantity + unit_price).",
            warnings=[f"Missing required roles: {', '.join(missing)}"],
        )

    try:
        df = ctx.get_sheet(sheet).copy()
    except EngineError as e:
        return ReportResult(report_id="sales_overview", error=str(e))

    # Derive revenue if needed
    effective_rev_col = rev_col
    if not effective_rev_col and qty_col and price_col:
        effective_rev_col = "_derived_revenue"
        df[effective_rev_col] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0) * pd.to_numeric(
            df[price_col], errors="coerce"
        ).fillna(0)

    # Convert date column
    df["_date_parsed"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=ctx.dayfirst)
    df = df.dropna(subset=["_date_parsed"]).copy()
    if df.empty:
        return ReportResult(
            report_id="sales_overview",
            warnings=["No valid dates found in date column."],
            calculation_description="Date parsing returned 0 valid rows.",
        )

    df["_month"] = df["_date_parsed"].dt.to_period("M").astype(str)
    df["_revenue_num"] = pd.to_numeric(df[effective_rev_col], errors="coerce").fillna(0)

    # Aggregate by month
    monthly = (
        df.groupby("_month", as_index=False)
        .agg(
            revenue=("_revenue_num", "sum"),
            orders=("_revenue_num", "count"),
            avg_order=("_revenue_num", "mean"),
        )
        .sort_values("_month")
        .reset_index(drop=True)
    )

    monthly["mom_change"] = monthly["revenue"].diff()
    monthly["mom_pct"] = (monthly["revenue"].pct_change() * 100).round(2)

    total_revenue = float(monthly["revenue"].sum())
    total_orders = int(monthly["orders"].sum())
    avg_monthly_rev = float(monthly["revenue"].mean()) if not monthly.empty else 0.0

    best_row = monthly.loc[monthly["revenue"].idxmax()] if not monthly.empty else None
    _worst_row = monthly.loc[monthly["revenue"].idxmin()] if not monthly.empty else None

    # Latest MoM delta
    latest_mom: float | None = None
    if len(monthly) >= 2:
        val = monthly["mom_pct"].iloc[-1]
        if not pd.isna(val):
            latest_mom = float(val)

    kpis = [
        KPICard(
            label="Total Revenue",
            value=_format_currency(total_revenue),
            delta=_format_pct(latest_mom) if latest_mom is not None else None,
            delta_positive=latest_mom >= 0 if latest_mom is not None else None,
        ),
        KPICard(
            label="Avg Monthly Revenue",
            value=_format_currency(avg_monthly_rev),
        ),
        KPICard(
            label="Total Transactions",
            value=f"{total_orders:,}",
        ),
        KPICard(
            label="Best Month",
            value=f"{best_row['_month']} ({_format_currency(float(best_row['revenue']))})"
            if best_row is not None
            else "N/A",
            delta="Peak performance",
            delta_positive=True,
        ),
    ]

    records = []
    for _, r in monthly.iterrows():
        records.append(
            {
                "month": str(r["_month"]),
                "revenue": round(float(r["revenue"]), 2),
                "orders": int(r["orders"]),
                "avg_order": round(float(r["avg_order"]), 2),
                "mom_pct": float(r["mom_pct"]) if not pd.isna(r["mom_pct"]) else None,
            }
        )

    table_result = ToolResult(
        data=records,
        columns=["month", "revenue", "orders", "avg_order", "mom_pct"],
        row_count_total=len(records),
        truncated=len(records) > 50,
        calculation_description="Monthly revenue grouped by calendar month with MoM percentage change.",
    )

    chart = MakeChartInput(
        chart_type="line",
        x_column="month",
        y_column="revenue",
        title="Monthly Revenue Trend",
        x_label="Month",
        y_label="Revenue",
    )

    return ReportResult(
        report_id="sales_overview",
        kpis=kpis,
        tables={"monthly_sales": table_result},
        charts=[chart],
        calculation_description=(
            f"Aggregated column '{effective_rev_col}' grouped by month from '{date_col}'. "
            "MoM growth computed as (revenue_t - revenue_{t-1}) / revenue_{t-1} * 100."
        ),
    )


# ---------------------------------------------------------------------------
# 2. Top Products Report
# ---------------------------------------------------------------------------


def top_products(
    ctx: DatasetContext,
    sheet_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> ReportResult:
    """Compute Top Products report with Pareto (80/20) and margin analysis.

    Required roles:
        product: Product name/SKU
        revenue: Revenue OR (quantity AND unit_price)
    Optional roles:
        quantity, cost, unit_cost
    """
    sheet = sheet_name or ctx.first_sheet_name()
    prod_col = ctx.role_column("product")
    rev_col = ctx.role_column("revenue")
    qty_col = ctx.role_column("quantity")
    price_col = ctx.role_column("unit_price")
    cost_col = ctx.role_column("cost")
    unit_cost_col = ctx.role_column("unit_cost")

    missing: list[str] = []
    if not prod_col:
        missing.append("product")
    if not rev_col and not (qty_col and price_col):
        missing.append("revenue (or quantity + unit_price)")

    if missing:
        return ReportResult(
            report_id="top_products",
            missing_roles=missing,
            calculation_description="Requires product and revenue (or quantity + unit_price).",
            warnings=[f"Missing required roles: {', '.join(missing)}"],
        )

    try:
        df = ctx.get_sheet(sheet).copy()
    except EngineError as e:
        return ReportResult(report_id="top_products", error=str(e))

    effective_rev = rev_col
    if not effective_rev and qty_col and price_col:
        effective_rev = "_derived_revenue"
        df[effective_rev] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0) * pd.to_numeric(
            df[price_col], errors="coerce"
        ).fillna(0)

    df["_revenue_num"] = pd.to_numeric(df[effective_rev], errors="coerce").fillna(0)

    # Cost calculation if available
    has_cost = False
    if cost_col:
        df["_cost_num"] = pd.to_numeric(df[cost_col], errors="coerce").fillna(0)
        has_cost = True
    elif unit_cost_col and qty_col:
        df["_cost_num"] = pd.to_numeric(df[unit_cost_col], errors="coerce").fillna(0) * pd.to_numeric(
            df[qty_col], errors="coerce"
        ).fillna(0)
        has_cost = True

    agg_dict: dict[str, Any] = {"_revenue_num": "sum"}
    if qty_col:
        df["_qty_num"] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
        agg_dict["_qty_num"] = "sum"
    if has_cost:
        agg_dict["_cost_num"] = "sum"

    grouped = (
        df.groupby(prod_col, as_index=False)
        .agg(agg_dict)
        .sort_values("_revenue_num", ascending=False)
        .reset_index(drop=True)
    )

    total_revenue = float(grouped["_revenue_num"].sum())
    total_skus = len(grouped)

    if total_revenue > 0:
        grouped["share_of_total"] = (grouped["_revenue_num"] / total_revenue * 100).round(2)
        grouped["cumulative_share"] = grouped["share_of_total"].cumsum().round(2)
    else:
        grouped["share_of_total"] = 0.0
        grouped["cumulative_share"] = 0.0

    # Pareto: products generating first 80%
    pareto_mask = grouped["cumulative_share"] <= 80.0
    pareto_count = int(pareto_mask.sum())
    if pareto_count == 0 and len(grouped) > 0:
        pareto_count = 1
    pareto_pct = round((pareto_count / total_skus * 100), 1) if total_skus > 0 else 0.0

    top_item = grouped.iloc[0] if not grouped.empty else None

    # Profit & margin if cost available
    total_profit: float | None = None
    overall_margin: float | None = None
    if has_cost:
        grouped["profit"] = (grouped["_revenue_num"] - grouped["_cost_num"]).round(2)
        grouped["margin_pct"] = np.where(
            grouped["_revenue_num"] > 0,
            ((grouped["profit"] / grouped["_revenue_num"]) * 100).round(2),
            0.0,
        )
        total_cost = float(grouped["_cost_num"].sum())
        total_profit = total_revenue - total_cost
        overall_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0.0

    kpis = [
        KPICard(label="Total SKUs", value=f"{total_skus:,}"),
        KPICard(
            label="Top Product",
            value=str(top_item[prod_col]) if top_item is not None else "N/A",
            delta=f"{top_item['share_of_total']:.1f}% of revenue" if top_item is not None else None,
            delta_positive=True,
        ),
        KPICard(
            label="Pareto 80/20 Driver",
            value=f"{pareto_count} SKUs ({pareto_pct}%)",
            delta="Generate 80% of sales",
            delta_positive=True,
        ),
    ]

    if has_cost and total_profit is not None and overall_margin is not None:
        kpis.append(
            KPICard(
                label="Overall Gross Margin",
                value=f"{overall_margin:.1f}%",
                delta=_format_currency(total_profit, suffix=" Profit"),
                delta_positive=overall_margin >= 20.0,
            )
        )
    else:
        kpis.append(
            KPICard(
                label="Total Revenue",
                value=_format_currency(total_revenue),
            )
        )

    # Top 20 table
    top20 = grouped.head(20).copy()
    records = []
    cols = ["product", "revenue", "share_pct", "cumulative_share"]
    if qty_col:
        cols.insert(2, "quantity")
    if has_cost:
        cols.extend(["profit", "margin_pct"])

    for _, r in top20.iterrows():
        item: dict[str, Any] = {
            "product": str(r[prod_col]),
            "revenue": round(float(r["_revenue_num"]), 2),
            "share_pct": float(r["share_of_total"]),
            "cumulative_share": float(r["cumulative_share"]),
        }
        if qty_col:
            item["quantity"] = round(float(r["_qty_num"]), 2)
        if has_cost:
            item["profit"] = float(r["profit"])
            item["margin_pct"] = float(r["margin_pct"])
        records.append(item)

    table_result = ToolResult(
        data=records,
        columns=cols,
        row_count_total=len(grouped),
        truncated=len(grouped) > 20,
        calculation_description=(
            f"Products ranked by revenue from '{effective_rev}'. "
            "Cumulative share identifies products making up 80% of total revenue."
        ),
    )

    chart = MakeChartInput(
        chart_type="hbar",
        x_column="product",
        y_column="revenue",
        title="Top 10 Products by Revenue",
        x_label="Product",
        y_label="Revenue",
    )

    return ReportResult(
        report_id="top_products",
        kpis=kpis,
        tables={"top_products": table_result},
        charts=[chart],
        calculation_description=(
            f"Ranked {total_skus} products by revenue. "
            f"Pareto analysis showed {pareto_count} products ({pareto_pct}%) account for 80% of revenue."
        ),
    )


# ---------------------------------------------------------------------------
# 3. Slow-Moving Inventory Report
# ---------------------------------------------------------------------------


def slow_inventory(
    ctx: DatasetContext,
    sheet_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> ReportResult:
    """Identify inventory with no movement beyond the threshold.

    Required roles:
        product: SKU / product name
        stock_qty: On-hand quantity
    Optional roles:
        last_movement_date: Date of last outbound activity
        unit_cost: Cost per unit to estimate tied-up capital
    """
    sheet = sheet_name or ctx.first_sheet_name()
    prod_col = ctx.role_column("product")
    stock_col = ctx.role_column("stock_qty")
    date_col = ctx.role_column("last_movement_date") or ctx.role_column("date")
    unit_cost_col = ctx.role_column("unit_cost") or ctx.role_column("cost")

    missing: list[str] = []
    if not prod_col:
        missing.append("product")
    if not stock_col:
        missing.append("stock_qty")

    if missing:
        return ReportResult(
            report_id="slow_inventory",
            missing_roles=missing,
            calculation_description="Requires product and stock_qty columns.",
            warnings=[f"Missing required roles: {', '.join(missing)}"],
        )

    try:
        df = ctx.get_sheet(sheet).copy()
    except EngineError as e:
        return ReportResult(report_id="slow_inventory", error=str(e))

    threshold_days: int = int((params or {}).get("slow_days_threshold", 90))

    df["_stock_num"] = pd.to_numeric(df[stock_col], errors="coerce").fillna(0)
    has_cost = bool(unit_cost_col)
    if has_cost:
        df["_unit_cost_num"] = pd.to_numeric(df[unit_cost_col], errors="coerce").fillna(0)
        df["_tied_up_capital"] = df["_stock_num"] * df["_unit_cost_num"]
    else:
        df["_tied_up_capital"] = 0.0

    total_skus = len(df)
    _total_stock_units = float(df["_stock_num"].sum())

    # Movement date analysis
    has_date = bool(date_col)
    if has_date:
        df["_date_parsed"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=ctx.dayfirst)
        # Use latest date in dataset or current time as reference
        max_date = df["_date_parsed"].max()
        ref_date = max_date if pd.notna(max_date) else pd.Timestamp(date.today())
        df["days_inactive"] = (ref_date - df["_date_parsed"]).dt.days.fillna(999).astype(int)
        slow_df = df[(df["days_inactive"] >= threshold_days) & (df["_stock_num"] > 0)].copy()
    else:
        # Fallback if no date: items with zero movement / highest stock
        slow_df = df[df["_stock_num"] > 0].copy()
        slow_df["days_inactive"] = threshold_days

    sort_col = "_tied_up_capital" if has_cost else "_stock_num"
    slow_df = slow_df.sort_values(sort_col, ascending=False).reset_index(drop=True)

    slow_count = len(slow_df)
    slow_units = float(slow_df["_stock_num"].sum())
    tied_up_value = float(slow_df["_tied_up_capital"].sum()) if has_cost else None
    pct_slow = (slow_count / total_skus * 100) if total_skus > 0 else 0.0

    kpis = [
        KPICard(label="Total SKUs", value=f"{total_skus:,}"),
        KPICard(
            label=f"Slow Items (>{threshold_days}d)",
            value=f"{slow_count:,}",
            delta=f"{pct_slow:.1f}% of catalog",
            delta_positive=slow_count == 0,
        ),
        KPICard(
            label="Slow Stock Units",
            value=f"{slow_units:,.0f}",
        ),
    ]

    if tied_up_value is not None:
        kpis.append(
            KPICard(
                label="Tied-Up Capital",
                value=_format_currency(tied_up_value),
                delta="Capital locked in slow stock",
                delta_positive=False,
            )
        )
    else:
        kpis.append(
            KPICard(
                label="Inactive Stock Ratio",
                value=f"{pct_slow:.1f}%",
                delta=f"Threshold: {threshold_days} days",
            )
        )

    # Top slow items table
    records = []
    top_slow = slow_df.head(20)
    cols = ["product", "stock_qty"]
    if has_date:
        cols.append("days_inactive")
    if has_cost:
        cols.extend(["unit_cost", "tied_up_capital"])

    for _, r in top_slow.iterrows():
        rec: dict[str, Any] = {
            "product": str(r[prod_col]),
            "stock_qty": round(float(r["_stock_num"]), 2),
        }
        if has_date:
            rec["days_inactive"] = int(r["days_inactive"])
        if has_cost:
            rec["unit_cost"] = round(float(r["_unit_cost_num"]), 2)
            rec["tied_up_capital"] = round(float(r["_tied_up_capital"]), 2)
        records.append(rec)

    table_result = ToolResult(
        data=records,
        columns=cols,
        row_count_total=len(slow_df),
        truncated=len(slow_df) > 20,
        calculation_description=(
            f"Filtered stock > 0 and inactivity >= {threshold_days} days. "
            f"Sorted by {'tied-up capital' if has_cost else 'stock quantity'} descending."
        ),
    )

    chart = MakeChartInput(
        chart_type="hbar",
        x_column="product",
        y_column="tied_up_capital" if has_cost else "stock_qty",
        title=f"Top Slow-Moving Items (>{threshold_days} Days Inactive)",
        x_label="Product",
        y_label="Tied-Up Capital" if has_cost else "Units on Hand",
    )

    return ReportResult(
        report_id="slow_inventory",
        kpis=kpis,
        tables={"slow_items": table_result},
        charts=[chart],
        calculation_description=(
            f"Detected {slow_count} slow-moving items with inactivity >= {threshold_days} days. "
            + (f"Total capital tied up: {_format_currency(tied_up_value)}." if tied_up_value else "")
        ),
    )


# ---------------------------------------------------------------------------
# 4. Receivables Aging Report
# ---------------------------------------------------------------------------


def receivables_aging(
    ctx: DatasetContext,
    sheet_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> ReportResult:
    """Standard accounts receivable aging report (Current, 1-30, 31-60, 61-90, 90+).

    Required roles:
        customer: Customer / client name
        invoice_amount: Invoice total amount
        due_date: Payment due date
    Optional roles:
        paid_amount: Collected / paid amount so far
    """
    sheet = sheet_name or ctx.first_sheet_name()
    cust_col = ctx.role_column("customer")
    inv_col = ctx.role_column("invoice_amount")
    due_col = ctx.role_column("due_date")
    paid_col = ctx.role_column("paid_amount")

    missing: list[str] = []
    if not cust_col:
        missing.append("customer")
    if not inv_col:
        missing.append("invoice_amount")
    if not due_col:
        missing.append("due_date")

    if missing:
        return ReportResult(
            report_id="receivables_aging",
            missing_roles=missing,
            calculation_description="Requires customer, invoice_amount, and due_date.",
            warnings=[f"Missing required roles: {', '.join(missing)}"],
        )

    try:
        df = ctx.get_sheet(sheet).copy()
    except EngineError as e:
        return ReportResult(report_id="receivables_aging", error=str(e))

    df["_inv_amount"] = pd.to_numeric(df[inv_col], errors="coerce").fillna(0)
    if paid_col:
        df["_paid_amount"] = pd.to_numeric(df[paid_col], errors="coerce").fillna(0)
    else:
        df["_paid_amount"] = 0.0

    df["outstanding"] = (df["_inv_amount"] - df["_paid_amount"]).round(2)
    # Focus on invoices with positive outstanding balance
    active_df = df[df["outstanding"] > 0].copy()

    active_df["_due_parsed"] = pd.to_datetime(active_df[due_col], errors="coerce", dayfirst=ctx.dayfirst)
    valid_dates = active_df.dropna(subset=["_due_parsed"])

    if valid_dates.empty:
        return ReportResult(
            report_id="receivables_aging",
            warnings=["No valid dates found in due_date column."],
            calculation_description="Due date parsing produced 0 valid rows.",
        )

    max_due = valid_dates["_due_parsed"].max()
    ref_date = max_due if pd.notna(max_due) else pd.Timestamp(date.today())

    active_df["days_overdue"] = (ref_date - active_df["_due_parsed"]).dt.days.fillna(0).astype(int)

    def _assign_bucket(days: int) -> str:
        if days <= 0:
            return "Current (Not Due)"
        if days <= 30:
            return "1-30 Days"
        if days <= 60:
            return "31-60 Days"
        if days <= 90:
            return "61-90 Days"
        return "90+ Days"

    active_df["bucket"] = active_df["days_overdue"].apply(_assign_bucket)

    bucket_order = ["Current (Not Due)", "1-30 Days", "31-60 Days", "61-90 Days", "90+ Days"]

    total_outstanding = float(active_df["outstanding"].sum())
    overdue_df = active_df[active_df["days_overdue"] > 0]
    total_overdue = float(overdue_df["outstanding"].sum())
    pct_overdue = (total_overdue / total_outstanding * 100) if total_outstanding > 0 else 0.0

    # Bucket summary
    bucket_summary = (
        active_df.groupby("bucket", as_index=False)
        .agg(
            invoices=("outstanding", "count"),
            amount=("outstanding", "sum"),
        )
    )
    bucket_summary["amount"] = bucket_summary["amount"].round(2)
    bucket_summary["share_pct"] = (
        (bucket_summary["amount"] / total_outstanding * 100).round(2) if total_outstanding > 0 else 0.0
    )

    # Sort bucket summary to standard order
    bucket_summary["_order"] = bucket_summary["bucket"].map(lambda b: bucket_order.index(b) if b in bucket_order else 99)
    bucket_summary = bucket_summary.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)

    # Top overdue customers
    cust_overdue = (
        overdue_df.groupby(cust_col, as_index=False)
        .agg(
            total_overdue=("outstanding", "sum"),
            invoices=("outstanding", "count"),
            max_days_overdue=("days_overdue", "max"),
        )
        .sort_values("total_overdue", ascending=False)
        .head(10)
        .reset_index(drop=True)
    )

    kpis = [
        KPICard(
            label="Total Receivables",
            value=_format_currency(total_outstanding),
        ),
        KPICard(
            label="Total Overdue",
            value=_format_currency(total_overdue),
            delta=f"{pct_overdue:.1f}% overdue",
            delta_positive=pct_overdue < 20.0,
        ),
        KPICard(
            label="Overdue Invoices",
            value=f"{len(overdue_df):,} of {len(active_df):,}",
        ),
        KPICard(
            label="Oldest Overdue",
            value=f"{active_df['days_overdue'].max()} days" if not active_df.empty else "0 days",
            delta="Maximum aging",
            delta_positive=False,
        ),
    ]

    bucket_records = bucket_summary.to_dict(orient="records")
    cust_records = [
        {
            "customer": str(r[cust_col]),
            "total_overdue": round(float(r["total_overdue"]), 2),
            "invoices": int(r["invoices"]),
            "max_days_overdue": int(r["max_days_overdue"]),
        }
        for _, r in cust_overdue.iterrows()
    ]

    t_buckets = ToolResult(
        data=bucket_records,
        columns=["bucket", "invoices", "amount", "share_pct"],
        row_count_total=len(bucket_records),
        truncated=False,
        calculation_description="Invoices categorized into aging buckets based on difference between reference date and due date.",
    )

    t_cust = ToolResult(
        data=cust_records,
        columns=["customer", "total_overdue", "invoices", "max_days_overdue"],
        row_count_total=len(cust_overdue),
        truncated=False,
        calculation_description="Top 10 customers with the highest overdue balances.",
    )

    chart = MakeChartInput(
        chart_type="bar",
        x_column="bucket",
        y_column="amount",
        title="Receivables by Aging Bucket",
        x_label="Aging Bucket",
        y_label="Outstanding Balance",
    )

    return ReportResult(
        report_id="receivables_aging",
        kpis=kpis,
        tables={"aging_summary": t_buckets, "top_overdue_customers": t_cust},
        charts=[chart],
        calculation_description=(
            f"Outstanding calculated as invoice_amount minus paid_amount. "
            f"Aging computed relative to reference date {ref_date.strftime('%Y-%m-%d')}. "
            f"Total receivables: {_format_currency(total_outstanding)}, with {pct_overdue:.1f}% overdue."
        ),
    )


# ---------------------------------------------------------------------------
# 5. Expense Breakdown Report
# ---------------------------------------------------------------------------


def expense_breakdown(
    ctx: DatasetContext,
    sheet_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> ReportResult:
    """Analyze expense breakdown by category and monthly trend.

    Required roles:
        category: Expense category
        expense_amount: Expense amount / cost
    Optional roles:
        date: Expense date
    """
    sheet = sheet_name or ctx.first_sheet_name()
    cat_col = ctx.role_column("category")
    amt_col = ctx.role_column("expense_amount") or ctx.role_column("cost")
    date_col = ctx.role_column("date")

    missing: list[str] = []
    if not cat_col:
        missing.append("category")
    if not amt_col:
        missing.append("expense_amount (or cost)")

    if missing:
        return ReportResult(
            report_id="expense_breakdown",
            missing_roles=missing,
            calculation_description="Requires category and expense_amount (or cost).",
            warnings=[f"Missing required roles: {', '.join(missing)}"],
        )

    try:
        df = ctx.get_sheet(sheet).copy()
    except EngineError as e:
        return ReportResult(report_id="expense_breakdown", error=str(e))

    df["_amt_num"] = pd.to_numeric(df[amt_col], errors="coerce").fillna(0)

    total_expenses = float(df["_amt_num"].sum())
    total_txns = len(df)

    by_cat = (
        df.groupby(cat_col, as_index=False)
        .agg(
            total_amount=("_amt_num", "sum"),
            count=("_amt_num", "count"),
            avg_amount=("_amt_num", "mean"),
        )
        .sort_values("total_amount", ascending=False)
        .reset_index(drop=True)
    )

    by_cat["share_pct"] = (
        (by_cat["total_amount"] / total_expenses * 100).round(2) if total_expenses > 0 else 0.0
    )

    top_cat = by_cat.iloc[0] if not by_cat.empty else None

    kpis = [
        KPICard(
            label="Total Expenses",
            value=_format_currency(total_expenses),
        ),
        KPICard(
            label="Categories Count",
            value=f"{len(by_cat):,}",
        ),
        KPICard(
            label="Top Spending Driver",
            value=str(top_cat[cat_col]) if top_cat is not None else "N/A",
            delta=f"{top_cat['share_pct']:.1f}% of total" if top_cat is not None else None,
            delta_positive=False,
        ),
        KPICard(
            label="Avg per Entry",
            value=_format_currency(total_expenses / total_txns if total_txns > 0 else 0),
        ),
    ]

    records = [
        {
            "category": str(r[cat_col]),
            "total_amount": round(float(r["total_amount"]), 2),
            "share_pct": float(r["share_pct"]),
            "count": int(r["count"]),
            "avg_amount": round(float(r["avg_amount"]), 2),
        }
        for _, r in by_cat.iterrows()
    ]

    tables: dict[str, ToolResult] = {
        "expenses_by_category": ToolResult(
            data=records,
            columns=["category", "total_amount", "share_pct", "count", "avg_amount"],
            row_count_total=len(by_cat),
            truncated=len(by_cat) > 50,
            calculation_description=f"Grouped expense amounts from column '{amt_col}' by category.",
        )
    }

    # Monthly breakdown if date is available
    if date_col:
        df["_date_parsed"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=ctx.dayfirst)
        dated = df.dropna(subset=["_date_parsed"]).copy()
        if not dated.empty:
            dated["_month"] = dated["_date_parsed"].dt.to_period("M").astype(str)
            monthly_exp = (
                dated.groupby("_month", as_index=False)
                .agg(
                    total_amount=("_amt_num", "sum"),
                    count=("_amt_num", "count"),
                )
                .sort_values("_month")
                .reset_index(drop=True)
            )
            tables["monthly_expenses"] = ToolResult(
                data=[
                    {
                        "month": str(r["_month"]),
                        "total_amount": round(float(r["total_amount"]), 2),
                        "count": int(r["count"]),
                    }
                    for _, r in monthly_exp.iterrows()
                ],
                columns=["month", "total_amount", "count"],
                row_count_total=len(monthly_exp),
                truncated=len(monthly_exp) > 50,
                calculation_description="Monthly expense trend over time.",
            )

    chart = MakeChartInput(
        chart_type="pie",
        x_column="category",
        y_column="total_amount",
        title="Expense Share by Category",
        x_label="Category",
        y_label="Amount",
    )

    return ReportResult(
        report_id="expense_breakdown",
        kpis=kpis,
        tables=tables,
        charts=[chart],
        calculation_description=(
            f"Aggregated expenses from '{amt_col}' across {len(by_cat)} categories. "
            f"Largest category '{top_cat[cat_col] if top_cat is not None else ''}' "
            f"accounts for {top_cat['share_pct'] if top_cat is not None else 0}% of spending."
        ),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_REPORT_REGISTRY = {
    "sales_overview": sales_overview,
    "top_products": top_products,
    "slow_inventory": slow_inventory,
    "receivables_aging": receivables_aging,
    "expense_breakdown": expense_breakdown,
}


def run_report(ctx: DatasetContext, inp: RunReportInput) -> ReportResult:
    """Execute a report by its ID using the active dataset context.

    Args:
        ctx: Active DatasetContext bound to user's dataset.
        inp: Input describing which report to run and parameter overrides.

    Returns:
        ReportResult with computed KPIs, tables, and chart specs.
    """
    fn = _REPORT_REGISTRY.get(inp.report_id)
    if fn is None:
        return ReportResult(
            report_id=inp.report_id,
            error=f"Unknown report_id: {inp.report_id!r}. Supported reports: {list(_REPORT_REGISTRY.keys())}",
        )
    return fn(ctx, sheet_name=inp.sheet_name, params=inp.params)
