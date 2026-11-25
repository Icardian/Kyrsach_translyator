# Сборка SQL2Py

## Запуск и проверка исходников

Для исходников достаточно CPython 3.10 или новее и стандартной библиотеки.
Выполните команды из корня Kyrsach_tr.

~~~powershell
python -m sql2py --help
python -m sql2py examples/summary.sql -o summary.py
python summary.py examples/orders.csv
python -m unittest discover -s tests -v
~~~

Синтаксические правила описаны в grammar/sql.g и вручную реализованы
в sql2py/lexer.py и sql2py/parser.py.

## Компиляция Python-модулей

~~~powershell
python tools/build.py --output dist-bytecode
python -I dist-bytecode/bin/sql2py.pyz --version
~~~

В sql2py.pyz находятся файлы .pyc, полученные компиляцией Python-модулей.
Для запуска нужен CPython той же версии 3.x, на которой выполнена сборка.
В архив включён исходный текст runtime.py, который генератор вставляет в
создаваемые скрипты.

## Сборка комплекта Windows x64

Нужны CPython 3.12 и ZIP встраиваемой поставки CPython 3.12 x64. Для сборки
под Windows установите MinGW-w64 и проверьте, что в PATH есть
x86_64-w64-mingw32-gcc. На Linux x86-64 скрипт поддерживает GCC и GNU binutils
с PE-линкером i386pep. Для самостоятельной сборки на странице релиза
выберите Windows embeddable package (64-bit).
[Пакет CPython 3.12.10](https://www.python.org/downloads/release/python-31210/).

~~~powershell
python tools/build.py --windows-runtime "C:\path\python-3.12.10-embed-amd64.zip" --output dist-win
~~~

Команда компилирует Python-модули в sql2py.pyz, собирает sql2py.exe из
tools/native_launcher.c и помещает CPython со стандартной библиотекой в
bin/runtime. Нативный файл загружает python312.dll и запускает SQL2Py через
C-функцию Py_Main. Комплект использует библиотеки Win32 из Windows 10/11 и
встроенный CPython. ZIP должен содержать файлы интерпретатора в корне.
При повторной сборке укажите новый путь --output или переместите прошлый
результат.

На Windows проверка при сборке запускает sql2py.exe. При сборке под Linux
скрипт проверяет байткод sql2py.pyz на локальном CPython 3.12. В обоих случаях
проверяются выдача справки, перевод примера, чтение CSV и JSON и диагностика.
Выводы записываются в verification/demo внутри каталога сборки.

Готовый комплект рассчитан на Windows 10/11 x64. Для поставки использована
среда CPython 3.12.14 x64 из предоставленного примера TableScript. Её файлы
сверены с манифестом примера. Лицензия находится в bin/runtime/LICENSE.txt.
Транслятор SQL2Py, пусковой файл sql2py.exe и сборка sql2py.pyz разработаны
для этой работы. Пусковой файл проверен в Linux с моделированием вызовов
Win32. Журнал находится в verification/windows-launcher.txt.

## Docker

С Docker можно запустить ту же проверку и исходную программу. Базовый образ
python:3.12-slim требуется Docker при первой сборке.

~~~powershell
docker build -t sql2py:1.0.0 .
docker run --rm -v "${PWD}:/work" sql2py:1.0.0 examples/summary.sql -o summary.py
docker run --rm -v "${PWD}:/work" --entrypoint python sql2py:1.0.0 summary.py examples/orders.csv
~~~
