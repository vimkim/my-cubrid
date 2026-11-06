#!/usr/bin/env python3
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WATCH = Path(__file__).resolve().parents[1] / 'bin/cubrid-ci-watch'
HEAD = 'a' * 40
BASE = 'https://github.com/CUBRID/cubrid'


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.fixture = self.root / 'fixture.json'
        fake = self.root / 'fake'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys, time
p = os.environ['FIXTURE']
data = json.load(open(p))
if data.get('sleep'): time.sleep(data['sleep'])
if data.get('bad'): print('bad json'); sys.exit(0)
if sys.argv[0].endswith('snapshot'): print(json.dumps(data['snapshot']))
elif '/jobs?' in sys.argv[-1]: print(json.dumps(data['jobs']))
else: print(json.dumps(data.get('runs', {}).get(sys.argv[-1].split('/')[-1], data['run'])))
''')
        fake.chmod(0o755)
        (self.root / 'snapshot').symlink_to(fake)
        (self.root / 'gh').symlink_to(fake)
        self.env = dict(os.environ, FIXTURE=str(self.fixture), CUBRID_CI_WATCH_SNAPSHOT=str(self.root / 'snapshot'), CUBRID_CI_WATCH_GH=str(self.root / 'gh'))
        self.when = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.write_fixture()

    def tearDown(self):
        self.tmp.cleanup()

    def write_fixture(self, states=None, run_attempt=1, head=HEAD, bad=False, sleep=0):
        states = states or {}
        current = (self.when - dt.timedelta(minutes=5)).isoformat()
        checks = []
        for name, state in states.items():
            checks.append({'name': 'gha-ci: ' + name, 'current': {'state': state, 'reported_for_sha': HEAD, 'detail_url': BASE + '/actions/runs/123', 'reported_at': current}})
        jobs = [{'name': name, 'started_at': (self.when - dt.timedelta(minutes=6)).isoformat(), 'completed_at': (self.when - dt.timedelta(minutes=4)).isoformat(), 'status': 'completed', 'conclusion': 'success'} for name in ('build status', 'status sql', 'status shell', 'status medium')]
        self.fixture.write_text(json.dumps({'bad': bad, 'sleep': sleep, 'snapshot': {'schema_version': 1, 'repository': 'CUBRID/cubrid', 'complete': True, 'errors': [], 'pr': {'number': 12, 'url': BASE + '/pull/12', 'head_sha': head}, 'checks': checks}, 'run': {'id': 123, 'run_attempt': run_attempt, 'path': '.github/workflows/gha-ci.yml', 'created_at': (self.when - dt.timedelta(minutes=9)).isoformat()}, 'jobs': [{'jobs': jobs}]}))

    def run_cli(self, *args, expected=0):
        proc = subprocess.run([str(WATCH), '--state-dir', str(self.state), *args], env=self.env, text=True, capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, expected, proc.stderr)
        return proc.stdout

    def register(self, hours=0, receipt='receipt', binding=True):
        args = ['register', '12', '--head', HEAD, '--suite', 'sql', '--triggered-at', (self.when - dt.timedelta(hours=hours, minutes=10)).isoformat(), '--receipt', receipt]
        if binding:
            args += ['--run-id', '123', '--attempt', '1']
        return json.loads(self.run_cli(*args))['request_id']

    def status(self):
        return json.loads(self.run_cli('status', '--json'))['requests']

    def events(self, after=0):
        return [json.loads(line) for line in self.run_cli('events', '--after', str(after)).splitlines()]

    def test_registration_idempotence_conflict_and_enrichment(self):
        self.assertEqual(self.register(binding=False), self.register(binding=True))
        self.assertEqual(self.register(), 1)
        args = ['register', '12', '--head', HEAD, '--suite', 'shell', '--triggered-at', (self.when - dt.timedelta(minutes=10)).isoformat(), '--receipt', 'receipt']
        self.run_cli(*args, expected=2)
        self.assertEqual([e['kind'] for e in self.events()], ['registered', 'binding'])

    def test_partial_failure_deduplicated_then_complete_and_replay(self):
        self.register()
        self.write_fixture({'build (debug)': 'FAILURE', 'test_sql': 'SUCCESS'})
        self.run_cli('poll', '--once')
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['phase'], 'active')
        self.assertEqual(sum(e['kind'] == 'failure' for e in self.events()), 1)
        cursor = self.events()[-1]['id']
        self.write_fixture({'build (debug)': 'FAILURE', 'build (release)': 'SUCCESS', 'test_sql': 'SUCCESS', 'test_shell': 'FAILURE'})
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['outcome'], 'failure')
        self.assertEqual([e['kind'] for e in self.events(cursor)], ['complete'])
        self.assertEqual(self.events(cursor), self.events(cursor))

    def test_poll_streams_committed_events_and_replays_after_output_loss(self):
        self.register()
        cursor = self.events()[-1]['id']
        states = {name: 'SUCCESS' for name in ('build (debug)', 'build (release)', 'test_sql')}
        self.write_fixture(states)
        streamed = [json.loads(line) for line in self.run_cli('poll', '--once').splitlines()]
        self.assertEqual([event['kind'] for event in streamed], ['complete'])
        self.assertEqual(streamed, self.events(cursor))
        self.assertEqual(self.run_cli('poll', '--once'), '')
        self.register(receipt='lost-output')
        with open(os.devnull, 'w') as sink:
            proc = subprocess.run([str(WATCH), '--state-dir', str(self.state), 'poll', '--once'],
                                  env=self.env, stdout=sink, stderr=subprocess.PIPE, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.status()[-1]['outcome'], 'success')
        self.assertEqual(self.events()[-1]['kind'], 'complete')

    def test_running_poller_discovers_registration_and_flushes_events(self):
        import select
        import time
        states = {name: 'SUCCESS' for name in ('build (debug)', 'build (release)', 'test_sql')}
        self.write_fixture(states)
        proc = subprocess.Popen([str(WATCH), '--state-dir', str(self.state), 'poll', '--interval', '1'],
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(.3)
            request = self.register()
            buffered = b''
            observed = []
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not any(event['kind'] == 'complete' for event in observed):
                ready, _, _ = select.select([proc.stdout], [], [], max(0, deadline - time.monotonic()))
                if not ready:
                    break
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                buffered += chunk
                while b'\n' in buffered:
                    line, buffered = buffered.split(b'\n', 1)
                    observed.append(json.loads(line))
            self.assertIsNone(proc.poll())
            completed = [event for event in observed if event['kind'] == 'complete']
            self.assertEqual(len(completed), 1)
            self.assertEqual(completed[0]['request_id'], request)
            self.assertIn(completed[0], self.events())
        finally:
            proc.terminate()
            proc.communicate(timeout=10)

    def test_unbound_candidate_old_status_and_recovery(self):
        self.register(binding=False)
        states = {name: 'SUCCESS' for name in ('build (debug)', 'build (release)', 'test_sql')}
        self.write_fixture(states)
        self.run_cli('poll', '--once')
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(sum(e['kind'] == 'pickup_candidate' for e in self.events()), 1)
        self.assertEqual(self.status()[0]['phase'], 'active')
        self.register()
        fixture = json.loads(self.fixture.read_text())
        fixture['jobs'][0]['jobs'] = []
        self.fixture.write_text(json.dumps(fixture))
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['phase'], 'active')
        self.write_fixture(bad=True)
        self.run_cli('poll', '--once', '--force', expected=2)
        self.assertTrue(self.status()[0]['last_error'])
        self.write_fixture(states)
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['outcome'], 'success')

    def test_deadline_final_success_and_api_error(self):
        self.register(hours=49, receipt='done')
        self.register(hours=49, receipt='gap')
        self.write_fixture({name: 'SUCCESS' for name in ('build (debug)', 'build (release)', 'test_sql')})
        self.run_cli('poll', '--once')
        self.assertEqual([r['outcome'] for r in self.status()], ['success', 'success'])
        self.register(hours=49, receipt='error')
        self.register(hours=49, receipt='error2')
        self.write_fixture(bad=True)
        self.run_cli('poll', '--once', expected=2)
        self.assertEqual([r['outcome'] for r in self.status()[-2:]], ['deadline', 'deadline'])
        self.assertEqual([e['kind'] for e in self.events() if e['request_id'] == 3][-2:], ['delay', 'deadline'])

    def test_delay_head_change_and_attempt_replacement(self):
        self.register(hours=25)
        self.write_fixture()
        self.run_cli('poll', '--once')
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(sum(e['kind'] == 'delay' for e in self.events()), 1)
        self.write_fixture(run_attempt=2)
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['outcome'], 'superseded')
        self.register(receipt='new')
        self.write_fixture(head='b' * 40)
        self.run_cli('poll', '--once')
        self.assertEqual(self.status()[-1]['outcome'], 'head_changed')

    def test_unknown_and_inherited_results_remain_unresolved(self):
        self.register()
        states = {'build (debug)': 'SUCCESS', 'build (release)': 'SUCCESS', 'test_sql': 'NEUTRAL'}
        self.write_fixture(states)
        self.run_cli('poll', '--once')
        self.assertEqual(self.status()[0]['phase'], 'active')
        fixture = json.loads(self.fixture.read_text())
        fixture['snapshot']['checks'][-1]['current']['state'] = 'SUCCESS'
        fixture['jobs'][0]['jobs'] = [j for j in fixture['jobs'][0]['jobs'] if j['name'] != 'status sql']
        self.fixture.write_text(json.dumps(fixture))
        self.run_cli('poll', '--once', '--force')
        result = self.status()[0]['observation']['contexts']['test_sql']
        self.assertFalse(result['attributed'])
        self.assertEqual(self.status()[0]['phase'], 'active')

    def test_pr_url_validation(self):
        args = ['--head', HEAD, '--suite', 'sql', '--triggered-at', self.when.isoformat(), '--receipt', 'url']
        self.run_cli('register', BASE + '/pull/12', *args)
        self.assertEqual(self.status()[0]['pr'], 12)
        for invalid in ('0', '-1', BASE + '/pull/12/', 'https://github.com/other/cubrid/pull/12', BASE + '/pull/12?x=1'):
            with self.subTest(invalid=invalid):
                self.run_cli('register', invalid, *args, expected=2)

    def test_newer_replacement_and_stale_other_run(self):
        self.register()
        states = {name: 'SUCCESS' for name in ('build (debug)', 'build (release)', 'test_sql')}
        self.write_fixture(states)
        fixture = json.loads(self.fixture.read_text())
        fixture['snapshot']['checks'][0]['current']['detail_url'] = BASE + '/actions/runs/124'
        older = dict(fixture['run'], id=124, created_at=(self.when - dt.timedelta(minutes=20)).isoformat())
        fixture['runs'] = {'124': older}
        self.fixture.write_text(json.dumps(fixture))
        self.run_cli('poll', '--once')
        previous = self.status()[0]['observation']
        self.assertEqual(self.status()[0]['phase'], 'active')
        self.assertNotIn('pickup_candidate', [e['kind'] for e in self.events()])
        fixture['runs']['124']['created_at'] = 'invalid'
        self.fixture.write_text(json.dumps(fixture))
        self.run_cli('poll', '--once', '--force', expected=2)
        self.assertEqual(self.status()[0]['observation'], previous)
        self.assertTrue(self.status()[0]['last_error'])
        fixture['runs']['124']['created_at'] = (self.when - dt.timedelta(minutes=8)).isoformat()
        self.fixture.write_text(json.dumps(fixture))
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['outcome'], 'superseded')
        self.assertEqual(self.status()[0]['observation'], previous)
        self.assertEqual(self.events()[-1]['payload']['run_id'], 124)

    def test_invalid_time_and_publisher_evidence(self):
        self.register()
        states = {name: 'SUCCESS' for name in ('build (debug)', 'build (release)', 'test_sql')}
        for case in ('old_run', 'future_end', 'bad_end', 'future_report', 'running_job', 'failed_publisher'):
            with self.subTest(case=case):
                self.write_fixture(states)
                f = json.loads(self.fixture.read_text())
                if case == 'old_run': f['run']['created_at'] = (self.when - dt.timedelta(minutes=11)).isoformat()
                if case == 'future_end': f['jobs'][0]['jobs'][0]['completed_at'] = (self.when + dt.timedelta(hours=1)).isoformat()
                if case == 'bad_end': f['jobs'][0]['jobs'][0]['completed_at'] = 'bad'
                if case == 'future_report': f['snapshot']['checks'][0]['current']['reported_at'] = (self.when + dt.timedelta(hours=1)).isoformat()
                if case == 'running_job': f['jobs'][0]['jobs'][0]['status'] = 'in_progress'
                if case == 'failed_publisher': f['jobs'][0]['jobs'][0]['conclusion'] = 'failure'
                self.fixture.write_text(json.dumps(f))
                self.run_cli('poll', '--once', '--force', expected=2 if case == 'old_run' else 0)
                self.assertEqual(self.status()[0]['phase'], 'active')
        self.write_fixture(states)
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['outcome'], 'success')

    def test_no_verdict_and_failure_precedence(self):
        for state, expected in [('ERROR', 'no_verdict'), ('CANCELLED', 'no_verdict'), ('FAILURE', 'failure')]:
            with self.subTest(state=state):
                self.register(receipt=state)
                self.write_fixture({'build (debug)': state, 'build (release)': 'SUCCESS', 'test_sql': 'ERROR'})
                self.run_cli('poll', '--once')
                self.assertEqual(self.status()[-1]['outcome'], expected)
                kinds = [e['kind'] for e in self.events() if e['request_id'] == self.status()[-1]['id']]
                self.assertIn('no_verdict', kinds)
                self.assertEqual('failure' in kinds, state == 'FAILURE')

    def test_failed_rerun_requires_selected_attempt_publication(self):
        args = ['register', '12', '--head', HEAD, '--suite', 'sql', '--triggered-at',
                (self.when - dt.timedelta(minutes=10)).isoformat(), '--receipt', 'rerun',
                '--kind', 'rerun-failed', '--run-id', '123', '--attempt', '2']
        self.run_cli(*args)
        states = {name: 'SUCCESS' for name in ('build (debug)', 'build (release)', 'test_sql')}
        self.write_fixture(states, run_attempt=2)
        f = json.loads(self.fixture.read_text())
        f['run']['created_at'] = (self.when - dt.timedelta(days=1)).isoformat()
        f['jobs'][0]['jobs'] = []
        self.fixture.write_text(json.dumps(f))
        self.run_cli('poll', '--once')
        self.assertEqual(self.status()[0]['phase'], 'active')
        self.write_fixture(states, run_attempt=2)
        f = json.loads(self.fixture.read_text())
        f['run']['created_at'] = (self.when - dt.timedelta(days=1)).isoformat()
        self.fixture.write_text(json.dumps(f))
        self.run_cli('poll', '--once', '--force')
        self.assertEqual(self.status()[0]['outcome'], 'success')

    def test_binding_during_collection_invalidates_observation(self):
        self.register(binding=False)
        self.write_fixture(sleep=2)
        proc = subprocess.Popen([str(WATCH), '--state-dir', str(self.state), 'poll', '--once'], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        import time
        time.sleep(.4)
        self.register()
        proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 0)
        row = self.status()[0]
        self.assertIsNone(row['observation'])
        self.assertEqual(row['run_id'], 123)

    def test_parallel_registration_and_poller_lock(self):
        args = [str(WATCH), '--state-dir', str(self.state), 'register', '12', '--head', HEAD, '--suite', 'sql', '--triggered-at', self.when.isoformat(), '--receipt', 'same']
        procs = [subprocess.Popen(args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
        for proc in procs:
            out, err = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 0, err)
            self.assertEqual(json.loads(out)['request_id'], 1)
        self.write_fixture(sleep=2)
        first = subprocess.Popen([str(WATCH), '--state-dir', str(self.state), 'poll', '--once'], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        import time
        time.sleep(.4)
        self.run_cli('poll', '--once', expected=2)
        self.register(receipt='while-polling')
        first.communicate(timeout=15)
        self.assertEqual(first.returncode, 0)


if __name__ == '__main__':
    unittest.main()
