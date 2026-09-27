"""Formula evaluator with dependency resolution and standard Excel functions."""

import math
import re
from typing import Any, Callable, Dict, List, Set, Tuple, Optional
from officer.rsheet.formula.parser import parse_cell_ref, parse_range_ref


class FormulaEvaluator:
    """Evaluates formulas in a spreadsheet sheet with cycle detection."""

    def __init__(self, get_cell_value: Callable[[int, int], Any]):
        """
        get_cell_value is a callable (row, col) -> raw or evaluated value
        """
        self._get_cell_value = get_cell_value
        self._evaluating_cells: Set[Tuple[int, int]] = set()

    def evaluate(self, formula: str, current_cell: Tuple[int, int] = (-1, -1)) -> Any:
        """
        Evaluate a formula string starting with '='.
        """
        if not formula.startswith("="):
            return formula

        expr = formula[1:].strip()
        if not expr:
            return ""

        if current_cell in self._evaluating_cells:
            return "#CYCLE!"

        self._evaluating_cells.add(current_cell)
        try:
            val = self._eval_expr(expr)
            return val
        except ZeroDivisionError:
            return "#DIV/0!"
        except Exception as e:
            return f"#VALUE!"
        finally:
            self._evaluating_cells.discard(current_cell)

    def _eval_expr(self, expr: str) -> Any:
        # Match function calls like SUM(A1:A5), AVERAGE(B1:B10), IF(...)
        fn_pattern = re.compile(r"([A-Za-z]+)\(([^()]+)\)")
        while True:
            match = fn_pattern.search(expr)
            if not match:
                break
            fn_name = match.group(1).upper()
            args_str = match.group(2)
            fn_res = self._call_function(fn_name, args_str)
            expr = expr[:match.start()] + str(fn_res) + expr[match.end():]

        # Replace remaining cell references like A1, B4 with their values
        expr = self._replace_refs(expr)

        # Safely evaluate arithmetic expression using AST or restricted eval
        return self._safe_arithmetic(expr)

    def _replace_refs(self, text: str) -> str:
        ref_pattern = re.compile(r"\b([A-Za-z]+)(\d+)\b")
        def replace_ref(m):
            col_str, row_str = m.group(1), m.group(2)
            cell = parse_cell_ref(f"{col_str}{row_str}")
            if cell:
                val = self._get_numeric_value(cell[0], cell[1])
                return str(val)
            return m.group(0)
        return ref_pattern.sub(replace_ref, text)

    def _call_function(self, name: str, args_str: str) -> Any:
        # Split args by comma (simple top-level)
        raw_args = [a.strip() for a in args_str.split(",")]

        if name in ("SUM", "AVERAGE", "MIN", "MAX", "COUNT", "COUNTA"):
            values = []
            for arg in raw_args:
                if ":" in arg:
                    for r, c in parse_range_ref(arg):
                        v = self._get_numeric_value(r, c)
                        if v is not None:
                            values.append(v)
                else:
                    cell = parse_cell_ref(arg)
                    if cell:
                        v = self._get_numeric_value(cell[0], cell[1])
                        if v is not None:
                            values.append(v)
                    else:
                        try:
                            values.append(float(arg))
                        except ValueError:
                            pass

            if name == "SUM":
                return sum(values)
            elif name == "AVERAGE":
                return sum(values) / len(values) if values else 0.0
            elif name == "MIN":
                return min(values) if values else 0.0
            elif name == "MAX":
                return max(values) if values else 0.0
            elif name in ("COUNT", "COUNTA"):
                return len(values)

        elif name == "IF":
            if len(raw_args) >= 2:
                cond_expr = self._replace_refs(raw_args[0])
                cond_val = self._safe_arithmetic(cond_expr)
                true_val = raw_args[1].strip("\"'")
                false_val = raw_args[2].strip("\"'") if len(raw_args) > 2 else ""
                return true_val if bool(cond_val) else false_val

        elif name == "CONCAT":
            out = ""
            for arg in raw_args:
                cell = parse_cell_ref(arg)
                if cell:
                    out += str(self._get_cell_value(cell[0], cell[1]) or "")
                else:
                    out += arg.strip("\"'")
            return out

        return 0

    def _get_numeric_value(self, row: int, col: int) -> Optional[float]:
        val = self._get_cell_value(row, col)
        if val is None or val == "":
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str) and val.startswith("="):
            val = self.evaluate(val, (row, col))
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def _safe_arithmetic(self, expr: str) -> Any:
        """Safely compute mathematical expression without exposing dangerous functions."""
        # Replace ^ with ** for power
        expr = expr.replace("^", "**")
        allowed_chars = set("0123456789.+-*/() <>!=eE")
        if not all(ch in allowed_chars for ch in expr):
            # If string contains non-math characters, return trimmed string
            return expr.strip("\"'")
        try:
            # Evaluate strictly in clean environment
            res = eval(expr, {"__builtins__": None}, {})
            if isinstance(res, float) and res.is_integer():
                return int(res)
            return res
        except Exception:
            return "#ERROR!"
