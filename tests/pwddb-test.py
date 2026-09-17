#!/usr/bin/env python3
"""Exercise the public commands with real Git directories and a stateful CUBRID fake."""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

BIN = Path(__file__).resolve().parents[1] / 'bin'
spec = importlib.util.spec_from_file_location('runtime_fixture', Path(__file__).with_name('runtime-guard-test.py'))
runtime_fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_fixture)
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
root = pathlib.Path(os.environ['CUBRID_DATABASES'])
with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(args) + '\n')
registry = root / 'databases.txt'
rows = registry.read_text().splitlines() if registry.exists() else []
if os.environ.get('FAIL') == ' '.join(args[:2]) or os.environ.get('FAIL') == args[0]: sys.exit(1)
if args == ['server', 'status']:
    print('Server unrelated (rel 11.5, pid 1)')
    if os.environ.get('RUNNING'): print('Server ' + os.environ['RUNNING'] + ' (rel 11.5, pid 2)')
elif args[0] == 'createdb':
    if os.environ.get('PAUSE_CREATE'):
        registry.write_text('incomplete')
        pause = pathlib.Path(os.environ['PAUSE_CREATE'])
        pause.with_suffix('.reached').touch()
        while not pause.exists(): time.sleep(0.01)
    name = args[args.index('en_US.utf8') - 1]
    rows.append(name + ' ' + args[args.index('-F') + 1] + ' localhost ' + args[args.index('-L') + 1]
                + ' ' + args[args.index('-B') + 1])
    registry.write_text('\n'.join(rows) + '\n')
elif args[0] == 'deletedb':
    registry.write_text('\n'.join(row for row in rows if row.split()[0] != args[1]) + '\n')
