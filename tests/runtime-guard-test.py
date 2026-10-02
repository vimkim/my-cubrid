#!/usr/bin/env python3
"""Retirement contract: legacy authority never mutates retained state or data.

Allocation, interrupted initialization and ownership diagnostics now belong to
cubrid-workenv's public test_cli/test_state/test_reclamation/test_doctor suites.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'bin/my-cubrid-runtime'


class RetirementTest(unittest.TestCase):
    def test_every_legacy_action_is_explicitly_retired_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / 'legacy'; legacy.mkdir()
            sentinel = legacy / 'manifest.json'; sentinel.write_text('retained legacy state')
            for action in ('init', 'validate', 'adopt', 'deinit', 'env', '--help'):
                result = subprocess.run([str(CLI), action], cwd=root,
                    env=dict(os.environ, CUBRID_RUNTIME_STATE_ROOT=str(legacy)), text=True, capture_output=True)
                self.assertEqual(result.returncode, 64)
                self.assertIn('cub-workenv', result.stderr)
                self.assertIn('No files were changed', result.stderr)
                self.assertEqual(sentinel.read_text(), 'retained legacy state')
                self.assertEqual(sorted(p.name for p in root.iterdir()), ['legacy'])


if __name__ == '__main__':
    unittest.main()
