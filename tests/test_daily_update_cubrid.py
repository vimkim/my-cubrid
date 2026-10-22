"""Exercise the updater with real Git remotes and Just in disposable homes."""

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
GIT = shutil.which("git")


@unittest.skipUnless(GIT and shutil.which("just"), "git and just are required")
class DailyUpdateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.log = self.root / "sync.log"
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            DAILY_UPDATE_TEST_LOG=str(self.log),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_AUTHOR_NAME="Test",
            GIT_AUTHOR_EMAIL="test@example.invalid",
            GIT_COMMITTER_NAME="Test",
            GIT_COMMITTER_EMAIL="test@example.invalid",
        )
        self.seeds = {}
        self.remotes = {}
        tool_bin = self.root / "bin"
        tool_bin.mkdir()
        uv = tool_bin / "uv"
        uv.write_text(
            '#!/bin/sh\n'
            '[ "$*" = "tool install --reinstall ." ] || exit 9\n'
            'test "$(cat revision)" = "${DAILY_UPDATE_TEST_REVISION:-before}" || exit 9\n'
            'printf "cubrid-qahome\\n" >> "$DAILY_UPDATE_TEST_LOG"\n'
            'exit "${DAILY_UPDATE_TEST_UV_RESULT:-0}"\n'
        )
        uv.chmod(0o755)
        self.env["PATH"] = str(tool_bin) + os.pathsep + os.environ["PATH"]

    def git(self, project, *args):
        return subprocess.run(
            [GIT, "-C", str(project), *map(str, args)],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def commit(self, project, message="change"):
        self.git(project, "add", ".")
        self.git(project, "commit", "-m", message)

    def run_cli(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            cwd=self.root,
            env=self.env if env is None else env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def project(self, name, exit_code=0, relative=None):
        number = len(self.seeds)
        remote = self.root / f"remote-{number}.git"
        seed = self.root / f"seed-{number}"
        self.git(self.root, "init", "--bare", "--initial-branch=main", remote)
        self.git(self.root, "clone", remote, seed)
        (seed / "revision").write_text("before")
        (seed / "justfile").write_text(
            "sync:\n"
            f"    @printf '%s\\n' {shlex.quote(name)} >> \"$DAILY_UPDATE_TEST_LOG\"\n"
            '    @test "$(cat revision)" = "${DAILY_UPDATE_TEST_REVISION:-before}"\n'
            f"    @exit {exit_code}\n"
            "\ninstall: sync\n"
        )
        self.commit(seed, "initial")
        self.git(seed, "push", "-u", "origin", "main")
        project = self.home / relative if relative else self.root / name
        project.parent.mkdir(parents=True, exist_ok=True)
        self.git(self.root, "clone", remote, project)
        self.seeds[project] = seed
        self.remotes[project] = remote
        if relative:
            official = f"https://github.com/vimkim/{name}.git"
            self.git(project, "config", f"url.{remote}.insteadOf", official)
            self.git(project, "config", "remote.origin.url", official)
        return project

    def advance(self, project):
        seed = self.seeds[project]
        (seed / "revision").write_text("after")
        self.commit(seed, "advance")
        self.git(seed, "push")

    def test_default_list_contains_all_registered_tools(self):
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            str(self.home / "gh/cubrid-conf-tui"),
            str(self.home / "gh/cubrid-build-coordinator"),
            str(self.home / "gh/cubrid-workenv"),
            str(self.home / "gh/cubrid-jira"),
            str(self.home / "gh/cubrid-ci"),
            str(self.home / "gh/cubrid-qahome-fetcher"),
        ])
        self.assertFalse(self.log.exists())

    def test_default_run_syncs_all_registered_tools(self):
        tools = {
            "cubrid-conf-tui": "gh/cubrid-conf-tui",
            "cubrid-build-coordinator": "gh/cubrid-build-coordinator",
            "cubrid-workenv": "gh/cubrid-workenv",
            "cubrid-jira": "gh/cubrid-jira",
            "cubrid-ci": "gh/cubrid-ci",
            "cubrid-qahome": "gh/cubrid-qahome-fetcher",
        }
        for tool, relative in tools.items():
            self.project(tool, relative=relative)
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), list(tools))

    def test_uv_installation_error_is_a_failure_and_other_tools_continue(self):
        project = self.project("cubrid-qahome", relative="gh/cubrid-qahome-fetcher")
        other = self.project("other")
        result = self.run_cli(
            project, other, env=dict(self.env, DAILY_UPDATE_TEST_UV_RESULT="2")
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("installation exited 2", result.stdout)
        self.assertEqual(self.log.read_text(), "cubrid-qahome\nother\n")

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
        self.commit(project)
        self.git(project, "push")
        result = self.run_cli(project)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Failed projects:", result.stderr)
        self.assertFalse(self.log.exists())

    def test_fetch_and_fast_forward_precede_installation(self):
        project = self.project("tool")
        self.advance(project)
        result = self.run_cli(project, env=dict(self.env, DAILY_UPDATE_TEST_REVISION="after"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((project / "revision").read_text(), "after")
        self.assertEqual(self.git(project, "rev-parse", "HEAD"), self.git(self.seeds[project], "rev-parse", "HEAD"))
        self.assertEqual(self.log.read_text(), "tool\n")

    def test_dirty_checkouts_are_preserved_and_other_tools_continue(self):
        for tracked in (True, False):
            with self.subTest(tracked=tracked):
                project = self.project(f"dirty-{tracked}")
                filename = "revision" if tracked else "scratch"
                (project / filename).write_text("local work")
                self.advance(project)
                other = self.project(f"other-{tracked}")
                result = self.run_cli(project, other)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("dirty checkout", result.stdout)
                self.assertEqual((project / filename).read_text(), "local work")
                self.assertNotIn(f"{project.name}\n", self.log.read_text())
                self.assertIn(f"{other.name}\n", self.log.read_text())

    def test_ahead_and_diverged_checkouts_are_never_installed(self):
        for diverged in (True, False):
            with self.subTest(diverged=diverged):
                project = self.project(f"local-{diverged}")
                (project / "local").write_text("preserve me")
                self.commit(project)
                before = self.git(project, "rev-parse", "HEAD")
                if diverged:
                    self.advance(project)
                result = self.run_cli(project)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("ahead or diverged", result.stdout)
                self.assertEqual(self.git(project, "rev-parse", "HEAD"), before)
                self.assertFalse(self.log.exists())

    def test_topic_detached_and_untracked_branches_are_skipped(self):
        changes = (
            ("topic", ("switch", "-c", "topic")),
            ("detached", ("checkout", "--detach")),
            ("no-upstream", ("branch", "--unset-upstream")),
        )
        for name, command in changes:
            with self.subTest(name=name):
                project = self.project(name)
                self.git(project, *command)
                result = self.run_cli(project)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("main tracking origin/main", result.stdout)
                self.assertFalse(self.log.exists())

    def test_linked_and_symlinked_checkouts_are_skipped(self):
        primary = self.project("primary")
        linked = self.root / "linked"
        self.git(primary, "worktree", "add", "--detach", linked)
        symlink = self.root / "symlink"
        symlink.symlink_to(primary, target_is_directory=True)
        for project in (linked, symlink):
            with self.subTest(project=project):
                result = self.run_cli(project)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("independent primary checkout", result.stdout)
                self.assertFalse(self.log.exists())

    def test_default_checkout_with_wrong_origin_is_skipped(self):
        self.project("cubrid-ci", relative="gh/cubrid-ci")
        project = self.home / "gh/cubrid-ci"
        self.git(project, "config", "remote.origin.url", "https://github.com/someone/other.git")
        result = self.run_cli(project)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("unexpected origin", result.stdout)
        self.assertFalse(self.log.exists())

    def test_missing_remote_main_prevents_installation_from_stale_ref(self):
        project = self.project("stale")
        self.git(self.remotes[project], "update-ref", "-d", "refs/heads/main")
        result = self.run_cli(project)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fetch failed", result.stdout)
        self.assertFalse(self.log.exists())

    def test_fetch_failure_does_not_stop_other_projects(self):
        project = self.project("offline")
        self.git(project, "config", "remote.origin.url", str(self.root / "missing.git"))
        other = self.project("working")
        result = self.run_cli(project, other)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fetch failed", result.stdout)
        self.assertEqual(self.log.read_text(), "working\n")

    def test_non_checkout_never_installs(self):
        directory = self.root / "not-git"
        directory.mkdir()
        (directory / "justfile").write_text("sync:\n    @touch forbidden\n")
        result = self.run_cli(directory)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse((directory / "forbidden").exists())

    def test_recipe_removed_upstream_never_falls_back_to_parent(self):
        project = self.project("removed-recipe")
        seed = self.seeds[project]
        (seed / "justfile").unlink()
        self.commit(seed)
        self.git(seed, "push")
        (self.root / "justfile").write_text("sync:\n    @touch forbidden\n")
        result = self.run_cli(project)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("missing local justfile after refresh", result.stdout)
        self.assertFalse((self.root / "forbidden").exists())

    def test_dry_run_does_not_fetch_merge_or_install(self):
        project = self.project("preview-update")
        before = self.git(project, "rev-parse", "origin/main")
        self.advance(project)
        result = self.run_cli("--dry-run", project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("git fetch", result.stdout)
        self.assertIn("git merge --ff-only", result.stdout)
        self.assertEqual((project / "revision").read_text(), "before")
        self.assertEqual(self.git(project, "rev-parse", "origin/main"), before)
        self.assertFalse(self.log.exists())

    def test_partial_sync_returns_two_and_continues(self):
        partial = self.project("partial", 2)
        other = self.project("complete")
        result = self.run_cli(partial, other)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("partial/skipped", result.stdout)
        self.assertEqual(self.log.read_text(), "partial\ncomplete\n")

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
