import re
from pathlib import Path
from typing import List, Optional, Set


def resolve_includes(
    file_path: Path,
    base_dir: Path,
    processed_files: Set[Path],
    extra_include_dirs: Optional[List[Path]] = None,
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

        inc_path: Optional[Path] = None

        # 1. Relative to the current file
        candidate = (file_path.parent / match).resolve()
        if candidate.exists() and candidate.is_relative_to(base_dir):
            inc_path = candidate
        else:
            # 2. Relative to project root
            candidate = (base_dir / match).resolve()
            if candidate.exists() and candidate.is_relative_to(base_dir):
                inc_path = candidate
            else:
                # 3. Search extra -I directories (e.g. "include/")
                for inc_dir in extra_include_dirs or []:
                    candidate = (inc_dir / match).resolve()
                    if candidate.exists() and candidate.is_relative_to(base_dir):
                        inc_path = candidate
                        break

        if inc_path is None:
            # System header or genuinely missing - skip silently
            continue

        if inc_path not in processed_files:
            resolve_includes(inc_path, base_dir, processed_files, extra_include_dirs)

        # Heuristic: if we found a local header, try to find its matching source file
        if inc_path.suffix.lower() in {".h", ".hpp", ".hh"}:
            for src_ext in {".cpp", ".c", ".cc", ".cxx"}:
                src_path = inc_path.with_suffix(src_ext)
                if src_path.exists() and src_path not in processed_files:
                    resolve_includes(
                        src_path, base_dir, processed_files, extra_include_dirs
                    )

    return processed_files


def collect_sources(
    entry_file: Path,
    project_root: Path,
    extra_include_dirs: Optional[List[Path]] = None,
) -> List[Path]:
    """Collect all sources and headers needed for compilation.

    Args:
        entry_file: The main translation unit.
        project_root: Root of the project (archive boundary).
        extra_include_dirs: Additional directories to search for angle-bracket
            includes (e.g. paths derived from ``-I`` flags in build.json).
    """
    all_files = resolve_includes(entry_file, project_root, set(), extra_include_dirs)
    return list(all_files)
