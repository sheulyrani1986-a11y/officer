"""Unit tests for OfficeR Command and Undo/Redo stack."""

import pytest
from officer.core.commands.base import Command
from officer.core.commands.stack import CommandStack


class TextInsertCommand(Command):
    def __init__(self, target: list, text: str):
        super().__init__(f"Insert '{text}'")
        self.target = target
        self.text = text

    def execute(self) -> None:
        self.target.append(self.text)

    def undo(self) -> None:
        if self.target and self.target[-1] == self.text:
            self.target.pop()


def test_command_execution_and_undo_redo():
    doc = []
    stack = CommandStack()

    cmd1 = TextInsertCommand(doc, "Hello")
    stack.push(cmd1)

    assert doc == ["Hello"]
    assert stack.can_undo is True
    assert stack.can_redo is False
    assert stack.undo_text == "Insert 'Hello'"

    cmd2 = TextInsertCommand(doc, "World")
    stack.push(cmd2)

    assert doc == ["Hello", "World"]
    assert stack.can_undo is True

    # Undo cmd2
    stack.undo()
    assert doc == ["Hello"]
    assert stack.can_redo is True
    assert stack.redo_text == "Insert 'World'"

    # Undo cmd1
    stack.undo()
    assert doc == []
    assert stack.can_undo is False
    assert stack.can_redo is True

    # Redo cmd1
    stack.redo()
    assert doc == ["Hello"]

    # Redo cmd2
    stack.redo()
    assert doc == ["Hello", "World"]
    assert stack.can_redo is False


def test_command_stack_clean_state():
    doc = []
    stack = CommandStack()
    assert stack.is_clean is True

    stack.push(TextInsertCommand(doc, "A"))
    assert stack.is_clean is False

    stack.set_clean()
    assert stack.is_clean is True

    stack.push(TextInsertCommand(doc, "B"))
    assert stack.is_clean is False

    stack.undo()
    assert stack.is_clean is True  # Returned to clean point


def test_macro_compound_command():
    doc = []
    stack = CommandStack()

    with stack.macro("Type Sentence"):
        stack.push(TextInsertCommand(doc, "OfficeR"))
        stack.push(TextInsertCommand(doc, "is"))
        stack.push(TextInsertCommand(doc, "awesome"))

    assert doc == ["OfficeR", "is", "awesome"]
    assert stack.undo_text == "Type Sentence"

    # Undoing once should undo all three items atomically
    stack.undo()
    assert doc == []
    assert stack.can_redo is True

    # Redo should restore all three
    stack.redo()
    assert doc == ["OfficeR", "is", "awesome"]
