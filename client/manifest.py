import datetime
from pathlib import Path
from typing import List

from shared.checksum import get_sha256
from shared.manifest import BuildManifest


def generate_build_manifest(
    entry_point: Path,
    project_root: Path,
    sources: List[Path],
    output: str = "main",
    language: str = "c++",
    standard: str = "c++17",
    compiler: str = "g++",
    flags: List[str] = None,
    link_flags: List[str] = None,
    defines: List[str] = None,
    platform: str = "linux"
) -> BuildManifest:
    """Generate a manifest for the compilation job."""
    
    # Paths in manifest are relative to project_root
    rel_entry = entry_point.relative_to(project_root).as_posix()
    
    # Filter sources: we only want to pass actual source files to the compiler command line.
    # Header files should be present in the src directory but NOT on the command line.
    source_exts = {".cpp", ".c", ".cc", ".cxx", ".cp", ".c++"}
    rel_sources = [
        s.relative_to(project_root).as_posix() 
        for s in sources 
        if s.suffix.lower() in source_exts
    ]
    
    # Ensure entry_point is in sources if it wasn't captured (shouldn't happen)
    if rel_entry not in rel_sources:
        rel_sources.append(rel_entry)
    
    # Simplistic include_dirs extraction
    include_dirs = sorted(list(set(s.parent.relative_to(project_root).as_posix() for s in sources)))
    
    return BuildManifest(
        schema_version="1.0",
        target=entry_point.stem,
        language=language,
        standard=standard,
        entry_point=rel_entry,
        sources=rel_sources,
        include_dirs=include_dirs,
        defines=defines or [],
        flags=flags or ["-Wall", "-Wextra", "-O2"],
        link_flags=link_flags or [],
        output=output,
        compiler=compiler,
        platform=platform,
        timestamp=datetime.datetime.utcnow().isoformat() + "Z",
        checksum_sha256=get_sha256(entry_point) # Spec says "checksum of the archive", but build.json is inside.
        # Let's use the checksum of main entry file as a placeholder or it will be overriden later.
    )