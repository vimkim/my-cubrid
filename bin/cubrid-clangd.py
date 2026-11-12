#!/usr/bin/env python3

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile

MODES = {
    'server': ('server', 'neutral', 'sa', 'cs'),
    'sa': ('sa', 'neutral', 'server', 'cs'),
    'cs': ('cs', 'neutral', 'sa', 'server'),
}
MACROS = {'SERVER_MODE': 'server', 'SA_MODE': 'sa', 'CS_MODE': 'cs'}
CORE = {'server': 'cubrid', 'sa': 'cubridsa', 'cs': 'cubridcs'}
PRODUCTS = ('cub_broker', 'cubrid_broker', 'cub_cas', 'cas_common_lib',
            'broker_monitor', 'broker_log_converter', 'cub_master', 'cubrid-bin', 'cmdep')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def preset_name(preset):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', preset):
        raise ValueError(f'Invalid preset: {preset!r}')
    return preset


def source_db(root, preset):
    return root / f'build_preset_{preset}' / 'compile_commands.json'


def parse_entry(entry):
    directory = Path(entry['directory']).resolve()
    source = (directory / entry['file']).resolve()
    argv = entry.get('arguments')
    if argv is None:
        argv = shlex.split(entry['command'])
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise ValueError(f'Invalid arguments for {source}')
    enabled = set()
    output = entry.get('output', '')
    equivalent = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('-D', '-U'):
            i += 1
            if i >= len(argv):
                raise ValueError(f'Missing argument for {arg} in {source}')
            macro = argv[i].split('=', 1)[0]
            operation = arg
        else:
            macro = arg[2:].split('=', 1)[0]
            operation = arg[:2]
        if operation in ('-D', '-U') and macro in MACROS:
            if operation == '-D':
                enabled.add(MACROS[macro])
            else:
                enabled.discard(MACROS[macro])
        if arg in ('-o', '-MF', '-MT', '-MQ', '-MJ'):
            i += 1
            if i >= len(argv):
                raise ValueError(f'Missing argument for {arg} in {source}')
            if arg == '-o':
                output = argv[i]
        elif any(arg.startswith(x) and len(arg) > len(x) for x in ('-o', '-MF', '-MT', '-MQ', '-MJ')):
            if arg.startswith('-o'):
                output = arg[2:]
        elif arg not in ('-MD', '-MMD', '-MP'):
            equivalent.append(arg)
            if arg in ('-D', '-U'):
                equivalent.append(argv[i])
        i += 1
    if len(enabled) > 1:
        raise ValueError(f'Conflicting mode macros for {source}: {sorted(enabled)}')
    mode = next(iter(enabled), 'neutral')
    match = re.search(r'(?:^|/)CMakeFiles/([^/]+)\.dir(?:/|$)', output)
    target = match.group(1) if match else None
    return source, mode, target, (str(directory), tuple(equivalent))


def select_entries(data, root, mode):
    entries = json.loads(data)
    if not isinstance(entries, list):
        raise ValueError('Compilation database must be a JSON array')
    groups = {}
    for entry in entries:
        source, native_mode, target, equivalent = parse_entry(entry)
        is_test = source.is_relative_to(root / 'unit_tests')
        target_rank = (0 if target and target.startswith('unittest') else 1) if is_test else (0 if CORE.get(native_mode) == target and target else 1)
        product_rank = PRODUCTS.index(target) if target in PRODUCTS and not is_test else len(PRODUCTS)
        rank = ((target_rank, MODES[mode].index(native_mode), product_rank) if is_test
                else (MODES[mode].index(native_mode), target_rank, product_rank))
        groups.setdefault(source, []).append((rank, equivalent, target, native_mode, entry))
    result, fallback = [], []
    for source, candidates in sorted(groups.items()):
        best_rank = min(item[0] for item in candidates)
        best = [item for item in candidates if item[0] == best_rank]
        if len({item[1] for item in best}) != 1:
            details = ', '.join(f'{item[2] or "unknown target"} ({item[3]})' for item in best)
            raise ValueError(f'Ambiguous commands for {source}: {details}')
        chosen = min(best, key=lambda item: json.dumps(item[4], sort_keys=True))
        result.append(chosen[4])
        if chosen[3] != mode:
            fallback.append(str(source))
    return result, fallback


def alias(root):
    link = root / 'compile_commands.json'
    if not link.is_symlink():
        if link.exists():
            raise ValueError(f'Refusing to replace regular file: {link}')
        return None
    target = (root / os.readlink(link)).resolve()
    try:
        rel = target.relative_to(root / '.lsp')
        if len(rel.parts) == 4 and rel.name == 'compile_commands.json':
            receipt = json.loads((target.parent / 'receipt.json').read_text())
            if (receipt['root'] == str(root) and receipt['preset'] == rel.parts[0]
                    and receipt['mode'] == rel.parts[1] and receipt['mode'] in MODES
                    and receipt['generation'] == rel.parts[2]):
                return receipt
    except (ValueError, OSError, KeyError, json.JSONDecodeError):
        pass
    if target.parent.parent == root and re.fullmatch(r'build_preset_[A-Za-z0-9_.-]+', target.parent.name) and target.name == 'compile_commands.json' and target.is_file():
        return {'preset': target.parent.name.removeprefix('build_preset_'), 'mode': 'server', 'legacy': True}
    raise ValueError(f'Refusing to replace unrecognized link: {link} -> {os.readlink(link)}')


