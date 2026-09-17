#!/usr/bin/env python3
"""Exercise the worktree runtime guard through its public CLI."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "bin" / "my-cubrid-runtime"


class RuntimeGuardCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.worktree = self.root / "source"
        self.worktree.mkdir()
        subprocess.run(["git", "init", "-q", str(self.worktree)], check=True)
        for filename in ("CMakeLists.txt", "VERSION"):
            (self.worktree / filename).touch()
        for directory in ("src", "broker", "pl_engine"):
            (self.worktree / directory).mkdir()
        self.state_home = self.root / "state"
        self.calls = self.root / "lifecycle-calls"
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        for command in ("cubrid", "cub_master", "cub_server", "broker", "cub_pl"):
            executable = fake_bin / command
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$0 $*\" >>\"$LIFECYCLE_CALLS\"\n"
            )
            executable.chmod(0o755)
        self.environment = {
            **os.environ,
            "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
            "XDG_STATE_HOME": str(self.state_home),
            "LIFECYCLE_CALLS": str(self.calls),
        }

    def snapshot(self):
        snapshot = []
        for path in (self.root, *self.root.rglob("*")):
            metadata = path.lstat()
            content = path.read_bytes() if path.is_file() else None
            snapshot.append((
                str(path.relative_to(self.root)),
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
                content,
            ))
        return sorted(snapshot)

    def run_cli(self, *arguments):
        return subprocess.run(
            [str(CLI), "validate", *arguments],
            cwd=self.worktree,
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def use_fake_state(self, runtime_id, manifest, observations=None):
        environment_path = self.worktree / ".env"
        manifest_path = (
            self.state_home
            / "cubrid-worktree-guard"
            / "worktrees"
            / runtime_id
            / "manifest.json"
        )
        fixture = self.root / "observations.json"
        fixture.write_text(json.dumps({
            "filesystem": {
                str(environment_path): {
                    "type": "file",
                    "owner": os.geteuid(),
                    "mode": "0600",
                    "content": f"CUBRID_WORKTREE_ID={runtime_id}\n",
                },
                str(manifest_path): manifest,
            },
            "observations": observations or {
                "complete": True,
                "processes": [],
                "sockets": [],
                "listeners": [],
                "system_v_ipc": [],
            },
        }))
        self.environment["MY_CUBRID_RUNTIME_TEST_OBSERVATIONS"] = str(fixture)
        return manifest_path

    def test_absent_manifest_is_actionable_uninitialized_without_mutation(self):
        before = self.snapshot()
        result = self.run_cli("--preset", "debug")

        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn("Outcome: uninitialized", result.stdout)
        self.assertIn(f"Affected worktree runtime: {self.worktree}", result.stdout)
        self.assertIn("Evidence quality: definitive", result.stdout)
        self.assertIn("Next action: Keep this worktree build-only", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_json_reports_the_same_uninitialized_outcome_without_secrets(self):
        self.environment.update(PRESET_MODE="release_gcc", API_SECRET="never-print-this")
        result = subprocess.run(
            [
                str(CLI),
                "validate",
                "--worktree",
                str(self.worktree),
                "--json",
            ],
            cwd=self.root,
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], "uninitialized")
        self.assertFalse(report["ready"])
        self.assertEqual(report["worktree"], str(self.worktree))
        self.assertEqual(report["preset"], "release_gcc")
        self.assertEqual(report["diagnostic"]["affected_object"], {
            "kind": "worktree runtime",
            "value": str(self.worktree),
        })
        self.assertEqual(report["diagnostic"]["evidence_quality"], "definitive")
        self.assertEqual(
            report["diagnostic"]["next_action"],
            "Keep this worktree build-only; do not run CUBRID services until its "
            "runtime guard has been initialized.",
        )
        self.assertNotIn("never-print-this", result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.calls.exists())

    def test_malformed_manifest_is_invalid_not_uninitialized(self):
        manifest_path = self.use_fake_state("runtime-01", {
            "type": "file",
            "owner": os.geteuid(),
            "mode": "0600",
            "content": "{",
        })
        before = self.snapshot()
        result = self.run_cli("--preset", "debug")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertIn("Outcome: invalid", result.stdout)
        self.assertIn(f"Affected worktree manifest: {manifest_path}", result.stdout)
        self.assertIn("Evidence quality: definitive", result.stdout)
        self.assertIn("Details: Manifest is not valid JSON.", result.stdout)
        self.assertIn("Next action: inspect or restore the manifest", result.stdout)
        self.assertNotIn("uninitialized", result.stdout)
        structured = self.run_cli("--preset", "debug", "--json")
        report = json.loads(structured.stdout)
        self.assertEqual(structured.returncode, result.returncode)
        self.assertIn(f"Outcome: {report['outcome']}", result.stdout)
        affected = report["diagnostic"]["affected_object"]
        self.assertIn(f"Affected {affected['kind']}: {affected['value']}", result.stdout)
        self.assertIn(
            f"Evidence quality: {report['diagnostic']['evidence_quality']}", result.stdout
        )
        self.assertIn(f"Next action: {report['diagnostic']['next_action']}", result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_unsupported_manifest_version_is_rejected(self):
        self.use_fake_state("runtime-01", {
            "type": "file",
            "owner": os.geteuid(),
            "mode": "0600",
            "content": json.dumps({"schema_version": 2}),
        })
        result = self.run_cli("--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], "invalid")
        self.assertEqual(report["diagnostic"]["code"], "manifest_unsupported_version")
        self.assertIn("version 2", report["diagnostic"]["message"])
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.calls.exists())

    def test_manifest_for_another_runtime_is_rejected_as_inconsistent(self):
        self.use_fake_state("runtime-01", {
            "type": "file",
            "owner": os.geteuid(),
            "mode": "0600",
            "content": json.dumps({
                "schema_version": 1,
                "generation": 1,
                "state": "ready",
                "worktree_id": "runtime-02",
                "worktree_path": str(self.worktree),
                "git_common_dir": str(self.worktree / ".git"),
                "active_preset": "debug",
                "resource_bundle": {},
            }),
        })
        result = self.run_cli("--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["diagnostic"]["code"], "manifest_inconsistent")
        self.assertIn("worktree ID", report["diagnostic"]["message"])
        self.assertEqual(report["diagnostic"]["affected_object"]["kind"], "worktree identity")
        self.assertEqual(report["diagnostic"]["normalized_value"], "runtime-02")
        self.assertEqual(report["diagnostic"]["observed_value"], "runtime-02")
        self.assertEqual(report["diagnostic"]["expected_value"], "runtime-01")
        self.assertEqual(report["diagnostic"]["source"], "worktree manifest worktree_id")
        self.assertIn(".env", report["diagnostic"]["next_action"])
        self.assertNotEqual(report["outcome"], "uninitialized")
        self.assertFalse(self.calls.exists())

    def test_unsafe_manifest_metadata_is_rejected(self):
        cases = (
            ({"type": "directory", "owner": os.geteuid(), "mode": "0600"},
             "manifest_wrong_type"),
            ({"type": "file", "owner": os.geteuid() + 1, "mode": "0600", "content": "{}"},
             "manifest_wrong_owner"),
            ({"type": "file", "owner": os.geteuid(), "mode": "0644", "content": "{}"},
             "manifest_wrong_mode"),
        )
        for manifest, code in cases:
            with self.subTest(code=code):
                self.use_fake_state("runtime-01", manifest)
                before = self.snapshot()
                result = self.run_cli("--preset", "debug", "--json")

                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report["outcome"], "invalid")
                self.assertEqual(report["diagnostic"]["code"], code)
                self.assertEqual(report["diagnostic"]["evidence_quality"], "definitive")
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.calls.exists())

    def test_ambiguous_worktree_identity_is_invalid_state(self):
        (self.worktree / ".env").write_text(
            "CUBRID_WORKTREE_ID=runtime-01\n"
            "CUBRID_WORKTREE_ID=runtime-02\n"
        )
        result = self.run_cli("--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], "invalid")
        self.assertEqual(report["diagnostic"]["code"], "worktree_identity_invalid")
        self.assertEqual(report["diagnostic"]["affected_object"], {
            "kind": "worktree environment",
            "value": str(self.worktree / ".env"),
        })
        self.assertFalse(self.calls.exists())

    def test_non_cubrid_git_repository_is_rejected(self):
        ordinary_repository = self.root / "ordinary"
        subprocess.run(["git", "init", "-q", str(ordinary_repository)], check=True)
        result = self.run_cli("--worktree", str(ordinary_repository), "--preset", "debug")

        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertIn("not a CUBRID Git worktree", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.calls.exists())

    def test_incomplete_fake_runtime_observations_fail_closed(self):
        self.use_fake_state("runtime-01", {
            "type": "file",
            "owner": os.geteuid(),
            "mode": "0600",
            "content": json.dumps({
                "schema_version": 1,
                "generation": 1,
                "state": "ready",
                "worktree_id": "runtime-01",
                "worktree_path": str(self.worktree),
                "git_common_dir": str(self.worktree / ".git"),
                "active_preset": "debug",
                "resource_bundle": {"master_port": 15000},
            }),
        }, observations={
            "complete": False,
            "processes": [],
            "sockets": [],
            "listeners": [],
            "system_v_ipc": [],
        })
        result = self.run_cli("--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["diagnostic"]["code"], "observation_incomplete")
        self.assertEqual(report["diagnostic"]["evidence_quality"], "unknown")
        self.assertEqual(
            report["diagnostic"]["affected_object"]["kind"], "runtime observation snapshot"
        )
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
