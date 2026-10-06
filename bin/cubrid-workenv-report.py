#!/usr/bin/env python3
"""Read-only views of cub-workenv schema 1; never allocate or load an environment."""
import argparse
import configparser
import json
import os
from pathlib import Path
import subprocess
import sys


def worktrees(root):
    result = subprocess.run(['git', '-C', str(root), 'worktree', 'list', '--porcelain', '-z'],
                            check=True, stdout=subprocess.PIPE)
    return [Path(os.fsdecode(field[9:])) for field in result.stdout.split(b'\0')
            if field.startswith(b'worktree ')]


def snapshot(root):
    root = root.resolve()
    result = {'worktree': str(root), 'state': None, 'error': None}
    marker = root / '.cub-workenv/state.json'
    try:
        state = json.loads(marker.read_text())
        if not isinstance(state, dict) or state.get('schema') != 1:
            raise ValueError('Unsupported state schema; use cub-workenv doctor')
        if not isinstance(state.get('allocation', {}), dict):
            raise ValueError('Invalid allocation object; use cub-workenv doctor')
        if state.get('worktree') != str(root):
            raise ValueError('State belongs to a different worktree; use cub-workenv doctor')
        result['state'] = state
        result['isolation'] = isolation(root, state)
        if result['isolation']['errors']:
            result['error'] = '; '.join(result['isolation']['errors'])
    except FileNotFoundError:
        if not root.is_dir():
            result['error'] = 'Worktree is missing'
        elif (root / '.cub-workenv').exists():
            result['error'] = 'Workenv directory exists without readable state.json'
    except (OSError, ValueError) as error:
        result['error'] = str(error)
    return result



def isolation(root, state):
    """Report expected selection and current disk settings, never execute env.sh."""
    allocation = state.get('allocation', {})
    install = state.get('install')
    tmp = allocation.get('tmp')
    port = allocation.get('master_port')
    env = {'CUBRID': install,
           'CUBRID_CONF_FILE': str(root / '.cub-workenv/conf/cubrid.conf'),
           'CUBRID_BROKER_CONF_FILE': str(root / '.cub-workenv/conf/cubrid_broker.conf'),
           'CUBRID_DATABASES': str(root / '.cub-workenv/databases'),
           'CUBRID_TMP': tmp, 'CUBRID_CUBRID_PORT_ID': str(port) if port is not None else None,
           'CUBRID_JAVA_HOME': state.get('java_home'),
           'PATH prefix': str(Path(install) / 'bin') if install else None,
           'LD_LIBRARY_PATH prefix': str(Path(install) / 'lib') if install else None}
    result = {'expected_environment': env, 'disk_settings': {}, 'databases': [], 'errors': [],
              'master_socket': str(Path(tmp) / f'CUBRID{port}') if tmp and port is not None else None,
              'pl_socket_pattern': str(Path(tmp) / 'sp_<database>.sock') if tmp else None,
              'pl_info_pattern': str(Path(install) / 'var/pl/pl_<database>.info') if install else None}
    for key in ('CUBRID_CONF_FILE', 'CUBRID_BROKER_CONF_FILE'):
        config = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=('#', ';'))
        try:
            with Path(env[key]).open() as stream:
                config.read_file(stream)
            wanted = {'cubrid_port_id', 'stored_procedure', 'stored_procedure_uds', 'stored_procedure_port',
                      'ha_mode', 'file_lock', 'master_shm_id', 'appl_server_shm_id', 'broker_port',
                      'service', 'admin_log_file', 'log_dir', 'error_log_dir'}
            result['disk_settings'][key] = {section: {k: v for k, v in config.items(section) if k in wanted}
                                            for section in config.sections()}
        except (OSError, configparser.Error) as error:
            result['errors'].append(f'{env[key]}: {error}')
    try:
        registry = root / '.cub-workenv/databases/databases.txt'
        names = set()
        for line in registry.read_text().splitlines():
            fields = line.split()
            if not fields or fields[0].startswith('#'):
                continue
            if len(fields) not in (4, 5) or fields[0] in names:
                raise ValueError('Malformed or duplicate database registration')
            name, data, host, log = fields[:4]
            names.add(name)
            result['databases'].append({'name': name, 'data': data, 'host': host, 'log': log,
                'lob': fields[4] if len(fields) == 5 else None,
                'data_realpath': str(Path(data).resolve()) if Path(data).is_absolute() else None,
                'log_realpath': str(Path(log).resolve()) if Path(log).is_absolute() else None,
                'pl_socket': str(Path(tmp) / f'sp_{name}.sock') if tmp else None,
                'pl_info': str(Path(install) / f'var/pl/pl_{name}.info') if install else None})
    except (OSError, ValueError) as error:
        result['errors'].append(f'Database registry: {error}')
    return result


