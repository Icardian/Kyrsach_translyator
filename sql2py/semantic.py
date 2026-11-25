"""Проверки, которые можно выполнить до чтения файла данных."""

from dataclasses import dataclass
from typing import Iterator

from .model import (
    Aggregate, Comparison, Junction, Name, Negation, NullTest, Predicate,
    Query, QueryError,
)


@dataclass(frozen=True)
class Projection:
    label: str
    expression: Name | Aggregate


@dataclass(frozen=True)
class Analysis:
    query: Query
    projections: tuple[Projection, ...]
    required_columns: tuple[str, ...]
    order: tuple[tuple[str, bool], ...]
    grouped: bool


def predicate_names(predicate: Predicate) -> Iterator[Name]:
    if isinstance(predicate, Comparison):
        for operand in (predicate.left, predicate.right):
            if isinstance(operand, Name):
                yield operand
    elif isinstance(predicate, NullTest):
        if isinstance(predicate.operand, Name):
            yield predicate.operand
    elif isinstance(predicate, Negation):
        yield from predicate_names(predicate.condition)
    else:
        for condition in predicate.conditions:
            yield from predicate_names(condition)


def semantic_error(name: Name, message: str) -> QueryError:
    return QueryError("семантическая", name.location, message)


def analyze(query: Query) -> Analysis:
    group_names: set[str] = set()
    for name in query.group_by:
        if name.key in group_names:
            raise semantic_error(name, f"Столбец {name.text!r} повторяется в GROUP BY.")
        group_names.add(name.key)

    items = query.items or ()
    grouped = bool(query.group_by) or any(isinstance(item.expression, Aggregate) for item in items)
    if query.items is None and grouped:
        raise QueryError("семантическая", query.location, "SELECT * несовместим с GROUP BY.")

    sources = list(query.group_by)
    if query.where is not None:
        sources.extend(predicate_names(query.where))
    labels: dict[str, str] = {}
    projections = []
    for item in items:
        expression = item.expression
        if isinstance(expression, Aggregate):
            if expression.column is None and expression.function != "COUNT":
                raise QueryError("семантическая", expression.location,
                                 "Аргумент * разрешён только для COUNT.")
            if expression.column is not None:
                sources.append(expression.column)
            default = Name(expression.function.lower(), expression.location)
        else:
            if grouped and expression.key not in group_names:
                raise semantic_error(expression, f"Столбец {expression.text!r} отсутствует в GROUP BY.")
            sources.append(expression)
            default = expression
        label = item.alias or default
        if label.key in labels:
            raise semantic_error(label, f"Повторяется имя результата {label.text!r}. Задайте AS.")
        labels[label.key] = label.text
        projections.append(Projection(label.text, expression))

    order = []
    for term in query.order_by:
        name = term.name
        if query.items is None:
            sources.append(name)
            key = name.key
        else:
            if name.key not in labels:
                raise semantic_error(name, f"Имя {name.text!r} отсутствует в списке SELECT.")
            key = labels[name.key]
        order.append((key, term.descending))

    seen_columns: dict[str, str] = {}
    for name in sources:
        seen_columns.setdefault(name.key, name.text)
    return Analysis(query, tuple(projections), tuple(seen_columns.values()), tuple(order), grouped)
