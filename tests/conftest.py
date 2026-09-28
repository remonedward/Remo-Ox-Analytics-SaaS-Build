from __future__ import annotations

"""Pytest fixtures for REMO_OX Analytics test suite."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pandas as pd
import pytest

from analytics.engine import DatasetContext
from analytics.schemas import QualitySummary
from core.config import Settings
from storage.local_backend import LocalBackend

SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"


@pytest.fixture(autouse=True)
def clean_session_state() -> Generator[None, None, None]:
    """Ensure clean isolated Streamlit session state for every test."""
    try:
        import streamlit as st
        st.session_state.clear()
    except Exception:
        pass
    yield
    try:
        import streamlit as st
        st.session_state.clear()
    except Exception:
        pass


@pytest.fixture
def temp_backend() -> Generator[LocalBackend, None, None]:
    """Provide an isolated LocalBackend in a temporary directory."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        backend = LocalBackend(data_dir=tmpdir)
        yield backend
        backend.close()


@pytest.fixture
def test_settings() -> Settings:
    """Settings instance configured for tests."""
    return Settings(
        llm_model="openai/gpt-4o-mini",
        llm_api_key="sk-test-key-not-real",
        admin_emails="admin@example.com",
        max_upload_mb=10,
        max_rows=10_000,
        max_columns=50,
        retention_days=30,
        send_sample_rows_to_llm=False,
    )


@pytest.fixture
def simple_sales_df() -> pd.DataFrame:
    """Deterministic sales DataFrame with known numbers for unit tests."""
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "product": [
                "Laptop", "Mouse", "Laptop", "Keyboard", "Mouse",
                "Laptop", "Monitor", "Monitor", "Laptop", "Keyboard",
            ],
            "category": [
                "Tech", "Accessories", "Tech", "Accessories", "Accessories",
                "Tech", "Tech", "Tech", "Tech", "Accessories",
            ],
            "customer": [
                "Alice", "Bob", "Alice", "Charlie", "Bob",
                "Charlie", "Alice", "David", "David", "Alice",
            ],
            "quantity": [1, 2, 2, 1, 3, 1, 1, 2, 1, 2],
            "unit_price": [1000.0, 25.0, 1000.0, 75.0, 25.0, 1000.0, 300.0, 300.0, 1000.0, 75.0],
            "revenue": [1000.0, 50.0, 2000.0, 75.0, 75.0, 1000.0, 300.0, 600.0, 1000.0, 150.0],
            "cost": [700.0, 30.0, 1400.0, 45.0, 45.0, 700.0, 200.0, 400.0, 700.0, 90.0],
        }
    )


@pytest.fixture
def sales_context(simple_sales_df: pd.DataFrame) -> DatasetContext:
    """DatasetContext wrapping simple_sales_df with standard mapping."""
    mapping = {
        "date": "date",
        "product": "product",
        "category": "category",
        "customer": "customer",
        "quantity": "quantity",
        "unit_price": "unit_price",
        "revenue": "revenue",
        "cost": "cost",
    }
    return DatasetContext(
        sheets={"Sales": simple_sales_df},
        mapping=mapping,
        quality_summary={"Sales": QualitySummary(sheet_name="Sales", row_count=len(simple_sales_df))},
        dayfirst=False,
        send_sample_rows=False,
    )


@pytest.fixture
def inventory_df() -> pd.DataFrame:
    """Deterministic inventory DataFrame."""
    return pd.DataFrame(
        {
            "product": ["Widget A", "Widget B", "Widget C", "Widget D"],
            "stock_qty": [100, 50, 0, 20],
            "unit_cost": [10.0, 25.0, 5.0, 100.0],
            "last_movement_date": ["2023-01-01", "2024-03-01", "2024-03-15", "2023-06-01"],
        }
    )


@pytest.fixture
def receivables_df() -> pd.DataFrame:
    """Deterministic receivables DataFrame."""
    return pd.DataFrame(
        {
            "customer": ["Cust A", "Cust B", "Cust A", "Cust C"],
            "invoice_amount": [5000.0, 2000.0, 3000.0, 1500.0],
            "paid_amount": [1000.0, 2000.0, 0.0, 500.0],
            "due_date": ["2024-01-15", "2024-02-01", "2023-11-01", "2024-05-01"],
        }
    )


@pytest.fixture
def expenses_df() -> pd.DataFrame:
    """Deterministic expenses DataFrame."""
    return pd.DataFrame(
        {
            "category": ["Rent", "Salaries", "Rent", "Marketing", "Utilities"],
            "expense_amount": [5000.0, 12000.0, 5000.0, 3000.0, 800.0],
            "date": ["2024-01-01", "2024-01-25", "2024-02-01", "2024-02-10", "2024-02-15"],
        }
    )
