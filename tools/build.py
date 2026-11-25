"""Сборка байткода SQL2Py и исполняемого комплекта Windows x64."""

import argparse
import json
import platform
import py_compile
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "native_launcher.c"
IMPORTS = {
    "KERNEL32.dll": (
        "GetModuleFileNameW", "GetCommandLineW", "LoadLibraryExW",
        "GetProcAddress", "GetStdHandle", "WriteFile", "GetProcessHeap",
        "HeapAlloc", "HeapFree", "LocalFree", "ExitProcess",
    ),
    "SHELL32.dll": ("CommandLineToArgvW",),
}
COMPILER_FLAGS = (
    "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
    "-fno-builtin", "-fno-stack-protector", "-fno-asynchronous-unwind-tables",
    "-fno-unwind-tables", "-mno-red-zone",
)
RUNTIME_FILES = ("python.exe", "python312.dll", "python312.zip", "LICENSE.txt")


def build_bytecode(destination, scratch):
    entry = scratch / "__main__.py"
    entry.write_text(
        'from sql2py.__main__ import main\n'
        'raise SystemExit(main(prog="sql2py.exe"))\n',
        encoding="utf-8",
    )
    inputs = [(entry, "__main__.py")]
    inputs.extend((path, "sql2py/" + path.name)
                  for path in sorted((ROOT / "sql2py").glob("*.py")))

    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for source, name in inputs:
            compiled = scratch / "compiled.pyc"
            py_compile.compile(
                str(source), cfile=str(compiled), dfile=name, doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            )
            archive.writestr(name + "c", compiled.read_bytes())
        archive.write(ROOT / "sql2py" / "runtime.py", "sql2py/runtime.py")


def copy_runtime(source, destination):
    destination.mkdir()
    with ZipFile(source) as runtime:
        for member in runtime.infolist():
            path = PurePosixPath(member.filename)
            if (not path.parts or path.is_absolute() or ".." in path.parts or
                    any("\\" in part or ":" in part for part in path.parts)):
                raise ValueError(f"Некорректный путь в ZIP среды Python: {member.filename!r}")
            if member.is_dir():
                continue
            if len(path.parts) != 1 and not (
                len(path.parts) == 2 and path.parts[0] == "DLLs"
            ):
                raise ValueError("Поместите файлы встраиваемого Python в корень ZIP.")
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(exist_ok=True)
            with runtime.open(member) as incoming, target.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)

    for name in RUNTIME_FILES:
        if not (destination / name).is_file():
            raise ValueError(f"В комплекте среды отсутствует {name}.")
    for name in ("python.exe", "python312.dll"):
        code = (destination / name).read_bytes()
        offset = int.from_bytes(code[60:64], "little")
        if (code[:2] != b"MZ" or code[offset:offset+4] != b"PE\0\0" or
                code[offset+4:offset+6] != b"\x64\x86"):
            raise ValueError(f"Требуется версия {name} для Windows x64.")
    (destination / "python312._pth").write_text(
        "python312.zip\nDLLs\n.\n", encoding="ascii", newline="\n"
    )


def run(*arguments, cwd=None):
    subprocess.run([str(arg) for arg in arguments], cwd=cwd, check=True)


def compile_linux_object(source, target):
    run("gcc", *COMPILER_FLAGS, "-fno-pie", "-fno-pic", "-mcmodel=large",
        "-fshort-wchar", "-c", source, "-o", target)
    run("objcopy", "-R", ".comment", "-R", ".note.GNU-stack", target)


def build_windows_launcher(destination, scratch):
    mingw = shutil.which("x86_64-w64-mingw32-gcc")
    if mingw:
        run(mingw, *COMPILER_FLAGS, "-nostdlib", "-s",
            "-Wl,--subsystem,console,--entry,mainCRTStartup",
            LAUNCHER, "-lkernel32", "-lshell32", "-o", destination)
        return
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise ValueError("Для сборки нужен x86_64-w64-mingw32-gcc или GNU binutils на Linux x86-64.")

    # The import libraries describe Windows system exports to the linker.
    # The temporary DLL stubs are used only during the build.
    for library, names in IMPORTS.items():
        stem = library.removesuffix(".dll").lower()
        stub = scratch / f"{stem}.c"
        stub.write_text("".join(f"void {name}(void) {{}}\n" for name in names), encoding="ascii")
        definitions = scratch / f"{stem}.def"
        definitions.write_text(f"LIBRARY {library}\nEXPORTS\n    " +
                               "\n    ".join(names) + "\n", encoding="ascii")
        obj = scratch / f"{stem}.o"
        compile_linux_object(stub, obj)
        run("ld", "-m", "i386pep", "-shared", "-e", "0",
            "--out-implib", scratch / f"lib{stem}.a", "-o", scratch / f"{stem}.dll",
            obj, definitions)

    obj = scratch / "launcher.o"
    compile_linux_object(LAUNCHER, obj)
    run("ld", "-m", "i386pep", "--subsystem", "console", "-e", "mainCRTStartup",
        "-s", "-o", destination, obj, "-L", scratch, "-lkernel32", "-lshell32")


