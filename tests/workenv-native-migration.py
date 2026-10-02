#!/usr/bin/env python3
"""Native public-recipe acceptance on owned installation copies; retain evidence.

Native output goes to regular files because daemons can inherit output pipes.
Never opens a user's DB. Fixtures remain for review and explicit owned cleanup.
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import stat
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument('--install', type=Path, required=True)
parser.add_argument('--expect-old-failure', action='store_true')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
root = Path(tempfile.mkdtemp(prefix='cwe-migration-'))
evidence = root / 'evidence'
evidence.mkdir()
cli = os.environ.get('CUB_WORKENV_CLI', 'cub-workenv')
record = {'root': str(root), 'source_install': str(args.install), 'steps': [],
          'tooling_head': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
          'source_binary_sha256': hashlib.sha256((args.install / 'bin/cubrid').read_bytes()).hexdigest()}
# Freeze shell scripts: rewriting a foreground supervisor while Bash reads it
# changes the running test. Subsequent edits belong to the next evidence run.
snapshot = root / 'tooling'
for part in ('bin', 'stow'):
    shutil.copytree(repo / part, snapshot / part, symlinks=True)
record['tooling_files_sha256'] = {str(p.relative_to(snapshot)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in snapshot.rglob('*') if p.is_file() and not p.is_symlink()}
repo = snapshot
instances = []


def save():
    (evidence / 'results.json').write_text(json.dumps(record, indent=2) + '\n')


def run(label, command, instance, expected=0):
    log = evidence / (label + '.txt')
    start = time.monotonic()
    with log.open('w') as stream:
        result = subprocess.run(list(map(str, command)), cwd=instance['worktree'], env=instance['env'],
                                stdout=stream, stderr=subprocess.STDOUT, timeout=120)
    record['steps'].append({'label': label, 'command': list(map(str, command)),
                            'returncode': result.returncode, 'seconds': time.monotonic() - start})
    save()
    assert result.returncode == expected, (label, log.read_text())
    return log.read_text()


def prepare(name):
    worktree = root / name
    worktree.mkdir()
    install = root / (name + '-install')
    install.mkdir()
    env = dict(os.environ, MY_CUBRID=str(repo), PRESET_MODE='debug_gcc',
               CUBRID=str(install), CUBRID_BUILD_DIR=str(worktree / 'build'),
               CUB_WORKENV_INSTALL=str(install), CUB_WORKENV_CLI=cli)
    instance = {'worktree': worktree, 'install': install, 'env': env}
    instances.append(instance)
    for part in ('bin', 'lib', 'conf', 'msg', 'locales', 'timezones', 'vm', 'demo'):
        if (args.install / part).exists():
            subprocess.run(['cp', '-a', '--reflink=auto', str(args.install / part),
                            str(install / part)], check=True)
    for part in ('log', 'var/pl', 'var/CUBRID_SOCK'):
        (install / part).mkdir(parents=True, exist_ok=True)
    for name in ('justfile', '.just'):
        (worktree / name).symlink_to(repo / 'stow/cubrid' / name)
    run(worktree.name + '-init-no-db', [cli, 'init', '--no-db', '--worktree', worktree,
        '--install', install, '--preset', env['PRESET_MODE'], '--state-home', root / 'host',
        '--port-start', '51000', '--port-end', '51999',
        '--java-home', '/home/vimkim/.local/share/mise/installs/java/temurin-8.0.462+8'], instance)
    loaded = subprocess.check_output(['bash', '-c', 'source .cub-workenv/env.sh && env -0'],
                                     cwd=worktree, env=env)
    instance['env'] = dict(item.decode().split('=', 1) for item in loaded.split(b'\0') if b'=' in item)
    instance['state'] = json.loads((worktree / '.cub-workenv/state.json').read_text())
    return instance


def sql(label, instance, statement, database='testdb', mode='-C'):
    return run(label, ['csql', mode, '-u', 'dba', '-c', statement, database], instance)


def owned(instance):
    found = []
    for process in Path('/proc').glob('[0-9]*'):
        try:
            values = (process / 'environ').read_bytes().split(b'\0')
            if f"CUBRID={instance['install']}".encode() in values:
                found.append(int(process.name))
        except OSError:
            pass
    return found


print(root, flush=True)
try:
    a = prepare('a')
    runtime = a['worktree'] / '.cub-workenv'
    registry = runtime / 'databases/databases.txt'
    assert registry.read_bytes() == b''
    assert not (runtime / 'db/testdb').exists()
    if args.expect_old_failure:
        output = run('create-testdb-before', ['just', 'db::create-testdb'], a, expected=1)
        assert 'not registered' in output
        assert registry.read_bytes() == b''
        assert not (runtime / 'db/testdb').exists()
        record['verdict'] = 'old recipe defect reproduced; no DB created'
    else:
        run('create-testdb', ['just', 'db::create-testdb'], a)
        before = registry.read_bytes()
        primary = runtime / 'db/testdb/data/testdb'
        identity = primary.stat().st_ino
        run('duplicate-create', ['just', 'db::create-testdb'], a, expected=1)
        assert registry.read_bytes() == before and primary.stat().st_ino == identity
        sql('standalone-sql', a, 'create table marker (id integer); insert into marker values (262); commit;', mode='-S')
        # Default CLI-created DBs also have provenance; reuse does not invent it.
        run('create-extra', [cli, 'create-db', 'extra'], a)
        assert (runtime / 'created-extra.json').is_file()
        external = root / 'external-db'
        run('create-external', [cli, 'create-db', 'outside', '--path', external], a)
        external_before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in external.rglob('*') if p.is_file()}
        registry_before = registry.read_bytes()
        run('reject-external-delete', ['just', 'db::delete', 'outside'], a, expected=1)
        assert registry.read_bytes() == registry_before
        assert external_before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in external.rglob('*') if p.is_file()}
        # An added volume outside the owned DB root makes the whole deletion fail.
        vinf = runtime / 'db/testdb/data/testdb_vinf'
        original_vinf = vinf.read_bytes()
        vinf.write_bytes(original_vinf + f'2 {external}/data/outside\n'.encode())
        run('reject-mixed-volumes', ['just', 'db::delete-testdb'], a, expected=1)
        assert registry.read_bytes() == registry_before and primary.exists()
        vinf.write_bytes(original_vinf)  # Restore only this harness's injected line.
        run('start-testdb', ['just', 'db::start-testdb'], a)
        busy = run('reject-running-delete', ['just', 'db::delete-testdb'], a, expected=1)
        assert registry.read_bytes() == registry_before
        assert '262' in sql('health-after-refused-delete', a, 'select id from marker;')
        run('busy-install', [repo / 'bin/cubrid-build-coordinator.sh', 'install', '0'], a, expected=75)
        run('select-server', [repo / 'bin/my-cubrid-process-select', 'server'], a)
        b = prepare('b')
        run('b-create', ['just', 'db::create-testdb'], b)
        run('b-start', ['just', 'db::start-testdb'], b)
        sql('b-sql', b, 'create table marker (id integer); insert into marker values (263); commit;')
        run('a-stop', ['just', 'db::stop-testdb'], a)
        assert '263' in sql('b-unaffected', b, 'select id from marker;')
        run('create-demodb', ['just', 'db::create-demodb'], a)
        assert '6677' in sql('demodb-loaded', a, 'select count(*) from athlete;', 'demodb', '-S')
        run('recreate-demodb', ['just', 'db::recreate-demodb'], a)
        sql('demodb-reloaded', a, 'select count(*) from athlete;', 'demodb', '-S')
        # Real composition stops only the selected DB and recreates it explicitly.
        run('a-restart', ['just', 'db::start-testdb'], a)
        run('stop-recreate-start', ['just', 'db::stop-recreate-start-testdb'], a)
        sql('fresh-recreated', a, 'create table marker (id integer); insert into marker values (264); commit;')
        assert '263' in sql('b-unaffected-after-recreate', b, 'select id from marker;')
        # Reentry and switching use the public artifact; no legacy authority.
        for n in range(3):
            output = run(f'reentry-{n}', ['bash', '-c',
                'eval "$("$CUB_WORKENV_CLI" env --worktree "$PWD" --preset "$PRESET_MODE" --install "$CUBRID")" && csql -C -u dba -c "select id from marker;" testdb'], a)
            assert '264' in output
        switched = run('a-to-b', ['bash', '-c',
            'source "$1/.cub-workenv/env.sh" && csql -C -u dba -c "select id from marker;" testdb; '
            'source "$2/.cub-workenv/env.sh" && csql -C -u dba -c "select id from marker;" testdb',
            'bash', a['worktree'], b['worktree']], a)
        assert '264' in switched and '263' in switched
        selected_config = runtime / 'conf/cubrid.conf'
        original_install_config = (a['install'] / 'conf/cubrid.conf').read_bytes()
        run('restore-allocated-port', ['just', 'db::set-port'], a)
        parsed = configparser.ConfigParser(); parsed.read(selected_config)
        assert parsed.getint('common', 'cubrid_port_id') == a['state']['allocation']['master_port']
        assert (a['install'] / 'conf/cubrid.conf').read_bytes() == original_install_config
        # Doctor is read-only, including ready live environments.
        watched = [runtime / 'state.json', runtime / 'env.sh', registry, selected_config]
        snapshot = [p.read_bytes() for p in watched]
        stale = Path(a['state']['allocation']['tmp']) / 'sp_demodb.sock'
        socket_lines = Path('/proc/net/unix').read_text()
        expect_stale = stale.exists() and str(stale) not in socket_lines
        output = run('doctor-live', [cli, 'doctor', '--worktree', a['worktree']], a, expected=1 if expect_stale else 0)
        assert snapshot == [p.read_bytes() for p in watched]
        if expect_stale:
            assert 'stale or unconfirmed filesystem entry' in output
            assert stat.S_ISSOCK(stale.lstat().st_mode) and stale.stat().st_uid == os.getuid()
            for pid in owned(a):
                assert b'demodb' not in Path(f'/proc/{pid}/cmdline').read_bytes()
            assert str(stale) not in Path('/proc/net/unix').read_text()
            stale.unlink()  # Exact known fixture-created unbound socket, outside doctor.
            record['owned_stale_socket_cleanup'] = str(stale)
            run('doctor-after-owned-socket-cleanup', [cli, 'doctor', '--worktree', a['worktree']], a)
        run('delete-cli-created-extra', ['just', 'db::delete', 'extra'], a)
        assert {'outside', 'demodb'} <= {line.split()[0] for line in registry.read_text().splitlines() if line.strip()}
        # Compile a real tiny target, explicitly stop the live selected instance,
        # then install that target alongside copied CUBRID. No engine rebuild claim.
        (a['worktree'] / 'probe.c').write_text('int main(void) { return 0; }\n')
        (a['worktree'] / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.21)\nproject(probe C)\n'
            'add_executable(probe probe.c)\ninstall(TARGETS probe DESTINATION bin)\n')
        (a['worktree'] / 'CMakePresets.json').write_text(json.dumps({'version': 3,
            'configurePresets': [{'name': 'debug_gcc', 'generator': 'Ninja',
                                  'binaryDir': '${sourceDir}/build'}],
            'buildPresets': [{'name': 'debug_gcc', 'configurePreset': 'debug_gcc'}]}))
        run('configure-build-fixture', [repo / 'bin/cubrid-build-coordinator.sh', 'configure'], a)
        registry_before_build = registry.read_bytes()
        run('explicit-stop-and-build', [repo / 'bin/cubrid-build-coordinator.sh', 'stop-and-build'], a)
        assert registry.read_bytes() == registry_before_build
        assert (a['install'] / 'bin/probe').is_file()
        run('restart-after-build', ['just', 'db::start-testdb'], a)
        assert '264' in sql('data-preserved-after-stop-build', a, 'select id from marker;')
        assert '263' in sql('b-unaffected-after-stop-build', b, 'select id from marker;')
        record['verdict'] = 'pass'
finally:
    for instance in instances:
        if 'state' not in instance:
            continue
        # Stop only this harness's instance. No broad kill/IPC cleanup.
        for command in (['cubrid', 'server', 'stop', 'testdb'], ['cubrid', 'broker', 'stop'], ['cubrid', 'service', 'stop']):
            with (evidence / f"{instance['worktree'].name}-cleanup.txt").open('a') as log:
                subprocess.run(command, cwd=instance['worktree'], env=instance['env'], stdout=log,
                               stderr=subprocess.STDOUT, timeout=45)
        deadline = time.monotonic() + 15
        while owned(instance) and time.monotonic() < deadline:
            time.sleep(0.2)
    record['remaining_owned_processes'] = {str(i['worktree']): owned(i) for i in instances}
    save()
    print(record.get('verdict', 'failed; inspect evidence'), flush=True)
    assert not any(record['remaining_owned_processes'].values()), record['remaining_owned_processes']
