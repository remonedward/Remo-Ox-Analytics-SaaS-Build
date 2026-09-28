from __future__ import annotations

"""Abstract Base Component for reusable UI widgets."""

from abc import ABC, abstractmethod


class BaseComponent(ABC):
    """Abstract base class for all reusable UI components."""

    @abstractmethod
    def render(self) -> None:
        """Render component into the Streamlit container."""
