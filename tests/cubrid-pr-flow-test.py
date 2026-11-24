#!/usr/bin/env python3
"""Isolated unit and concurrency tests for cubrid-pr-flow Phase 1."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "bin" / "cubrid-pr-flow"
SHA_A = "a" * 40
SHA_B = "b" * 40


def make_executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


class CubridPrFlowPhase1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="cubrid-pr-flow-test-")
        self.root = Path(self.tmp.name)
        self.state_dir = self.root / "state"
        self.bin_dir = self.root / "fakes"
        self.bin_dir.mkdir()
        self.hermes_log = self.root / "hermes-calls.jsonl"
        self.gh_log = self.root / "gh-calls.jsonl"
        self.runner_log = self.root / "runner-calls.jsonl"
        self.gh_state_file = self.root / "gh-pr.json"
        self.hermes_mode_file = self.root / "hermes-mode.txt"
        self.runner_mode_file = self.root / "runner-mode.txt"

        self.gh_state_file.write_text(
            json.dumps(
                {
                    "number": 8504,
                    "url": "https://github.com/CUBRID/cubrid/pull/8504",
                    "state": "OPEN",
                    "isDraft": True,
                    "headRefOid": SHA_A,
                }
            ),
            encoding="utf-8",
        )
        self.hermes_mode_file.write_text("ok", encoding="utf-8")
        self.runner_mode_file.write_text("ok", encoding="utf-8")

        self.fake_hermes = make_executable(
            self.bin_dir / "fake-hermes",
            f"""#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv[1:]
msg_file = None
target = None
for i, a in enumerate(args):
    if a == "--file" and i + 1 < len(args):
        msg_file = args[i + 1]
    if a == "--to" and i + 1 < len(args):
        target = args[i + 1]
body = pathlib.Path(msg_file).read_text(encoding="utf-8") if msg_file else ""
with open({str(self.hermes_log)!r}, "a", encoding="utf-8") as log:
    log.write(json.dumps({{"args": args, "target": target, "body": body}}, ensure_ascii=False) + "\\n")
mode = pathlib.Path({str(self.hermes_mode_file)!r}).read_text().strip()
if mode == "ok":
    print(json.dumps({{"success": True, "target": target}}))
    sys.exit(0)
elif mode == "bad_json":
    print("NOT_JSON")
    sys.exit(0)
else:
    print("backend failure", file=sys.stderr)
    sys.exit(1)
""",
        )

        self.fake_gh = make_executable(
            self.bin_dir / "fake-gh",
            f"""#!/usr/bin/env python3
