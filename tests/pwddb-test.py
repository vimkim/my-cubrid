#!/usr/bin/env python3
"""Public lifecycle preservation/failure cases; native engine proof is separate."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CLI = os.environ.get('CUB_WORKENV_CLI')
NATIVE = '''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
registry = Path(os.environ['CUBRID_DATABASES']) / 'databases.txt'
if args[0] == 'createdb':
    name = args[-2]
    data, log, lob = (Path(args[args.index(flag)+1]) for flag in ('-F', '-L', '-B'))
    (data / name).write_text('volume sentinel')
    (log / (name + '_lgat')).write_text('log sentinel')
    (data / (name + '_vinf')).write_text(f'0 {data}/{name}\\n-2 {log}/{name}_lgat\\n')
    registry.write_text(f'{name} {data} localhost {log} file:{lob}\\n')
elif args[0] == 'deletedb':
    if os.environ.get('FAIL_DELETE'):
        print('native owner PID 123; deletion refused', file=sys.stderr); sys.exit(7)
    fields = registry.read_text().split()
    data, log = Path(fields[1]), Path(fields[3])
    for path in (data / fields[0], data / (fields[0] + '_vinf'), log / (fields[0] + '_lgat')):
        path.unlink()
    registry.write_text('')
elif args[0] == 'loaddb' and os.environ.get('FAIL_LOAD'):
    sys.exit(8)
'''


@unittest.skipUnless(CLI, 'set CUB_WORKENV_CLI to the reviewed CLI')
class WorkenvDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cwe-db-test-')
        self.root = Path(self.temp.name)
        self.install = self.root / 'install'
        (self.install / 'bin').mkdir(parents=True)
        for name in ('cubrid', 'csql'):
            binary = self.install / 'bin' / name
            binary.write_text(NATIVE)
            binary.chmod(0o755)
        (self.install / 'demo').mkdir()
        for name in ('demodb_schema', 'demodb_objects'):
            (self.install / 'demo' / name).touch()
        self.env = dict(os.environ, CUB_WORKENV_CLI=CLI, CUBRID=str(self.install), PRESET_MODE='debug',
                        CUBRID_BUILD_DIR=str(self.root / 'build'), XDG_RUNTIME_DIR=str(self.root),
                        MY_CUBRID=str(REPO))
        subprocess.run([CLI, 'init', '--no-db', '--install', str(self.install), '--preset', 'debug',
            '--worktree', str(self.root), '--state-home', str(self.root / 'host')],
            env=self.env, check=True, capture_output=True)
        self.runtime = self.root / '.cub-workenv'
        self.registry = self.runtime / 'databases/databases.txt'
        (self.root / 'justfile').symlink_to(REPO / 'stow/cubrid/justfile')
        (self.root / '.just').symlink_to(REPO / 'stow/cubrid/.just')

    def tearDown(self):
        state = json.loads((self.runtime / 'state.json').read_text())
        shutil.rmtree(state['allocation']['tmp'])
        self.temp.cleanup()

    def run_db(self, *args, ok=True, helper='cubrid-workenv-db', **extra):
        result = subprocess.run([str(REPO / 'bin' / helper), *args], cwd=self.root,
                                env=dict(self.env, **extra), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_empty_registry_real_recipe_create_and_duplicate_preservation(self):
        result = subprocess.run(['just', 'db::create-testdb'], cwd=self.root, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.registry.read_bytes()
        primary = self.runtime / 'db/testdb/data/testdb'
        identity = primary.stat().st_ino
        self.run_db('create', ok=False)
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertEqual(primary.stat().st_ino, identity)

    def test_names_listing_compatibility_and_ensure_preserve_arbitrary_entries(self):
        self.assertEqual(self.run_db('list').stdout, '')
        self.assertEqual(self.run_db(helper='my-cubrid-pwddb-getname').stdout, 'testdb\n')
        self.run_db('create', 'extra', helper='my-cubrid-pwddb')
        self.run_db('create')
        before = self.registry.read_bytes()
        self.assertEqual(self.run_db('list').stdout, 'extra\ntestdb\n')
        self.run_db('ensure', 'extra')
        self.assertEqual(self.registry.read_bytes(), before)
        self.run_db('name', '--append-name', 'demodb', ok=False)

    def test_delete_and_recreate_preserve_other_rows_comments_and_leftovers(self):
        self.run_db('create', 'extra')
        original = self.registry.read_bytes() + b'# keep this exact comment\r\n'
        self.registry.write_bytes(original)
        self.run_db('create')
        leftover = self.runtime / 'db/testdb/lob/user-file'
        leftover.write_text('retain me')
        self.run_db('recreate')
        self.assertTrue(self.registry.read_bytes().startswith(original))
        self.assertEqual(leftover.read_text(), 'retain me')
        self.run_db('delete')
        self.assertEqual(self.registry.read_bytes(), original)

    def test_native_failure_preserves_registration_and_receipt_without_fallback(self):
        self.run_db('create')
        before = self.registry.read_bytes()
        result = self.run_db('delete', ok=False, FAIL_DELETE='1')
        self.assertIn('native owner PID 123', result.stderr)
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertTrue((self.runtime / 'created-testdb.json').exists())
        self.assertTrue((self.runtime / 'db/testdb/data/testdb').exists())

    def test_external_mixed_symlink_and_unknown_provenance_refuse_without_writes(self):
        self.run_db('create')
        base = self.runtime / 'db/testdb'
        receipt = self.runtime / 'created-testdb.json'
        registry = self.registry.read_bytes()
        saved_receipt = receipt.read_bytes()
        receipt.unlink()
        self.run_db('delete', ok=False)
        receipt.write_bytes(saved_receipt)
        outside = self.root / 'external'; outside.write_text('external sentinel')
        link = base / 'lob/link'; link.symlink_to(outside)
        self.run_db('delete', ok=False)
        link.unlink()
        vinf = base / 'data/testdb_vinf'; original = vinf.read_text()
        vinf.write_text(original + f'1 {outside}\n')
        self.run_db('delete', ok=False)
        vinf.write_text(original)
        self.registry.write_bytes(registry.replace(str(base / 'log').encode(), str(self.root).encode()))
        self.run_db('delete', ok=False)
        self.assertEqual(outside.read_text(), 'external sentinel')
        self.assertTrue((base / 'data/testdb').exists())

    def test_load_failure_retains_created_database_and_missing_template_creates_nothing(self):
        self.run_db('create', '--load', 'demodb', ok=False, FAIL_LOAD='1')
        self.assertIn(b'testdb ', self.registry.read_bytes())
        self.assertTrue((self.runtime / 'created-testdb.json').is_file())
        (self.install / 'demo/demodb_schema').unlink()
        self.run_db('create', 'demodb', '--load', 'demodb', ok=False)
        self.assertNotIn(b'demodb ', self.registry.read_bytes())
        self.assertFalse((self.runtime / 'db/demodb').exists())

    def test_disabled_native_locking_refuses_deletion(self):
        self.run_db('create')
        config = self.runtime / 'conf/cubrid.conf'
        config.write_text(config.read_text() + '\n[@testdb]\nfile_lock=no\n')
        before = self.registry.read_bytes()
        result = self.run_db('delete', ok=False)
        self.assertIn('native exclusion is required', result.stderr)
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertTrue((self.runtime / 'db/testdb/data/testdb').exists())


if __name__ == '__main__':
    unittest.main()
