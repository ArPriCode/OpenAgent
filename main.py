import sys
import time
import argparse
import logging
import warnings

# Suppress minor ecosystem warnings for clean CLI output
warnings.filterwarnings("ignore")

import uvicorn
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config.settings import settings, load_repos_config
from core.orchestrator import AgentOrchestrator
from core.scheduler import TimeWindowScheduler

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def show_banner():
    console.print(Panel.fit(
        "[bold cyan]⚡ OS-Agent: Autonomous Open-Source Contribution System[/bold cyan]\n"
        "[dim]Powered by Gemini 2.0 (Coder) + Grok xAI (Comms) + PyGithub[/dim]\n"
        f"[yellow]Active Contribution Window:[/yellow] [bold green]{settings.WORK_WINDOW_START} - {settings.WORK_WINDOW_END}[/bold green] "
        f"[dim]({settings.TIMEZONE})[/dim]",
        border_style="blue"
    ))

def cmd_status():
    show_banner()
    sched = TimeWindowScheduler()
    is_active, msg = sched.is_active_now()
    repos = load_repos_config()

    table = Table(title="Agent System Status", border_style="cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Current Time", sched.get_current_time().strftime("%Y-%m-%d %H:%M:%S"))
    table.add_row("Active Window", f"{settings.WORK_WINDOW_START} - {settings.WORK_WINDOW_END}")
    table.add_row("Window Status", "[green]ACTIVE[/green]" if is_active else "[yellow]DORMANT/WAITING[/yellow]")
    table.add_row("Dry-Run Mode", "[yellow]Enabled (Safe)[/yellow]" if settings.DRY_RUN else "[red]Disabled (Live)[/red]")
    table.add_row("Human Approval Required", str(settings.REQUIRE_APPROVAL))
    table.add_row("Tracked Repositories", str(len([r for r in repos if r.enabled])))
    console.print(table)

def cmd_run(force: bool = False):
    show_banner()
    orchestrator = AgentOrchestrator()
    console.print(f"[bold yellow]Triggering contribution cycle (force={force})...[/bold yellow]")
    results = orchestrator.run_contribution_cycle(force=force)
    console.print("\n[bold green]Cycle Results:[/bold green]")
    console.print(results)

def cmd_daemon():
    show_banner()
    orchestrator = AgentOrchestrator()
    sched = TimeWindowScheduler()
    console.print("[bold green]OS-Agent Daemon started. Checking time window every 60 seconds...[/bold green]")
    console.print("[dim]Press Ctrl+C to terminate.[/dim]\n")

    while True:
        try:
            is_active, msg = sched.is_active_now()
            console.print(f"[{time.strftime('%H:%M:%S')}] {msg}")
            if is_active:
                orchestrator.run_contribution_cycle(force=False)
            time.sleep(60)
        except KeyboardInterrupt:
            console.print("\n[red]Daemon stopped by user.[/red]")
            break
        except Exception as e:
            console.print(f"[bold red]Daemon error:[/bold red] {e}")
            time.sleep(30)

def cmd_dashboard(host: str = "127.0.0.1", port: int = 8000):
    show_banner()
    console.print(f"[bold green]Starting Web Dashboard on http://{host}:{port}[/bold green]")
    console.print(f"[dim]Open your browser at http://{host}:{port} to view live status, configure repos, and review diffs.[/dim]")
    uvicorn.run("dashboard.app:app", host=host, port=port, reload=False)

def main():
    parser = argparse.ArgumentParser(description="OS-Agent: Autonomous Open-Source Contribution Framework")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # dashboard
    dash_p = subparsers.add_parser("dashboard", help="Start the interactive Web Dashboard")
    dash_p.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    dash_p.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")

    # run
    run_p = subparsers.add_parser("run", help="Execute a single contribution cycle")
    run_p.add_argument("--force", action="store_true", help="Force execution even if outside the scheduled time window")

    # daemon
    subparsers.add_parser("daemon", help="Run in continuous background loop respecting time windows")

    # status
    subparsers.add_parser("status", help="Display current agent configuration and status")

    args = parser.parse_args()
    if args.command == "dashboard":
        cmd_dashboard(args.host, args.port)
    elif args.command == "run":
        cmd_run(force=args.force)
    elif args.command == "daemon":
        cmd_daemon()
    elif args.command == "status":
        cmd_status()
    else:
        # Default action: launch dashboard if no args given
        cmd_dashboard()

if __name__ == "__main__":
    main()
