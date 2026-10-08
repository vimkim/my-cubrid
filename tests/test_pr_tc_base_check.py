#!/usr/bin/env python3
"""Integration checks using disposable local Git remotes; no network access."""
import errno
import io
import json
import os
from pathlib import Path
import pty
import runpy
import select
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / 'bin'
SCRIPT = BIN / 'cubrid-pr-tc-base-check'
WRAPPER = BIN / 'cubrid-pr-tc-base-check-oos'


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                        GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.org',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.org')
        self.repos = []
        for name in ('public', 'private'):
            remote = self.root / (name + '.git')
            repo = self.root / name
            self.run_cmd('git', 'init', '--bare', str(remote))
            self.run_cmd('git', 'clone', str(remote), str(repo))
            self.git(repo, 'checkout', '-b', 'feature/oos-merge')
            self.git(repo, 'commit', '--allow-empty', '-m', 'baseline')
            self.git(repo, 'branch', 'tc/pr-42')
            self.git(repo, 'push', 'origin', '--all')
            self.repos.append(repo)
        self.env['CUBRID_TESTCASES_DIR'] = str(self.repos[0])
        self.env['CUBRID_TESTCASES_PRIVATE_EX_DIR'] = str(self.repos[1])
        self.fake_bin = self.root / 'bin'
        self.fake_bin.mkdir()
        self.env['PATH'] = str(self.fake_bin) + os.pathsep + os.environ['PATH']
        for name in ('public', 'private'):
            (self.root / f'{name}-prs.json').write_text('[[]]')
        gh = self.fake_bin / 'gh'
        gh.write_text(f'''#!/usr/bin/env python3
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit
root = Path({str(self.root)!r})
with (root / 'gh-calls.jsonl').open('a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
assert sys.argv[1] == 'api'
endpoint = urlsplit(sys.argv[2])
assert endpoint.path in ('repos/CUBRID/cubrid-testcases/pulls',
                         'repos/CUBRID/cubrid-testcases-private-ex/pulls')
assert parse_qs(endpoint.query)['head'] == ['CUBRID:tc/pr-42']
assert sys.argv[3:] == ['--hostname', 'github.com', '--method', 'GET', '--paginate', '--slurp']
name = 'private' if '-private-ex/' in endpoint.path else 'public'
error = root / (name + '-error')
if error.exists():
    print(error.read_text(), file=sys.stderr)
    sys.exit(1)
print((root / (name + '-prs.json')).read_text())
''')
        gh.chmod(0o755)
        self.fake_gh(42, 'feature/oos-merge')

    def run_cmd(self, *args):
        return subprocess.run(args, env=self.env, text=True, capture_output=True, check=True).stdout.strip()

    def git(self, repo, *args):
        return self.run_cmd('git', '-C', str(repo), *args)

    def check(self, expected, *args, script=WRAPPER):
        before = [self.git(p, 'show-ref', '--heads') for p in self.repos]
        result = subprocess.run([str(script), *args], env=self.env, cwd=self.root,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(before, [self.git(p, 'show-ref', '--heads') for p in self.repos])
        return result.stdout + result.stderr

    def test_equal_and_tc_ahead(self):
        self.assertEqual(self.check(0, '--pr', '42').count('[common ancestor]'), 2)
        repo = self.repos[0]
        self.git(repo, 'checkout', 'tc/pr-42')
        self.git(repo, 'commit', '--allow-empty', '-m', 'TC addition')
        self.git(repo, 'push', 'origin', 'tc/pr-42')
        self.assertIn('TC-only=1, base-only=0', self.check(0, '--pr', '42'))

    def test_stale_diverged_merge_and_rebase(self):
        for repo in self.repos:
            self.git(repo, 'commit', '--allow-empty', '-m', 'new baseline')
            self.git(repo, 'push', 'origin', 'feature/oos-merge')
        self.assertIn('TC-only=0, base-only=1', self.check(1, '--pr', '42'))
        for repo in self.repos:
            self.git(repo, 'checkout', 'tc/pr-42')
            (repo / 'testcase').write_text('test\n')
            self.git(repo, 'add', 'testcase')
            self.git(repo, 'commit', '-m', 'TC change')
            self.git(repo, 'push', 'origin', 'tc/pr-42')
        self.assertIn('TC-only=1, base-only=1', self.check(1, '--pr', '42'))
        self.git(self.repos[0], 'merge', '--no-edit', 'feature/oos-merge')
        self.git(self.repos[1], 'rebase', 'feature/oos-merge')
        for repo in self.repos:
            self.git(repo, 'push', '--force', 'origin', 'tc/pr-42')
        self.assertEqual(self.check(0, '--pr', '42').count('PASS:'), 2)

    def test_deleted_branch_and_narrow_fetch(self):
        repo = self.repos[0]
        self.check(0, '--pr', '42')
        self.git(repo, 'config', 'remote.origin.fetch', '+refs/heads/feature/oos-merge:refs/remotes/origin/feature/oos-merge')
        self.git(repo, 'push', 'origin', '--delete', 'tc/pr-42')
        output = self.check(1, '--pr', '42')
        self.assertIn('missing published branch origin/tc/pr-42', output)
        self.assertIn('PASS:', output)

    def test_unrelated_and_fetch_error(self):
        repo = self.repos[0]
        self.git(repo, 'checkout', '--orphan', 'unrelated')
        self.git(repo, 'commit', '--allow-empty', '-m', 'other root')
        self.git(repo, 'push', '--force', 'origin', 'HEAD:tc/pr-42')
        self.assertIn('unrelated histories', self.check(1, '--pr', '42'))
        self.git(repo, 'remote', 'set-url', 'origin', str(self.root / 'absent'))
        self.assertIn('PASS:', self.check(2, '--pr', '42'))

    def fake_gh(self, number, base, url=None):
        url = url or f'https://github.com/CUBRID/cubrid/pull/{number}'
        payload = dict(number=number, url=url, baseRefName=base)
        (self.root / 'metadata.json').write_text(json.dumps(payload))
        resolver = self.fake_bin / 'gh-pr-info'
        resolver.write_text(f"#!/usr/bin/env python3\nfrom pathlib import Path\n"
                            f"print(Path({str(self.root / 'metadata.json')!r}).read_text())\n")
        resolver.chmod(0o755)

    def pr(self, number, name='public', state='open', draft=False,
           updated='2026-10-08T10:00:00Z', merged=None, head='tc/pr-42', owner=None):
        repository = 'CUBRID/cubrid-testcases' + ('-private-ex' if name == 'private' else '')
        return dict(number=number, html_url=f'https://github.com/{repository}/pull/{number}',
                    state=state, draft=draft, updated_at=updated, merged_at=merged,
                    head=dict(ref=head, repo=dict(full_name=owner or repository)))

    def set_prs(self, name, pages):
        (self.root / f'{name}-prs.json').write_text(json.dumps(pages))

    def test_pr_detection_and_validation(self):
        self.fake_gh(42, 'feature/oos-merge')
        self.assertIn('PR #42:', self.check(0))
        self.assertIn('PR #42:', self.check(0, script=SCRIPT))
        self.fake_gh(42, 'feature/oos-merge', 'https://github.com/other/repo/pull/42')
        self.assertIn('must belong to CUBRID', self.check(2))
        self.assertIn('positive integer', self.check(2, '--pr', '0'))
        self.assertIn('valid Git branch name', self.check(2, '--base', 'bad..branch', script=SCRIPT))

    def test_generic_base_detection(self):
        self.fake_gh(42, 'feature/other')
        self.assertIn('missing published branch origin/feature/other', self.check(1, script=SCRIPT))
        self.assertIn('targets feature/other, not feature/oos-merge', self.check(2))
        for repo in self.repos:
            self.git(repo, 'checkout', '-b', 'feature/other', 'feature/oos-merge')
            self.git(repo, 'commit', '--allow-empty', '-m', 'other baseline')
            self.git(repo, 'push', 'origin', 'feature/other')
        output = self.check(1, script=SCRIPT)
        self.assertIn('FAIL: latest feature/other tip is not an ancestor', output)
        self.assertIn('TC-only=0, base-only=1', output)
        self.fake_gh(42, 'develop')
        self.assertIn('missing published branch origin/develop', self.check(1, script=SCRIPT))
        self.assertIn('PASS:', self.check(0, '--pr', '42', '--base', 'feature/oos-merge', script=SCRIPT))

    def test_develop_advances_and_merge_or_rebase_restores_ancestry(self):
        for repo in self.repos:
            self.git(repo, 'branch', 'develop', 'feature/oos-merge')
            self.git(repo, 'push', 'origin', 'develop')
        self.fake_gh(42, 'develop')
        output = self.check(0, script=SCRIPT)
        self.assertIn('contains latest develop tip', output)
        self.assertNotIn('SKIP', output)
        for repo in self.repos:
            self.git(repo, 'checkout', 'tc/pr-42')
            (repo / 'testcase').write_text('develop TC change\n')
            self.git(repo, 'add', 'testcase')
            self.git(repo, 'commit', '-m', 'TC addition')
            self.git(repo, 'push', 'origin', 'tc/pr-42')
        self.assertIn('TC-only=1, base-only=0', self.check(0, script=SCRIPT))
        for repo in self.repos:
            self.git(repo, 'checkout', 'develop')
            self.git(repo, 'commit', '--allow-empty', '-m', 'develop advances')
            self.git(repo, 'push', 'origin', 'develop')
        output = self.check(1, script=SCRIPT)
        self.assertIn('Baseline ancestry check: FAIL', output)
        self.assertEqual(output.count('FAIL: latest develop tip is not an ancestor'), 2)
        self.assertIn('TC-only=1, base-only=1', output)
        for repo in self.repos:
            self.git(repo, 'checkout', 'tc/pr-42')
        self.git(self.repos[0], 'merge', '--no-edit', 'develop')
        self.git(self.repos[1], 'rebase', 'develop')
        for repo in self.repos:
            self.git(repo, 'push', '--force', 'origin', 'tc/pr-42')
        self.assertEqual(self.check(0, script=SCRIPT).count('PASS:'), 2)

    def test_generic_baseline_names_and_invalid_refs(self):
        for name in ('develop', 'release/11.4', 'topic/baseline'):
            for repo in self.repos:
                self.git(repo, 'branch', name, 'feature/oos-merge')
                self.git(repo, 'push', 'origin', name)
            self.assertIn(f'contains latest {name} tip', self.check(
                0, '--pr', '42', '--base', name, script=SCRIPT))
        for invalid in ('bad name', 'bad..name', '-bad', 'bad~name', 'HEAD', '@{-1}'):
            self.assertIn('valid Git branch name', self.check(
                2, '--pr', '42', f'--base={invalid}', script=SCRIPT))

    def test_open_pr_links_are_paginated_and_repository_scoped(self):
        self.set_prs('public', [
            [self.pr(9000, state='closed'), self.pr(901, owner='other/fork'),
             self.pr(902, head='tc/pr-99')],
            [self.pr(122), self.pr(123, draft=True), self.pr(122)],
        ])
        self.set_prs('private', [[self.pr(456, name='private')]])
        output = self.check(0, '--pr', '42')
        self.assertTrue(output.startswith('Baseline ancestry check: PASS'))
        self.assertIn('Public  CUBRID/cubrid-testcases', output)
        self.assertIn('Private  CUBRID/cubrid-testcases-private-ex', output)
        for number in (122, 123):
            self.assertIn(f'https://github.com/CUBRID/cubrid-testcases/pull/{number}', output)
        self.assertIn('https://github.com/CUBRID/cubrid-testcases-private-ex/pull/456', output)
        self.assertIn('OPEN (draft)', output)
        for number in (9000, 901, 902):
            self.assertNotIn(f'/pull/{number}', output)
        self.assertNotIn('/tree/', output)

    def test_historical_fallback_uses_update_time_not_pr_number(self):
        self.set_prs('public', [[self.pr(999, state='closed', updated='2026-10-01T10:00:00Z'),
                                 self.pr(200, state='closed', merged='2026-10-07T10:00:00Z')]])
        self.set_prs('private', [[self.pr(998, name='private', state='closed',
                                        updated='2026-10-01T10:00:00Z', merged='2026-10-01T10:00:00Z'),
                                  self.pr(201, name='private', state='closed')]])
        output = self.check(0, '--pr', '42')
        self.assertIn('/pull/200  MERGED', output)
        self.assertIn('/pull/201  CLOSED', output)
        self.assertNotIn('/pull/999', output)
        self.assertNotIn('/pull/998', output)

    def test_links_remain_available_on_missing_tc_branch(self):
        self.set_prs('public', [[self.pr(123)]])
        self.set_prs('private', [[self.pr(456, name='private')]])
        self.git(self.repos[0], 'push', 'origin', '--delete', 'tc/pr-42')
        output = self.check(1, '--pr', '42')
        self.assertIn('/pull/123', output)
        self.assertIn('/pull/456', output)
        self.assertIn('missing published branch origin/tc/pr-42', output)

    def test_lookup_errors_do_not_change_ancestry_exit_status(self):
        output = self.check(0, '--pr', '42')
        self.assertEqual(output.count('no matching testcase PR'), 2)
        self.set_prs('public', [[self.pr(123)]])
        (self.root / 'private-error').write_text('\033[31mgh: HTTP 403: authentication unavailable\033[0m')
        output = self.check(0, '--pr', '42')
        self.assertIn('/pull/123', output)
        self.assertIn('URL unavailable: gh: HTTP 403', output)
        self.assertNotIn('\033[', output)
        self.assertEqual(output.count('PASS:'), 2)
        self.git(self.repos[0], 'commit', '--allow-empty', '-m', 'baseline advances')
        self.git(self.repos[0], 'push', 'origin', 'feature/oos-merge')
        self.assertIn('URL unavailable', self.check(1, '--pr', '42'))
        self.git(self.repos[1], 'remote', 'set-url', 'origin', str(self.root / 'absent'))
        self.assertIn('Baseline ancestry check: ERROR', self.check(2, '--pr', '42'))

    def test_malformed_lookup_is_reported_without_invalid_urls(self):
        for payload in ('not JSON', '{}', '[[null]]'):
            (self.root / 'public-prs.json').write_text(payload)
            self.assertIn('URL unavailable:', self.check(0, '--pr', '42'))
        for field, value in (('html_url', 'https://other.example/pull/123'),
                             ('html_url', None), ('updated_at', None), ('number', True)):
            item = self.pr(123)
            item[field] = value
            self.set_prs('public', [[item]])
            output = self.check(0, '--pr', '42')
            self.assertIn('URL unavailable:', output)
            self.assertNotIn('https://other.example', output)

    def test_git_only_opt_out_never_invokes_gh_or_metadata_resolver(self):
        (self.fake_bin / 'gh-pr-info').write_text('#!/bin/sh\nexit 99\n')
        for repo in self.repos:
            self.git(repo, 'branch', 'develop', 'feature/oos-merge')
            self.git(repo, 'push', 'origin', 'develop')
        output = self.check(0, '--pr', '42', '--base', 'develop', '--no-pr-links', script=SCRIPT)
        self.assertEqual(output.count('lookup disabled (--no-pr-links)'), 2)
        self.assertFalse((self.root / 'gh-calls.jsonl').exists())

    def test_missing_gh_is_best_effort(self):
        (self.fake_bin / 'gh').unlink()
        for executable in ('python3', 'git'):
            (self.fake_bin / executable).symlink_to(shutil.which(executable))
        self.env['PATH'] = str(self.fake_bin)
        output = self.check(0, '--pr', '42', '--base', 'feature/oos-merge', script=SCRIPT)
        self.assertEqual(output.count('URL unavailable:'), 2)
        self.assertEqual(output.count('PASS:'), 2)

    def test_lookup_timeout_is_best_effort(self):
        checker = runpy.run_path(str(SCRIPT))
        namespace = checker['main'].__globals__
        real_command = namespace['command']

        def timed_command(*args, **kwargs):
            if args[0] == 'gh':
                raise subprocess.TimeoutExpired(args, 30)
            return real_command(*args, **kwargs)

        output = io.StringIO()
        with mock.patch.dict(namespace, command=timed_command), \
                mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(sys, 'argv', [str(SCRIPT), '--pr', '42', '--base', 'feature/oos-merge']), \
                mock.patch.object(sys, 'stdout', output):
            self.assertEqual(checker['main'](), 0)
        self.assertEqual(output.getvalue().count('URL unavailable:'), 2)

    def tty_check(self, *args):
        master, slave = pty.openpty()
        process = subprocess.Popen([str(WRAPPER), '--pr', '42', *args], env=self.env,
                                   stdout=slave, stderr=slave, cwd=self.root)
        os.close(slave)
        chunks = []
        try:
            while True:
                self.assertTrue(select.select([master], [], [], 20)[0], 'TTY command timed out')
                try:
                    chunk = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    break
                if not chunk:
                    break
                chunks.append(chunk)
            output = b''.join(chunks).decode()
            self.assertEqual(process.wait(timeout=5), 0, output)
            return output
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_color_auto_and_overrides_in_pipes_and_terminals(self):
        self.env['TERM'] = 'xterm-256color'
        self.env.pop('NO_COLOR', None)
        self.assertNotIn('\033[', self.check(0, '--pr', '42'))
        self.assertIn('\033[', self.check(0, '--pr', '42', '--color=always'))
        self.assertIn('\033[', self.tty_check())
        self.assertNotIn('\033[', self.tty_check('--color=never'))
        self.env['NO_COLOR'] = '1'
        self.assertNotIn('\033[', self.tty_check())
        self.assertIn('\033[', self.tty_check('--color=always'))
        self.env.pop('NO_COLOR')
        self.env['TERM'] = 'dumb'
        self.assertNotIn('\033[', self.tty_check())

    def test_shallow_history_is_error_and_other_repository_still_checked(self):
        for repo in self.repos:
            self.git(repo, 'checkout', 'tc/pr-42')
            self.git(repo, 'commit', '--allow-empty', '-m', 'TC addition')
            self.git(repo, 'push', 'origin', 'tc/pr-42')
            self.git(repo, 'checkout', 'feature/oos-merge')
            self.git(repo, 'merge', '--ff-only', 'tc/pr-42')
            self.git(repo, 'push', 'origin', 'feature/oos-merge')
        shallow = self.root / 'shallow'
        self.run_cmd('git', 'clone', '--depth=1', '--branch', 'feature/oos-merge',
                     (self.root / 'public.git').as_uri(), str(shallow))
        self.env['CUBRID_TESTCASES_DIR'] = str(shallow)
        output = self.check(2, '--pr', '42')
        self.assertIn('ERROR: shallow history', output)
        self.assertIn('Private: PASS', output)

if __name__ == '__main__':
    unittest.main()
