import logging
import tarfile
from pathlib import Path
from typing import List

logger = logging.getLogger("rgcc.security")

# Dangerous compiler flags that could lead to RCE or sandbox escape.
# -fplugin / -fplugin-arg: Loads arbitrary shared libraries.
# -wrapper: Executes an arbitrary wrapper command.
# -B: Changes the search path for binaries (can point to malicious ones).
# -specs / --specs: Loads alternative spec files.
# -load: Loads arbitrary shared libraries (Clang).
# -MF: Writes dependency file to an arbitrary path.
# -MT / -MQ: Dependency tracking with path control.
# -MD / -MMD: Dependency tracking that generates files.
# -x: Forces interpretation as assembler or other language.
# -save-temps: Leaves intermediate files in unpredictable locations.
# -fprofile-generate: Writes profiling data to an arbitrary path.
#
# All entries are lowercased; is_flag_safe() normalises input before matching.
DANGEROUS_FLAGS = {
    "-fplugin",
    "-fplugin-arg",
    "-wrapper",
    "-b",
    "-specs",
    "--specs",
    "-load",
    "-mf",
    "-mt",
    "-mq",
    "-md",
    "-mmd",
    "-x",
    "-save-temps",
    "-fprofile-generate",
}

# Subset of dangerous flags that consume the *next* token as their argument.
# When one of these is encountered without an inlined "=" value, both the flag
# and the following element must be dropped to prevent the orphaned argument
# from being misinterpreted by the compiler.
_DANGEROUS_FLAGS_WITH_ARG = {
    "-fplugin",
    "-wrapper",
    "-b",
    "-specs",
    "--specs",
    "-load",
    "-mf",
    "-mt",
    "-mq",
    "-x",
}


def is_flag_safe(flag: str) -> bool:
    """Check if a compiler flag is safe to execute on the server."""
    flag_lower = flag.split("=")[0].lower().strip()
    return not any(flag_lower.startswith(d) for d in DANGEROUS_FLAGS)


def safe_extract(tar: tarfile.TarFile, path: Path) -> None:
    """Extract a tarball safely, mitigating Path Traversal attacks.

    Uses filter="data" on Python 3.12+ and manual validation on older versions.
    """
    if hasattr(tarfile, "data_filter"):
        # Python 3.12+ native protection
        tar.extractall(path=path, filter="data")
    else:
        # Manual validation for older Python versions.
        # Extract each member individually to prevent a TOCTOU race
        # where a symlink entry followed by a file entry could write
        # through the symlink to an arbitrary location.
        resolved_base = path.resolve()
        for member in tar.getmembers():
            # Reject symlinks and hardlinks entirely
            if member.issym() or member.islnk():
                raise PermissionError(
                    f"Refusing symlink/hardlink in archive: {member.name}"
                )
            member_path = (path / member.name).resolve()
            if not member_path.is_relative_to(resolved_base):
                raise PermissionError(f"Attempted Path Traversal: {member.name}")
            tar.extract(member, path=path)


def filter_safe_flags(flags: List[str]) -> List[str]:
    """Filter out dangerous flags from a list and log warnings.

    Performs pairwise scanning: if a dangerous flag takes a separate argument
    (e.g. ["-B", "/evil/path"]), both the flag and the following token are
    dropped to prevent the orphaned argument from reaching the compiler.
    """
    safe_flags: List[str] = []
    skip_next = False

    for i, flag in enumerate(flags):
        if skip_next:
            logger.warning("Blocked argument of dangerous flag: %s", flag)
            skip_next = False
            continue

        if not is_flag_safe(flag):
            logger.warning("Blocked dangerous compiler flag: %s", flag)
            # If this flag takes a separate next-token argument and the value
            # is not inlined via "=", skip the next token too.
            flag_lower = flag.split("=")[0].lower().strip()
            if "=" not in flag and any(
                flag_lower.startswith(d) for d in _DANGEROUS_FLAGS_WITH_ARG
            ):
                skip_next = True
            continue

        safe_flags.append(flag)

    return safe_flags
