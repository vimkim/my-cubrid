#!/usr/bin/env python3
import fcntl
import json
import os
import pty
import select
import signal
import struct
from pathlib import Path
import subprocess
import tempfile
import termios
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / 'bin/cubrid-dev2-pr-reviewers'
OLD = ROOT / 'bin/cubrid-dev2-add-reviewers.py'
BASE = 'a' * 40
HEAD = 'b' * 40
MERGE = 'c' * 40
URL = 'https://github.com/CUBRID/cubrid/pull/42'

FAKE_GH = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
state = json.loads(pathlib.Path(os.environ['FAKE_GH_DATA']).read_text())
log = pathlib.Path(os.environ['FAKE_GH_LOG'])
with log.open('a') as f:
    f.write(json.dumps(args) + "\\n")
if not args or args[0] != 'api':
    sys.exit('forbidden command')
args = args[1:]
if args[:2] == ['-H', 'Accept: application/vnd.github.raw+json']:
    args = args[2:]
    if len(args) != 1 or args[0] not in state.get('sources', {}):
        sys.exit('unexpected source request')
    print(state['sources'][args[0]], end='')
elif len(args) == 1 and args[0] == 'repos/CUBRID/cubrid/pulls/42':
    calls = sum(1 for line in log.read_text().splitlines() if json.loads(line) == ['api', args[0]])
    selected = state.get('metadata_late', state['metadata']) if calls > 2 else state.get('metadata_after', state['metadata']) if calls > 1 else state['metadata']
    print(json.dumps(selected))
elif len(args) == 1 and args[0].startswith('repos/CUBRID/cubrid/pulls/42/files?per_page=100&page='):
    page = int(args[0].rsplit('=', 1)[1])
    print(json.dumps(state['files'][(page-1)*100:page*100]))
elif len(args) == 1 and args[0] == f"repos/CUBRID/cubrid/compare/{'a'*40}...{'b'*40}":
    print(json.dumps({'merge_base_commit': {'sha': 'c'*40}}))
else:
    sys.exit('forbidden endpoint: ' + repr(args))
