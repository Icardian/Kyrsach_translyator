"""Синтаксический анализ SELECT методом рекурсивного спуска."""

import math

from .lexer import AGGREGATES, Token, tokenize
from .model import (
    Aggregate, Comparison, Junction, Literal, Name, Negation, NullTest,
    Operand, Predicate, Query, QueryError, SelectItem, SortTerm,
)


MAX_NESTING = 32
MAX_NUMBER_LENGTH = 256
COMPARISONS = frozenset({"=", "!=", "<>", "<", "<=", ">", ">="})
LITERALS = {"NULL": None, "TRUE": True, "FALSE": False}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def take(self) -> Token:
        token = self.current
        self.index += 1
        return token

    def accept(self, kind: str) -> bool:
        if self.current.kind != kind:
            return False
        self.take()
        return True

    def expect(self, kind: str, label: str | None = None) -> Token:
        if self.current.kind == kind:
            return self.take()
        found = "конец SQL-файла" if self.current.kind == "EOF" else repr(self.current.text)
        raise self.error(f"Ожидалось {label or kind!r}, получено {found}.")

    def error(self, message: str) -> QueryError:
        return QueryError("синтаксическая", self.current.location, message)

    def name(self) -> Name:
        token = self.expect("NAME", "имя")
        return Name(token.text, token.location)

    def comma_list(self, parse_item):
        values = [parse_item()]
        while self.accept(","):
            values.append(parse_item())
        return tuple(values)

    def query(self) -> Query:
        start = self.expect("SELECT")
        items = None if self.accept("*") else self.comma_list(self.select_item)
        self.expect("FROM")
        table = self.name()
        where = self.parse_or() if self.accept("WHERE") else None
        group_by = ()
        if self.accept("GROUP"):
            self.expect("BY")
            group_by = self.comma_list(self.name)
        order_by = ()
        if self.accept("ORDER"):
            self.expect("BY")
            order_by = self.comma_list(self.sort_term)
        limit = self.limit() if self.accept("LIMIT") else None
        self.accept(";")
        self.expect("EOF", "конец SQL-файла")
        return Query(table, items, where, group_by, order_by, limit, start.location)

    def select_item(self) -> SelectItem:
        if self.current.kind in AGGREGATES:
            function = self.take()
            self.expect("(")
            column = None if self.accept("*") else self.name()
            self.expect(")")
            expression = Aggregate(function.kind, column, function.location)
        else:
            expression = self.name()
        alias = self.name() if self.accept("AS") else None
        return SelectItem(expression, alias)

    def sort_term(self) -> SortTerm:
        name = self.name()
        descending = self.accept("DESC")
        if not descending:
            self.accept("ASC")
        return SortTerm(name, descending)

    def limit(self) -> int:
        token = self.expect("NUMBER", "целое неотрицательное число")
        if not token.text.isdigit() or len(token.text) > MAX_NUMBER_LENGTH:
            raise QueryError("синтаксическая", token.location,
                             "LIMIT должен быть целым неотрицательным числом без знака.")
        return int(token.text)

    def parse_or(self, depth: int = 0) -> Predicate:
        conditions = [self.parse_and(depth)]
        while self.accept("OR"):
            conditions.append(self.parse_and(depth))
        return conditions[0] if len(conditions) == 1 else Junction("OR", tuple(conditions))

    def parse_and(self, depth: int) -> Predicate:
        conditions = [self.parse_not(depth)]
        while self.accept("AND"):
            conditions.append(self.parse_not(depth))
        return conditions[0] if len(conditions) == 1 else Junction("AND", tuple(conditions))

    def parse_not(self, depth: int) -> Predicate:
        if depth > MAX_NESTING:
            raise self.error(f"Вложенность условий превышает {MAX_NESTING}.")
        if self.accept("NOT"):
            return Negation(self.parse_not(depth + 1))
        if self.accept("("):
            condition = self.parse_or(depth + 1)
            self.expect(")")
            return condition
        return self.test()

    def test(self) -> Predicate:
        left = self.operand()
        if self.accept("IS"):
            negated = self.accept("NOT")
            self.expect("NULL")
            return NullTest(left, negated)
        if self.current.kind not in COMPARISONS:
            raise self.error("Ожидался оператор сравнения или IS [NOT] NULL.")
        operator = self.take().kind
        return Comparison(left, operator, self.operand())

    def operand(self) -> Operand:
        kind = self.current.kind
        if kind == "NAME":
            return self.name()
        if kind == "STRING":
            return Literal(self.take().text)
        if kind in LITERALS:
            self.take()
            return Literal(LITERALS[kind])
        if kind == "NUMBER":
            return Literal(parse_number(self.take()))
        raise self.error("Ожидалось имя столбца или литерал.")


def parse_number(token: Token) -> int | float:
    if len(token.text) > MAX_NUMBER_LENGTH:
        raise QueryError("синтаксическая", token.location, "Числовой литерал слишком длинный.")
    if any(char in token.text for char in ".eE"):
        value = float(token.text)
        if not math.isfinite(value):
            raise QueryError("синтаксическая", token.location, "Число вне допустимого диапазона.")
        return value
    return int(token.text)


def parse(text: str) -> Query:
    return Parser(tokenize(text)).query()
