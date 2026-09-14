import json
import os
from pathlib import Path
import subprocess
import signal
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'bin/cubrid-pr-status'
HEAD = 'a' * 40
OLD = 'b' * 40
PREFIX = 'repos/CUBRID/cubrid'


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pr = dict(number=7939, title='Example PR', url='https://github.com/CUBRID/cubrid/pull/7939',
                       headRefOid=HEAD, state='OPEN', isDraft=False, reviewDecision='', mergeable='MERGEABLE')
        self.responses = {'pr': self.pr,
                          f'{PREFIX}/commits/{HEAD}/statuses?per_page=100': [[]],
                          f'{PREFIX}/commits/{HEAD}/check-runs?per_page=100': [{'check_runs': []}],
                          f'{PREFIX}/pulls/7939/commits?per_page=100': [[{'sha': OLD}, {'sha': HEAD}]],
                          f'{PREFIX}/commits/{OLD}/statuses?per_page=100': [[]],
                          f'{PREFIX}/commits/{OLD}/check-runs?per_page=100': [{'check_runs': []}]}
        fake = self.root / 'gh'
        fake.write_text('''#!/usr/bin/env python3
import json,os,sys
with open(os.environ['GH_FIXTURE']) as f: data=json.load(f)
key='pr' if sys.argv[1:3]==['pr','view'] else sys.argv[2]
value=data.get(key, {'error':'Unexpected request: '+repr(sys.argv)})
if isinstance(value,dict) and 'sequence' in value:
 from pathlib import Path
 counter=Path(os.environ['GH_FIXTURE']+'.counter')
 n=int(counter.read_text()) if counter.exists() else 0
 counter.write_text(str(n+1))
 value=value['sequence'][min(n,len(value['sequence'])-1)]
if isinstance(value,dict) and 'error' in value:
 print(value['error'],file=sys.stderr); sys.exit(1)
print(json.dumps(value))
''')
        fake.chmod(0o755)

    def run_cli(self, *args):
        fixture = self.root / 'fixture.json'
        fixture.write_text(json.dumps(self.responses))
        return subprocess.run([str(SCRIPT), '--history', '0', *args], cwd=self.root,
                              env={**os.environ, 'PATH': str(self.root)+os.pathsep+os.environ['PATH'],
                                   'GH_FIXTURE': str(fixture)}, text=True, capture_output=True, timeout=10)

    def status(self, name, state, url):
        return dict(context=name, state=state, target_url=url, updated_at='2026-09-14T10:00:00Z', id=1)

    def test_provider_results_and_expected_missing(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = [[
            self.status('gha-ci: test_shell', 'failure', 'https://github.com/example/run'),
            self.status('ci/circleci: test_shell', 'success', 'https://circleci.com/example/job')]]
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FAILURE', result.stdout)
        self.assertIn('SUCCESS', result.stdout)
        self.assertIn('gha-ci: test_shell', result.stdout)
        self.assertIn('ci/circleci: test_shell', result.stdout)
        self.assertIn('https://github.com/example/run', result.stdout)
        self.assertIn('https://circleci.com/example/job', result.stdout)
        self.assertIn('NOT OBSERVED', result.stdout)
        self.assertIn(HEAD[:12], result.stdout)

    def test_old_pending_is_stale_and_does_not_make_current_running(self):
        self.responses[f'{PREFIX}/commits/{OLD}/statuses?per_page=100'] = [[
            self.status('gha-ci: test_sql', 'pending', 'https://github.com/old/run')]]
        result = self.run_cli('--history', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('NOT OBSERVED   gha-ci: test_sql', result.stdout)
        self.assertIn('STALE previous: PENDING', result.stdout)
        self.assertIn(OLD[:12], result.stdout)
        self.assertIn('https://github.com/old/run', result.stdout)
        self.assertIn('History: searched 1', result.stdout)

    def test_paginated_rerun_and_workflow_revision_do_not_hide_current_pending(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/check-runs?per_page=100'] = [
            {'check_runs': [dict(name='license', app={'slug': 'github-actions'}, id=10,
                                status='completed', conclusion='success',
                                completed_at='2026-09-14T10:00:00Z', details_url='https://github.com/old')]},
            {'check_runs': [dict(name='license', app={'slug': 'github-actions'}, id=11,
                                status='queued', conclusion=None, started_at=None,
                                head_sha=OLD, details_url='https://github.com/new')]}]
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = [[], [
            self.status('gha-ci: test_sql', 'success', 'https://github.com/develop-workflow')]]
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('QUEUED         github-actions: license', result.stdout)
        self.assertIn('https://github.com/new', result.stdout)
        self.assertNotIn('https://github.com/old', result.stdout)
        self.assertIn('SUCCESS        gha-ci: test_sql | current '+HEAD[:12], result.stdout)

    def test_history_api_error_preserves_current_results_but_reports_incomplete(self):
        self.responses[f'{PREFIX}/commits/{OLD}/statuses?per_page=100'] = {'error': 'HTTP 403 rate limit'}
        result = self.run_cli('--history', '1')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('PR #7939', result.stdout)
        self.assertIn('INCOMPLETE', result.stdout)
        self.assertIn('403', result.stdout)

    def test_current_api_error_is_not_reported_as_missing(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = {'error': 'HTTP 401 authentication'}
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn('401', result.stderr)
        self.assertNotIn('NOT OBSERVED', result.stdout)

    def test_watch_refreshes_pr_head_and_stops_with_ctrl_c(self):
        newer = dict(self.pr, headRefOid=OLD)
        self.responses['pr'] = {'sequence': [self.pr, self.pr, newer, newer]}
        fixture = self.root / 'fixture.json'
        fixture.write_text(json.dumps(self.responses))
        output = self.root / 'watch.txt'
        with output.open('w') as stream:
            process = subprocess.Popen([str(SCRIPT), '--history', '0', '--watch', '--interval', '0.05'],
                                       cwd=self.root, stdout=stream, stderr=subprocess.PIPE, text=True,
                                       env={**os.environ, 'PATH': str(self.root)+os.pathsep+os.environ['PATH'],
                                            'GH_FIXTURE': str(fixture)})
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and process.poll() is None:
                    if 'PR head: '+OLD in output.read_text():
                        break
                    time.sleep(0.02)
                process.send_signal(signal.SIGINT) if process.poll() is None else None
                _, error = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, error)
                self.assertIn('PR head: '+HEAD, output.read_text())
                self.assertIn('PR head: '+OLD, output.read_text())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_changed_head_during_fetch_does_not_claim_current(self):
        self.responses['pr'] = {'sequence': [self.pr, dict(self.pr, headRefOid=OLD)]}
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn('head changed', result.stderr)
        self.assertNotIn('PR head:', result.stdout)

    def test_configuration_replaces_expected_jobs_but_keeps_discovery(self):
        config = self.root / 'config.json'
        config.write_text(json.dumps({'expected_checks': ['gha-ci: optional-suite']}))
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = [[
            self.status('ci/circleci: test_shell', 'success', 'https://circleci.com/job')]]
        result = self.run_cli('--config', str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('gha-ci: optional-suite', result.stdout)
        self.assertIn('ci/circleci: test_shell', result.stdout)
        self.assertNotIn('gha-ci: test_sql', result.stdout)

    def test_malformed_configuration_reports_error_without_traceback(self):
        config = self.root / 'bad-config.json'
        config.write_text('null')
        result = self.run_cli('--config', str(config))
        self.assertEqual(result.returncode, 2)
        self.assertIn('configuration', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_invalid_input_and_absent_pr_have_actionable_errors(self):
        for args in [('--history', '-1'), ('--interval', 'nan'),
                     ('https://github.com/another/repo/pull/123',)]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('Traceback', result.stderr)
        self.responses['pr'] = {'error': 'no pull requests found for branch example'}
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn('no pull requests found', result.stderr)

    def test_url_selection_works_outside_git_and_foreign_pr_is_rejected(self):
        result = self.run_cli(self.pr['url'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.pr['url'] = 'https://github.com/another/repo/pull/7939'
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn('CUBRID/cubrid PRs only', result.stderr)


if __name__ == '__main__':
    unittest.main()
