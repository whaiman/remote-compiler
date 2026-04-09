import logging
import tarfile
from pathlib import Path
from typing import List

logger = logging.getLogger("rgcc.security")

# Dangerous compiler flags that could lead to RCE or sandbox escape.
# -fplugin: Loads arbitrary shared libraries.
# -wrapper: Executes an arbitrary wrapper command.
# -B: Changes the search path for binaries (can point to malicious ones).
# -specs: Loads alternative spec files.
DANGEROUS_FLAGS = {
    "-fplugin",
    "-fplugin-arg",
    "-wrapper",
    "-B",
    "-specs",
    "--specs",
    "-load",
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
        # Manual validation for older Python versions
        for member in tar.getmembers():
            member_path = (path / member.name).resolve()
            if not member_path.is_relative_to(path.resolve()):
                raise PermissionError(f"Attempted Path Traversal: {member.name}")
        tar.extractall(path=path)


def filter_safe_flags(flags: List[str]) -> List[str]:
    """Filter out dangerous flags from a list and log warnings."""
    safe_flags = []
    for f in flags:
        if is_flag_safe(f):
            safe_flags.append(f)
        else:
            logger.warning(f"Blocked dangerous compiler flag: {f}")
    return safe_flags
