# PostgreSQL utilities for Windows

Run PostgreSQL 16 in Docker and manage databases, users, SQL files, and backups
with a Python CLI. The host port binds to `127.0.0.1:5432` for local development.

## Requirements

- Docker Desktop running with Linux containers and Docker Compose v2.
- Python 3.12 (the Windows `py` launcher or `python` on PATH).

## Quickstart (PowerShell)

```powershell
Copy-Item .env.example .env
# Edit .env and choose a local password before starting PostgreSQL.
docker compose up -d
docker compose ps
.\scripts\run-cli.ps1 --help
.\scripts\run-cli.ps1 sql --database test --command "SELECT version();"
```

The default user is `devops`, and the initial database is `test`. The password
comes from your local `.env`. PostgreSQL data is stored in `./data`.

Stop the service without removing its data:

```powershell
docker compose down
```

The image's `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` settings apply
only when initializing an empty data directory. Editing `.env` does not change
credentials or databases in an existing cluster. Change existing passwords with
the CLI's `user password` command and update `.env` to match.

## CLI usage

On first use, the Windows wrappers create `.venv` and install `requirements.txt`.
PowerShell and CMD accept the same CLI arguments:

```powershell
.\scripts\run-cli.ps1 database list
.\scripts\run-cli.ps1 database create mydb
.\scripts\run-cli.ps1 database drop mydb
.\scripts\run-cli.ps1 database backup mydb
.\scripts\run-cli.ps1 database restore mydb .\backups\mydb_backup.sql
.\scripts\run-cli.ps1 user list
.\scripts\run-cli.ps1 user create myuser
.\scripts\run-cli.ps1 user password myuser
.\scripts\run-cli.ps1 user drop myuser
.\scripts\run-cli.ps1 sql --database mydb --command "SELECT version();"
.\scripts\run-cli.ps1 sql --database mydb --file .\scripts\example.sql
.\scripts\run-cli.ps1 shell mydb
.\scripts\run-cli.ps1 status
```

User creation and password changes prompt for a hidden password unless
`--password` is supplied. Use `user create --superuser` or `--createdb` to grant
those privileges. Drop commands ask for confirmation; `--force` skips it.
Restoring an existing database drops and recreates it after confirmation;
`database restore --force` skips that confirmation. Back up anything you need
before replacing a database.

Backups are plain SQL files in `./backups` by default. Use
`database backup --output <path>` to choose a destination. Restore and
`sql --file` stream files to `psql` and stop on the first SQL error. A failed
restore can leave a partially loaded database; correct the error before retrying.

In CMD:

```cmd
scripts\run-cli.cmd --help
scripts\run-cli.cmd database list
```

If PowerShell blocks script execution:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-cli.ps1 --help
```

To install and run the CLI directly:

```powershell
py -3 -m pip install -r requirements.txt
py -3 .\cli.py --help
```

The CLI locates Compose relative to its own file, so the wrappers also work
from other directories. It connects inside the container as `devops` using
`postgres` for administrative queries. If you customize the initial user, set
`DB_USER` in the calling shell. Set `DEFAULT_DB` to change the CLI's default
database:

```powershell
$env:DB_USER = "myadmin"
$env:DEFAULT_DB = "test"
```

## Direct database access

From the host (requires `psql`; enter the password from `.env` when prompted):

```powershell
psql -h localhost -U devops -d test -c "SELECT version();"
```

Inside the container:

```powershell
docker exec -it dev_postgres psql -U devops -d postgres
```

Example SQL:

```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL
);
INSERT INTO users (name) VALUES ('Alice'), ('Bob');
SELECT * FROM users;
```

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
docker compose config --quiet
.\scripts\run-cli.ps1 sql --database test --command "SELECT version();"
```

Unit tests use mocked Docker commands and do not change a database.

## Local files

Git ignores `data/`, `backups/`, `.env`, virtual environments, Python caches,
and database exports in the repository root. Keep SQL source scripts under
`scripts/` so they can be versioned. `.env.example` contains shareable settings.

This setup is for local development; TLS is not configured. Existing containers
pick up the localhost port binding when recreated with `docker compose up -d`.
