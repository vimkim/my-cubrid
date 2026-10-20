#!/usr/bin/env python3
"""Verify the exec shim and representative recipes with disposable commands."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SHIM = REPO / 'bin/cubrid-build-coordinator.sh'


class CoordinatorShimTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cmake') and shutil.which('make'), 'requires CMake and make')
    def test_shared_recipes_build_while_busy_then_install_existing_artifacts(self):
        with tempfile.TemporaryDirectory(prefix='coordinator-stages-') as tmp:
            root = Path(tmp)
            for name in ('justfile', '.just'):
                (root / name).symlink_to(REPO / 'stow/cubrid' / name)
            commands = root / 'commands'
            commands.mkdir()
            direnv = commands / 'direnv'
            direnv.write_text('#!/bin/sh\nshift 2; exec "$@"\n')
            direnv.chmod(0o755)
            java = root / 'java'
            for name in ('bin/java', 'bin/javac', 'include/jni.h'):
                path = java / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (root / 'payload').write_text('first\n')
            (root / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.21)\nproject(stage_probe NONE)\n'
                'add_custom_target(probe ALL COMMAND "${CMAKE_COMMAND}" -E copy '
                '"${CMAKE_SOURCE_DIR}/payload" "${CMAKE_BINARY_DIR}/artifact")\n'
                'install(FILES "${CMAKE_BINARY_DIR}/artifact" DESTINATION share)\n')
            (root / 'CMakePresets.json').write_text(json.dumps({
                'version': 3, 'configurePresets': [
                    {'name': 'debug', 'generator': 'Unix Makefiles',
                     'binaryDir': '$env{CUBRID_BUILD_DIR}',
                     'cacheVariables': {'CMAKE_INSTALL_PREFIX': '$env{CUBRID}'}}],
                'buildPresets': [{'name': 'debug', 'configurePreset': 'debug'}]}))
            env = dict(os.environ, MY_CUBRID=str(REPO), XDG_RUNTIME_DIR=str(root),
                       CUBRID=str(root / 'install'), CUBRID_BUILD_DIR=str(root / 'build'),
                       PRESET_MODE='debug', JAVA_HOME=str(java),
                       PATH=f'{commands}:{os.environ["PATH"]}')

            def recipe(*args):
                return subprocess.run(['just', *args], cwd=root, env=env,
                                      text=True, capture_output=True, timeout=15)

            locks = root / f'cubrid-dev-locks-{os.getuid()}'
            locks.mkdir(mode=0o700)
            digest = hashlib.sha256(os.fsencode(os.path.realpath(env['CUBRID']))).hexdigest()
            with (locks / f'runtime-{digest}.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = recipe('configure-build')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / 'build/artifact').read_text(), 'first\n')
                self.assertFalse((root / 'install/share/artifact').exists())
                result = recipe('build-and-install')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('75', result.stderr)
                self.assertFalse((root / 'install/share/artifact').exists())
            (root / 'payload').write_text('second\n')
            result = recipe('install')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'install/share/artifact').read_text(), 'first\n')
            result = recipe('configure-build-and-install')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'install/share/artifact').read_text(), 'second\n')
            self.assertFalse((root / '.cub-workenv').exists())

    def test_exec_preserves_pid_arguments_streams_and_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / 'reviewed cli'
            cli.write_text(f'#!{sys.executable}\n' +
                           'import json,os,sys\n'
                           'print(json.dumps([os.getpid(),sys.argv[1:],sys.stdin.read()]))\n'
                           'sys.exit(23)\n')
            cli.chmod(0o755)
            args = ['installation-use','0','--','argument with spaces','',"quote'",'$(false)']
            child = subprocess.Popen([str(SHIM),*args],env=dict(os.environ,CUBRID_BUILD_COORDINATOR_CLI=str(cli)),
                                     stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            output,error = child.communicate('editor input\n',timeout=5)
            self.assertEqual(child.returncode,23,error)
            self.assertEqual(json.loads(output),[child.pid,args,'editor input\n'])

    def test_missing_cli_fails_with_installation_guidance(self):
        result = subprocess.run([str(SHIM),'install','0'],capture_output=True,text=True,
                                env=dict(os.environ,CUBRID_BUILD_COORDINATOR_CLI='/no/such/coordinator'))
        self.assertEqual(result.returncode,127)
        self.assertIn('Install cubrid-build-coordinator',result.stderr)

    def test_real_recipes_keep_input_and_build_pipeline_status(self):
        with tempfile.TemporaryDirectory(prefix='coordinator-recipes-') as tmp:
            root = Path(tmp)
            commands = root / 'commands'
            commands.mkdir()
            for name in ('justfile','.just'):
                (root/name).symlink_to(REPO/'stow/cubrid'/name)
            bodies = {
                'cub-workenv': 'printf "%s\\n" "export CUBRID_RUNTIME_READY=1"',
                'direnv': 'shift 2; exec "$@"',
                'cmake': 'if [ "$1" = --build ]; then echo compile-fixture-failed; exit 9; fi',
                'ctest': 'printf ctest-fixture-pass',
                'nvim': 'cat',
                'cgdb': 'cat',
            }
            for name,body in bodies.items():
                executable = commands/name
                executable.write_text('#!/bin/sh\n'+body+'\n')
                executable.chmod(0o755)
            java = root/'java'
            for name in ('bin/java','bin/javac','include/jni.h'):
                path = java/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.touch()
            registry = root/'databases'
            registry.mkdir()
            (registry/'databases.txt').write_text('testdb /data localhost /log\n')
            env = dict(os.environ,MY_CUBRID=str(REPO),XDG_RUNTIME_DIR=str(root),
                       CUBRID=str(root/'install'),CUBRID_BUILD_DIR=str(root/'build'),
                       CUBRID_DATABASES=str(registry),CUBRID_TMP=str(root/'tmp'),
                       PRESET_MODE='debug',JAVA_HOME=str(java),CUB_WORKENV_CLI=str(commands/'cub-workenv'),
                       PATH=f'{commands}:{os.environ["PATH"]}')
            (root / 'CMakePresets.json').write_text(json.dumps({
                'version': 3, 'configurePresets': [
                    {'name': 'debug', 'binaryDir': '$env{CUBRID_BUILD_DIR}'}],
                'buildPresets': [{'name': 'debug', 'configurePreset': 'debug'}]}))
            for recipe in ('db::edit-config','debug::csql-sa'):
                result = subprocess.run(['just',recipe],env=env,cwd=root,text=True,
                                        input='interactive recipe input\n',capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,'interactive recipe input\n')
            result = subprocess.run(['just','ctest'],env=env,cwd=root,text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('ctest-fixture-pass',result.stdout)
            for recipe in [('build',), ('build-and-install',), ('build-and-install', '--stop-runtime')]:
                result = subprocess.run(['just',*recipe],env=env,cwd=root,text=True,capture_output=True,timeout=5)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('exit code 9',result.stderr)
                self.assertIn('compile-fixture-failed',(root/'build/build.log').read_text())


if __name__ == '__main__':
    unittest.main()
