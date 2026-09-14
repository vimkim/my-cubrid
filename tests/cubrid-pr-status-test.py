import json
import os
import errno
from pathlib import Path
import select
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

    def test_json_preserves_provider_freshness_and_history_without_prose(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = [[
            self.status('gha-ci: test_shell', 'failure', 'https://github.com/example/run'),
            self.status('ci/circleci: test_shell', 'success', 'https://circleci.com/example/job')]]
        self.responses[f'{PREFIX}/commits/{OLD}/statuses?per_page=100'] = [[
            self.status('gha-ci: test_sql', 'pending', 'https://github.com/old/run')]]
        result = self.run_cli('--json', '--history', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot['schema_version'], 1)
        self.assertTrue(snapshot['complete'])
        self.assertEqual(snapshot['pr']['head_sha'], HEAD)
        checks = {row['name']: row for row in snapshot['checks']}
        self.assertEqual(checks['gha-ci: test_shell']['provider'], 'GitHub Actions')
        self.assertEqual(checks['gha-ci: test_shell']['current']['state'], 'FAILURE')
        self.assertEqual(checks['ci/circleci: test_shell']['provider'], 'CircleCI')
        self.assertEqual(checks['ci/circleci: test_shell']['current']['state'], 'SUCCESS')
        missing = checks['gha-ci: test_sql']
        self.assertTrue(missing['expected'])
        self.assertEqual(missing['freshness'], 'not_observed')
        self.assertIsNone(missing['current'])
        self.assertEqual(missing['previous']['reported_for_sha'], OLD)
        self.assertEqual(missing['previous']['state'], 'PENDING')
        self.assertEqual(missing['previous']['detail_url'], 'https://github.com/old/run')
        self.assertEqual(missing['previous']['reported_at'], '2026-09-14T10:00:00Z')
        self.assertEqual(snapshot['history']['searched'], 1)
        self.assertFalse(snapshot['history']['truncated'])
        self.assertEqual(snapshot['errors'], [])
        self.assertNotIn('\x1b', result.stdout)

    def test_json_errors_are_structured_and_never_manufacture_missing_rows(self):
        bad_config = self.root / 'bad.json'
        bad_config.write_text('null')
        for args, stage in [(('--history', '-1'), 'arguments'),
                            (('--human',), 'arguments'),
                            (('--config', str(bad_config)), 'configuration')]:
            with self.subTest(args=args):
                result = self.run_cli('--json', *args)
                self.assertEqual(result.returncode, 2)
                data = json.loads(result.stdout)
                self.assertFalse(data['complete'])
                self.assertEqual(data['errors'][0]['stage'], stage)
                self.assertEqual(data['checks'], [])
                self.assertEqual(result.stderr, '')
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = {'error': 'HTTP 401 auth'}
        result = self.run_cli('--json')
        self.assertEqual(result.returncode, 2)
        data = json.loads(result.stdout)
        self.assertEqual(data['errors'][0]['stage'], 'current_checks')
        self.assertEqual(data['checks'], [])
        self.assertIn('401', data['errors'][0]['message'])

    def run_pty(self, *args, no_color=False, term='xterm-256color'):
        fixture = self.root / 'fixture.json'
        fixture.write_text(json.dumps(self.responses))
        env = {k: v for k, v in os.environ.items() if k != 'NO_COLOR'}
        env.update(PATH=str(self.root)+os.pathsep+os.environ['PATH'], GH_FIXTURE=str(fixture), TERM=term)
        if no_color:
            env['NO_COLOR'] = '1'
        master, slave = os.openpty()
        process = subprocess.Popen([str(SCRIPT), '--history', '0', *args], cwd=self.root,
                                   stdout=slave, stderr=subprocess.PIPE, env=env)
        os.close(slave)
        chunks = []
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
            _, error = process.communicate(timeout=2)
            self.assertEqual(process.returncode, 0, error)
            return b''.join(chunks).decode()
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_human_has_ascii_layout_color_in_terminal_and_plain_redirects(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = [[
            self.status('gha-ci: test_shell', 'failure', 'https://github.com/run'),
            self.status('ci/circleci: test_shell', 'success', 'https://circleci.com/job')]]
        human = self.run_pty('--human')
        self.assertIn('\x1b[31m', human)
        self.assertIn('\x1b[32m', human)
        self.assertIn('+---', human)
        self.assertIn('[!]', human)
        self.assertIn('https://github.com/run', human)
        plain = self.run_cli('--human')
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertNotIn('\x1b', plain.stdout)
        self.assertIn('+---', plain.stdout)
        self.assertNotIn('\x1b', self.run_pty('--human', no_color=True))
        self.assertNotIn('\x1b', self.run_pty('--human', term='dumb'))
        self.assertNotIn('\x1b', self.run_pty('--json'))

    def test_human_aligns_long_names_and_long_status_labels(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/check-runs?per_page=100'] = [
            {'check_runs': [dict(name='x' * 70, app={'slug': 'github-actions'}, id=10,
                                status='completed', conclusion='action_required',
                                details_url='https://github.com/job')]}]
        result = self.run_cli('--human')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line for line in result.stdout.splitlines()
                 if '| current' in line and ('github-actions:' in line or 'gha-ci:' in line)]
        self.assertGreater(len(lines), 2)
        self.assertEqual(len({line.index('| current') for line in lines}), 1)
        self.assertIn('x' * 70, result.stdout)

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
        self.assertRegex(result.stdout, r'SUCCESS\s+gha-ci: test_sql\s+\| current '+HEAD[:12])

    def test_history_api_error_preserves_current_results_but_reports_incomplete(self):
        self.responses[f'{PREFIX}/commits/{OLD}/statuses?per_page=100'] = {'error': 'HTTP 403 rate limit'}
        result = self.run_cli('--history', '1')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('PR #7939', result.stdout)
        self.assertIn('INCOMPLETE', result.stdout)
        self.assertIn('403', result.stdout)

    def test_json_partial_history_keeps_current_but_head_race_discards_results(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = [[
            self.status('gha-ci: test_shell', 'success', 'https://github.com/run')]]
        self.responses[f'{PREFIX}/commits/{OLD}/statuses?per_page=100'] = {'error': 'HTTP 403 rate limit'}
        result = self.run_cli('--json', '--history', '1')
        self.assertEqual(result.returncode, 2)
        data = json.loads(result.stdout)
        self.assertFalse(data['complete'])
        self.assertEqual(data['history']['status'], 'incomplete')
        self.assertIsNone(data['history']['searched'])
        self.assertEqual(data['errors'][0]['stage'], 'history')
        shell = next(row for row in data['checks'] if row['name'] == 'gha-ci: test_shell')
        self.assertEqual(shell['current']['reported_for_sha'], HEAD)
        self.assertEqual(shell['current']['state'], 'SUCCESS')
        self.responses['pr'] = {'sequence': [self.pr, dict(self.pr, headRefOid=OLD)]}
        result = self.run_cli('--json')
        self.assertEqual(result.returncode, 2)
        data = json.loads(result.stdout)
        self.assertEqual(data['errors'][0]['stage'], 'head_check')
        self.assertEqual(data['checks'], [])

    def test_current_api_error_is_not_reported_as_missing(self):
        self.responses[f'{PREFIX}/commits/{HEAD}/statuses?per_page=100'] = {'error': 'HTTP 401 authentication'}
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn('401', result.stderr)
        self.assertNotIn('NOT OBSERVED', result.stdout)

    def test_watch_refreshes_pr_head_and_stops_with_ctrl_c(self):
        newer = dict(self.pr, headRefOid=OLD)
        self.responses['pr'] = {'sequence': [self.pr, self.pr, newer, newer]}
        output, error = self.run_watch(lambda text: 'PR head: '+OLD in text)
        self.assertEqual(error, '')
        self.assertIn('PR head: '+HEAD, output)
        self.assertIn('PR head: '+OLD, output)

    def test_json_watch_emits_complete_lines_recovers_from_error_and_refreshes_head(self):
        newer = dict(self.pr, headRefOid=OLD)
        self.responses['pr'] = {'sequence': [{'error': 'HTTP 503 temporary'}, self.pr, self.pr, newer, newer]}
        output, error = self.run_watch(lambda text: '"head_sha": "'+OLD+'"' in text, '--json')
        self.assertEqual(error, '')
        events = [json.loads(line) for line in output.splitlines()]
        self.assertGreaterEqual(len(events), 3)
        self.assertFalse(events[0]['complete'])
        self.assertEqual(events[0]['errors'][0]['stage'], 'pr')
        self.assertEqual(events[1]['pr']['head_sha'], HEAD)
        self.assertTrue(events[1]['complete'])
        self.assertEqual(events[2]['pr']['head_sha'], OLD)
        self.assertNotIn('\x1b', output)

    def run_watch(self, finished, *args):
        fixture = self.root / 'fixture.json'
        fixture.write_text(json.dumps(self.responses))
        output = self.root / 'watch.txt'
        with output.open('w') as stream:
            process = subprocess.Popen([str(SCRIPT), '--history', '0', '--watch', '--interval', '0.1', *args],
                                       cwd=self.root, stdout=stream, stderr=subprocess.PIPE, text=True,
                                       env={**os.environ, 'PATH': str(self.root)+os.pathsep+os.environ['PATH'],
                                            'GH_FIXTURE': str(fixture)})
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and process.poll() is None:
                    if finished(output.read_text()):
                        break
                    time.sleep(0.02)
                process.send_signal(signal.SIGINT) if process.poll() is None else None
                _, error = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, error)
                return output.read_text(), error
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
