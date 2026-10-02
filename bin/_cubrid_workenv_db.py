"""Explicit DB recipes for the selected workenv; never read legacy manifests.

Creation delegates to the public CLI. A receipt records only newly created
physical storage provenance, not runtime selection or resource ownership.
Deletion uses native locking and utilities, with a private registry so unrelated
rows/comments are byte-preserved. No recursive storage removal or binary fallback.
"""
import argparse
import configparser
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import uuid


def registrations(content):
    result = {}
    for line in content.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith(b'#'):
            continue
        name = fields[0].decode()
        if name in result:
            raise ValueError(f'Duplicate registration: {name}; inspect manually')
        result[name] = fields
    return result


def native(*arguments, env=None):
    subprocess.run([str(Path(os.environ['CUBRID']) / 'bin/cubrid'), *arguments],
                   env=env, check=True)


def create(root, name, template, recreate=False):
    registry = root / 'databases/databases.txt'
    if template:
        for part in ('schema', 'objects'):
            if not (Path(os.environ['CUBRID']) / 'demo' / f'demodb_{part}').is_file():
                raise ValueError('Missing CUBRID/demo sample files; no database created')
    command = [os.environ.get('CUB_WORKENV_CLI', 'cub-workenv'), 'create-db', name,
               '--worktree', str(root.parent)]
    if recreate:
        command += ['--path', str(root / 'db' / (name + '-' + uuid.uuid4().hex))]
    subprocess.run(command, check=True)
    if template:
        demo = Path(os.environ['CUBRID']) / 'demo'
        try:
            native('loaddb', '-u', 'dba', '-s', str(demo / 'demodb_schema'),
                   '-d', str(demo / 'demodb_objects'), name)
        except subprocess.CalledProcessError as error:
            raise ValueError(f'demodb load failed; {name} and its data are retained for inspection') from error


def checked_internal_storage(root, name, fields):
    guidance = ('Storage preserved. Automatic deletion requires known, wholly internal storage; '
                'see docs/host-workenv.md#manual-database-lifecycle for manual review.')
    receipt_path = root / f'created-{name}.json'
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError(f'No creation receipt for {name}. {guidance}')
    receipt = json.loads(receipt_path.read_text())
    base = Path(receipt['base'])
    expected = [name, str(base / 'data'), 'localhost', str(base / 'log'), 'file:' + str(base / 'lob')]
    if (receipt.get('name') != name or base.parent != root / 'db'
            or receipt.get('registration') != expected or [f.decode() for f in fields] != expected):
        raise ValueError(f'External, changed or mixed registration for {name}. {guidance}')
    if base.resolve(strict=True) != base or os.path.ismount(base):
        raise ValueError(f'Symlink/mount storage for {name}. {guidance}')
    primary = (base / 'data' / name).stat()
    if (primary.st_dev, primary.st_ino) != (receipt['primary_device'], receipt['primary_inode']):
        raise ValueError(f'Primary volume identity changed for {name}. {guidance}')
    # Never traverse a symlink, mount, hard link or foreign-owned storage entry.
    for directory, dirs, files in os.walk(base, followlinks=False):
        for path in [Path(directory), *(Path(directory) / p for p in dirs + files)]:
            metadata = path.lstat()
            if (metadata.st_uid != os.geteuid() or metadata.st_dev != primary.st_dev
                    or os.path.ismount(path) or stat.S_ISLNK(metadata.st_mode)
                    or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode))
                    or (stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1)):
                raise ValueError(f'Uncertain storage at {path}. {guidance}')
    # Native deletedb reads this volume list, including additional volumes.
    volume_info = base / 'data' / (name + '_vinf')
    volumes = set()
    for line in volume_info.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r'-?\d+', parts[0]):
            raise ValueError(f'Unrecognized volume information. {guidance}')
        path = Path(parts[1])
        if not path.is_absolute() or not path.resolve().is_relative_to(base):
            raise ValueError(f'External/mixed volume: {path}. {guidance}')
        volumes.add(path)
    if base / 'data' / name not in volumes or base / 'log' / (name + '_lgat') not in volumes:
        raise ValueError(f'Incomplete volume information. {guidance}')
    return base, receipt_path


def delete(root, name):
    registry = root / 'databases/databases.txt'
    # Same preparation lock as cub-workenv init/create-db, not a runtime lease.
    with (root / 'init.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = registry.read_bytes()
        rows = registrations(before)
        if name not in rows:
            raise ValueError(f'Database {name} is not registered; nothing deleted')
        base, receipt = checked_internal_storage(root, name, rows[name])
        config = configparser.ConfigParser(strict=False, interpolation=None)
        with Path(os.environ['CUBRID_CONF_FILE']).open() as stream:
            config.read_file(stream)
        for section in config.sections():
            if config.has_option(section, 'file_lock') and not config.getboolean(section, 'file_lock'):
                raise ValueError('file_lock is disabled; native exclusion is required. Storage preserved.')
        # Native active-log exclusion rejects a live server/standalone owner.
        # No implicit stop and no --delete-backup, forced delete or retry.
        with tempfile.TemporaryDirectory(prefix='delete-', dir=root) as scratch:
            temporary = Path(scratch) / 'databases.txt'
            temporary.write_bytes(b' '.join(rows[name]) + b'\n')
            native('deletedb', name, env=dict(os.environ, CUBRID_DATABASES=scratch))
        if registry.read_bytes() != before:
            raise ValueError('Registry changed during deletion; inspect retained registration; no retry')
        retained = b''.join(line for line in before.splitlines(keepends=True)
                            if not line.split() or line.split()[0] != name.encode())
        with tempfile.NamedTemporaryFile(dir=registry.parent, delete=False) as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(registry.stat().st_mode))
            stream.write(retained)
            stream.flush()
            os.fsync(stream.fileno())
            replacement = stream.name
        os.replace(replacement, registry)
        receipt.unlink()
        # Preserve leftover LOBs, utility output and unknown files. Recreating
        # uses a new location if needed; it never recursively removes leftovers.
        for path in (base / 'data', base / 'log', base / 'lob', base):
            try:
                path.rmdir()
            except OSError:
                pass
        print(f'Deleted {name}; any remaining files are preserved at {base}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('name', 'list', 'create', 'ensure', 'delete', 'recreate'))
    parser.add_argument('database', nargs='?', default='testdb')
    parser.add_argument('--load', choices=('demodb',))
    parser.add_argument('--expected-name', dest='expected_name')
    args = parser.parse_args()
    name = args.expected_name or args.database
    try:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,62}', name):
            raise ValueError('Invalid DB name')
        if args.load and args.action not in ('create', 'ensure', 'recreate'):
            raise ValueError('--load is only valid for creation')
        if os.environ.get('CUBRID_RUNTIME_READY') != '1':
            raise ValueError('Load the initialized workenv before DB use')
        root = Path(os.environ['CUBRID_DATABASES']).parent
        if root != Path.cwd() / '.cub-workenv':
            raise ValueError('Run from the selected worktree root')
        rows = registrations((root / 'databases/databases.txt').read_bytes())
        if args.action == 'name':
            print(name)
        elif args.action == 'list':
            print('\n'.join(rows), end='\n' if rows else '')
        elif args.action == 'ensure' and name in rows:
            print(f'Database already registered: {name}; unchanged')
        else:
            if args.action in ('delete', 'recreate'):
                delete(root, name)
            if args.action in ('create', 'ensure', 'recreate'):
                create(root, name, args.load, recreate=args.action == 'recreate')
    except (ValueError, OSError, KeyError, configparser.Error, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
