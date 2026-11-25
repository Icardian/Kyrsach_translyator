(* SQL2Py 1.0.0. Грамматика входного языка в EBNF.
   Синтаксический разбор методом рекурсивного спуска реализован в parser.py.
   Смысловые ограничения проверяются модулем semantic.py. *)

query        = "SELECT", select_list, "FROM", name,
               [ "WHERE", condition ],
               [ "GROUP", "BY", name, { ",", name } ],
               [ "ORDER", "BY", sort_key, { ",", sort_key } ],
               [ "LIMIT", unsigned_integer ], [ ";" ], EOF ;
select_list  = "*" | item, { ",", item } ;
item         = (name | aggregate), [ "AS", name ] ;
aggregate    = "COUNT", "(", ("*" | name), ")"
             | ("SUM" | "AVG" | "MIN" | "MAX"), "(", name, ")" ;
sort_key     = name, [ "ASC" | "DESC" ] ;
condition    = conjunction, { "OR", conjunction } ;
conjunction  = negation, { "AND", negation } ;
negation     = "NOT", negation | "(", condition, ")" | test ;
test         = operand, (comparison, operand | "IS", [ "NOT" ], "NULL") ;
comparison   = "=" | "!=" | "<>" | "<" | "<=" | ">" | ">=" ;
operand      = name | number | string | "TRUE" | "FALSE" | "NULL" ;

(* Пробелы и комментарии пропускаются лексером там, где допустима граница
   токена. Сопоставление ключевых слов нечувствительно к регистру.
   Сопоставление имён в данных использует Unicode casefold. *)

name             = unquoted_name | quoted_name ;
unquoted_name    = (letter | "_"), {letter | digit | "_"} ;
quoted_name      = '"', { ? символ кроме двойной кавычки ? | '""' }, '"' ;
string           = "'", { ? символ кроме одинарной кавычки ? | "''" }, "'" ;
number           = [sign], (unsigned_integer, [".", {digit}] | ".", unsigned_integer),
                   [("e" | "E"), [sign], unsigned_integer] ;
sign             = "+" | "-" ;
unsigned_integer = digit, {digit} ;
letter           = ? латинская буква ASCII A–Z или a–z ? ;
digit            = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
line_comment     = "--", { ? символ кроме конца строки ? } ;
block_comment    = "/*", ? текст до первого закрывающего маркера ?, "*/" ;
EOF              = ? конец исходного файла ? ;

(* Имена без кавычек исключают зарезервированные слова SQL2Py.
   Имена в кавычках содержат хотя бы один непробельный символ, управляющие
   коды ASCII исключаются. Число заканчивается перед символом, отличным
   от латинской буквы, цифры, точки или подчёркивания, либо в конце файла.
   Ограничения размеров и семантика описаны в LANGUAGE.md. *)
