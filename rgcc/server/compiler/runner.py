import logging
import platform as _platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rgcc.shared.manifest import BuildManifest
from rgcc.shared.platforms import ALLOWED_COMPILERS, PLATFORM_MAP

logger = logging.getLogger("server.compiler")

_HOST_PLATFORM = PLATFORM_MAP.get(_platform.system().lower(), "linux")


@dataclass
class CompilationResult:
    returncode: int
    stdout: str
    stderr: str
    duration: float
    output_path: Optional[Path] = None


def _build_command(manifest: BuildManifest, src_dir: Path, output_path: Path, config: dict) -> list[str]:
    """Assemble the compiler command from manifest + server config."""
    compilers_cfg = config.get("compilers", {})
    if manifest.compiler not in compilers_cfg and manifest.compiler not in ALLOWED_COMPILERS:
        raise ValueError(f"Compiler '{manifest.compiler}' is not allowed on this server.")

    compiler_cfg = compilers_cfg.get(manifest.compiler, {})
    platform_cfg = compiler_cfg.get("platforms", {}).get(manifest.platform, {})
    is_cross = _HOST_PLATFORM != manifest.platform

    compiler_exe = platform_cfg.get("executable", manifest.compiler)
    cmd = [compiler_exe]

    # Global compiler args (e.g. color diagnostics)
    cmd.extend(compiler_cfg.get("default_args", []))

    # Cross-compilation flags
    if is_cross:
        if target := platform_cfg.get("target"):
            cmd.extend(["-target", target])
        if sysroot := platform_cfg.get("sysroot"):
            cmd.extend(["-sysroot", sysroot])
        cmd.extend(platform_cfg.get("args", []))

    # Language standard
    if manifest.language == "c++":
        cmd.append(f"-std={manifest.standard}")

    cmd.extend(manifest.flags)

    # Always expose the project root so that <lib/header.hpp> style includes
    # resolve correctly for local libraries bundled with the project.
    cmd.extend(["-I", str(src_dir)])

    # Additional include dirs declared in the manifest (resolved to absolute)
    for inc in manifest.include_dirs:
        inc_path = (src_dir / inc).resolve()
        if inc_path.is_relative_to(src_dir) and inc_path != src_dir:
            cmd.extend(["-I", str(inc_path)])

    # Defines
    cmd.extend(f"-D{d}" for d in manifest.defines)

    # Source files (resolved to absolute)
    for src in manifest.sources:
        src_path = (src_dir / src).resolve()
        if src_path.is_relative_to(src_dir):
            cmd.append(str(src_path))

    cmd.extend(manifest.link_flags)
    cmd.extend(["-o", str(output_path)])
    return cmd


def run_compilation(manifest: BuildManifest, working_dir: Path, config: dict = None) -> CompilationResult:
    """Run a compilation task based on a manifest."""
    config = config or {}
    src_dir = working_dir / "src"
    out_dir = working_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    output_path = out_dir / manifest.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    entry_path = (src_dir / manifest.entry_point).resolve()
    if not entry_path.is_relative_to(src_dir):
        raise ValueError("entry_point escapes src directory")

    cmd = _build_command(manifest, src_dir, output_path, config)
    logger.info("Running: %s", " ".join(cmd))

    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=src_dir)
        return CompilationResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration=round(time.time() - start, 3),
            output_path=output_path if proc.returncode == 0 else None,
        )
    except Exception as e:
        return CompilationResult(
            returncode=-1,
            stdout="",
            stderr=str(e),
            duration=round(time.time() - start, 3),
        )
