from __future__ import annotations

"""Deterministic chart rendering engine with bilingual Arabic/English support."""

import io
import re
from typing import Any

import arabic_reshaper
import matplotlib
from bidi.algorithm import get_display

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core.logging_setup import get_logger

logger = get_logger(__name__)

# Arabic unicode range pattern
_ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF]")

# Professional Color Palette
DEFAULT_PALETTE = [
    "#1B4F72",  # Brand primary
    "#2E86C1",  # Blue
    "#16A085",  # Teal
    "#F39C12",  # Amber
    "#E74C3C",  # Coral red
    "#8E44AD",  # Purple
    "#2C3E50",  # Slate
    "#27AE60",  # Green
]


class ChartRenderer:
    """Renderer for high-quality, reproducible analytical charts with Arabic text shaping."""

    def __init__(
        self,
        primary_color: str = "#1B4F72",
        palette: list[str] | None = None,
    ) -> None:
        self.primary_color = primary_color
        self.palette = palette or DEFAULT_PALETTE

    @staticmethod
    def shape_text(text: Any) -> str:
        """Reshape and reorder Arabic text for correct Matplotlib visual rendering."""
        str_val = str(text)
        if _ARABIC_PATTERN.search(str_val):
            reshaped = arabic_reshaper.reshape(str_val)
            return get_display(reshaped)
        return str_val

    def render_figure(
        self,
        chart_type: str,
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        title: str = "",
        language: str = "ar",
    ) -> matplotlib.figure.Figure:
        """Construct and return a Matplotlib Figure."""
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=100)

        # Style figure background and spines
        fig.patch.set_facecolor("#FFFFFF")
        ax.set_facecolor("#FFFFFF")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#CBD5E1")
        ax.spines["bottom"].set_color("#CBD5E1")
        ax.tick_params(colors="#475569")
        ax.grid(axis="y", linestyle="--", alpha=0.3, color="#94A3B8")

        x_vals = df[x_col] if x_col in df.columns else df.iloc[:, 0]
        y_vals = pd.to_numeric(df[y_col], errors="coerce").fillna(0) if y_col in df.columns else pd.to_numeric(df.iloc[:, 1], errors="coerce").fillna(0)

        # Labels with Arabic text shaping
        x_labels = [self.shape_text(v) for v in x_vals]

        match chart_type:
            case "hbar":
                # Horizontal Bar (ideal for top products / categories)
                y_pos = range(len(df))
                bars = ax.barh(
                    y_pos,
                    y_vals,
                    color=self.primary_color,
                    alpha=0.9,
                    edgecolor="none",
                    height=0.65,
                )
                ax.set_yticks(y_pos)
                ax.set_yticklabels(x_labels, fontsize=9)
                ax.invert_yaxis()  # Top items on top
                ax.grid(axis="x", linestyle="--", alpha=0.3, color="#94A3B8")
                ax.grid(axis="y", visible=False)

                # Value annotations on bar tips
                max_val = max(y_vals) if len(y_vals) > 0 and max(y_vals) > 0 else 1
                for bar in bars:
                    width = bar.get_width()
                    ax.text(
                        width + (max_val * 0.01),
                        bar.get_y() + bar.get_height() / 2,
                        f"{width:,.0f}" if width >= 10 else f"{width:,.2f}",
                        va="center",
                        ha="left",
                        fontsize=8,
                        color="#334155",
                    )

            case "line":
                # Time-series trend line
                ax.plot(
                    x_labels,
                    y_vals,
                    color=self.primary_color,
                    marker="o",
                    linewidth=2.5,
                    markersize=6,
                )
                ax.fill_between(x_labels, y_vals, color=self.primary_color, alpha=0.1)
                plt.xticks(rotation=45, ha="right", fontsize=8)

            case "pie":
                # Donut chart
                colors = (self.palette * ((len(df) // len(self.palette)) + 1))[: len(df)]
                ax.grid(visible=False)
                wedges, _ = ax.pie(
                    y_vals,
                    labels=None,
                    startangle=90,
                    colors=colors,
                    wedgeprops={"width": 0.6, "edgecolor": "white", "linewidth": 2},
                )
                # Legend with percentages
                total = sum(y_vals) if sum(y_vals) > 0 else 1
                legend_labels = [
                    f"{label} ({val / total * 100:.1f}%)"
                    for label, val in zip(x_labels, y_vals, strict=False)
                ]
                ax.legend(
                    wedges,
                    legend_labels,
                    loc="center left",
                    bbox_to_anchor=(1, 0, 0.5, 1),
                    fontsize=8,
                    frameon=False,
                )

            case _:
                # Vertical Bar
                bars = ax.bar(
                    x_labels,
                    y_vals,
                    color=self.primary_color,
                    width=0.6,
                    alpha=0.9,
                )
                plt.xticks(rotation=45, ha="right", fontsize=8)

        if title:
            ax.set_title(self.shape_text(title), fontsize=12, fontweight="bold", color="#1E293B", pad=15)

        fig.tight_layout()
        return fig

    def render_png_bytes(
        self,
        chart_type: str,
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        title: str = "",
        language: str = "ar",
        dpi: int = 150,
    ) -> bytes:
        """Render chart directly to PNG bytes for PDF embedding or download."""
        fig = self.render_figure(chart_type, df, x_col, y_col, title=title, language=language)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def render_to_streamlit(
        self,
        chart_type: str,
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        title: str = "",
        language: str = "ar",
    ) -> None:
        """Render chart directly into Streamlit application."""
        try:
            import streamlit as st

            fig = self.render_figure(chart_type, df, x_col, y_col, title=title, language=language)
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        except Exception as exc:
            logger.warning("Could not render chart to Streamlit: %s", exc)
