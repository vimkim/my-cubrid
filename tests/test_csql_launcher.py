"""Check the cs helper's history launch and CUBRID source-tree boundary."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CsqlLauncherTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.commands = self.root / "bin"
        self.commands.mkdir()
        self.source = self.root / "source"
        self.source.mkdir()
        self.environment = dict(
            os.environ,
            PATH=str(self.commands) + ":/usr/bin:/bin",
            CUBRID_DATABASES=str(self.root),
            SERVER_STATUS="",
            CLIENT_SOURCE=str(self.source),
            SERVER_SOURCE=str(self.source),
        )
        (self.commands / "rg").symlink_to(shutil.which("rg"))
        self.command("cubrid", 'printf "%s\\n" "$SERVER_STATUS"')
        self.command("cubrid_rel", 'echo CUBRID')
        self.command("fzf", 'head -n 1')
        self.command("csql", 'printf "CSQL_ARGS\\n"; printf "%s\\n" "$@"')
        self.command("csql-future", 'echo HISTORY_LAUNCH; exec csql "$@"')
        self.command("cubrid-binary-source-dir", '''case "$1" in
            /proc/*) printf "%s\\n" "$SERVER_SOURCE" ;;
            *) printf "%s\\n" "$CLIENT_SOURCE" ;;
        esac''')
        (self.root / "databases.txt").write_text("picked /unused localhost /unused\n")

    def command(self, name, body):
        binary = self.commands / name
        binary.write_text("#!/bin/sh\n" + body + "\n")
        binary.chmod(0o755)
        return binary

    def run_helper(self, *arguments):
        return subprocess.run(
            [str(ROOT / "bin/csql.sh"), *arguments],
            cwd=self.root, env=self.environment, capture_output=True, text=True,
            timeout=10,
        )

    def start_server(self):
        server = self.commands / "cub_server"
        shutil.copyfile(shutil.which("sleep"), server)
        server.chmod(0o755)
        process = subprocess.Popen([str(server), "60"], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.terminate)
        self.environment["SERVER_STATUS"] = f"Server testdb (rel 11.5, pid {process.pid})"

    def test_database_picker_and_auto_sa_use_history_launcher(self):
        result = self.run_helper("-c", "select 1;")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HISTORY_LAUNCH", result.stdout)
        self.assertIn("CSQL_ARGS\n--no-pager\n-u\ndba\npicked\n-S\n-c\nselect 1;\n", result.stdout)

    def test_running_matching_server_uses_cs_without_injected_sa(self):
        self.start_server()
        result = self.run_helper("testdb")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HISTORY_LAUNCH", result.stdout)
        self.assertIn("CSQL_ARGS\n--no-pager\n-u\ndba\ntestdb\n", result.stdout)
        self.assertNotIn("\n-S\n", result.stdout)

    def test_mismatched_server_is_rejected_before_history_launch(self):
        self.start_server()
        other_source = self.root / "other-source"
        other_source.mkdir()
        self.environment["SERVER_SOURCE"] = str(other_source)
        result = self.run_helper("testdb")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("running server belongs to another source tree", result.stderr)
        self.assertNotIn("HISTORY_LAUNCH", result.stdout)

    def test_missing_history_tool_has_install_guidance(self):
        (self.commands / "csql-future").unlink()
        result = self.run_helper("testdb", "-S")
        self.assertEqual(127, result.returncode)
        self.assertIn("just sync in ~/gh/csql-future", result.stderr)

    @unittest.skipUnless(shutil.which("nu"), "Nushell is required")
    def test_nushell_cs_alias_reaches_the_history_launcher(self):
        (self.commands / "csql.sh").symlink_to(ROOT / "bin/csql.sh")
        result = subprocess.run(
            [shutil.which("nu"), "--no-config-file", "-c",
             f"source {json.dumps(str(ROOT / 'aliases.nu'))}; cs testdb -S"],
            cwd=self.root, env=self.environment, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HISTORY_LAUNCH", result.stdout)


if __name__ == "__main__":
    unittest.main()
