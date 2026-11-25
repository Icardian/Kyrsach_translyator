/* Windows x64 entry point. The SQL2Py bytecode runs through CPython's Py_Main. */

#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#else
/* Win32 declarations used by the Linux x86-64 cross-build. */
#define WINAPI __attribute__((ms_abi))
#define LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR 0x00000100
#define LOAD_LIBRARY_SEARCH_SYSTEM32 0x00000800
#define STD_ERROR_HANDLE ((DWORD)-12)
typedef wchar_t WCHAR;
typedef uint32_t DWORD;
typedef int32_t BOOL;
typedef void *HANDLE;
typedef void *HMODULE;
typedef void (WINAPI *FARPROC)(void);
extern DWORD WINAPI GetModuleFileNameW(HMODULE, WCHAR *, DWORD);
extern WCHAR *WINAPI GetCommandLineW(void);
extern WCHAR **WINAPI CommandLineToArgvW(const WCHAR *, int *);
extern HMODULE WINAPI LoadLibraryExW(const WCHAR *, HANDLE, DWORD);
extern FARPROC WINAPI GetProcAddress(HMODULE, const char *);
extern HANDLE WINAPI GetStdHandle(DWORD);
extern BOOL WINAPI WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
extern HANDLE WINAPI GetProcessHeap(void);
extern void *WINAPI HeapAlloc(HANDLE, DWORD, size_t);
extern BOOL WINAPI HeapFree(HANDLE, DWORD, void *);
extern HANDLE WINAPI LocalFree(HANDLE);
extern __attribute__((noreturn)) void WINAPI ExitProcess(DWORD);
#endif

#define PATH_CAPACITY 32768

typedef int (WINAPI *PythonMain)(int, WCHAR **);

static WCHAR launcher_path[PATH_CAPACITY];
static WCHAR python_path[PATH_CAPACITY];
static WCHAR dll_path[PATH_CAPACITY];
static WCHAR archive_path[PATH_CAPACITY];
static WCHAR isolated[] = L"-I";

static __attribute__((noreturn)) void fail(const char *message)
{
    DWORD length = 0;
    DWORD written;
    while (message[length] != '\0') {
        ++length;
    }
    WriteFile(GetStdHandle(STD_ERROR_HANDLE), message, length, &written, NULL);
    ExitProcess(3);
}

static void sibling(WCHAR *destination, DWORD prefix_length, const WCHAR *suffix)
{
    DWORD index;
    for (index = 0; index < prefix_length; ++index) {
        destination[index] = launcher_path[index];
    }
    while (*suffix != 0) {
        if (index >= PATH_CAPACITY - 1) {
            fail("SQL2Py: installation path is too long.\n");
        }
        destination[index++] = *suffix++;
    }
    destination[index] = 0;
}

__attribute__((noreturn)) void WINAPI mainCRTStartup(void)
{
    DWORD prefix_length = GetModuleFileNameW(NULL, launcher_path, PATH_CAPACITY);
    if (prefix_length == 0 || prefix_length >= PATH_CAPACITY) {
        fail("SQL2Py: cannot determine the executable location.\n");
    }
    while (prefix_length > 0 && launcher_path[prefix_length - 1] != L'\\' &&
           launcher_path[prefix_length - 1] != L'/') {
        --prefix_length;
    }
    sibling(python_path, prefix_length, L"runtime\\python.exe");
    sibling(dll_path, prefix_length, L"runtime\\python312.dll");
    sibling(archive_path, prefix_length, L"sql2py.pyz");

    HMODULE library = LoadLibraryExW(dll_path, NULL,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (library == NULL) {
        fail("SQL2Py: cannot load runtime\\python312.dll. Keep bin together.\n");
    }
    union {
        FARPROC native;
        PythonMain python;
    } entry;
    entry.native = GetProcAddress(library, "Py_Main");
    if (entry.native == NULL) {
        fail("SQL2Py: the supplied CPython library has no Py_Main entry point.\n");
    }

    int argc;
    WCHAR **arguments = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (arguments == NULL || argc < 1) {
        fail("SQL2Py: cannot read command-line arguments.\n");
    }

    HANDLE heap = GetProcessHeap();
    WCHAR **python_arguments = HeapAlloc(heap, 0, (size_t)(argc + 3) * sizeof(WCHAR *));
    if (python_arguments == NULL) {
        LocalFree(arguments);
        fail("SQL2Py: cannot allocate command-line arguments.\n");
    }
    python_arguments[0] = python_path;
    python_arguments[1] = isolated;
    python_arguments[2] = archive_path;
    for (int index = 1; index < argc; ++index) {
        python_arguments[index + 2] = arguments[index];
    }
    python_arguments[argc + 2] = NULL;

    int status = entry.python(argc + 2, python_arguments);
    HeapFree(heap, 0, python_arguments);
    LocalFree(arguments);
    ExitProcess((DWORD)status);
}
