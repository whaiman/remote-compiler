import asyncio
import json
import logging
import platform as _platform
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn

from rgcc.client.collect import collect_sources
from rgcc.client.manifest import generate_build_manifest
from rgcc.client.transport.api import ApiClient
from rgcc.core.checksum import get_sha256
from rgcc.core.config import load_client_config
from rgcc.core.manifest import SOURCE_EXTENSIONS, BuildManifest
from rgcc.core.platforms import PLATFORM_MAP
from rgcc.core.security import safe_extract


app = typer.Typer(name="rgcc", help="Remote GCC Compiler Client")
console = Console()

logging.basicConfig(
    level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console)]
)
logger = logging.getLogger("rgcc")


def _version_callback(value: bool) -> None:
    if value:
        from rgcc import __version__

        console.print(f"rgcc [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()  # type: ignore[untyped-decorator]
def callback(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """RGCC - Remote GCC Compiler System."""


# ─── Smart Defaults ────────────────────────────────────────────────────────────

_CPP_EXTENSIONS = {".cpp", ".cc", ".cxx", ".c++", ".cp"}


def _detect_language(entry_point: Path) -> str:
    return "c++" if entry_point.suffix.lower() in _CPP_EXTENSIONS else "c"


def _detect_standard(language: str) -> str:
    return "c17" if language == "c" else "c++23"


def _get_available_standards(language: str) -> list[str]:
    if language == "c":
        return [
            "c89",
            "c90",
            "c99",
            "c11",
            "c17",
            "c23",
            "gnu99",
            "gnu11",
            "gnu17",
            "gnu23",
        ]
    return [
        "c++11",
        "c++14",
        "c++17",
        "c++20",
        "c++23",
        "gnu++17",
        "gnu++20",
        "gnu++23",
    ]


def complete_platform(incomplete: str):
    platforms = ["linux", "win64", "darwin"]
    return [p for p in platforms if p.startswith(incomplete)]


def complete_standard(ctx: typer.Context, incomplete: str):
    # Try to find entry_point in params
    entry_point = ctx.params.get("entry_point")
    language = "c++"
    if entry_point:
        path = Path(entry_point)
        if path.suffix.lower() == ".c":
            language = "c"

    standards = _get_available_standards(language)
    return [s for s in standards if s.startswith(incomplete)]


def _detect_compiler(entry_point: Path) -> str:
    return "g++" if _detect_language(entry_point) == "c++" else "gcc"


def _detect_platform() -> str:
    return PLATFORM_MAP.get(_platform.system().lower(), "linux")


def _output_name(stem: str, platform_tag: str) -> str:
    return f"{stem}.exe" if platform_tag == "win64" else stem


def _parse_include_dirs_from_flags(flags: list[str], base: Path) -> list[Path]:
    """Extract -I paths from a flags list and resolve them against *base*.

    Handles both ``-Ipath`` (single token) and ``-I path`` (two tokens).
    Paths that don't exist inside *base* are silently dropped.
    """
    dirs: list[Path] = []
    i = 0
    while i < len(flags):
        f = flags[i]
        if f.startswith("-I") and len(f) > 2:
            dirs.append((base / f[2:]).resolve())
        elif f == "-I" and i + 1 < len(flags):
            dirs.append((base / flags[i + 1]).resolve())
            i += 1
        i += 1
    return [d for d in dirs if d.exists() and d.is_relative_to(base)]


def _resolve_project_root(entry_point: Path) -> Path:
    cwd = Path.cwd()
    return cwd if entry_point.is_relative_to(cwd) else entry_point.parent


def _load_manifest(path: Path) -> Optional[BuildManifest]:
    if not path.exists():
        return None
    console.print(f"Using existing manifest: [cyan]{path}[/cyan]")
    try:
        return BuildManifest.from_json(path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[bold red]Error loading {path}:[/bold red] {e}")
        raise typer.Exit(1)


def _apply_cli_overrides(
    manifest: BuildManifest,
    *,
    entry_point: Path,
    platform: Optional[str],
    target: Optional[str],
    sysroot: Optional[str],
    output: Optional[str],
    standard: Optional[str],
    compile_only: bool,
    out_dir: Path,
    save_logs: bool,
    save_manifest_flag: bool,
) -> None:
    """Apply CLI overrides to a loaded manifest in-place.

    Fields not explicitly set via CLI fall back to language-based auto-detection
    when the build.json still carries the dataclass defaults (i.e. the user
    never customised them).
    """
    if platform:
        manifest.platform = platform
    if target:
        manifest.target = target
    if sysroot:
        manifest.sysroot = sysroot
    if output:
        manifest.output = output

    # --- standard ---
    if standard is not None:
        # Explicit CLI value always wins.
        manifest.standard = standard
    elif manifest.standard in ("c++17", "c++23", "c11", "c17"):
        # Looks like a dataclass default - re-derive from the actual language.
        manifest.standard = _detect_standard(manifest.language)

    # --- compiler ---
    if manifest.compiler in ("g++", "gcc"):
        # Dataclass default - re-derive from the entry point language.
        manifest.compiler = _detect_compiler(entry_point)

    if compile_only and "-c" not in manifest.flags:
        manifest.flags.append("-c")
    if str(out_dir) != "dist":
        manifest.out_dir = str(out_dir)
    if not save_logs:
        manifest.save_logs = False
    if not save_manifest_flag:
        manifest.save_manifest = False
    manifest.output = _output_name(Path(manifest.output).stem, manifest.platform)


def _run_interactive(
    manifest: BuildManifest, entry_point: Path, local_manifest_path: Path
) -> None:
    """Prompt the user to configure the manifest interactively."""
    console.print(
        "\n[bold yellow]--- Interactive Build Configuration ---[/bold yellow]"
    )

    # Apply smarter defaults if manifest uses generic values
    if manifest.compiler in ("g++", "gcc"):
        manifest.compiler = _detect_compiler(entry_point)
    if manifest.platform == "linux":
        manifest.platform = _detect_platform()

    manifest.compiler = typer.prompt("Compiler executable", default=manifest.compiler)

    standards = _get_available_standards(manifest.language)
    manifest.standard = typer.prompt(
        f"Language standard ({', '.join(standards)})", default=manifest.standard
    )

    manifest.platform = typer.prompt("Target platform", default=manifest.platform)
    manifest.output = typer.prompt("Output binary name", default=manifest.output)
    manifest.out_dir = typer.prompt("Artifacts directory", default=manifest.out_dir)
    manifest.save_logs = typer.confirm(
        "Save compilation logs?", default=manifest.save_logs
    )
    manifest.save_manifest = typer.confirm(
        "Save result manifest?", default=manifest.save_manifest
    )

    # Re-apply correct extension after user may have typed a new platform
    manifest.output = _output_name(Path(manifest.output).stem, manifest.platform)

    flags_str = ", ".join(manifest.flags)
    new_flags = typer.prompt("Compilation flags (comma separated)", default=flags_str)
    manifest.flags = [f.strip() for f in new_flags.split(",") if f.strip()]

    if not typer.confirm("Everything ready? Proceed with compilation?"):
        console.print("Cancelled by user.")
        raise typer.Exit(0)

    if typer.confirm("Save these settings to build.json for next time?"):
        try:
            manifest.save_config(local_manifest_path)
            console.print(
                f"[bold green]Settings saved to {local_manifest_path}[/bold green]"
            )
        except Exception as e:
            console.print(f"[bold red]Failed to save build.json:[/bold red] {e}")

    console.print("")


def _finalize_manifest(
    manifest: BuildManifest,
    all_sources: list[Path],
    project_root: Path,
    entry_point: Path,
) -> None:
    """Stamp dynamic fields (sources, timestamp, checksum) onto the manifest."""
    manifest.sources = [
        s.relative_to(project_root).as_posix()
        for s in all_sources
        if s.suffix.lower() in SOURCE_EXTENSIONS
    ]
    manifest.include_dirs = sorted(
        {s.parent.relative_to(project_root).as_posix() for s in all_sources}
    )
    manifest.timestamp = datetime.now(timezone.utc).isoformat()
    manifest.checksum_sha256 = get_sha256(entry_point)


def _build_archive(
    work_dir: Path,
    all_sources: list[Path],
    project_root: Path,
    manifest: BuildManifest,
) -> Path:
    """Pack sources + build.json into a payload archive."""
    archive_path = work_dir / "payload.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for src in all_sources:
            arcname = src.resolve().relative_to(project_root.resolve()).as_posix()
            logger.debug("Adding %s as %s", src, arcname)
            tar.add(src, arcname=arcname)

        build_json_path = work_dir / "build.json"
        build_json_path.write_text(manifest.to_json(), encoding="utf-8")
        tar.add(build_json_path, arcname="build.json")

    return archive_path


def _print_result(out_dist: Path) -> None:
    """Print compilation summary from manifest_result.json."""
    res_path = out_dist / "manifest_result.json"
    if not res_path.exists():
        return
    res = json.loads(res_path.read_text())
    status = (
        "[bold green]Compilation successful![/bold green]"
        if res.get("returncode") == 0
        else "[bold red]Compilation failed.[/bold red]"
    )
    console.print(f"\n{status}")
    console.print(f"Duration: [cyan]{res.get('duration')}s[/cyan]")
    console.print(f"Artifacts saved to: [cyan]{out_dist}/[/cyan]")


def _cleanup_artifacts(out_dist: Path, manifest: BuildManifest) -> None:
    """Print log and delete artifacts the user did not request."""
    log_path = out_dist / "compile.log"
    res_path = out_dist / "manifest_result.json"

    if log_path.exists() and manifest.save_logs:
        console.print("\n" + log_path.read_text())

    if not manifest.save_manifest and res_path.exists():
        res_path.unlink()
    if not manifest.save_logs and log_path.exists():
        log_path.unlink()


# ─── Commands ──────────────────────────────────────────────────────────────────


@app.command()  # type: ignore[untyped-decorator]
def compile(
    entry_point: Path = typer.Argument(..., help="Main .c / .cpp file"),
    output: Optional[str] = typer.Option(
        None, "-o", "--output", help="Output filename (default: entry point stem)"
    ),
    endpoint: Optional[str] = typer.Option(
        None, "--endpoint", help="API endpoint override"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't transfer to server"),
    compile_only: bool = typer.Option(
        False, "--compile-only", help="Compile only, don't link"
    ),
    standard: Optional[str] = typer.Option(
        None,
        "--std",
        help="Language standard (auto-detected if omitted)",
        autocompletion=complete_standard,
    ),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        help="Target platform (linux, win64, darwin)",
        autocompletion=complete_platform,
    ),
    target: Optional[str] = typer.Option(
        None, "--target", help="Compilation target triple (e.g. aarch64-linux-gnu)"
    ),
    sysroot: Optional[str] = typer.Option(
        None, "--sysroot", help="Path to remote sysroot (if required)"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Prompt for build settings before starting"
    ),
    out_dir: Path = typer.Option(
        Path("dist"), "-d", "--out-dir", help="Artifacts destination directory"
    ),
    save_logs: bool = typer.Option(
        True, "--logs/--no-logs", help="Whether to save compilation logs"
    ),
    save_manifest: bool = typer.Option(
        True, "--manifest/--no-manifest", help="Whether to save manifest_result.json"
    ),
) -> None:
    """Compile and link a source tree on a remote server."""
    if not entry_point.exists():
        console.print(f"[bold red]Error:[/bold red] File {entry_point} not found.")
        raise typer.Exit(1)

    console.print(f"📡 Remote Compiler: Preparing [cyan]{entry_point.name}[/cyan]...")

    entry_point = entry_point.resolve()
    project_root = _resolve_project_root(entry_point)
    local_manifest_path = project_root / "build.json"

    # Load manifest first so we can extract -I flags before collecting sources.
    manifest = _load_manifest(local_manifest_path)

    extra_include_dirs = _parse_include_dirs_from_flags(
        manifest.flags if manifest else [], project_root
    )
    all_sources = collect_sources(entry_point, project_root, extra_include_dirs)

    if manifest is None:
        detected_platform = platform or _detect_platform()
        flags = ["-Wall", "-O2", "-static"] + (["-c"] if compile_only else [])
        manifest = generate_build_manifest(
            entry_point,
            project_root,
            all_sources,
            output=output or _output_name(entry_point.stem, detected_platform),
            language=_detect_language(entry_point),
            compiler=_detect_compiler(entry_point),
            standard=standard or _detect_standard(_detect_language(entry_point)),
            platform=detected_platform,
            target=target,
            sysroot=sysroot,
            flags=flags,
            out_dir=str(out_dir),
            save_logs=save_logs,
            save_manifest=save_manifest,
        )
    else:
        _apply_cli_overrides(
            manifest,
            entry_point=entry_point,
            platform=platform,
            target=target,
            sysroot=sysroot,
            output=output,
            standard=standard,
            compile_only=compile_only,
            out_dir=out_dir,
            save_logs=save_logs,
            save_manifest_flag=save_manifest,
        )

    if interactive:
        _run_interactive(manifest, entry_point, local_manifest_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Finalizing manifest...", total=None)
        _finalize_manifest(manifest, all_sources, project_root, entry_point)

        progress.add_task("Packing archive...", total=None)
        work_dir = Path(tempfile.mkdtemp(prefix="rgcc_client_"))
        try:
            archive_path = _build_archive(work_dir, all_sources, project_root, manifest)

            if dry_run:
                console.print(
                    f"[bold blue]Dry run complete.[/bold blue] Archive: {archive_path}"
                )
                return

            progress.add_task("Uploading and compiling...", total=None)
            cfg = load_client_config().get("client", {})
            api_ep = endpoint or cfg.get("endpoint")
            api_token = cfg.get("auth_token")

            if not api_ep or not api_token or "CHANGE_ME" in str(api_ep) or "PASTE_TOKEN" in str(api_token):
                console.print(
                    "\n[bold red]Error:[/bold red] Missing or invalid configuration in [cyan]rgcc.yaml[/cyan]."
                )
                console.print("Please edit [cyan]rgcc.yaml[/cyan] and set your server [bold yellow]endpoint[/bold yellow] and [bold yellow]auth_token[/bold yellow].")
                raise typer.Exit(1)

            api_client = ApiClient(api_ep, api_token)
            response_encrypted = asyncio.run(api_client.send_payload(archive_path))

            progress.add_task("Downloading artifacts...", total=None)
            response_data = asyncio.run(api_client.decrypt_response(response_encrypted))

            result_archive_path = work_dir / "result.tar.gz"
            result_archive_path.write_bytes(response_data)

            out_dist = Path(manifest.out_dir)
            out_dist.mkdir(exist_ok=True, parents=True)
            with tarfile.open(result_archive_path, "r:gz") as tar:
                safe_extract(tar, out_dist)

            _print_result(out_dist)
            _cleanup_artifacts(out_dist, manifest)

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


@app.command()  # type: ignore[untyped-decorator]
def init(
    entry_point: Path = typer.Argument(..., help="Main .c / .cpp file"),
    output: Optional[str] = typer.Option(
        None, "-o", "--output", help="Output filename (default: entry point stem)"
    ),
    standard: Optional[str] = typer.Option(None, "--std", help="Language standard"),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        help="Target platform (linux, win64, darwin). Defaults to current OS.",
    ),
    out_dir: str = typer.Option(
        "dist", "-d", "--out-dir", help="Default artifacts directory"
    ),
) -> None:
    """Create a build.json file for this project."""
    if not entry_point.exists():
        console.print(f"[bold red]Error:[/bold red] File {entry_point} not found.")
        raise typer.Exit(1)

    entry_point = entry_point.resolve()
    project_root = _resolve_project_root(entry_point)
    manifest_path = project_root / "build.json"

    if manifest_path.exists() and not typer.confirm(
        "build.json already exists. Overwrite?"
    ):
        console.print("Cancelled.")
        return

    detected_platform = platform or _detect_platform()
    console.print("Analyzing project and generating manifest...")
    detected_language = _detect_language(entry_point)
    manifest = generate_build_manifest(
        entry_point,
        project_root,
        collect_sources(entry_point, project_root),
        output=output or _output_name(entry_point.stem, detected_platform),
        language=detected_language,
        compiler=_detect_compiler(entry_point),
        standard=standard or _detect_standard(detected_language),
        platform=detected_platform,
        out_dir=out_dir,
        save_logs=False,
        save_manifest=False,
    )

    manifest.save_config(manifest_path)
    console.print(f"[bold green]Successfully initialized:[/bold green] {manifest_path}")
    console.print("You can now edit this file to customize your build process.")


if __name__ == "__main__":
    app()
