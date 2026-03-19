from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from shared.checksum import get_sha256
from shared.manifest import BuildManifest, SOURCE_EXTENSIONS


def generate_build_manifest(
    entry_point: Path,
    project_root: Path,
    sources: List[Path],
    output: str = "main",
    language: str = "c++",
    standard: str = "c++17",
    compiler: str = "g++",
    flags: Optional[List[str]] = None,
    defines: Optional[List[str]] = None,
    platform: str = "linux",
    out_dir: str = "dist",
    save_logs: bool = True,
    save_manifest: bool = True,
) -> BuildManifest:
    """Generate a manifest for the compilation job."""
    rel_entry = entry_point.relative_to(project_root).as_posix()

    rel_sources = [
        s.relative_to(project_root).as_posix()
        for s in sources
        if s.suffix.lower() in SOURCE_EXTENSIONS
    ]
    if rel_entry not in rel_sources:
        rel_sources.append(rel_entry)

    include_dirs = sorted({s.parent.relative_to(project_root).as_posix() for s in sources})

    return BuildManifest(
        language=language,
        standard=standard,
        entry_point=rel_entry,
        sources=rel_sources,
        include_dirs=include_dirs,
        defines=defines or [],
        flags=flags or ["-Wall", "-O2", "-static"],
        output=output,
        compiler=compiler,
        platform=platform,
        out_dir=out_dir,
        save_logs=save_logs,
        save_manifest=save_manifest,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checksum_sha256=get_sha256(entry_point),
    )