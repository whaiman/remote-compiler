import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def get_file_hash(path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_source_hash(source_dir: Path) -> str:
    """Calculates a deterministic hash of all files in the source directory."""
    hashes = []
    for root, _, files in os.walk(source_dir):
        for file in sorted(files):
            file_path = Path(root) / file
            rel_path = file_path.relative_to(source_dir).as_posix()
            file_hash = get_file_hash(file_path)
            hashes.append(f"{rel_path}:{file_hash}")

    combined = "\n".join(sorted(hashes)).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def get_compiler_version(compiler_exe: str) -> str:
    try:
        result = subprocess.run(
            [compiler_exe, "--version"], capture_output=True, text=True, check=True
        )
        return result.stdout.splitlines()[0]
    except Exception:
        return "unknown"


def generate(
    compiler: str,
    standard: str,
    flags: List[str],
    platform_target: str,
    source_dir: Path,
    binary_path: Path,
) -> Dict[str, Any]:
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", 0))
    ts = (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    return {
        "schema": "rgcc-buildinfo/1",
        "source_hash": get_source_hash(source_dir),
        "binary_hash": get_file_hash(binary_path),
        "compiler": compiler,
        "compiler_version": get_compiler_version(compiler),
        "standard": standard,
        "flags": flags,
        "platform": platform_target,
        "build_timestamp_utc": ts,
    }
