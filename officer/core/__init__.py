"""OfficeR Core - Shared infrastructure for WriteR, RSheet, and PresentR."""

from officer.core.commands.base import Command, CompoundCommand
from officer.core.commands.stack import CommandStack

__all__ = ["Command", "CompoundCommand", "CommandStack"]
