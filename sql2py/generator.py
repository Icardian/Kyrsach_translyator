"""Генерация автономного Python-модуля для конкретного SQL-запроса."""

from importlib.resources import files

from .model import Aggregate, Comparison, Name, Negation, NullTest, Operand, Predicate
from .semantic import Analysis


def operand_code(operand: Operand) -> str:
    if isinstance(operand, Name):
        return f"row.get({operand.key!r})"
    return repr(operand.value)


def predicate_code(predicate: Predicate) -> str:
    if isinstance(predicate, Comparison):
        left, right = operand_code(predicate.left), operand_code(predicate.right)
        return f"sql_compare({left}, {predicate.operator!r}, {right})"
    if isinstance(predicate, NullTest):
        operator = "is not" if predicate.negated else "is"
        return f"{operand_code(predicate.operand)} {operator} None"
    if isinstance(predicate, Negation):
        return f"sql_not({predicate_code(predicate.condition)})"
    conditions = ", ".join(predicate_code(condition) for condition in predicate.conditions)
    return f"sql_{predicate.operator.lower()}({conditions})"


def projection_code(expression: Name | Aggregate, grouped: bool) -> str:
    if isinstance(expression, Name):
        source = "group[0]" if grouped else "row"
        return f"{source}.get({expression.key!r})"
    if expression.column is None:
        return "len(group)"
    return f"sql_{expression.function.lower()}(group, {expression.column.key!r})"


def generate(analysis: Analysis) -> str:
    query = analysis.query
    lines = [
        "# Код запроса",
        f"TABLE_NAME = {query.table.text!r}",
        "",
        "",
        "def execute_query(columns, rows):",
        f"    require_columns(columns, {analysis.required_columns!r})",
    ]
    if query.where is not None:
        condition = predicate_code(query.where)
        lines.extend([
            "    rows = [",
            "        row for row in rows",
            f"        if ({condition}) is True",
            "    ]",
        ])

    source = "for row in rows"
    if query.group_by:
        keys = tuple(name.key for name in query.group_by)
        lines.append(f"    groups = group_rows(rows, {keys!r})")
        source = "for group in groups"
    elif analysis.grouped:
        lines.append("    groups = [rows]")
        source = "for group in groups"

    if query.items is None:
        if analysis.order:
            lines.append(f"    rows = sort_rows(rows, {analysis.order!r})")
        lines.append("    rows = [{label: row.get(key) for key, label in columns.items()} for row in rows]")
    else:
        lines.append("    rows = [")
        lines.append("        {")
        for projection in analysis.projections:
            value = projection_code(projection.expression, analysis.grouped)
            lines.append(f"            {projection.label!r}: {value},")
        lines.extend(["        }", f"        {source}", "    ]"])
        if analysis.order:
            lines.append(f"    rows = sort_rows(rows, {analysis.order!r})")

    result = "rows" if query.limit is None else f"rows[:{query.limit}]"
    lines.extend([
        f"    return {result}",
        "",
        "",
        'if __name__ == "__main__":',
        "    raise SystemExit(run_program(TABLE_NAME, execute_query))",
    ])
    runtime = files(__package__).joinpath("runtime.py").read_text(encoding="utf-8")
    return runtime.rstrip() + "\n\n\n" + "\n".join(lines) + "\n"
