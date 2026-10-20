"""Exercise the updater with real just recipes in temporary directories."""

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "daily-update-cubrid.py"


@unittest.skipUnless(shutil.which("just"), "just is required")
class DailyUpdateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = self.root / "sync.log"
        self.env = dict(os.environ, DAILY_UPDATE_TEST_LOG=str(self.log))

    def run_cli(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            cwd=self.root,
            env=self.env if env is None else env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def project(self, name, exit_code=0):
        project = self.root / name
        project.mkdir()
        (project / "justfile").write_text(
            "sync:\n"
            f"    @printf '%s\\n' {shlex.quote(name)} >> \"$DAILY_UPDATE_TEST_LOG\"\n"
            f"    @exit {exit_code}\n"
        )
        return project

    def test_default_list_contains_only_the_tui(self):
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(Path.home() / "gh/cubrid-conf-tui"))
        self.assertFalse(self.log.exists())

    def test_runs_in_each_checkout_and_deduplicates_directories(self):
        first = self.project("first project")
        second = self.project("second; literal")
        result = self.run_cli(first, first, second)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.log.read_text(), "first project\nsecond; literal\n")

    def test_failure_and_missing_directory_do_not_stop_remaining_projects(self):
        first = self.project("fails", 7)
        second = self.project("works")
        result = self.run_cli(first, self.root / "missing", second)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.log.read_text(), "fails\nworks\n")
        self.assertIn("fails", result.stderr)
        self.assertIn("missing", result.stderr)
        self.assertIn("works: updated", result.stdout)

    def test_never_falls_back_to_a_parent_justfile(self):
        self.project("parent")
        child = self.root / "parent/child"
        child.mkdir()
        result = self.run_cli(child)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("local justfile", result.stdout)
        self.assertFalse(self.log.exists())

    def test_missing_sync_recipe_is_a_failure(self):
        project = self.project("no sync")
        (project / "justfile").write_text("other:\n    @true\n")
        result = self.run_cli(project)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Failed projects:", result.stderr)
        self.assertFalse(self.log.exists())

    def test_dry_run_does_not_execute_recipes(self):
        project = self.project("preview")
        result = self.run_cli("--dry-run", project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("./justfile sync", result.stdout)
        self.assertFalse(self.log.exists())

    def test_missing_just_reports_an_actionable_error(self):
        project = self.project("tool")
        result = self.run_cli(project, env=dict(self.env, PATH=str(self.root)))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("just is not installed or not on PATH", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
