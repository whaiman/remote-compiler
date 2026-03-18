import json
from dataclasses import dataclass, field
from typing import List


@dataclass
class BuildManifest:
    schema_version: str = "1.0"
    target: str = "main"
    language: str = "c++"
    standard: str = "c++17"
    entry_point: str = "src/main.cpp"
    sources: List[str] = field(default_factory=list)
    include_dirs: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    link_flags: List[str] = field(default_factory=list)
    output: str = "a.out"
    compiler: str = "g++"
    platform: str = "linux" # default platform
    timestamp: str = ""
    checksum_sha256: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "BuildManifest":
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_dict(cls, data: dict) -> "BuildManifest":
        return cls(**data)
