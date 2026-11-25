"""Функции чтения таблиц и выполнения операций с данными."""

import argparse
import csv
import json
import math
import operator
import re
import statistics
import sys
import tempfile
from pathlib import Path


NUMBER_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
COMPARATORS = {
    "=": operator.eq, "!=": operator.ne, "<>": operator.ne,
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
}


class DataError(ValueError):
    """Ошибка формата таблицы или её обработки."""


def configure_console():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def same_file(first, second):
    if first.resolve() == second.resolve():
        return True
    try:
        return first.samefile(second)
    except FileNotFoundError:
        return False


def write_text_atomic(path, text):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(text)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def column_map(names):
    columns = {}
    for name in names:
        if not name.strip() or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise DataError(f"Недопустимое имя столбца {name!r}.")
        name.encode("utf-8")
        key = name.casefold()
        if key in columns:
            raise DataError(f"Имя столбца {name!r} повторяется.")
        columns[key] = name
    return columns


def data_number(text):
    if len(text) > 256:
        raise DataError("Число в данных длиннее 256 символов.")
    if any(char in text for char in ".eE"):
        value = float(text)
        if not math.isfinite(value):
            raise DataError(f"Число {text!r} вне допустимого диапазона.")
        return value
    return int(text)


def csv_value(text):
    if text == "":
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if NUMBER_PATTERN.fullmatch(text):
        return data_number(text)
    return text


def load_csv(path, delimiter):
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        header = next((fields for fields in reader if fields), None)
        if header is None:
            raise DataError("В CSV отсутствует строка заголовков.")
        columns = column_map(header)
        for fields in reader:
            if not fields:
                continue
            if len(fields) != len(columns):
                raise DataError(f"CSV, строка {reader.line_num}: ожидалось {len(columns)} полей, "
                                f"получено {len(fields)}.")
            try:
                rows.append(dict(zip(columns, map(csv_value, fields))))
            except DataError as error:
                raise DataError(f"CSV, строка {reader.line_num}: {error}") from error
    return columns, rows


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise DataError(f"Свойство JSON {name!r} повторяется.")
        result[name] = value
    return result


def reject_constant(text):
    raise DataError(f"JSON не допускает числовую константу {text!r}.")


def load_json(path):
    with path.open(encoding="utf-8-sig") as stream:
        data = json.load(stream, parse_int=data_number, parse_float=data_number,
                         parse_constant=reject_constant, object_pairs_hook=unique_object)
    if not isinstance(data, list):
        raise DataError("Ожидался JSON-массив объектов.")
    columns = {}
    rows = []
    for index, record in enumerate(data, start=1):
        if not isinstance(record, dict):
            raise DataError(f"JSON, запись {index}: ожидался объект.")
        names = column_map(record)
        row = {}
        for key, name in names.items():
            value = record[name]
            if isinstance(value, (dict, list)):
                raise DataError(f"JSON, запись {index}: поле {name!r} содержит вложенное значение.")
            if isinstance(value, str):
                value.encode("utf-8")
            columns.setdefault(key, name)
            row[key] = value
        rows.append(row)
    return columns, rows


def load_data(path, delimiter):
    extension = path.suffix.casefold()
    if extension == ".csv":
        separator = {None: ",", ",": ",", ";": ";", "tab": "\t"}[delimiter]
        return load_csv(path, separator)
    if extension == ".json":
        if delimiter is not None:
            raise DataError("Параметр --delimiter применяется к CSV.")
        return load_json(path)
    raise DataError(f"Ожидался файл .csv или .json, получено {path.name!r}.")


def require_columns(columns, required):
    missing = [name for name in required if name.casefold() not in columns]
    if missing:
        raise DataError("В таблице отсутствуют столбцы: " + ", ".join(map(repr, missing)) + ".")


