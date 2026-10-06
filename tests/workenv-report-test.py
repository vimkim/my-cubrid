#!/usr/bin/env python3
"""Reporting remains usable across incomplete and damaged worktrees."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'bin/cubrid-workenv-report.py'
spec = importlib.util.spec_from_file_location('report', SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class Reports(unittest.TestCase):
    def test_state_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.assertIsNone(report.snapshot(root)['error'])
            folder = root / '.cub-workenv'
            folder.mkdir()
            self.assertIn('without', report.snapshot(root)['error'])
            marker = folder / 'state.json'
            for value in ['{', '[]', '{"schema": 99}']:
                marker.write_text(value)
                self.assertIsNotNone(report.snapshot(root)['error'])
            state = dict(schema=1, status='preparing', worktree=str(root), stage='allocation')
            marker.write_text(json.dumps(state))
            self.assertEqual(report.snapshot(root)['state'], state)
            state['worktree'] = '/different'
            marker.write_text(json.dumps(state))
            self.assertIn('different', report.snapshot(root)['error'])
            self.assertEqual(report.shm(1644167168), '0x62000000 (1644167168)')

    def test_isolation_reports_named_environment_settings_and_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / '.cub-workenv'
            (folder / 'conf').mkdir(parents=True)
            (folder / 'databases').mkdir()
            (folder / 'conf/cubrid.conf').write_text('[common]\ncubrid_port_id=41000\nstored_procedure_uds=yes\nha_mode=off\n')
            (folder / 'conf/cubrid_broker.conf').write_text('[broker]\nMASTER_SHM_ID=0x62000000\n[%workenv]\nBROKER_PORT=41001\nAPPL_SERVER_SHM_ID=0x62000001\n')
            (folder / 'databases/databases.txt').write_text('testdb /data localhost /log file:/lob\n')
            state = dict(schema=1, status='ready', worktree=str(root), install='/install',
                         allocation={'tmp': '/tmp/instance', 'master_port': 41000})
            (folder / 'state.json').write_text(json.dumps(state))
            record = report.snapshot(root)
            self.assertIsNone(record['error'])
            info = record['isolation']
            self.assertEqual(info['expected_environment']['CUBRID_TMP'], '/tmp/instance')
            self.assertEqual(info['expected_environment']['CUBRID_CUBRID_PORT_ID'], '41000')
            self.assertEqual(info['master_socket'], '/tmp/instance/CUBRID41000')
            self.assertEqual(info['databases'][0]['pl_socket'], '/tmp/instance/sp_testdb.sock')
            self.assertEqual(info['databases'][0]['pl_info'], '/install/var/pl/pl_testdb.info')
            self.assertEqual(info['databases'][0]['lob'], 'file:/lob')
            self.assertEqual(info['disk_settings']['CUBRID_BROKER_CONF_FILE']['%workenv']['broker_port'], '41001')
            state.update(status='reset', allocation={'tmp': '/tmp/instance', 'status': 'reset'})
            (folder / 'state.json').write_text(json.dumps(state))
            info = report.snapshot(root)['isolation']
            self.assertIsNone(info['master_socket'])
            self.assertEqual(info['expected_environment']['CUBRID_TMP'], '/tmp/instance')
            self.assertIsNone(info['expected_environment']['CUBRID_CUBRID_PORT_ID'])

    def test_all_keeps_errors_and_uninitialized_worktrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / 'repo with spaces'
            repo.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
            git('init', '-q')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                'commit', '--allow-empty', '-qm', 'fixture')
            other = root / 'other worktree'
            git('worktree', 'add', '-qb', 'other', str(other))
            (other / '.cub-workenv').mkdir()
            (other / '.cub-workenv/state.json').write_text('broken')
            result = subprocess.run(['python3', str(SCRIPT), 'all-json', '--worktree', str(repo)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            records = json.loads(result.stdout)
            self.assertEqual(len(records), 2)
            self.assertIsNone(records[0]['state'])
            self.assertIsNone(records[0]['error'])
            self.assertIsNotNone(records[1]['error'])
            fake = root / 'doctor'
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$3"\nexit 1\n')
            fake.chmod(0o755)
            result = subprocess.run(['python3', str(SCRIPT), 'doctor-all', '--worktree', str(repo)],
                                    env=dict(os.environ, CUB_WORKENV_CLI=str(fake)),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(str(repo), result.stdout)
            self.assertIn(str(other), result.stdout)

    def test_just_uses_worktree_root_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'justfile').write_text("mod workenv '" + str(REPO / 'stow/cubrid/.just/workenv.just') + "'\n")
            nested = root / 'src'
            nested.mkdir()
            result = subprocess.run(['just', 'workenv::json'], cwd=nested,
                                    env=dict(os.environ, MY_CUBRID=str(REPO)), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['worktree'], str(root.resolve()))


if __name__ == '__main__':
    unittest.main()
