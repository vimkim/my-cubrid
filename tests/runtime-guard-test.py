#!/usr/bin/env python3
"""Exercise the worktree runtime guard through its public CLI."""

import json
import os
from pathlib import Path
import shutil
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
        for command in ("cubrid", "cub_master", "cub_server", "broker", "cub_pl"):
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
        return subprocess.run(
            [str(CLI), command, *arguments],
            cwd=self.worktree,
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def run_cli(self, *arguments):
        return self.run_runtime("validate", *arguments)

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

    def test_init_creates_one_complete_runtime_and_validate_reports_ready(self):
        (self.worktree / ".env").write_text(
            "# human setting\nPRESET_MODE=debug\n\nOTHER=value\n"
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
        manifest = json.loads(manifest_path.read_text())
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

        validated = self.run_runtime("validate", "--preset", "debug", "--json")
        self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
        validation_report = json.loads(validated.stdout)
        self.assertEqual(validation_report["outcome"], "ready")
        self.assertTrue(validation_report["ready"])
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
        manifest = json.loads(Path(json.loads(result.stdout)["manifest_path"]).read_text())
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
        manifest = json.loads(Path(json.loads(result.stdout)["manifest_path"]).read_text())
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
            "effective_configuration_uncertain",
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

    def test_effective_configuration_overrides_are_rejected_before_mutation(self):
        cases = {
            "CUBRID_CONF_FILE": str(self.root / "alternate.conf"),
            "CUBRID_BROKER_CONF_FILE": str(self.root / "alternate-broker.conf"),
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
                self.assertEqual(self.snapshot(), before)
                del self.environment[name]
        self.assertFalse(self.calls.exists())

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
        manifest = json.loads(Path(json.loads(initialized.stdout)["manifest_path"]).read_text())
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
