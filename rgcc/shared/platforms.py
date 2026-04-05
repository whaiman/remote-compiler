# Canonical mapping from platform.system() to internal platform tags.
# Add new platforms here — one place for both client and server.
PLATFORM_MAP: dict[str, str] = {
    "windows": "win64",
    "linux": "linux",
    "darwin": "darwin",
}

# Server-side whitelist of permitted compiler executables.
# Compilers listed in server_config.yaml are also considered allowed.
# Anything not in this set AND not in the config will be rejected.
ALLOWED_COMPILERS: frozenset[str] = frozenset(
    {
        "gcc",
        "g++",
        "clang",
        "clang++",
        "cc",
        "c++",
        "x86_64-w64-mingw32-gcc",
        "x86_64-w64-mingw32-g++",
        "x86_64-w64-mingw32-clang",
        "x86_64-w64-mingw32-clang++",
    }
)
