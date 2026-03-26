import re
from pathlib import Path
from typing import List, Set


def resolve_includes(
    file_path: Path, base_dir: Path, processed_files: Set[Path]
) -> Set[Path]:
    """Recursively resolve local #include dependencies."""
    if file_path in processed_files:
        return processed_files

    processed_files.add(file_path)

    if not file_path.exists():
        return processed_files

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return processed_files

    # Match both #include "file.h" and #include <file.h>
    include_pattern = re.compile(r'#include\s+(?:"([^"]+)"|<([^>]+)>)')
    matches = include_pattern.findall(content)

    for quoted, angled in matches:
        match = quoted or angled
        if not match:
            continue

        # Try relative to the current file first
        inc_path = (file_path.parent / match).resolve()
        if inc_path.exists() and inc_path.is_relative_to(base_dir):
            if inc_path not in processed_files:
                resolve_includes(inc_path, base_dir, processed_files)
        else:
            # Try relative to base_dir
            # Angle-bracket paths that don't exist here (system headers like
            # <vector>, <stdio.h>, …) will simply not be found and are skipped.
            inc_path = (base_dir / match).resolve()
            if inc_path.exists() and inc_path.is_relative_to(base_dir):
                if inc_path not in processed_files:
                    resolve_includes(inc_path, base_dir, processed_files)

        # Heuristic: if we found a local header, try to find its matching source file
        if inc_path.exists() and inc_path.suffix.lower() in {".h", ".hpp", ".hh"}:
            for src_ext in {".cpp", ".c", ".cc", ".cxx"}:
                src_path = inc_path.with_suffix(src_ext)
                if src_path.exists() and src_path not in processed_files:
                    resolve_includes(src_path, base_dir, processed_files)

    return processed_files


def collect_sources(entry_file: Path, project_root: Path) -> List[Path]:
    """Collect all sources and headers needed for compilation."""
    all_files = resolve_includes(entry_file, project_root, set())
    return list(all_files)
