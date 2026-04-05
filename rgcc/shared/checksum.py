import hashlib
from pathlib import Path


def get_sha256(path: Path) -> str:
    """Compute sha256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(path: Path, expected_sha256: str) -> bool:
    """Verify checksum of a file."""
    actual = get_sha256(path)
    return actual.lower() == expected_sha256.lower()
