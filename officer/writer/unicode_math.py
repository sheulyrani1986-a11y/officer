"""Typed maths → Unicode maths, so an equation stays text.

Word keeps an equation as characters: you can search it, fix one symbol, and a
screen reader can say it. A rendered PNG cannot do any of that. This module
converts what a person types in the equation box -- LaTeX-style commands or
plain linear maths like ``x^2 + y^2 = z^2`` -- into the Unicode characters that
mean the same thing.

Conversion is deliberately lossless. A command with no equivalent here, or a
script using a character that has no superscript form, is kept as it was typed
rather than dropped or guessed at. :func:`to_math_runs` marks the second of
those, because Unicode has no raised π and a document can raise one anyway.
"""

import re
from typing import Dict, List, Tuple

__all__ = ["to_unicode_math", "to_math_runs"]

# ------------------------------------------------------------------ character maps #

#: Superscript/subscript forms. Characters absent here make the whole script
#: fall back to its as-typed spelling, so ``e^{i\pi}`` never loses the pi.
_SUPERSCRIPT: Dict[str, str] = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ",
    "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ",
    "m": "ᵐ", "n": "ⁿ", "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ",
    "t": "ᵗ", "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
    "A": "ᴬ", "B": "ᴮ", "D": "ᴰ", "E": "ᴱ", "G": "ᴳ", "H": "ᴴ",
    "I": "ᴵ", "J": "ᴶ", "K": "ᴷ", "L": "ᴸ", "M": "ᴹ", "N": "ᴺ",
    "O": "ᴼ", "P": "ᴾ", "R": "ᴿ", "T": "ᵀ", "U": "ᵁ", "V": "ⱽ", "W": "ᵂ",
}

_SUBSCRIPT: Dict[str, str] = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
    "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ", "q": "ₔ",
}

#: ``\hat{x}`` and friends: a combining mark laid over the base. The base stays
#: a normal letter, so the result is still editable and searchable.
_ACCENT: Dict[str, str] = {
    "hat": "\u0302", "widehat": "\u0302", "tilde": "\u0303", "widetilde": "\u0303",
    "bar": "\u0304", "overline": "\u0305", "dot": "\u0307", "ddot": "\u0308",
    "dddot": "\u20db", "vec": "\u20d7", "overrightarrow": "\u20d7",
    "acute": "\u0301", "grave": "\u0300", "check": "\u030c", "breve": "\u0306",
    "mathring": "\u030a", "utilde": "\u0303",
}

#: Single-letter variable sets, the ones fontconfig carries everywhere. Other
#: ``\mathbb`` letters keep their plain form rather than reaching for a block
#: most installed faces have no glyphs for.
_DOUBLE_STRUCK: Dict[str, str] = {
    "R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ", "H": "ℍ",
}

#: ``\frac{1}{2}`` has a character of its own; beyond that a fraction slash
#: would render at the baseline in most text fonts, so it is not used.
_VULGAR: Dict[Tuple[str, str], str] = {
    ("1", "2"): "½", ("1", "3"): "⅓", ("2", "3"): "⅔",
    ("1", "4"): "¼", ("3", "4"): "¾", ("1", "5"): "⅕", ("2", "5"): "⅖",
    ("3", "5"): "⅗", ("4", "5"): "⅘", ("1", "6"): "⅙", ("5", "6"): "⅚",
    ("1", "8"): "⅛", ("3", "8"): "⅜", ("5", "8"): "⅝", ("7", "8"): "⅞",
    ("1", "7"): "⅐", ("1", "9"): "⅑", ("1", "10"): "⅒",
}

#: Spacing commands, translated into the spaces they ask for.
_SPACE: Dict[str, str] = {
    ",": "\u2009", ";": "\u2009", ":": "\u2009", "!": "", " ": " ",
    "quad": "\u2003", "qquad": "\u2003\u2003",
}

#: Layout-only commands with no textual content of their own.
_DROP = {
    "left", "right", "big", "Big", "bigg", "Bigg", "bigl", "Bigl", "biggr",
    "Biggr", "bigm", "Biggm", "displaystyle", "textstyle", "scriptstyle",
    "limits", "nolimits", "nonumber",
}

#: Commands whose braced argument names a layout rather than says anything:
#: ``\begin{pmatrix}`` asks for a matrix, and the characters inside it are the
#: maths. The environment is dropped; its contents stay.
_DROP_ARGUMENT = {"begin", "end", "substack"}

#: ``\\`` ends a row of one of those environments, so it needs a break that
#: reads as a break once the environment itself is gone.
_ROW_BREAK = " "

