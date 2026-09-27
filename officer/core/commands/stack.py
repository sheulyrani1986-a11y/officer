"""CommandStack managing Undo and Redo operations with Qt signals."""

from contextlib import contextmanager
from typing import List, Optional
from PySide6.QtCore import QObject, Signal
from officer.core.commands.base import Command, CompoundCommand


class CommandStack(QObject):
    """
    Manages the undo/redo history for an active document.
    Emits signals when undo/redo availability or document clean state changes.
    """

    canUndoChanged = Signal(bool)
    canRedoChanged = Signal(bool)
    cleanChanged = Signal(bool)
    undoTextChanged = Signal(str)
    redoTextChanged = Signal(str)

    def __init__(self, limit: int = 1000, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._limit = limit
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._clean_index: int = 0
        self._active_macro: Optional[CompoundCommand] = None
        self._is_executing: bool = False

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def is_clean(self) -> bool:
        """True if the document matches the last saved state."""
        return len(self._undo_stack) == self._clean_index

    @property
    def undo_text(self) -> str:
        return self._undo_stack[-1].description if self._undo_stack else ""

    @property
    def redo_text(self) -> str:
        return self._redo_stack[-1].description if self._redo_stack else ""

    def push(self, command: Command) -> None:
        """
        Execute and record a command onto the undo stack.
        Clears the redo stack.
        """
        if self._is_executing:
            return

        # If a macro transaction is open, record into it instead
        if self._active_macro is not None:
            self._is_executing = True
            try:
                command.execute()
                self._active_macro.add(command)
            finally:
                self._is_executing = False
            return

        # Try merging with the previous command if possible
        if self._undo_stack and self._undo_stack[-1].merge_with(command):
            # Already executed and merged
            return

        self._is_executing = True
        try:
            command.execute()
        finally:
            self._is_executing = False

        self._undo_stack.append(command)
        if len(self._undo_stack) > self._limit:
            self._undo_stack.pop(0)
            if self._clean_index > 0:
                self._clean_index -= 1

        self._redo_stack.clear()
        self._emit_changes()

    def undo(self) -> None:
        """Undo the most recent command."""
        if not self.can_undo or self._is_executing:
            return

        command = self._undo_stack.pop()
        self._is_executing = True
        try:
            command.undo()
        finally:
            self._is_executing = False

        self._redo_stack.append(command)
        self._emit_changes()

    def redo(self) -> None:
        """Redo the previously undone command."""
        if not self.can_redo or self._is_executing:
            return

        command = self._redo_stack.pop()
        self._is_executing = True
        try:
            command.redo()
        finally:
            self._is_executing = False

        self._undo_stack.append(command)
        self._emit_changes()

    def set_clean(self) -> None:
        """Mark the current state as saved (clean)."""
        self._clean_index = len(self._undo_stack)
        self.cleanChanged.emit(True)

    def clear(self) -> None:
        """Clear all undo and redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._clean_index = 0
        self._emit_changes()

    @contextmanager
    def macro(self, description: str):
        """
        Context manager to group multiple operations into one atomic undo step.
        Example:
            with stack.macro("Apply Style to Selection"):
                stack.push(ChangeFontCommand(...))
                stack.push(ChangeColorCommand(...))
        """
        parent_macro = self._active_macro
        new_macro = CompoundCommand(description)
        self._active_macro = new_macro
        try:
            yield
        finally:
            self._active_macro = parent_macro

        if len(new_macro) > 0:
            if parent_macro is not None:
                parent_macro.add(new_macro)
            else:
                self._undo_stack.append(new_macro)
                self._redo_stack.clear()
                self._emit_changes()

    def _emit_changes(self) -> None:
        self.canUndoChanged.emit(self.can_undo)
        self.canRedoChanged.emit(self.can_redo)
        self.cleanChanged.emit(self.is_clean)
        self.undoTextChanged.emit(self.undo_text)
        self.redoTextChanged.emit(self.redo_text)
