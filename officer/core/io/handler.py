"""Base Document IO interface and format registry."""

from abc import ABC, abstractmethod
from typing import List, Tuple, Any, Optional


class DocumentIOHandler(ABC):
    """Abstract file format handler for loading and saving application documents."""

    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """List of extensions, e.g. ['.docx', '.odt']."""
        pass

    @abstractmethod
    def load(self, filepath: str, target_model: Any) -> bool:
        """Load data from filepath into target_model."""
        pass

    @abstractmethod
    def save(self, filepath: str, source_model: Any) -> bool:
        """Save data from source_model to filepath."""
        pass
