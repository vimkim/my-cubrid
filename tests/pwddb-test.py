#!/usr/bin/env python3
"""Exercise the public commands with real Git directories and a stateful CUBRID fake."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

BIN = Path(__file__).resolve().parents[1] / 'bin'
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
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
    name = args[args.index('en_US.utf8') - 1]
    rows.append(name + ' ' + str(root / name) + ' localhost ' + str(root / name))
    registry.write_text('\n'.join(rows) + '\n')
elif args[0] == 'deletedb':
    registry.write_text('\n'.join(row for row in rows if row.split()[0] != args[1]) + '\n')
'''


class PwddbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cwd = self.root / 'oos-storage'
        self.cwd.mkdir()
        fakebin = self.root / 'bin'
        fakebin.mkdir()
        fake = fakebin / 'cubrid'
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.dbroot = self.root / 'databases'
        self.dbroot.mkdir()
        demo = self.root / 'install' / 'demo'
        demo.mkdir(parents=True)
        for name in ('demodb_schema', 'demodb_objects'):
            (demo / name).touch()
        self.env = dict(os.environ, PATH=str(fakebin) + ':' + os.environ['PATH'],
                        CUBRID_DATABASES=str(self.dbroot), CUBRID=str(demo.parent),
                        CALLS=str(self.root / 'calls'), RUNNING='', FAIL='')

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
            f'{name} {self.dbroot / name} localhost {self.dbroot / name}\n' for name in names))

    def test_naming_precedence(self):
        self.assertEqual(self.run_cli('my-cubrid-ticket-get', ok=False).returncode, 1)
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'oos-storag\n')
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname', '--append-name', 'demodb').stdout,
                         'oos-storag-demodb\n')
        subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True)
        subprocess.run(['git', 'symbolic-ref', 'HEAD', 'refs/heads/feat/cbrd-12345'], cwd=self.cwd, check=True)
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'CBRD-12345\n')
        child = self.cwd / 'CBRD-67890-work'
        child.mkdir()
        self.cwd = child
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'CBRD-67890\n')

    def test_ambiguous_and_invalid_names(self):
        for directory in ('CBRD-1-CBRD-2', 'bad name', '#invalid', '-option'):
            self.cwd = self.root / directory
            self.cwd.mkdir()
            self.run_cli('my-cubrid-pwddb-getname', ok=False)
        self.cwd = self.root / 'oos-storage'
        for suffix in ('', '../escape', 'very-long-suffix', 'bad name', '@host'):
            self.run_cli('my-cubrid-pwddb-getname', '--append-name', suffix, ok=False)

    def test_repeated_ticket_is_not_ambiguous(self):
        self.cwd = self.root / 'cbrd-123-CBRD-123'
        self.cwd.mkdir()
        self.assertEqual(self.run_cli('my-cubrid-ticket-get').stdout, 'CBRD-123\n')

    def test_branch_ambiguity_and_detached_head(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True)
        subprocess.run(['git', 'symbolic-ref', 'HEAD', 'refs/heads/CBRD-1-CBRD-2'], cwd=self.cwd, check=True)
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname', ok=False).returncode, 2)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '--allow-empty', '-qm', 'test'], cwd=self.cwd, check=True)
        subprocess.run(['git', 'checkout', '--detach', '-q'], cwd=self.cwd, check=True)
        self.assertEqual(self.run_cli('my-cubrid-pwddb-getname').stdout, 'oos-storag\n')

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
                    expected += ['--append-name', 'demodb']
                    if action != 'delete':
                        expected += ['--load', 'demodb']
                result = subprocess.run(['just', 'db', recipe], cwd=child,
                                        env=dict(self.env, HOME=str(home)),
                                        text=True, capture_output=True, check=True)
                self.assertEqual(result.stdout.splitlines(), expected)

    def test_empty_create_and_suffix_without_load(self):
        self.run_cli('my-cubrid-pwddb', 'create', '--append-name', 'demodb')
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('oos-storag-demodb', self.calls()[0])
        self.run_cli('my-cubrid-pwddb', 'create', '--append-name', 'demodb', ok=False)
        self.assertEqual(len(self.calls()), 1)

    def test_ensure_creates_once_and_preserves_existing_database(self):
        self.register('unrelated')
        self.run_cli('my-cubrid-pwddb', 'ensure')
        registry = (self.dbroot / 'databases.txt').read_text()
        self.env['RUNNING'] = 'oos-storag'
        result = self.run_cli('my-cubrid-pwddb', 'ensure')
        self.assertIn('already exists', result.stdout)
        self.assertEqual([call[0] for call in self.calls()], ['createdb'])
        self.assertEqual((self.dbroot / 'databases.txt').read_text(), registry)
        self.assertIn('unrelated', registry)

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

    def test_template_load_and_failure_retention(self):
        self.env['FAIL'] = 'loaddb'
        result = self.run_cli('my-cubrid-pwddb', 'create', '--append-name', 'demodb', '--load', 'demodb', ok=False)
        self.assertIn('retained', result.stderr)
        self.assertEqual([x[0] for x in self.calls()], ['createdb', 'loaddb'])
        self.assertIn('--db-page-size=16K', self.calls()[0])
        self.assertIn('oos-storag-demodb', (self.dbroot / 'databases.txt').read_text())

    def test_targeted_recreate_running_and_missing(self):
        self.register('oos-storag', 'unrelated')
        self.env['RUNNING'] = 'oos-storag'
        self.run_cli('my-cubrid-pwddb', 'recreate')
        self.assertEqual([x[:2] for x in self.calls()[:3]],
                         [['server', 'status'], ['server', 'stop'], ['deletedb', 'oos-storag']])
        self.assertIn('unrelated', (self.dbroot / 'databases.txt').read_text())
        self.register('unrelated')
        self.run_cli('my-cubrid-pwddb', 'recreate', '--append-name', 'demo')
        self.assertEqual(self.calls()[-1][0], 'createdb')

    def test_delete_absent_and_failures(self):
        self.run_cli('my-cubrid-pwddb', 'delete')
        self.assertEqual(self.calls(), [])
        self.register('oos-storag', 'unrelated')
        for failure in ('server status', 'server stop', 'deletedb'):
            self.env.update(FAIL=failure, RUNNING='oos-storag')
            self.run_cli('my-cubrid-pwddb', 'recreate', ok=False)
            self.assertFalse(any(call[0] == 'createdb' for call in self.calls()))

    def test_preflight_before_deletion(self):
        self.register('oos-storag')
        (Path(self.env['CUBRID']) / 'demo/demodb_schema').unlink()
        self.run_cli('my-cubrid-pwddb', 'recreate', '--load', 'demodb', ok=False)
        self.run_cli('my-cubrid-pwddb', 'delete', '--load', 'demodb', ok=False)
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main()
