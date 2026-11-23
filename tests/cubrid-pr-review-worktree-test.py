#!/usr/bin/env python3

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "cubrid-pr-review-worktree"
ADD_SCRIPT = ROOT / "bin" / "cubrid-worktree-add.sh"
JUSTFILE = ROOT / "cubrid-justfiles" / "justfile"

LOADER = importlib.machinery.SourceFileLoader("cubrid_pr_review_worktree", os.fspath(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = MODULE
LOADER.exec_module(MODULE)


class ReviewWorktreeWrapperTest(unittest.TestCase):
    def test_translates_arguments_and_preserves_default_no_prepare(self) -> None:
        captured: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0)

        with (
            mock.patch.object(MODULE.shutil, "which", return_value="/usr/local/bin/cubrid-worktree"),
            mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run),
        ):
            rc1 = MODULE.main(["https://github.com/CUBRID/cubrid/pull/7887"])
            rc2 = MODULE.main(["--interactive", "--prepare", "--no-focus"])
            rc3 = MODULE.main(["--all", "--prepare", "--dry-run"])

        self.assertEqual((rc1, rc2, rc3), (0, 0, 0))
        self.assertEqual(
            captured[0],
            ["/usr/local/bin/cubrid-worktree", "review", "https://github.com/CUBRID/cubrid/pull/7887", "--no-prepare"],
        )
        self.assertEqual(
            captured[1],
            ["/usr/local/bin/cubrid-worktree", "review", "--interactive", "--no-focus"],
        )
        self.assertEqual(
            captured[2],
            ["/usr/local/bin/cubrid-worktree", "review", "--all", "--dry-run"],
        )

    def test_missing_cubrid_worktree_reports_install_hint(self) -> None:
        stderr = StringIO()
        with (
            mock.patch.object(MODULE.shutil, "which", return_value=None),
            redirect_stderr(stderr),
        ):
            rc = MODULE.main(["--interactive"])
        self.assertEqual(rc, 1)
        self.assertIn("just install", stderr.getvalue())

    def test_requires_exactly_one_mode(self) -> None:
        with redirect_stderr(StringIO()):
            for bad in ([], ["--interactive", "7887"], ["--interactive", "--all"], ["--interactive", "--herdr", "--no-herdr"]):
                with self.subTest(bad=bad):
                    with self.assertRaises(SystemExit) as ctx:
                        MODULE.parse_args(bad)
                    self.assertEqual(ctx.exception.code, 2)

    def test_global_justfile_exposes_worktree_and_review_launchers(self) -> None:
        expected = {
            "worktree": "cubrid-worktree create",
            "worktree-open": "cubrid-worktree open",
            "worktree-list": "cubrid-worktree list",
            "pr-review": "cubrid-worktree review --interactive",
            "pr-review-all": "cubrid-worktree review --all",
        }
        for recipe, snippet in expected.items():
            with self.subTest(recipe=recipe):
                result = subprocess.run(
                    ["just", "--justfile", os.fspath(JUSTFILE), "--dry-run", recipe],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(snippet, result.stdout + result.stderr)

    def test_worktree_add_shim_delegates_to_cubrid_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "cb" / "develop"
            repo.mkdir(parents=True)
            subprocess.run(["git", "-C", os.fspath(repo), "init", "-b", "develop"], check=True, capture_output=True)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            log = root / "args.log"
            stub = fake_bin / "cubrid-worktree"
            stub.write_text(f"#!/usr/bin/env sh\nprintf '%s\\n' \"$@\" > {os.fspath(log)!r}\n")
            stub.chmod(0o755)
            env = dict(os.environ, PATH=f"{fake_bin}:{os.environ.get('PATH', '')}")
            result = subprocess.run(
                [os.fspath(ADD_SCRIPT), "CBRD-28099-exp", "feat/exp", "HEAD"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text().splitlines(),
                [
                    "create",
                    "CBRD-28099-exp",
                    "--branch",
                    "feat/exp",
                    "--base",
                    "HEAD",
                    "--control-dir",
                    os.fspath(repo.resolve()),
                    "--parent-dir",
                    os.fspath(repo.parent.resolve()),
                    "--no-fetch",
                    "--no-prepare",
                    "--no-herdr",
                ],
            )


if __name__ == "__main__":
    unittest.main()
