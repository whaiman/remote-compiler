import logging
import os
import secrets
import signal
from pathlib import Path
from typing import Optional

import typer
import uvicorn
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rgcc import __version__
from rgcc.core.config import SERVER_CONFIG_PATH, load_server_config

app = typer.Typer(name="rgccd", help="RGCC Build Server Control Panel")
console = Console()

PID_FILE = Path.cwd() / "rgccd.pid"


def _get_pid() -> Optional[int]:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text())
        except ValueError:
            return None
    return None

@app.callback()
def callback(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit", is_eager=True
    ),
):
    """RGCC Build Server Control Panel."""
    if version:
        console.print(f"rgccd [cyan]v{__version__}[/cyan]")
        raise typer.Exit()


@app.command()
def start(
    host: Optional[str] = typer.Option(None, help="Override host from config"),
    port: Optional[int] = typer.Option(None, help="Override port from config"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development)"),
):
    """Start the build server daemon."""
    pid = _get_pid()
    if pid:
        # Check if process actually exists
        try:
            os.kill(pid, 0)
            console.print(f"[bold red]Error:[/bold red] Server is already running (PID: {pid})")
            raise typer.Exit(1)
        except OSError:
            # Process doesn't exist, stale PID file
            PID_FILE.unlink()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    cfg = load_server_config()
    server_cfg = cfg.get("server", {})
    
    final_host = host or server_cfg.get("host", "0.0.0.0")
    final_port = port or server_cfg.get("port", 4444)

    PID_FILE.write_text(str(os.getpid()))
    
    console.print(Panel(
        f"🚀 [bold cyan]RGCC Server v{__version__}[/bold cyan]\n"
        f"📍 [yellow]Endpoint:[/yellow] {final_host}:{final_port}\n"
        f"📝 [dim]Logging enabled (Standard Output)[/dim]",
        title="Server Startup",
        expand=False
    ))

    try:
        uvicorn.run(
            "rgcc.server.api.app:app",
            host=final_host,
            port=final_port,
            reload=reload,
            log_level="info"
        )
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


@app.command()
def stop():
    """Stop the running build server."""
    pid = _get_pid()
    if not pid:
        console.print("[bold yellow]Warning:[/bold yellow] No running server found (missing rgccd.pid).")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"Stopping server (PID: [bold cyan]{pid}[/bold cyan])...")
        if PID_FILE.exists():
            PID_FILE.unlink()
    except OSError:
        console.print(f"[bold red]Error:[/bold red] Could not stop process {pid}. It might have already exited.")
        if PID_FILE.exists():
            PID_FILE.unlink()


@app.command()
def token(
    new: bool = typer.Option(False, "--new", help="Generate and save a fresh auth token")
):
    """View or regenerate the server authentication token."""
    cfg = load_server_config()
    
    if new:
        new_token = secrets.token_urlsafe(32)
        if "server" not in cfg:
            cfg["server"] = {}
        cfg["server"]["auth_token"] = new_token
        
        with open(SERVER_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False)
        
        console.print("\n✨ [bold green]New Token Generated and Saved![/bold green]")
        console.print(Panel(f"[bold yellow]{new_token}[/bold yellow]", title="RGCC Auth Token", expand=False))
    else:
        current_token = cfg.get("server", {}).get("auth_token", "NOT_SET")
        console.print("\n🔑 [bold cyan]Current Auth Token:[/bold cyan]")
        console.print(Panel(f"[bold yellow]{current_token}[/bold yellow]", title="RGCC Auth Token", expand=False))


@app.command()
def stats():
    """Show server status and metadata."""
    cfg = load_server_config()
    pid = _get_pid()
    
    table = Table(title="RGCC Server Status", show_header=False, expand=False)
    table.add_row("Version", f"[cyan]{__version__}[/cyan]")
    table.add_row("Status", "[bold green]Running[/bold green]" if pid else "[bold dim]Stopped[/bold dim]")
    if pid:
        table.add_row("PID", str(pid))
    table.add_row("Config Path", str(SERVER_CONFIG_PATH))
    table.add_row("Host", cfg.get("server", {}).get("host", "0.0.0.0"))
    table.add_row("Port", str(cfg.get("server", {}).get("port", 4444)))
    
    console.print(table)


def main():
    """Entry point for the rgccd command."""
    app()


if __name__ == "__main__":
    main()