def capture_demo(package):
    directory = package / "verification" / "demo"
    directory.mkdir(parents=True)
    if sys.platform == "win32":
        translator = [str(package / "bin" / "sql2py.exe")]
        interpreter = [str(package / "bin" / "runtime" / "python.exe"), "-I"]
    else:
        interpreter = [sys.executable, "-I"]
        translator = [*interpreter, "bin/sql2py.pyz"]
    program = "verification/demo/summary.py"
    commands = (
        ("version", 0, [*translator, "--version"]),
        ("usage", 2, translator),
        ("translation", 0, [*translator, "examples/summary.sql", "-o", program]),
        ("csv", 0, [*interpreter, program, "examples/orders.csv"]),
        ("json", 0, [*interpreter, program, "examples/orders.json"]),
        ("invalid", 1, [*translator, "examples/invalid.sql", "-o", "verification/demo/invalid.py"]),
    )
    expected = json.loads((package / "examples" / "summary_expected.json").read_text(encoding="utf-8"))
    description = [
        f"Платформа проверки: {platform.system()} {platform.machine()}.",
        f"Интерпретатор сборки: CPython {platform.python_version()}.",
        "Входные файлы: examples/summary.sql, examples/orders.csv, examples/orders.json и examples/invalid.sql.",
        "stdout.txt содержит стандартный вывод, stderr.txt содержит диагностику.",
        "",
    ]
    for name, returncode, command in commands:
        result = subprocess.run(command, cwd=package, capture_output=True, check=False, timeout=30)
        (directory / f"{name}.stdout.txt").write_bytes(result.stdout)
        (directory / f"{name}.stderr.txt").write_bytes(result.stderr)
        if result.returncode != returncode:
            raise ValueError(f"Проверка {name} завершилась кодом {result.returncode}: "
                             + result.stderr.decode("utf-8", errors="replace").strip())
        if name == "usage" and b"-o OUTPUT" not in result.stderr:
            raise ValueError("При запуске без аргументов отсутствует краткая справка.")
        if name in ("csv", "json") and json.loads(result.stdout) != expected:
            raise ValueError(f"Результат {name} отличается от контрольного ответа.")
        if sys.platform == "win32":
            relative = str(Path(command[0]).relative_to(package))
            display = subprocess.list2cmdline([".\\" + relative, *command[1:]])
        else:
            display = shlex.join(command)
        description.append(f"{name} (код {result.returncode})  {display}")
    (directory / "commands.txt").write_text("\n".join(description) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist",
                        help="Новый каталог для результата сборки.")
    parser.add_argument("--windows-runtime", type=Path,
                        help="ZIP с встраиваемым CPython 3.12 для Windows x64.")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.windows_runtime and (platform.python_implementation() != "CPython" or
                                 sys.version_info[:2] != (3, 12)):
        parser.error("Для Windows-комплекта запустите сборку на CPython 3.12.")
    if output.exists():
        parser.error("Каталог результата существует. Укажите новый путь в --output.")

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as work:
            scratch = Path(work)
            staging = scratch / "package"
            bin_dir = staging / "bin"
            bin_dir.mkdir(parents=True)
            build_bytecode(bin_dir / "sql2py.pyz", scratch)
            if args.windows_runtime:
                copy_runtime(args.windows_runtime.resolve(), bin_dir / "runtime")
                build_windows_launcher(bin_dir / "sql2py.exe", scratch)
                shutil.copy2(ROOT / "USER_GUIDE.md", staging)
                shutil.copy2(ROOT / "LANGUAGE.md", staging)
                shutil.copytree(ROOT / "grammar", staging / "grammar")
                shutil.copytree(ROOT / "examples", staging / "examples")
                capture_demo(staging)
            staging.rename(output)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Ошибка сборки: {error}\n")
    print(f"Сборка завершена: {output}")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
