#!/usr/bin/env python3
"""A daemon spawned by a runtime command must not retain the coordinator lock."""
import hashlib
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


COORDINATOR = Path(__file__).resolve().parents[1] / 'bin/cubrid-build-coordinator.sh'


class RuntimeLockTest(unittest.TestCase):
    def coordinator_environment(
        self,
        root: Path,
        guard_status: int = 0,
        guard_report: str = '{"outcome":"ready"}',
    ) -> dict[str, str]:
        helper_bin = root / 'helpers' / 'bin'
        helper_bin.mkdir(parents=True)
        guard = helper_bin / 'my-cubrid-runtime'
        guard.write_text(
            '#!/usr/bin/env bash\n'
            f"printf '%s\\n' '{guard_report}'\n"
            f'exit {guard_status}\n'
        )
        guard.chmod(0o755)
        environment = dict(
            os.environ,
            XDG_RUNTIME_DIR=str(root),
            MY_CUBRID=str(root / 'helpers'),
            CUBRID=str(root / 'install'),
            CUBRID_BUILD_DIR=str(root / 'build'),
            PRESET_MODE='debug',
        )
        environment.pop('CUBRID_RUNTIME_LOCK_HELD', None)
        return environment

    def test_runtime_action_revalidates_before_running_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'command-ran'
            env = self.coordinator_environment(
                root,
                guard_status=4,
                guard_report='{"outcome":"invalid","diagnostic":{"code":"runtime_invalid"}}',
            )

            for lock_already_held in (False, True):
                with self.subTest(lock_already_held=lock_already_held):
                    if lock_already_held:
                        env['CUBRID_RUNTIME_LOCK_HELD'] = '1'
                    else:
                        env.pop('CUBRID_RUNTIME_LOCK_HELD', None)
                    result = subprocess.run(
                        [
                            str(COORDINATOR), 'runtime', '0', '--', 'python3', '-c',
                            f'import pathlib; pathlib.Path({str(marker)!r}).touch()',
                        ],
                        cwd=root,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )

                    self.assertEqual(result.returncode, 4)
                    self.assertFalse(marker.exists())
                    self.assertIn('runtime_invalid', result.stderr)

    def test_stop_and_build_revalidates_before_stopping_or_installing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command_log = root / 'commands.log'
            command_bin = root / 'commands'
            command_bin.mkdir()
            cmake = command_bin / 'cmake'
            cmake.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'cmake %s\\n\' "$*" >> {str(command_log)!r}\n'
            )
            cmake.chmod(0o755)
            cubrid = root / 'install' / 'bin' / 'cubrid'
            cubrid.parent.mkdir(parents=True)
            cubrid.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'cubrid %s\\n\' "$*" >> {str(command_log)!r}\n'
            )
            cubrid.chmod(0o755)
            env = self.coordinator_environment(
                root,
                guard_status=4,
                guard_report='{"outcome":"invalid","diagnostic":{"code":"runtime_invalid"}}',
            )
            env['PATH'] = f'{command_bin}:{env["PATH"]}'

            result = subprocess.run(
                [str(COORDINATOR), 'stop-and-build'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertEqual(command_log.read_text().splitlines(), ['cmake --build --preset debug'])
            self.assertIn('runtime_invalid', result.stderr)

    def test_installation_delete_requires_guard_proven_idle_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = root / 'install'
            install.mkdir()
            retained = install / 'retained'
            retained.touch()
            env = self.coordinator_environment(root)
            guard_log = root / 'guard.log'
            guard = root / 'helpers' / 'bin' / 'my-cubrid-runtime'
            guard.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'%s\\n\' "$*" > {str(guard_log)!r}\n'
                'printf \'%s\\n\' \'{"outcome":"invalid","diagnostic":{"code":"live_ownership_unknown"}}\'\n'
                'exit 4\n'
            )

            result = subprocess.run(
                [str(COORDINATOR), 'installation-delete', '0'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertTrue(retained.exists())
            self.assertIn('validate', guard_log.read_text())
            self.assertIn('--require-idle', guard_log.read_text())

            guard.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'%s\\n\' "$*" > {str(guard_log)!r}\n'
                'printf \'%s\\n\' \'{"outcome":"ready"}\'\n'
            )
            deleted = subprocess.run(
                [str(COORDINATOR), 'installation-delete', '0'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(deleted.returncode, 0, deleted.stderr)
            self.assertFalse(install.exists())

    def test_runtime_action_checks_selected_database_while_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'command-ran'
            env = self.coordinator_environment(root)
            runtime_lock_id = hashlib.sha256(str(root / 'install').encode()).hexdigest()
            runtime_lock = (
                root / f'cubrid-dev-locks-{os.getuid()}' / f'runtime-{runtime_lock_id}.lock'
            )
            selector = root / 'helpers' / 'bin' / 'my-cubrid-pwddb-getname'

            def select(database: str) -> None:
                selector.write_text(
                    '#!/usr/bin/env bash\n'
                    f'if flock -n {str(runtime_lock)!r} -c true; then exit 88; fi\n'
                    f"printf '%s\\n' {database!r}\n"
                )
                selector.chmod(0o755)

            command = [
                str(COORDINATOR), 'runtime', '0', '--database', 'testdb', '--',
                'python3', '-c',
                f'import pathlib; pathlib.Path({str(marker)!r}).touch()',
            ]
            select('develop')

            refused = subprocess.run(
                command, cwd=root, env=env, capture_output=True, text=True, timeout=5
            )

            self.assertEqual(refused.returncode, 1, refused.stderr)
            self.assertFalse(marker.exists())
            self.assertIn(
                'manifest-selected database is develop', refused.stderr
            )

            select('testdb')
            accepted = subprocess.run(
                command, cwd=root, env=env, capture_output=True, text=True, timeout=5
            )

            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertTrue(marker.exists())

    def test_runtime_lock_environment_marker_cannot_bypass_real_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'command-ran'
            env = self.coordinator_environment(root)
            env['CUBRID_RUNTIME_LOCK_HELD'] = '1'
            runtime_lock_id = hashlib.sha256(str(root / 'install').encode()).hexdigest()
            runtime_lock = (
                root / f'cubrid-dev-locks-{os.getuid()}' / f'runtime-{runtime_lock_id}.lock'
            )
            runtime_lock.parent.mkdir(mode=0o700)

            with runtime_lock.open('w') as lock_stream:
                fcntl.flock(lock_stream, fcntl.LOCK_EX)
                result = subprocess.run(
                    [
                        str(COORDINATOR), 'runtime', '0', '--', 'python3', '-c',
                        f'import pathlib; pathlib.Path({str(marker)!r}).touch()',
                    ],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertFalse(marker.exists())
            self.assertIn('could not acquire the lock', result.stderr)

    def test_database_delete_runs_known_helper_while_runtime_lock_is_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = self.coordinator_environment(root)
            runtime_lock_id = hashlib.sha256(str(root / 'install').encode()).hexdigest()
            runtime_lock = (
                root / f'cubrid-dev-locks-{os.getuid()}' / f'runtime-{runtime_lock_id}.lock'
            )
            command_log = root / 'database-delete.log'
            helper = root / 'helpers' / 'bin' / 'my-cubrid-pwddb'
            helper.write_text(
                '#!/usr/bin/env bash\n'
                f'if flock -n {str(runtime_lock)!r} -c true; then exit 88; fi\n'
                f'printf \'%s\\n\' "$*" > {str(command_log)!r}\n'
            )
            helper.chmod(0o755)

            result = subprocess.run(
                [
                    str(COORDINATOR), 'database-delete', '0',
                    '--database', 'testdb',
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                command_log.read_text().strip(),
                'delete --expected-name testdb',
            )

            command_log.unlink()
            default_timeout = subprocess.run(
                [str(COORDINATOR), 'database-delete', '--database', 'testdb'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(default_timeout.returncode, 0, default_timeout.stderr)
            self.assertEqual(
                command_log.read_text().strip(),
                'delete --expected-name testdb',
            )

    def test_full_install_initializes_guarded_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command_log = root / 'commands.log'
            command_bin = root / 'commands'
            command_bin.mkdir()
            cmake = command_bin / 'cmake'
            cmake.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'cmake %s\\n\' "$*" >> {str(command_log)!r}\n'
            )
            cmake.chmod(0o755)
            env = self.coordinator_environment(root)
            env['PATH'] = f'{command_bin}:{env["PATH"]}'
            runtime_lock_id = hashlib.sha256(str(root / 'install').encode()).hexdigest()
            runtime_lock = (
                root / f'cubrid-dev-locks-{os.getuid()}' / f'runtime-{runtime_lock_id}.lock'
            )
            guard = root / 'helpers' / 'bin' / 'my-cubrid-runtime'
            guard.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'guard %s\\n\' "$*" >> {str(command_log)!r}\n'
                f'if flock -n {str(runtime_lock)!r} -c true; then exit 88; fi\n'
                'printf \'%s\\n\' \'{"outcome":"ready"}\'\n'
            )

            result = subprocess.run(
                [str(COORDINATOR), 'install', '0'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            commands = command_log.read_text().splitlines()
            self.assertEqual(commands[0], f'cmake --install {root / "build"} --prefix {root / "install"}')
            self.assertEqual(
                commands[1],
                f'guard init --worktree {root} --preset debug',
            )

    def test_partial_install_does_not_initialize_guarded_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command_log = root / 'commands.log'
            command_bin = root / 'commands'
            command_bin.mkdir()
            cmake = command_bin / 'cmake'
            cmake.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'cmake %s\\n\' "$*" >> {str(command_log)!r}\n'
            )
            cmake.chmod(0o755)
            env = self.coordinator_environment(root)
            env['PATH'] = f'{command_bin}:{env["PATH"]}'
            guard = root / 'helpers' / 'bin' / 'my-cubrid-runtime'
            guard.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'guard %s\\n\' "$*" >> {str(command_log)!r}\n'
            )

            result = subprocess.run(
                [str(COORDINATOR), 'install-target', 'util/install', '0'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                command_log.read_text().splitlines(),
                ['cmake --build --preset debug --target util/install'],
            )

    def test_initialization_failure_fails_after_completed_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command_log = root / 'commands.log'
            installed = root / 'installed'
            command_bin = root / 'commands'
            command_bin.mkdir()
            cmake = command_bin / 'cmake'
            cmake.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'cmake %s\\n\' "$*" >> {str(command_log)!r}\n'
                f'touch {str(installed)!r}\n'
            )
            cmake.chmod(0o755)
            env = self.coordinator_environment(root)
            env['PATH'] = f'{command_bin}:{env["PATH"]}'
            guard = root / 'helpers' / 'bin' / 'my-cubrid-runtime'
            guard.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'guard %s\\n\' "$*" >> {str(command_log)!r}\n'
                'exit 4\n'
            )

            result = subprocess.run(
                [str(COORDINATOR), 'install', '0'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 4)
            self.assertTrue(installed.exists())
            self.assertEqual(
                command_log.read_text().splitlines(),
                [
                    f'cmake --install {root / "build"} --prefix {root / "install"}',
                    f'guard init --worktree {root} --preset debug',
                ],
            )

    def test_build_failure_prevents_runtime_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command_log = root / 'commands.log'
            command_bin = root / 'commands'
            command_bin.mkdir()
            cmake = command_bin / 'cmake'
            cmake.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'cmake %s\\n\' "$*" >> {str(command_log)!r}\n'
                'exit 9\n'
            )
            cmake.chmod(0o755)
            env = self.coordinator_environment(root)
            env['PATH'] = f'{command_bin}:{env["PATH"]}'
            guard = root / 'helpers' / 'bin' / 'my-cubrid-runtime'
            guard.write_text(
                '#!/usr/bin/env bash\n'
                f'printf \'guard %s\\n\' "$*" >> {str(command_log)!r}\n'
            )

            result = subprocess.run(
                [str(COORDINATOR), 'build', '0'],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 9)
            self.assertEqual(
                command_log.read_text().splitlines(),
                ['cmake --build --preset debug'],
            )

    def test_foreground_command_keeps_lock_and_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = self.coordinator_environment(root)
            ready = root / 'ready'
            release = root / 'release'
            code = ('import pathlib,time,sys; '
                    f'pathlib.Path({str(ready)!r}).touch(); '
                    f'release=pathlib.Path({str(release)!r})\n'
                    'while not release.exists(): time.sleep(0.01)\n'
                    'sys.exit(23)')
            running = subprocess.Popen([str(COORDINATOR), 'runtime', '0', '--', 'python3', '-c', code], env=env)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists(), 'Foreground command did not start')
                probe = subprocess.run([str(COORDINATOR), 'runtime', '0', '--', 'true'],
                                       env=env, capture_output=True, timeout=5)
                self.assertEqual(probe.returncode, 75, 'Lock released before foreground command finished')
            finally:
                release.touch()
                running.wait(timeout=5)
            self.assertEqual(running.returncode, 23)

    def test_daemon_does_not_retain_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = self.coordinator_environment(root)
            pidfile = root / 'daemon.pid'
            spawn = (
                'import pathlib, subprocess; '
                'p = subprocess.Popen(["sleep", "30"], close_fds=False, start_new_session=True, '
                'stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); '
                f'pathlib.Path({str(pidfile)!r}).write_text(str(p.pid))'
            )
            try:
                subprocess.run([str(COORDINATOR), 'runtime', '0', '--', 'python3', '-c', spawn],
                               env=env, check=True, capture_output=True, timeout=5)
                probe = subprocess.run([str(COORDINATOR), 'runtime', '0', '--', 'true'],
                                       env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(probe.returncode, 0,
                                 'A background child retained the runtime lock: ' + probe.stderr)
            finally:
                if pidfile.exists():
                    os.kill(int(pidfile.read_text()), signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