def display(value):
    # Keep unusual paths and metadata from injecting terminal control characters.
    return str(value).encode('unicode_escape').decode() if value is not None else '-'


def shm(value):
    return f'{value:#010x} ({value})' if type(value) is int else display(value)


def details(record):
    root = Path(record['worktree'])
    state = record['state'] or {}
    allocation = state.get('allocation', {})
    fields = {
        'Worktree': root,
        'Saved state (not live health)': 'ERROR' if record['error'] else state.get('status', 'uninitialized'),
        'Stage': state.get('stage'), 'Preset': state.get('preset'),
        'Installation': state.get('install'),
        'Allocated master port': allocation.get('master_port'),
        'Allocated broker port': allocation.get('broker_port'),
        'Broker master SHM key': shm(allocation.get('broker_master_shm_id')),
        'Broker application SHM key': shm(allocation.get('broker_appl_server_shm_id')),
        'Temporary/socket directory': allocation.get('tmp'),
        'Java home': state.get('java_home'), 'Allocation state home': state.get('state_home'),
        'Settings directory': root / '.cub-workenv/conf',
        'Database registry': root / '.cub-workenv/databases/databases.txt',
        'Environment script': root / '.cub-workenv/env.sh',
    }
    if state.get('error'):
        fields['Initialization error'] = state['error']
    if record['error']:
        fields['Report error'] = record['error']
    for label, value in fields.items():
        print(f'{label}: {display(value)}')
    info = record.get('isolation')
    if info:
        print('\nExpected environment selection (not observed running-process values):')
        for key, value in info['expected_environment'].items():
            print(f'  {key}={display(value)}')
        for key in ('master_socket', 'pl_socket_pattern', 'pl_info_pattern'):
            print(f'{key}: {display(info[key])}')
        print('\nIsolation settings currently on disk (PL paths assume UDS enabled):')
        for source, sections in info['disk_settings'].items():
            for section, values in sections.items():
                for key, value in values.items():
                    print(f'  {source} [{display(section)}] {key}={display(value)}')
        print('\nRegistered databases (shared physical paths require sequential use):')
        for database in info['databases']:
            print('  ' + json.dumps(database, ensure_ascii=True))
        if not info['databases']:
            print('  None recorded.')
        for error in info['errors']:
            print(f'Inspection error: {display(error)}')
        print('Scope: managed host master/server/broker/PL. HA, Manager and containers are not allocated here.')


def summary(records):
    rows = [['WORKTREE', 'SAVED STATE', 'PRESET', 'MASTER', 'BROKER', 'MASTER SHM', 'APP SHM']]
    for record in records:
        state = record['state'] or {}
        allocation = state.get('allocation', {})
        rows.append([record['worktree'], 'ERROR' if record['error'] else state.get('status', 'uninitialized'),
                     state.get('preset'), allocation.get('master_port'), allocation.get('broker_port'),
                     shm(allocation.get('broker_master_shm_id')), shm(allocation.get('broker_appl_server_shm_id'))])
    rows = [[display(cell) for cell in row] for row in rows]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for row in rows:
        print('  '.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
    print('\nSaved allocations only; ready does not mean running or healthy. Use workenv::doctor for live checks.')
    for record in records:
        if record['error']:
            print(f"{display(record['worktree'])}: {display(record['error'])}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'all', 'json', 'all-json', 'config', 'doctor-all', 'all-details'])
    parser.add_argument('--worktree', type=Path, default=Path.cwd())
    args = parser.parse_args()
    roots = worktrees(args.worktree) if args.command in ('all', 'all-json', 'doctor-all', 'all-details') else [args.worktree]
    if args.command == 'doctor-all':
        failed = False
        for root in roots:
            print(f'\n=== {display(root)} ===', flush=True)
            result = subprocess.run([os.environ.get('CUB_WORKENV_CLI', 'cub-workenv'),
                                     'doctor', '--worktree', str(root)])
            failed |= result.returncode != 0
        return int(failed)
    if args.command == 'config':
        for name in ('cubrid.conf', 'cubrid_broker.conf'):
            path = args.worktree / '.cub-workenv/conf' / name
            print(f'=== {display(path)} ===')
            print(path.read_text(), end='\n')
        return 0
    records = [snapshot(root) for root in roots]
    if args.command in ('json', 'all-json'):
        print(json.dumps(records if args.command == 'all-json' else records[0], indent=2))
    elif args.command == 'all-details':
        for record in records:
            details(record)
            print()
    elif args.command == 'all':
        summary(records)
    else:
        details(records[0])
    return int(any(record['error'] or record.get('isolation', {}).get('errors') for record in records))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'workenv report: {error}', file=sys.stderr)
        sys.exit(1)
