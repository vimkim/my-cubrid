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
            result = subprocess.run([CLI, 'init', '--no-db', '--worktree', str(root), '--install', str(install),
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
                switched = subprocess.run(['bash', '-c',
                    'source "$1" -w "$2" -p debug && printf "%s|%s" "$PRESET_MODE" "$CUBRID_DATABASES"',
                    'bash', str(REPO / 'bin/cub-env.sh'), str(root)], cwd=root,
                    env=dict(env, PRESET_MODE='previous-preset'), capture_output=True, text=True)
                self.assertEqual(switched.returncode, 0, switched.stderr)
                self.assertEqual(switched.stdout, 'debug|' + str(registry.parent))
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
                    'cubrid server status', 'cubrid service stop', 'cubrid broker stop', f'cmake --install {root / "build"} --prefix {install}'])

                refused = subprocess.run([str(REPO / 'bin/my-cubrid-pwddb'), 'delete'],
                                         cwd=root, env=env, capture_output=True, text=True)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn('No creation receipt', refused.stderr)
                self.assertTrue(registry.exists())
                # Public just recipes must edit/read the selected configuration,
                # leaving the installation's default configuration untouched.
                (root / 'justfile').symlink_to(REPO / 'stow/cubrid/justfile')
                (root / '.just').symlink_to(REPO / 'stow/cubrid/.just')
                (install / 'conf').mkdir(exist_ok=True)
                original = install / 'conf/cubrid.conf'
                original.write_text('[common]\nunfill_factor=0.7\ndouble_write_buffer_size=32M\n')
                selected = root / '.cub-workenv/conf/cubrid.conf'
                original_before = original.read_bytes()
                env['CUBRID_CONF_FILE'] = str(selected)
                crudini = shutil.which('crudini')
                self.assertIsNotNone(crudini, 'configuration recipe integration requires crudini')
                ini = commands / 'ini.sh'
                ini.write_text('#!/bin/sh\n' +
                    f'if [ "$#" = 5 ]; then exec {shlex.quote(crudini)} --set "$3" "$2" "$4" "$5"; '
                    f'else exec {shlex.quote(crudini)} --get "$3" "$2" "$4"; fi\n')
                ini.chmod(0o755)
                recipe_env = dict(env, PATH=str(commands) + ':' + env['PATH'])
                for setter, getter, expected_value in (
                        ('db::set-unfill-factor', 'db::get-unfill-factor', '0.0'),
                        ('dwb-off', 'dwb-get', '0')):
                    updated = subprocess.run(['just', setter], cwd=root, env=recipe_env,
                                             capture_output=True, text=True)
                    self.assertEqual(updated.returncode, 0, updated.stderr)
                    observed = subprocess.run(['just', getter], cwd=root, env=recipe_env,
                                              capture_output=True, text=True)
                    self.assertEqual(observed.returncode, 0, observed.stderr)
                    self.assertEqual(observed.stdout.strip(), expected_value)
                    self.assertEqual(original.read_bytes(), original_before)
                self.assertIn('unfill_factor = 0.0', selected.read_text())
                self.assertIn('double_write_buffer_size = 0', selected.read_text())

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
