#!/usr/bin/env python3
"""Collision semantics and bounded filesystem work at the validation seam."""

import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader(
    "runtime_claims", str(Path(__file__).resolve().parents[1] / "bin/my-cubrid-runtime")
)
spec = importlib.util.spec_from_loader(loader.name, loader)
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
previous_bytecode_setting = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    loader.exec_module(runtime)
finally:
    sys.dont_write_bytecode = previous_bytecode_setting


class ClaimsTest(unittest.TestCase):
    def check_claims(self, selected, retained, identities=None):
        observations = []
        identities = identities or {}

        def inspect(path):
            observations.append(path)
            identity = identities.get(path)
            return SimpleNamespace(exists=identity is not None,
                                   device=identity[0] if identity else None,
                                   inode=identity[1] if identity else None)

        bundle = SimpleNamespace(claims=lambda: SimpleNamespace(
            tcp_ports=(), system_v_keys=(), paths=selected))
        with patch.object(runtime, "all_claimed_values", return_value=(set(), set(), set(retained))):
            runtime.reject_managed_claim_collisions(
                bundle, {}, "selected", Path("/guard"), SimpleNamespace(inspect_file=inspect))
        return observations

    def test_validation_observes_each_claim_at_most_once(self):
        selected = [Path(f"/selected/{i}") for i in range(40)]
        retained = [Path(f"/retained/{i}") for i in range(300)]
        observations = self.check_claims(selected, retained)
        self.assertLessEqual(len(observations), len(selected) + len(retained))
        self.assertEqual(len(observations), len(set(observations)))

    def test_equal_ancestor_descendant_and_hardlink_collisions(self):
        for left, right, identities in (
            ("/one/db", "/one/db", {}),
            ("/one", "/one/db", {}),
            ("/one/db", "/one", {}),
            ("/one/db", "/two/db", {Path("/one/db"): (1, 42), Path("/two/db"): (1, 42)}),
        ):
            with self.subTest(left=left, right=right), self.assertRaises(runtime.OperationError) as raised:
                self.check_claims([Path(left)], [Path(right)], identities)
            self.assertEqual(raised.exception.diagnostic.code, "managed_path_collision")

    def test_index_is_refreshed_between_validations(self):
        left, right = Path("/one"), Path("/two")
        self.check_claims([left], [right])
        with self.assertRaises(runtime.OperationError):
            self.check_claims([left], [right], {left: (1, 42), right: (1, 42)})

    def test_index_matches_pairwise_check_on_real_filesystem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original"
            original.write_text("claim")
            alias = root / "alias"
            alias.hardlink_to(original)
            adapter = runtime.LinuxObservationAdapter()
            candidates = (root, original, alias, root / "missing", root / "missing/child")
            for left in candidates:
                for right in candidates:
                    with self.subTest(left=left, right=right):
                        expected = runtime.paths_overlap(left, right, adapter)
                        actual = runtime.first_overlapping_claim((left,), {right}, adapter)
                        self.assertEqual(actual is not None, expected)

    def test_prefixes_missing_paths_and_different_devices_do_not_collide(self):
        self.check_claims([Path("/one")], [Path("/one-more")])
        self.check_claims([Path("/one")], [Path("/two")],
                          {Path("/one"): (1, 42), Path("/two"): (2, 42)})
        self.assertEqual(self.check_claims([Path("/one")], []), [])


if __name__ == "__main__":
    unittest.main()