def snapshot(root, preset, mode, data=None):
    if data is None:
        entries, fallback, fingerprint = None, [], None
    else:
        entries, fallback = select_entries(data, root, mode)
        fingerprint = digest(data)
    content = json.dumps(entries, indent=2, ensure_ascii=False).encode() + b'\n' if entries is not None else None
    generation = digest(json.dumps([str(root), preset, mode, fingerprint, digest(content) if content else None, fallback], sort_keys=True).encode())
    receipt = {'root': str(root), 'preset': preset, 'mode': mode, 'generation': generation,
               'source_sha256': fingerprint, 'fallback': fallback}
    parent = root / '.lsp' / preset / mode
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / generation
    if not destination.exists():
        temp = Path(tempfile.mkdtemp(prefix='.tmp-', dir=parent))
        try:
            (temp / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
            if content is not None:
                (temp / 'compile_commands.json').write_bytes(content)
            os.rename(temp, destination)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
    else:
        if json.loads((destination / 'receipt.json').read_text()) != receipt or (content is not None and (destination / 'compile_commands.json').read_bytes() != content) or (content is None and (destination / 'compile_commands.json').exists()):
            raise ValueError(f'Snapshot does not match its receipt: {destination}')
    return destination / 'compile_commands.json'


def activate(root, target):
    alias(root)
    link = root / 'compile_commands.json'
    fd, name = tempfile.mkstemp(prefix='.compile_commands.json.', dir=root)
    os.close(fd)
    temp = Path(name)
    temp.unlink()
    try:
        temp.symlink_to(os.path.relpath(target, root))
        os.replace(temp, link)
    finally:
        temp.unlink(missing_ok=True)


def check_preset(root, preset):
    env = root / '.env'
    if not env.exists():
        return
    saved = None
    for line in env.read_text().splitlines():
        match = re.match(r'^\s*(?:export\s+)?PRESET_MODE\s*=\s*(.*)$', line)
        if match:
            values = shlex.split(match.group(1), comments=True)
            if len(values) != 1:
                raise ValueError('Cannot read PRESET_MODE in .env; select the preset again')
            saved = values[0]
    if saved is not None and saved != preset:
        raise ValueError(f'Preset environment is stale ({preset}); .env selects {saved}. Reload direnv')


def set_preset(root, preset):
    current = alias(root)
    env = root / '.env'
    text = env.read_text() if env.exists() else ''
    lines = text.splitlines(keepends=True)
    pattern = re.compile(r'^\s*(?:export\s+)?PRESET_MODE\s*=')
    updated, replaced = [], False
    for line in lines:
        if pattern.match(line):
            if not replaced:
                updated.append(f'PRESET_MODE={preset}\n')
                replaced = True
        else:
            updated.append(line)
    if not replaced:
        if updated and not updated[-1].endswith('\n'):
            updated[-1] += '\n'
        updated.append(f'PRESET_MODE={preset}\n')
    fd, name = tempfile.mkstemp(prefix='.env.', dir=root)
    try:
        with os.fdopen(fd, 'w') as file:
            file.writelines(updated)
        if env.exists():
            os.chmod(name, env.stat().st_mode & 0o7777)
        if current and current['preset'] != preset:
            activate(root, snapshot(root, preset, current['mode']))
        os.replace(name, env)
    finally:
        Path(name).unlink(missing_ok=True)
    print(f'Selected preset: {preset}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('select', 'refresh', 'auto-refresh', 'status', 'preset'))
    parser.add_argument('value', nargs='?')
    parser.add_argument('--preset')
    args = parser.parse_args()
    root = Path.cwd().resolve()
    preset = preset_name(args.value if args.action == 'preset' else (args.preset or os.environ.get('PRESET_MODE', '')))
    if args.action == 'select' and args.value not in MODES:
        parser.error('select requires server, sa, or cs')
    (root / '.lsp').mkdir(exist_ok=True)
    with (root / '.lsp' / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'preset':
            set_preset(root, preset)
            return
        check_preset(root, preset)
        current = alias(root)
        mode = args.value if args.action == 'select' else (current['mode'] if current else 'server')
        database = source_db(root, preset)
        if args.action == 'status':
            print(f'Preset: {preset}\nMode: {mode}')
            if not current:
                print('State: not selected')
            elif current.get('legacy'):
                print('State: legacy build database')
            elif current['preset'] != preset:
                print(f'State: preset mismatch (selection: {current["preset"]}); refresh required')
            elif current['source_sha256'] is None:
                print('State: pending configuration')
            else:
                selected = root / '.lsp' / current['preset'] / mode / current['generation'] / 'compile_commands.json'
                stale = not selected.is_file() or not database.is_file() or digest(database.read_bytes()) != current['source_sha256']
                print(f'State: {"stale; refresh required" if stale else "current"}')
                print(f'Fallback sources: {len(current["fallback"])}')
                for source in current['fallback']:
                    print(f'  {source}')
            return
        if args.action == 'auto-refresh' and not current and not database.is_file():
            return
        if not database.is_file():
            raise ValueError(f'No compilation database for {preset}: {database}; run just configure')
        target = snapshot(root, preset, mode, database.read_bytes())
        changed = (root / 'compile_commands.json').resolve() != target.resolve()
        if changed:
            activate(root, target)
        receipt = json.loads((target.parent / 'receipt.json').read_text())
        print(f'Selected {mode} for {preset}; {len(receipt["fallback"])} fallback sources')
        if changed:
            print('Restart running clangd servers (editor, Claude Code LSP, Serena); they keep the previous commands.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'cubrid-clangd: {exc}', file=sys.stderr)
        sys.exit(1)