'''


class PwddbTests(unittest.TestCase):
    def setUp(self):
        fixture = runtime_fixture.RuntimeGuardCliTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        self.cwd = fixture.worktree
        fake = fixture.installation / 'bin' / 'cubrid'
        fake.write_text(FAKE)
        fake.chmod(0o755)
        demo = fixture.installation / 'demo'
        demo.mkdir(parents=True)
        for name in ('demodb_schema', 'demodb_objects'):
            (demo / name).touch()
        self.env = dict(fixture.environment, PRESET_MODE='debug',
                        CALLS=str(self.root / 'calls'), RUNNING='', FAIL='')
        result = fixture.run_runtime_for(self.cwd, self.env, 'init', '--db-name', 'Chosen_DB', '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.manifest = fixture.manifest_for(result)
        self.bundle = self.manifest['resource_bundle']
        self.dbroot = Path(self.bundle['database_registry'])

    def run_cli(self, command, *args, ok=True):
        env = dict(self.env, PWD=str(self.cwd))
        result = subprocess.run([str(BIN / command), *args], cwd=self.cwd,
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr + result.stdout)
        return result

    def calls(self):
        path = self.root / 'calls'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def register(self, *names):
        (self.dbroot / 'databases.txt').write_text(''.join(
            f'{name} {self.bundle["data_root"]} localhost {self.bundle["log_root"]} file:{self.bundle["lob_root"]}\n' for name in names))
        (self.dbroot / 'databases.txt').chmod(0o600)

    def test_naming_precedence(self):
        self.assertEqual(self.run_cli('my-cubrid-ticket-get', ok=False).returncode, 1)
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'Chosen_DB\n')
        self.run_cli('my-cubrid-pwddb-getname', '--append-name', 'demodb', ok=False)
        subprocess.run(['git', 'symbolic-ref', 'HEAD', 'refs/heads/feat/cbrd-12345'], cwd=self.cwd, check=True)
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'Chosen_DB\n')
        child = self.cwd / 'CBRD-67890-work'
        child.mkdir()
        self.cwd = child
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'Chosen_DB\n')

    def test_non_ready_manifests_refuse_every_helper_action(self):
        manifest_path = next(self.fixture.state_home.glob('cubrid-worktree-guard/worktrees/*/manifest.json'))
        for state in ('initializing', 'recovery_required', 'deinitializing'):
            manifest_path.write_text(json.dumps({**self.manifest, 'state': state}))
            self.run_cli('my-cubrid-pwddb-getname', ok=False)
            for action in ('ensure', 'create', 'recreate', 'delete'):
                self.run_cli('my-cubrid-pwddb', action, ok=False)
        self.assertEqual(self.calls(), [])

    def test_inherited_registry_and_executable_do_not_override_manifest(self):
        outside = self.root / 'unrelated-registry'
        outside.mkdir()
        self.env['CUBRID_DATABASES'] = str(outside)
        self.run_cli('my-cubrid-pwddb', 'ensure')
        self.assertEqual([call[0] for call in self.calls()], ['createdb'])
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.fixture.calls.exists())

    def test_ambiguous_and_invalid_names(self):
        for directory in ('CBRD-1-CBRD-2', 'bad name', '#invalid', '-option'):
            self.cwd = self.root / directory
            self.cwd.mkdir()
            self.run_cli('my-cubrid-pwddb-getname', ok=False)
        self.cwd = self.fixture.worktree
        for suffix in ('', '../escape', 'very-long-suffix', 'bad name', '@host'):
            self.run_cli('my-cubrid-pwddb-getname', '--append-name', suffix, ok=False)

    def test_repeated_ticket_is_not_ambiguous(self):
        self.cwd = self.root / 'cbrd-123-CBRD-123'
        self.cwd.mkdir()
        self.assertEqual(self.run_cli('my-cubrid-ticket-get').stdout, 'CBRD-123\n')

    def test_branch_ambiguity_and_detached_head(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True)
        subprocess.run(['git', 'symbolic-ref', 'HEAD', 'refs/heads/CBRD-1-CBRD-2'], cwd=self.cwd, check=True)
        self.assertEqual(self.run_cli('my-cubrid-ticket-get', ok=False).returncode, 2)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '--allow-empty', '-qm', 'test'], cwd=self.cwd, check=True)
        subprocess.run(['git', 'checkout', '--detach', '-q'], cwd=self.cwd, check=True)
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'Chosen_DB\n')

    @unittest.skipUnless(shutil.which('just'), 'just unavailable')
    def test_recipes_preserve_invocation_directory(self):
        home = self.root / 'home'
        wrapper = home / 'my-cubrid/bin/my-cubrid-pwddb'
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$@"\n')
        wrapper.chmod(0o755)
        (self.cwd / 'justfile').write_text(
            "mod db '" + str(BIN.parent / 'stow/cubrid/.just/db.just') + "'\n")
        child = self.cwd / 'child'
        child.mkdir()
        for action in ('create', 'recreate', 'delete'):
            for demo in (False, True):
                recipe = 'pwddb-' + action + ('-demodb' if demo else '')
                expected = [str(child), action]
                if demo:
                    if action != 'delete':
                        expected += ['--load', 'demodb']
                result = subprocess.run(['just', 'db', recipe], cwd=child,
                                        env=dict(self.env, HOME=str(home)),
                                        text=True, capture_output=True, check=True)
                self.assertEqual(result.stdout.splitlines(), expected)

    def test_empty_create_and_suffix_without_load(self):
        self.run_cli('my-cubrid-pwddb', 'create', '--append-name', 'demodb', ok=False)
        self.assertEqual(self.calls(), [])
        self.run_cli('my-cubrid-pwddb', 'create')
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('Chosen_DB', self.calls()[0])
        self.run_cli('my-cubrid-pwddb', 'create', ok=False)
        self.assertEqual(len(self.calls()), 1)

    def test_ensure_creates_once_and_preserves_existing_database(self):
        self.run_cli('my-cubrid-pwddb', 'ensure')
        registry = (self.dbroot / 'databases.txt').read_text()
        self.env['RUNNING'] = 'Chosen_DB'
        result = self.run_cli('my-cubrid-pwddb', 'ensure')
        self.assertIn('already exists', result.stdout)
        self.assertEqual([call[0] for call in self.calls()], ['createdb'])
        self.assertEqual((self.dbroot / 'databases.txt').read_text(), registry)
        self.assertIn('Chosen_DB', registry)
        for flag, role in (('-F', 'data_root'), ('-L', 'log_root')):
            self.assertEqual(self.calls()[0][self.calls()[0].index(flag) + 1], self.bundle[role])
        self.assertEqual(self.calls()[0][-1], 'file:' + self.bundle['lob_root'])

    def test_ensure_creation_failure_is_reported(self):
        self.env['FAIL'] = 'createdb'
        self.run_cli('my-cubrid-pwddb', 'ensure', ok=False)
        self.assertFalse((self.dbroot / 'databases.txt').exists())

    def test_concurrent_ensure_creates_once(self):
        processes = [subprocess.Popen([str(BIN / 'my-cubrid-pwddb'), 'ensure'],
                                     cwd=self.cwd, env=dict(self.env, PWD=str(self.cwd)),
                                     text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(4)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual([call[0] for call in self.calls()], ['createdb'])

    def test_concurrent_ensure_waits_for_registry_publication(self):
        pause = self.root / 'create-resume'
        self.env['PAUSE_CREATE'] = str(pause)
        processes = []
        try:
            processes.append(subprocess.Popen([str(BIN / 'my-cubrid-pwddb'), 'ensure'], cwd=self.cwd,
                                              env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            deadline = time.monotonic() + 5
            while not pause.with_suffix('.reached').exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            self.fixture.replace_observations({'processes': [{
                'pid': 123, 'executable': str(self.fixture.installation / 'bin' / 'cubrid'),
                'configuration': {'database_registry': str(self.dbroot)},
            }]})
            processes.append(subprocess.Popen([str(BIN / 'my-cubrid-pwddb'), 'ensure'], cwd=self.cwd,
                                              env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            time.sleep(0.15)
            self.fixture.replace_observations({})
            pause.touch()
            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stdout + stderr)
            self.assertEqual([call[0] for call in self.calls()], ['createdb'])
        finally:
            pause.touch()
            for process in processes:
                process.communicate(timeout=10)

    def test_template_load_and_failure_retention(self):
        self.env['FAIL'] = 'loaddb'
        result = self.run_cli('my-cubrid-pwddb', 'create', '--load', 'demodb', ok=False)
        self.assertIn('retained', result.stderr)
        self.assertEqual([x[0] for x in self.calls()], ['createdb', 'loaddb'])
        self.assertIn('--db-page-size=16K', self.calls()[0])
        self.assertIn('Chosen_DB', (self.dbroot / 'databases.txt').read_text())

    def test_targeted_recreate_running_and_missing(self):
        self.register('Chosen_DB')
        self.env['RUNNING'] = 'Chosen_DB'
        self.run_cli('my-cubrid-pwddb', 'recreate')
        self.assertEqual([x[:2] for x in self.calls()[:3]],
                         [['server', 'status'], ['server', 'stop'], ['deletedb', 'Chosen_DB']])
        self.register()
        self.run_cli('my-cubrid-pwddb', 'recreate')
        self.assertEqual(self.calls()[-1][0], 'createdb')

    def test_delete_absent_and_failures(self):
        self.run_cli('my-cubrid-pwddb', 'delete')
        self.assertEqual(self.calls(), [])
        self.register('Chosen_DB')
        for failure in ('server status', 'server stop', 'deletedb'):
            self.env.update(FAIL=failure, RUNNING='Chosen_DB')
            self.run_cli('my-cubrid-pwddb', 'recreate', ok=False)
            self.assertFalse(any(call[0] == 'createdb' for call in self.calls()))

    def test_preflight_before_deletion(self):
        self.register('Chosen_DB')
        (Path(self.env['CUBRID']) / 'demo/demodb_schema').unlink()
        self.run_cli('my-cubrid-pwddb', 'recreate', '--load', 'demodb', ok=False)
        self.run_cli('my-cubrid-pwddb', 'delete', '--load', 'demodb', ok=False)
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main()
