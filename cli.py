#!/usr/bin/env python3
"""
Enhanced CLI for PostgreSQL Docker container management.
"""

import os
import sys


def _resolve_script_dir():
    """Find the script directory even if the current working directory is missing."""
    if os.path.isabs(__file__):
        return os.path.dirname(__file__)

    pwd = os.environ.get("PWD")
    if pwd and os.path.isdir(pwd):
        candidate = os.path.normpath(os.path.join(pwd, __file__))
        if os.path.exists(candidate):
            return os.path.dirname(candidate)
        return pwd

    try:
        cwd_link = os.readlink("/proc/self/cwd")
        if cwd_link.endswith(" (deleted)"):
            cwd_link = cwd_link[:-10]
        if os.path.isdir(cwd_link):
            candidate = os.path.join(cwd_link, __file__)
            if os.path.exists(candidate):
                return os.path.dirname(candidate)
            return cwd_link
    except OSError:
        pass

    return os.path.dirname(sys.executable) or "/"


def _ensure_cwd_exists():
    """Recover if the current working directory was removed."""
    try:
        os.getcwd()
    except FileNotFoundError:
        os.chdir(_resolve_script_dir())
    if sys.path and sys.path[0] in ("", "."):
        sys.path[0] = os.getcwd()


_ensure_cwd_exists()

import subprocess
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

app = typer.Typer(
    name="postgres-cli",
    help="Enhanced CLI for managing PostgreSQL Docker container",
    add_completion=False,
)
console = Console()

# Configuration
PROJECT_ROOT = Path(__file__).parent.resolve()
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
SERVICE_NAME = "postgres"
DB_USER = os.getenv("DB_USER", "devops")
DEFAULT_DB = os.getenv("DEFAULT_DB", "postgres")


def require_tools():
    """Check if required tools are available."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[red]Error: docker is required but not found in PATH.[/red]")
        raise typer.Exit(1)

    try:
        subprocess.run(
            ["docker", "compose", "version"], capture_output=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[red]Error: docker compose is required but not found.[/red]")
        raise typer.Exit(1)


def docker_compose(*args):
    """Run docker compose command."""
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_service_running():
    """Ensure the PostgreSQL service is running."""
    result = docker_compose("ps", "--services", "--filter", "status=running")
    if result.returncode != 0 or SERVICE_NAME not in result.stdout.splitlines():
        console.print(
            f"[red]Service '{SERVICE_NAME}' is not running. Start it with 'docker compose up -d'.[/red]"
        )
        raise typer.Exit(1)


def quote_identifier(value: str) -> str:
    """Quote a PostgreSQL identifier, including embedded double quotes."""
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Quote a PostgreSQL string independently of standard_conforming_strings."""
    return "E'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def run_psql_command(database: str, command: str, capture_output: bool = False):
    """Run a psql command in the container."""
    ensure_service_running()
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        SERVICE_NAME,
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        DB_USER,
        "-d",
        database,
        "-c",
        command,
    ]
    result = subprocess.run(cmd, capture_output=capture_output, text=True)
    return result


def run_psql_file(database: str, path: Path):
    """Stream SQL through stdin to preserve psql directives and avoid size limits."""
    ensure_service_running()
    with path.open("rb") as source:
        return subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T",
             SERVICE_NAME, "psql", "-X", "-v", "ON_ERROR_STOP=1",
             "-U", DB_USER, "-d", database, "-f", "-"],
            stdin=source,
        )


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """PostgreSQL Docker Container CLI"""
    require_tools()
    if not COMPOSE_FILE.exists():
        console.print(f"[red]docker-compose.yml not found at {COMPOSE_FILE}[/red]")
        raise typer.Exit(1)

    # Show help if no command is provided
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


database_app = typer.Typer()
app.add_typer(database_app, name="database", help="Database management commands")


@database_app.callback(invoke_without_command=True)
def database_main(ctx: typer.Context):
    """Database management commands."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


user_app = typer.Typer()
app.add_typer(user_app, name="user", help="User management commands")


@user_app.callback(invoke_without_command=True)
def user_main(ctx: typer.Context):
    """User management commands."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


