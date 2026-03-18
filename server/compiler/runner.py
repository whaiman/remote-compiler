import logging
import subprocess
import time
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.manifest import BuildManifest

logger = logging.getLogger("server.compiler")

@dataclass
class CompilationResult:
    returncode: int
    stdout: str
    stderr: str
    duration: float
    output_path: Optional[Path] = None



def run_compilation(manifest: BuildManifest, working_dir: Path, config: dict = None) -> CompilationResult:
    """Run a compilation task based on a manifest."""
    start_time = time.time()
    
    # 0. Server environment detection
    # Map platform.system() to our internal platform tags
    host_platform_map = {
        "windows": "win64",
        "linux": "linux",
        "darwin": "darwin"
    }
    host_platform = host_platform_map.get(platform.system().lower(), "linux")
    
    # 1. Resolve compiler settings
    config = config or {}
    compilers_cfg = config.get("compilers", {})
    compiler_cfg = compilers_cfg.get(manifest.compiler, {})
    
    # Default args from compiler (global for this compiler)
    cmd_args = compiler_cfg.get("default_args", [])
    
    # Platform-specific settings for this compiler
    platform_settings = compiler_cfg.get("platforms", {}).get(manifest.platform, {})
    
    # 2. Setup paths
    # Paths in manifest should be relative to working_dir (where src is extracted)
    src_dir = working_dir / "src"
    out_dir = working_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # output in manifest could be a path like "bin/main"
    output_path = out_dir / manifest.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if entry_point is valid
    entry_path = (src_dir / manifest.entry_point).resolve()
    if not entry_path.is_relative_to(src_dir):
         raise ValueError("entry_point escapes src directory")

    # 3. Build command components
    # If we are NOT on the target platform, apply cross-compilation flags
    is_cross = (host_platform != manifest.platform)
    
    # Use overridden executable or the one from manifest
    compiler_exe = platform_settings.get("executable", manifest.compiler)
    cmd = [compiler_exe]
    
    # Apply global args
    cmd.extend(cmd_args)
    
    # Apply platform-specific target and args
    if is_cross:
        target = platform_settings.get("target")
        if target:
            cmd.extend(["-target", target])
        
        sysroot = platform_settings.get("sysroot")
        if sysroot:
            cmd.extend(["-sysroot", sysroot])
            
        # Extra args for cross-compilation
        cmd.extend(platform_settings.get("args", []))

    # Add flags
    if manifest.language == "c++":
        cmd.extend([f"-std={manifest.standard}"])
    
    for flag in manifest.flags:
        cmd.append(flag)
    
    for inc in manifest.include_dirs:
        # include_dirs are relative to src_dir
        # resolve them to absolute paths for the compiler
        inc_path = (src_dir / inc).resolve()
        if inc_path.is_relative_to(src_dir):
            cmd.extend(["-I", str(inc_path)])
    
    for d in manifest.defines:
        cmd.append(f"-D{d}")
    
    # Add sources (relative paths)
    for src in manifest.sources:
        src_entry = (src_dir / src).resolve()
        if src_entry.is_relative_to(src_dir):
            cmd.append(str(src_entry))
    
    # Add link flags
    for lf in manifest.link_flags:
        cmd.append(lf)
    
    # Output
    cmd.extend(["-o", str(output_path)])
    
    logger.info("Running: %s", " ".join(cmd))
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        duration = time.time() - start_time
        return CompilationResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration=round(duration, 3),
            output_path=output_path if proc.returncode == 0 else None
        )
    except Exception as e:
        duration = time.time() - start_time
        return CompilationResult(
            returncode=-1,
            stdout="",
            stderr=str(e),
            duration=round(duration, 3)
        )
