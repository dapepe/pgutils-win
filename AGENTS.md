# Repository Guidelines

## Project Structure & Module Organization
- `docker-compose.yml` holds the PostgreSQL 16 service definition, port mapping, and environment defaults. Update this file when adding extensions or more services.
- `data/` mirrors Postgres’ data directory (`base/`, `pg_wal/`, config files). Treat it as disposable in local dev; do not hand-edit internal subfolders.
- `README.md` provides developer-facing connection info. Keep examples in sync with any password or database changes.

## Build, Test, and Development Commands
- `docker compose up -d` boots the container in detached mode; use it for day-to-day development.
- `docker compose down` stops the container and leaves the data folder intact.
- `docker compose ps` surfaces container health and exit codes.
- `docker exec -it dev_postgres psql -U devops -d postgres` opens an interactive psql shell inside the running container.
- `psql -h localhost -U devops -d test -c "SELECT version();"` is the quickest smoke check from the host.

## Coding Style & Naming Conventions
- Compose YAML uses two-space indentation and lowercase service keys (`postgres`). Maintain uppercase for environment variables such as `POSTGRES_USER`.
- Configuration files under `data/` stay in PostgreSQL’s default format; prefer editing via SQL commands or `ALTER SYSTEM` statements rather than manual edits.
- Name additional helper scripts with descriptive kebab-case (e.g., `scripts/init-extensions.sh`) and document them in the README.

## Testing Guidelines
- Run the smoke check query after configuration changes and record results in the PR description.
- For schema migrations, execute `psql -f` scripts against the running container and confirm a clean rerun to ensure idempotency.
- Consider adding lightweight psql scripts under a future `scripts/` directory for repeatable validation.

## Commit & Pull Request Guidelines
- Write commit subjects in the imperative mood (`Add logical replication slot`) and limit to ~72 characters.
- Reference impacted services or configs in the body (e.g., `docker-compose.yml`, `data/postgresql.conf`).
- Pull requests should outline configuration changes, include the smoke-check output, and call out any manual steps such as purging `data/`.
- Link tracking issues when available and request review from another operator before merging.

## Security & Configuration Tips
- Never commit real production credentials; rotate the sample password if shared externally.
- When testing destructive changes, back up `data/` or point the volume at a throwaway directory.