'''


def changed(path, content='x', status='modified', previous=None):
    obj = {'filename': path, 'status': status, 'additions': 1, 'deletions': 0, 'patch': '@@ -0,0 +1 @@\n+' + content}
    if previous:
        obj['previous_filename'] = previous
    return obj


def meta(files, author='other', reviewers=(), teams=()):
    return {'base': {'sha': BASE}, 'head': {'sha': HEAD}, 'user': {'login': author}, 'changed_files': len(files), 'requested_reviewers': [{'login': r} for r in reviewers], 'requested_teams': [{'slug': t} for t in teams]}


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        fake = self.dir / 'gh'
        fake.write_text(FAKE_GH)
        fake.chmod(0o755)
        self.data = self.dir / 'data.json'
        self.log = self.dir / 'log'
        self.env = dict(os.environ, PATH=str(self.dir) + os.pathsep + os.environ['PATH'], FAKE_GH_DATA=str(self.data), FAKE_GH_LOG=str(self.log))

    def run_cli(self, files, *, author='other', reviewers=(), teams=(), sources=None, after=None, late=None, reported_count=None, args=()):
        state = {'metadata': meta(files, author, reviewers, teams), 'files': files, 'sources': sources or {}}
        if reported_count is not None:
            state['metadata']['changed_files'] = reported_count
        if after is not None:
            state['metadata_after'] = after
        if late is not None:
            state['metadata_late'] = late
        self.data.write_text(json.dumps(state))
        if self.log.exists():
            self.log.unlink()
        run = subprocess.run([str(CLI), URL, '--json', *args], text=True, capture_output=True, env=self.env)
        return run, json.loads(run.stdout)

    def test_exact_cover_and_primary_preference(self):
        heap = changed('src/storage/heap_file.c', 'btree_insert();')
        btree = changed('src/storage/btree.c')
        run, report = self.run_cli([heap, btree])
        self.assertEqual(run.returncode, 0)
        self.assertEqual(report['required_modules'], ['btree', 'heap'])
        self.assertEqual(report['recommendations'][0]['additional'], ['lht1199'])
        run, report = self.run_cli([heap, changed('src/storage/oos_file.hpp')])
        self.assertEqual(report['recommendations'][0]['additional'], ['InChiJun', 'lht1199'])
        run, report = self.run_cli([heap, changed('src/transaction/recovery.c')])
        self.assertEqual(len(report['recommendations'][0]['additional']), 2)
        self.assertEqual(report['recommendations'][0]['additional'], ['hgryoo', 'lht1199'])
        run, report = self.run_cli([heap], author='lht1199')
        self.assertEqual((run.returncode, report['verdict']), (2, 'uncoverable'))
        run, report = self.run_cli([heap], reviewers=['vimkim', 'unknown'], teams=['team-a'])
        self.assertEqual(report['recommendations'][0]['additional'], [])
        self.assertEqual(report['unmapped_requested'], ['unknown'])
        self.assertEqual(report['requested_teams'], ['team-a'])

    def test_text_recommends_count_and_existing_coverage(self):
        files = [changed('src/storage/heap_file.c')]
        for reviewers, expected in [((), 'lht1199; 주담당: heap'), (('vimkim',), '추가 요청 없음; 주담당: 없음')]:
            self.data.write_text(json.dumps({'metadata': meta(files, reviewers=reviewers), 'files': files}))
            if self.log.exists():
                self.log.unlink()
            run = subprocess.run([str(CLI), URL], text=True, capture_output=True, env=self.env, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn(expected, run.stdout)
            self.assertIn('Head: ' + HEAD, run.stdout)
        slug = 'storage-reviewers-for-international-database-maintenance'
        run, report = self.run_cli(files, teams=[slug])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(report['requested_teams'], [slug])

    def test_transaction_and_recovery_families(self):
        files = [changed('src/transaction/transaction_sr.c'), changed('src/transaction/log_tran_table.c'), changed('src/transaction/log_recovery.c'), changed('src/transaction/log_recovery_redo_parallel.hpp')]
        run, report = self.run_cli(files)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(report['required_modules'], ['log_manager', 'recovery'])
        self.assertEqual(report['recommendations'][0]['additional'], ['hgryoo'])

    def test_unknown_missing_patch_and_no_source(self):
        run, report = self.run_cli([changed('src/mystery.c')])
        self.assertEqual((run.returncode, report['verdict']), (2, 'provisional'))
        self.assertTrue(report['gaps'])
        f = changed('src/storage/heap_file.c')
        del f['patch']
        run, report = self.run_cli([f])
        self.assertEqual(run.returncode, 2)
        self.assertEqual(report['required_modules'], ['heap'])
        f['patch'] = '@@ -0,0 +1,2 @@\n+one'
        f['additions'] = 2
        run, report = self.run_cli([f])
        self.assertEqual(run.returncode, 2)
        self.assertIn('patch', report['gaps'][0]['reason'])
        run, report = self.run_cli([changed('README.md')])
        self.assertEqual((run.returncode, report['verdict']), (0, 'no-source-changes'))

    def test_renames_delete_and_pagination(self):
        f = changed('src/storage/btree.c', status='renamed', previous='src/storage/heap_file.c')
        f.update(additions=0, deletions=0, patch=None)
        run, report = self.run_cli([f])
        self.assertEqual(report['required_modules'], ['btree', 'heap'])
        self.assertEqual(run.returncode, 2)
        self.assertIn('patch unavailable', report['gaps'][0]['reason'])
        f = changed('src/storage/heap_file.c', status='removed')
        f.update(additions=0, deletions=1, patch='@@ -1 +0,0 @@\n---removed content')
        run, report = self.run_cli([f])
        self.assertEqual((run.returncode, report['required_modules']), (0, ['heap']))
        files = [changed(f'docs/file{i}') for i in range(100)] + [changed('src/storage/heap_file.c')]
        run, report = self.run_cli(files)
        self.assertEqual(run.returncode, 0)
        self.assertIn('page=2', self.log.read_text())

    def test_changed_metadata(self):
        files = [changed('src/storage/heap_file.c')]
        after = meta(files, reviewers=['vimkim'])
        run, report = self.run_cli(files, after=after)
        self.assertEqual(run.returncode, 2)
        self.assertIn('changed while', report['gaps'][0]['reason'])
        run, report = self.run_cli(files, late=after)
        self.assertEqual(run.returncode, 2)
        self.assertIn('reading source', report['gaps'][0]['reason'])
        run, report = self.run_cli(files, reported_count=2)
        self.assertEqual(run.returncode, 2)
        self.assertIn('returned 1', report['gaps'][0]['reason'])

    def test_shared_sources_use_merge_base_and_definitions(self):
        path = 'src/storage/file_io.c'
        old = 'static int\nfileio_backup_data (void)\n{\n  return 1;\n}\n'
        new = 'static int\nfileio_read_data (void)\n{\n  fileio_backup_data();\n  return 2;\n}\n'
        f = changed(path)
        f.update(additions=1, deletions=1, patch='@@ -4 +5 @@ fileio_backup_data\n-  return 1;\n+  return 2;')
        sources = {f'repos/CUBRID/cubrid/contents/{path}?ref={MERGE}': old, f'repos/CUBRID/cubrid/contents/{path}?ref={HEAD}': new}
        run, report = self.run_cli([f], sources=sources)
        self.assertEqual(run.returncode, 0, report)
        self.assertEqual(report['required_modules'], ['backup', 'file_io'])
        self.assertIn(f'ref={MERGE}', self.log.read_text())
        f.update(additions=1, deletions=0, patch='@@ -0,0 +1 @@\n+static int')
        run, report = self.run_cli([f], sources=sources)
        self.assertEqual(report['required_modules'], ['file_io'])
        f['patch'] = '@@ -0,0 +7 @@\n+#define X 1'
        run, report = self.run_cli([f], sources=sources)
        self.assertEqual(run.returncode, 2)
        self.assertTrue(report['gaps'])

    def test_shared_cdc_header_and_missing_source(self):
        path = 'src/transaction/log_manager.c'
        source = 'void\ncdc_extract (void)\n{\n  log_backup();\n}\n'
        f = changed(path)
        f['patch'] = '@@ -0,0 +4 @@\n+  log_backup();'
        sources = {f'repos/CUBRID/cubrid/contents/{path}?ref={HEAD}': source}
        run, report = self.run_cli([f], sources=sources)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(report['required_modules'], ['cdc'])
        run, report = self.run_cli([f], reviewers=['hornetmj'], sources=sources)
        self.assertEqual(report['existing_coverage'], ['cdc'])
        self.assertEqual(report['recommendations'][0]['additional'], [])
        run, report = self.run_cli([f])
        self.assertEqual(run.returncode, 2)
        self.assertIn('source unavailable', report['gaps'][0]['reason'])
        header = changed('src/transaction/log_manager.h')
        run, report = self.run_cli([header])
        self.assertEqual(run.returncode, 2)
        self.assertEqual(report['required_modules'], [])
        doc = changed('src/storage/docs/btree-indexes.md')
        run, report = self.run_cli([doc])
        self.assertEqual(run.returncode, 2)
        self.assertEqual(report['required_modules'], [])

    def test_six_people_ranks_states_and_reasons(self):
        files = [changed('src/storage/heap_file.c')]
        for author in ('vimkim', 'outside'):
            run, report = self.run_cli(files, author=author, reviewers=['hgryoo'])
            self.assertEqual(run.returncode, 0)
            rows = report['ranking']
            self.assertEqual(len(rows), 6)
            self.assertEqual({r['login'] for r in rows}, {'lht1199', 'YeunjunLee', 'InChiJun', 'hgryoo', 'H2SU', 'youngjun9072'})
            self.assertEqual((rows[0]['login'], rows[0]['rank'], rows[0]['primary_count']), ('lht1199', 1, 1))
            zeros = [r for r in rows if not r['module_count']]
            self.assertEqual({r['rank'] for r in zeros}, {2})
            self.assertTrue(all(r['tied'] and '직접 담당 없음' in r['reason'] for r in zeros))
            requested = next(r for r in rows if r['login'] == 'hgryoo')
            self.assertTrue(requested['requested'])
            self.assertFalse(requested['can_request'])
            self.assertIn('이미 요청됨', requested['reason'])
            self.assertTrue(all(not {'vimkim', 'hornetmj'} & set(c['additional']) for c in report['recommendations']))
        run, report = self.run_cli(files, author='lht1199')
        self.assertEqual(sum(r['can_request'] for r in report['ranking']), 5)
        row = report['ranking'][-1]
        self.assertTrue(row['author'])
        self.assertIsNone(row['rank'])
        self.assertIn('작성자', row['reason'])
        self.assertFalse(any('lht1199' in c['additional'] for c in report['recommendations']))
        run, report = self.run_cli(files, author='lht1199', reviewers=['lht1199'])
        self.assertTrue(report['ranking'][-1]['requested'])
        self.assertFalse(report['ranking'][-1]['can_request'])
        self.assertIn('이미 요청됨', report['ranking'][-1]['reason'])
        run, report = self.run_cli([changed('src/mystery.c')])
        self.assertTrue(all('분석 대기' in r['reason'] for r in report['ranking']))
        run, report = self.run_cli([changed('README.md')])
        self.assertTrue(all('src/ 변경이 없어' in r['reason'] for r in report['ranking']))
        run, report = self.run_cli(files + [changed('src/mystery.c')])
        self.assertEqual(report['verdict'], 'provisional')
        self.assertIn('heap (주담당)', report['ranking'][0]['reason'])

    def test_exclusion_config_validation(self):
        original = (ROOT / 'cubrid-review-owners.toml').read_text()
        config = self.dir / 'owners.toml'
        for exclusions in ('["nobody"]', '["vimkim", "VIMKIM"]', '"vimkim"', '[1]'):
            config.write_text(original.replace('["vimkim", "hornetmj"]', exclusions))
            run, report = self.run_cli([], args=('--config', str(config)))
            self.assertEqual(run.returncode, 1)
            self.assertIn('configuration', report['error'])
        config.write_text(original.replace('["vimkim", "hornetmj"]', '["lht1199", "vimkim", "YeunjunLee", "InChiJun", "youngjun9072", "hgryoo", "H2SU", "hornetmj"]'))
        run, report = self.run_cli([], args=('--config', str(config)))
        self.assertEqual(run.returncode, 1)
        self.assertIn('candidate', report['error'])
        config.write_text(original.replace('recommendation_exclusions = ["vimkim", "hornetmj"]\n', ''))
        run, report = self.run_cli([], args=('--config', str(config)))
        self.assertEqual(run.returncode, 1)

    def test_tui_navigation_scroll_resize_and_quit(self):
        files = [changed(f'src/storage/heap_file.case{i}') for i in range(30)]
        self.data.write_text(json.dumps({'metadata': meta(files), 'files': files}))
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        def resize(rows, cols):
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        resize(24, 80)
        env = dict(self.env, TERM='xterm-256color', LC_ALL='C.UTF-8')
        process = subprocess.Popen([str(CLI), URL], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        def cleanup_process():
            if process.poll() is None:
                process.kill()
                process.wait()
        self.addCleanup(cleanup_process)

        def receive(needle):
            output = b''
            deadline = time.monotonic() + 15
            while needle.encode() not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.25)[0]:
                    try:
                        output += os.read(master, 65536)
                    except OSError:
                        break
            self.assertIn(needle.encode(), output, output.decode('utf-8', 'replace'))
            return output.decode('utf-8', 'replace')

        initial = receive('@lht1199')
        for name in ('임형태', '이연준', '인치준', '유형규', '김희수', '유영준'):
            self.assertIn(name, initial)
        os.write(master, b'\x1b[6~')
        receive('heap_file.case9')
        os.write(master, b'\x1b[5~')
        receive('@lht1199')
        os.write(master, b'\x1bOB')
        receive('@H2SU')
        while select.select([master], [], [], 0.2)[0]:
            os.read(master, 65536)
        resize(10, 40)
        os.kill(process.pid, signal.SIGWINCH)
        receive('화면이 너무 작습니다')
        resize(24, 80)
        os.kill(process.pid, signal.SIGWINCH)
        receive('@H2SU')
        os.write(master, b'q')
        self.assertEqual(process.wait(timeout=5), 0)

    def test_plain_and_json_remain_noninteractive_on_tty(self):
        files = [changed('src/storage/heap_file.c')]
        self.data.write_text(json.dumps({'metadata': meta(files), 'files': files}))
        for option, expected in (('--plain', '검토자 순위'), ('--json', '"ranking"')):
            if self.log.exists():
                self.log.unlink()
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen([str(CLI), URL, option], stdin=slave, stdout=slave, stderr=slave, env=self.env)
                os.close(slave)
                output = b''
                while select.select([master], [], [], 15)[0]:
                    try:
                        output += os.read(master, 65536)
                    except OSError:
                        break
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertIn(expected, output.decode('utf-8'))
                self.assertNotIn(b'\x1b[?1049h', output)
            finally:
                os.close(master)

    def test_json_parse_errors(self):
        run = subprocess.run([str(CLI), '--json', '--alternatives', 'bad', URL], text=True, capture_output=True, env=self.env)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)['verdict'], 'error')

    def test_invalid_input_help_and_deprecation(self):
        run = subprocess.run([str(CLI), 'https://github.com/elsewhere/cubrid/pull/1', '--json'], text=True, capture_output=True, env=self.env)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)['verdict'], 'error')
        bad = self.dir / 'bad.toml'
        bad.write_text('bad = [')
        run = subprocess.run([str(CLI), URL, '--config', str(bad), '--json'], text=True, capture_output=True, env=self.env)
        self.assertEqual(run.returncode, 1)
        self.assertIn('configuration', json.loads(run.stdout)['error'])
        self.data.write_text(json.dumps({'metadata': {}, 'files': []}))
        run = subprocess.run([str(CLI), URL, '--json'], text=True, capture_output=True, env=self.env)
        self.assertEqual(run.returncode, 1)
        self.assertIn('metadata', json.loads(run.stdout)['error'])
        (self.dir / 'gh').write_text('#!/bin/sh\necho permission denied >&2\nexit 1\n')
        run = subprocess.run([str(CLI), URL, '--json'], text=True, capture_output=True, env=self.env)
        self.assertEqual(run.returncode, 1)
        self.assertIn('permission denied', json.loads(run.stdout)['error'])
        self.assertFalse((ROOT / 'bin' / ('cubrid-' + 'pr-reviewers')).exists())
        for cli in (CLI, OLD):
            run = subprocess.run([str(cli), '--help'], text=True, capture_output=True, env=self.env)
            self.assertEqual(run.returncode, 0)
            if cli == OLD:
                self.assertIn('Deprecated', run.stdout)
                self.assertIn('whole team', run.stderr)
                self.assertIn('cubrid-dev2-pr-reviewers', run.stderr)


if __name__ == '__main__':
    unittest.main()
