#!/usr/bin/env python3
"""A daemon spawned by a runtime command must not retain the coordinator lock."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


COORDINATOR = Path(__file__).resolve().parents[1] / 'bin/cubrid-build-coordinator.sh'


class RuntimeLockTest(unittest.TestCase):
    def test_foreground_command_keeps_lock_and_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = dict(os.environ, XDG_RUNTIME_DIR=tmp, CUBRID=str(root / 'install'),
                       CUBRID_BUILD_DIR=str(root / 'build'), PRESET_MODE='debug')
            env.pop('CUBRID_RUNTIME_LOCK_HELD', None)
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
            env = dict(os.environ, XDG_RUNTIME_DIR=tmp, CUBRID=str(root / 'install'),
                       CUBRID_BUILD_DIR=str(root / 'build'), PRESET_MODE='debug')
            env.pop('CUBRID_RUNTIME_LOCK_HELD', None)
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