#: Named characters, including the function words LaTeX only asks for a
#: upright rendering of.
_SYMBOL: Dict[str, str] = {
    # Greek
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "varsigma": "ς", "tau": "τ",
    "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ",
    "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Xi": "Ξ", "Pi": "Π", "Rho": "Ρ", "Sigma": "Σ", "Upsilon": "Υ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    # Operators
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "cdot": "⋅", "ast": "∗",
    "star": "⋆", "circ": "∘", "bullet": "∙", "oplus": "⊕", "ominus": "⊖",
    "otimes": "⊗", "odot": "⊙", "setminus": "∖", "amalg": "⨿",
    # Relations
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "equiv": "≡", "approx": "≈", "cong": "≅", "simeq": "≃", "sim": "∼",
    "propto": "∝", "ll": "≪", "gg": "≫", "doteq": "≐", "perp": "⊥",
    "parallel": "∥", "mid": "∣", "nmid": "∤", "asymp": "≍", "Bumpeq": "≎",
    # Sets and logic
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆",
    "subsetneq": "⊊", "supset": "⊃", "supseteq": "⊇", "cup": "∪", "cap": "∩",
    "emptyset": "∅", "varnothing": "∅", "forall": "∀", "exists": "∃",
    "nexists": "∄", "neg": "¬", "lnot": "¬", "land": "∧", "wedge": "∧",
    "lor": "∨", "vee": "∨", "therefore": "∴", "because": "∵",
    # Large operators
    "sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬",
    "iiint": "∭", "oint": "∮", "bigcup": "⋃", "bigcap": "⋂", "bigsqcup": "⨆",
    "bigoplus": "⨁", "bigotimes": "⨂", "bigodot": "⨀", "bigwedge": "⋀",
    "bigvee": "⋁",
    # Arrows
    "to": "→", "rightarrow": "→", "longrightarrow": "⟶", "leftarrow": "←",
    "longleftarrow": "⟵", "leftrightarrow": "↔", "longleftrightarrow": "⟷",
    "Rightarrow": "⇒", "Longrightarrow": "⟹", "Leftarrow": "⇐",
    "Longleftarrow": "⟸", "Leftrightarrow": "⇔", "mapsto": "↦",
    "longmapsto": "⟼", "uparrow": "↑", "downarrow": "↓", "Uparrow": "⇑",
    "Downarrow": "⇓", "nearrow": "↗", "searrow": "↘", "swarrow": "↙",
    "nwarrow": "↖", "implies": "⟹", "iff": "⟺", "updownarrow": "↕",
    # Calculus and constants
    "infty": "∞", "partial": "∂", "nabla": "∇", "hbar": "ℏ", "ell": "ℓ",
    "aleph": "ℵ", "wp": "℘", "Re": "ℜ", "Im": "ℑ", "prime": "′",
    "degree": "°", "celsius": "℃", "percent": "%",
    # Delimiters and shapes
    "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋",
    "lceil": "⌈", "rceil": "⌉", "angle": "∠", "measuredangle": "∡",
    "triangle": "△", "square": "□", "surd": "√",
    "backslash": "\\",
    # Dots and marks
    "dots": "…", "ldots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
    "colon": "∶", "checkmark": "✓", "dagger": "†", "ddagger": "‡",
    "S": "§", "P": "¶", "copyright": "©", "pound": "£", "euro": "€",
    "yen": "¥", "cent": "¢",
    # Escaped punctuation
    "%": "%", "&": "&", "#": "#", "$": "$", "_": "_", "{": "{", "}": "}",
    "^": "^", "~": "∼",
    # Function words: LaTeX typesets them upright, so they are letters, not marks
    "sin": "sin", "cos": "cos", "tan": "tan", "cot": "cot", "sec": "sec",
    "csc": "csc", "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan",
    "sinh": "sinh", "cosh": "cosh", "tanh": "tanh", "log": "log", "ln": "ln",
    "exp": "exp", "lim": "lim", "max": "max", "min": "min", "sup": "sup",
    "inf": "inf", "det": "det", "dim": "dim", "ker": "ker", "deg": "deg",
    "gcd": "gcd", "arg": "arg", "Pr": "Pr", "mod": "mod",
}

