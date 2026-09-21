#!/usr/bin/env python3
"""Behavior tests for the shared managed-workflow environment loader."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
ENVIRONMENT_LOADER = REPOSITORY / "stow" / "cubrid" / ".envrc"
SHARED_JUSTFILE = REPOSITORY / "stow" / "cubrid" / "justfile"
SHARED_JUST_MODULES = REPOSITORY / "stow" / "cubrid" / ".just"


class RuntimeEnvironmentTest(unittest.TestCase):
    def run_loader(
        self,
        guard_exit_status: int,
        preset: str | None = "debug_gcc",
        ready: bool = False,
        environment_mode: int = 0o600,
        loads: int = 1,
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

        if ready:
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


if __name__ == "__main__":
    unittest.main()
