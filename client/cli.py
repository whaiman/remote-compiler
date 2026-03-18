import asyncio
import json
import logging
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn

from client.collect import collect_sources
from client.manifest import generate_build_manifest
from client.transport.api import ApiClient
from shared.config import load_client_config
from shared.manifest import BuildManifest

app = typer.Typer(name="rgcc", help="Remote GCC Compiler Client")
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console)]
)
logger = logging.getLogger("rgcc")


@app.callback()
def callback():
    """RGCC - Remote GCC Compiler System."""
    pass


@app.command()
def compile(
    entry_point: Path = typer.Argument(..., help="Main .c / .cpp file"),
    output: str = typer.Option("main", "-o", "--output", help="Output filename"),
    host: Optional[str] = typer.Option(None, "--host", help="Server host override"),
    endpoint: Optional[str] = typer.Option(
        None, "--endpoint", help="API endpoint override"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't transfer to server"),
    compile_only: bool = typer.Option(
        False, "--compile-only", help="Compile only, don't link"
    ),
    standard: str = typer.Option("c++17", "--std", help="Language standard"),
    config_file: Optional[Path] = typer.Option(
        None, "--config", help="Config file path override"
    ),
    platform: Optional[str] = typer.Option(
        None, "--platform", help="Target platform (linux, win64, darwin)"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Prompt for build settings before starting"
    ),
    out_dir: Path = typer.Option(
        Path("compiled"), "-d", "--out-dir", help="Artifacts destination directory"
    ),
    save_logs: bool = typer.Option(
        True, "--logs/--no-logs", help="Whether to save compilation logs"
    ),
    save_manifest: bool = typer.Option(
        True, "--manifest/--no-manifest", help="Whether to save manifest_result.json"
    ),
):
    """Compile and link a source tree on a remote server."""

    if not entry_point.exists():
        console.print(f"[bold red]Error:[/bold red] File {entry_point} not found.")
        raise typer.Exit(1)

    entry_point = entry_point.resolve()
    project_root = entry_point.parent

    # Simple search for root?
    # Let's assume current working directory is the root?
    cwd = Path.cwd()
    if entry_point.resolve().is_relative_to(cwd):
        project_root = cwd

    manifest = None
    all_sources = []

    # Check for existing build.json in project_root
    local_manifest_path = project_root / "build.json"
    if local_manifest_path.exists():
        console.print(f"Using existing manifest: [cyan]{local_manifest_path}[/cyan]")
        try:
            with open(local_manifest_path, "r", encoding="utf-8") as f:
                manifest = BuildManifest.from_json(f.read())
        except Exception as e:
            console.print(
                f"[bold red]Error loading {local_manifest_path}:[/bold red] {e}"
            )
            raise typer.Exit(1)

    # 1. Collect sources (always needed for packing)
    all_sources = collect_sources(entry_point, project_root)

    # 2. Generate manifest if not loaded
    if not manifest:
        manifest = generate_build_manifest(
            entry_point,
            project_root,
            all_sources,
            output=output,
            language="c++" if entry_point.suffix in {".cpp", ".cc"} else "c",
            standard=standard,
            flags=["-Wall", "-O2"] + (["-c"] if compile_only else []),
        )
    else:
        # If manifest was loaded, we might still want to override some things via CLI?
        if platform:
            manifest.platform = platform
        if output != "main":
            manifest.output = output
        if standard != "c++17":
            manifest.standard = standard
        if compile_only and "-c" not in manifest.flags:
            manifest.flags.append("-c")

        # Set output persistence settings if they exist or use CLI defaults
        # We store these as custom fields in manifest for internal use
        manifest.__dict__.setdefault("out_dir", str(out_dir))
        manifest.__dict__.setdefault("save_logs", save_logs)
        manifest.__dict__.setdefault("save_manifest", save_manifest)

        # Override with CLI if they are NOT defaults (user explicitly provided them)
        if str(out_dir) != "compiled":
            manifest.out_dir = str(out_dir)
        if not save_logs:
            manifest.save_logs = False
        if not save_manifest:
            manifest.save_manifest = False

        # Adjust output according to platform
        stem = Path(manifest.output).stem
        if manifest.platform == "win64":
            manifest.output = f"{stem}.exe"
        elif manifest.platform == "linux" or manifest.platform == "darwin":
            manifest.output = stem

    # --- INTERACTIVE MODE ---
    if interactive:
        console.print(
            "\n[bold yellow]--- Interactive Build Configuration ---[/bold yellow]"
        )
        manifest.compiler = typer.prompt(
            "Compiler executable", default=manifest.compiler
        )
        manifest.standard = typer.prompt("Language standard", default=manifest.standard)
        manifest.platform = typer.prompt("Target platform", default=manifest.platform)
        manifest.output = typer.prompt("Output binary name", default=manifest.output)
        manifest.out_dir = typer.prompt("Artifacts directory", default=manifest.out_dir)
        manifest.save_logs = typer.confirm(
            "Save compilation logs?", default=manifest.save_logs
        )
        manifest.save_manifest = typer.confirm(
            "Save result manifest?", default=manifest.save_manifest
        )

        # Re-adjust after user prompt
        stem = Path(manifest.output).stem
        if manifest.platform == "win64":
            manifest.output = f"{stem}.exe"
        elif manifest.platform == "linux" or manifest.platform == "darwin":
            manifest.output = stem

        flags_str = ", ".join(manifest.flags)
        new_flags = typer.prompt(
            "Compilation flags (comma separated)", default=flags_str
        )
        manifest.flags = [f.strip() for f in new_flags.split(",") if f.strip()]

        if not typer.confirm("Everything ready? Proceed with compilation?"):
            console.print("Cancelled by user.")
            return

        # Save to build.json if user wants
        if typer.confirm("Save these settings to build.json for next time?"):
            try:
                # We only want to save persistent settings, not transient ones
                transient_fields = {
                    "timestamp",
                    "checksum_sha256",
                    "sources",
                    "include_dirs",
                }
                config_data = {
                    k: v
                    for k, v in manifest.__dict__.items()
                    if k not in transient_fields
                }

                with open(local_manifest_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=2)
                console.print(
                    f"[bold green]Settings saved to {local_manifest_path}[/bold green]"
                )
            except Exception as e:
                console.print(f"[bold red]Failed to save build.json:[/bold red] {e}")

        console.print("")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        # Refresh dynamic fields in manifest from last discovery (just in case)
        # sources and include_dirs MUST be from the CURRENT scan, not from build.json
        progress.add_task("Finalizing manifest...", total=None)

        # Filter sources for the compiler again (in case discovery changed)
        source_exts = {".cpp", ".c", ".cc", ".cxx", ".cp", ".c++"}
        manifest.sources = [
            s.relative_to(project_root).as_posix()
            for s in all_sources
            if s.suffix.lower() in source_exts
        ]
        manifest.include_dirs = sorted(
            list(
                set(s.parent.relative_to(project_root).as_posix() for s in all_sources)
            )
        )

        from datetime import datetime

        from shared.checksum import get_sha256

        manifest.timestamp = datetime.utcnow().isoformat() + "Z"
        manifest.checksum_sha256 = get_sha256(entry_point)

        # 3. Pack payload
        progress.add_task("Packing archive...", total=None)
        work_dir = Path(tempfile.mkdtemp(prefix="rgcc_client_"))
        try:
            archive_path = work_dir / "payload.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                # Add sources
                for src in all_sources:
                    rel_path = src.resolve().relative_to(project_root.resolve())
                    arcname = Path(rel_path).as_posix()
                    print(f"Adding {src} as {arcname}")
                    tar.add(src, arcname=arcname)

                # Add build.json
                build_json_path = work_dir / "build.json"
                with open(build_json_path, "w", encoding="utf-8") as f:
                    f.write(manifest.to_json())

                tar.add(build_json_path, arcname="build.json")

            if dry_run:
                console.print(
                    f"[bold blue]Dry run complete.[/bold blue] Archive: {archive_path}"
                )
                return

            # 4. Transfer
            progress.add_task("Uploading and compiling...", total=None)

            # Load client-specific config
            cfg = load_client_config()
            client_cfg = cfg.get("client", {})

            api_ep = endpoint or client_cfg.get("endpoint")
            api_token = client_cfg.get("auth_token")

            if not api_ep or not api_token:
                console.print(
                    "[bold red]Error:[/bold red] Missing configuration (endpoint or auth_token) in client_config.yaml."
                )
                raise typer.Exit(1)

            api_client = ApiClient(api_ep, api_token)

            # Send and get (encrypted) result
            response_encrypted = asyncio.run(api_client.send_payload(archive_path))

            # 5. Receive and Finalize
            progress.add_task("Downloading artifacts...", total=None)
            response_data = asyncio.run(api_client.decrypt_response(response_encrypted))

            # It's an archive?
            result_archive_path = work_dir / "result.tar.gz"
            with open(result_archive_path, "wb") as f:
                f.write(response_data)

            # Extract artifacts
            out_dist = Path(getattr(manifest, "out_dir", "compiled"))
            out_dist.mkdir(exist_ok=True, parents=True)

            with tarfile.open(result_archive_path, "r:gz") as tar:
                tar.extractall(path=out_dist)

            # 6. Post-process (delete unwanted files)
            res_path = out_dist / "manifest_result.json"
            log_path = out_dist / "compile.log"

            # Print summary anyway if it exists before we potentially delete it
            if res_path.exists():
                with open(res_path, "r") as f:
                    res = json.load(f)
                    if res.get("returncode") == 0:
                        console.print(
                            f"\n[bold green]Compilation successful![/bold green]"
                        )
                    else:
                        console.print(f"\n[bold red]Compilation failed.[/bold red]")

                    console.print(f"Duration: [cyan]{res.get('duration')}s[/cyan]")
                    console.print(f"Artifacts saved to: [cyan]{out_dist}/[/cyan]")

            if log_path.exists() and getattr(manifest, "save_logs", True):
                with open(log_path, "r") as f:
                    print("\n" + f.read())

            # Delete if not requested
            if not getattr(manifest, "save_manifest", True) and res_path.exists():
                res_path.unlink()
            if not getattr(manifest, "save_logs", True) and log_path.exists():
                log_path.unlink()

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


@app.command()
def init(
    entry_point: Path = typer.Argument(..., help="Main .c / .cpp file"),
    output: str = typer.Option("main", "-o", "--output", help="Output filename"),
    standard: str = typer.Option("c++17", "--std", help="Language standard"),
    platform: str = typer.Option(
        "linux", "--platform", help="Target platform (linux, win64, darwin)"
    ),
    out_dir: str = typer.Option(
        "dist", "-d", "--out-dir", help="Default artifacts directory"
    ),
):
    """Create a build.json file in the project directory."""
    if not entry_point.exists():
        console.print(f"[bold red]Error:[/bold red] File {entry_point} not found.")
        raise typer.Exit(1)

    entry_point = entry_point.resolve()
    project_root = entry_point.parent
    cwd = Path.cwd()
    if entry_point.resolve().is_relative_to(cwd):
        project_root = cwd

    manifest_path = project_root / "build.json"
    if manifest_path.exists():
        if not typer.confirm("build.json already exists. Overwrite?"):
            console.print("Cancelled.")
            return

    console.print("Analyzing project and generating manifest...")
    all_sources = collect_sources(entry_point, project_root)
    manifest = generate_build_manifest(
        entry_point,
        project_root,
        all_sources,
        output=output,
        language="c++" if entry_point.suffix in {".cpp", ".cc"} else "c",
        standard=standard,
        platform=platform,
    )

    # Adjust output according to platform
    manifest.out_dir = out_dir
    manifest.save_logs = False
    manifest.save_manifest = False

    stem = Path(manifest.output).stem
    if manifest.platform == "win64":
        manifest.output = f"{stem}.exe"
    elif manifest.platform == "linux" or manifest.platform == "darwin":
        manifest.output = stem

    # Exclude transient fields from being saved to the configuration file
    transient_fields = {"timestamp", "checksum_sha256", "sources", "include_dirs"}
    config_data = {
        k: v for k, v in manifest.__dict__.items() if k not in transient_fields
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    console.print(f"[bold green]Successfully initialized:[/bold green] {manifest_path}")
    console.print("You can now edit this file to customize your build process.")


if __name__ == "__main__":
    app()