#: What someone types without LaTeX at all. Applied last, so it only sees the
#: characters the document really meant.
_LINEAR = (
    ("<=>", "⇔"), ("-->", "⟶"), ("=>", "⇒"), ("->", "→"), ("<-", "←"),
    ("<=", "≤"), (">=", "≥"), ("!=", "≠"), ("/=", "≠"), ("~=", "≈"),
    ("+-", "±"), ("...", "…"), ("||", "∥"), ("|--", "⊢"),
)

_COMMAND = re.compile(r"\\([A-Za-z]+|.)")


def to_unicode_math(expression: str) -> str:
    """Return *expression* written with Unicode maths characters.

    Accepts LaTeX-style input (``$`` delimiters optional) and linear input
    alike; whatever cannot be mapped is left in the form it was typed.
    """
    return _linear_pass(_convert(_unwrap(expression)))


def to_math_runs(text: str) -> List[Tuple[str, int]]:
    """Split converted maths into ``(text, script)`` runs.

    *script* is ``1`` for raised text, ``-1`` for lowered, ``0`` for the line.
    A script whose characters all have a Unicode form arrives already wearing
    it; one that has no such form -- the π of ``e^iπ`` -- is left marked, and
    this reads the mark back so the document can lift those characters with real
    formatting instead of spelling them out.
    """
    runs: List[Tuple[str, int]] = []
    plain: List[str] = []
    index, length = 0, len(text)
    while index < length:
        if text[index] in "^_":
            body, taken = _marked_script(text, index + 1)
            if taken:
                if plain:
                    runs.append(("".join(plain), 0))
                    plain = []
                runs.append((body, 1 if text[index] == "^" else -1))
                index += 1 + taken
                continue
        plain.append(text[index])
        index += 1
    if plain:
        runs.append(("".join(plain), 0))
    return runs


# --------------------------------------------------------------------- internals #

def _marked_script(text: str, at: int) -> Tuple[str, int]:
    """The body a caret or underscore marks at *at*, and how far it reaches."""
    if at >= len(text):
        return "", 0
    if text[at] == "(":
        depth = 0
        for index in range(at, len(text)):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    return text[at + 1:index], index - at + 1
        return "", 0
    if text[at] not in " )":
        return text[at], 1
    return "", 0

def _unwrap(text: str) -> str:
    """Drop the ``$...$`` / ``\\(...\\)`` wrapper a LaTeX snippet comes with."""
    text = text.strip()
    for opening, closing in (("$", "$"), (r"\(", r"\)"), (r"\[", r"\]")):
        if text.startswith(opening) and text.endswith(closing) and len(text) > 2:
            text = text[len(opening):-len(closing)].strip()
    return text


def _convert(text: str) -> str:
    """One pass over *text*, expanding commands, scripts and groups."""
    out: list[str] = []
    position, length = 0, len(text)
    while position < length:
        char = text[position]
        if char == "\\":
            command, position = _read_command(text, position)
            piece, position = _expand(command, text, position)
            out.append(piece)
        elif char in "^_":
            body, position = _read_script(text, position + 1)
            table = _SUPERSCRIPT if char == "^" else _SUBSCRIPT
            out.append(_apply_script(body, table))
        elif char == "{":
            inner, position = _read_group(text, position)
            out.append(_convert(inner))
        else:
            out.append(char)
            position += 1
    return "".join(out)


def _read_command(text: str, start: int) -> Tuple[str, int]:
    """The name after ``text[start:]``'s backslash: ``\\frac`` → ``frac``."""
    match = _COMMAND.match(text, start)
    if not match:
        return "", start + 1
    return match.group(1), match.end()


