#!/usr/bin/env python3
"""Real Podman lifetime boundary; test install contains harmless native probes.

This proves bind-mount ownership/lock lifetime, not CUBRID SQL inside containers.
The existing container runner's independent DB environment is unchanged.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

repo = Path(__file__).resolve().parents[1]
root = Path(tempfile.mkdtemp(prefix='cwe-container-', dir='/tmp'))
root.chmod(0o755)
install = root / 'install'
(install / 'bin').mkdir(parents=True)
for part in ('log', 'tmp', 'var'):
    (install / part).mkdir()
for name in ('cubrid', 'csql'):
    shutil.copy2('/usr/bin/true', install / 'bin' / name)
source = root / 'source'; source.mkdir()
for name in ('justfile', '.just'):
    (source / name).symlink_to(repo / 'stow/cubrid' / name)
script = root / 'test.sh'
script.write_text('#!/bin/sh\nset -eu\ntest -x "$CUBRID/bin/cubrid"\n"$CUBRID/bin/cubrid"\necho mount-probe-pass\n')
script.chmod(0o755)
name = 'cwe-migration-' + root.name.rsplit('-', 1)[-1]
env = dict(os.environ, MY_CUBRID=str(repo), CUBRID=str(install), PRESET_MODE='debug',
           CUBRID_BUILD_DIR=str(source / 'build'), TMPDIR='/tmp')
coordinator = repo / 'bin/cubrid-build-coordinator.sh'
runner = repo / 'bin/cubrid-podman-test.sh'
record = {'root': str(root), 'container': name, 'steps': []}


def run(label, command, expected=0):
    with (root / (label + '.log')).open('w') as stream:
        result = subprocess.run(list(map(str, command)), cwd=source, env=env,
                                stdout=stream, stderr=subprocess.STDOUT, timeout=40)
    record['steps'].append({'label': label, 'command': list(map(str, command)), 'returncode': result.returncode})
    (root / 'results.json').write_text(json.dumps(record, indent=2) + '\n')
    assert result.returncode == expected, (label, (root / (label + '.log')).read_text())


print(root, flush=True)
with (root / 'container.log').open('w') as log:
    process = subprocess.Popen(['just', 'ctp::podman-test-new', name, 'probe', str(script)],
                               cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError((root / 'container.log').read_text())
            result = subprocess.run(['podman', 'exec', name, 'test', '-f', '/sandbox/test.ready'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError('owned container did not reach test.ready')
        assert not (source / '.cub-workenv').exists()
        run('install-blocked-after-test', [coordinator, 'install', '0'], expected=75)
        run('delete-blocked-after-test', [coordinator, 'installation-delete', '0'], expected=75)
        # Deliver to the actual supervisor: just is a separate recipe parent.
        children = []
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                cmdline = (proc / 'cmdline').read_bytes().split(b'\0')
                if str(coordinator).encode() in cmdline and str(script).encode() in cmdline:
                    children.append(int(proc.name))
            except OSError:
                pass
        assert len(children) == 1, children
        os.kill(children[0], 15)
        status = process.wait(timeout=40)
        record['signalled_supervisor'] = children[0]
        record['recipe_exit_after_signal'] = status
        result = subprocess.run(['podman', 'container', 'exists', name])
        assert result.returncode == 1, 'owned container survived supervisor signal'
        run('lock-released-after-cleanup', [coordinator, 'installation-use', '0', '--', 'true'])
        record['verdict'] = 'pass'
    finally:
        # The runner owns immutable-ID/label verification; never remove by a raw
        # unverified podman name from this harness.
        if subprocess.run(['podman', 'container', 'exists', name]).returncode == 0:
            run('cleanup-owned-container', [runner, 'stop', name])
        if process.poll() is None:
            process.wait(timeout=40)
        (root / 'results.json').write_text(json.dumps(record, indent=2) + '\n')
print(record.get('verdict', 'failed'), flush=True)
