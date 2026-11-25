"""Преобразование исходного текста в лексемы с координатами."""

import re
from dataclasses import dataclass

from .model import Location, QueryError


AGGREGATES = frozenset({"COUNT", "SUM", "AVG", "MIN", "MAX"})
KEYWORDS = AGGREGATES | {
    "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "ASC", "DESC", "LIMIT",
    "AS", "AND", "OR", "NOT", "IS", "NULL", "TRUE", "FALSE",
}
MAX_TOKENS = 4096

TOKEN_PATTERN = re.compile(
    r"(?P<SPACE>\s+)"
    r"|(?P<COMMENT>--[^\n]*|/\*[\s\S]*?\*/)"
    r"|(?P<STRING>'(?:[^']|'')*')"
    r'|(?P<QUOTED>"(?:[^"]|"")*")'
    r"|(?P<NUMBER>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?)(?![A-Za-z_0-9.])"
    r"|(?P<NAME>[A-Za-z_][A-Za-z_0-9]*)"
    r"|(?P<SYMBOL><=|>=|<>|!=|[=<>(),*;])"
)


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    location: Location


def tokenize(text: str) -> list[Token]:
    tokens = []
    offset = 0
    line = column = 1
    while offset < len(text):
        location = Location(line, column)
        match = TOKEN_PATTERN.match(text, offset)
        if match is None:
            starts = {"/*": "Многострочный комментарий не закрыт.",
                      "'": "Строковый литерал не закрыт.",
                      '"': "Имя в кавычках не закрыто."}
            marker = "/*" if text.startswith("/*", offset) else text[offset]
            message = starts.get(marker, f"Недопустимый символ {marker!r}.")
            raise QueryError("лексическая", location, message)

        kind = match.lastgroup
        raw = match.group()
        offset = match.end()
        newlines = raw.count("\n")
        if newlines:
            line += newlines
            column = len(raw) - raw.rfind("\n")
        else:
            column += len(raw)

        if kind in {"SPACE", "COMMENT"}:
            continue
        value = raw
        if kind == "NAME" and raw.upper() in KEYWORDS:
            kind = raw.upper()
        elif kind == "QUOTED":
            kind = "NAME"
            value = raw[1:-1].replace('""', '"')
            if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise QueryError("лексическая", location, "Недопустимое имя в кавычках.")
        elif kind == "STRING":
            value = raw[1:-1].replace("''", "'")
        elif kind == "SYMBOL":
            kind = raw

        tokens.append(Token(kind, value, location))
        if len(tokens) > MAX_TOKENS:
            raise QueryError("лексическая", location, f"В запросе больше {MAX_TOKENS} лексем.")

    tokens.append(Token("EOF", "", Location(line, column)))
    return tokens
