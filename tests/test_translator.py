"""Сквозные проверки командной строки, генерации и результата."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class TranslatorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name)
        self.program = self.work / "результат.py"
        self.query = self.work / "запрос.sql"

    def invoke(self, *arguments, cwd=ROOT):
        return subprocess.run(
            [sys.executable, *map(str, arguments)], cwd=cwd, capture_output=True,
            encoding="utf-8", timeout=15, check=False,
        )

    def translate(self, source):
        self.query.write_text(source, encoding="utf-8")
        return self.invoke("-m", "sql2py", self.query, "-o", self.program)

    def build(self, source):
        result = self.translate(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.program.is_file())

    def execute(self, data, *arguments):
        # Изолированный запуск не использует пакет sql2py из каталога проекта.
        return self.invoke("-I", self.program, data, *arguments, cwd=self.work)

    def result(self, data, *arguments):
        result = self.execute(data, *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def fixture(self, name, text, encoding="utf-8"):
        data = self.work / name
        data.write_bytes(text.encode(encoding))
        return data

    def test_summary_csv_json_and_expected(self):
        self.build((EXAMPLES / "summary.sql").read_text(encoding="utf-8"))
        expected = json.loads((EXAMPLES / "summary_expected.json").read_text(encoding="utf-8"))
        self.assertEqual(self.result(EXAMPLES / "orders.csv"), expected)
        self.assertEqual(self.result(EXAMPLES / "orders.json"), expected)

    def test_selection_csv_json_and_expected(self):
        self.build((EXAMPLES / "selection.sql").read_text(encoding="utf-8"))
        expected = json.loads((EXAMPLES / "selection_expected.json").read_text(encoding="utf-8"))
        self.assertEqual(self.result(EXAMPLES / "orders.csv"), expected)
        self.assertEqual(self.result(EXAMPLES / "orders.json"), expected)

    def test_generated_code_contains_query_operations(self):
        self.build("SELECT SUM(amount) AS total FROM orders WHERE paid = TRUE LIMIT 1;")
        text = self.program.read_text(encoding="utf-8")
        self.assertIn("def execute_query(columns, rows):", text)
        self.assertIn("sql_compare(row.get('paid'), '=', True)", text)
        self.assertIn("sql_sum(group, 'amount')", text)
        self.assertIn("return rows[:1]", text)
        self.assertNotIn("FROM orders", text)

    def test_global_aggregates_and_null_counting(self):
        self.build("SELECT COUNT(*) AS n, COUNT(amount) AS m, SUM(amount) AS s, "
                   "AVG(amount) AS a, MIN(amount) AS lo, MAX(amount) AS hi FROM orders;")
        expected = [{"n": 9, "m": 8, "s": 800.0, "a": 100.0, "lo": 40, "hi": 190}]
        self.assertEqual(self.result(EXAMPLES / "orders.json"), expected)

    def test_empty_filtered_aggregate(self):
        self.build("SELECT COUNT(*) AS n, COUNT(amount) AS m, SUM(amount) AS total, "
                   "AVG(amount) AS average, MIN(amount) AS lo, MAX(amount) AS hi "
                   "FROM orders WHERE id < 0;")
        expected = [{"n": 0, "m": 0, "total": None, "average": None, "lo": None, "hi": None}]
        self.assertEqual(self.result(EXAMPLES / "orders.csv"), expected)

    def test_empty_filtered_group(self):
        self.build("SELECT city, COUNT(*) AS n FROM orders WHERE id < 0 GROUP BY city;")
        self.assertEqual(self.result(EXAMPLES / "orders.csv"), [])

    def test_multiple_group_fields_and_missing_value(self):
        self.build("SELECT city, status, COUNT(*) AS n, SUM(amount) AS total "
                   "FROM orders GROUP BY city, status ORDER BY status, city;")
        self.assertEqual(self.result(EXAMPLES / "orders.json"), [
            {"city": "Москва", "status": "cancelled", "n": 1, "total": 190},
            {"city": "Казань", "status": "paid", "n": 2, "total": 125},
            {"city": "Москва", "status": "paid", "n": 2, "total": 250.0},
            {"city": "Пермь", "status": "paid", "n": 3, "total": 90},
            {"city": "Казань", "status": "pending", "n": 1, "total": 145},
        ])

    def test_group_without_aggregates(self):
        self.build("SELECT city FROM orders GROUP BY city ORDER BY city;")
        self.assertEqual(self.result(EXAMPLES / "orders.json"),
                         [{"city": "Казань"}, {"city": "Москва"}, {"city": "Пермь"}])

    def test_group_null_keys_and_distinct_value_kinds(self):
        self.build("SELECT x, COUNT(*) AS n FROM data GROUP BY x;")
        data = self.fixture("data.json", '[{"x": true}, {"x": 1}, {"x": 1.0}, {}, {"x": null}]')
        output = self.result(data)
        self.assertEqual([record["n"] for record in output], [1, 2, 2])
        self.assertIs(output[0]["x"], True)
        self.assertIs(type(output[1]["x"]), int)
        self.assertIsNone(output[2]["x"])

    def test_null_in_not_and_comparison(self):
        self.build("SELECT id FROM orders WHERE NOT amount = 50 AND id >= 4 ORDER BY id;")
        self.assertEqual(self.result(EXAMPLES / "orders.json"), [{"id": 6}, {"id": 7}, {"id": 8}])

    def test_boolean_precedence_and_null_test(self):
        self.build("SELECT id FROM orders WHERE id = 1 OR id = 5 AND NOT amount IS NOT NULL;")
        self.assertEqual(self.result(EXAMPLES / "orders.csv"), [{"id": 1}, {"id": 5}])

    def test_unknown_with_true_or_false_and(self):
        self.build("SELECT id FROM orders WHERE (amount = NULL OR id = 5) "
                   "AND NOT (amount = NULL AND id = 0);")
        self.assertEqual(self.result(EXAMPLES / "orders.json"), [{"id": 5}])

    def test_string_escaping_and_numeric_literal(self):
        self.build("SELECT id FROM orders WHERE customer = 'О''Брайен' AND amount >= +1.2e2")
        self.assertEqual(self.result(EXAMPLES / "orders.csv"), [{"id": 6}])

    def test_csv_quotes_embedded_newline_and_text_code(self):
        data = self.fixture("data.csv", 'code,text,amount\r\n001,"Б, В\r\nГ",\r\n')
        self.build("SELECT * FROM data WHERE code = '001';")
        self.assertEqual(self.result(data), [{"code": "001", "text": "Б, В\r\nГ", "amount": None}])

    def test_casefold_quoted_names_bom_and_semicolon_delimiter(self):
        data = self.fixture("Мои заказы.csv", 'Город;"A""B"\r\nМосква;1\r\n', "utf-8-sig")
        # Кавычки в идентификаторе удваиваются и сохраняются в имени результата.
        self.query.write_bytes(
            ('/* отчёт */\r\nsElEcT "ГОРОД" AS "Населённый пункт" FROM "таблица = 1" '
             'WHERE "a""b" = 1 -- условие\r\n;').encode("utf-8-sig")
        )
        result = self.invoke("-m", "sql2py", self.query, "-o", self.program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.result(data, "--table", "Таблица = 1", "--delimiter", ";"),
                         [{"Населённый пункт": "Москва"}])

    def test_schema_union_and_star_preserves_display_names(self):
        data = self.fixture("data.json", '[{"ID": 1}, {"id": 2, "city": "Пермь"}]')
        self.build("SELECT * FROM data ORDER BY CITY DESC;")
        self.assertEqual(self.result(data),
                         [{"ID": 2, "city": "Пермь"}, {"ID": 1, "city": None}])

    def test_sort_secondary_key_and_nulls_last(self):
        data = self.fixture("data.json", '[{"id": 1, "x": 2}, {"id": 2, "x": 2}, {"id": 3}, '
                                           '{"id": 4, "x": 1}, {"id": 5}]')
        self.build("SELECT id, x AS y FROM data ORDER BY Y ASC, id DESC;")
        self.assertEqual([row["id"] for row in self.result(data)], [4, 2, 1, 5, 3])

    def test_empty_json_and_limit_zero(self):
        data = self.fixture("data.json", "[]")
        self.build('SELECT COUNT(*) FROM data ORDER BY "count";')
        self.assertEqual(self.result(data), [{"count": 0}])
        self.build("SELECT * FROM data;")
        self.assertEqual(self.result(data), [])
        self.build("SELECT * FROM orders LIMIT 0;")
        self.assertEqual(self.result(EXAMPLES / "orders.csv"), [])

    def test_header_only_csv_known_columns(self):
        data = self.fixture("data.csv", "id,amount\n")
        self.build("SELECT SUM(amount) AS total, COUNT(id) AS n FROM data;")
        self.assertEqual(self.result(data), [{"total": None, "n": 0}])

    def test_lexical_diagnostic_position(self):
        result = self.translate("SELECT id\nFROM orders\nWHERE @id = 1;")
        self.assertEqual(result.returncode, 1)
        self.assertIn(":3:7: лексическая ошибка:", result.stderr)
        self.assertFalse(self.program.exists())

    def test_syntax_failures(self):
        cases = ["SELECT id FROM orders WHERE (id = 1;", "SELECT id FROM orders LIMIT -1;",
                 "SELECT id FROM orders LIMIT 2.5;", "SELECT id FROM orders; SELECT id FROM orders;",
                 "DELETE FROM orders;", "SELECT id FROM orders WHERE id;"]
        for source in cases:
            with self.subTest(source=source):
                result = self.translate(source)
                self.assertEqual(result.returncode, 1)
                self.assertIn("синтаксическая ошибка", result.stderr)
                self.assertFalse(self.program.exists())

    def test_semantic_failures_preserve_existing_output(self):
        self.program.write_text("previous result", encoding="utf-8")
        cases = ["SELECT city, SUM(amount) FROM orders;", "SELECT SUM(*) FROM orders;",
                 "SELECT id AS x, city AS X FROM orders;", "SELECT id FROM orders ORDER BY city;",
                 "SELECT * FROM orders GROUP BY city;", "SELECT city FROM orders GROUP BY city, CITY;"]
        for source in cases:
            with self.subTest(source=source):
                result = self.translate(source)
                self.assertEqual(result.returncode, 1)
                self.assertIn("семантическая ошибка", result.stderr)
                self.assertEqual(self.program.read_text(encoding="utf-8"), "previous result")

    def test_limits_for_nesting_tokens_and_file_size(self):
        cases = [
            ("SELECT id FROM orders WHERE " + "(" * 33 + "id = 1" + ")" * 33, 1, "Вложенность"),
            ("SELECT id FROM orders WHERE " + " AND ".join(["id = 1"] * 1100), 1, "лексем"),
            (" " * (256 * 1024 + 1), 3, "256 КиБ"),
        ]
        for source, expected, message in cases:
            with self.subTest(expected=expected, message=message):
                result = self.translate(source)
                self.assertEqual(result.returncode, expected)
                self.assertIn(message, result.stderr)

    def test_lexical_failures_on_unclosed_text(self):
        for text in ("/* открытый комментарий", "SELECT id FROM orders WHERE city = 'Москва"):
            with self.subTest(text=text):
                result = self.translate(text)
                self.assertEqual(result.returncode, 1)
                self.assertIn("лексическая ошибка", result.stderr)

    def test_missing_input_column_at_runtime(self):
        self.build("SELECT nonexistent FROM orders;")
        result = self.execute(EXAMPLES / "orders.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("'nonexistent'", result.stderr)
        self.assertIn("отсутствуют столбцы", result.stderr)
        self.assertFalse(result.stdout)

    def test_wrong_table_can_be_bound_explicitly(self):
        self.build("SELECT id FROM warehouse LIMIT 1;")
        result = self.execute(EXAMPLES / "orders.csv")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--table", result.stderr)
        self.assertEqual(self.result(EXAMPLES / "orders.csv", "--table", "WAREHOUSE"), [{"id": 1}])

    def test_invalid_csv_data(self):
        self.build("SELECT * FROM data;")
        cases = [("a,b\n1\n", "ожидалось 2 полей"), ("x,X\n1,2\n", "повторяется"),
                 ("", "отсутствует строка заголовков"), ('a,b\n1,"oops\n', "Ошибка выполнения")]
        for text, message in cases:
            with self.subTest(text=text):
                result = self.execute(self.fixture("data.csv", text))
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertFalse(result.stdout)

    def test_invalid_json_data(self):
        self.build("SELECT * FROM data;")
        cases = [
            ('{"x": 1}', "массив объектов"),
            ('[1]', "ожидался объект"),
            ('[{"x": [1]}]', "вложенное значение"),
            ('[{"x": 1, "x": 2}]', "повторяется"),
            ('[{"x": 1, "X": 2}]', "повторяется"),
            ('[{"x": NaN}]', "числовую константу"),
            ('[{"x": 1e999}]', "вне допустимого диапазона"),
            ('[{"x": 1}', "Ошибка выполнения"),
        ]
        for text, message in cases:
            with self.subTest(text=text):
                result = self.execute(self.fixture("data.json", text))
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertFalse(result.stdout)

    def test_type_mismatch_in_filters_sorting_and_aggregates(self):
        data = self.fixture("data.json", '[{"x": 1}, {"x": "текст"}]')
        cases = [
            ("SELECT x FROM data WHERE x >= 0;", "несовместимые типы"),
            ("SELECT x FROM data ORDER BY x;", "несравнимые типы"),
            ("SELECT SUM(x) FROM data;", "требуют числа"),
            ("SELECT MAX(x) FROM data;", "несравнимые типы"),
        ]
        for source, message in cases:
            with self.subTest(source=source):
                self.build(source)
                result = self.execute(data)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)

    def test_failed_result_write_does_not_touch_input_or_existing_output(self):
        data = self.fixture("data.csv", "x\n1\n")
        output = self.fixture("existing.json", "original")
        self.build("SELECT missing FROM data;")
        result = self.execute(data, "-o", output)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(output.read_text(encoding="utf-8"), "original")
        self.build("SELECT x FROM data;")
        result = self.execute(data, "-o", data)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(data.read_text(encoding="utf-8"), "x\n1\n")
        before = self.program.read_bytes()
        result = self.execute(data, "-o", self.program)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.program.read_bytes(), before)

    def test_save_json_output_replaces_previous_result(self):
        self.build("SELECT id FROM orders ORDER BY id DESC LIMIT 1;")
        output = self.fixture("мой ответ.json", "previous")
        result = self.execute(EXAMPLES / "orders.csv", "-o", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result.stdout)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), [{"id": 9}])
        self.assertEqual(set(self.work.iterdir()), {self.program, self.query, output})

    def test_translator_file_errors_and_cli_exit_codes(self):
        result = self.invoke("-m", "sql2py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Файл с одним запросом SELECT", result.stderr)
        self.assertIn("-o OUTPUT", result.stderr)
        result = self.invoke("-m", "sql2py", self.query, "-o", self.program)
        self.assertEqual(result.returncode, 3)
        self.query.write_text("SELECT * FROM orders;", encoding="utf-8")
        result = self.invoke("-m", "sql2py", self.query, "-o", self.query)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(self.query.read_text(encoding="utf-8"), "SELECT * FROM orders;")
        result = self.invoke("-m", "sql2py", self.query, "-o", self.work / "missing" / "out.py")
        self.assertEqual(result.returncode, 3)
        result = self.invoke("-m", "sql2py", "--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "SQL2Py 1.0.0")

    def test_packaged_bytecode_translates_without_source_package(self):
        package = self.work / "package"
        build = self.invoke("tools/build.py", "--output", package)
        self.assertEqual(build.returncode, 0, build.stderr)
        archive = package / "bin" / "sql2py.pyz"
        usage = self.invoke("-I", archive, cwd=self.work)
        self.assertEqual(usage.returncode, 2, usage.stderr)
        self.assertIn("sql2py.exe", usage.stderr)
        result = self.invoke("-I", archive, EXAMPLES / "summary.sql",
                             "-o", self.program, cwd=self.work)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = json.loads((EXAMPLES / "summary_expected.json").read_text(encoding="utf-8"))
        self.assertEqual(self.result(EXAMPLES / "orders.json"), expected)

    def test_runtime_cli_errors(self):
        self.build("SELECT * FROM orders;")
        result = self.invoke("-I", self.program, cwd=self.work)
        self.assertEqual(result.returncode, 2)
        result = self.execute(EXAMPLES / "orders.json", "--delimiter", ";")
        self.assertEqual(result.returncode, 1)
        self.assertIn("применяется к CSV", result.stderr)
        result = self.execute(self.work / "orders.txt")
        self.assertEqual(result.returncode, 1)
        self.assertIn(".csv или .json", result.stderr)

    def test_hard_link_output_cannot_replace_input(self):
        self.query.write_text("SELECT * FROM orders;", encoding="utf-8")
        try:
            os.link(self.query, self.program)
        except OSError as error:
            self.skipTest(f"Жёсткие ссылки недоступны: {error}")
        result = self.invoke("-m", "sql2py", self.query, "-o", self.program)
        self.assertEqual(result.returncode, 3)
        self.assertIn("должны различаться", result.stderr)


if __name__ == "__main__":
    unittest.main()
