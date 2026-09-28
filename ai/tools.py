from __future__ import annotations

"""Tool declarations and deterministic tool execution layer for REMO_OX Analytics AI Assistant."""

import json
from typing import Any

from analytics.engine import (
    DatasetContext,
    EngineError,
    aggregate,
    compare_periods,
    describe_column,
    get_schema,
    top_n,
)
from analytics.reports import run_report
from analytics.schemas import (
    AggregateInput,
    ComparePeriodInput,
    DescribeColumnInput,
    MetricSpec,
    PeriodSpec,
    RunReportInput,
    SafeFilter,
    ToolResult,
    TopNInput,
)
from core.logging_setup import get_logger

logger = get_logger(__name__)

# Standard function calling schemas compatible with OpenAI & LiteLLM
ANALYTICS_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": "Inspect the workbook schema, sheet names, columns, data types, and confirmed mapped roles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_name": {
                        "type": "string",
                        "description": "Optional specific sheet name to inspect.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate",
            "description": "Aggregate business metrics (sum, mean, median, count, nunique, min, max) grouped by dimensions, with optional date grain (day, week, month, quarter, year) and safe filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_name": {
                        "type": "string",
                        "description": "Sheet name to query.",
                    },
                    "metrics": {
                        "type": "array",
                        "description": "List of metrics to compute.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "agg": {
                                    "type": "string",
                                    "enum": ["sum", "mean", "median", "count", "nunique", "min", "max"],
                                },
                                "alias": {"type": "string"},
                            },
                            "required": ["column", "agg"],
                        },
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Columns to group by. Empty array computes grand totals.",
                    },
                    "date_column": {
                        "type": "string",
                        "description": "Optional date column for time-based bucketing.",
                    },
                    "date_grain": {
                        "type": "string",
                        "enum": ["day", "week", "month", "quarter", "year"],
                    },
                    "sort_by": {"type": "string"},
                    "sort_desc": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["sheet_name", "metrics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "Compare a metric across two time periods (period_a vs period_b) calculating absolute and percentage growth/change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_name": {"type": "string"},
                    "metric": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "agg": {"type": "string", "enum": ["sum", "mean", "count"]},
                            "alias": {"type": "string"},
                        },
                        "required": ["column", "agg"],
                    },
                    "period_a": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                            "end": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                        },
                        "required": ["start", "end"],
                    },
                    "period_b": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                            "end": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                        },
                        "required": ["start", "end"],
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["sheet_name", "metric", "period_a", "period_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_n",
            "description": "Identify top or bottom ranking categories by a metric (e.g. top 10 best-selling products or top 5 clients).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_name": {"type": "string"},
                    "category_column": {"type": "string"},
                    "metric": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "agg": {"type": "string", "enum": ["sum", "mean", "count"]},
                            "alias": {"type": "string"},
                        },
                        "required": ["column", "agg"],
                    },
                    "n": {"type": "integer", "default": 10},
                    "descending": {
                        "type": "boolean",
                        "default": True,
                        "description": "True for Top N, False for Bottom N.",
                    },
                },
                "required": ["sheet_name", "category_column", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_column",
            "description": "Compute statistical summary for a column (count, mean, median, min, max, std, or frequency of top categories).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_name": {"type": "string"},
                    "column": {"type": "string"},
                },
                "required": ["sheet_name", "column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_report",
            "description": "Execute one of the 5 built-in ready-made business intelligence reports: 'sales_overview', 'top_products', 'slow_inventory', 'receivables_aging', 'expense_breakdown'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_id": {
                        "type": "string",
                        "enum": [
                            "sales_overview",
                            "top_products",
                            "slow_inventory",
                            "receivables_aging",
                            "expense_breakdown",
                        ],
                    },
                    "sheet_name": {"type": "string"},
                },
                "required": ["report_id"],
            },
        },
    },
]


