#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / 'bin/cubrid-clangd.py'


class ClangdModesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'build_preset_debug/compile_commands.json'
        self.db.parent.mkdir()
        self.entries = []

    def entry(self, source, target, flags, arguments=False):
        argv = ['c++', *flags, '-o', f'CMakeFiles/{target}.dir/{source}.o', '-c', str(self.root / source)]
        entry = {'directory': str(self.root), 'file': str(self.root / source)}
        entry['arguments' if arguments else 'command'] = argv if arguments else shlex.join(argv)
        self.entries.append(entry)
        return entry

    def save(self):
        self.db.write_text(json.dumps(self.entries))

    def run_cli(self, *args, root=None, preset='debug', ok=True):
        p = subprocess.run([str(CLI), *args, '--preset', preset], cwd=root or self.root, capture_output=True, text=True)
        if ok:
            self.assertEqual(p.returncode, 0, p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0)
        return p

    def selected(self):
        return {Path(e['file']).name: e for e in json.loads((self.root / 'compile_commands.json').read_text())}

    def test_native_ranking_and_flag_order(self):
        self.entry('src/a.c', 'cubridsa', ['-DSA_MODE', '-x', 'c++'])
        server = self.entry('src/a.c', 'cubrid', ['-DSERVER_MODE', '-x', 'c++'], True)
        self.entry('src/a.c', 'unittests_lf', ['-DSERVER_MODE', '-DTEST'])
        self.entry('src/a.c', 'cubridcs', ['-DCS_MODE'])
        neutral = self.entry('src/neutral.c', 'other', ['-DSERVER_MODE', '-U', 'SERVER_MODE'])
        native = self.entry('src/only.c', 'other', ['-D', 'SA_MODE'])
        test = self.entry('unit_tests/t.c', 'unittests_one', ['-DSA_MODE', '-DTEST'])
        self.entry('unit_tests/t.c', 'cubrid', ['-DSERVER_MODE'])
        broker = self.entry('src/broker.c', 'cub_broker', ['-DCAS_BROKER'])
        self.entry('src/broker.c', 'cub_gateway', ['-DCAS_BROKER', '-DFOR_ODBC_GATEWAY'])
        self.save()
        self.run_cli('select', 'server')
        selected = self.selected()
        self.assertEqual(selected['a.c'], server)
        self.assertEqual(selected['neutral.c'], neutral)
        self.assertEqual(selected['only.c'], native)
        self.assertEqual(selected['t.c'], test)
        self.assertEqual(selected['broker.c'], broker)
        self.assertIn('Fallback sources: 4', self.run_cli('status').stdout)
        self.run_cli('select', 'sa')
        self.assertIn('-DSA_MODE', self.selected()['a.c']['command'])
        self.run_cli('select', 'cs')
        self.assertIn('-DCS_MODE', self.selected()['a.c']['command'])

    def test_equivalent_duplicates_and_ambiguity_preserve_previous(self):
        self.entry('a.c', 'cubrid', ['-DSERVER_MODE'])
        self.save(); self.run_cli('select', 'server')
        duplicate = self.entry('a.c', 'cubrid', ['-DSERVER_MODE'])
        duplicate['command'] = duplicate['command'].replace('a.c.o', 'other.o')
        self.save(); self.run_cli('refresh')
        old = os.readlink(self.root / 'compile_commands.json')
        self.entry('a.c', 'cubrid', ['-DSERVER_MODE', '-DDIFFERENT'])
        self.save()
        p = self.run_cli('refresh', ok=False)
        self.assertIn('Ambiguous commands', p.stderr)
        self.assertIn('cubrid', p.stderr)
        self.assertEqual(os.readlink(self.root / 'compile_commands.json'), old)
        selected_link = os.readlink(self.root / 'compile_commands.json')
        self.run_cli('select', 'sa', ok=False)
        self.assertEqual(os.readlink(self.root / 'compile_commands.json'), selected_link)
        self.assertEqual(len(self.selected()), 1)

    def test_mode_fallback_order(self):
        self.entry('a.c', 'cubrid', ['-DSERVER_MODE'])
        self.entry('a.c', 'cubridsa', ['-DSA_MODE'])
        self.entry('b.c', 'cubridsa', ['-DSA_MODE'])
        self.entry('b.c', 'cubridcs', ['-DCS_MODE'])
        self.entry('c.c', 'cubrid', ['-DSERVER_MODE'])
        self.entry('c.c', 'cubridcs', ['-DCS_MODE'])
        self.save()
        self.run_cli('select', 'cs')
        self.assertIn('-DSA_MODE', self.selected()['a.c']['command'])
        self.run_cli('select', 'server')
        self.assertIn('-DSA_MODE', self.selected()['b.c']['command'])
        self.run_cli('select', 'sa')
        self.assertIn('-DSERVER_MODE', self.selected()['c.c']['command'])

    def test_unknown_equal_tier_refuses_to_guess(self):
        self.entry('a.c', 'unknown1', ['-DONE'])
        self.entry('a.c', 'unknown2', ['-DTWO'])
        self.save()
        p = self.run_cli('select', 'server', ok=False)
        self.assertIn('unknown1', p.stderr); self.assertIn('unknown2', p.stderr)
        self.assertFalse((self.root / 'compile_commands.json').exists())

    def test_split_macro_values_are_not_treated_as_equivalent(self):
        self.entry('a.c', 'cubrid', ['-D', 'SERVER_MODE', '-D', 'VALUE=1'])
        self.entry('a.c', 'cubrid', ['-D', 'SERVER_MODE', '-D', 'VALUE=2'])
        self.save()
        self.assertIn('Ambiguous', self.run_cli('select', 'server', ok=False).stderr)

    def test_protect_foreign_files_and_links(self):
        self.entry('a.c', 'cubrid', ['-DSERVER_MODE']); self.save()
        link = self.root / 'compile_commands.json'
        link.write_text('user data')
        self.run_cli('select', 'server', ok=False)
        self.assertEqual(link.read_text(), 'user data')
        link.unlink(); foreign = self.root / 'foreign.json'; foreign.write_text('[]'); link.symlink_to(foreign)
        self.run_cli('select', 'server', ok=False)
        self.run_cli('preset', 'release', ok=False)
        self.assertEqual(link.resolve(), foreign)
        self.assertFalse((self.root / '.env').exists())

    def test_refresh_preset_transition_and_isolation(self):
        self.entry('a.c', 'cubridsa', ['-DSA_MODE']); self.save()
        link = self.root / 'compile_commands.json'; link.symlink_to(self.db.relative_to(self.root))
        self.run_cli('select', 'sa')
        first = os.readlink(link)
        self.run_cli('refresh'); self.assertEqual(os.readlink(link), first)
        self.entry('b.c', 'cubridsa', ['-DSA_MODE']); self.save()
        self.assertIn('stale', self.run_cli('status').stdout)
        self.run_cli('refresh'); self.assertNotEqual(os.readlink(link), first)
        envfile = self.root / '.env'; envfile.write_text('OTHER=keep\nexport PRESET_MODE=debug\n'); envfile.chmod(0o640)
        self.run_cli('preset', 'release')
        self.assertEqual(envfile.read_text(), 'OTHER=keep\nPRESET_MODE=release\n')
        self.assertEqual(envfile.stat().st_mode & 0o777, 0o640)
        self.assertTrue(link.is_symlink()); self.assertFalse(link.exists())
        self.assertIn('pending', self.run_cli('status', preset='release').stdout)
        stale = self.run_cli('refresh', preset='debug', ok=False)
        self.assertIn('environment is stale', stale.stderr)
        self.assertFalse(link.exists())
        self.run_cli('refresh', preset='release', ok=False)
        self.assertFalse(link.exists())
        other = self.root / 'other'; other.mkdir(); (other / 'build_preset_debug').mkdir()
        (other / 'build_preset_debug/compile_commands.json').write_text('[]')
        self.run_cli('select', 'cs', root=other)
        self.assertIn('Mode: cs', self.run_cli('status', root=other).stdout)
        self.assertIn('Mode: sa', self.run_cli('status', preset='release').stdout)

    def test_just_recipes_and_invalid_preset(self):
        for name in ('justfile', '.just'):
            (self.root / name).symlink_to(REPO / 'stow/cubrid' / name)
        commands = self.root / 'commands'; commands.mkdir()
        for name, body in {'direnv': 'shift 2; exec "$@"', 'cmake': 'printf "  \\\"debug\\\"\\n"'}.items():
            path = commands / name; path.write_text('#!/bin/sh\n' + body + '\n'); path.chmod(0o755)
        self.entry('a.c', 'cubrid', ['-DSERVER_MODE']); self.save()
        env = dict(os.environ, MY_CUBRID=str(REPO), PRESET_MODE='debug', PATH=f'{commands}:{os.environ["PATH"]}')
        def just(*args):
            return subprocess.run(['just', *args], cwd=self.root, env=env, capture_output=True, text=True)
        p = just('clangd', 'server'); self.assertEqual(p.returncode, 0, p.stderr)
        p = just('clangd-status'); self.assertIn('Mode: server', p.stdout)
        p = just('clangd-refresh'); self.assertEqual(p.returncode, 0, p.stderr)
        previous = os.readlink(self.root / 'compile_commands.json')
        p = just('preset', 'unknown'); self.assertNotEqual(p.returncode, 0)
        self.assertEqual(os.readlink(self.root / 'compile_commands.json'), previous)
        self.assertFalse((self.root / '.env').exists())

    def test_configure_refreshes_only_after_success(self):
        for name in ('justfile', '.just'):
            (self.root / name).symlink_to(REPO / 'stow/cubrid' / name)
        commands = self.root / 'commands'; commands.mkdir()
        direnv = commands / 'direnv'; direnv.write_text('#!/bin/sh\nshift 2; exec "$@"\n'); direnv.chmod(0o755)
        coordinator = commands / 'coordinator'; coordinator.write_text('#!/bin/sh\nexit "${FAKE_RESULT:-0}"\n'); coordinator.chmod(0o755)
        java = self.root / 'java'
        for name in ('bin/java', 'bin/javac', 'include/jni.h'):
            path = java / name; path.parent.mkdir(parents=True, exist_ok=True); path.touch()
        self.entry('a.c', 'cubrid', ['-DSERVER_MODE']); self.save()
        self.run_cli('select', 'server')
        old = os.readlink(self.root / 'compile_commands.json')
        self.entry('b.c', 'cubrid', ['-DSERVER_MODE']); self.save()
        env = dict(os.environ, MY_CUBRID=str(REPO), PRESET_MODE='debug', JAVA_HOME=str(java),
                   CUBRID_BUILD_DIR=str(self.db.parent), CUBRID_BUILD_COORDINATOR_CLI=str(coordinator),
                   PATH=f'{commands}:{os.environ["PATH"]}')
        def configure():
            return subprocess.run(['just', 'configure'], cwd=self.root, env=env, text=True, capture_output=True)
        env['FAKE_RESULT'] = '1'
        self.assertNotEqual(configure().returncode, 0)
        self.assertEqual(os.readlink(self.root / 'compile_commands.json'), old)
        env['FAKE_RESULT'] = '0'
        p = configure(); self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotEqual(os.readlink(self.root / 'compile_commands.json'), old)
        self.assertEqual(len(self.selected()), 2)

    def test_stow_excludes_only_generated_directory(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        env = dict(os.environ, CUBRID_SKIP_SHARED_STOW='1', MY_CUBRID=str(REPO),
                   CUBRID_JUSTFILES_DIR=str(self.root / 'local-files'))
        for _ in range(2):
            subprocess.run([str(REPO / 'stow-create.sh')], cwd=self.root, env=env, check=True, capture_output=True)
        exclude = (self.root / '.git/info/exclude').read_text().splitlines()
        self.assertEqual(exclude.count('/.lsp/'), 1)
        self.assertNotIn('/compile_commands.json', exclude)

    @unittest.skipUnless(shutil.which('clangd') and shutil.which('c++'), 'requires clangd and c++')
    def test_clangd_reads_selected_cpp_flags(self):
        source = self.root / 'modes.c'
        self.entry('modes.c', 'cubrid', ['-DSERVER_MODE', '-x', 'c++'])
        self.entry('modes.c', 'cubridsa', ['-DSA_MODE', '-x', 'c++'])
        self.save()
        (self.root / '.clangd').symlink_to(REPO / 'stow/cubrid/.clangd')
        for mode, active, inactive in [('server', 'SERVER_MODE', 'SA_MODE'), ('sa', 'SA_MODE', 'SERVER_MODE')]:
            source.write_text(f'template<class T> T identity(T x) {{ return x; }}\n#ifndef {active}\n#error selected_mode_missing\n#endif\n#ifdef {inactive}\n#error inactive_mode_defined\n#endif\n#if defined({active})\nint selected_only() {{ return identity(1); }}\n#else\n#error inactive_branch_parsed\n#endif\n')
            self.run_cli('select', mode)
            p = subprocess.run(['clangd', '--check=' + str(source), '--log=verbose'], cwd=self.root, text=True, capture_output=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('0 errors', p.stderr)
            self.assertIn('-D' + active, p.stderr)
            self.assertNotIn('-D' + inactive, p.stderr)
            self.assertIn('-x c++', p.stderr)


if __name__ == '__main__':
    unittest.main()