@user_app.command("list")
def list_users():
    """List all database users."""
    ensure_service_running()
    result = run_psql_command(
        DEFAULT_DB,
        'SELECT usename AS "Username", '
        "CASE WHEN usesuper THEN 'Yes' ELSE 'No' END AS \"Superuser\", "
        "CASE WHEN usecreatedb THEN 'Yes' ELSE 'No' END AS \"Create DB\" "
        "FROM pg_user WHERE usename NOT LIKE 'pg_%' ORDER BY usename;",
        capture_output=True,
    )

    if result.returncode != 0:
        console.print(f"[red]Error listing users: {result.stderr}[/red]")
        raise typer.Exit(1)

    lines = result.stdout.strip().split("\n")
    if len(lines) < 3:
        console.print("[yellow]No users found.[/yellow]")
        return

    table = Table(title="Database Users")
    table.add_column("Username", style="cyan", no_wrap=True)
    table.add_column("Superuser", style="magenta")
    table.add_column("Create DB", style="green")

    for line in lines[2:]:
        if line.strip():
            parts = line.strip().split("|")
            if len(parts) == 3:
                table.add_row(parts[0].strip(), parts[1].strip(), parts[2].strip())

    console.print(table)


@user_app.command("create")
def create_user(
    username: Optional[str] = typer.Argument(None, help="Username"),
    password: Optional[str] = typer.Option(
        None, "--password", "-p", help="Password (prompts if not provided)"
    ),
    superuser: bool = typer.Option(
        False, "--superuser", "-s", help="Grant superuser privileges"
    ),
    create_db: bool = typer.Option(
        False, "--createdb", help="Grant database creation privileges"
    ),
):
    """Create a new database user."""
    if not username:
        username = Prompt.ask("Username")

    if not username:
        console.print("[red]Username is required.[/red]")
        raise typer.Exit(1)

    if not password:
        password = Prompt.ask("Password", password=True)

    if not password:
        console.print("[red]Password is required.[/red]")
        raise typer.Exit(1)

    ensure_service_running()

    privileges = []
    if superuser:
        privileges.append("SUPERUSER")
    else:
        privileges.append("NOSUPERUSER")

    if create_db:
        privileges.append("CREATEDB")
    else:
        privileges.append("NOCREATEDB")

    privileges_str = " ".join(privileges)
    command = f"CREATE USER {quote_identifier(username)} WITH PASSWORD {quote_literal(password)} {privileges_str};"

    result = run_psql_command(DEFAULT_DB, command)

    if result.returncode == 0:
        console.print(f"[green]✓ Created user '{username}'[/green]")
    else:
        console.print(f"[red]Error creating user: {result.stderr}[/red]")
        raise typer.Exit(1)


@user_app.command("password")
def set_password(
    username: Optional[str] = typer.Argument(None, help="Username"),
    password: Optional[str] = typer.Option(
        None, "--password", "-p", help="New password (prompts if not provided)"
    ),
):
    """Set or reset a user's password."""
    if not username:
        username = Prompt.ask("Username")

    if not username:
        console.print("[red]Username is required.[/red]")
        raise typer.Exit(1)

    if not password:
        password = Prompt.ask("New password", password=True)

    if not password:
        console.print("[red]Password is required.[/red]")
        raise typer.Exit(1)

    ensure_service_running()
    command = f"ALTER USER {quote_identifier(username)} WITH PASSWORD {quote_literal(password)};"

    result = run_psql_command(DEFAULT_DB, command)

    if result.returncode == 0:
        console.print(f"[green]✓ Password updated for user '{username}'[/green]")
    else:
        console.print(f"[red]Error updating password: {result.stderr}[/red]")
        raise typer.Exit(1)


