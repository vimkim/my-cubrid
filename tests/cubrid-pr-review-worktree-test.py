#!/usr/bin/env python3

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "cubrid-pr-review-worktree"
JUSTFILE = Path(__file__).resolve().parents[1] / "cubrid-justfiles" / "justfile"
LOADER = importlib.machinery.SourceFileLoader(
    "cubrid_pr_review_worktree", os.fspath(SCRIPT)
)
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = MODULE
LOADER.exec_module(MODULE)


class CommandFixture:
    def __init__(
        self, root: Path, title: str = "[CBRD-27325] Rediscover pages"
    ) -> None:
        self.control = root / "cb" / "develop"
        self.parent = self.control.parent
        self.control.mkdir(parents=True)
        self.pr_titles = {7887: title}
        self.branch_exists = False
        self.registered_paths: list[Path] = [self.control]
        self.checkout_returncode = 0
        self.checkout_returncodes: dict[int, int] = {}
        self.prepare_returncode = 0
        self.calls: list[tuple[list[str], Path]] = []
        self.command_inputs: dict[str, str] = {}
        self.interactive_output: str | None = None
        self.dev2_returncode = 0
        self.fzf_returncode = 0
        self.fzf_selection = "https://github.com/CUBRID/cubrid/pull/7887"
        self.fzf_missing = False

    def environment(self) -> dict[str, str]:
        return {
            "CUBRID_REVIEW_CONTROL_DIR": os.fspath(self.control),
            "CUBRID_REVIEW_WORKTREE_PARENT": os.fspath(self.parent),
            "CUBRID_REVIEW_JUSTFILE": os.fspath(self.parent / "personal.just"),
        }

    def run(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        cwd = Path(os.fspath(kwargs["cwd"]))
        self.calls.append((list(command), cwd))

        if command == ["git", "rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(command, 0, f"{self.control}\n", "")
        if command[:3] == ["gh", "pr", "view"]:
            number = int(command[3].rsplit("/", 1)[-1])
            metadata = {
                "number": number,
                "title": self.pr_titles[number],
                "url": f"https://github.com/CUBRID/cubrid/pull/{number}",
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(metadata), "")
        if command == ["cubrid-dev2-pr", "--json", "--requested-only"]:
            output = self.interactive_output
            if output is None:
                output = json.dumps(
                    [
                        {
                            "number": 7887,
                            "title": self.pr_titles[7887],
                            "url": "https://github.com/CUBRID/cubrid/pull/7887",
                            "author_login": "YeunjunLee",
                            "created_at": "2026-09-07T01:02:03Z",
                            "is_draft": False,
                            "approved_count": 0,
                            "reviewer_pool_count": 4,
                            "requested": True,
                            "review_state": "not reviewed",
                        }
                    ]
                )
            return subprocess.CompletedProcess(
                command,
                self.dev2_returncode,
                output if self.dev2_returncode == 0 else "",
                "dev2 query failed" if self.dev2_returncode else "",
            )
        if command == ["git", "worktree", "list", "--porcelain", "-z"]:
            output = "".join(
                f"worktree {path}\0HEAD deadbeef\0\0" for path in self.registered_paths
            )
            return subprocess.CompletedProcess(command, 0, output, "")
        if command[:4] == ["git", "show-ref", "--verify", "--quiet"]:
            return subprocess.CompletedProcess(
                command, 0 if self.branch_exists else 1, "", ""
            )
        if command[:3] == ["gh", "pr", "checkout"]:
            number = int(command[3])
            returncode = self.checkout_returncodes.get(number, self.checkout_returncode)
            if returncode == 0:
                Path(command[command.index("--worktree") + 1]).mkdir()
            return subprocess.CompletedProcess(command, returncode, "", "")
        if command and command[0] == "fzf":
            if self.fzf_missing:
                raise FileNotFoundError("fzf")
            self.command_inputs["fzf"] = str(kwargs.get("input", ""))
            return subprocess.CompletedProcess(
                command, self.fzf_returncode, self.fzf_selection, ""
            )
        if command and command[0] == "just":
            return subprocess.CompletedProcess(command, self.prepare_returncode, "", "")
        raise AssertionError(f"unexpected command: {command}")

    def calls_starting_with(self, prefix: list[str]) -> list[tuple[list[str], Path]]:
        return [call for call in self.calls if call[0][: len(prefix)] == prefix]


class ReviewWorktreeTest(unittest.TestCase):
    def run_main(
        self, fixture: CommandFixture, *arguments: str
    ) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with (
            mock.patch.dict(os.environ, fixture.environment()),
            mock.patch.object(MODULE.subprocess, "run", side_effect=fixture.run),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = MODULE.main(list(arguments))
        return result, stdout.getvalue(), stderr.getvalue()

    def test_ticket_checkout_uses_generated_branch_and_worktree_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(
                Path(temporary), "[cbrd-27325] Rediscover free heap pages"
            )
            result, stdout, stderr = self.run_main(
                fixture, "https://github.com/CUBRID/cubrid/pull/7887"
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            expected = fixture.parent / "review-CBRD-27325-pr-7887"
            self.assertIn(f"Created review worktree: {expected}", stdout)
            checkout_calls = fixture.calls_starting_with(["gh", "pr", "checkout"])
            self.assertEqual(len(checkout_calls), 1)
            self.assertEqual(
                checkout_calls[0],
                (
                    [
                        "gh",
                        "pr",
                        "checkout",
                        "7887",
                        "--repo",
                        "CUBRID/cubrid",
                        "--branch",
                        "review-CBRD-27325-pr-7887",
                        "--worktree",
                        os.fspath(expected),
                    ],
                    fixture.control,
                ),
            )

    def test_first_ticket_token_wins(self) -> None:
        self.assertEqual(
            MODULE.review_name(42, "[APIS-1087] [CBRD-27325] Fix API"),
            "review-APIS-1087-pr-42",
        )

    def test_no_ticket_does_not_use_title_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary), "Fix crash when dropping tables")
            result, stdout, stderr = self.run_main(
                fixture, "https://github.com/CUBRID/cubrid/pull/7887"
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("review-noticket-pr-7887", stdout)
            self.assertNotIn("fix", stdout.casefold())

    def test_existing_path_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            target = fixture.parent / "review-CBRD-27325-pr-7887"
            target.mkdir()
            result, _, stderr = self.run_main(
                fixture, "https://github.com/CUBRID/cubrid/pull/7887"
            )

            self.assertEqual(result, 1)
            self.assertIn(f"review worktree path already exists: {target}", stderr)
            self.assertEqual(fixture.calls_starting_with(["gh", "pr", "checkout"]), [])

    def test_existing_branch_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.branch_exists = True
            result, _, stderr = self.run_main(
                fixture, "https://github.com/CUBRID/cubrid/pull/7887"
            )

            self.assertEqual(result, 1)
            self.assertIn(
                "review branch already exists: review-CBRD-27325-pr-7887", stderr
            )
            self.assertEqual(fixture.calls_starting_with(["gh", "pr", "checkout"]), [])

    def test_registered_missing_worktree_path_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            target = fixture.parent / "review-CBRD-27325-pr-7887"
            fixture.registered_paths.append(target)
            result, _, stderr = self.run_main(
                fixture, "https://github.com/CUBRID/cubrid/pull/7887"
            )

            self.assertEqual(result, 1)
            self.assertIn(
                f"review worktree path is already registered: {target}", stderr
            )

    def test_prepare_failure_keeps_checkout_and_prints_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.prepare_returncode = 9
            result, stdout, stderr = self.run_main(
                fixture,
                "--prepare",
                "https://github.com/CUBRID/cubrid/pull/7887",
            )

            target = fixture.parent / "review-CBRD-27325-pr-7887"
            self.assertEqual(result, 1)
            self.assertTrue(target.is_dir())
            self.assertIn(f"Created review worktree: {target}", stdout)
            self.assertIn(f"The review worktree remains at: {target}", stderr)
            self.assertIn("Retry preparation with: just --justfile", stderr)
            self.assertEqual(
                fixture.calls_starting_with(["just"]),
                [
                    (
                        [
                            "just",
                            "--justfile",
                            os.fspath(fixture.parent / "personal.just"),
                            "--working-directory",
                            os.fspath(target),
                            "prepare-build",
                        ],
                        target,
                    )
                ],
            )

    def test_checkout_failure_does_not_attempt_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.checkout_returncode = 7
            result, _, stderr = self.run_main(
                fixture, "https://github.com/CUBRID/cubrid/pull/7887"
            )

            self.assertEqual(result, 1)
            self.assertIn("No automatic cleanup was attempted.", stderr)

    def test_interactive_selection_reuses_checkout_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            result, stdout, stderr = self.run_main(fixture, "--interactive")

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("review-CBRD-27325-pr-7887", stdout)
            self.assertIn(
                "https://github.com/CUBRID/cubrid/pull/7887\t#7887",
                fixture.command_inputs["fzf"],
            )
            fzf_calls = fixture.calls_starting_with(["fzf"])
            self.assertEqual(len(fzf_calls), 1)
            self.assertIn("--with-nth=2", fzf_calls[0][0])
            self.assertIn("--accept-nth=1", fzf_calls[0][0])
            self.assertIn("--no-preview", fzf_calls[0][0])
            self.assertEqual(
                len(fixture.calls_starting_with(["gh", "pr", "checkout"])), 1
            )

    def test_interactive_prepare_runs_after_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            result, stdout, stderr = self.run_main(
                fixture, "--interactive", "--prepare"
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Prepared review worktree", stdout)
            self.assertEqual(len(fixture.calls_starting_with(["just"])), 1)

    def test_all_prints_create_and_existing_lists_before_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.pr_titles[7888] = "[CBRD-28888] Fix another review"
            fixture.interactive_output = json.dumps(
                [
                    {
                        "number": 7887,
                        "title": fixture.pr_titles[7887],
                        "url": "https://github.com/CUBRID/cubrid/pull/7887",
                        "author_login": "YeunjunLee",
                        "created_at": "2026-09-07T01:02:03Z",
                        "is_draft": False,
                        "approved_count": 0,
                        "reviewer_pool_count": 4,
                        "requested": True,
                        "review_state": "not reviewed",
                    },
                    {
                        "number": 7888,
                        "title": fixture.pr_titles[7888],
                        "url": "https://github.com/CUBRID/cubrid/pull/7888",
                        "author_login": "hgryoo",
                        "created_at": "2026-09-08T01:02:03Z",
                        "is_draft": False,
                        "approved_count": 1,
                        "reviewer_pool_count": 3,
                        "requested": True,
                        "review_state": "commented only",
                    },
                ]
            )
            existing = fixture.parent / "review-CBRD-27325-pr-7887"
            existing.mkdir()

            result, stdout, stderr = self.run_main(fixture, "--all")

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Review worktrees to create:\n  #7888", stdout)
            self.assertIn(
                "Review worktrees to skip [existing]:\n  [existing] #7887", stdout
            )
            self.assertLess(
                stdout.index("Review worktrees to create:"), stdout.index("Created")
            )
            checkout_calls = fixture.calls_starting_with(["gh", "pr", "checkout"])
            self.assertEqual(len(checkout_calls), 1)
            self.assertEqual(checkout_calls[0][0][3], "7888")
            self.assertEqual(fixture.calls_starting_with(["fzf"]), [])

    def test_all_prepare_continues_after_failure_and_reports_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.pr_titles[7888] = "[CBRD-28888] Fix another review"
            fixture.checkout_returncodes[7887] = 7
            fixture.interactive_output = json.dumps(
                [
                    {
                        "number": number,
                        "title": fixture.pr_titles[number],
                        "url": f"https://github.com/CUBRID/cubrid/pull/{number}",
                        "author_login": "hgryoo",
                        "created_at": "2026-09-08T01:02:03Z",
                        "is_draft": False,
                        "approved_count": 0,
                        "reviewer_pool_count": 3,
                        "requested": True,
                        "review_state": "not reviewed",
                    }
                    for number in (7887, 7888)
                ]
            )

            result, stdout, stderr = self.run_main(fixture, "--all", "--prepare")

            self.assertEqual(result, 1)
            self.assertIn("error: PR #7887", stderr)
            self.assertIn("Failed to create 1 review worktree(s).", stderr)
            self.assertIn("Prepared review worktree: ", stdout)
            checkout_calls = fixture.calls_starting_with(["gh", "pr", "checkout"])
            self.assertEqual([call[0][3] for call in checkout_calls], ["7887", "7888"])
            prepare_calls = fixture.calls_starting_with(["just"])
            self.assertEqual(len(prepare_calls), 1)
            self.assertIn("review-CBRD-28888-pr-7888", os.fspath(prepare_calls[0][1]))

    def test_interactive_marks_existing_candidate_then_reports_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.branch_exists = True
            result, _, stderr = self.run_main(fixture, "--interactive")

            self.assertEqual(result, 1)
            self.assertIn("[existing] #7887", fixture.command_inputs["fzf"])
            self.assertIn("review branch already exists", stderr)
            self.assertEqual(fixture.calls_starting_with(["gh", "pr", "checkout"]), [])

    def test_interactive_empty_inbox_is_successful_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.interactive_output = "[]"
            result, stdout, stderr = self.run_main(fixture, "--interactive")

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("No pull requests currently request your review.", stdout)
            self.assertEqual(fixture.calls_starting_with(["fzf"]), [])
            self.assertEqual(fixture.calls_starting_with(["gh", "pr", "checkout"]), [])

    def test_interactive_cancellation_exits_130(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.fzf_returncode = 130
            fixture.fzf_selection = ""
            result, _, stderr = self.run_main(fixture, "--interactive")

            self.assertEqual(result, 130)
            self.assertIn("Selection cancelled.", stderr)
            self.assertEqual(fixture.calls_starting_with(["gh", "pr", "checkout"]), [])

    def test_interactive_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.interactive_output = "not-json"
            result, _, stderr = self.run_main(fixture, "--interactive")

            self.assertEqual(result, 1)
            self.assertIn("could not parse cubrid-dev2-pr JSON output", stderr)
            self.assertEqual(fixture.calls_starting_with(["fzf"]), [])

    def test_interactive_reports_dev2_query_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.dev2_returncode = 9
            result, _, stderr = self.run_main(fixture, "--interactive")

            self.assertEqual(result, 1)
            self.assertIn("dev2 query failed", stderr)
            self.assertEqual(fixture.calls_starting_with(["fzf"]), [])

    def test_interactive_reports_missing_fzf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            fixture.fzf_missing = True
            result, _, stderr = self.run_main(fixture, "--interactive")

            self.assertEqual(result, 1)
            self.assertIn("interactive selection requires fzf on PATH", stderr)
            self.assertEqual(fixture.calls_starting_with(["gh", "pr", "checkout"]), [])

    def test_requires_exactly_one_input_mode(self) -> None:
        all_mode = MODULE.parse_args(["--all"])
        self.assertTrue(all_mode.all)

        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as missing:
                MODULE.parse_args([])
            self.assertEqual(missing.exception.code, 2)

            with self.assertRaises(SystemExit) as conflicting:
                MODULE.parse_args(
                    [
                        "--interactive",
                        "https://github.com/CUBRID/cubrid/pull/7887",
                    ]
                )
            self.assertEqual(conflicting.exception.code, 2)

            with self.assertRaises(SystemExit) as conflicting_all:
                MODULE.parse_args(["--interactive", "--all"])
            self.assertEqual(conflicting_all.exception.code, 2)

            with self.assertRaises(SystemExit) as conflicting_url_all:
                MODULE.parse_args(
                    ["--all", "https://github.com/CUBRID/cubrid/pull/7887"]
                )
            self.assertEqual(conflicting_url_all.exception.code, 2)

    def test_rejects_non_cubrid_pr_url_before_running_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CommandFixture(Path(temporary))
            result, _, stderr = self.run_main(
                fixture, "https://github.com/example/project/pull/7887"
            )

            self.assertEqual(result, 1)
            self.assertIn("expected a CUBRID PR URL", stderr)
            self.assertEqual(fixture.calls, [])

    def test_global_justfile_exposes_both_review_launchers(self) -> None:
        expected_commands = {
            "pr-review": "cubrid-pr-review-worktree --interactive --prepare",
            "pr-review-all": "cubrid-pr-review-worktree --all --prepare",
        }
        for recipe, expected_command in expected_commands.items():
            with self.subTest(recipe=recipe):
                result = subprocess.run(
                    ["just", "--justfile", os.fspath(JUSTFILE), "--dry-run", recipe],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected_command, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
