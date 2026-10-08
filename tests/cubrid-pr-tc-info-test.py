import errno
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import unittest
from urllib.parse import quote, urlencode

SCRIPT = Path(__file__).resolve().parents[1] / 'bin/cubrid-pr-tc-info'
URL = 'https://github.com/CUBRID/cubrid/pull/7927'
PUBLIC = 'CUBRID/cubrid-testcases'
PRIVATE = 'CUBRID/cubrid-testcases-private-ex'
HEAD, PUBLIC_TC, PUBLIC_BASE, PRIVATE_TC, PRIVATE_BASE = [char * 40 for char in '9abcd']
BRANCH = 'tc/pr-7927'
BASE = 'feature/oos-merge'


def ref_path(repository, branch):
    return f'repos/{repository}/git/ref/heads/{quote(branch, safe="")}'


def ref(branch, sha):
    return dict(ref=f'refs/heads/{branch}', object=dict(type='commit', sha=sha))


def pulls_path(repository):
    query = urlencode(dict(state='all', head=f'CUBRID:{BRANCH}', per_page=100))
    return f'repos/{repository}/pulls?{query}'


def pull(repository, number, state='open', merged=False, base=BASE):
    return dict(number=number, html_url=f'https://github.com/{repository}/pull/{number}',
                state=state, draft=state == 'open', merged_at='2026-10-08T00:00:00Z' if merged else None,
                head=dict(ref=BRANCH, sha=PUBLIC_TC if repository == PUBLIC else PRIVATE_TC,
                          repo=dict(full_name=repository)), base=dict(ref=base))


class CliTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = self.root / 'fixture.json'
        self.log = self.root / 'calls.jsonl'
        self.pr = dict(number=7927, title='Deferred OOS writes', url=URL, state='OPEN',
                       headRefName='feat/oos-deferred-write', headRefOid=HEAD, baseRefName=BASE)
        self.responses: dict = {'pr': self.pr}
        for repository, tc_sha, base_sha, number in (
                (PUBLIC, PUBLIC_TC, PUBLIC_BASE, 3664),
                (PRIVATE, PRIVATE_TC, PRIVATE_BASE, 4335)):
            self.responses[f'repos/{repository}'] = dict(full_name=repository, permissions=dict(pull=True))
            self.responses[ref_path(repository, BRANCH)] = ref(BRANCH, tc_sha)
            self.responses[ref_path(repository, BASE)] = ref(BASE, base_sha)
            self.responses[pulls_path(repository)] = [[pull(repository, number),
                                                       pull(repository, number - 100, 'closed')]]
            self.responses[f'repos/{repository}/compare/{base_sha}...{tc_sha}'] = dict(
                status='ahead', ahead_by=2, behind_by=0,
                base_commit=dict(sha=base_sha), merge_base_commit=dict(sha=base_sha))
        fake = self.root / 'gh'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['TC_INFO_CALLS'], 'a') as log:
    log.write(json.dumps(dict(executable=name, args=args, cwd=os.getcwd())) + '\\n')
with open(os.environ['TC_INFO_FIXTURE']) as fixture:
    responses = json.load(fixture)
if name == 'gh-pr-info':
    key = 'pr'
elif args[0] == 'api' and args[args.index('--method') + 1] == 'GET':
    key = args[1]
else:
    print('Only read-only API requests are permitted in this test', file=sys.stderr)
    sys.exit(1)
value = responses.get(key, dict(error='Unexpected request: ' + repr(args)))
if isinstance(value, dict) and 'sequence' in value:
    counter = Path(os.environ['TC_INFO_FIXTURE'] + '.counter')
    count = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(count + 1))
    value = value['sequence'][min(count, len(value['sequence']) - 1)]
if isinstance(value, dict) and 'error' in value:
    print(value['error'], file=sys.stderr)
    sys.exit(1)
if isinstance(value, dict) and 'raw' in value:
    print(value['raw'])
else:
    print(json.dumps(value))