def value_kind(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "логическое значение"
    if isinstance(value, (int, float)):
        return "число"
    return "строка"


def sql_compare(left, comparison, right):
    if left is None or right is None:
        return None
    if value_kind(left) != value_kind(right):
        raise DataError(f"Нельзя сравнить {left!r} и {right!r}: несовместимые типы.")
    return COMPARATORS[comparison](left, right)


def sql_not(value):
    return None if value is None else not value


def sql_and(*values):
    if False in values:
        return False
    if None in values:
        return None
    return True


def sql_or(*values):
    if True in values:
        return True
    if None in values:
        return None
    return False


def group_rows(rows, columns):
    groups = {}
    for row in rows:
        values = (row.get(column) for column in columns)
        # Метка типа отделяет логическое True от числа 1.
        key = tuple((value_kind(value), value) for value in values)
        groups.setdefault(key, []).append(row)
    return groups.values()


def non_null_values(rows, column):
    return [value for row in rows if (value := row.get(column)) is not None]


def sql_count(rows, column):
    return sum(row.get(column) is not None for row in rows)


def numeric_values(rows, column):
    values = non_null_values(rows, column)
    if any(value_kind(value) != "число" for value in values):
        raise DataError(f"SUM и AVG требуют числа в столбце {column!r}.")
    return values


def sql_sum(rows, column):
    values = numeric_values(rows, column)
    if not values:
        return None
    if all(isinstance(value, int) for value in values):
        return sum(values)
    return math.fsum(values)


def sql_avg(rows, column):
    values = numeric_values(rows, column)
    return statistics.mean(values) if values else None


def require_comparable(values, column):
    if len({value_kind(value) for value in values}) > 1:
        raise DataError(f"Столбец {column!r} содержит несравнимые типы.")


def sql_min(rows, column):
    values = non_null_values(rows, column)
    require_comparable(values, column)
    return min(values, default=None)


def sql_max(rows, column):
    values = non_null_values(rows, column)
    require_comparable(values, column)
    return max(values, default=None)


def sort_rows(rows, order):
    for column, descending in reversed(order):
        present = []
        missing = []
        for row in rows:
            (missing if row.get(column) is None else present).append(row)
        require_comparable((row[column] for row in present), column)
        present.sort(key=operator.itemgetter(column), reverse=descending)
        rows = present + missing
    return rows


def run_program(table_name, execute_query, argv=None):
    configure_console()
    parser = argparse.ArgumentParser(description=f"Выполнить запрос к таблице {table_name!r}.")
    parser.add_argument("data", type=Path, help="Путь к файлу CSV или JSON.")
    parser.add_argument("--table", help="Логическое имя таблицы. По умолчанию имя файла без расширения.")
    parser.add_argument("--delimiter", choices=(",", ";", "tab"), help="Разделитель CSV. По умолчанию запятая.")
    parser.add_argument("-o", "--output", type=Path, help="Записать результат в указанный JSON-файл.")
    args = parser.parse_args(argv)
    try:
        name = args.data.stem if args.table is None else args.table
        if name.casefold() != table_name.casefold():
            raise DataError(f"В FROM указана таблица {table_name!r}, получено имя {name!r}. "
                            "Укажите логическое имя через --table.")
        if args.output is not None:
            if same_file(args.data, args.output) or same_file(Path(__file__), args.output):
                raise DataError("Файл результата должен отличаться от файла данных и кода программы.")
        columns, rows = load_data(args.data, args.delimiter)
        result = execute_query(columns, rows)
        text = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(text)
        else:
            write_text_atomic(args.output, text)
    except (ValueError, OSError, ArithmeticError, csv.Error, RuntimeError) as error:
        print(f"Ошибка выполнения ({args.data}): {error}", file=sys.stderr)
        return 1
    return 0


# Код запроса
TABLE_NAME = 'orders'


def execute_query(columns, rows):
    require_columns(columns, ('city', 'status', 'amount'))
    rows = [
        row for row in rows
        if (sql_compare(row.get('status'), '=', 'paid')) is True
    ]
    groups = group_rows(rows, ('city',))
    rows = [
        {
            'city': group[0].get('city'),
            'orders': len(group),
            'priced': sql_count(group, 'amount'),
            'total': sql_sum(group, 'amount'),
            'average': sql_avg(group, 'amount'),
        }
        for group in groups
    ]
    rows = sort_rows(rows, (('total', True), ('city', False)))
    return rows[:3]


if __name__ == "__main__":
    raise SystemExit(run_program(TABLE_NAME, execute_query))
