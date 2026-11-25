"""Командная строка транслятора: python -m sql2py."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .generator import generate
from .model import QueryError
from .parser import parse
from .runtime import configure_console, same_file, write_text_atomic
from .semantic import analyze


MAX_QUERY_BYTES = 256 * 1024


class TranslatorArguments(argparse.ArgumentParser):
    def error(self, message):
        self.print_help(sys.stderr)
        self.exit(2, f"\nОшибка аргументов: {message}\n")


def read_query(path: Path) -> str:
    with path.open("rb") as stream:
        content = stream.read(MAX_QUERY_BYTES + 1)
    if len(content) > MAX_QUERY_BYTES:
        raise ValueError("Размер SQL-файла превышает 256 КиБ.")
    text = content.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def main(argv=None, *, prog="python -m sql2py") -> int:
    configure_console()
    parser = TranslatorArguments(
        prog=prog,
        description="Трансляция SQL-запроса в автономный Python-скрипт.",
    )
    parser.add_argument("query", type=Path, help="Файл с одним запросом SELECT в UTF-8.")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Путь для создания файла Python.")
    parser.add_argument("--version", action="version", version=f"SQL2Py {__version__}")
    args = parser.parse_args(argv)

    try:
        if same_file(args.query, args.output):
            raise ValueError("Входной и выходной файлы должны различаться.")
        query = parse(read_query(args.query))
        python_source = generate(analyze(query))
        compile(python_source, str(args.output), "exec")
        write_text_atomic(args.output, python_source)
    except QueryError as error:
        position = error.location
        print(f"{args.query}:{position.line}:{position.column}: {error.phase} ошибка: {error}",
              file=sys.stderr)
        return 1
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Ошибка транслятора ({args.query}): {error}", file=sys.stderr)
        return 3
    print(f"Трансляция завершена: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
