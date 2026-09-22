#!/usr/bin/env python3
"""Behavior tests for the shared managed-workflow environment loader."""

import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
ENVIRONMENT_LOADER = REPOSITORY / "stow" / "cubrid" / ".envrc"
SHARED_JUSTFILE = REPOSITORY / "stow" / "cubrid" / "justfile"
SHARED_JUST_MODULES = REPOSITORY / "stow" / "cubrid" / ".just"
BUILD_COORDINATOR = REPOSITORY / "bin" / "cubrid-build-coordinator.sh"
PODMAN_TEST_RUNNER = REPOSITORY / "bin" / "cubrid-podman-test.sh"
PROCESS_SELECTOR = REPOSITORY / "bin" / "my-cubrid-process-select"


class RuntimeEnvironmentTest(unittest.TestCase):
    def run_loader(
        self,
        guard_exit_status: int,
        preset: str | None = "debug_gcc",
        ready: bool = False,
        environment_mode: int = 0o600,
        loads: int = 1,
        guard_report: dict[str, object] | None = None,
        worktree_id: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[bytes], dict[str, str]]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        home = root / "home"
        worktree = root / "develop"
        helper_bin = root / "helpers" / "bin"
        home.mkdir()
        worktree.mkdir()
        helper_bin.mkdir(parents=True)

        if guard_report is not None:
            report = guard_report
        elif ready:
            state = root / "state" / "worktree-runtime"
            state.mkdir(parents=True)
            manifest = state / "manifest.json"
            manifest.write_text("{}\n")
            runtime_installation = root / "private-install"
            runtime_database = root / "private-databases"
            runtime_tmp = root / "private-tmp"
            runtime_environment = state / "env.sh"
            runtime_environment.write_text(
                "export PRESET_MODE=debug_gcc\n"
                "export CUBRID_WORKTREE_ID=runtime01\n"
                f"export CUBRID={shlex.quote(str(runtime_installation))}\n"
                f"export CUBRID_DATABASES={shlex.quote(str(runtime_database))}\n"
                f"export CUBRID_TMP={shlex.quote(str(runtime_tmp))}\n"
                "export CUBRID_RUNTIME_READY=1\n"
                f"export PATH={shlex.quote(str(runtime_installation / 'bin'))}${{PATH:+:$PATH}}\n"
                f"export LD_LIBRARY_PATH={shlex.quote(str(runtime_installation / 'lib'))}${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}\n"
            )
            runtime_environment.chmod(environment_mode)
            report = {
                "outcome": "ready",
                "manifest_path": str(manifest),
                "environment_path": str(runtime_environment),
            }
        else:
            report = {"outcome": "uninitialized"}

        guard = helper_bin / "my-cubrid-runtime"
        guard.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' {shlex.quote(json.dumps(report))}\n"
            f"exit {guard_exit_status}\n"
        )
        guard.chmod(0o755)

        inherited_installation = root / "legacy-install"
        environment = dict(
            os.environ,
            HOME=str(home),
            MY_CUBRID=str(root / "helpers"),
            PRESET_MODE="debug_gcc",
            CUBRID=str(inherited_installation),
            CUBRID_DATABASES=str(root / "legacy-databases"),
            CUBRID_TMP=str(root / "legacy-tmp"),
            CUBRID_CONF_FILE=str(root / "legacy-cubrid.conf"),
            CUBRID_BROKER_CONF_FILE=str(root / "legacy-broker.conf"),
            CUBRID_RUNTIME_READY="1",
            PATH=f"{inherited_installation}/bin:/usr/bin:/bin",
            LD_LIBRARY_PATH=(
                f"{inherited_installation}/cci/lib:{inherited_installation}/lib:/safe/lib"
            ),
        )
        if preset is None:
            environment.pop("PRESET_MODE")
        else:
            environment["PRESET_MODE"] = preset
        if worktree_id is not None:
            environment["CUBRID_WORKTREE_ID"] = worktree_id
        load_commands = "\n".join(
            f"source {shlex.quote(str(ENVIRONMENT_LOADER))} || status=$?"
            for _ in range(loads)
        )
        command = f"""
PATH_add() {{ export PATH="$1${{PATH:+:$PATH}}"; }}
has() {{ command -v "$1" >/dev/null 2>&1; }}
log_status() {{ :; }}
cd {shlex.quote(str(worktree))}
status=0
{load_commands}
env -0
exit "$status"
"""
        result = subprocess.run(
            ["bash", "-c", command],
            env=environment,
            capture_output=True,
            timeout=10,
        )
        loaded = {}
        for assignment in result.stdout.split(b"\0"):
            if not assignment or b"=" not in assignment:
                continue
            name, value = assignment.split(b"=", 1)
            loaded[name.decode()] = value.decode()
        return result, loaded

    def test_uninitialized_worktree_loads_build_only_environment(self):
        result, loaded = self.run_loader(3)

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(loaded["CUBRID_RUNTIME_READY"], "0")
        self.assertEqual(loaded["PRESET_MODE"], "debug_gcc")
        self.assertEqual(
            loaded["CUBRID"],
            str(Path(loaded["HOME"]) / ".cub" / "install" / "develop" / "debug_gcc"),
        )
        self.assertEqual(
            loaded["CUBRID_BUILD_DIR"],
            str(Path(loaded["PWD"]) / "build_preset_debug_gcc"),
        )
        self.assertNotIn("CUBRID_DATABASES", loaded)
        self.assertNotIn("CUBRID_TMP", loaded)
        self.assertNotIn("CUBRID_CONF_FILE", loaded)
        self.assertNotIn("CUBRID_BROKER_CONF_FILE", loaded)
        self.assertNotIn("legacy-install/bin", loaded["PATH"])
        self.assertNotIn("legacy-install/cci/lib", loaded.get("LD_LIBRARY_PATH", ""))
        self.assertNotIn("legacy-install/lib", loaded.get("LD_LIBRARY_PATH", ""))

    def test_missing_preset_fails_closed_and_clears_inherited_runtime(self):
        result, loaded = self.run_loader(3, preset=None)

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("CUBRID_DATABASES", loaded)
        self.assertNotIn("CUBRID_TMP", loaded)
        self.assertNotIn("CUBRID_CONF_FILE", loaded)
        self.assertNotIn("CUBRID_BROKER_CONF_FILE", loaded)
        self.assertNotIn("legacy-install/bin", loaded["PATH"])
        self.assertNotIn("legacy-install/cci/lib", loaded.get("LD_LIBRARY_PATH", ""))
        self.assertNotIn("legacy-install/lib", loaded.get("LD_LIBRARY_PATH", ""))

    def test_ready_worktree_loads_validated_generated_environment(self):
        result, loaded = self.run_loader(0, ready=True)

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(loaded["CUBRID_RUNTIME_READY"], "1")
        self.assertEqual(loaded["CUBRID_WORKTREE_ID"], "runtime01")
        self.assertTrue(loaded["CUBRID"].endswith("/private-install"))
        self.assertTrue(loaded["CUBRID_DATABASES"].endswith("/private-databases"))
        self.assertTrue(loaded["CUBRID_TMP"].endswith("/private-tmp"))
        self.assertIn(str(Path(loaded["CUBRID"]) / "bin"), loaded["PATH"].split(":"))
        self.assertIn(str(Path(loaded["CUBRID"]) / "lib"), loaded["LD_LIBRARY_PATH"].split(":"))
        self.assertNotIn("legacy-install/bin", loaded["PATH"])
        self.assertNotIn("legacy-install/lib", loaded["LD_LIBRARY_PATH"])

    def test_invalid_guard_state_fails_closed(self):
        result, loaded = self.run_loader(4)

        self.assertEqual(result.returncode, 4)
        self.assertEqual(loaded["CUBRID_RUNTIME_READY"], "0")
        self.assertNotIn("CUBRID_DATABASES", loaded)
        self.assertNotIn("legacy-install/bin", loaded["PATH"])

    def test_preset_mismatch_loads_build_only_environment(self):
        result, loaded = self.run_loader(
            4,
            preset="release_gcc",
            guard_report={
                "outcome": "invalid",
                "diagnostic": {
                    "code": "manifest_inconsistent",
                    "affected_object": {"kind": "active preset"},
                },
            },
            worktree_id="runtime01",
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(loaded["CUBRID_RUNTIME_READY"], "0")
        self.assertEqual(loaded["CUBRID_WORKTREE_ID"], "runtime01")
        self.assertEqual(loaded["PRESET_MODE"], "release_gcc")
        self.assertEqual(
            loaded["CUBRID"],
            str(Path(loaded["HOME"]) / ".cub" / "install" / "develop" / "release_gcc"),
        )
        self.assertEqual(
            loaded["CUBRID_BUILD_DIR"],
            str(Path(loaded["PWD"]) / "build_preset_release_gcc"),
        )
        self.assertNotIn("CUBRID_DATABASES", loaded)
        self.assertNotIn("CUBRID_TMP", loaded)
        self.assertNotIn("legacy-install/bin", loaded["PATH"])
        self.assertIn("build-only", result.stderr.decode())

        unrelated, _ = self.run_loader(
            4,
            preset="release_gcc",
            guard_report={
                "outcome": "invalid",
                "diagnostic": {
                    "code": "manifest_inconsistent",
                    "affected_object": {"kind": "worktree path"},
                },
            },
            worktree_id="runtime01",
        )
        self.assertEqual(unrelated.returncode, 4)

    def test_ready_environment_requires_owner_only_mode(self):
        result, loaded = self.run_loader(0, ready=True, environment_mode=0o644)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(loaded["CUBRID_RUNTIME_READY"], "0")
        self.assertNotIn("CUBRID_DATABASES", loaded)
        self.assertIn("not a trusted owner-only regular file", result.stderr.decode())

    def test_reloading_ready_environment_does_not_duplicate_runtime_paths(self):
        result, loaded = self.run_loader(0, ready=True, loads=2)

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        runtime_bin = str(Path(loaded["CUBRID"]) / "bin")
        runtime_lib = str(Path(loaded["CUBRID"]) / "lib")
        self.assertEqual(loaded["PATH"].split(":").count(runtime_bin), 1)
        self.assertEqual(loaded["LD_LIBRARY_PATH"].split(":").count(runtime_lib), 1)

    def test_preset_recipe_preserves_runtime_identity_and_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "justfile").symlink_to(SHARED_JUSTFILE)
            (root / ".just").symlink_to(SHARED_JUST_MODULES, target_is_directory=True)
            environment_file = root / ".env"
            environment_file.write_text(
                "# local settings\n"
                "PRESET_MODE=debug_gcc\n"
                "\n"
                "CUBRID_WORKTREE_ID=runtime01\n"
                "EXTRA_SETTING=keep-me\n"
            )
            environment_file.chmod(0o640)
            command_bin = root / "commands"
            command_bin.mkdir()
            cmake = command_bin / "cmake"
            cmake.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' 'Available configure presets:' '  \"debug_gcc\"' '  \"release_gcc\"'\n"
            )
            cmake.chmod(0o755)
            environment = dict(os.environ, PATH=f"{command_bin}:{os.environ['PATH']}")

            result = subprocess.run(
                ["just", "--justfile", str(root / "justfile"), "core::preset-set", "release_gcc"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                environment_file.read_text(),
                "# local settings\n"
                "PRESET_MODE=release_gcc\n"
                "\n"
                "CUBRID_WORKTREE_ID=runtime01\n"
                "EXTRA_SETTING=keep-me\n",
            )
            self.assertEqual(environment_file.stat().st_mode & 0o777, 0o640)

    def test_fixed_database_recipes_refuse_non_selected_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            helper_bin = home / "my-cubrid" / "bin"
            command_bin = root / "commands"
            helper_bin.mkdir(parents=True)
            command_bin.mkdir()
            (root / "justfile").symlink_to(SHARED_JUSTFILE)
            (root / ".just").symlink_to(SHARED_JUST_MODULES, target_is_directory=True)
            selected_database = helper_bin / "my-cubrid-pwddb-getname"
            selected_database.write_text("#!/usr/bin/env bash\nprintf '%s\\n' develop\n")
            selected_database.chmod(0o755)
            command_marker = root / "runtime-command-ran"
            coordinator = helper_bin / "cubrid-build-coordinator.sh"
            coordinator.symlink_to(BUILD_COORDINATOR)
            guard = helper_bin / "my-cubrid-runtime"
            guard.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' '{\"outcome\":\"ready\"}'\n"
            )
            guard.chmod(0o755)
            for name in ("cubrid", "cgdb"):
                command = command_bin / name
                command.write_text(
                    "#!/usr/bin/env bash\n"
                    f"touch {shlex.quote(str(command_marker))}\n"
                )
                command.chmod(0o755)
            environment = dict(
                os.environ,
                HOME=str(home),
                MY_CUBRID=str(home / "my-cubrid"),
                XDG_RUNTIME_DIR=str(root),
                CUBRID=str(root / "install"),
                CUBRID_BUILD_DIR=str(root / "build"),
                CUBRID_DATABASES=str(root / "databases"),
                PRESET_MODE="debug",
                PATH=f"{command_bin}:{os.environ['PATH']}",
            )
            environment.pop("CUBRID_RUNTIME_LOCK_HELD", None)

            for recipe in ("start-testdb", "start-demodb"):
                with self.subTest(recipe=recipe):
                    result = subprocess.run(
                        ["just", "--justfile", str(root / "justfile"), f"db::{recipe}"],
                        cwd=root,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(command_marker.exists())
                    self.assertIn("develop", result.stderr)

            for database in ("testdb", "demodb"):
                with self.subTest(recipe=f"create-{database}"):
                    database_directory = root / "databases" / database
                    result = subprocess.run(
                        [
                            "just",
                            "--justfile",
                            str(root / "justfile"),
                            f"db::create-{database}",
                        ],
                        cwd=root,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(database_directory.exists())
                    self.assertIn("develop", result.stderr)

            debug_result = subprocess.run(
                ["just", "--justfile", str(root / "justfile"), "debug::csql-cs"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(debug_result.returncode, 0)
            self.assertIn("develop", debug_result.stderr)

            for database in ("testdb", "demodb"):
                with self.subTest(selected_database=database):
                    selected_database.write_text(
                        f"#!/usr/bin/env bash\nprintf '%s\\n' {shlex.quote(database)}\n"
                    )
                    command_marker.unlink(missing_ok=True)
                    result = subprocess.run(
                        [
                            "just",
                            "--justfile",
                            str(root / "justfile"),
                            f"db::start-{database}",
                        ],
                        cwd=root,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(command_marker.exists())

    def test_database_sql_and_debug_recipes_use_coordinator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            helper_bin = home / "my-cubrid" / "bin"
            command_bin = root / "commands"
            helper_bin.mkdir(parents=True)
            command_bin.mkdir()
            (root / "justfile").symlink_to(SHARED_JUSTFILE)
            (root / ".just").symlink_to(SHARED_JUST_MODULES, target_is_directory=True)
            coordinator_log = root / "coordinator.log"
            direct_log = root / "direct.log"
            selected_database = helper_bin / "my-cubrid-pwddb-getname"
            selected_database.write_text("#!/usr/bin/env bash\nprintf '%s\\n' testdb\n")
            selected_database.chmod(0o755)
            coordinator = helper_bin / "cubrid-build-coordinator.sh"
            coordinator.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(coordinator_log))}\n"
                "case \" $* \" in *' cub-auto '*) printf '%s\\n' buffer ;; esac\n"
            )
            coordinator.chmod(0o755)
            for name in ("cub-auto", "csql.sh", "cubrid", "cgdb"):
                command = command_bin / name
                command.write_text(
                    "#!/usr/bin/env bash\n"
                    f"printf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(direct_log))}\n"
                    + ("printf '%s\\n' buffer\n" if name == "cub-auto" else "")
                )
                command.chmod(0o755)
            environment = dict(
                os.environ,
                HOME=str(home),
                PATH=f"{command_bin}:{os.environ['PATH']}",
            )
            cases = (
                (
                    "db::pwddb-delete",
                    "database-delete 300",
                ),
                (
                    "db::delete-testdb",
                    "database-delete 300 --database testdb",
                ),
                (
                    "db::delete-demodb",
                    "database-delete 300 --database demodb",
                ),
                (
                    "db::create-testdb",
                    f"runtime 300 --database testdb -- {helper_bin / 'my-cubrid-pwddb'} create",
                ),
                (
                    "db::create-demodb",
                    f"runtime 300 --database demodb -- {helper_bin / 'my-cubrid-pwddb'} create --load demodb",
                ),
                (
                    "db::recreate-demodb",
                    f"runtime 300 --database demodb -- {helper_bin / 'my-cubrid-pwddb'} recreate --load demodb",
                ),
                (
                    "db::paramdump-testdb",
                    "runtime 300 --database testdb -- cub-auto paramdump testdb",
                ),
                (
                    "db::csql-sa",
                    "runtime 300 --database testdb -- csql.sh",
                ),
                (
                    "db::unloaddb-sa",
                    "runtime 300 --database testdb -- cubrid unloaddb testdb -S -t 0 -v",
                ),
                (
                    "debug::csql-cs",
                    "runtime 300 --database testdb -- cgdb --args csql -udba testdb",
                ),
            )

            for recipe, expected in cases:
                with self.subTest(recipe=recipe):
                    coordinator_log.unlink(missing_ok=True)
                    direct_log.unlink(missing_ok=True)

                    result = subprocess.run(
                        ["just", "--justfile", str(root / "justfile"), recipe],
                        cwd=root,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(coordinator_log.read_text().strip(), expected)
                    self.assertFalse(direct_log.exists())

    def test_unsafe_database_and_local_bridge_recipes_are_removed(self):
        removed = (
            "db::delete-all",
            "db::remove-databases",
            "db::edit-databases",
            "edit-databases-txt",
            "cubrid-deletedb-all",
            "database-remove",
            "update-cubrid-conf",
            "build-update",
            "update-restart-testdb",
        )

        for recipe in removed:
            with self.subTest(recipe=recipe):
                result = subprocess.run(
                    ["just", "--justfile", str(SHARED_JUSTFILE), "--show", recipe],
                    cwd=REPOSITORY,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("justfile does not contain recipe", result.stderr.lower())

    def test_all_managed_runtime_recipe_classes_use_coordinator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            helper_bin = home / "my-cubrid" / "bin"
            command_bin = root / "commands"
            ctp_bin = home / "CTP" / "bin"
            helper_bin.mkdir(parents=True)
            command_bin.mkdir()
            ctp_bin.mkdir(parents=True)
            (root / "justfile").symlink_to(SHARED_JUSTFILE)
            (root / ".just").symlink_to(SHARED_JUST_MODULES, target_is_directory=True)
            coordinator_log = root / "coordinator.log"
            direct_log = root / "direct.log"
            coordinator = helper_bin / "cubrid-build-coordinator.sh"
            coordinator.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(coordinator_log))}\n"
                "if [[ \"$*\" == *\"my-cubrid-pwddb list\"* ]]; then\n"
                "  printf '%s\\n' testdb\n"
                "fi\n"
            )
            coordinator.chmod(0o755)

            def direct_command(path: Path, name: str, body: str = "") -> None:
                path.write_text(
                    "#!/usr/bin/env bash\n"
                    f"printf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(direct_log))}\n"
                    + body
                )
                path.chmod(0o755)

            for name in ("ini.sh", "crudini", "nvim", "cubrid-shell-debug.sh",
                         "cubrid-oos-isolation-test.sh", "sudo", "objdump"):
                direct_command(command_bin / name, name)
            gum = command_bin / "gum"
            gum.write_text("#!/usr/bin/env bash\nexit 0\n")
            gum.chmod(0o755)
            direct_command(helper_bin / "cubrid-podman-test.sh", "cubrid-podman-test.sh")
            direct_command(ctp_bin / "ctp.sh", "ctp.sh")
            direct_command(
                command_bin / "ps",
                "ps",
                "printf '%s\\n' 'vimkim 123 cub_server'\n",
            )
            for name, body in (("rg", "cat\n"), ("fzf", "head -n 1\n")):
                command = command_bin / name
                command.write_text("#!/usr/bin/env bash\n" + body)
                command.chmod(0o755)

            database_root = root / "databases"
            database_root.mkdir()
            (database_root / "databases.txt").write_text(
                f"testdb {database_root / 'data'} localhost {database_root / 'log'} "
                f"file:{database_root / 'lob'}\n"
            )
            environment = dict(
                os.environ,
                HOME=str(home),
                MY_CUBRID=str(home / "my-cubrid"),
                CUBRID=str(root / "install"),
                CUBRID_DATABASES=str(database_root),
                PATH=f"{command_bin}:{os.environ['PATH']}",
            )
            cases = (
                ("dwb-off", ()),
                ("dwb-get", ()),
                ("db::list-all", ()),
                ("db::get-string-compression", ()),
                ("db::enable-string-compression", ()),
                ("db::disable-string-compression", ()),
                ("db::get-pgbuf-inspector", ()),
                ("db::enable-pgbuf-inspector", ()),
                ("db::disable-pgbuf-inspector", ()),
                ("db::get-use-system-malloc", ()),
                ("db::enable-use-system-malloc", ()),
                ("db::disable-use-system-malloc", ()),
                ("db::get-unfill-factor", ()),
                ("db::set-unfill-factor", ()),
                ("db::get-port", ()),
                ("db::set-port", ()),
                ("db::get-data-buffer-size", ()),
                ("db::set-data-buffer-20g", ()),
                ("db::set-data-buffer-50g", ()),
                ("db::set-data-buffer-512m", ()),
                ("db::edit-config", ()),
                ("ctp::shell-debug", ("case",)),
                ("ctp::shell-debug-many", ("subtree",)),
                ("ctp::shell-debug-interactive", ()),
                ("ctp::podman-test-new", ("container", "db", "/tmp/test.sh")),
                ("oos::test-isolation", ()),
                ("debug::server-interactive", ()),
                ("debug::server", ()),
                ("debug::attach-unloaddb", ()),
                ("profile::perf-record-server", ()),
                ("profile::check-simd-native", ()),
                ("core::delete-install", ()),
            )

            for recipe, arguments in cases:
                with self.subTest(recipe=recipe):
                    coordinator_log.unlink(missing_ok=True)
                    direct_log.unlink(missing_ok=True)
                    result = subprocess.run(
                        ["just", "--justfile", str(root / "justfile"), recipe, *arguments],
                        cwd=root,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(coordinator_log.exists(), recipe)
                    self.assertFalse(direct_log.exists(), recipe)

            coordinator_log.unlink(missing_ok=True)
            result = subprocess.run(
                ["just", "--justfile", str(root / "justfile"), "db::start-interactive"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = coordinator_log.read_text().splitlines()
            self.assertIn("my-cubrid-pwddb list", calls[0])
            self.assertIn("--database testdb", calls[-1])

    def test_live_pid_recipes_filter_for_the_selected_runtime(self):
        expectations = {
            "debug::server-interactive": "my-cubrid-process-select server --interactive",
            "debug::server": "my-cubrid-process-select server",
            "debug::attach-unloaddb": "my-cubrid-process-select unloaddb --interactive",
            "profile::perf-record-server": "my-cubrid-process-select server --interactive",
        }

        for recipe, required in expectations.items():
            with self.subTest(recipe=recipe):
                result = subprocess.run(
                    ["just", "--justfile", str(SHARED_JUSTFILE), "--show", recipe],
                    cwd=REPOSITORY,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                self.assertNotIn("ps aux", result.stdout)
                self.assertNotIn('/proc/[0-9]*', result.stdout)
                self.assertIn(required, result.stdout)

        selector = PROCESS_SELECTOR.read_text()
        self.assertIn('Path("/proc")', selector)
        self.assertIn('process / "exe"', selector)
        self.assertIn('process / "cwd"', selector)
        self.assertIn('process / "cmdline"', selector)
        self.assertIn('process / "stat"', selector)

        role_matches = runpy.run_path(str(PROCESS_SELECTOR))["role_matches"]
        self.assertTrue(role_matches("server", ("cub_server", "testdb")))
        self.assertFalse(role_matches("server", ("cub_server", "--database", "testdb")))
        self.assertTrue(
            role_matches("unloaddb", ("cubrid", "unloaddb", "-S", "testdb"))
        )
        self.assertFalse(
            role_matches("unloaddb", ("cubrid", "spacedb", "unloaddb", "testdb"))
        )
        self.assertFalse(
            role_matches("unloaddb", ("cubrid", "testdb", "unloaddb"))
        )

    def test_managed_podman_recipe_holds_the_runtime_lock_until_stop(self):
        result = subprocess.run(
            ["just", "--justfile", str(SHARED_JUSTFILE), "--show", "ctp::podman-test-new"],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )

        self.assertIn("--wait-for-stop", result.stdout)
        source = PODMAN_TEST_RUNNER.read_text()
        self.assertLess(
            source.index(
                'arm_managed_container_cleanup "${container_name}" "${container_token}"'
            ),
            source.index('podman run --detach'),
        )

    def test_podman_wait_retries_until_container_absence_is_proven(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command_bin = root / "commands"
            command_bin.mkdir()
            counter = root / "presence-count"
            podman = command_bin / "podman"
            podman.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1 $2\" == 'container exists' ]]; then\n"
                "  count=0; [[ ! -f \"$COUNTER\" ]] || count=$(cat \"$COUNTER\")\n"
                "  count=$((count + 1)); printf '%s\\n' \"$count\" >\"$COUNTER\"\n"
                "  case \"$count\" in 1) exit 125 ;; 2) exit 0 ;; *) exit 1 ;; esac\n"
                "fi\n"
                "if [[ \"$1\" == inspect ]]; then echo 'container-id token'; exit 0; fi\n"
                "exit 64\n"
            )
            podman.chmod(0o755)
            environment = dict(
                os.environ,
                PATH=f"{command_bin}:{os.environ['PATH']}",
                COUNTER=str(counter),
            )

            result = subprocess.run(
                [
                    "bash", "-c",
                    'source "$1"; sleep() { :; }; '
                    'arm_managed_container_cleanup demo token; '
                    'wait_for_container_stop demo 0',
                    "bash", str(PODMAN_TEST_RUNNER),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(counter.read_text().strip(), "3")
            self.assertIn("ownership is unknown", result.stderr)

    def test_podman_signal_cleanup_retries_until_absence_is_proven(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command_bin = root / "commands"
            command_bin.mkdir()
            removed = root / "removed"
            attempts = root / "remove-attempts"
            podman = command_bin / "podman"
            podman.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1 $2\" == 'container exists' ]]; then\n"
                "  [[ -f \"$REMOVED\" ]] && exit 1\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == inspect ]]; then echo \"container-id $TOKEN\"; exit 0; fi\n"
                "if [[ \"$1\" == rm ]]; then\n"
                "  count=0; [[ ! -f \"$ATTEMPTS\" ]] || count=$(cat \"$ATTEMPTS\")\n"
                "  count=$((count + 1)); printf '%s\\n' \"$count\" >\"$ATTEMPTS\"\n"
                "  [[ \"$count\" -ge 2 ]] || exit 125\n"
                "  touch \"$REMOVED\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 64\n"
            )
            podman.chmod(0o755)
            environment = dict(
                os.environ,
                PATH=f"{command_bin}:{os.environ['PATH']}",
                REMOVED=str(removed),
                ATTEMPTS=str(attempts),
                TOKEN="owned-token",
            )

            result = subprocess.run(
                [
                    "bash", "-c",
                    'source "$1"; sleep() { :; }; '
                    'arm_managed_container_cleanup demo owned-token; '
                    'kill -TERM $$; exit 99',
                    "bash", str(PODMAN_TEST_RUNNER),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 130, result.stderr)
            self.assertEqual(attempts.read_text().strip(), "2")
            self.assertTrue(removed.exists())
            self.assertIn("Cleanup failed", result.stderr)

    def test_podman_signal_during_container_creation_cleans_before_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command_bin = root / "commands"
            cubrid = root / "cubrid"
            command_bin.mkdir()
            (cubrid / "bin").mkdir(parents=True)
            for name in ("cubrid", "csql"):
                executable = cubrid / "bin" / name
                executable.write_text("#!/usr/bin/env bash\nexit 0\n")
                executable.chmod(0o755)
            test_script = root / "test.sh"
            test_script.write_text("#!/usr/bin/env bash\nexit 0\n")
            created = root / "created"
            removed = root / "removed"
            podman = command_bin / "podman"
            podman.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1 $2\" == 'container exists' ]]; then\n"
                "  [[ -f \"$CREATED\" ]] && exit 0\n"
                "  exit 1\n"
                "fi\n"
                "if [[ \"$1 $2\" == 'image exists' ]]; then exit 0; fi\n"
                "if [[ \"$1\" == run ]]; then\n"
                "  for argument in \"$@\"; do\n"
                "    case \"$argument\" in io.cubrid.podman-test.token=*)\n"
                "      printf '%s\\n' \"${argument#*=}\" >\"$TOKEN_FILE\" ;;\n"
                "    esac\n"
                "  done\n"
                "  touch \"$CREATED\"\n"
                "  kill -TERM \"$PPID\"\n"
                "  sleep 0.1\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == inspect ]]; then printf 'container-id '; cat \"$TOKEN_FILE\"; exit 0; fi\n"
                "if [[ \"$1\" == rm ]]; then\n"
                "  unlink \"$CREATED\"\n"
                "  touch \"$REMOVED\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 64\n"
            )
            podman.chmod(0o755)
            environment = dict(
                os.environ,
                PATH=f"{command_bin}:{os.environ['PATH']}",
                CREATED=str(created),
                REMOVED=str(removed),
                TOKEN_FILE=str(root / "token"),
            )

            result = subprocess.run(
                [
                    str(PODMAN_TEST_RUNNER), "run",
                    "--name", "creation-race",
                    "--cubrid-root", str(cubrid),
                    "--wait-for-stop",
                    str(test_script),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 130, result.stderr)
            self.assertTrue(removed.exists())
            self.assertFalse(created.exists())

    def test_podman_cleanup_uses_owned_id_not_replacement_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command_bin = root / "commands"
            command_bin.mkdir()
            owned_removed = root / "owned-removed"
            replacement = root / "replacement"
            foreign_removed = root / "foreign-removed"
            podman = command_bin / "podman"
            podman.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1 $2\" == 'container exists' ]]; then exit 0; fi\n"
                "if [[ \"$1\" == inspect ]]; then\n"
                "  if [[ -f \"$OWNED_REMOVED\" ]]; then echo 'foreign-id foreign-token'; exit 0; fi\n"
                "  touch \"$REPLACEMENT\"\n"
                "  echo 'owned-id owned-token'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == rm ]]; then\n"
                "  target=\"${!#}\"\n"
                "  if [[ \"$target\" == owned-id ]]; then touch \"$OWNED_REMOVED\"; exit 0; fi\n"
                "  touch \"$FOREIGN_REMOVED\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 64\n"
            )
            podman.chmod(0o755)
            environment = dict(
                os.environ,
                PATH=f"{command_bin}:{os.environ['PATH']}",
                OWNED_REMOVED=str(owned_removed),
                REPLACEMENT=str(replacement),
                FOREIGN_REMOVED=str(foreign_removed),
            )

            result = subprocess.run(
                [
                    "bash", "-c",
                    'source "$1"; sleep() { :; }; '
                    'arm_managed_container_cleanup demo owned-token; '
                    'kill -TERM $$; exit 99',
                    "bash", str(PODMAN_TEST_RUNNER),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 130, result.stderr)
            self.assertTrue(owned_removed.exists())
            self.assertTrue(replacement.exists())
            self.assertFalse(foreign_removed.exists())
            self.assertIn("Refusing to remove", result.stderr)

    def test_podman_name_collision_never_removes_foreign_container(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command_bin = root / "commands"
            cubrid = root / "cubrid"
            command_bin.mkdir()
            (cubrid / "bin").mkdir(parents=True)
            for name in ("cubrid", "csql"):
                executable = cubrid / "bin" / name
                executable.write_text("#!/usr/bin/env bash\nexit 0\n")
                executable.chmod(0o755)
            test_script = root / "test.sh"
            test_script.write_text("#!/usr/bin/env bash\nexit 0\n")
            foreign = root / "foreign"
            removed = root / "removed"
            podman = command_bin / "podman"
            podman.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1 $2\" == 'container exists' ]]; then\n"
                "  [[ -f \"$FOREIGN\" ]] && exit 0\n"
                "  exit 1\n"
                "fi\n"
                "if [[ \"$1 $2\" == 'image exists' ]]; then exit 0; fi\n"
                "if [[ \"$1\" == run ]]; then touch \"$FOREIGN\"; exit 125; fi\n"
                "if [[ \"$1\" == inspect ]]; then echo 'foreign-id foreign-token'; exit 0; fi\n"
                "if [[ \"$1\" == rm ]]; then touch \"$REMOVED\"; exit 0; fi\n"
                "exit 64\n"
            )
            podman.chmod(0o755)
            environment = dict(
                os.environ,
                PATH=f"{command_bin}:{os.environ['PATH']}",
                FOREIGN=str(foreign),
                REMOVED=str(removed),
            )

            result = subprocess.run(
                [
                    str(PODMAN_TEST_RUNNER), "run",
                    "--name", "collision",
                    "--cubrid-root", str(cubrid),
                    "--wait-for-stop",
                    str(test_script),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertTrue(foreign.exists())
            self.assertFalse(removed.exists())
            self.assertIn("Refusing to remove", result.stderr)

            foreign.unlink()
            started = root / "started"
            podman.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1 $2\" == 'container exists' ]]; then exit 125; fi\n"
                "if [[ \"$1\" == run ]]; then touch \"$STARTED\"; exit 0; fi\n"
                "if [[ \"$1\" == rm ]]; then touch \"$REMOVED\"; exit 0; fi\n"
                "exit 64\n"
            )
            environment["STARTED"] = str(started)
            unknown = subprocess.run(
                [
                    str(PODMAN_TEST_RUNNER), "run",
                    "--name", "unknown",
                    "--cubrid-root", str(cubrid),
                    "--wait-for-stop",
                    str(test_script),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertNotEqual(unknown.returncode, 0)
            self.assertFalse(started.exists())
            self.assertFalse(removed.exists())
            self.assertIn("presence cannot be determined safely", unknown.stderr)


if __name__ == "__main__":
    unittest.main()
