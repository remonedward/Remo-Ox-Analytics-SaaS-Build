from __future__ import annotations

"""Unit tests for ChartRenderer (analytics/charts.py)."""

from unittest.mock import MagicMock, patch

import matplotlib.figure
import pandas as pd
import pytest

from analytics.charts import DEFAULT_PALETTE, ChartRenderer


@pytest.fixture
def sample_sales_df() -> pd.DataFrame:
    return pd.DataFrame({
        "المنتج": ["لابتوب ديل", "شاشة سامسونج", "ماوس لاسلكي", "لوحة مفاتيح"],
        "المبيعات": [15000.0, 8500.5, 1200.0, 2400.0],
    })


@pytest.fixture
def sample_timeseries_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Month": ["2024-01", "2024-02", "2024-03", "2024-04"],
        "Revenue": [10000, 15000, 13000, 19000],
    })


def test_chart_renderer_initialization():
    renderer = ChartRenderer(primary_color="#1B4F72")
    assert renderer.primary_color == "#1B4F72"
    assert renderer.palette == DEFAULT_PALETTE

    custom_palette = ["#111111", "#222222"]
    renderer2 = ChartRenderer(primary_color="#000000", palette=custom_palette)
    assert renderer2.palette == custom_palette


def test_shape_text_arabic_and_english():
    # English text should return as-is
    en_text = "Revenue by Product"
    assert ChartRenderer.shape_text(en_text) == en_text

    # Arabic text should be reshaped (not equal to raw Arabic due to bidi/reshaping)
    ar_text = "المبيعات حسب الصنف"
    shaped = ChartRenderer.shape_text(ar_text)
    assert shaped != ar_text
    assert len(shaped) > 0

    # Non-string / numeric should be converted to string safely
    assert ChartRenderer.shape_text(12345) == "12345"


def test_render_figure_hbar(sample_sales_df):
    renderer = ChartRenderer()
    fig = renderer.render_figure(
        chart_type="hbar",
        df=sample_sales_df,
        x_col="المنتج",
        y_col="المبيعات",
        title="أفضل المنتجات مبيعاً",
        language="ar",
    )
    assert isinstance(fig, matplotlib.figure.Figure)
    assert len(fig.axes) == 1
    # Check that y-ticks match category count
    assert len(fig.axes[0].get_yticks()) == len(sample_sales_df)
    matplotlib.pyplot.close(fig)


def test_render_figure_line(sample_timeseries_df):
    renderer = ChartRenderer()
    fig = renderer.render_figure(
        chart_type="line",
        df=sample_timeseries_df,
        x_col="Month",
        y_col="Revenue",
        title="Monthly Trend",
        language="en",
    )
    assert isinstance(fig, matplotlib.figure.Figure)
    assert len(fig.axes) == 1
    matplotlib.pyplot.close(fig)


def test_render_figure_pie(sample_sales_df):
    renderer = ChartRenderer()
    fig = renderer.render_figure(
        chart_type="pie",
        df=sample_sales_df,
        x_col="المنتج",
        y_col="المبيعات",
        title="توزيع المبيعات",
        language="ar",
    )
    assert isinstance(fig, matplotlib.figure.Figure)
    assert len(fig.axes) == 1
    matplotlib.pyplot.close(fig)


def test_render_figure_default_bar(sample_sales_df):
    renderer = ChartRenderer()
    fig = renderer.render_figure(
        chart_type="bar",
        df=sample_sales_df,
        x_col="المنتج",
        y_col="المبيعات",
        title="أعمدة رأسية",
    )
    assert isinstance(fig, matplotlib.figure.Figure)
    matplotlib.pyplot.close(fig)


def test_render_figure_fallback_columns(sample_sales_df):
    renderer = ChartRenderer()
    # Request columns that don't exist; should fall back to iloc[:, 0] and iloc[:, 1]
    fig = renderer.render_figure(
        chart_type="hbar",
        df=sample_sales_df,
        x_col="non_existent_x",
        y_col="non_existent_y",
    )
    assert isinstance(fig, matplotlib.figure.Figure)
    matplotlib.pyplot.close(fig)


def test_render_png_bytes(sample_sales_df):
    renderer = ChartRenderer()
    png_bytes = renderer.render_png_bytes(
        chart_type="hbar",
        df=sample_sales_df,
        x_col="المنتج",
        y_col="المبيعات",
        title="PNG Test",
    )
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 0
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_to_streamlit(sample_sales_df):
    renderer = ChartRenderer()
    mock_st = MagicMock()
    with patch.dict("sys.modules", {"streamlit": mock_st}):
        renderer.render_to_streamlit(
            chart_type="line",
            df=sample_sales_df,
            x_col="المنتج",
            y_col="المبيعات",
            title="Streamlit Render",
        )
        assert mock_st.pyplot.called