import json, pathlib, sys
with open({str(self.gh_log)!r}, "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
print(pathlib.Path({str(self.gh_state_file)!r}).read_text(encoding="utf-8"))
""",
        )

        self.fake_runner = make_executable(
            self.bin_dir / "fake-runner",
            f"""#!/usr/bin/env python3
import json, pathlib, sys, time
req = json.loads(sys.stdin.read())
with open({str(self.runner_log)!r}, "a", encoding="utf-8") as log:
    log.write(json.dumps(req, ensure_ascii=False) + "\\n")
mode = pathlib.Path({str(self.runner_mode_file)!r}).read_text().strip()
if mode == "slow_ok":
    time.sleep(0.15)
    print(json.dumps({{"ok": True, "summary": f"PR #{{req['pr_number']}} 처리 완료", "report_url": "https://example.org/r/1"}}))
    sys.exit(0)
elif mode == "fail":
    print(json.dumps({{"ok": False, "summary": "대상 브랜치 권한 오류"}}))
    sys.exit(1)
else:
    print(json.dumps({{"ok": True, "summary": f"PR #{{req['pr_number']}} Open 완료", "report_url": "https://example.org/r/ok"}}))
    sys.exit(0)
""",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(
        self,
        *args: str,
        with_runner: bool = False,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["CUBRID_PR_FLOW_HERMES"] = str(self.fake_hermes)
        env["CUBRID_PR_FLOW_GH"] = str(self.fake_gh)
        if with_runner:
            env["CUBRID_PR_FLOW_ACTION_RUNNER"] = str(self.fake_runner)
        else:
            env.pop("CUBRID_PR_FLOW_ACTION_RUNNER", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(CLI_PATH), "--state-dir", str(self.state_dir), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_01_init_idempotent_and_preserves_config(self) -> None:
        r1 = self.run_cli("init", "--discord-target", "discord:12345", "--allowed-actor", "u1", "--json")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        cfg1 = json.loads(r1.stdout)["config"]
        self.assertEqual(cfg1["discord_target"], "discord:12345")
        self.assertEqual(cfg1["allowed_actors"], ["u1"])

        r2 = self.run_cli("init", "--allowed-actor", "u2", "--json")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        cfg2 = json.loads(r2.stdout)["config"]
        self.assertEqual(cfg2["discord_target"], "discord:12345")
        self.assertEqual(cfg2["allowed_actors"], ["u1", "u2"])

    def test_02_emit_flush_korean_card_and_dedupe_idempotency(self) -> None:
        self.run_cli("init", "--allowed-actor", "u1")
        args = [
            "emit",
            "--dedupe-key",
            "pr-8504-open-1",
            "--kind",
            "ask_open_pr",
            "--title",
            "PR #8504 통과",
            "--summary",
            "CI와 코드 리뷰가 모두 통과했습니다.",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--ticket",
            "CBRD-28000",
            "--report-url",
            "https://example.org/report",
            "--question",
            "PR을 Open 할까요?",
            "--action-kind",
            "open_pr",
            "--flush",
            "--json",
        ]
        r1 = self.run_cli(*args)
        self.assertEqual(r1.returncode, 0, r1.stderr)
        d1 = json.loads(r1.stdout)
        self.assertTrue(d1["created"])
        self.assertEqual(d1["action"]["code"], "ACT-1")
        self.assertEqual(d1["flush"]["sent_count"], 1)

        # Repeating emit with same dedupe-key must not create a second notification or action
        r2 = self.run_cli(*args)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        d2 = json.loads(r2.stdout)
        self.assertFalse(d2["created"])
        self.assertEqual(d2["action"]["code"], "ACT-1")
        self.assertEqual(d2["flush"]["sent_count"], 0)

        calls = self.read_jsonl(self.hermes_log)
        self.assertEqual(len(calls), 1)
        body = calls[0]["body"]
        self.assertIn("[PR Open 확인]", body)
        self.assertIn("PR을 Open 할까요?", body)
        self.assertIn("`ACT-1`", body)
        self.assertIn("https://example.org/report", body)

    def test_03_long_summary_truncation_preserves_footer_and_links(self) -> None:
        self.run_cli("init", "--allowed-actor", "u1")
        long_summary = "가나다라마바사아자차카타파하 " * 300
        res = self.run_cli(
            "emit",
            "--dedupe-key",
            "long-1",
            "--kind",
            "ci_analyzed",
            "--title",
            "긴 분석 결과",
            "--summary",
            long_summary,
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--report-url",
            "https://example.org/long-report",
            "--question",
            "이슈로 등록할까요?",
            "--action-kind",
            "draft_jira_issue",
            "--flush",
            "--json",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        calls = self.read_jsonl(self.hermes_log)
        self.assertEqual(len(calls), 1)
        body = calls[0]["body"]
        self.assertLessEqual(len(body), 1900)
        self.assertIn("https://example.org/long-report", body)
        self.assertIn("`ACT-1`", body)
        self.assertIn("이슈로 등록할까요?", body)

    def test_04_unknown_delivery_not_retried_until_resolved(self) -> None:
        self.run_cli("init", "--allowed-actor", "u1")
        self.hermes_mode_file.write_text("bad_json", encoding="utf-8")
        r1 = self.run_cli(
            "emit",
            "--dedupe-key",
            "unk-1",
            "--kind",
            "ci_failed",
            "--title",
            "CI 실패",
            "--summary",
            "shell suite 실패",
            "--flush",
            "--json",
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(json.loads(r1.stdout)["flush"]["unknown_count"], 1)

        # Subsequent flush must NOT auto-retry unknown
        self.hermes_mode_file.write_text("ok", encoding="utf-8")
        r2 = self.run_cli("flush", "--json")
        self.assertEqual(r2.returncode, 0)
        self.assertEqual(json.loads(r2.stdout)["sent_count"], 0)
        self.assertEqual(len(self.read_jsonl(self.hermes_log)), 1)

        # Resolve as pending -> next flush sends it
        r3 = self.run_cli("resolve", "--dedupe-key", "unk-1", "--outcome", "pending", "--reason", "confirmed absent", "--json")
        self.assertEqual(r3.returncode, 0, r3.stderr)
        r4 = self.run_cli("flush", "--json")
        self.assertEqual(r4.returncode, 0)
        self.assertEqual(json.loads(r4.stdout)["sent_count"], 1)
        self.assertEqual(len(self.read_jsonl(self.hermes_log)), 2)

        # Second unknown case resolved directly as sent -> no resend
        self.hermes_mode_file.write_text("fail", encoding="utf-8")
        self.run_cli("emit", "--dedupe-key", "unk-2", "--kind", "generic", "--title", "테스트", "--flush")
        r5 = self.run_cli("resolve", "--dedupe-key", "unk-2", "--outcome", "sent", "--reason", "observed in channel", "--json")
        self.assertEqual(r5.returncode, 0)
        self.assertEqual(json.loads(r5.stdout)["state"], "sent")
        self.hermes_mode_file.write_text("ok", encoding="utf-8")
        r6 = self.run_cli("flush", "--json")
        self.assertEqual(json.loads(r6.stdout)["sent_count"], 0)

    def test_05_unauthorized_actor_fail_closed(self) -> None:
        # Empty allowed_actors -> fail closed
        self.run_cli("init")
        self.run_cli(
            "emit",
            "--dedupe-key",
            "auth-1",
            "--kind",
            "ask_open_pr",
            "--title",
            "Open",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "open_pr",
        )
        r1 = self.run_cli("dispatch", "ACT-1", "--actor", "u1", "--json", with_runner=True)
        self.assertEqual(r1.returncode, 1)
        self.assertEqual(json.loads(r1.stdout)["status"], "unauthorized")
        self.assertEqual(self.read_jsonl(self.gh_log), [])
        self.assertEqual(self.read_jsonl(self.runner_log), [])

        # Configured allowed_actors -> wrong actor rejected, action stays pending
        self.run_cli("init", "--allowed-actor", "owner123")
        r2 = self.run_cli("dispatch", "ACT-1", "--actor", "intruder999", "--json", with_runner=True)
        self.assertEqual(r2.returncode, 1)
        self.assertEqual(json.loads(r2.stdout)["status"], "unauthorized")
        show = json.loads(self.run_cli("action", "show", "ACT-1", "--json").stdout)
        self.assertEqual(show["state"], "pending")

    def test_06_live_head_mismatch_marks_superseded(self) -> None:
        self.run_cli("init", "--allowed-actor", "owner123")
        self.run_cli(
            "emit",
            "--dedupe-key",
            "head-1",
            "--kind",
            "ask_open_pr",
            "--title",
            "Open",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "open_pr",
        )
        self.run_cli(
            "emit",
            "--dedupe-key",
            "head-2",
            "--kind",
            "ask_rerun_ci",
            "--title",
            "Rerun",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "rerun_ci",
        )
        # Live PR moved to SHA_B
        self.gh_state_file.write_text(
            json.dumps({"number": 8504, "url": "https://github.com/CUBRID/cubrid/pull/8504", "state": "OPEN", "isDraft": True, "headRefOid": SHA_B}),
            encoding="utf-8",
        )
        for code in ("ACT-1", "ACT-2"):
            r = self.run_cli("dispatch", code, "--actor", "owner123", "--json", with_runner=True)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(json.loads(r.stdout)["status"], "superseded")
        self.assertEqual(self.read_jsonl(self.runner_log), [])

    def test_07_live_pr_not_draft_or_closed_marks_expired(self) -> None:
        self.run_cli("init", "--allowed-actor", "owner123")
        self.run_cli(
            "emit",
            "--dedupe-key",
            "exp-1",
            "--kind",
            "ask_open_pr",
            "--title",
            "Open",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "open_pr",
        )
        self.gh_state_file.write_text(
            json.dumps({"number": 8504, "url": "https://github.com/CUBRID/cubrid/pull/8504", "state": "OPEN", "isDraft": False, "headRefOid": SHA_A}),
            encoding="utf-8",
        )
        r1 = self.run_cli("dispatch", "ACT-1", "--actor", "owner123", "--json", with_runner=True)
        self.assertEqual(r1.returncode, 1)
        self.assertEqual(json.loads(r1.stdout)["status"], "expired")

        self.run_cli(
            "emit",
            "--dedupe-key",
            "exp-2",
            "--kind",
            "ask_rerun_ci",
            "--title",
            "Rerun",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "rerun_ci",
        )
        self.gh_state_file.write_text(
            json.dumps({"number": 8504, "url": "https://github.com/CUBRID/cubrid/pull/8504", "state": "CLOSED", "isDraft": True, "headRefOid": SHA_A}),
            encoding="utf-8",
        )
        r2 = self.run_cli("dispatch", "ACT-2", "--actor", "owner123", "--json", with_runner=True)
        self.assertEqual(r2.returncode, 1)
        self.assertEqual(json.loads(r2.stdout)["status"], "expired")

    def test_08_pr_supersede_preserves_jira_actions(self) -> None:
        self.run_cli("init", "--allowed-actor", "owner123")
        self.run_cli("pr", "upsert", "--pr", "8504", "--head", SHA_A, "--ci-state", "running", "--review-state", "passed")
        self.run_cli(
            "emit",
            "--dedupe-key",
            "sup-open",
            "--kind",
            "ask_open_pr",
            "--title",
            "Open",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "open_pr",
        )
        self.run_cli(
            "emit",
            "--dedupe-key",
            "sup-jira",
            "--kind",
            "ask_draft_jira",
            "--title",
            "Jira",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "draft_jira_issue",
        )
        res = self.run_cli("pr", "supersede", "--pr", "8504", "--new-head", SHA_B, "--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["superseded_runs"], 1)
        self.assertEqual(data["superseded_actions"], 1)

        act_open = json.loads(self.run_cli("action", "show", "ACT-1", "--json").stdout)
        act_jira = json.loads(self.run_cli("action", "show", "ACT-2", "--json").stdout)
        self.assertEqual(act_open["state"], "superseded")
        self.assertEqual(act_jira["state"], "pending")

    def test_09_concurrent_dispatch_claims_exactly_once(self) -> None:
        self.run_cli("init", "--allowed-actor", "owner123")
        self.runner_mode_file.write_text("slow_ok", encoding="utf-8")
        self.run_cli(
            "emit",
            "--dedupe-key",
            "race-1",
            "--kind",
            "ask_open_pr",
            "--title",
            "Open",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "open_pr",
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(self.run_cli, "dispatch", "ACT-1", "--actor", "owner123", "--json", with_runner=True)
            f2 = pool.submit(self.run_cli, "dispatch", "ACT-1", "--actor", "owner123", "--json", with_runner=True)
            r1, r2 = f1.result(), f2.result()

        rcs = sorted([r1.returncode, r2.returncode])
        self.assertEqual(rcs, [0, 1], f"r1={r1.stdout} r2={r2.stdout}")
        statuses = {json.loads(r1.stdout)["status"], json.loads(r2.stdout)["status"]}
        self.assertEqual(statuses, {"succeeded", "already_handled"})
        self.assertEqual(len(self.read_jsonl(self.runner_log)), 1)

    def test_10_dispatch_success_and_failure_with_send_result(self) -> None:
        self.run_cli("init", "--allowed-actor", "owner123")
        self.run_cli(
            "emit",
            "--dedupe-key",
            "res-1",
            "--kind",
            "ask_open_pr",
            "--title",
            "Open",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "open_pr",
            "--flush",
        )
        r_ok = self.run_cli("dispatch", "ACT-1", "--actor", "owner123", "--send-result", "--json", with_runner=True)
        self.assertEqual(r_ok.returncode, 0, r_ok.stderr)
        d_ok = json.loads(r_ok.stdout)
        self.assertEqual(d_ok["status"], "succeeded")
        self.assertEqual(d_ok["flush"]["sent_count"], 1)

        self.run_cli(
            "emit",
            "--dedupe-key",
            "res-2",
            "--kind",
            "ask_draft_jira",
            "--title",
            "Draft Jira",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "draft_jira_issue",
            "--flush",
        )
        self.runner_mode_file.write_text("fail", encoding="utf-8")
        r_fail = self.run_cli("dispatch", "ACT-2", "--actor", "owner123", "--send-result", "--json", with_runner=True)
        self.assertEqual(r_fail.returncode, 1)
        d_fail = json.loads(r_fail.stdout)
        self.assertEqual(d_fail["status"], "failed")
        self.assertEqual(d_fail["flush"]["sent_count"], 1)

        calls = self.read_jsonl(self.hermes_log)
        self.assertEqual(len(calls), 4)
        self.assertIn("[액션 결과]", calls[1]["body"])
        self.assertIn("ACT-1", calls[1]["body"])
        self.assertIn("대상 브랜치 권한 오류", calls[3]["body"])

    def test_11_dry_run_and_missing_runner_preserve_pending(self) -> None:
        self.run_cli("init", "--allowed-actor", "owner123")
        self.run_cli(
            "emit",
            "--dedupe-key",
            "dry-1",
            "--kind",
            "ask_open_pr",
            "--title",
            "Open",
            "--pr",
            "8504",
            "--head",
            SHA_A,
            "--action-kind",
            "open_pr",
        )
        r_dry = self.run_cli("dispatch", "ACT-1", "--actor", "owner123", "--dry-run", "--json")
        self.assertEqual(r_dry.returncode, 0, r_dry.stderr)
        self.assertEqual(json.loads(r_dry.stdout)["status"], "ready")

        r_no_runner = self.run_cli("dispatch", "ACT-1", "--actor", "owner123", "--json", with_runner=False)
        self.assertEqual(r_no_runner.returncode, 2)
        self.assertEqual(json.loads(r_no_runner.stdout)["status"], "executor_unavailable")

        show = json.loads(self.run_cli("action", "show", "ACT-1", "--json").stdout)
        self.assertEqual(show["state"], "pending")


if __name__ == "__main__":
    unittest.main()
