import json
from pathlib import Path

from rgcc.core.manifest import BuildManifest


def test_defaults_are_valid():
    manifest = BuildManifest()
    assert manifest.schema_version == "1.1"
    assert manifest.language == "c++"
    assert manifest.standard == "c++23"
    assert manifest.entry_point == "src/main.cpp"
    assert manifest.sources == []


def test_json_roundtrip():
    manifest = BuildManifest(
        language="c",
        standard="c17",
        entry_point="main.c",
        sources=["main.c"],
        include_dirs=["include"],
        defines=["DEBUG=1"],
        flags=["-O2"],
        link_flags=["-lm"],
        output="app",
        compiler="gcc",
        platform="linux",
        target=None,
        sysroot=None,
        out_dir="dist",
        save_logs=False,
        save_manifest=False,
        timestamp="2026-01-01T00:00:00Z",
        checksum_sha256="abc",
    )
    restored = BuildManifest.from_json(manifest.to_json())
    assert restored == manifest


def test_from_dict_ignores_unknown_fields():
    manifest = BuildManifest.from_dict({"language": "c", "unknown": 123})
    assert manifest.language == "c"
    assert not hasattr(manifest, "unknown")


def test_save_config_excludes_transient_fields(tmp_path: Path):
    manifest = BuildManifest(
        timestamp="now", checksum_sha256="hash", sources=["a.cpp"], include_dirs=["."]
    )
    path = tmp_path / "build.json"
    manifest.save_config(path)
    data = json.loads(path.read_text())
    assert "timestamp" not in data
    assert "checksum_sha256" not in data
    assert "sources" not in data
    assert "include_dirs" not in data
    assert data["language"] == "c++"


def test_to_json_contains_all_fields():
    data = json.loads(BuildManifest().to_json())
    assert set(data) == set(BuildManifest().__dict__)
