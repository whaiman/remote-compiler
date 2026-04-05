import logging
import subprocess
import time
from pathlib import Path

from rgcc.server.compiler.runner import CompilationResult

logger = logging.getLogger("server.compiler.fallback")

def run_fallback_compilation(src_path: Path, output_file: Path) -> CompilationResult:
    """Fallback compilation for single source file if no build.json is present."""
    start_time = time.time()
    
    if src_path.suffix == ".c":
        cmd = ["gcc", str(src_path), "-o", str(output_file)]
    elif src_path.suffix == ".cpp":
        cmd = ["g++", str(src_path), "-o", str(output_file)]
    else:
        raise ValueError(f"Unsupported file extension: {src_path.suffix}")

    logger.info("Running fallback: %s", " ".join(cmd))
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        duration = time.time() - start_time
        return CompilationResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration=round(duration, 3),
            output_path=output_file if proc.returncode == 0 else None
        )
    except Exception as e:
        duration = time.time() - start_time
        return CompilationResult(
            returncode=-1,
            stdout="",
            stderr=str(e),
            duration=round(duration, 3)
        )
