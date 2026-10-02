#!/usr/bin/env python3
"""Cross-repository contract; set CUB_WORKENV_CLI to the reviewed CLI."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CLI = os.environ.get('CUB_WORKENV_CLI')

@unittest.skipUnless(CLI, 'set CUB_WORKENV_CLI for cross-repository integration')
class WorkenvIntegration(unittest.TestCase):
    def test_new_environment_supports_coordinator_runtime_without_legacy_manifest(self):
        with tempfile.TemporaryDirectory(prefix='cwe-tooling-') as tmp:
            root = Path(tmp)
            install = root / 'install'
            (install / 'bin').mkdir(parents=True)
            for name in ('cubrid', 'csql'):
                command = install / 'bin' / name
                command.write_text('#!/bin/sh\nexit 0\n')
                command.chmod(0o755)
            env = dict(os.environ, CUB_WORKENV_CLI=CLI, CUBRID=str(install),
                       CUBRID_BUILD_DIR=str(root / 'build'), PRESET_MODE='debug',
                       XDG_RUNTIME_DIR=str(root), MY_CUBRID=str(REPO))
            result = subprocess.run([CLI, 'init', '--worktree', str(root), '--install', str(install),
                '--preset', 'debug', '--state-home', str(root / 'host'),
                '--port-start', '46000', '--port-end', '46999'], text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads((root / '.cub-workenv/state.json').read_text())
            try:
                result = subprocess.run([str(REPO / 'bin/cubrid-build-coordinator.sh'), 'runtime', '0', '--',
                    'bash', '-c', 'printf "%s" "$CUBRID_TMP"'], cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, state['allocation']['tmp'])
                registry = root / '.cub-workenv/databases/databases.txt'
                registry.write_text('testdb /data localhost /log\nextra /other localhost /other-log\n')
                env['CUBRID_DATABASES'] = str(registry.parent)
                listed = subprocess.run([str(REPO / 'bin/my-cubrid-pwddb'), 'list'],
                                        cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(listed.returncode, 0, listed.stderr)
                self.assertEqual(listed.stdout, 'testdb\nextra\n')
                named = subprocess.run([str(REPO / 'bin/my-cubrid-pwddb-getname')],
                                       cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(named.returncode, 0, named.stderr)
                self.assertEqual(named.stdout, 'testdb\n')
                commands = root / 'commands'
                commands.mkdir()
                log = root / 'build-stop.log'
                for command, target in (('cmake', commands / 'cmake'), ('cubrid', install / 'bin/cubrid')):
                    target.write_text('#!/bin/sh\n' + f'printf "%s\\n" "{command} $*" >> {shlex.quote(str(log))}\n')
                    target.chmod(0o755)
                before = (root / '.cub-workenv/state.json').read_bytes()
                rebuilt = subprocess.run([str(REPO / 'bin/cubrid-build-coordinator.sh'), 'stop-and-build'],
                    cwd=root, env=dict(env, PATH=str(commands) + ':' + env['PATH']), capture_output=True, text=True)
                self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
                self.assertEqual((root / '.cub-workenv/state.json').read_bytes(), before)
                self.assertEqual(log.read_text().splitlines(), ['cmake --build --preset debug',
                    'cubrid service stop', 'cubrid broker stop', f'cmake --install {root / "build"} --prefix {install}'])

                refused = subprocess.run([str(REPO / 'bin/my-cubrid-pwddb'), 'delete'],
                                         cwd=root, env=env, capture_output=True, text=True)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn('Existing files are preserved', refused.stderr)
                self.assertTrue(registry.exists())
                for selected_preset, selected_install, expected in (
                        ('debug', install, 0), ('release', install, 1),
                        ('debug', root / 'wrong-install', 1)):
                    loaded = subprocess.run(['bash', '-c',
                        'PATH_add() { export PATH="$1:$PATH"; }; has() { command -v "$1" >/dev/null 2>&1; }; log_status() { :; }; '
                        'source "$1" >/dev/null; status=$?; printf "%s|%s" "$CUBRID_RUNTIME_READY" "${CUBRID_TMP:-}"; exit "$status"',
                        'bash', str(REPO / 'stow/cubrid/.envrc')], cwd=root,
                        env=dict(env, PRESET_MODE=selected_preset, CUB_WORKENV_INSTALL=str(selected_install),
                                 CUBRID_TMP='/inherited/tmp'), capture_output=True, text=True)
                    self.assertEqual(loaded.returncode, expected, loaded.stderr)
                    self.assertEqual(loaded.stdout, '0|' if expected else '1|' + state['allocation']['tmp'])


            finally:
                shutil.rmtree(state['allocation']['tmp'])

if __name__ == '__main__':
    unittest.main()