''')
        fake.chmod(0o755)
        (self.root / 'gh-pr-info').symlink_to(fake)
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'],
                        TC_INFO_FIXTURE=str(self.fixture), TC_INFO_CALLS=str(self.log),
                        TERM='xterm', NO_COLOR='')

    def prepare(self):
        self.fixture.write_text(json.dumps(self.responses))
        self.log.unlink(missing_ok=True)
        Path(str(self.fixture) + '.counter').unlink(missing_ok=True)

    def run_cli(self, *args, json_mode=True, env=None):
        self.prepare()
        return subprocess.run([str(SCRIPT), *(['--json'] if json_mode else []), *args],
                              cwd=self.root, env=env or self.env, capture_output=True,
                              text=True, timeout=20)

    def data(self, result, code=0):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertNotIn('\x1b', result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual(value['schema_version'], 1)
        self.assertEqual(value['complete'], code == 0)
        return value

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def run_tty(self, *args, env=None):
        self.prepare()
        master, slave = pty.openpty()
        process = subprocess.Popen([str(SCRIPT), *args], cwd=self.root, env=env or self.env,
                                   stdout=slave, stderr=subprocess.PIPE)
        os.close(slave)
        output = bytearray()
        try:
            while True:
                ready, _, _ = select.select([master], [], [], 10)
                if not ready:
                    self.fail('CLI did not finish writing to its terminal')
                try:
                    chunk = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output.extend(chunk)
            _, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stderr, b'')
            return output.decode()
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_explicit_url_from_outside_git_checkout(self):
        data = self.data(self.run_cli(URL + '/'))
        self.assertEqual(data['pr']['url'], URL)
        self.assertEqual(data['pr']['base_branch'], BASE)
        self.assertEqual(data['errors'], [])
        public, private = data['repositories']
        self.assertEqual((public['visibility'], private['visibility']), ('public', 'private'))
        self.assertEqual(public['branch']['name'], BRANCH)
        self.assertEqual(public['branch']['sha'], PUBLIC_TC)
        self.assertEqual(private['branch']['sha'], PRIVATE_TC)
        self.assertEqual(public['tc_prs'][0]['url'], 'https://github.com/CUBRID/cubrid-testcases/pull/3664')
        self.assertEqual(private['tc_prs'][0]['url'], 'https://github.com/CUBRID/cubrid-testcases-private-ex/pull/4335')
        self.assertTrue(public['baseline']['comparison']['contains_baseline'])
        self.assertEqual(public['baseline']['sha'], PUBLIC_BASE)
        resolver_calls = [call for call in self.calls() if call['executable'] == 'gh-pr-info']
        self.assertEqual(resolver_calls[0]['args'][0], URL)
        self.assertEqual(resolver_calls[0]['cwd'], str(self.root))
        self.assertIn('--repo', resolver_calls[0]['args'])
        self.assertIn('CUBRID/cubrid', resolver_calls[0]['args'])

    def test_no_arguments_use_current_worktree_resolver(self):
        data = self.data(self.run_cli())
        self.assertEqual(data['pr']['number'], 7927)
        resolver_calls = [call for call in self.calls() if call['executable'] == 'gh-pr-info']
        self.assertEqual(resolver_calls[0]['args'][0], '--repo')
        self.assertEqual(resolver_calls[1]['args'][0], URL)

    def test_missing_baseline_updates_are_informational(self):
        self.responses[f'repos/{PUBLIC}/compare/{PUBLIC_BASE}...{PUBLIC_TC}'].update(
            status='diverged', ahead_by=2, behind_by=3, merge_base_commit=dict(sha='f' * 40))
        self.responses[f'repos/{PRIVATE}/compare/{PRIVATE_BASE}...{PRIVATE_TC}'].update(
            status='behind', ahead_by=0, behind_by=1, merge_base_commit=dict(sha=PRIVATE_TC))
        data = self.data(self.run_cli(URL))
        self.assertFalse(data['repositories'][0]['baseline']['comparison']['contains_baseline'])
        self.assertEqual(data['repositories'][0]['baseline']['comparison']['baseline_only'], 3)
        self.assertFalse(data['repositories'][1]['baseline']['comparison']['contains_baseline'])
        human = self.run_cli(URL, json_mode=False)
        self.assertEqual(human.returncode, 0)
        self.assertIn('OUTDATED: baseline updates missing', human.stdout)

    def test_identical_baseline_is_current(self):
        self.responses[ref_path(PUBLIC, BASE)] = ref(BASE, PUBLIC_TC)
        self.responses[f'repos/{PUBLIC}/compare/{PUBLIC_TC}...{PUBLIC_TC}'] = dict(
            status='identical', ahead_by=0, behind_by=0,
            base_commit=dict(sha=PUBLIC_TC), merge_base_commit=dict(sha=PUBLIC_TC))
        public = self.data(self.run_cli(URL))['repositories'][0]
        self.assertTrue(public['baseline']['comparison']['contains_baseline'])
        self.assertEqual(public['baseline']['comparison']['tc_only'], 0)

    def test_explicit_fallback_is_resolved_independently_per_repository(self):
        self.responses[ref_path(PUBLIC, BASE)] = dict(error='gh: Not Found (HTTP 404)')
        self.responses[ref_path(PUBLIC, 'develop')] = ref('develop', PUBLIC_BASE)
        data = self.data(self.run_cli(URL))
        public, private = data['repositories']
        self.assertTrue(public['baseline']['fallback'])
        self.assertEqual(public['baseline']['name'], 'develop')
        self.assertEqual(public['baseline']['requested_branch'], BASE)
        self.assertEqual(public['baseline']['sha'], PUBLIC_BASE)
        self.assertFalse(private['baseline']['fallback'])
        human = self.run_cli(URL, json_mode=False)
        self.assertIn('develop fallback: feature/oos-merge is absent', human.stdout)
        self.assertIn('TC PR target: feature/oos-merge (differs from baseline)', human.stdout)

    def test_develop_baseline_is_inspected_instead_of_skipped(self):
        self.pr['baseRefName'] = 'develop'
        for repository, base_sha in ((PUBLIC, PUBLIC_BASE), (PRIVATE, PRIVATE_BASE)):
            self.responses[ref_path(repository, 'develop')] = ref('develop', base_sha)
        data = self.data(self.run_cli(URL))
        for row in data['repositories']:
            self.assertEqual(row['baseline']['name'], 'develop')
            self.assertFalse(row['baseline']['fallback'])
            self.assertTrue(row['baseline']['comparison']['contains_baseline'])

    def test_paginated_history_prefers_all_open_matches(self):
        self.responses[pulls_path(PUBLIC)] = [[pull(PUBLIC, 4000, 'closed'), pull(PUBLIC, 3664)],
                                              [pull(PUBLIC, 3600), pull(PUBLIC, 3555, 'closed')]]
        data = self.data(self.run_cli(URL))
        self.assertEqual([item['number'] for item in data['repositories'][0]['tc_prs']], [3664, 3600])
        call = next(call for call in self.calls() if pulls_path(PUBLIC) in call['args'])
        self.assertIn('--paginate', call['args'])
        self.assertIn('--slurp', call['args'])

    def test_latest_historical_pr_keeps_merged_state(self):
        self.responses[pulls_path(PUBLIC)] = [[pull(PUBLIC, 3555, 'closed')],
                                              [pull(PUBLIC, 3664, 'closed', merged=True)]]
        data = self.data(self.run_cli(URL))
        self.assertEqual(len(data['repositories'][0]['tc_prs']), 1)
        self.assertEqual(data['repositories'][0]['tc_prs'][0]['number'], 3664)
        self.assertEqual(data['repositories'][0]['tc_prs'][0]['state'], 'MERGED')
        human = self.run_cli(URL, json_mode=False)
        self.assertIn('MERGED', human.stdout)

    def test_no_tc_pr_is_distinct_from_lookup_failure(self):
        self.responses[pulls_path(PUBLIC)] = [[]]
        data = self.data(self.run_cli(URL))
        self.assertEqual(data['repositories'][0]['tc_prs'], [])
        self.assertIn('TC PR      NONE', self.run_cli(URL, json_mode=False).stdout)

    def test_missing_tc_branch_is_a_complete_snapshot(self):
        self.responses[ref_path(PUBLIC, BRANCH)] = dict(error='gh: Not Found (HTTP 404)')
        data = self.data(self.run_cli(URL))
        public = data['repositories'][0]
        self.assertEqual(public['branch']['status'], 'missing')
        self.assertIsNone(public['branch']['sha'])
        self.assertIsNone(public['baseline']['comparison'])
        self.assertFalse(any(f'repos/{PUBLIC}/compare/' in call['args'][1]
                             for call in self.calls() if call['executable'] == 'gh'))

    def test_missing_fallback_baseline_remains_visible(self):
        for branch in (BASE, 'develop'):
            self.responses[ref_path(PUBLIC, branch)] = dict(error='gh: Not Found (HTTP 404)')
        public = self.data(self.run_cli(URL))['repositories'][0]
        self.assertEqual(public['baseline']['status'], 'missing')
        self.assertTrue(public['baseline']['fallback'])
        self.assertIsNone(public['baseline']['comparison'])

    def test_private_repository_access_failure_is_not_a_missing_branch(self):
        self.responses[f'repos/{PRIVATE}'] = dict(error='gh: Not Found (HTTP 404)')
        data = self.data(self.run_cli(URL), 2)
        public, private = data['repositories']
        self.assertTrue(public['complete'])
        self.assertEqual(public['branch']['sha'], PUBLIC_TC)
        self.assertFalse(private['complete'])
        self.assertEqual(private['branch']['status'], 'unknown')
        self.assertEqual(private['baseline']['status'], 'unknown')
        self.assertFalse(private['baseline']['fallback'])
        self.assertEqual(data['errors'][0]['stage'], 'repository')
        calls = [call['args'][1] for call in self.calls() if call['executable'] == 'gh']
        self.assertEqual([path for path in calls if PRIVATE in path], [f'repos/{PRIVATE}'])

    def test_branch_and_pr_errors_preserve_other_information(self):
        self.responses[ref_path(PUBLIC, BRANCH)] = dict(error='gh: Forbidden (HTTP 403)')
        self.responses[pulls_path(PRIVATE)] = dict(error='gh: Bad Gateway (HTTP 502)')
        data = self.data(self.run_cli(URL), 2)
        public, private = data['repositories']
        self.assertEqual(public['branch']['status'], 'unknown')
        self.assertEqual(public['baseline']['sha'], PUBLIC_BASE)
        self.assertEqual(public['tc_prs'][0]['number'], 3664)
        self.assertEqual(private['branch']['sha'], PRIVATE_TC)
        self.assertTrue(private['baseline']['comparison']['contains_baseline'])
        self.assertEqual({item['stage'] for item in data['errors']}, {'branch', 'tc_prs'})
        human = self.run_cli(URL, json_mode=False)
        self.assertEqual(human.returncode, 2)
        self.assertIn('INCOMPLETE', human.stdout)
        self.assertIn('TC PR      UNAVAILABLE', human.stdout)

    def test_compare_error_does_not_discard_branch_tips(self):
        path = f'repos/{PUBLIC}/compare/{PUBLIC_BASE}...{PUBLIC_TC}'
        self.responses[path] = dict(error='gh: Not Found (HTTP 404)')
        public = self.data(self.run_cli(URL), 2)['repositories'][0]
        self.assertEqual(public['branch']['sha'], PUBLIC_TC)
        self.assertEqual(public['baseline']['sha'], PUBLIC_BASE)
        self.assertIsNone(public['baseline']['comparison'])
        self.assertEqual(public['errors'][0]['stage'], 'comparison')

    def test_comparison_must_use_observed_baseline_sha(self):
        self.responses[f'repos/{PUBLIC}/compare/{PUBLIC_BASE}...{PUBLIC_TC}']['base_commit']['sha'] = 'f' * 40
        data = self.data(self.run_cli(URL), 2)
        self.assertEqual(data['errors'][0]['stage'], 'comparison')
        self.assertIn('requested baseline SHA', data['errors'][0]['message'])

    def test_malformed_repository_identity_is_an_error(self):
        self.responses[f'repos/{PRIVATE}']['full_name'] = None
        data = self.data(self.run_cli(URL), 2)
        self.assertEqual(data['repositories'][1]['branch']['status'], 'unknown')
        self.assertEqual(data['errors'][0]['stage'], 'repository')

    def test_malformed_response_is_an_incomplete_snapshot(self):
        self.responses[ref_path(PUBLIC, BRANCH)] = dict(raw='not JSON')
        data = self.data(self.run_cli(URL), 2)
        self.assertEqual(data['errors'][0]['stage'], 'branch')
        self.assertIn('invalid JSON', data['errors'][0]['message'])
        self.assertTrue(data['repositories'][1]['complete'])

    def test_pr_resolution_failure_has_structured_json(self):
        self.responses['pr'] = dict(error='No PR associated with the current branch')
        data = self.data(self.run_cli(), 2)
        self.assertIsNone(data['pr'])
        self.assertEqual(data['repositories'], [])
        self.assertEqual(data['errors'][0]['stage'], 'pr')

    def test_argument_errors_are_json_when_requested(self):
        for args in (('--wat',), ('--human',), ('7927',),
                     ('https://github.com/other/repo/pull/7927',),
                     ('https://github.com/CUBRID/cubrid/pull/0',)):
            with self.subTest(args=args):
                data = self.data(self.run_cli(*args), 2)
                self.assertIsNone(data['pr'])
                self.assertEqual(data['errors'][0]['stage'], 'arguments')

    def test_wrong_resolved_repository_is_rejected(self):
        self.pr['url'] = 'https://github.com/vimkim/cubrid/pull/7927'
        data = self.data(self.run_cli(URL), 2)
        self.assertIsNone(data['pr'])
        self.assertIn('must belong to CUBRID/cubrid', data['errors'][0]['message'])

    def test_changing_pr_base_rejects_snapshot_but_keeps_rows(self):
        changed = dict(self.pr, baseRefName='develop')
        self.responses['pr'] = dict(sequence=[self.pr, changed])
        data = self.data(self.run_cli(URL), 2)
        self.assertEqual(data['errors'][0]['stage'], 'pr_check')
        self.assertEqual(len(data['repositories']), 2)
        self.assertIn('changed during lookup', data['errors'][0]['message'])

    def test_human_terminal_colors_and_plain_redirected_output(self):
        plain = self.run_cli(URL, json_mode=False)
        self.assertEqual(plain.returncode, 0)
        self.assertNotIn('\x1b', plain.stdout)
        for expected in ('PUBLIC  CUBRID/cubrid-testcases', 'PRIVATE  CUBRID/cubrid-testcases-private-ex',
                         'tc/pr-7927', PUBLIC_TC[:12], PRIVATE_TC[:12], 'feature/oos-merge',
                         'includes latest baseline', '/pull/3664', '/pull/4335'):
            self.assertIn(expected, plain.stdout)
        terminal = self.run_tty(URL)
        self.assertIn('\x1b[1;36mPUBLIC', terminal)
        self.assertIn('\x1b[32mCURRENT', terminal)
        self.assertNotIn('\x1b', self.run_tty(URL, env=dict(self.env, NO_COLOR='1')))
        self.assertNotIn('\x1b', self.run_tty(URL, env=dict(self.env, TERM='dumb')))

    def test_json_on_terminal_has_no_colors(self):
        output = self.run_tty('--json', URL)
        self.assertNotIn('\x1b', output)
        self.assertTrue(json.loads(output)['complete'])


if __name__ == '__main__':
    unittest.main()
