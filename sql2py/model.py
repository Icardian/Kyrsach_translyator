"""Узлы абстрактного синтаксического дерева SQL-запроса."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    line: int
    column: int


class QueryError(ValueError):
    def __init__(self, phase: str, location: Location, message: str):
        super().__init__(message)
        self.phase = phase
        self.location = location


Scalar = str | int | float | bool | None


@dataclass(frozen=True)
class Name:
    text: str
    location: Location

    @property
    def key(self) -> str:
        return self.text.casefold()


@dataclass(frozen=True)
class Literal:
    value: Scalar


Operand = Name | Literal


@dataclass(frozen=True)
class Comparison:
    left: Operand
    operator: str
    right: Operand


@dataclass(frozen=True)
class NullTest:
    operand: Operand
    negated: bool


@dataclass(frozen=True)
class Negation:
    condition: Predicate


@dataclass(frozen=True)
class Junction:
    operator: str
    conditions: tuple[Predicate, ...]


Predicate = Comparison | NullTest | Negation | Junction


@dataclass(frozen=True)
class Aggregate:
    function: str
    column: Name | None  # None соответствует COUNT(*).
    location: Location


@dataclass(frozen=True)
class SelectItem:
    expression: Name | Aggregate
    alias: Name | None


@dataclass(frozen=True)
class SortTerm:
    name: Name
    descending: bool


@dataclass(frozen=True)
class Query:
    table: Name
    items: tuple[SelectItem, ...] | None  # None соответствует SELECT *.
    where: Predicate | None
    group_by: tuple[Name, ...]
    order_by: tuple[SortTerm, ...]
    limit: int | None
    location: Location
