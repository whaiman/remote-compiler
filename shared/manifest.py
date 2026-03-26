import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

TRANSIENT_FIELDS = {"timestamp", "checksum_sha256", "sources", "include_dirs"}

SOURCE_EXTENSIONS = {".cpp", ".c", ".cc", ".cxx", ".cp", ".c++"}


@dataclass
class BuildManifest:
    schema_version: str = "1.0"
    language: str = "c++"
    standard: str = "c++23"
    entry_point: str = "src/main.cpp"
    sources: List[str] = field(default_factory=list)
    include_dirs: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    link_flags: List[str] = field(default_factory=list)
    output: str = "a.out"
    compiler: str = "g++"
    platform: str = "linux"
    out_dir: str = "dist"
    save_logs: bool = True
    save_manifest: bool = True
    timestamp: str = ""
    checksum_sha256: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)

    def save_config(self, path: Path) -> None:
        """Save only persistent (non-transient) fields to a JSON file."""
        config_data = {k: v for k, v in self.__dict__.items() if k not in TRANSIENT_FIELDS}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "BuildManifest":
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_dict(cls, data: dict) -> "BuildManifest":
        # Ignore unknown fields for forward-compatibility
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})
