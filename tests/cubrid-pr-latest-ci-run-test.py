#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "bin/cubrid-pr-latest-ci-run"
PR_URL = "https://github.com/CUBRID/cubrid/pull/7927"
HEAD_SHA = "a" * 40


class LatestCiRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.fixture = self.root / "fixture.json"
        fake_gh = self.root / "gh"
        fake_gh.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["GH_FIXTURE"], encoding="utf-8") as fixture_file:
    fixture = json.load(fixture_file)
key = json.dumps(sys.argv[1:], separators=(",", ":"))
response = fixture.get(key)
if response is None:
    print("unexpected gh invocation: " + repr(sys.argv[1:]), file=sys.stderr)
    raise SystemExit(1)
if isinstance(response, dict) and "error" in response:
    print(response["error"], file=sys.stderr)
    raise SystemExit(response.get("exit_code", 1))
print(json.dumps(response))
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

    @staticmethod
    def key(*arguments: str) -> str:
        return json.dumps(list(arguments), separators=(",", ":"))

    def responses(self, status_pages: list[list[object]]) -> dict[str, object]:
        return {
            self.key("api", "repos/CUBRID/cubrid/pulls/7927"): {
                "head": {"sha": HEAD_SHA}
            },
            self.key(
                "api",
                "--paginate",
                "--slurp",
                f"repos/CUBRID/cubrid/commits/{HEAD_SHA}/statuses?per_page=100",
            ): status_pages,
        }

    def run_cli(
        self, responses: dict[str, object], pr_url: str = PR_URL
    ) -> subprocess.CompletedProcess[str]:
        self.fixture.write_text(json.dumps(responses), encoding="utf-8")
        return subprocess.run(
            [str(SCRIPT), pr_url],
            cwd=self.root,
            env={
                **os.environ,
                "PATH": f"{self.root}{os.pathsep}{os.environ['PATH']}",
                "GH_FIXTURE": str(self.fixture),
            },
            capture_output=True,
            text=True,
            timeout=10,
        )

    @staticmethod
    def status(
        context: str, run_id: int, updated_at: str, *, job_id: int | None = None
    ) -> dict[str, object]:
        suffix = f"/job/{job_id}" if job_id is not None else ""
        return {
            "context": context,
            "target_url": (
                f"https://github.com/CUBRID/cubrid/actions/runs/{run_id}{suffix}"
            ),
            "updated_at": updated_at,
        }

    def test_prints_latest_gha_ci_run_from_paginated_statuses(self) -> None:
        responses = self.responses(
            [
                [
                    self.status("gha-ci: test_shell", 100, "2026-09-23T09:00:00Z"),
                    self.status("github-checks: style", 999, "2026-09-23T12:00:00Z"),
                ],
                [
                    self.status(
                        "gha-ci: test_sql",
                        200,
                        "2026-09-23T10:00:00Z",
                        job_id=300,
                    ),
                    self.status("gha-ci: build (debug)", 100, "2026-09-23T09:05:00Z"),
                ],
            ]
        )

        result = self.run_cli(responses)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "200\n")
        self.assertEqual(result.stderr, "")

    def test_rejects_non_pr_url_before_calling_gh(self) -> None:
        result = self.run_cli({}, "https://github.com/CUBRID/cubrid/issues/7927")

        self.assertEqual(result.returncode, 1)
        self.assertIn("expected a GitHub PR URL", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_reports_when_current_head_has_no_gha_ci_run(self) -> None:
        responses = self.responses(
            [[self.status("github-checks: style", 999, "2026-09-23T12:00:00Z")]]
        )

        result = self.run_cli(responses)

        self.assertEqual(result.returncode, 1)
        self.assertIn("no gha-ci run is attached", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_ignores_run_links_from_another_repository(self) -> None:
        status = self.status("gha-ci: test_shell", 100, "2026-09-23T09:00:00Z")
        status["target_url"] = "https://github.com/another/repo/actions/runs/100"

        result = self.run_cli(self.responses([[status]]))

        self.assertEqual(result.returncode, 1)
        self.assertIn("no gha-ci run is attached", result.stderr)

    def test_reports_gh_errors_without_a_traceback(self) -> None:
        responses = {
            self.key("api", "repos/CUBRID/cubrid/pulls/7927"): {
                "error": "HTTP 401: authentication required"
            }
        }

        result = self.run_cli(responses)

        self.assertEqual(result.returncode, 1)
        self.assertIn("HTTP 401", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
