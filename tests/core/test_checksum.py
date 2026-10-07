from pathlib import Path

from rgcc.core.checksum import get_sha256, verify_checksum


def test_compute_sha256(tmp_path: Path):
    file = tmp_path / "data.bin"
    file.write_bytes(b"hello")

    assert get_sha256(file) == ("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")


def test_compute_sha256_empty(tmp_path: Path):
    file = tmp_path / "empty"
    file.write_bytes(b"")

    assert get_sha256(file) == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_verify_checksum_success(tmp_path: Path):
    file = tmp_path / "data"
    file.write_bytes(b"hello")

    checksum = get_sha256(file)

    assert verify_checksum(file, checksum)


def test_verify_checksum_failure(tmp_path: Path):
    file = tmp_path / "data"
    file.write_bytes(b"hello")

    assert not verify_checksum(file, "0" * 64)
