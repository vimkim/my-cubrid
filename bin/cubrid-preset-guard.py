#!/usr/bin/env python3
"""Refuse a preset change while a coordinator lock for this worktree is held.

A preset change rewrites the worktree .env. A build or runtime command that is
running reads .env again in later steps, so the change can mix presets. Lock
state comes from `cubrid-build-coordinator locks --all --json`; only held (or
unknown) locks count, not lock files that exist.

Exit status: 0 when no such lock is held, 75 when one is held, 1 when lock
state cannot be read.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def canonical(path):
    return os.path.realpath(os.path.expanduser(path))


def inside(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


def env_file_value(root, name):
    try:
        lines = (Path(root) / '.env').read_text().splitlines()
    except OSError:
        return None
    value = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('export '):
            stripped = stripped[len('export '):].lstrip()
        key, separator, rest = stripped.partition('=')
        if separator and key.strip() == name:
            try:
                words = shlex.split(rest, comments=True)
            except ValueError:
                continue
            value = words[0] if len(words) == 1 else None
    return value


def install_matchers(root):
    """Return (exact install dirs, install prefixes) that belong to this worktree."""
    exact = set()
    home = os.environ.get('HOME') or os.path.expanduser('~')
    # .envrc default: $HOME/.cub/install/<worktree basename>/<preset>
    prefixes = {canonical(os.path.join(home, '.cub/install', os.path.basename(root)))}
    for value in (os.environ.get('CUB_WORKENV_INSTALL'), env_file_value(root, 'CUB_WORKENV_INSTALL')):
        if value:
            exact.add(canonical(value))
    build_dir = os.environ.get('CUBRID_BUILD_DIR')
    if os.environ.get('CUBRID') and build_dir and inside(canonical(build_dir), root):
        exact.add(canonical(os.environ['CUBRID']))
    return exact, prefixes


def blocking_locks(report, root):
    exact, prefixes = install_matchers(root)
    result = []
    for lock in report.get('locks', []):
        if lock.get('state') == 'idle':
            continue
        resource = lock.get('resource')
        if resource is None:
            # The holder's environment was unreadable. Do not guess that the
            # lock belongs to another worktree.
            result.append(lock)
            continue
        resource = canonical(resource)
        if inside(resource, root) or resource in exact or any(inside(resource, prefix) for prefix in prefixes):
            result.append(lock)
    return result


def main(argv):
    if len(argv) != 2:
        print('Usage: cubrid-preset-guard.py WORKTREE', file=sys.stderr)
        return 2
    root = canonical(argv[1])
    shim = Path(os.environ.get('MY_CUBRID') or Path(__file__).resolve().parents[1]) / 'bin/cubrid-build-coordinator.sh'
    stderr = ''
    try:
        result = subprocess.run([str(shim), 'locks', '--all', '--json'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        stderr = result.stderr.strip()
        report = json.loads(result.stdout)
        if not isinstance(report, dict) or report.get('error'):
            raise ValueError(report.get('error') if isinstance(report, dict) else 'unexpected JSON')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'Preset not changed: cannot read coordinator lock state ({stderr or error}).', file=sys.stderr)
        return 1
    held = blocking_locks(report, root)
    if not held:
        return 0
    print(f'Preset not changed: a build or runtime lock for this worktree is held ({root}).', file=sys.stderr)
    for lock in held:
        print(f'  {lock.get("kind", "?")} lock ({lock.get("state")}): {lock.get("resource") or "resource unknown"}',
              file=sys.stderr)
        print(f'    Lock file: {lock.get("path")}', file=sys.stderr)
        for owner in lock.get('owners', []):
            print(f'    Holder: PID {owner.get("pid")}: {shlex.join(owner.get("command") or [])}', file=sys.stderr)
    print('Wait for the command to finish (`just locks-all` shows holders), then retry.', file=sys.stderr)
    return 75


if __name__ == '__main__':
    sys.exit(main(sys.argv))
