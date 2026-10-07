"""Regression checks that never connect to a real PostgreSQL instance."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

import cli


def result(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, "test error" if returncode else "")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tools = patch.object(cli, "require_tools")
        self.tools.start()
        self.addCleanup(self.tools.stop)
        self.running = patch.object(cli, "ensure_service_running")
        self.running.start()
        self.addCleanup(self.running.stop)
        self.runner = CliRunner()

    def test_file_execution_and_error_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.sql"
            path.write_text("SELECT 1;", encoding="utf-8")
            with patch.object(cli, "run_psql_file", return_value=result(returncode=1)) as run:
                response = self.runner.invoke(cli.app, ["sql", "--file", str(path)])
            self.assertEqual(response.exit_code, 1, response.output)
            run.assert_called_once_with(cli.DEFAULT_DB, path)

    def test_sql_error_exit(self):
        with patch.object(cli, "run_psql_command", return_value=result(returncode=1)):
            response = self.runner.invoke(cli.app, ["sql", "--command", "invalid SQL"])
        self.assertEqual(response.exit_code, 1)

    def test_streamed_sql_preserves_copy_and_unicode(self):
        payload = "COPY sample FROM stdin;\nGrüße\n\\.\n".encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dump.sql"
            path.write_bytes(payload)

            def run(command, **kwargs):
                self.assertEqual(kwargs["stdin"].read(), payload)
                self.assertEqual(command[-2:], ["-f", "-"])
                self.assertIn("ON_ERROR_STOP=1", command)
                return result()

            with patch.object(cli.subprocess, "run", side_effect=run):
                self.assertEqual(cli.run_psql_file("sample", path).returncode, 0)

    def test_user_input_is_quoted(self):
        with patch.object(cli, "run_psql_command", return_value=result()) as run:
            response = self.runner.invoke(cli.app, [
                "user", "create", 'user"name', "--password", "a'b\\c",
            ])
        self.assertEqual(response.exit_code, 0, response.output)
        self.assertEqual(run.call_args.args[1],
                         'CREATE USER "user""name" WITH PASSWORD E\'a\'\'b\\\\c\' NOSUPERUSER NOCREATEDB;')

    def test_failed_backup_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.sql"
            path.write_bytes(b"previous backup")

            def run(command, **kwargs):
                kwargs["stdout"].write(b"partial dump")
                return subprocess.CompletedProcess(command, 1, None, b"dump failed")

            with patch.object(cli.subprocess, "run", side_effect=run):
                response = self.runner.invoke(cli.app, [
                    "database", "backup", "sample", "--output", str(path),
                ])
            self.assertEqual(response.exit_code, 1, response.output)
            self.assertEqual(path.read_bytes(), b"previous backup")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_backup_preserves_unicode_bytes(self):
        payload = "Grüße\n".encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.sql"

            def run(command, **kwargs):
                kwargs["stdout"].write(payload)
                return subprocess.CompletedProcess(command, 0, None, b"")

            with patch.object(cli.subprocess, "run", side_effect=run):
                response = self.runner.invoke(cli.app, [
                    "database", "backup", "sample", "--output", str(path),
                ])
            self.assertEqual(response.exit_code, 0, response.output)
            self.assertEqual(path.read_bytes(), payload)

    def restore(self, exists, force=False, confirm=True, check_error=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dump.sql"
            path.write_text("SELECT 1;", encoding="utf-8")
            commands = []

            def compose(*args):
                commands.append(args)
                if "psql" in args:
                    return result("1\n" if exists else "", 1 if check_error else 0)
                return result()

            with patch.object(cli, "docker_compose", side_effect=compose), \
                    patch.object(cli.Confirm, "ask", return_value=confirm) as ask, \
                    patch.object(cli, "run_psql_file", return_value=result()) as restore:
                args = ["database", "restore", "sample", str(path)]
                if force:
                    args.append("--force")
                response = self.runner.invoke(cli.app, args)
            return response, commands, ask, restore

    def test_restore_new_database(self):
        response, commands, ask, restore = self.restore(exists=False)
        self.assertEqual(response.exit_code, 0, response.output)
        self.assertEqual([c[3] for c in commands], ["psql", "createdb"])
        ask.assert_not_called()
        restore.assert_called_once()

    def test_restore_existing_database_with_confirmation(self):
        response, commands, ask, restore = self.restore(exists=True)
        self.assertEqual(response.exit_code, 0, response.output)
        self.assertEqual([c[3] for c in commands], ["psql", "dropdb", "createdb"])
        ask.assert_called_once()
        restore.assert_called_once()

    def test_force_restore_drops_before_create(self):
        response, commands, ask, restore = self.restore(exists=True, force=True)
        self.assertEqual(response.exit_code, 0, response.output)
        self.assertEqual([c[3] for c in commands], ["psql", "dropdb", "createdb"])
        ask.assert_not_called()
        restore.assert_called_once()

    def test_cancelled_restore_does_not_change_database(self):
        response, commands, _, restore = self.restore(exists=True, confirm=False)
        self.assertEqual(response.exit_code, 0, response.output)
        self.assertEqual(len(commands), 1)
        restore.assert_not_called()

    def test_failed_database_check_does_not_change_database(self):
        response, commands, _, restore = self.restore(exists=False, check_error=True)
        self.assertEqual(response.exit_code, 1, response.output)
        self.assertEqual(len(commands), 1)
        restore.assert_not_called()


if __name__ == "__main__":
    unittest.main()
