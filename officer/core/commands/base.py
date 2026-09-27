"""Base Command abstractions for OfficeR's Undo/Redo system."""

from abc import ABC, abstractmethod
from typing import List


class Command(ABC):
    """Abstract base class for all undoable operations in OfficeR."""

    def __init__(self, description: str = ""):
        self.description = description

    @abstractmethod
    def execute(self) -> None:
        """Apply the command's changes to the document."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Revert the command's changes."""
        pass

    def redo(self) -> None:
        """Re-apply the command (defaults to execute)."""
        self.execute()

    def merge_with(self, other: "Command") -> bool:
        """
        Attempt to merge another command into this one (e.g. continuous typing).
        Returns True if merged, False otherwise.
        """
        return False

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: '{self.description}'>"


class CompoundCommand(Command):
    """A composite command that bundles multiple operations into a single undo step."""

    def __init__(self, description: str = ""):
        super().__init__(description)
        self.commands: List[Command] = []

    def add(self, command: Command) -> None:
        """Add a command to the compound batch."""
        self.commands.append(command)

    def execute(self) -> None:
        for cmd in self.commands:
            cmd.execute()

    def undo(self) -> None:
        # Revert in reverse order of execution
        for cmd in reversed(self.commands):
            cmd.undo()

    def redo(self) -> None:
        for cmd in self.commands:
            cmd.redo()

    def __len__(self) -> int:
        return len(self.commands)