@user_app.command("drop")
def drop_user(
    username: Optional[str] = typer.Argument(None, help="Username"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Drop a database user."""
    if not username:
        username = Prompt.ask("Username to drop")

    if not username:
        console.print("[red]Username is required.[/red]")
        raise typer.Exit(1)

    # Prevent dropping the default admin user
    if username == DB_USER:
        console.print(f"[red]Cannot drop the default admin user '{DB_USER}'.[/red]")
        raise typer.Exit(1)

    if not force:
        if not Confirm.ask(
            f"Are you sure you want to drop user '{username}'? This action cannot be undone."
        ):
            console.print("[yellow]Operation cancelled.[/yellow]")
            return

    ensure_service_running()
    command = f"DROP USER {quote_identifier(username)};"

    result = run_psql_command(DEFAULT_DB, command)

    if result.returncode == 0:
        console.print(f"[green]✓ Dropped user '{username}'[/green]")
    else:
        console.print(f"[red]Error dropping user: {result.stderr}[/red]")
        raise typer.Exit(1)


@database_app.command("list")
def list_databases():
    """List all non-template databases."""
    ensure_service_running()
    result = docker_compose(
        "exec", "-T", SERVICE_NAME, "psql", "-X", "-A", "-t",
        "-U", DB_USER, "-d", DEFAULT_DB, "-c",
        "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;",
    )

    if result.returncode != 0:
        console.print(f"[red]Error listing databases: {result.stderr}[/red]")
        raise typer.Exit(1)

    # Parse and display results in a table
    lines = result.stdout.strip().split("\n")
    if not result.stdout.strip():
        console.print("[yellow]No databases found.[/yellow]")
        return

    table = Table(title="Databases")
    table.add_column("Database", style="cyan", no_wrap=True)

    for line in lines:
        if line.strip():
            table.add_row(line.strip())

    console.print(table)


@database_app.command("create")
def create_database(name: Optional[str] = typer.Argument(None, help="Database name")):
    """Create a new database."""
    if not name:
        name = Prompt.ask("Database name")

    if not name:
        console.print("[red]Database name is required.[/red]")
        raise typer.Exit(1)

    ensure_service_running()
    result = docker_compose("exec", "-T", SERVICE_NAME, "createdb", "-U", DB_USER, "--", name)

    if result.returncode == 0:
        console.print(f"[green]✓ Created database '{name}'[/green]")
    else:
        console.print(f"[red]Error creating database: {result.stderr}[/red]")
        raise typer.Exit(1)


@database_app.command("drop")
def drop_database(
    name: Optional[str] = typer.Argument(None, help="Database name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Drop a database."""
    if not name:
        name = Prompt.ask("Database name to drop")

    if not name:
        console.print("[red]Database name is required.[/red]")
        raise typer.Exit(1)

    if not force:
        if not Confirm.ask(
            f"Are you sure you want to drop database '{name}'? This action cannot be undone."
        ):
            console.print("[yellow]Operation cancelled.[/yellow]")
            return

    ensure_service_running()
    result = docker_compose("exec", "-T", SERVICE_NAME, "dropdb", "-U", DB_USER, "--", name)

    if result.returncode == 0:
        console.print(f"[green]✓ Dropped database '{name}'[/green]")
    else:
        console.print(f"[red]Error dropping database: {result.stderr}[/red]")
        raise typer.Exit(1)


@database_app.command("backup")
def backup_database(
    name: Optional[str] = typer.Argument(None, help="Database name"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create a backup of a database."""
    if not name:
        name = Prompt.ask("Database name to backup")

    if not name:
        console.print("[red]Database name is required.[/red]")
        raise typer.Exit(1)

    if not output:
        backup_dir = PROJECT_ROOT / "backups"
        backup_dir.mkdir(exist_ok=True)
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        output = str(backup_dir / f"{safe_name}_{timestamp}.sql")

    ensure_service_running()
    # Write bytes directly to avoid Windows encoding and newline conversions.
    output_path = Path(output)
    with NamedTemporaryFile(dir=output_path.parent, prefix=output_path.name + ".",
                            suffix=".tmp", delete=False) as destination:
        temporary_path = Path(destination.name)
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T",
                 SERVICE_NAME, "pg_dump", "-U", DB_USER, "--", name],
                stdout=destination, stderr=subprocess.PIPE,
            )
        except BaseException:
            destination.close()
            temporary_path.unlink(missing_ok=True)
            raise

    try:
        if result.returncode == 0:
            temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    if result.returncode == 0:
        console.print(f"[green]✓ Backup saved to {output}[/green]")
    else:
        console.print(f"[red]Error creating backup: {result.stderr.decode(errors='replace')}[/red]")
        raise typer.Exit(1)


@database_app.command("restore")
def restore_database(
    name: Optional[str] = typer.Argument(None, help="Target database name"),
    backup_file: str = typer.Argument(..., help="Backup file path"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Drop and recreate database if it exists"
    ),
):
    """Restore a database from backup."""
    if not name:
        name = Prompt.ask("Target database name")

    if not name:
        console.print("[red]Database name is required.[/red]")
        raise typer.Exit(1)

    backup_path = Path(backup_file)
    if not backup_path.is_file():
        console.print(f"[red]Backup file not found: {backup_file}[/red]")
        raise typer.Exit(1)

    ensure_service_running()

    # Check if database exists
    result = docker_compose(
        "exec", "-T", SERVICE_NAME, "psql", "-X", "-A", "-t",
        "-U", DB_USER, "-d", DEFAULT_DB, "-c",
        f"SELECT 1 FROM pg_database WHERE datname = {quote_literal(name)};",
    )

    if result.returncode != 0:
        console.print(f"[red]Error checking database: {result.stderr}[/red]")
        raise typer.Exit(1)
    db_exists = result.stdout.strip() == "1"

    if db_exists:
        if not force and not Confirm.ask(f"Database '{name}' already exists. Drop and recreate it?"):
            console.print("[yellow]Operation cancelled.[/yellow]")
            return
        # Drop existing database
        drop_result = docker_compose(
            "exec", "-T", SERVICE_NAME, "dropdb", "-U", DB_USER, "--", name
        )
        if drop_result.returncode != 0:
            console.print(
                f"[red]Error dropping existing database: {drop_result.stderr}[/red]"
            )
            raise typer.Exit(1)

    create_result = docker_compose(
        "exec", "-T", SERVICE_NAME, "createdb", "-U", DB_USER, "--", name
    )
    if create_result.returncode != 0:
        console.print(f"[red]Error creating database: {create_result.stderr}[/red]")
        raise typer.Exit(1)

    # Restore from backup
    restore_result = run_psql_file(name, backup_path)

    if restore_result.returncode == 0:
        console.print(f"[green]✓ Database '{name}' restored from {backup_file}[/green]")
    else:
        console.print(f"[red]Error restoring database: {restore_result.stderr}[/red]")
        raise typer.Exit(1)


@app.command("sql")
def run_sql(
    database: str = typer.Option(
        DEFAULT_DB, "--database", "-d", help="Target database"
    ),
    command: Optional[str] = typer.Option(
        None, "--command", "-c", help="SQL command to execute"
    ),
    file: Optional[str] = typer.Option(
        None, "--file", "-f", help="SQL file to execute"
    ),
):
    """Execute SQL commands."""
    if command and file:
        console.print("[red]Please provide either --command or --file, not both.[/red]")
        raise typer.Exit(1)

    if not command and not file:
        command = Prompt.ask("SQL command")

    if not command and not file:
        console.print("[red]No SQL command provided.[/red]")
        raise typer.Exit(1)

    if file:
        file_path = Path(file)
        if not file_path.is_file():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        result = run_psql_file(database, file_path)
    else:
        result = run_psql_command(database, command)
    if result.returncode != 0:
        raise typer.Exit(1)


@app.command("shell")
def open_shell(database: str = typer.Argument(DEFAULT_DB, help="Database name")):
    """Open an interactive psql shell."""
    ensure_service_running()
    console.print(
        f"[blue]Connecting to database '{database}'... (press Ctrl+D to exit)[/blue]"
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "exec",
            SERVICE_NAME,
            "psql",
            "-U",
            DB_USER,
            "-d",
            database,
        ]
    )
    if result.returncode != 0:
        raise typer.Exit(1)


@app.command("status")
def show_status():
    """Show container status."""
    result = docker_compose("ps", "--format", "json")

    if result.returncode == 0:
        raw = result.stdout.strip()
        if raw:
            containers = json.loads(raw) if raw.startswith("[") else [
                json.loads(line) for line in raw.splitlines() if line.strip()
            ]
            table = Table(title="Container Status")
            table.add_column("Name", style="cyan")
            table.add_column("Command", style="magenta")
            table.add_column("Status", style="green")
            table.add_column("Ports", style="yellow")

            for container in containers:
                table.add_row(container.get("Name", ""), container.get("Command", ""),
                              container.get("Status", ""), container.get("Ports", ""))

            console.print(table)
        else:
            console.print("[yellow]No containers found.[/yellow]")
    else:
        console.print(f"[red]Error getting status: {result.stderr}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
