#!/usr/bin/env python3
"""Exercise the worktree runtime guard through its public CLI."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


CLI = Path(__file__).resolve().parents[1] / "bin" / "my-cubrid-runtime"
PUBLICATION_BOUNDARIES = tuple(
    f"{when}_{publication}"
    for publication in (
        "registry", "manifest", "engine_configuration", "broker_configuration",
        "identity", "environment", "ready_manifest", "ready_registry",
    )
    for when in ("before", "after")
)


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
        self.home = self.root / "home"
        self.home.mkdir()
        self.installation = self.root / "install"
        for directory in ("bin", "lib", "conf", "var", "log", "tmp"):
            (self.installation / directory).mkdir(parents=True)
        for executable_name in ("cubrid", "cub_master", "cub_server", "cub_broker", "cub_pl"):
            executable = self.installation / "bin" / executable_name
            executable.write_text(f"synthetic {executable_name}\n")
            executable.chmod(0o755)
        (self.installation / "lib" / "libcubrid.so").write_text("synthetic library\n")
        (self.installation / "conf" / "cubrid.conf").write_text(
            "# engine comment\n"
            "[service]\n"
            "service=server,broker,manager\n\n"
            "[common]\n"
            "cubrid_port_id=1523\n"
            "stored_procedure_uds=no\n"
            "custom_parameter=preserved\n"
        )
        (self.installation / "conf" / "cubrid_broker.conf").write_text(
            "# broker comment\n"
            "[broker]\n"
            "MASTER_SHM_ID=30001\n\n"
            "[%query_editor]\n"
            "SERVICE=ON\n"
            "BROKER_PORT=30000\n"
            "MIN_NUM_APPL_SERVER=1\n"
            "MAX_NUM_APPL_SERVER=2\n"
            "APPL_SERVER_SHM_ID=30000\n"
            "CUSTOM_BROKER_SETTING=preserved\n"
        )
        self.calls = self.root / "lifecycle-calls"
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        for command in ("cubrid", "cub_master", "cub_server", "cub_broker", "broker", "cub_pl",
                        "pkill", "killall", "kill", "ipcrm", "ipcmk", "rm", "rmdir"):
            executable = fake_bin / command
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$0 $*\" >>\"$LIFECYCLE_CALLS\"\n"
            )
            executable.chmod(0o755)
        self.environment = {
            **os.environ,
            "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
            "HOME": str(self.home),
            "CUBRID": str(self.installation),
            "CUBRID_BUILD_DIR": str(self.worktree / "build_preset_debug"),
            "XDG_STATE_HOME": str(self.state_home),
            "LIFECYCLE_CALLS": str(self.calls),
        }
        self.fixture = self.root / "observations.json"
        self.fixture.write_text(json.dumps({
            "filesystem": {},
            "observations": {
                "complete": True,
                "processes": [],
                "sockets": [],
                "listeners": [],
                "system_v_ipc": [],
            },
        }))
        self.environment["MY_CUBRID_RUNTIME_TEST_OBSERVATIONS"] = str(self.fixture)

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

    def run_runtime(self, command, *arguments):
        return self.run_runtime_for(
            self.worktree, self.environment, command, *arguments
        )

    def run_runtime_for(self, worktree, environment, command, *arguments):
        return subprocess.run(
            [str(CLI), command, *arguments],
            cwd=worktree,
            env=environment,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def create_additional_runtime(self, name):
        worktree = self.root / f"source-{name}"
        worktree.mkdir()
        subprocess.run(["git", "init", "-q", str(worktree)], check=True)
        for filename in ("CMakeLists.txt", "VERSION"):
            (worktree / filename).touch()
        for directory in ("src", "broker", "pl_engine"):
            (worktree / directory).mkdir()
        installation = self.root / f"install-{name}"
        shutil.copytree(self.installation, installation)
        environment = {
            **self.environment,
            "CUBRID": str(installation),
            "CUBRID_BUILD_DIR": str(worktree / "build_preset_debug"),
        }
        return worktree, installation, environment

    def run_cli(self, *arguments):
        return self.run_runtime("validate", *arguments)

    def adoption_database(self, name="CBRD-12345"):
        registry = self.home / "existing-registry"
        registry.mkdir(mode=0o700)
        roots = [self.home / f"existing-{role}" for role in ("data", "log", "lob")]
        for root in roots:
            root.mkdir(mode=0o700)
        (roots[0] / name).write_text("existing database volume\n")
        (roots[0] / f"{name}_vinf").write_text(f"0 {roots[0] / name}\n")
        entry = registry / "databases.txt"
        entry.write_text(f"{name} {roots[0]} localhost {roots[1]} file:{roots[2]}\n")
        entry.chmod(0o600)
        return registry, roots

    def test_deinit_releases_only_guard_metadata_and_is_absent_idempotent(self):
        unrelated = "# personal settings\r\nPRESET_MODE=debug\r\n\r\nOTHER='keep me'\r\n"
        (self.worktree / ".env").write_bytes(unrelated.encode())
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        manifest = self.manifest_for(initialized)
        manifest_path = Path(json.loads(initialized.stdout)["manifest_path"])
        # Preserve the bytes presented to deinit, including CRLF and no final newline.
        identity = f"export CUBRID_WORKTREE_ID='{manifest['worktree_id']}'\r\n"
        (self.worktree / ".env").write_bytes((identity + unrelated + "TAIL=value").encode())
        bundle = manifest["resource_bundle"]
        retained = [Path(bundle["log_root"]) / "user.log",
                    Path(bundle["cubrid_tmp"]) / "unrelated-socket-stand-in",
                    self.installation / "var" / "runtime-data"]
        for path in retained:
            path.write_text("must survive\n")
        installation_before = {str(path): path.read_bytes() for path in self.installation.rglob("*") if path.is_file()}
        result = self.run_runtime("deinit", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], "deinitialized")
        self.assertFalse(report["ready"])
        self.assertEqual(report["worktree_id"], manifest["worktree_id"])
        self.assertEqual({item["kind"] for item in report["released"]},
                         {"worktree identity", "worktree manifest", "generated environment",
                          "allocation registry entry", "guard transaction"})
        self.assertEqual(report["released_claims"], manifest["normalized_claims"])
        self.assertTrue(any(item["value"] == bundle["database_registry"] for item in report["retained"]))
        self.assertEqual((self.worktree / ".env").read_bytes(), (unrelated + "TAIL=value").encode())
        self.assertFalse(manifest_path.exists())
        self.assertFalse((manifest_path.parent / "env.sh").exists())
        self.assertFalse((manifest_path.parent / "transaction.json").exists())
        registry = self.state_home / "cubrid-worktree-guard" / "allocations.json"
        self.assertNotIn(manifest["worktree_id"], json.loads(registry.read_text())["allocations"])
        self.assertEqual(installation_before, {str(path): path.read_bytes() for path in self.installation.rglob("*") if path.is_file()})
        for path in retained:
            self.assertEqual(path.read_text(), "must survive\n")
        before = self.snapshot()
        again = self.run_runtime("deinit", "--preset", "debug", "--json")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(json.loads(again.stdout)["released"], [])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_deinit_retry_retains_claims_until_the_final_durable_release(self):
        publications = ("deinit_transaction", "deinit_registry", "deinit_manifest",
                        "release_identity", "release_environment", "release_manifest",
                        "release_allocation", "release_transaction")
        for publication in publications:
            for when in ("before", "after"):
                with self.subTest(boundary=f"{when}_{publication}"):
                    self.setUp()
                    initial = self.run_runtime("init", "--preset", "debug", "--json")
                    self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
                    manifest = self.manifest_for(initial)
                    transaction_path = Path(json.loads(initial.stdout)["manifest_path"]).parent / "transaction.json"
                    fixture = json.loads(self.fixture.read_text())
                    fixture["publication_failure"] = f"{when}_{publication}"
                    self.fixture.write_text(json.dumps(fixture))
                    interrupted = self.run_runtime("deinit", "--preset", "debug", "--json")
                    self.assertEqual(interrupted.returncode, 86, interrupted.stdout + interrupted.stderr)
                    fixture.pop("publication_failure")
                    self.fixture.write_text(json.dumps(fixture))
                    committed = publication == "release_transaction" and when == "after"
                    if not committed:
                        retained = json.loads(transaction_path.read_text())
                        self.assertEqual(retained["manifest"]["normalized_claims"], manifest["normalized_claims"])
                        self.assertEqual(retained["state"], "ready" if publication == "deinit_transaction" and when == "before" else "deinitializing")
                    other_worktree, _, other_environment = self.create_additional_runtime("other")
                    other = self.run_runtime_for(other_worktree, other_environment, "init", "--preset", "debug", "--json")
                    self.assertEqual(other.returncode, 0, other.stdout + other.stderr)
                    other_claims = self.manifest_for(other)["normalized_claims"]
                    for kind in ("tcp_ports", "system_v_keys"):
                        self.assertEqual(set(other_claims[kind]).isdisjoint(manifest["normalized_claims"][kind]), not committed)
                    retried = self.run_runtime("deinit", "--preset", "debug", "--json")
                    self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
                    self.assertFalse(transaction_path.exists())
                    third_worktree, _, third_environment = self.create_additional_runtime("third")
                    third = self.run_runtime_for(third_worktree, third_environment, "init", "--preset", "debug", "--json")
                    self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
                    if not committed:
                        for kind in ("tcp_ports", "system_v_keys"):
                            self.assertEqual(self.manifest_for(third)["normalized_claims"][kind], manifest["normalized_claims"][kind])
                    self.assertFalse(self.calls.exists())

    def test_deinit_refuses_live_unknown_and_inconsistent_ownership_without_writes(self):
        for problem in ("live", "endpoint", "process", "ipc", "socket", "incomplete",
                        "preset", "configuration", "storage", "installation", "identity-alias"):
            with self.subTest(problem=problem):
                self.setUp()
                initial = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
                manifest = self.manifest_for(initial)
                bundle = manifest["resource_bundle"]
                options = []
                if problem in ("live", "endpoint"):
                    process = self.runtime_process(manifest)
                    self.replace_observations({
                        "processes": [process] if problem == "live" else [],
                        "listeners": [{"protocol": "tcp", "address": "0.0.0.0",
                                       "port": bundle["master_port"], "inode": 7001,
                                       "namespace": self.observation_scope()["namespaces"]["network"],
                                       "owner_pid": process["pid"], "owner_start_time": process["start_time"]}],
                    })
                elif problem == "process":
                    self.replace_observations({"processes": [self.runtime_process(manifest)]})
                elif problem == "ipc":
                    self.replace_observations({"system_v_ipc": [{"key": bundle["master_shm_key"]}]})
                elif problem == "socket":
                    Path(bundle["socket_paths"][0]).write_text("stale socket stand-in\n")
                elif problem == "incomplete":
                    self.replace_observations({"complete": False})
                elif problem == "preset":
                    options = ["--preset", "release_gcc"]
                elif problem == "configuration":
                    config = self.installation / "conf" / "cubrid.conf"
                    config.write_text(config.read_text().replace("cubrid_port_id=15000", "cubrid_port_id=15042"))
                elif problem == "storage":
                    (Path(bundle["database_registry"]) / "databases.txt").write_text("contradictory registry\n")
                elif problem == "installation":
                    (self.installation / "bin" / "cub_master").write_text("reinstalled\n")
                elif problem == "identity-alias":
                    identity = self.worktree / ".env"
                    outside = self.root / "outside-env"
                    identity.rename(outside)
                    identity.symlink_to(outside)
                before = self.snapshot()
                refused = self.run_runtime("deinit", "--preset", "debug", *options, "--json")
                self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
                report = json.loads(refused.stdout)
                self.assertEqual(report["command"], "deinit")
                self.assertIn("diagnostic", report)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.calls.exists())

    def test_waiting_deinit_cannot_release_a_replacement_identity(self):
        initial = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_pause"] = "before_lock"
        self.fixture.write_text(json.dumps(fixture))
        waiting = subprocess.Popen([str(CLI), "deinit", "--preset", "debug", "--json"],
                                   cwd=self.worktree, env=self.environment,
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: waiting.communicate(timeout=15))
        self.wait_for_publication(waiting)
        fixture.pop("publication_pause")
        self.fixture.write_text(json.dumps(fixture))
        removed = self.run_runtime("deinit", "--preset", "debug", "--json")
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        replacement = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(replacement.returncode, 0, replacement.stdout + replacement.stderr)
        replacement_manifest = self.manifest_for(replacement)
        self.fixture.with_suffix(".resume").touch()
        before = self.snapshot()
        stdout, stderr = waiting.communicate(timeout=10)
        self.assertEqual(waiting.returncode, 4, stdout + stderr)
        self.assertEqual(json.loads(stdout)["diagnostic"]["code"], "transaction_operation_mismatch")
        self.assertEqual(self.manifest_for(replacement), replacement_manifest)
        self.assertEqual(self.snapshot(), before)

    def test_deinit_absent_identity_does_not_create_guard_state(self):
        before = self.snapshot()
        result = self.run_runtime("deinit", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["released"], [])
        self.assertEqual(self.snapshot(), before)

    def test_deinit_preserves_adopted_database_and_reports_human_inventory(self):
        registry, roots = self.adoption_database()
        adopted = self.run_runtime("adopt", "--preset", "debug", "--db-name", "CBRD-12345",
                                   "--registry", str(registry), "--json")
        self.assertEqual(adopted.returncode, 0, adopted.stdout + adopted.stderr)
        paths = [registry, *roots, self.installation]
        before = {str(path): path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()}
        released = self.run_runtime("deinit", "--preset", "debug")
        self.assertEqual(released.returncode, 0, released.stdout + released.stderr)
        self.assertIn("Released metadata:", released.stdout)
        self.assertIn("Retained runtime data:", released.stdout)
        self.assertIn("database: CBRD-12345", released.stdout)
        for path in paths:
            self.assertIn(str(path), released.stdout)
        self.assertEqual(before, {str(path): path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()})
        self.assertFalse(self.calls.exists())

    def test_deinit_recovery_refuses_changed_command_identity_and_unknown_evidence(self):
        initial = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        path = Path(json.loads(initial.stdout)["manifest_path"]).parent / "transaction.json"
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_failure"] = "after_release_allocation"
        self.fixture.write_text(json.dumps(fixture))
        interrupted = self.run_runtime("deinit", "--preset", "debug", "--json")
        self.assertEqual(interrupted.returncode, 86, interrupted.stdout + interrupted.stderr)
        fixture.pop("publication_failure")
        self.fixture.write_text(json.dumps(fixture))
        transaction = json.loads(path.read_text())
        for command, options in (("init", []), ("adopt", []), ("deinit", ["--preset", "release_gcc"])):
            before = self.snapshot()
            result = self.run_runtime(command, "--preset", "debug", *options, "--json")
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["diagnostic"]["code"], "transaction_operation_mismatch")
            self.assertEqual(self.snapshot(), before)
        for problem in ("observation", "configuration", "identity", "generation"):
            with self.subTest(problem=problem):
                engine = self.installation / "conf" / "cubrid.conf"
                original_engine = engine.read_bytes()
                identity = self.worktree / ".env"
                original_identity = identity.read_bytes()
                allocation_path = path.parents[2] / "allocations.json"
                original_allocation = allocation_path.read_bytes()
                if problem == "observation":
                    fixture["observations"]["complete"] = False
                    self.fixture.write_text(json.dumps(fixture))
                elif problem == "configuration":
                    engine.write_bytes(original_engine + b"\n# changed identity\n")
                elif problem == "identity":
                    identity.write_text("CUBRID_WORKTREE_ID=replacement\n")
                else:
                    allocation = json.loads(original_allocation)
                    allocation["generation"] += 1
                    allocation["allocations"][transaction["manifest"]["worktree_id"]] = {
                        "generation": allocation["generation"], "state": "ready",
                        "claims": transaction["manifest"]["normalized_claims"],
                        "worktree_path": str(self.worktree),
                    }
                    allocation_path.write_text(json.dumps(allocation))
                before = self.snapshot()
                refused = self.run_runtime("deinit", "--preset", "debug", "--json")
                self.assertEqual(refused.returncode, 4, refused.stdout + refused.stderr)
                self.assertEqual(json.loads(path.read_text()), transaction)
                self.assertEqual(self.snapshot(), before)
                fixture["observations"]["complete"] = True
                self.fixture.write_text(json.dumps(fixture))
                engine.write_bytes(original_engine)
                identity.write_bytes(original_identity)
                allocation_path.write_bytes(original_allocation)
        recovered = self.run_runtime("deinit", "--preset", "debug", "--json")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(json.loads(allocation_path.read_text())["generation"], transaction["generation"])
        self.assertFalse(path.exists())
        self.assertFalse(self.calls.exists())

    def test_concurrent_deinit_retries_release_only_once(self):
        initial = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_pause"] = "before_release_identity"
        self.fixture.write_text(json.dumps(fixture))
        command = [str(CLI), "deinit", "--preset", "debug", "--json"]
        first = subprocess.Popen(command, cwd=self.worktree, env=self.environment,
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: first.communicate(timeout=15))
        reached = self.wait_for_publication(first)
        reached.unlink()
        fixture["publication_pause"] = "before_lock"
        self.fixture.write_text(json.dumps(fixture))
        second = subprocess.Popen(command, cwd=self.worktree, env=self.environment,
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: second.communicate(timeout=15))
        self.wait_for_publication(second)
        self.fixture.with_suffix(".resume").touch()
        reports = []
        for process in (first, second):
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
            reports.append(json.loads(stdout))
        self.assertEqual(sum(bool(report["released"]) for report in reports), 1)
        self.assertEqual(json.loads((self.state_home / "cubrid-worktree-guard" / "allocations.json").read_text())["allocations"], {})
        self.assertFalse(self.calls.exists())

    def test_deinit_stale_writer_cannot_release_changed_generation_or_configuration(self):
        for target in ("manifest", "identity", "configuration"):
            with self.subTest(target=target):
                self.setUp()
                initial = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
                fixture = json.loads(self.fixture.read_text())
                fixture["publication_pause"] = "before_release_identity"
                self.fixture.write_text(json.dumps(fixture))
                process = subprocess.Popen([str(CLI), "deinit", "--preset", "debug", "--json"],
                                           cwd=self.worktree, env=self.environment,
                                           text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.addCleanup(lambda: process.communicate(timeout=15))
                self.wait_for_publication(process)
                if target == "manifest":
                    path = Path(json.loads(initial.stdout)["manifest_path"])
                    changed = json.loads(path.read_text())
                    changed["generation"] += 1
                    path.write_text(json.dumps(changed))
                else:
                    path = (self.worktree / ".env" if target == "identity" else
                            self.installation / "conf" / "cubrid.conf")
                    path.write_text(path.read_text() + "\n# concurrent user edit\n")
                self.fixture.with_suffix(".resume").touch()
                before = self.snapshot()
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 4, stdout + stderr)
                self.assertEqual(json.loads(stdout)["diagnostic"]["code"], "transaction_generation_conflict")
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.calls.exists())

    def test_adopt_preserves_name_and_disjoint_storage_without_lifecycle(self):
        registry, roots = self.adoption_database()
        (roots[0] / "extension_vinf").write_text("selected extension volume\n")
        with (roots[0] / "CBRD-12345_vinf").open("a") as inventory:
            inventory.write(f"-3 {roots[1] / 'CBRD-12345_bkvinf'}\n")
            inventory.write(f"1 {roots[0] / 'extension_vinf'}\n")
        original_entry = (registry / "databases.txt").read_bytes()
        result = self.run_runtime("adopt", "--preset", "debug", "--db-name", "CBRD-12345",
                                  "--registry", str(registry), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        manifest = self.manifest_for(result)
        self.assertEqual(manifest["database_name"], "CBRD-12345")
        bundle = manifest["resource_bundle"]
        self.assertEqual(bundle["database_registry"], str(registry))
        self.assertEqual([bundle[f"{role}_root"] for role in ("data", "log", "lob")],
                         list(map(str, roots)))
        self.assertEqual((registry / "databases.txt").read_bytes(), original_entry)
        self.assertFalse(self.calls.exists())
        validated = self.run_cli("--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)

    def test_helpers_refuse_without_ready_manifest(self):
        for helper, arguments in (("my-cubrid-pwddb-getname", ()),
                                  ("my-cubrid-pwddb", ("ensure",))):
            result = subprocess.run([str(CLI.parent / helper), *arguments], cwd=self.worktree,
                                    env={**self.environment, "PRESET_MODE": "debug"},
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("ready", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_adopt_preserves_database_names_ending_in_inventory_suffix(self):
        registry, _ = self.adoption_database("existing_vinf")
        result = self.run_runtime("adopt", "--preset", "debug", "--db-name", "existing_vinf",
                                  "--registry", str(registry), "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.manifest_for(result)["database_name"], "existing_vinf")

    def test_adopt_rejects_incomplete_aliased_and_foreign_evidence_without_writes(self):
        for problem in ("duplicate", "other-name", "remote", "missing-lob", "missing-directory",
                        "registry-alias", "registry-hardlink", "storage-alias", "escape",
                        "foreign", "inaccessible", "shared-volume", "volume-alias",
                        "missing-volume", "missing-inventory", "escaped-volume",
                        "other-database", "duplicate-volume-id"):
            with self.subTest(problem=problem):
                self.setUp()
                registry, roots = self.adoption_database()
                entry = registry / "databases.txt"
                original = entry.read_text()
                if problem == "duplicate":
                    entry.write_text(original * 2)
                elif problem == "other-name":
                    entry.write_text(original.replace("CBRD-12345", "unrelated"))
                elif problem == "remote":
                    entry.write_text(original.replace("localhost", "foreign-host"))
                elif problem == "missing-lob":
                    entry.write_text(" ".join(original.split()[:4]) + "\n")
                elif problem == "missing-directory":
                    roots[2].rmdir()
                elif problem == "registry-alias":
                    alias = self.home / "alias"
                    alias.symlink_to(registry, target_is_directory=True)
                    registry = alias
                elif problem == "registry-hardlink":
                    os.link(entry, self.home / "other-registry")
                elif problem == "storage-alias":
                    alias = self.home / "alias"
                    alias.symlink_to(roots[0], target_is_directory=True)
                    entry.write_text(original.replace(str(roots[0]), str(alias)))
                elif problem == "escape":
                    entry.write_text(original.replace(str(roots[0]), str(registry / ".." / roots[0].name)))
                elif problem in ("foreign", "inaccessible"):
                    self.replace_observations({}, {str(roots[0]): {
                        "type": "directory", "mode": "0700", "owner": os.geteuid() + (problem == "foreign"),
                        "accessible": problem != "inaccessible", "canonical": True,
                    }})
                elif problem == "shared-volume":
                    os.link(roots[0] / "CBRD-12345", self.home / "shared-volume")
                elif problem == "volume-alias":
                    (roots[0] / "outside-volume").symlink_to(self.home / "outside")
                elif problem == "missing-volume":
                    (roots[0] / "CBRD-12345").unlink()
                elif problem == "missing-inventory":
                    (roots[0] / "CBRD-12345_vinf").unlink()
                elif problem == "escaped-volume":
                    with (roots[0] / "CBRD-12345_vinf").open("a") as output:
                        output.write(f"1 {self.home / 'foreign-volume'}\n")
                elif problem == "other-database":
                    (roots[0] / "unrelated_vinf").write_text("another database's volume inventory\n")
                elif problem == "duplicate-volume-id":
                    (roots[0] / "CBRD-12345_vinf").write_text(f"0 {roots[0] / 'CBRD-12345'}\n" * 2)
                before = self.snapshot()
                result = self.run_runtime("adopt", "--preset", "debug", "--db-name", "CBRD-12345",
                                          "--registry", str(registry), "--json")
                self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
                self.assertEqual(self.snapshot(), before)

    def test_adopt_rejects_shared_and_nested_managed_roots_without_writes(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        shared = Path(self.manifest_for(initialized)["resource_bundle"]["data_root"])
        other_worktree, _, environment = self.create_additional_runtime("adopt")
        registry, roots = self.adoption_database()
        for root in (shared, shared / "nested", roots[0]):
            root.mkdir(mode=0o700, exist_ok=True)
            (root / "CBRD-12345").write_text("volume")
            (root / "CBRD-12345_vinf").write_text(f"0 {root / 'CBRD-12345'}\n")
            if root == roots[0]:
                metadata = shared.stat()
                self.replace_observations({}, {str(root): {
                    "type": "directory", "owner": os.geteuid(), "mode": "0700",
                    "canonical": True, "device": metadata.st_dev, "inode": metadata.st_ino,
                }})
            entry = registry / "databases.txt"
            entry.write_text(f"CBRD-12345 {root} localhost {roots[1]} file:{roots[2]}\n")
            before = self.snapshot()
            result = self.run_runtime_for(other_worktree, environment, "adopt", "--preset", "debug",
                                           "--db-name", "CBRD-12345", "--registry", str(registry), "--json")
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertEqual(self.snapshot(), before)

    def test_adopt_refuses_live_and_unknown_observations_without_writes(self):
        for condition in ("incomplete", "unlinked-process", "storage-fd", "same-runtime"):
            with self.subTest(condition=condition):
                self.setUp()
                registry, roots = self.adoption_database()
                arguments = ("--preset", "debug", "--db-name", "CBRD-12345", "--registry", str(registry), "--json")
                if condition == "incomplete":
                    self.replace_observations({"complete": False})
                elif condition == "unlinked-process":
                    self.replace_observations({"processes": [{"pid": 123, "configuration": {
                        "database_registry": str(registry)}, "executable": "/foreign/cub_server"}]})
                elif condition == "storage-fd":
                    self.replace_observations({"processes": [{"pid": 123, "configuration": {},
                        "executable": "/foreign/cub_server", "fds": [{"path": str(roots[0] / "CBRD-12345")}]}]})
                else:
                    adopted = self.run_runtime("adopt", *arguments)
                    self.assertEqual(adopted.returncode, 0, adopted.stdout + adopted.stderr)
                    manifest = self.manifest_for(adopted)
                    process = self.runtime_process(manifest)
                    self.replace_observations({"processes": [process], "listeners": [{
                        "protocol": "tcp", "address": "127.0.0.1", "port": manifest["resource_bundle"]["master_port"],
                        "inode": 7001, "namespace": "net:[200]", "owner_pid": 4242, "owner_start_time": 100,
                    }]})
                before = self.snapshot()
                result = self.run_runtime("adopt", *arguments)
                self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
                self.assertEqual(self.snapshot(), before)

    def test_adopt_recovers_every_publication_with_original_generation(self):
        for boundary in (*PUBLICATION_BOUNDARIES, "before_ready_transaction", "after_ready_transaction"):
            with self.subTest(boundary=boundary):
                self.setUp()
                registry, _ = self.adoption_database()
                arguments = ("--preset", "debug", "--db-name", "CBRD-12345", "--registry", str(registry), "--json")
                fixture = json.loads(self.fixture.read_text())
                fixture["publication_failure"] = boundary
                self.fixture.write_text(json.dumps(fixture))
                interrupted = self.run_runtime("adopt", *arguments)
                self.assertEqual(interrupted.returncode, 86, interrupted.stderr + interrupted.stdout)
                transaction_path = next(self.state_home.glob("cubrid-worktree-guard/worktrees/*/transaction.json"))
                transaction = self.read_manifest(transaction_path)
                fixture.pop("publication_failure")
                self.fixture.write_text(json.dumps(fixture))
                before = self.snapshot()
                if boundary != "after_ready_transaction":
                    wrong = self.run_runtime("init", "--preset", "debug", "--json")
                    self.assertEqual(json.loads(wrong.stdout)["diagnostic"]["code"], "transaction_operation_mismatch")
                    self.assertEqual(self.snapshot(), before)
                recovered = self.run_runtime("adopt", *arguments)
                self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
                manifest = self.manifest_for(recovered)
                self.assertEqual(manifest["normalized_claims"], transaction["manifest"]["normalized_claims"])
                if boundary != "after_ready_transaction":
                    self.assertEqual(manifest["generation"], transaction["generation"])
                self.assertEqual(self.run_cli("--preset", "debug").returncode, 0)
                self.assertFalse(self.calls.exists())

    def test_adopt_matching_name_is_not_discovery_and_registry_drift_is_rejected(self):
        registry, roots = self.adoption_database()
        absent = self.run_cli("--preset", "debug")
        self.assertEqual(absent.returncode, 3)
        self.assertFalse(self.state_home.exists())
        adopted = self.run_runtime("adopt", "--preset", "debug", "--db-name", "CBRD-12345",
                                   "--registry", str(registry), "--json")
        self.assertEqual(adopted.returncode, 0, adopted.stdout + adopted.stderr)
        helper = subprocess.run([str(CLI.parent / "my-cubrid-pwddb-getname")], cwd=self.worktree,
                                env={**self.environment, "PRESET_MODE": "debug"}, text=True, capture_output=True)
        self.assertEqual(helper.stdout, "CBRD-12345\n", helper.stderr)
        entry = registry / "databases.txt"
        entry.write_text(entry.read_text().replace(str(roots[0]), str(roots[1])))
        before = self.snapshot()
        result = self.run_cli("--preset", "debug", "--json")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(self.snapshot(), before)

    def test_adopt_recovery_fences_changed_registry_without_writes(self):
        registry, _ = self.adoption_database()
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_failure"] = "after_manifest"
        self.fixture.write_text(json.dumps(fixture))
        result = self.run_runtime("adopt", "--preset", "debug", "--db-name", "CBRD-12345",
                                  "--registry", str(registry), "--json")
        self.assertEqual(result.returncode, 86)
        fixture.pop("publication_failure")
        self.fixture.write_text(json.dumps(fixture))
        other = self.home / "other-registry"
        other.mkdir(mode=0o700)
        shutil.copy2(registry / "databases.txt", other / "databases.txt")
        before = self.snapshot()
        result = self.run_runtime("adopt", "--preset", "debug", "--db-name", "CBRD-12345",
                                  "--registry", str(other), "--json")
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(json.loads(result.stdout)["diagnostic"]["code"], "transaction_operation_mismatch")

    def manifest_for(self, result):
        report = json.loads(result.stdout)
        return self.read_manifest(Path(report["manifest_path"]))

    def read_manifest(self, path):
        return json.loads(path.read_text())

    def configure_broker_spawn_environment(self, content):
        source_environment = self.installation / "conf" / "query-editor.env"
        if isinstance(content, bytes):
            source_environment.write_bytes(content)
        else:
            source_environment.write_text(content)
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(
            broker_path.read_text().replace(
                "CUSTOM_BROKER_SETTING=preserved",
                "SOURCE_ENV=conf/query-editor.env\nCUSTOM_BROKER_SETTING=preserved",
            )
        )
        return source_environment

    def use_fake_state(self, runtime_id, manifest, observations=None):
        environment_path = self.worktree / ".env"
        manifest_path = (
            self.state_home
            / "cubrid-worktree-guard"
            / "worktrees"
            / runtime_id
            / "manifest.json"
        )
        self.fixture.write_text(json.dumps({
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
        return manifest_path

    def observation_scope(self):
        return {
            "observer": "fake-linux",
            "uid": os.geteuid(),
            "boot_id": "synthetic-boot",
            "namespaces": {
                "pid": "pid:[100]",
                "network": "net:[200]",
                "ipc": "ipc:[300]",
                "mount": "mnt:[400]",
            },
            "sources": {
                "processes": "complete",
                "sockets": "complete",
                "listeners": "complete",
                "system_v_ipc": "complete",
                "filesystem": "complete",
                "configuration": "complete",
            },
            "inaccessible_processes": [],
        }

    def runtime_process(self, manifest, *, pid=4242, start_time=100, **changes):
        bundle = manifest["resource_bundle"]
        process = {
            "pid": pid,
            "name": "cub_master",
            "start_time": start_time,
            "start_wall_ns": 123455 * 1_000_000_000,
            "executable": str(Path(bundle["executable_directory"]) / "cub_master"),
            "libraries": [
                record.get("resolved_path", record["path"])
                for record in manifest["installation"]["libraries"]
            ],
            "loaded_files": [
                record.get("resolved_path", record["path"])
                for record in manifest["installation"]["libraries"]
            ],
            "deleted_libraries": [],
            "system_v_keys": [bundle["master_shm_key"]],
            "namespaces": dict(self.observation_scope()["namespaces"]),
            "configuration": {
                "installation_root": bundle["installation_root"],
                "cubrid_tmp": bundle["cubrid_tmp"],
                "database_registry": bundle["database_registry"],
                "active_preset": manifest["active_preset"],
                "evidence": "launch-correlated",
                "engine_configuration": manifest["configurations"]["engine"]["path"],
                "engine_configuration_sha256": manifest["configurations"]["engine"]["sha256"],
                "broker_configuration": manifest["configurations"]["broker"]["path"],
                "broker_configuration_sha256": manifest["configurations"]["broker"]["sha256"],
            },
            "fds": [{"socket_inode": 7001}],
            "accessible": True,
        }
        process.update(changes)
        return process

    def replace_observations(self, observations, filesystem=None):
        self.fixture.write_text(json.dumps({
            "filesystem": filesystem or {},
            "observations": {
                "complete": True,
                "scope": self.observation_scope(),
                "processes": [],
                "sockets": [],
                "listeners": [],
                "system_v_ipc": [],
                **observations,
            },
        }))

    def test_interrupted_registry_publication_retains_claims_and_recovers(self):
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_failure"] = "before_registry"
        self.fixture.write_text(json.dumps(fixture))
        interrupted = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertNotEqual(interrupted.returncode, 0)
        guard = self.state_home / "cubrid-worktree-guard"
        transactions = list(guard.glob("worktrees/*/transaction.json"))
        self.assertEqual(len(transactions), 1)
        transaction = self.read_manifest(transactions[0])
        claims = transaction["manifest"]["normalized_claims"]
        self.assertEqual(transaction["state"], "initializing")
        self.assertNotEqual(self.run_cli("--preset", "debug").returncode, 0)

        fixture.pop("publication_failure")
        self.fixture.write_text(json.dumps(fixture))
        other_worktree, _, other_environment = self.create_additional_runtime("other")
        other = self.run_runtime_for(
            other_worktree, other_environment, "init", "--preset", "debug", "--json"
        )
        self.assertEqual(other.returncode, 0, other.stderr + other.stdout)
        for kind in ("tcp_ports", "system_v_keys", "paths"):
            self.assertTrue(set(claims[kind]).isdisjoint(
                self.manifest_for(other)["normalized_claims"][kind]
            ), kind)
        recovered = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
        manifest = self.manifest_for(recovered)
        self.assertEqual(manifest["generation"], transaction["generation"])
        self.assertEqual(manifest["normalized_claims"], claims)
        self.assertEqual(self.run_cli("--preset", "debug").returncode, 0)
        self.assertFalse(self.calls.exists())

    def interrupt_initialization(self, boundary):
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_failure"] = boundary
        self.fixture.write_text(json.dumps(fixture))
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 86, result.stderr + result.stdout)
        fixture.pop("publication_failure")
        self.fixture.write_text(json.dumps(fixture))
        guard = self.state_home / "cubrid-worktree-guard"
        paths = list(guard.glob("worktrees/*/transaction.json"))
        self.assertEqual(len(paths), 1)
        return paths[0], self.read_manifest(paths[0])

    def test_every_publication_boundary_is_non_ready_and_recoverable(self):
        for boundary in PUBLICATION_BOUNDARIES:
            with self.subTest(boundary=boundary):
                self.setUp()
                transaction_path, transaction = self.interrupt_initialization(boundary)
                retained = transaction["manifest"]
                self.assertNotEqual(self.run_cli("--preset", "debug").returncode, 0)
                guard = transaction_path.parents[2]
                for path in (guard, *guard.rglob("*")):
                    self.assertEqual(path.stat().st_mode & 0o777,
                                     0o700 if path.is_dir() else 0o600, str(path))
                recovered = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
                manifest = self.manifest_for(recovered)
                self.assertEqual(manifest["generation"], transaction["generation"])
                self.assertEqual(manifest["normalized_claims"], retained["normalized_claims"])
                self.assertEqual(self.read_manifest(transaction_path)["state"], "ready")
                self.assertEqual(self.run_cli("--preset", "debug").returncode, 0)
                self.assertFalse(self.calls.exists())

    def test_ready_runtime_reinitialization_recovers_each_publication_boundary(self):
        for boundary in PUBLICATION_BOUNDARIES:
            with self.subTest(boundary=boundary):
                self.setUp()
                initial = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)
                previous = self.manifest_for(initial)
                path, transaction = self.interrupt_initialization(boundary)
                self.assertNotEqual(self.run_cli("--preset", "debug").returncode, 0)
                recovered = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
                manifest = self.manifest_for(recovered)
                self.assertEqual(manifest["generation"], transaction["generation"])
                self.assertEqual(manifest["normalized_claims"], previous["normalized_claims"])
                self.assertEqual(self.run_cli("--preset", "debug").returncode, 0)

    def test_final_transaction_publication_is_the_readiness_commit_marker(self):
        for when in ("before", "after"):
            with self.subTest(when=when):
                self.setUp()
                path, transaction = self.interrupt_initialization(f"{when}_ready_transaction")
                validated = self.run_cli("--preset", "debug", "--json")
                self.assertEqual(validated.returncode == 0, when == "after")
                recovered = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
                self.assertEqual(self.manifest_for(recovered)["normalized_claims"],
                                 transaction["manifest"]["normalized_claims"])
                self.assertEqual(self.read_manifest(path)["state"], "ready")

    def test_recovery_refuses_other_commands_and_changed_selection(self):
        transaction_path, transaction = self.interrupt_initialization("after_environment")
        before = self.snapshot()
        for command, options in (
            ("adopt", ()), ("deinit", ()),
            ("init", ("--db-name", "different")),
            ("init", ("--preset", "release_gcc")),
        ):
            with self.subTest(command=command, options=options):
                result = self.run_runtime(command, "--preset", "debug", *options, "--json")
                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                diagnostic = json.loads(result.stdout)["diagnostic"]
                self.assertEqual(diagnostic["code"], "transaction_operation_mismatch")
                self.assertIn("init", diagnostic["next_action"])
                self.assertEqual(self.snapshot(), before)

    def test_recovery_retains_claims_when_live_evidence_is_contradictory(self):
        transaction_path, transaction = self.interrupt_initialization("after_environment")
        manifest = transaction["manifest"]
        self.replace_observations({"listeners": [{
            "port": manifest["resource_bundle"]["master_port"],
            "inode": 7001, "owner_pid": 404, "owner_start_time": 100,
            "protocol": "tcp", "address": "0.0.0.0",
            "namespace": self.observation_scope()["namespaces"]["network"],
        }]})
        environment = (transaction_path.parent / "env.sh").read_bytes()
        engine = (self.installation / "conf" / "cubrid.conf").read_bytes()
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertEqual(self.read_manifest(transaction_path)["state"], "recovery_required")
        self.assertEqual(self.read_manifest(transaction_path.parent / "manifest.json")["state"],
                         "recovery_required")
        registry = self.read_manifest(transaction_path.parents[2] / "allocations.json")
        self.assertEqual(registry["allocations"][manifest["worktree_id"]]["claims"],
                         manifest["normalized_claims"])
        self.assertEqual((transaction_path.parent / "env.sh").read_bytes(), environment)
        self.assertEqual((self.installation / "conf" / "cubrid.conf").read_bytes(), engine)
        self.assertIn("init", json.loads(result.stdout)["diagnostic"]["next_action"])
        self.replace_observations({})
        recovered = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
        self.assertEqual(self.manifest_for(recovered)["generation"], transaction["generation"])
        self.assertFalse(self.calls.exists())

    def test_newer_published_generation_fences_a_stale_recovery(self):
        for target in ("manifest", "registry"):
            with self.subTest(target=target):
                self.setUp()
                path, transaction = self.interrupt_initialization("after_environment")
                if target == "manifest":
                    changed_path = path.parent / "manifest.json"
                    changed = self.read_manifest(changed_path)
                    changed["generation"] += 1
                else:
                    changed_path = path.parents[2] / "allocations.json"
                    changed = self.read_manifest(changed_path)
                    changed["generation"] += 1
                    changed["allocations"][transaction["manifest"]["worktree_id"]]["generation"] += 1
                changed_path.write_text(json.dumps(changed))
                before = self.snapshot()
                result = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                self.assertEqual(json.loads(result.stdout)["diagnostic"]["code"],
                                 "transaction_generation_conflict")
                self.assertEqual(self.snapshot(), before)

    def test_recovery_does_not_overwrite_configuration_outside_its_partial_plan(self):
        path, transaction = self.interrupt_initialization("after_engine_configuration")
        engine = self.installation / "conf" / "cubrid.conf"
        edited = engine.read_text() + "\n# edit after interruption\n"
        engine.write_text(edited)
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["diagnostic"]["code"],
                         "transaction_input_changed")
        self.assertEqual(engine.read_text(), edited)
        self.assertEqual(self.read_manifest(path)["state"], "recovery_required")

    def wait_for_publication(self, process):
        reached = self.fixture.with_suffix(".reached")
        deadline = time.monotonic() + 5
        while not reached.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.01)
        self.assertTrue(reached.exists(), "guard did not reach the publication boundary")
        return reached

    def launch_runtime(self, worktree=None, environment=None):
        process = subprocess.Popen(
            [str(CLI), "init", "--preset", "debug", "--json"],
            cwd=worktree or self.worktree, env=environment or self.environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: process.communicate(timeout=15))
        return process

    def test_stale_writer_cannot_publish_after_newer_state_appears(self):
        path, transaction = self.interrupt_initialization("after_environment")
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_pause"] = "before_ready_manifest"
        self.fixture.write_text(json.dumps(fixture))
        process = self.launch_runtime()
        self.wait_for_publication(process)
        manifest_path = path.parent / "manifest.json"
        newer = self.read_manifest(manifest_path)
        newer["generation"] += 1
        manifest_path.write_text(json.dumps(newer))
        self.fixture.with_suffix(".resume").touch()
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 4, stderr + stdout)
        self.assertEqual(json.loads(stdout)["diagnostic"]["code"], "transaction_generation_conflict")
        self.assertEqual(self.read_manifest(manifest_path), newer)
        self.assertEqual(self.read_manifest(path)["generation"], transaction["generation"])

    def test_concurrent_retries_accept_exactly_one_generation(self):
        path, interrupted = self.interrupt_initialization("after_environment")
        fixture = json.loads(self.fixture.read_text())
        fixture["publication_pause"] = "before_ready_manifest"
        self.fixture.write_text(json.dumps(fixture))
        first = self.launch_runtime()
        self.wait_for_publication(first)
        second_fixture = self.root / "second-observations.json"
        fixture["publication_pause"] = "before_lock"
        second_fixture.write_text(json.dumps(fixture))
        second = self.launch_runtime(environment={
            **self.environment, "MY_CUBRID_RUNTIME_TEST_OBSERVATIONS": str(second_fixture),
        })
        original_fixture = self.fixture
        self.fixture = second_fixture
        self.wait_for_publication(second)
        self.fixture = original_fixture
        second_fixture.with_suffix(".resume").touch()
        self.fixture.with_suffix(".resume").touch()
        results = [process.communicate(timeout=10) for process in (first, second)]
        for process, (stdout, stderr) in zip((first, second), results):
            self.assertEqual(process.returncode, 0, stderr + stdout)
        self.assertEqual(self.read_manifest(path)["generation"], interrupted["generation"])
        registry = self.read_manifest(path.parents[2] / "allocations.json")
        self.assertEqual(len(registry["allocations"]), 1)
        self.assertEqual(registry["generation"], interrupted["generation"])
        self.assertEqual(self.run_cli("--preset", "debug").returncode, 0)

    def test_missing_worktree_and_old_transaction_never_release_claims(self):
        path, transaction = self.interrupt_initialization("before_registry")
        transaction["created_at"] = "1970-01-01T00:00:00Z"
        transaction["lease_expires_at"] = "1970-01-01T00:00:01Z"
        path.write_text(json.dumps(transaction))
        os.utime(path, (1, 1))
        missing_worktree = self.worktree.with_name("temporarily-missing")
        self.worktree.rename(missing_worktree)
        before = path.read_bytes()
        other_worktree, _, environment = self.create_additional_runtime("other")
        result = self.run_runtime_for(other_worktree, environment, "init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime, 1)
        for kind in ("tcp_ports", "system_v_keys", "paths"):
            self.assertTrue(set(transaction["manifest"]["normalized_claims"][kind]).isdisjoint(
                self.manifest_for(result)["normalized_claims"][kind]
            ))
        missing_worktree.rename(self.worktree)
        recovered = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
        self.assertEqual(self.manifest_for(recovered)["generation"], transaction["generation"])

    def test_deinitializing_generation_cannot_be_overwritten_by_init(self):
        path, transaction = self.interrupt_initialization("after_environment")
        transaction["operation"] = "deinit"
        transaction["state"] = "deinitializing"
        transaction["manifest"]["state"] = "deinitializing"
        path.write_text(json.dumps(transaction))
        (path.parent / "manifest.json").write_text(json.dumps(transaction["manifest"]))
        registry_path = path.parents[2] / "allocations.json"
        registry = self.read_manifest(registry_path)
        registry["allocations"][transaction["manifest"]["worktree_id"]]["state"] = "deinitializing"
        registry_path.write_text(json.dumps(registry))
        before = self.snapshot()
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["diagnostic"]["code"], "transaction_operation_mismatch")
        self.assertIn("deinit", json.loads(result.stdout)["diagnostic"]["next_action"])
        self.assertEqual(self.snapshot(), before)
        self.assertNotEqual(self.run_cli("--preset", "debug").returncode, 0)

    def test_replacing_worktree_id_cannot_bypass_unfinished_generation(self):
        path, _ = self.interrupt_initialization("after_environment")
        (self.worktree / ".env").write_text("CUBRID_WORKTREE_ID=replacement01\n")
        before = self.snapshot()
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["diagnostic"]["code"], "transaction_operation_mismatch")
        self.assertEqual(self.snapshot(), before)

    def test_recovery_requires_complete_fresh_observation(self):
        path, transaction = self.interrupt_initialization("after_environment")
        self.replace_observations({"complete": False})
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertEqual(self.read_manifest(path)["state"], "recovery_required")
        self.assertEqual(self.read_manifest(path)["manifest"]["normalized_claims"],
                         transaction["manifest"]["normalized_claims"])

    def test_failed_recovery_before_registry_does_not_relabel_predecessor_generation(self):
        initial = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)
        path, transaction = self.interrupt_initialization("before_registry")
        self.replace_observations({"complete": False})
        refused = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(refused.returncode, 4, refused.stderr + refused.stdout)
        self.replace_observations({})
        recovered = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
        self.assertEqual(self.manifest_for(recovered)["generation"], transaction["generation"])

    def test_recovery_preserves_runtime_data_and_stale_sockets(self):
        path, transaction = self.interrupt_initialization("after_environment")
        bundle = transaction["manifest"]["resource_bundle"]
        canaries = [Path(bundle[kind]) / "keep" for kind in ("data_root", "log_root", "lob_root")]
        for canary in canaries:
            canary.write_bytes(b"existing database data\x00")
        socket_path = Path(bundle["socket_paths"][0])
        socket_path.write_bytes(b"stale socket stand-in")
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        for canary in canaries:
            self.assertEqual(canary.read_bytes(), b"existing database data\x00")
        self.assertEqual(socket_path.read_bytes(), b"stale socket stand-in")
        self.assertEqual(self.read_manifest(path)["state"], "recovery_required")
        self.assertFalse(self.calls.exists())

    def test_init_creates_one_complete_runtime_and_validate_reports_ready(self):
        (self.worktree / ".env").write_text(
            "# human setting\nPRESET_MODE=debug\n\nOTHER=value\n"
        )
        self.assertIn(
            "service=server,broker,manager",
            (self.installation / "conf" / "cubrid.conf").read_text(),
        )

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        init_report = json.loads(initialized.stdout)
        self.assertEqual(init_report["outcome"], "ready")
        self.assertTrue(init_report["ready"])
        runtime_id = init_report["worktree_id"]
        manifest_path = (
            self.state_home / "cubrid-worktree-guard" / "worktrees"
            / runtime_id / "manifest.json"
        )
        manifest = self.read_manifest(manifest_path)
        bundle = manifest["resource_bundle"]
        self.assertEqual(manifest["state"], "ready")
        self.assertEqual(manifest["active_preset"], "debug")
        self.assertEqual(bundle["database_name"], manifest["database_name"])
        self.assertEqual(bundle["installation_root"], str(self.installation))
        self.assertEqual(
            bundle["engine_configuration"],
            str(self.installation / "conf" / "cubrid.conf"),
        )
        self.assertEqual(bundle["master_port"], 15000)
        self.assertEqual(bundle["brokers"][0]["port"], 20000)
        self.assertEqual(bundle["master_shm_key"], 0x60000000)
        self.assertEqual(bundle["brokers"][0]["appl_server_shm_key"], 0x60000001)
        self.assertEqual(
            bundle["brokers"][0]["query_replacement_shm_key"], 0x51000001
        )
        effective = manifest["configurations"]["effective"]
        self.assertEqual(effective["engine"]["service"], "server,broker")
        self.assertEqual(effective["engine"]["cubrid_port_id"], "15000")

        self.assertEqual(effective["engine"]["stored_procedure_uds"], "yes")
        self.assertEqual(effective["broker"]["MASTER_SHM_ID"], "0x60000000")
        self.assertRegex(manifest["database_name"], r"^[A-Za-z][A-Za-z0-9_]{0,16}$")
        self.assertTrue(manifest["database_name"].startswith("source"))
        self.assertIn(str(Path(bundle["cubrid_tmp"]) / "CUBRID15000"), bundle["socket_paths"])
        self.assertIn(str(Path(bundle["cubrid_tmp"]) / "query_editor.B"), bundle["socket_paths"])
        self.assertIn(str(Path(bundle["cubrid_tmp"]) / "query_editor.2"), bundle["socket_paths"])
        self.assertIn(bundle["pl_socket_path"], bundle["socket_paths"])
        self.assertIn(
            bundle["pl_mutable_paths"]["info"], manifest["normalized_claims"]["paths"]
        )
        self.assertEqual(bundle["cubrid_tmp"], str(self.home / ".cub" / "runtime" / runtime_id[:8] / "tmp"))
        self.assertEqual(
            bundle["database_registry"],
            str(self.home / ".cub" / "db" / runtime_id[:8] / "commondb"),
        )
        self.assertFalse((Path(bundle["data_root"]) / manifest["database_name"]).exists())
        self.assertFalse((Path(bundle["database_registry"]) / "databases.txt").exists())
        self.assertFalse(any(path.name == manifest["database_name"] for path in self.root.rglob("*")))
        self.assertIn("# human setting\nPRESET_MODE=debug\n\nOTHER=value\n", (self.worktree / ".env").read_text())
        self.assertEqual((self.worktree / ".env").read_text().count("CUBRID_WORKTREE_ID="), 1)
        engine = (self.installation / "conf" / "cubrid.conf").read_text()
        broker = (self.installation / "conf" / "cubrid_broker.conf").read_text()
        self.assertIn("# engine comment", engine)
        self.assertIn("custom_parameter=preserved", engine)
        self.assertIn("service=server,broker", engine)
        self.assertIn("cubrid_port_id=15000", engine)
        self.assertIn("stored_procedure_uds=yes", engine)
        self.assertIn("# broker comment", broker)
        self.assertIn("CUSTOM_BROKER_SETTING=preserved", broker)
        self.assertIn("MASTER_SHM_ID=0x60000000", broker)
        self.assertIn("BROKER_PORT=20000", broker)
        self.assertIn("APPL_SERVER_SHM_ID=0x60000001", broker)
        for path in (
            self.state_home / "cubrid-worktree-guard",
            manifest_path.parent,
            Path(bundle["cubrid_tmp"]),
            Path(bundle["database_registry"]),
        ):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for path in (
            self.state_home / "cubrid-worktree-guard" / "allocations.json",
            self.state_home / "cubrid-worktree-guard" / "registry.lock",
            manifest_path,
            manifest_path.parent / "env.sh",
        ):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

        before_validation = self.snapshot()
        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        validation_report = json.loads(validated.stdout)
        self.assertEqual(validation_report["outcome"], "ready")
        self.assertTrue(validation_report["ready"])
        self.assertEqual(self.snapshot(), before_validation)
        self.assertFalse(self.calls.exists())

    def test_validate_accepts_a_listener_positively_owned_by_this_runtime(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest)
        self.replace_observations({
            "processes": [process],
            "listeners": [{
                "protocol": "tcp",
                "address": "0.0.0.0",
                "port": manifest["resource_bundle"]["master_port"],
                "inode": 7001,
                "namespace": self.observation_scope()["namespaces"]["network"],
                "owner_pid": process["pid"],
                "owner_start_time": process["start_time"],
            }],
        })

        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        human = self.run_runtime("validate", "--preset", "debug")

        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(report["outcome"], "ready")
        ownership = report["live_ownership"]
        self.assertEqual(ownership["classification"], "same-runtime")
        self.assertEqual(ownership["normalized_value"], "tcp://0.0.0.0:15000")
        self.assertIn("socket inode to file descriptor", ownership["evidence"])
        self.assertEqual(ownership["missing_evidence"], [])
        self.assertEqual(ownership["observation_scope"], self.observation_scope())
        self.assertIn("Live ownership: same-runtime", human.stdout)
        self.assertIn(f"Expected owner: {ownership['expected_owner']}", human.stdout)
        self.assertIn(f"Observed owner: {ownership['observed_owner']}", human.stdout)
        self.assertIn("Next action: " + ownership["next_action"], human.stdout)
        self.assertFalse(self.calls.exists())

    def test_managed_foreign_listener_is_a_conflict_with_equivalent_diagnostics(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest, managed_runtime_id="runtime-foreign")
        self.replace_observations({
            "processes": [process],
            "listeners": [{
                "protocol": "tcp",
                "address": "0.0.0.0",
                "port": manifest["resource_bundle"]["master_port"],
                "inode": 7001,
                "namespace": self.observation_scope()["namespaces"]["network"],
                "owner_pid": process["pid"],
                "owner_start_time": process["start_time"],
            }],
        })

        structured = self.run_runtime("validate", "--preset", "debug", "--json")
        human = self.run_runtime("validate", "--preset", "debug")

        self.assertEqual(structured.returncode, 4, structured.stderr + structured.stdout)
        report = json.loads(structured.stdout)
        diagnostic = report["diagnostic"]
        self.assertEqual(diagnostic["code"], "live_ownership_conflict")
        self.assertEqual(diagnostic["normalized_value"], "tcp://0.0.0.0:15000")
        self.assertEqual(
            diagnostic["expected_owner"],
            f"worktree runtime {manifest['worktree_id']}",
        )
        self.assertIn("runtime-foreign", diagnostic["observed_owner"])
        self.assertIn("socket inode to file descriptor", diagnostic["evidence"])
        self.assertEqual(diagnostic["missing_evidence"], [])
        self.assertEqual(diagnostic["observation_scope"], self.observation_scope())
        self.assertEqual(human.returncode, structured.returncode)
        self.assertIn(f"Normalized value: {diagnostic['normalized_value']}", human.stdout)
        self.assertIn(f"Expected owner: {diagnostic['expected_owner']}", human.stdout)
        self.assertIn(f"Observed owner: {diagnostic['observed_owner']}", human.stdout)
        self.assertIn("Evidence: " + ", ".join(diagnostic["evidence"]), human.stdout)
        self.assertIn("Observation scope: ", human.stdout)
        self.assertFalse(self.calls.exists())

    def test_unmanaged_listener_and_wrong_library_are_conflicts(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        for process in (
            self.runtime_process(
                manifest,
                executable=str(self.root / "unmanaged" / "cub_master"),
            ),
            self.runtime_process(
                manifest,
                libraries=[str(self.root / "foreign" / "libcubrid.so")],
            ),
        ):
            with self.subTest(process=process["executable"], libraries=process["libraries"]):
                self.replace_observations({
                    "processes": [process],
                    "listeners": [{
                        "protocol": "tcp",
                        "address": "127.0.0.1",
                        "port": manifest["resource_bundle"]["master_port"],
                        "inode": 7001,
                        "namespace": self.observation_scope()["namespaces"]["network"],
                        "owner_pid": process["pid"],
                        "owner_start_time": process["start_time"],
                    }],
                })
                result = self.run_runtime("validate", "--preset", "debug", "--json")
                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                diagnostic = json.loads(result.stdout)["diagnostic"]
                self.assertEqual(diagnostic["code"], "live_ownership_conflict")
                self.assertEqual(diagnostic["evidence_quality"], "definitive")
        self.assertFalse(self.calls.exists())

    def test_incomplete_or_contradictory_listener_evidence_is_unknown(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        base_process = self.runtime_process(manifest)
        base_listener = {
            "protocol": "tcp",
            "address": "0.0.0.0",
            "port": manifest["resource_bundle"]["master_port"],
            "inode": 7001,
            "namespace": self.observation_scope()["namespaces"]["network"],
            "owner_pid": base_process["pid"],
            "owner_start_time": base_process["start_time"],
        }
        cases = []
        reused = dict(base_listener, owner_start_time=99)
        cases.append(("reused-pid", base_process, reused))
        hidden = dict(base_process, accessible=False)
        cases.append(("hidden-process", hidden, base_listener))
        wrong_namespace = dict(base_listener, namespace="net:[999]")
        cases.append(("wrong-namespace", base_process, wrong_namespace))
        wrong_address = dict(base_listener, address="127.0.0.1")
        cases.append(("wrong-listener-address", base_process, wrong_address))
        wrong_owner = dict(base_listener, inode=9999)
        cases.append(("wrong-socket-owner", base_process, wrong_owner))
        contradictory = dict(base_process)
        contradictory["configuration"] = dict(
            base_process["configuration"], cubrid_tmp=str(self.root / "other-tmp")
        )
        cases.append(("contradictory-configuration", contradictory, base_listener))

        for name, process, listener in cases:
            with self.subTest(name=name):
                self.replace_observations({
                    "processes": [process],
                    "listeners": [listener],
                })
                result = self.run_runtime("validate", "--preset", "debug", "--json")
                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                diagnostic = json.loads(result.stdout)["diagnostic"]
                self.assertEqual(diagnostic["code"], "live_ownership_unknown")
                self.assertEqual(diagnostic["evidence_quality"], "unknown")
                self.assertTrue(diagnostic["missing_evidence"])
                self.assertEqual(diagnostic["observation_scope"], self.observation_scope())
        self.assertFalse(self.calls.exists())

    def test_validate_correlates_same_runtime_socket_and_system_v_segment(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        bundle = manifest["resource_bundle"]
        process = self.runtime_process(
            manifest,
            fds=[{"socket_inode": 8001}],
        )
        socket_path = bundle["socket_paths"][0]
        self.replace_observations({
            "processes": [process],
            "sockets": [{
                "path": socket_path,
                "inode": 8001,
                "namespace": self.observation_scope()["namespaces"]["network"],
                "owner_pid": process["pid"],
                "owner_start_time": process["start_time"],
                "device": 55,
                "path_inode": 66,
                "filesystem_identity_correlated": True,
            }],
            "system_v_ipc": [{
                "key": bundle["master_shm_key"],
                "shmid": 71,
                "uid": os.geteuid(),
                "cpid": process["pid"],
                "ctime": 123456,
                "nattch": 1,
                "namespace": self.observation_scope()["namespaces"]["ipc"],
                "process_start_time": process["start_time"],
            }],
        }, filesystem={
            socket_path: {
                "type": "socket",
                "owner": os.geteuid(),
                "mode": "0700",
                "device": 55,
                "inode": 66,
            },
        })

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        self.assertEqual(json.loads(validated.stdout)["outcome"], "ready")
        self.assertFalse(self.calls.exists())

    def test_stale_path_and_incomplete_ipc_metadata_are_unknown(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        bundle = manifest["resource_bundle"]
        socket_path = bundle["socket_paths"][0]
        self.replace_observations({}, filesystem={
            socket_path: {
                "type": "socket",
                "owner": os.geteuid(),
                "mode": "0700",
                "device": 55,
                "inode": 66,
            },
        })
        stale = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(stale.returncode, 4, stale.stderr + stale.stdout)
        self.assertEqual(
            json.loads(stale.stdout)["diagnostic"]["code"], "live_ownership_unknown"
        )

        process = self.runtime_process(manifest, fds=[{"socket_inode": 8001}])
        self.replace_observations({
            "processes": [process],
            "sockets": [{
                "path": socket_path,
                "inode": 8001,
                "namespace": self.observation_scope()["namespaces"]["network"],
                "owner_pid": process["pid"],
                "owner_start_time": process["start_time"],
                "device": 55,
                "path_inode": 66,
                "filesystem_identity_correlated": False,
            }],
        }, filesystem={
            socket_path: {
                "type": "socket", "owner": os.geteuid(), "mode": "0700",
                "device": 55, "inode": 66,
            },
        })
        replaced_path = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(
            replaced_path.returncode, 4, replaced_path.stderr + replaced_path.stdout
        )
        self.assertEqual(
            json.loads(replaced_path.stdout)["diagnostic"]["code"],
            "live_ownership_unknown",
        )

        self.replace_observations({
            "system_v_ipc": [{
                "key": bundle["master_shm_key"],
                "shmid": 71,
                "uid": os.geteuid(),
            }],
        })
        incomplete_ipc = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(
            incomplete_ipc.returncode, 4, incomplete_ipc.stderr + incomplete_ipc.stdout
        )
        diagnostic = json.loads(incomplete_ipc.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "live_ownership_unknown")
        self.assertIn("ctime", diagnostic["missing_evidence"])
        self.assertFalse(self.calls.exists())

    def test_socket_permission_denial_is_unknown(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        socket_path = manifest["resource_bundle"]["socket_paths"][0]
        self.replace_observations({}, filesystem={
            socket_path: {
                "type": "socket",
                "accessible": False,
                "owner": None,
                "mode": "0000",
            },
        })

        result = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        diagnostic = json.loads(result.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "live_ownership_unknown")
        self.assertEqual(diagnostic["evidence_quality"], "unknown")
        self.assertIn("readable socket filesystem identity", diagnostic["missing_evidence"])
        self.assertFalse(self.calls.exists())

    def test_init_refuses_same_runtime_live_and_unknown_claims_without_mutation(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest)
        listener = {
            "protocol": "tcp",
            "address": "0.0.0.0",
            "port": manifest["resource_bundle"]["master_port"],
            "inode": 7001,
            "namespace": self.observation_scope()["namespaces"]["network"],
            "owner_pid": process["pid"],
            "owner_start_time": process["start_time"],
        }
        self.replace_observations({"processes": [process], "listeners": [listener]})
        before_live = self.snapshot()

        live = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(live.returncode, 4, live.stderr + live.stdout)
        self.assertEqual(
            json.loads(live.stdout)["diagnostic"]["code"], "runtime_mutation_live"
        )
        self.assertEqual(self.snapshot(), before_live)

        listener["owner_start_time"] = 99
        self.replace_observations({"processes": [process], "listeners": [listener]})
        before_unknown = self.snapshot()
        unknown = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(unknown.returncode, 4, unknown.stderr + unknown.stdout)
        self.assertEqual(
            json.loads(unknown.stdout)["diagnostic"]["code"], "live_ownership_unknown"
        )
        self.assertEqual(self.snapshot(), before_unknown)
        self.assertFalse(self.calls.exists())

    def test_first_init_ownership_refusal_preserves_exact_state(self):
        runtime_id = "runtime01"
        (self.worktree / ".env").write_text(f"CUBRID_WORKTREE_ID={runtime_id}\n")
        socket_path = str(
            self.home / ".cub" / "runtime" / runtime_id[:8] / "tmp" / "CUBRID15000"
        )
        self.replace_observations({}, filesystem={
            socket_path: {
                "type": "socket",
                "owner": os.geteuid(),
                "mode": "0700",
                "device": 55,
                "inode": 66,
            },
        })
        before = self.snapshot()

        refused = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(refused.returncode, 4, refused.stderr + refused.stdout)
        self.assertEqual(
            json.loads(refused.stdout)["diagnostic"]["code"],
            "live_ownership_unknown",
        )
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.state_home / "cubrid-worktree-guard").exists())
        self.assertFalse(self.calls.exists())

    def test_first_init_refusal_does_not_create_missing_lock_or_chmod_guard_root(self):
        runtime_id = "runtime01"
        (self.worktree / ".env").write_text(f"CUBRID_WORKTREE_ID={runtime_id}\n")
        guard_root = self.state_home / "cubrid-worktree-guard"
        guard_root.mkdir(parents=True, mode=0o750)
        guard_root.chmod(0o750)
        socket_path = str(
            self.home / ".cub" / "runtime" / runtime_id[:8] / "tmp" / "CUBRID15000"
        )
        self.replace_observations({}, filesystem={
            socket_path: {
                "type": "socket", "owner": os.geteuid(), "mode": "0700",
                "device": 55, "inode": 66,
            },
        })
        before = self.snapshot()

        refused = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(refused.returncode, 4, refused.stderr + refused.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(guard_root.stat().st_mode & 0o777, 0o750)
        self.assertFalse((guard_root / "registry.lock").exists())
        self.assertFalse(self.calls.exists())

    def test_preset_takeover_refuses_live_previous_preset_but_allows_proven_idle(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest)
        self.replace_observations({
            "processes": [process],
            "listeners": [{
                "protocol": "tcp",
                "address": "0.0.0.0",
                "port": manifest["resource_bundle"]["master_port"],
                "inode": 7001,
                "namespace": self.observation_scope()["namespaces"]["network"],
                "owner_pid": process["pid"],
                "owner_start_time": process["start_time"],
            }],
        })
        release_installation = self.root / "install-release-live"
        shutil.copytree(self.installation, release_installation)
        self.environment["CUBRID"] = str(release_installation)
        self.environment["CUBRID_BUILD_DIR"] = str(
            self.worktree / "build_preset_release_gcc"
        )
        before_live = self.snapshot()

        blocked = self.run_runtime("init", "--preset", "release_gcc", "--json")

        self.assertEqual(blocked.returncode, 4, blocked.stderr + blocked.stdout)
        self.assertIn(
            json.loads(blocked.stdout)["diagnostic"]["code"],
            {"live_ownership_conflict", "live_ownership_unknown"},
        )
        self.assertEqual(self.snapshot(), before_live)

        self.replace_observations({})
        takeover = self.run_runtime("init", "--preset", "release_gcc", "--json")
        self.assertEqual(takeover.returncode, 0, takeover.stderr + takeover.stdout)
        self.assertEqual(
            self.manifest_for(takeover)["active_preset"], "release_gcc"
        )
        self.assertFalse(self.calls.exists())

    def test_unmanaged_system_v_segment_is_a_conflict(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        self.replace_observations({
            "system_v_ipc": [{
                "key": manifest["resource_bundle"]["master_shm_key"],
                "shmid": 88,
                "uid": os.geteuid(),
                "cpid": 9999,
                "ctime": 123456,
                "nattch": 1,
                "namespace": self.observation_scope()["namespaces"]["ipc"],
                "owner_classification": "unmanaged",
            }],
        })

        result = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        diagnostic = json.loads(result.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "live_ownership_conflict")
        self.assertEqual(
            diagnostic["normalized_value"],
            f"0x{manifest['resource_bundle']['master_shm_key']:08x}",
        )
        self.assertIn("unmanaged segment", diagnostic["observed_owner"])
        self.assertFalse(self.calls.exists())

    def test_orphaned_or_reused_pid_system_v_evidence_is_unknown(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest)
        segment = {
            "key": manifest["resource_bundle"]["master_shm_key"],
            "shmid": 88,
            "uid": os.geteuid(),
            "cpid": process["pid"],
            "ctime": 123456,
            "nattch": 1,
            "namespace": self.observation_scope()["namespaces"]["ipc"],
            "process_start_time": 99,
        }
        self.replace_observations({
            "processes": [process],
            "system_v_ipc": [segment],
        })
        reused = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(reused.returncode, 4, reused.stderr + reused.stdout)
        self.assertEqual(
            json.loads(reused.stdout)["diagnostic"]["code"], "live_ownership_unknown"
        )

        segment.pop("process_start_time")
        self.replace_observations({"system_v_ipc": [segment]})
        orphaned = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(orphaned.returncode, 4, orphaned.stderr + orphaned.stdout)
        diagnostic = json.loads(orphaned.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "live_ownership_unknown")
        self.assertTrue(any(
            "visible process attachment" in item
            for item in diagnostic["missing_evidence"]
        ))
        self.assertFalse(self.calls.exists())

    def test_system_v_creator_wall_start_detects_reused_unmanaged_pid(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        attached = self.runtime_process(manifest)
        reused_creator = {
            "pid": 4343,
            "name": "sh",
            "start_time": 200,
            "start_wall_ns": 123457 * 1_000_000_000,
            "executable": "/usr/bin/sh",
            "libraries": [],
            "loaded_files": [],
            "deleted_libraries": [],
            "system_v_keys": [],
            "namespaces": dict(self.observation_scope()["namespaces"]),
            "configuration": {},
            "fds": [],
            "accessible": True,
        }
        self.replace_observations({
            "processes": [attached, reused_creator],
            "system_v_ipc": [{
                "key": manifest["resource_bundle"]["master_shm_key"],
                "shmid": 88,
                "uid": os.geteuid(),
                "cpid": reused_creator["pid"],
                "ctime": 123456,
                "nattch": 1,
                "namespace": self.observation_scope()["namespaces"]["ipc"],
            }],
        })

        result = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        diagnostic = json.loads(result.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "live_ownership_unknown")
        self.assertIn("matching creator process generation", diagnostic["missing_evidence"])
        self.assertFalse(self.calls.exists())

    def test_system_v_same_second_creator_generation_is_unknown(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(
            manifest,
            start_wall_ns=123456 * 1_000_000_000 + 500_000_000,
        )
        self.replace_observations({
            "processes": [process],
            "system_v_ipc": [{
                "key": manifest["resource_bundle"]["master_shm_key"],
                "shmid": 88,
                "uid": os.geteuid(),
                "cpid": process["pid"],
                "ctime": 123456,
                "nattch": 1,
                "namespace": self.observation_scope()["namespaces"]["ipc"],
            }],
        })

        result = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        diagnostic = json.loads(result.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "live_ownership_unknown")
        self.assertIn(
            "precise creator process generation",
            diagnostic["missing_evidence"],
        )
        self.assertFalse(self.calls.exists())

    def test_current_only_configuration_and_deleted_library_evidence_are_unknown(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest)
        listener = {
            "protocol": "tcp",
            "address": "0.0.0.0",
            "port": manifest["resource_bundle"]["master_port"],
            "inode": 7001,
            "namespace": self.observation_scope()["namespaces"]["network"],
            "owner_pid": process["pid"],
            "owner_start_time": process["start_time"],
        }
        current_only = dict(process)
        current_only["configuration"] = dict(
            process["configuration"], evidence="current-files-only"
        )
        deleted = dict(process, deleted_libraries=list(process["libraries"]))
        for name, observed_process in (
            ("current-config", current_only),
            ("deleted-library", deleted),
        ):
            with self.subTest(name=name):
                self.replace_observations({
                    "processes": [observed_process],
                    "listeners": [listener],
                })
                result = self.run_runtime("validate", "--preset", "debug", "--json")
                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["diagnostic"]["code"],
                    "live_ownership_unknown",
                )
        self.assertFalse(self.calls.exists())

    def test_foreign_loaded_file_with_cubrid_library_name_is_a_conflict(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest)
        process["loaded_files"] = [
            *process["loaded_files"],
            str(self.root / "foreign" / "libcubrid.so"),
        ]
        self.replace_observations({
            "processes": [process],
            "listeners": [{
                "protocol": "tcp", "address": "0.0.0.0",
                "port": manifest["resource_bundle"]["master_port"],
                "inode": 7001,
                "namespace": self.observation_scope()["namespaces"]["network"],
                "owner_pid": process["pid"],
                "owner_start_time": process["start_time"],
            }],
        })

        result = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["diagnostic"]["code"],
            "live_ownership_conflict",
        )
        self.assertFalse(self.calls.exists())

    def test_single_identifiers_and_mixed_evidence_never_establish_ownership(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        process = self.runtime_process(manifest)
        port = manifest["resource_bundle"]["master_port"]
        cases = (
            ("numeric-port", {"listeners": [{"protocol": "tcp", "port": port}]}),
            ("mixed", {
                "processes": [process],
                "listeners": [{
                    "protocol": "tcp",
                    "address": "0.0.0.0",
                    "port": port,
                    "inode": 7001,
                    "namespace": self.observation_scope()["namespaces"]["network"],
                    "owner_pid": process["pid"],
                    "owner_start_time": 99,
                }],
            }),
        )
        for name, observations in cases:
            with self.subTest(name=name):
                self.replace_observations(observations)
                result = self.run_runtime("validate", "--preset", "debug", "--json")
                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                diagnostic = json.loads(result.stdout)["diagnostic"]
                self.assertEqual(diagnostic["code"], "live_ownership_unknown")
                self.assertTrue(diagnostic["missing_evidence"])
        self.replace_observations({"processes": [{"name": "cub_master"}]})
        process_name_only = self.run_runtime(
            "validate", "--preset", "debug", "--json"
        )
        self.assertEqual(
            process_name_only.returncode,
            0,
            process_name_only.stderr + process_name_only.stdout,
        )
        self.assertFalse(self.calls.exists())

    def test_init_allocates_around_a_complete_foreign_runtime_observation(self):
        self.replace_observations({
            "processes": [{
                "pid": 9001,
                "name": "cub_master",
                "start_time": 10,
                "executable": str(self.root / "foreign" / "bin" / "cub_master"),
                "libraries": [str(self.root / "foreign" / "lib" / "libcubrid.so")],
                "namespaces": dict(self.observation_scope()["namespaces"]),
                "configuration": {
                    "installation_root": str(self.root / "foreign"),
                    "cubrid_tmp": str(self.root / "foreign-tmp"),
                    "database_registry": str(self.root / "foreign-db"),
                },
                "fds": [{"socket_inode": 90001}],
                "accessible": True,
            }],
            "listeners": [{
                "protocol": "tcp",
                "address": "0.0.0.0",
                "port": 15500,
                "inode": 90001,
                "namespace": self.observation_scope()["namespaces"]["network"],
                "owner_pid": 9001,
                "owner_start_time": 10,
            }],
        })

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        self.assertEqual(
            self.manifest_for(initialized)["resource_bundle"]["master_port"], 15000
        )
        self.assertFalse(self.calls.exists())

    def test_init_is_idempotent_and_database_override_is_stable(self):
        first = self.run_runtime(
            "init", "--preset", "debug", "--db-name", "Chosen_DB1", "--json"
        )
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        first_report = json.loads(first.stdout)
        manifest_path = Path(first_report["manifest_path"])
        first_manifest = json.loads(manifest_path.read_text())
        first_environment = (self.worktree / ".env").read_text()

        second = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        second_report = json.loads(second.stdout)
        second_manifest = json.loads(manifest_path.read_text())
        self.assertEqual(second_report["worktree_id"], first_report["worktree_id"])
        self.assertEqual(second_manifest["database_name"], "Chosen_DB1")
        self.assertEqual(
            second_manifest["resource_bundle"], first_manifest["resource_bundle"]
        )
        self.assertEqual((self.worktree / ".env").read_text(), first_environment)
        self.assertGreater(second_manifest["generation"], first_manifest["generation"])
        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        release_installation = self.root / "install-release"
        shutil.copytree(self.installation, release_installation)
        self.environment["CUBRID"] = str(release_installation)
        self.environment["CUBRID_BUILD_DIR"] = str(
            self.worktree / "build_preset_release_gcc"
        )
        takeover = self.run_runtime("init", "--preset", "release_gcc", "--json")
        self.assertEqual(takeover.returncode, 0, takeover.stderr + takeover.stdout)
        takeover_manifest = json.loads(manifest_path.read_text())
        self.assertEqual(json.loads(takeover.stdout)["worktree_id"], first_report["worktree_id"])
        for stable_field in (
            "database_name", "cubrid_tmp", "database_registry", "data_root",
            "log_root", "lob_root", "master_port", "master_shm_key", "brokers",
            "socket_paths", "pl_socket_path",
        ):
            self.assertEqual(
                takeover_manifest["resource_bundle"][stable_field],
                first_manifest["resource_bundle"][stable_field],
            )
        self.assertEqual(
            takeover_manifest["resource_bundle"]["installation_root"],
            str(release_installation),
        )
        self.assertTrue(
            takeover_manifest["resource_bundle"]["pl_mutable_paths"]["info"].startswith(
                str(release_installation)
            )
        )
        self.assertEqual(takeover_manifest["active_preset"], "release_gcc")
        self.assertEqual(
            self.run_runtime("validate", "--preset", "release_gcc", "--json").returncode,
            0,
        )
        self.assertFalse(self.calls.exists())

    def test_illegal_database_override_is_rejected_before_mutation(self):
        before = self.snapshot()

        result = self.run_runtime(
            "init", "--preset", "debug", "--db-name", "18-characters-long", "--json"
        )

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["diagnostic"]["code"], "database_name_invalid")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_configurable_allocation_ranges_are_applied_as_one_bundle(self):
        self.environment.update({
            "MY_CUBRID_RUNTIME_MASTER_PORT_RANGE": "15123-15123",
            "MY_CUBRID_RUNTIME_BROKER_PORT_RANGE": "23123-23123",
            "MY_CUBRID_RUNTIME_SHM_KEY_RANGE": "0x60000100-0x60000101",
        })

        result = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        manifest = self.manifest_for(result)
        bundle = manifest["resource_bundle"]
        self.assertEqual(bundle["master_port"], 15123)
        self.assertEqual(bundle["brokers"][0]["port"], 23123)
        self.assertEqual(bundle["master_shm_key"], 0x60000100)
        self.assertEqual(bundle["brokers"][0]["appl_server_shm_key"], 0x60000101)
        self.assertEqual(
            manifest["normalized_claims"]["system_v_keys"],
            [0x60000100, 0x60000101, 0x51000101],
        )
        self.assertFalse(self.calls.exists())

    def test_init_allocates_every_enabled_broker_as_one_disjoint_bundle(self):
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(
            broker_path.read_text()
            + "\n[%analytics]\n"
            + "SERVICE=ON\n"
            + "BROKER_PORT=33000\n"
            + "MAX_NUM_APPL_SERVER=3\n"
            + "APPL_SERVER_SHM_ID=0x33000\n"
            + "ANALYTICS_SETTING=preserved\n"
        )

        result = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        manifest = self.manifest_for(result)
        bundle = manifest["resource_bundle"]
        self.assertEqual(
            [broker["name"] for broker in bundle["brokers"]],
            ["query_editor", "analytics"],
        )
        self.assertEqual(
            [broker["port"] for broker in bundle["brokers"]], [20000, 20001]
        )
        self.assertEqual(
            [broker["appl_server_shm_key"] for broker in bundle["brokers"]],
            [0x60000001, 0x60000002],
        )
        self.assertEqual(
            manifest["normalized_claims"]["system_v_keys"],
            [
                0x60000000,
                0x60000001,
                0x60000002,
                0x51000001,
                0x51000002,
            ],
        )
        patched = broker_path.read_text()
        self.assertIn("ANALYTICS_SETTING=preserved", patched)
        self.assertIn("[%analytics]\nSERVICE=ON\nBROKER_PORT=20001", patched)
        self.assertIn("APPL_SERVER_SHM_ID=0x60000002", patched)
        self.assertFalse(self.calls.exists())

    def test_fake_occupied_values_are_excluded_by_key_not_kernel_shmid(self):
        self.fixture.write_text(json.dumps({
            "filesystem": {},
            "observations": {
                "complete": True,
                "processes": [],
                "sockets": [],
                "listeners": [{"port": 15000}, {"port": 20000}],
                "system_v_ipc": [
                    {"key": 0x60000000, "shmid": 41},
                    {"key": 0x51000002, "shmid": 0x60000001},
                ],
            },
        }))

        result = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        manifest = self.manifest_for(result)
        bundle = manifest["resource_bundle"]
        self.assertEqual(bundle["master_port"], 15001)
        self.assertEqual(bundle["brokers"][0]["port"], 20001)
        self.assertEqual(bundle["master_shm_key"], 0x60000001)
        self.assertEqual(bundle["brokers"][0]["appl_server_shm_key"], 0x60000003)
        self.assertEqual(
            bundle["brokers"][0]["query_replacement_shm_key"], 0x51000003
        )
        self.assertIn("MASTER_SHM_ID=0x60000001", (
            self.installation / "conf" / "cubrid_broker.conf"
        ).read_text())
        self.assertFalse(self.calls.exists())

    def test_broker_shared_memory_configuration_uses_hexadecimal_key_grammar(self):
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(
            broker_path.read_text().replace(
                "MASTER_SHM_ID=30001", "MASTER_SHM_ID=not-a-system-v-key"
            )
        )
        before = self.snapshot()

        result = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["diagnostic"]["code"], "broker_configuration_invalid")
        self.assertEqual(report["diagnostic"]["affected_object"]["kind"], "broker shared-memory key")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_broker_defaults_and_section_case_match_cubrid_effective_values(self):
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(
            "[BROKER]\nMASTER_SHM_ID=30001\n\n"
            "[%CaseBroker]\nBROKER_PORT=30000\nAPPL_SERVER_SHM_ID=30000\n"
        )

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        broker = manifest["resource_bundle"]["brokers"][0]
        self.assertEqual(broker["section"], "%casebroker")
        self.assertEqual(broker["name"], "casebroker")
        self.assertEqual(broker["max_appl_servers"], 40)
        self.assertEqual(len(broker["socket_paths"]), 41)
        configured = broker_path.read_text()
        self.assertIn("[BROKER]\nMASTER_SHM_ID=0x60000000", configured)
        self.assertNotIn("\n[broker]\n", configured)
        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)

    def test_ordinary_broker_names_may_contain_gateway_or_shard(self):
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(
            broker_path.read_text().replace("%query_editor", "%gateway_api")
            + "\n[%shard_reader]\nSERVICE=ON\nSHARD=OFF\nMAX_NUM_APPL_SERVER=1\n"
        )

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        self.assertEqual(
            [broker["section"] for broker in manifest["resource_bundle"]["brokers"]],
            ["%gateway_api", "%shard_reader"],
        )
        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        self.assertFalse(self.calls.exists())

    def test_claims_are_collected_from_every_manifest_not_only_the_registry(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        first = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        first_report = json.loads(first.stdout)
        first_manifest = self.manifest_for(first)
        registry_path = self.state_home / "cubrid-worktree-guard" / "allocations.json"
        registry = json.loads(registry_path.read_text())
        del registry["allocations"][first_report["worktree_id"]]
        registry_path.write_text(json.dumps(registry))

        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )

        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        second_manifest = self.manifest_for(second)
        first_claims = first_manifest["normalized_claims"]
        second_claims = second_manifest["normalized_claims"]
        for claim_kind in ("tcp_ports", "system_v_keys", "paths"):
            self.assertTrue(
                set(first_claims[claim_kind]).isdisjoint(second_claims[claim_kind]),
                claim_kind,
            )
        self.assertEqual(second_manifest["resource_bundle"]["master_port"], 15001)
        self.assertEqual(second_manifest["resource_bundle"]["brokers"][0]["port"], 20001)
        self.assertEqual(second_manifest["resource_bundle"]["master_shm_key"], 0x60000002)
        self.assertFalse(self.calls.exists())

    def test_incomplete_manifest_claims_fail_closed_instead_of_being_reused(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        first = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        first_report = json.loads(first.stdout)
        manifest_path = Path(first_report["manifest_path"])
        manifest = self.read_manifest(manifest_path)
        manifest["normalized_claims"] = {
            "tcp_ports": [],
            "system_v_keys": [],
            "paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))
        registry_path = self.state_home / "cubrid-worktree-guard" / "allocations.json"
        registry = json.loads(registry_path.read_text())
        del registry["allocations"][first_report["worktree_id"]]
        registry_path.write_text(json.dumps(registry))

        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )

        self.assertEqual(second.returncode, 4, second.stderr + second.stdout)
        report = json.loads(second.stdout)
        self.assertEqual(report["diagnostic"]["code"], "managed_claims_invalid")
        self.assertFalse((second_worktree / ".env").exists())
        self.assertFalse(self.calls.exists())

    def test_semantically_incomplete_manifest_bundle_fails_closed(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        first = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        first_report = json.loads(first.stdout)
        manifest_path = Path(first_report["manifest_path"])
        manifest = self.read_manifest(manifest_path)
        manifest["resource_bundle"]["brokers"] = []
        manifest["normalized_claims"]["tcp_ports"] = [
            manifest["resource_bundle"]["master_port"]
        ]
        manifest["normalized_claims"]["system_v_keys"] = [
            manifest["resource_bundle"]["master_shm_key"]
        ]
        manifest_path.write_text(json.dumps(manifest))
        registry_path = self.state_home / "cubrid-worktree-guard" / "allocations.json"
        registry = json.loads(registry_path.read_text())
        del registry["allocations"][first_report["worktree_id"]]
        registry_path.write_text(json.dumps(registry))

        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )

        self.assertEqual(second.returncode, 4, second.stderr + second.stdout)
        report = json.loads(second.stdout)
        self.assertEqual(report["diagnostic"]["code"], "managed_claims_invalid")
        self.assertFalse((second_worktree / ".env").exists())
        self.assertFalse(self.calls.exists())

    def test_repeated_init_rejects_a_new_managed_collision_with_its_retained_bundle(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        first = self.run_runtime("init", "--preset", "debug", "--json")
        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        first_manifest = self.manifest_for(first)
        second_manifest_path = Path(json.loads(second.stdout)["manifest_path"])
        second_manifest = self.read_manifest(second_manifest_path)
        old_master_socket = second_manifest["resource_bundle"]["socket_paths"][0]
        new_master_port = first_manifest["resource_bundle"]["master_port"]
        new_master_socket = str(
            Path(second_manifest["resource_bundle"]["cubrid_tmp"])
            / f"CUBRID{new_master_port}"
        )
        second_manifest["resource_bundle"]["master_port"] = (
            new_master_port
        )
        second_manifest["resource_bundle"]["socket_paths"][0] = new_master_socket
        second_manifest["normalized_claims"]["tcp_ports"][0] = (
            new_master_port
        )
        second_manifest["normalized_claims"]["paths"] = [
            new_master_socket if path == old_master_socket else path
            for path in second_manifest["normalized_claims"]["paths"]
        ]
        second_manifest_path.write_text(json.dumps(second_manifest))
        registry_path = self.state_home / "cubrid-worktree-guard" / "allocations.json"
        registry = json.loads(registry_path.read_text())
        registry["allocations"][second_manifest["worktree_id"]]["claims"] = (
            second_manifest["normalized_claims"]
        )
        registry_path.write_text(json.dumps(registry))
        before = self.snapshot()

        repeated = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(repeated.returncode, 4, repeated.stderr + repeated.stdout)
        report = json.loads(repeated.stdout)
        self.assertEqual(report["diagnostic"]["code"], "managed_claim_collision")
        self.assertEqual(report["diagnostic"]["affected_object"]["kind"], "TCP port")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_ready_reports_no_kernel_reservation_and_possible_startup_race(self):
        structured = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(structured.returncode, 0, structured.stderr + structured.stdout)
        report = json.loads(structured.stdout)
        self.assertFalse(report["kernel_resources_reserved"])
        self.assertTrue(report["kernel_acquisition_can_race"])

        human = self.run_runtime("validate", "--preset", "debug")
        self.assertEqual(human.returncode, 0, human.stderr + human.stdout)
        self.assertIn("Kernel reservation: none", human.stdout)
        self.assertIn("later kernel acquisition can still race", human.stdout)
        self.assertFalse(self.calls.exists())

    def test_init_makes_no_kernel_listener_or_system_v_reservation(self):
        strace = shutil.which("strace")
        self.assertIsNotNone(strace, "strace is required for kernel-reservation evidence")
        trace_path = self.root / "allocation-syscalls.trace"

        result = subprocess.run(
            [
                strace,
                "-f",
                "-qq",
                "-e",
                "trace=bind,listen,shmget",
                "-o",
                str(trace_path),
                str(CLI),
                "init",
                "--preset",
                "debug",
                "--json",
            ],
            cwd=self.worktree,
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        trace = trace_path.read_text()
        for reserving_call in ("bind(", "listen(", "shmget("):
            self.assertNotIn(reserving_call, trace)
        self.assertFalse(self.calls.exists())

    def test_two_worktrees_keep_stable_disjoint_complete_bundles(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")

        first = self.run_runtime("init", "--preset", "debug", "--json")
        repeated = self.run_runtime("init", "--preset", "debug", "--json")
        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )

        for result in (first, repeated, second):
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        first_manifest = self.manifest_for(first)
        repeated_manifest = self.manifest_for(repeated)
        second_manifest = self.manifest_for(second)
        self.assertEqual(
            first_manifest["resource_bundle"], repeated_manifest["resource_bundle"]
        )
        self.assertEqual(second_manifest["resource_bundle"]["master_port"], 15001)
        self.assertEqual(second_manifest["resource_bundle"]["brokers"][0]["port"], 20001)
        self.assertEqual(second_manifest["resource_bundle"]["master_shm_key"], 0x60000002)
        for claim_kind in ("tcp_ports", "system_v_keys", "paths"):
            self.assertTrue(set(first_manifest["normalized_claims"][claim_kind]).isdisjoint(
                second_manifest["normalized_claims"][claim_kind]
            ))
        self.assertFalse(self.calls.exists())

    def test_two_worktrees_cannot_reuse_one_stable_runtime_identity(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        first = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        runtime_id = json.loads(first.stdout)["worktree_id"]
        (second_worktree / ".env").write_text(f"CUBRID_WORKTREE_ID={runtime_id}\n")
        before_manifest = Path(json.loads(first.stdout)["manifest_path"]).read_text()

        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )

        self.assertEqual(second.returncode, 4, second.stderr + second.stdout)
        report = json.loads(second.stdout)
        self.assertEqual(report["diagnostic"]["code"], "worktree_identity_collision")
        self.assertEqual(
            Path(json.loads(first.stdout)["manifest_path"]).read_text(), before_manifest
        )
        self.assertFalse(self.calls.exists())

    def test_overlapping_port_ranges_still_exclude_cross_role_collisions(self):
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(
            broker_path.read_text()
            + "\n[%analytics]\nSERVICE=ON\nMAX_NUM_APPL_SERVER=1\n"
        )
        self.environment.update({
            "MY_CUBRID_RUNTIME_MASTER_PORT_RANGE": "25000-25002",
            "MY_CUBRID_RUNTIME_BROKER_PORT_RANGE": "25000-25002",
        })

        result = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        manifest = self.manifest_for(result)
        bundle = manifest["resource_bundle"]
        self.assertEqual(bundle["master_port"], 25000)
        self.assertEqual(
            [broker["port"] for broker in bundle["brokers"]], [25001, 25002]
        )
        self.assertEqual(len(set(manifest["normalized_claims"]["tcp_ports"])), 3)
        self.assertFalse(self.calls.exists())

    def test_two_worktrees_cannot_claim_the_same_mutable_installation_paths(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        second_environment["CUBRID"] = str(self.installation)
        first = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )

        self.assertEqual(second.returncode, 4, second.stderr + second.stdout)
        report = json.loads(second.stdout)
        self.assertEqual(report["diagnostic"]["code"], "managed_path_collision")
        self.assertIn(
            report["diagnostic"]["affected_object"]["value"],
            {str(self.installation / "tmp"), str(self.installation / "log")},
        )
        self.assertFalse((second_worktree / ".env").exists())
        self.assertFalse(self.calls.exists())

    def test_range_exhaustion_fails_without_duplicate_or_partial_claims(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        for environment in (self.environment, second_environment):
            environment.update({
                "MY_CUBRID_RUNTIME_MASTER_PORT_RANGE": "15000-15000",
                "MY_CUBRID_RUNTIME_BROKER_PORT_RANGE": "20000-20000",
                "MY_CUBRID_RUNTIME_SHM_KEY_RANGE": "0x60000000-0x60000001",
            })
        first = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

        second = self.run_runtime_for(
            second_worktree,
            second_environment,
            "init",
            "--preset",
            "debug",
            "--json",
        )

        self.assertEqual(second.returncode, 4, second.stderr + second.stdout)
        self.assertEqual(json.loads(second.stdout)["diagnostic"]["code"], "allocation_exhausted")
        registry = json.loads((
            self.state_home / "cubrid-worktree-guard" / "allocations.json"
        ).read_text())
        self.assertEqual(len(registry["allocations"]), 1)
        manifests = list((
            self.state_home / "cubrid-worktree-guard" / "worktrees"
        ).glob("*/manifest.json"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(len(list(manifests[0].parent.parent.iterdir())), 1)
        self.assertEqual(self.read_manifest(manifests[0])["state"], "ready")
        self.assertFalse((second_worktree / ".env").exists())
        self.assertFalse(self.calls.exists())

    def test_concurrent_initializations_publish_only_disjoint_ready_bundles(self):
        second_worktree, _, second_environment = self.create_additional_runtime("two")
        first_process = subprocess.Popen(
            [str(CLI), "init", "--preset", "debug", "--json"],
            cwd=self.worktree,
            env=self.environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        second_process = subprocess.Popen(
            [str(CLI), "init", "--preset", "debug", "--json"],
            cwd=second_worktree,
            env=second_environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        first_stdout, first_stderr = first_process.communicate(timeout=10)
        second_stdout, second_stderr = second_process.communicate(timeout=10)

        self.assertEqual(first_process.returncode, 0, first_stderr + first_stdout)
        self.assertEqual(second_process.returncode, 0, second_stderr + second_stdout)
        reports = [json.loads(first_stdout), json.loads(second_stdout)]
        manifests = [
            self.read_manifest(Path(report["manifest_path"])) for report in reports
        ]
        self.assertTrue(set(manifests[0]["normalized_claims"]["tcp_ports"]).isdisjoint(
            manifests[1]["normalized_claims"]["tcp_ports"]
        ))
        self.assertTrue(set(manifests[0]["normalized_claims"]["system_v_keys"]).isdisjoint(
            manifests[1]["normalized_claims"]["system_v_keys"]
        ))
        self.assertTrue(set(manifests[0]["normalized_claims"]["paths"]).isdisjoint(
            manifests[1]["normalized_claims"]["paths"]
        ))
        self.assertEqual([manifest["state"] for manifest in manifests], ["ready", "ready"])
        registry = json.loads((
            self.state_home / "cubrid-worktree-guard" / "allocations.json"
        ).read_text())
        self.assertEqual(len(registry["allocations"]), 2)
        self.assertTrue(all(
            allocation["state"] == "ready"
            for allocation in registry["allocations"].values()
        ))
        self.assertFalse(self.calls.exists())

    def home_for_pl_socket_length(self, target_bytes, database_name):
        runtime_id = "runtime01"
        suffix = f"/.cub/runtime/{runtime_id[:8]}/tmp/sp_{database_name}.sock"
        home_bytes = target_bytes - len(suffix.encode())
        segment_bytes = home_bytes - len(os.fsencode(self.root)) - 1
        self.assertGreater(segment_bytes, 2)
        segment = "é" * (segment_bytes // 2)
        if segment_bytes % 2:
            segment += "a"
        home = self.root / segment
        self.assertEqual(len(os.fsencode(home)), home_bytes)
        home.mkdir()
        self.environment["HOME"] = str(home)
        (self.worktree / ".env").write_text(f"CUBRID_WORKTREE_ID={runtime_id}\n")
        return home

    def test_multibyte_socket_path_at_linux_boundary_is_accepted(self):
        database_name = "BoundaryName12345"
        self.home_for_pl_socket_length(107, database_name)

        result = self.run_runtime(
            "init", "--preset", "debug", "--db-name", database_name, "--json"
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        manifest = self.manifest_for(result)
        pl_socket = manifest["resource_bundle"]["pl_socket_path"]
        self.assertEqual(len(os.fsencode(pl_socket)), 107)
        self.assertFalse(self.calls.exists())

    def test_multibyte_socket_path_beyond_linux_boundary_fails_before_mutation(self):
        database_name = "BoundaryName12345"
        self.home_for_pl_socket_length(108, database_name)
        before = self.snapshot()

        result = self.run_runtime(
            "init", "--preset", "debug", "--db-name", database_name, "--json"
        )

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["diagnostic"]["code"], "socket_path_too_long")
        self.assertIn("108 bytes", report["diagnostic"]["message"])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_aliased_and_relative_runtime_paths_fail_closed_before_mutation(self):
        real_home = self.root / "canonical-home"
        real_home.mkdir()
        alias_home = self.root / "alias-home"
        alias_home.symlink_to(real_home, target_is_directory=True)
        self.environment["HOME"] = str(alias_home)
        before_alias = self.snapshot()

        aliased = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(aliased.returncode, 4, aliased.stderr + aliased.stdout)
        self.assertEqual(json.loads(aliased.stdout)["diagnostic"]["code"], "path_unsafe")
        self.assertEqual(self.snapshot(), before_alias)

        self.environment["HOME"] = str(self.home)
        self.environment["CUBRID"] = "relative-install"
        before_relative = self.snapshot()
        relative = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(relative.returncode, 4, relative.stderr + relative.stdout)
        self.assertEqual(json.loads(relative.stdout)["diagnostic"]["code"], "path_unsafe")
        self.assertEqual(self.snapshot(), before_relative)
        self.assertFalse(self.calls.exists())

    def test_foreign_owned_and_world_writable_runtime_paths_fail_closed(self):
        unsafe_home = self.root / "unsafe-home"
        unsafe_home.mkdir(mode=0o777)
        unsafe_home.chmod(0o777)
        self.environment["HOME"] = str(unsafe_home)
        before = self.snapshot()
        unsafe = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(unsafe.returncode, 4, unsafe.stderr + unsafe.stdout)
        self.assertEqual(json.loads(unsafe.stdout)["diagnostic"]["code"], "path_unsafe")
        self.assertEqual(self.snapshot(), before)

        if Path("/tmp").stat().st_uid != os.geteuid():
            self.environment["HOME"] = "/tmp"
            before_foreign = self.snapshot()
            foreign = self.run_runtime("init", "--preset", "debug", "--json")
            self.assertEqual(foreign.returncode, 4, foreign.stderr + foreign.stdout)
            self.assertEqual(
                json.loads(foreign.stdout)["diagnostic"]["code"], "path_wrong_owner"
            )
            diagnostic = json.loads(foreign.stdout)["diagnostic"]
            self.assertEqual(diagnostic["expected_owner"], os.geteuid())
            self.assertEqual(diagnostic["observed_value"], str(Path("/tmp").stat().st_uid))
            self.assertEqual(self.snapshot(), before_foreign)
        self.assertFalse(self.calls.exists())

    def test_unsafe_private_path_ancestor_fails_before_mutation(self):
        runtime_id = "runtime01"
        (self.worktree / ".env").write_text(
            f"CUBRID_WORKTREE_ID={runtime_id}\n"
        )
        private_root = self.home / ".cub"
        runtime_tmp = private_root / "runtime" / runtime_id / "tmp"
        runtime_tmp.mkdir(parents=True, mode=0o700)
        private_root.chmod(0o777)
        before = self.snapshot()

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        report = json.loads(initialized.stdout)
        self.assertEqual(report["diagnostic"]["code"], "path_unsafe")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_aliased_private_configuration_fails_before_mutation(self):
        configuration = self.installation / "conf" / "cubrid.conf"
        content = configuration.read_text()
        alternate = self.root / "alternate-cubrid.conf"
        alternate.write_text(content)
        configuration.unlink()
        configuration.symlink_to(alternate)
        before = self.snapshot()

        result = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["diagnostic"]["code"], "path_unsafe")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_generated_environment_round_trips_shell_hostile_values_without_evaluation(self):
        marker = self.root / "must-not-exist"
        hostile_home = self.root / "home dir ' ;$HOME"
        hostile_home.mkdir()
        self.home = hostile_home
        self.environment["HOME"] = str(hostile_home)
        hostile_build = self.root / "build dir ' ;$(touch must-not-exist)\nsecond-line"
        self.environment["CUBRID_BUILD_DIR"] = str(hostile_build)
        result = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        environment_path = Path(json.loads(result.stdout)["environment_path"])

        sourced = subprocess.run(
            [
                "sh", "-c",
                '. "$1"; printf "%s\\0%s\\0%s\\0%s" "$CUBRID_BUILD_DIR" '
                '"$CUBRID_DATABASES" "$CUBRID_TMP" "$CUBRID_RUNTIME_READY"',
                "sh", str(environment_path),
            ],
            cwd=self.root,
            env={
                "PATH": os.environ["PATH"],
                "CUBRID_CONF_FILE": str(self.root / "hostile.conf"),
                "CUBRID_CUBRID_PORT_ID": "19999",
            },
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(sourced.returncode, 0, sourced.stderr.decode())
        values = sourced.stdout.split(b"\0")
        self.assertEqual(values[0].decode(), str(hostile_build))
        self.assertEqual(values[1].decode(), str(self.home / ".cub" / "db" / json.loads(result.stdout)["worktree_id"][:8] / "commondb"))
        self.assertEqual(values[2].decode(), str(self.home / ".cub" / "runtime" / json.loads(result.stdout)["worktree_id"][:8] / "tmp"))
        self.assertEqual(values[3], b"1")
        checked = subprocess.run(
            [
                "sh", "-c",
                '. "$1"; printf "%s\\0%s" "${CUBRID_CONF_FILE-unset}" '
                '"${CUBRID_CUBRID_PORT_ID-unset}"',
                "sh", str(environment_path),
            ],
            env={
                "PATH": os.environ["PATH"],
                "CUBRID_CONF_FILE": str(self.root / "hostile.conf"),
                "CUBRID_CUBRID_PORT_ID": "19999",
            },
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr.decode())
        self.assertEqual(checked.stdout.split(b"\0"), [b"unset", b"unset"])
        self.environment["CUBRID_CONF_FILE"] = str(self.root / "hostile.conf")
        rejected = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(rejected.returncode, 4, rejected.stderr + rejected.stdout)
        self.assertEqual(
            json.loads(rejected.stdout)["diagnostic"]["code"],
            "configuration_selection_drift",
        )
        self.assertFalse(marker.exists())
        self.assertFalse(self.calls.exists())

    def test_path_list_separator_in_installation_is_rejected_before_mutation(self):
        ambiguous_installation = self.root / "install:alternate"
        shutil.copytree(self.installation, ambiguous_installation)
        self.environment["CUBRID"] = str(ambiguous_installation)
        before = self.snapshot()

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        report = json.loads(initialized.stdout)
        self.assertEqual(report["diagnostic"]["code"], "path_list_ambiguous")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_generated_environment_has_no_empty_path_list_element(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        environment_path = Path(json.loads(initialized.stdout)["environment_path"])

        sourced = subprocess.run(
            [
                "/bin/sh",
                "-c",
                '. "$1"; printf "%s\\0%s" "$PATH" "$LD_LIBRARY_PATH"',
                "sh",
                str(environment_path),
            ],
            env={"PATH": "", "LD_LIBRARY_PATH": ""},
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(sourced.returncode, 0, sourced.stderr.decode())
        self.assertEqual(
            sourced.stdout.split(b"\0"),
            [
                os.fsencode(self.installation / "bin"),
                os.fsencode(self.installation / "lib"),
            ],
        )
        self.assertFalse(self.calls.exists())

    def test_managed_parameter_environment_overrides_are_rejected_before_mutation(self):
        cases = {
            "CUBRID_CUBRID_PORT_ID": "15555",
            "CUBRID_STORED_PROCEDURE_UDS": "no",
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                self.environment[name] = value
                before = self.snapshot()
                result = self.run_runtime("init", "--preset", "debug", "--json")
                self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(
                    report["diagnostic"]["code"], "effective_configuration_uncertain"
                )
                self.assertEqual(report["diagnostic"]["expected_value"], "unset")
                self.assertEqual(report["diagnostic"]["observed_value"], "<redacted>")
                self.assertEqual(self.snapshot(), before)
                del self.environment[name]
        self.assertFalse(self.calls.exists())

    def test_alternate_configuration_files_are_selected_and_revalidated(self):
        default_engine = self.installation / "conf" / "cubrid.conf"
        default_broker = self.installation / "conf" / "cubrid_broker.conf"
        alternate_engine = self.installation / "conf" / "runtime.conf"
        alternate_broker = self.installation / "conf" / "runtime-broker.conf"
        alternate_engine.write_text(default_engine.read_text())
        alternate_broker.write_text(default_broker.read_text())
        self.environment["CUBRID_CONF_FILE"] = str(alternate_engine)
        self.environment["CUBRID_BROKER_CONF_FILE"] = str(alternate_broker)

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        self.assertEqual(
            manifest["configurations"]["engine"]["path"], str(alternate_engine)
        )
        self.assertEqual(
            manifest["configurations"]["broker"]["path"], str(alternate_broker)
        )
        self.assertIn("cubrid_port_id=15000", alternate_engine.read_text())
        self.assertIn("cubrid_port_id=1523", default_engine.read_text())
        self.assertIn("BROKER_PORT=20000", alternate_broker.read_text())
        self.assertIn("BROKER_PORT=30000", default_broker.read_text())
        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)

        self.environment["CUBRID_CONF_FILE"] = str(default_engine)
        before = self.snapshot()
        rejected = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(rejected.returncode, 4, rejected.stderr + rejected.stdout)
        diagnostic = json.loads(rejected.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_selection_drift")
        self.assertEqual(diagnostic["source"], "CUBRID_CONF_FILE")
        self.assertEqual(diagnostic["expected_value"], str(alternate_engine))
        self.assertEqual(diagnostic["observed_value"], str(default_engine))
        self.assertEqual(self.snapshot(), before)

    def test_validate_reports_effective_managed_setting_drift_without_repair(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        engine_path = self.installation / "conf" / "cubrid.conf"
        engine_path.write_text(
            engine_path.read_text().replace("cubrid_port_id=15000", "cubrid_port_id=15555")
        )
        before = self.snapshot()

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_drift")
        self.assertEqual(diagnostic["affected_object"]["value"], "cubrid_port_id")
        self.assertEqual(diagnostic["normalized_value"], "15555")
        self.assertEqual(diagnostic["source"], "cubrid.conf [common] cubrid_port_id")
        self.assertEqual(diagnostic["expected_value"], "15000")
        self.assertEqual(diagnostic["observed_value"], "15555")
        self.assertIn("idle", diagnostic["next_action"])
        self.assertEqual(self.snapshot(), before)

    def test_validate_detects_reinstall_that_restores_stock_configuration(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        engine_path = self.installation / "conf" / "cubrid.conf"
        engine_path.write_text(
            "[service]\nservice=server,broker,manager\n"
            "[common]\ncubrid_port_id=1523\nstored_procedure_uds=no\n"
        )
        before = self.snapshot()

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertIn(
            diagnostic["code"], {"component_unsupported", "configuration_drift"}
        )
        self.assertIn("idle", diagnostic["next_action"])
        self.assertEqual(self.snapshot(), before)

    def test_validate_applies_environment_override_precedence(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        self.environment["CUBRID_CUBRID_PORT_ID"] = "15000"
        matching = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(matching.returncode, 0, matching.stderr + matching.stdout)

        self.environment["CUBRID_CUBRID_PORT_ID"] = "15555"
        before = self.snapshot()
        conflicting = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(conflicting.returncode, 4, conflicting.stderr + conflicting.stdout)
        diagnostic = json.loads(conflicting.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_drift")
        self.assertEqual(diagnostic["source"], "CUBRID_CUBRID_PORT_ID")
        self.assertEqual(diagnostic["expected_value"], "15000")
        self.assertEqual(diagnostic["observed_value"], "15555")
        self.assertEqual(self.snapshot(), before)

    def test_validate_rejects_contradictory_pl_aliases(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        engine_path = self.installation / "conf" / "cubrid.conf"
        engine_path.write_text(
            engine_path.read_text() + "java_stored_procedure_uds=no\n"
        )
        before = self.snapshot()

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_contradictory")
        self.assertEqual(diagnostic["affected_object"]["value"], "stored_procedure_uds")
        self.assertEqual(self.snapshot(), before)

    def test_validate_rechecks_supported_service_and_pl_contract(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        engine_path = self.installation / "conf" / "cubrid.conf"
        managed = engine_path.read_text()
        cases = {
            "manager": (
                managed.replace("service=server,broker", "service=server,broker,manager"),
                "service",
            ),
            "ha": (managed + "ha_mode=yes\n", "ha_mode"),
            "pl_tcp": (managed + "stored_procedure_port=15555\n", "stored_procedure_port"),
            "pl_debug": (managed + "stored_procedure_debug=5005\n", "stored_procedure_debug"),
        }
        for component, (content, setting) in cases.items():
            with self.subTest(component=component):
                engine_path.write_text(content)
                before = self.snapshot()
                validated = self.run_runtime("validate", "--preset", "debug", "--json")
                self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
                diagnostic = json.loads(validated.stdout)["diagnostic"]
                self.assertEqual(diagnostic["code"], "component_unsupported")
                self.assertEqual(diagnostic["affected_object"]["value"], setting)
                self.assertEqual(self.snapshot(), before)
                engine_path.write_text(managed)

    def test_validate_applies_ha_environment_precedence(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        self.environment["CUBRID_HA_MODE"] = "yes"
        before = self.snapshot()

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "component_unsupported")
        self.assertEqual(diagnostic["affected_object"]["value"], "ha_mode")
        self.assertEqual(diagnostic["source"], "CUBRID_HA_MODE")
        self.assertEqual(diagnostic["expected_value"], "off")
        self.assertEqual(diagnostic["observed_value"], "yes")
        self.assertEqual(self.snapshot(), before)

    def test_validate_rejects_newly_enabled_gateway_and_shard_components(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        managed_broker = broker_path.read_text()

        broker_path.write_text(managed_broker + "SHARD=ON\n")
        before_shard = self.snapshot()
        shard = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(shard.returncode, 4, shard.stderr + shard.stdout)
        shard_diagnostic = json.loads(shard.stdout)["diagnostic"]
        self.assertEqual(shard_diagnostic["code"], "component_unsupported")
        self.assertEqual(shard_diagnostic["affected_object"]["value"], "SHARD")
        self.assertEqual(shard_diagnostic["expected_value"], "OFF")
        self.assertEqual(shard_diagnostic["observed_value"], "ON")
        self.assertEqual(self.snapshot(), before_shard)

        broker_path.write_text(managed_broker)
        gateway_path = self.installation / "conf" / "cubrid_gateway.conf"
        gateway_path.write_text("[%gateway]\nSERVICE=ON\n")
        before_gateway = self.snapshot()
        gateway = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(gateway.returncode, 4, gateway.stderr + gateway.stdout)
        gateway_diagnostic = json.loads(gateway.stdout)["diagnostic"]
        self.assertEqual(gateway_diagnostic["code"], "component_unsupported")
        self.assertEqual(gateway_diagnostic["affected_object"]["value"], "%gateway")
        self.assertEqual(self.snapshot(), before_gateway)

    def test_validate_rechecks_every_enabled_broker_value(self):
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(
            broker_path.read_text()
            + "\n[%reporting]\nSERVICE=ON\nBROKER_PORT=31000\n"
            + "MAX_NUM_APPL_SERVER=1\nAPPL_SERVER_SHM_ID=31000\n"
        )
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        broker_path.write_text(
            broker_path.read_text().replace("BROKER_PORT=20001", "BROKER_PORT=29999")
        )
        before = self.snapshot()

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_drift")
        self.assertEqual(diagnostic["affected_object"]["value"], "BROKER_PORT")
        self.assertEqual(diagnostic["source"], "cubrid_broker.conf [%reporting] BROKER_PORT")
        self.assertEqual(diagnostic["expected_value"], "20001")
        self.assertEqual(diagnostic["observed_value"], "29999")
        self.assertEqual(self.snapshot(), before)

    def test_broker_spawn_environment_is_hashed_and_revalidated_without_secrets(self):
        source_environment = self.configure_broker_spawn_environment(
            "UNRELATED_SECRET do-not-publish\n"
        )

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        dependencies = manifest["configurations"]["broker"]["spawn_environments"]
        self.assertEqual(dependencies[0]["path"], str(source_environment))
        self.assertNotIn("do-not-publish", json.dumps(manifest))
        source_environment.write_text("UNRELATED_SECRET changed-but-still-private\n")
        before = self.snapshot()
        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_drift")
        self.assertEqual(diagnostic["affected_object"]["kind"], "broker spawn environment")
        self.assertNotIn("changed-but-still-private", validated.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_broker_spawn_environment_hash_is_stable_across_crlf_reads(self):
        self.configure_broker_spawn_environment(
            b"UNRELATED_SETTING value\r\nSECOND value\r\n"
        )

        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        self.assertFalse(self.calls.exists())

    def test_broker_spawn_environment_cannot_override_managed_identity(self):
        self.configure_broker_spawn_environment("CUBRID /another/install\n")
        before = self.snapshot()

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        diagnostic = json.loads(initialized.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_contradictory")
        self.assertEqual(diagnostic["affected_object"]["value"], "CUBRID")
        self.assertNotIn("another", diagnostic["message"])
        self.assertEqual(self.snapshot(), before)

    def test_broker_spawn_environment_parses_first_two_columns_like_cubrid(self):
        self.configure_broker_spawn_environment(
            "CUBRID /another/install trailing-column\n"
        )
        before = self.snapshot()

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        diagnostic = json.loads(initialized.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "configuration_contradictory")
        self.assertEqual(diagnostic["affected_object"]["value"], "CUBRID")
        self.assertNotIn("another", initialized.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_validate_rejects_selected_build_directory_drift(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        self.environment["CUBRID_BUILD_DIR"] = str(
            self.worktree / "build_preset_release_gcc"
        )
        before = self.snapshot()

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "active_preset_inconsistent")
        self.assertEqual(diagnostic["source"], "CUBRID_BUILD_DIR")
        self.assertEqual(self.snapshot(), before)

    def test_validate_rejects_a_different_active_preset(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        before = self.snapshot()

        validated = self.run_runtime("validate", "--preset", "release_gcc", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "manifest_inconsistent")
        self.assertEqual(diagnostic["affected_object"]["kind"], "active preset")
        self.assertEqual(diagnostic["expected_value"], "debug")
        self.assertEqual(diagnostic["observed_value"], "release_gcc")
        self.assertEqual(self.snapshot(), before)

    def test_human_configuration_drift_matches_structured_diagnostic(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        engine_path = self.installation / "conf" / "cubrid.conf"
        engine_path.write_text(
            engine_path.read_text().replace("cubrid_port_id=15000", "cubrid_port_id=15555")
        )
        before = self.snapshot()

        human = self.run_runtime("validate", "--preset", "debug")
        structured = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(human.returncode, 4, human.stderr + human.stdout)
        self.assertIn("Affected configuration setting: cubrid_port_id", human.stdout)
        self.assertIn("Normalized value: 15555", human.stdout)
        self.assertIn("Source: cubrid.conf [common] cubrid_port_id", human.stdout)
        self.assertIn("Expected value: 15000", human.stdout)
        self.assertIn("Observed value: 15555", human.stdout)
        self.assertIn("Evidence quality: definitive", human.stdout)
        diagnostic = json.loads(structured.stdout)["diagnostic"]
        self.assertEqual(diagnostic["normalized_value"], "15555")
        self.assertEqual(diagnostic["expected_value"], "15000")
        self.assertEqual(diagnostic["observed_value"], "15555")
        self.assertEqual(self.snapshot(), before)

    def test_database_specific_engine_settings_are_managed_effectively(self):
        engine_path = self.installation / "conf" / "cubrid.conf"
        engine_path.write_text(
            engine_path.read_text()
            + "\n[@Chosen_DB1]\n"
            + "cubrid_port_id=17777\n"
            + "stored_procedure_uds=no\n"
            + "db_specific_setting=preserved\n"
        )

        initialized = self.run_runtime(
            "init", "--preset", "debug", "--db-name", "Chosen_DB1", "--json"
        )

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        selected_section = engine_path.read_text().split("[@Chosen_DB1]", 1)[1]
        self.assertIn("cubrid_port_id=15000", selected_section)
        self.assertIn("stored_procedure_uds=yes", selected_section)
        self.assertIn("db_specific_setting=preserved", selected_section)
        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        self.assertFalse(self.calls.exists())

    def test_database_section_names_remain_case_sensitive_like_cubrid(self):
        engine_path = self.installation / "conf" / "cubrid.conf"
        engine_path.write_text(
            engine_path.read_text()
            + "\n[@chosen_db1]\n"
            + "cubrid_port_id=17777\n"
            + "stored_procedure_uds=no\n"
        )

        initialized = self.run_runtime(
            "init", "--preset", "debug", "--db-name", "Chosen_DB1", "--json"
        )

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        selected_section = engine_path.read_text().split("[@chosen_db1]", 1)[1]
        self.assertIn("cubrid_port_id=17777", selected_section)
        self.assertIn("stored_procedure_uds=no", selected_section)
        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        self.assertFalse(self.calls.exists())

    def assert_unsupported_pl_alias_is_rejected(self, setting):
        engine_path = self.installation / "conf" / "cubrid.conf"
        engine_path.write_text(engine_path.read_text() + setting + "\n")
        before = self.snapshot()
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        self.assertEqual(
            json.loads(initialized.stdout)["diagnostic"]["code"],
            "component_unsupported",
        )
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_legacy_pl_tcp_alias_is_rejected(self):
        self.assert_unsupported_pl_alias_is_rejected("java_stored_procedure_port=15555")

    def test_legacy_pl_debug_alias_is_rejected(self):
        self.assert_unsupported_pl_alias_is_rejected("java_stored_procedure_debug=5005")

    def test_legacy_pl_uds_alias_cannot_disable_uds(self):
        self.assert_unsupported_pl_alias_is_rejected("java_stored_procedure_uds=no")

    def test_enabled_shard_setting_is_rejected_before_mutation(self):
        broker_path = self.installation / "conf" / "cubrid_broker.conf"
        broker_path.write_text(broker_path.read_text() + "SHARD=ON\n")
        before = self.snapshot()

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        report = json.loads(initialized.stdout)
        self.assertEqual(report["diagnostic"]["code"], "component_unsupported")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_enabled_gateway_configuration_is_rejected_before_mutation(self):
        gateway_path = self.installation / "conf" / "cubrid_gateway.conf"
        gateway_path.write_text("[%custom]\nSERVICE=ON\n")
        before = self.snapshot()

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        report = json.loads(initialized.stdout)
        self.assertEqual(report["diagnostic"]["code"], "component_unsupported")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_registry_lock_alias_is_rejected_without_mutating_its_target(self):
        guard_root = self.state_home / "cubrid-worktree-guard"
        guard_root.mkdir(parents=True, mode=0o700)
        target = self.root / "foreign-lock-target"
        target.write_text("do not change\n")
        target.chmod(0o644)
        (guard_root / "registry.lock").symlink_to(target)
        before = self.snapshot()

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 4, initialized.stderr + initialized.stdout)
        report = json.loads(initialized.stdout)
        self.assertEqual(report["diagnostic"]["code"], "path_unsafe")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.assertFalse(self.calls.exists())

    def test_validate_rejects_a_managed_path_with_a_symlinked_ancestor(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        runtime_parent = Path(manifest["resource_bundle"]["cubrid_tmp"]).parent
        moved_parent = runtime_parent.with_name(runtime_parent.name + "-moved")
        runtime_parent.rename(moved_parent)
        runtime_parent.symlink_to(moved_parent, target_is_directory=True)

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(report["diagnostic"]["code"], "managed_path_unsafe")
        self.assertFalse(self.calls.exists())

    def test_validate_rejects_non_private_guard_state_directory(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest_directory = Path(json.loads(initialized.stdout)["manifest_path"]).parent
        manifest_directory.chmod(0o755)

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(
            report["diagnostic"]["code"], "guard_state_directory_unsafe"
        )
        self.assertFalse(self.calls.exists())

    def test_validate_rejects_unsafe_state_root_ancestor(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        self.state_home.chmod(0o777)

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(
            report["diagnostic"]["code"], "guard_state_directory_unsafe"
        )
        self.assertEqual(report["diagnostic"]["affected_object"]["value"], str(self.state_home))
        self.assertFalse(self.calls.exists())

    def test_init_rejects_unsafe_retained_bundle_before_mutation(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest_path = Path(json.loads(initialized.stdout)["manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        manifest["resource_bundle"]["data_root"] = "relative-data"
        manifest_path.write_text(json.dumps(manifest))
        manifest_path.chmod(0o600)
        before = self.snapshot()

        repeated = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(repeated.returncode, 4, repeated.stderr + repeated.stdout)
        report = json.loads(repeated.stdout)
        self.assertEqual(report["diagnostic"]["code"], "resource_bundle_invalid")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.worktree / "relative-data").exists())
        self.assertFalse(self.calls.exists())

    def test_init_rejects_cross_role_collisions_in_retained_bundle(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest_path = Path(json.loads(initialized.stdout)["manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        bundle = manifest["resource_bundle"]
        bundle["brokers"][0]["port"] = bundle["master_port"]
        bundle["brokers"][0]["appl_server_shm_key"] = bundle["master_shm_key"]
        bundle["brokers"][0]["query_replacement_shm_key"] = (
            bundle["master_shm_key"] & 0x00FFFFFF
        ) | 0x51000000
        manifest_path.write_text(json.dumps(manifest))
        before = self.snapshot()

        repeated = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(repeated.returncode, 4, repeated.stderr + repeated.stdout)
        report = json.loads(repeated.stdout)
        self.assertEqual(report["diagnostic"]["code"], "resource_bundle_invalid")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls.exists())

    def test_validate_rejects_self_consistent_unsafe_socket_bundle(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest_path = Path(json.loads(initialized.stdout)["manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        original = manifest["resource_bundle"]["socket_paths"][0]
        manifest["resource_bundle"]["socket_paths"][0] = "relative.sock"
        manifest["normalized_claims"]["paths"] = [
            "relative.sock" if path == original else path
            for path in manifest["normalized_claims"]["paths"]
        ]
        manifest_path.write_text(json.dumps(manifest))
        registry_path = self.state_home / "cubrid-worktree-guard" / "allocations.json"
        registry = json.loads(registry_path.read_text())
        runtime_id = manifest["worktree_id"]
        registry["allocations"][runtime_id]["claims"] = manifest["normalized_claims"]
        registry_path.write_text(json.dumps(registry))

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(report["diagnostic"]["code"], "resource_bundle_invalid")
        self.assertFalse(self.calls.exists())

    def test_validate_requires_a_canonical_selected_installation(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)

        del self.environment["CUBRID"]
        missing = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(missing.returncode, 4, missing.stderr + missing.stdout)
        self.assertEqual(
            json.loads(missing.stdout)["diagnostic"]["code"],
            "installation_inconsistent",
        )

        alias = self.root / "install-alias"
        alias.symlink_to(self.installation, target_is_directory=True)
        self.environment["CUBRID"] = str(alias)
        aliased = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(aliased.returncode, 4, aliased.stderr + aliased.stdout)
        self.assertEqual(
            json.loads(aliased.stdout)["diagnostic"]["code"],
            "installation_inconsistent",
        )
        self.assertFalse(self.calls.exists())

    def test_validate_detects_selected_executable_identity_drift(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        (self.installation / "bin" / "cub_master").write_text("replaced executable\n")

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(report["diagnostic"]["code"], "installation_identity_invalid")
        self.assertIn("cub_master", report["diagnostic"]["affected_object"]["value"])
        self.assertFalse(self.calls.exists())

    def test_library_soname_symlink_is_supported_and_target_drift_is_rejected(self):
        library_link = self.installation / "lib" / "libcubrid.so"
        library_link.unlink()
        cci_library = self.installation / "cci" / "lib"
        cci_library.mkdir(parents=True)
        library_target = cci_library / "libcubrid.so.11"
        library_target.write_text("synthetic versioned library\n")
        library_link.symlink_to(Path("..") / "cci" / "lib" / library_target.name)

        initialized = self.run_runtime("init", "--preset", "debug", "--json")

        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest = self.manifest_for(initialized)
        identities = manifest["installation"]["libraries"]
        link_identity = next(
            item for item in identities if item["path"] == str(library_link)
        )
        self.assertEqual(link_identity["resolved_path"], str(library_target))
        library_target.write_text("reinstalled versioned library\n")
        before = self.snapshot()
        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        diagnostic = json.loads(validated.stdout)["diagnostic"]
        self.assertEqual(diagnostic["code"], "installation_identity_invalid")
        self.assertEqual(diagnostic["affected_object"]["value"], str(library_link))
        self.assertEqual(self.snapshot(), before)

    def test_validate_rejects_incomplete_installation_identity_lists(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        manifest_path = Path(json.loads(initialized.stdout)["manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        unrelated = manifest["installation"]["libraries"][0]
        manifest["installation"]["executables"] = [unrelated]
        manifest["installation"]["libraries"] = [unrelated]
        manifest_path.write_text(json.dumps(manifest))

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(
            report["diagnostic"]["code"], "installation_identity_invalid"
        )
        self.assertFalse(self.calls.exists())

    def test_validate_rejects_invalid_registry_generation(self):
        initialized = self.run_runtime("init", "--preset", "debug", "--json")
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        registry_path = self.state_home / "cubrid-worktree-guard" / "allocations.json"
        registry = json.loads(registry_path.read_text())
        registry["generation"] = "bogus"
        registry_path.write_text(json.dumps(registry))

        validated = self.run_runtime("validate", "--preset", "debug", "--json")

        self.assertEqual(validated.returncode, 4, validated.stderr + validated.stdout)
        report = json.loads(validated.stdout)
        self.assertEqual(
            report["diagnostic"]["code"], "allocation_registry_inconsistent"
        )
        self.assertFalse(self.calls.exists())

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