def _read_group(text: str, start: int) -> Tuple[str, int]:
    """Braced content at ``text[start]``, so nested braces stay together."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    return text[start + 1:], len(text)


def _read_argument(text: str, start: int) -> Tuple[str, int]:
    """One operand: a braced group, a command, or a lone character."""
    index = start
    while index < len(text) and text[index] == " ":
        index += 1
    if index >= len(text):
        return "", index
    if text[index] == "{":
        inner, index = _read_group(text, index)
        return _convert(inner), index
    if text[index] == "\\":
        name, index = _read_command(text, index)
        piece, index = _expand(name, text, index)
        return piece, index
    return text[index], index + 1


def _read_script(text: str, start: int) -> Tuple[str, int]:
    """What a ``^`` or ``_`` raises: everything glued to it.

    Typed maths is read left to right, so a space is what ends a script's scope
    rather than a single character: ``e^i\\pi`` raises the pi with the *i*, while
    ``e^i \\pi`` leaves it on the line. A brace still says where it ends, and an
    operand that is neither letter nor command -- ``^-``, ``^(2y)`` -- is taken
    one at a time, as it has always been.
    """
    index = start
    while index < len(text) and text[index] == " ":
        index += 1
    parts: List[str] = []
    while index < len(text):
        if text[index] == "\\":
            piece, index = _read_argument(text, index)
            parts.append(piece)
        elif text[index].isalnum():
            parts.append(text[index])
            index += 1
        else:
            break
    if parts:
        return "".join(parts), index
    return _read_argument(text, start)


def _expand(command: str, text: str, index: int) -> Tuple[str, int]:
    """Render *command*, reading whatever operands it takes from *text*."""
    if command in _DROP:
        return "", index
    if command == "\\":
        return _ROW_BREAK, index
    if command in _SPACE:
        return _SPACE[command], index
    if command in _DROP_ARGUMENT:
        _, index = _raw_argument(text, index)
        return "", index

    if command.endswith("frac"):
        numerator, index = _read_argument(text, index)
        denominator, index = _read_argument(text, index)
        return _fraction(numerator, denominator), index
    if command == "binom":
        top, index = _read_argument(text, index)
        bottom, index = _read_argument(text, index)
        return f"({top} {bottom})", index
    if command == "sqrt":
        return _sqrt(text, index)
    if command in _ACCENT:
        base, index = _read_argument(text, index)
        return _apply_accent(base, _ACCENT[command]), index
    if command in ("text", "mbox", "textrm", "mathrm", "hbox"):
        return _raw_argument(text, index)
    if command in ("mathbf", "boldsymbol", "bm", "mathit", "mathsf", "mathtt"):
        # Styling only: the letters are the content, and the run's own
        # character format is where bold or italic belongs.
        return _raw_argument(text, index)
    if command == "mathbb":
        letters, index = _raw_argument(text, index)
        return "".join(_DOUBLE_STRUCK.get(letter, letter) for letter in letters), index
    if command in _SYMBOL:
        return _SYMBOL[command], index
    # Nothing to lose: an unknown command reads better as itself than as a guess.
    return f"\\{command}", index


def _raw_argument(text: str, index: int) -> Tuple[str, int]:
    """An operand taken verbatim -- ``\\text{hello world}`` keeps its spacing."""
    scan = index
    while scan < len(text) and text[scan] == " ":
        scan += 1
    if scan < len(text) and text[scan] == "{":
        return _read_group(text, scan)
    if scan < len(text) and text[scan] == "\\":
        return _read_command(text, scan)
    if scan < len(text):
        return text[scan], scan + 1
    return "", scan


def _apply_script(body: str, table: Dict[str, str]) -> str:
    """Superscript or subscript *body*, or its plain spelling where that fails."""
    if not body:
        return ""
    marker = "^" if table is _SUPERSCRIPT else "_"
    mapped = []
    for char in body:
        if char == " ":
            continue
        if char not in table:
            return f"{marker}{body}" if len(body) == 1 else f"{marker}({body})"
        mapped.append(table[char])
    return "".join(mapped)


def _apply_accent(base: str, mark: str) -> str:
    r"""``\hat`` over a group decorates its last letter, which is what Word does."""
    if not base:
        return mark
    return f"{base}{mark}"


def _fraction(numerator: str, denominator: str) -> str:
    if (numerator, denominator) in _VULGAR:
        return _VULGAR[(numerator, denominator)]
    return f"{_wrap(numerator)}/{_wrap(denominator)}"


def _wrap(operand: str) -> str:
    """Parenthesise anything a reader could misparse as part of its neighbour."""
    if len(operand) == 1 or (operand.isdigit() and len(operand) <= 2):
        return operand
    return f"({operand})"


def _sqrt(text: str, index: int) -> Tuple[str, int]:
    """``\\sqrt{x}`` → ``√(x)``; ``\\sqrt[3]{x}`` → ``³√(x)``."""
    degree = ""
    scan = index
    while scan < len(text) and text[scan] == " ":
        scan += 1
    if scan < len(text) and text[scan] == "[":
        close = text.find("]", scan)
        if close != -1:
            degree = _apply_script(_convert(text[scan + 1:close]), _SUPERSCRIPT)
            index = close + 1
    radicand, index = _read_argument(text, index)
    body = radicand if len(radicand) == 1 else f"({radicand})"
    return f"{degree}√{body}", index


def _linear_pass(text: str) -> str:
    """Turn the ASCII spellings people type into their mathematical characters."""
    for ascii_form, character in _LINEAR:
        text = text.replace(ascii_form, character)
    return text
