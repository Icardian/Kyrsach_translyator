# SQL2Py

Курсовой проект по дисциплине «Проектирование трансляторов».
SQL2Py 1.0.0 переводит запрос SELECT в код Python для обработки CSV и JSON.

Для исходников откройте PowerShell в папке Kyrsach_tr и выполните команды.
Нужен Python 3.10 или новее.

~~~powershell
python -m sql2py examples/summary.sql -o summary.py
python summary.py examples/orders.csv
python summary.py examples/orders.json
python -m unittest discover -s tests -v
~~~

В готовом комплекте Windows трансляция запускается командой
.\bin\sql2py.exe examples/summary.sql -o summary.py, а полученный скрипт можно
запустить через .\bin\runtime\python.exe.

- [Руководство пользователя](USER_GUIDE.md) описывает запуск и формат входных файлов.
- [Инструкция по сборке](BUILD.md) описывает инструменты, байткод и Windows-комплект.
- [Поддерживаемые конструкции SQL](LANGUAGE.md) объясняют правила обработки запроса.
- [Грамматика SQL](grammar/sql.g) задаёт синтаксис в EBNF.
- [Дамп запуска примера](verification/demo/commands.txt) указывает команды, выводы и результаты проверки.

## Структура

| Путь | Назначение |
| --- | --- |
| sql2py/ | Исходники лексера, парсера, семантического анализа и генератора |
| grammar/sql.g | Спецификация входного языка |
| tools/build.py и tools/native_launcher.c | Сборка и запуск исполняемого комплекта |
| examples/ | SQL-запросы, данные CSV и JSON, контрольные ответы и готовый пример Python |
| tests/ | Сквозные тесты |
| verification/ | Журналы проверок и дамп запуска |
| docs/ | Диаграммы из пояснительной записки |