class ToolExecutor:
    """Executes validated tool requests deterministically using the analytics engine."""

    def __init__(self, ctx: DatasetContext) -> None:
        self.ctx = ctx

    def execute_tool(
        self,
        name: str,
        raw_arguments: dict[str, Any] | str,
    ) -> tuple[dict[str, Any], ToolResult | None, str]:
        """Dispatch tool name and arguments to pure deterministic analytics methods.

        Returns:
            (tool_output_dict, optional_tool_result, calculation_description)
        """
        try:
            args = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else (raw_arguments or {})
            )
        except json.JSONDecodeError as exc:
            return {"error": f"Invalid JSON arguments: {exc}"}, None, ""

        try:
            match name:
                case "get_schema":
                    schema_res = get_schema(self.ctx)
                    return schema_res.model_dump(), None, "Inspected dataset schema"

                case "aggregate":
                    metrics = [MetricSpec(**m) for m in args.get("metrics", [])]
                    filters = [SafeFilter(**f) for f in args.get("filters", [])]
                    inp = AggregateInput(
                        sheet_name=args.get("sheet_name") or self.ctx.first_sheet_name(),
                        metrics=metrics,
                        group_by=args.get("group_by", []),
                        filters=filters,
                        date_column=args.get("date_column"),
                        date_grain=args.get("date_grain"),
                        sort_by=args.get("sort_by"),
                        sort_desc=args.get("sort_desc", True),
                        limit=min(args.get("limit", 20), 50),
                    )
                    res = aggregate(self.ctx, inp)
                    return res.model_dump(), res, res.calculation_description

                case "compare_periods":
                    metric = MetricSpec(**args["metric"])
                    period_a = PeriodSpec(**args["period_a"])
                    period_b = PeriodSpec(**args["period_b"])
                    filters = [SafeFilter(**f) for f in args.get("filters", [])]
                    inp = ComparePeriodInput(
                        sheet_name=args.get("sheet_name") or self.ctx.first_sheet_name(),
                        metric=metric,
                        period_a=period_a,
                        period_b=period_b,
                        group_by=args.get("group_by", []),
                        filters=filters,
                    )
                    res = compare_periods(self.ctx, inp)
                    return res.model_dump(), res, res.calculation_description

                case "top_n":
                    if "metric" in args and isinstance(args["metric"], dict):
                        metric = MetricSpec(**args["metric"])
                    elif "metric_column" in args:
                        metric = MetricSpec(column=args["metric_column"], agg=args.get("agg", "sum"))
                    else:
                        raise ValueError("Either 'metric' or 'metric_column' must be provided.")
                    filters = [SafeFilter(**f) for f in args.get("filters", [])]
                    inp = TopNInput(
                        sheet_name=args.get("sheet_name") or args.get("sheet") or self.ctx.first_sheet_name(),
                        category_column=args["category_column"],
                        metric=metric,
                        n=min(args.get("n", 10), 50),
                        filters=filters,
                        descending=args.get("descending", True),
                    )
                    res = top_n(self.ctx, inp)
                    return res.model_dump(), res, res.calculation_description

                case "describe_column":
                    inp = DescribeColumnInput(
                        sheet_name=args.get("sheet_name") or self.ctx.first_sheet_name(),
                        column=args["column"],
                    )
                    res = describe_column(self.ctx, inp)
                    return res.model_dump(), res, res.calculation_description

                case "run_report":
                    report_id = args["report_id"]
                    inp = RunReportInput(
                        report_id=report_id,
                        sheet_name=args.get("sheet_name"),
                    )
                    rep_res = run_report(self.ctx, inp)
                    first_table = next(iter(rep_res.tables.values())) if rep_res.tables else None
                    out = {
                        "report_id": rep_res.report_id,
                        "kpis": [k.model_dump() for k in rep_res.kpis],
                        "warnings": rep_res.warnings,
                        "missing_roles": rep_res.missing_roles,
                        "table_preview": first_table.model_dump() if first_table else None,
                    }
                    return out, first_table, rep_res.calculation_description

                case _:
                    return {"error": f"Unknown tool: {name}"}, None, ""

        except (EngineError, ValueError) as exc:
            logger.warning("Tool execution error in %s: %s", name, exc)
            return {"error": str(exc)}, None, ""
        except Exception as exc:
            logger.error("Unexpected tool execution error in %s: %s", name, exc, exc_info=True)
            return {"error": f"Failed to execute {name}: {exc}"}, None, ""
