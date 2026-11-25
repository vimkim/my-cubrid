#!/usr/bin/env python3
"""A preset change must not split a running configure, build or install run.

1. `just preset` refuses while a held coordinator lock belongs to the worktree.
2. A run keeps the preset it read at start when .env changes during the run.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[1]
STOW = REPO / 'stow/cubrid'


def lock_file(runtime_dir, kind, resource):
    digest = hashlib.sha256(os.fsencode(os.path.realpath(resource))).hexdigest()
    return Path(runtime_dir) / f'cubrid-dev-locks-{os.getuid()}' / f'{kind}-{digest}.lock'


def held(path):
    """True when another process holds the flock on path."""
    return path.exists() and subprocess.run(['flock', '--nonblock', str(path), 'true']).returncode != 0


def wait_until(condition, seconds=10):
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError('condition not reached')
        time.sleep(.05)


@unittest.skipUnless(shutil.which('cubrid-build-coordinator') and shutil.which('flock'),
                     'requires cubrid-build-coordinator and flock')
class PresetGuardTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='preset-guard-')
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.home = self.tmp / 'home'
        self.root = self.tmp / 'wt'
        self.root.mkdir(parents=True)
        for name in ('justfile', '.just'):
            (self.root / name).symlink_to(STOW / name)
        commands = self.tmp / 'commands'
        commands.mkdir()
        cmake = commands / 'cmake'
        cmake.write_text("#!/bin/sh\nprintf '%s\\n' 'Available configure presets:' '  \"debug_gcc\"' '  \"release_gcc\"'\n")
        cmake.chmod(0o755)
        self.env_file = self.root / '.env'
        self.env_file.write_text('PRESET_MODE=debug_gcc\n')
        self.env = dict(os.environ, MY_CUBRID=str(REPO), HOME=str(self.home), XDG_RUNTIME_DIR=str(self.tmp),
                        PATH=f'{commands}:{os.environ["PATH"]}')
        for name in ('CUBRID', 'CUBRID_BUILD_DIR', 'CUB_WORKENV_INSTALL', 'PRESET_MODE_PIN', 'PRESET_MODE_PIN_ROOT'):
            self.env.pop(name, None)
        self.holders = []
        self.addCleanup(self.release)

    def release(self):
        for holder in self.holders:
            holder.terminate()
            holder.wait(timeout=10)

    def hold(self, kind, resource, **variables):
        """Hold a coordinator-format lock in a process that names its resource."""
        path = lock_file(self.tmp, kind, resource)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        holder = subprocess.Popen(['flock', '--no-fork', str(path), 'sleep', '60'],
                                  env=dict(self.env, **variables))
        self.holders.append(holder)
        wait_until(lambda: held(path))
        return path

    def preset(self, value):
        return subprocess.run(['just', 'preset', value], cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=60)

    def test_held_build_lock_of_this_worktree_refuses(self):
        build = self.root / 'build_preset_debug_gcc'
        self.hold('build', build, CUBRID_BUILD_DIR=str(build))
        result = self.preset('release_gcc')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Preset not changed', result.stderr)
        self.assertIn(str(build), result.stderr)
        self.assertEqual(self.env_file.read_text(), 'PRESET_MODE=debug_gcc\n')

    def test_held_runtime_lock_of_this_worktree_install_refuses(self):
        install = self.home / '.cub/install/wt/debug_gcc'
        result = subprocess.Popen(
            ['cubrid-build-coordinator', 'installation-use', '0', '--', 'sleep', '60'], cwd=self.root,
            env=dict(self.env, PRESET_MODE='debug_gcc', CUBRID=str(install),
                     CUBRID_BUILD_DIR=str(self.root / 'build_preset_debug_gcc')),
            stderr=subprocess.DEVNULL)
        self.holders.append(result)
        path = lock_file(self.tmp, 'runtime', install)
        wait_until(lambda: held(path))
        refused = self.preset('release_gcc')
        self.assertEqual(refused.returncode, 75, refused.stderr)
        self.assertIn('runtime lock (held)', refused.stderr)
        self.assertIn('installation-use', refused.stderr)
        self.assertEqual(self.env_file.read_text(), 'PRESET_MODE=debug_gcc\n')

    def test_unrelated_held_lock_and_idle_lock_file_allow(self):
        other = self.tmp / 'other/build_preset_debug_gcc'
        self.hold('build', other, CUBRID_BUILD_DIR=str(other))
        idle = lock_file(self.tmp, 'build', self.root / 'build_preset_debug_gcc')
        idle.touch()
        result = self.preset('release_gcc')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_file.read_text(), 'PRESET_MODE=release_gcc\n')

    def test_unreadable_lock_state_refuses(self):
        self.env['CUBRID_BUILD_COORDINATOR_CLI'] = '/no/such/coordinator'
        result = self.preset('release_gcc')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('cannot read coordinator lock state', result.stderr)
        self.assertEqual(self.env_file.read_text(), 'PRESET_MODE=debug_gcc\n')


@unittest.skipUnless(all(shutil.which(name) for name in ('cubrid-build-coordinator', 'direnv', 'cmake', 'make')),
                     'requires cubrid-build-coordinator, direnv, CMake and make')
class PresetPinTest(unittest.TestCase):
    """Run the real .envrc and coordinator; change .env after the first load."""

    def test_configure_build_and_install_keeps_start_preset(self):
        with tempfile.TemporaryDirectory(prefix='preset-pin-') as tmp:
            tmp = Path(tmp)
            root = tmp / 'wt'
            root.mkdir()
            for name in ('justfile', '.just', '.envrc'):
                (root / name).symlink_to(STOW / name)
            (root / '.env').write_text('PRESET_MODE=pa\n')
            (root / 'payload').write_text('artifact\n')
            (root / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.21)\nproject(pin_probe NONE)\n'
                'add_custom_target(probe ALL COMMAND "${CMAKE_COMMAND}" -E copy '
                '"${CMAKE_SOURCE_DIR}/payload" "${CMAKE_BINARY_DIR}/artifact")\n'
                'install(FILES "${CMAKE_BINARY_DIR}/artifact" DESTINATION share)\n')
            presets = [{'name': name, 'generator': 'Unix Makefiles', 'binaryDir': '$env{CUBRID_BUILD_DIR}',
                        'cacheVariables': {'CMAKE_INSTALL_PREFIX': '$env{CUBRID}'}} for name in ('pa', 'pb')]
            (root / 'CMakePresets.json').write_text(json.dumps({
                'version': 3, 'configurePresets': presets,
                'buildPresets': [{'name': name, 'configurePreset': name} for name in ('pa', 'pb')]}))
            java = tmp / 'java'
            for name in ('bin/java', 'bin/javac', 'include/jni.h'):
                (java / name).parent.mkdir(parents=True, exist_ok=True)
                (java / name).touch()
            # The first direnv load selects pa. Right after it, another agent
            # selects pb. Every later load in this run must still select pa.
            commands = tmp / 'commands'
            commands.mkdir()
            direnv = commands / 'direnv'
            direnv.write_text(
                '#!/bin/sh\n'
                f'"{shutil.which("direnv")}" "$@"; status=$?\n'
                f'if [ ! -e "{tmp}/changed" ]; then : > "{tmp}/changed"; '
                f'printf "PRESET_MODE=pb\\n" > "{root}/.env"; fi\n'
                'exit "$status"\n')
            direnv.chmod(0o755)
            home = tmp / 'home'
            env = dict(os.environ, MY_CUBRID=str(REPO), HOME=str(home), XDG_RUNTIME_DIR=str(tmp),
                       XDG_DATA_HOME=str(tmp / 'data'), XDG_CONFIG_HOME=str(tmp / 'config'),
                       XDG_CACHE_HOME=str(tmp / 'cache'), JAVA_HOME=str(java),
                       CUB_WORKENV_CLI='/no/such/cub-workenv', PATH=f'{commands}:{os.environ["PATH"]}')
            for name in ('PRESET_MODE', 'CUBRID', 'CUBRID_BUILD_DIR', 'CUB_WORKENV_INSTALL', 'DIRENV_DIR',
                         'DIRENV_FILE', 'DIRENV_DIFF', 'DIRENV_WATCHES', 'PRESET_MODE_PIN', 'PRESET_MODE_PIN_ROOT'):
                env.pop(name, None)
            subprocess.run([shutil.which('direnv'), 'allow', str(root)], env=env, check=True, capture_output=True)

            result = subprocess.run(['just', 'configure-build-and-install'], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=120)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((tmp / 'changed').exists())
            self.assertEqual((root / '.env').read_text(), 'PRESET_MODE=pb\n')
            self.assertIn('Keeping preset pa for this run; .env now selects pb.', result.stderr)
            self.assertEqual((root / 'build_preset_pa/artifact').read_text(), 'artifact\n')
            self.assertEqual((home / '.cub/install/wt/pa/share/artifact').read_text(), 'artifact\n')
            self.assertFalse((root / 'build_preset_pb').exists())
            self.assertFalse((home / '.cub/install/wt/pb').exists())
            self.assertIn(str(root / 'build_preset_pa/build.log'), result.stdout)


if __name__ == '__main__':
    unittest.main()
