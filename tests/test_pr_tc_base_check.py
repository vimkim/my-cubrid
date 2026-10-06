#!/usr/bin/env python3
"""Integration checks using disposable local Git remotes; no network access."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

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
        fake_bin = self.root / 'bin'
        fake_bin.mkdir(exist_ok=True)
        gh = fake_bin / 'gh'
        url = url or f'https://github.com/CUBRID/cubrid/pull/{number}'
        payload = f'{{"number":{number},"url":"{url}","baseRefName":"{base}"}}'
        gh.write_text(f"#!/bin/sh\nprintf '%s\\n' '{payload}'\n")
        gh.chmod(0o755)
        resolver = fake_bin / 'gh-pr-info'
        resolver.write_text(gh.read_text())
        resolver.chmod(0o755)
        self.env['PATH'] = str(fake_bin) + os.pathsep + os.environ['PATH']

    def test_pr_detection_and_validation(self):
        self.fake_gh(42, 'feature/oos-merge')
        self.assertIn('PR #42:', self.check(0))
        self.assertIn('PR #42:', self.check(0, script=SCRIPT))
        self.fake_gh(42, 'feature/oos-merge', 'https://github.com/other/repo/pull/42')
        self.assertIn('must belong to CUBRID', self.check(2))
        self.assertIn('positive integer', self.check(2, '--pr', '0'))
        self.assertIn('feature/<name>', self.check(2, '--base', 'develop', script=SCRIPT))

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
        self.assertIn('SKIP', self.check(0, script=SCRIPT))
        self.assertIn('PASS:', self.check(0, '--pr', '42', '--base', 'feature/oos-merge', script=SCRIPT))

if __name__ == '__main__':
    unittest.main()
