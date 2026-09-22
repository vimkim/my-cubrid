"""Manifest authority and lifecycle locking for the personal database helpers."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def runtime_guard():
    loader = importlib.machinery.SourceFileLoader("_runtime_guard", str(Path(__file__).with_name("my-cubrid-runtime")))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


@contextmanager
def ready_database(*, lifecycle_operation: bool):
    guard = runtime_guard()
    worktree = guard.resolve_worktree(None)
    preset = os.environ.get("PRESET_MODE")
    if not preset:
        raise ValueError("A ready manifest and PRESET_MODE are required; run explicit runtime initialization first.")
    selection = guard.RuntimeSelection(worktree, guard.resolve_git_common_dir(worktree), preset)
    lock = guard.state_root() / "registry.lock"
    if not lock.exists():
        raise ValueError("A ready worktree manifest is required; run explicit runtime initialization first.")
    descriptor = guard.open_private_lock(lock)
    database_lock = None
    try:
        # Retain the generation through lifecycle; guard mutations need this lock exclusively.
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        adapter = guard.observation_adapter()
        identifier = guard.runtime_id(adapter, worktree)
        if identifier is None:
            raise ValueError("A ready worktree manifest is required.")
        manifest_path = guard.state_root() / "worktrees" / identifier / "manifest.json"
        retained = guard.existing_bundle(manifest_path, identifier, selection)
        if retained is None:
            raise ValueError("A ready worktree manifest is required.")
        bundle, _ = retained
        transaction_path = manifest_path.with_name("transaction.json")
        transaction = guard.read_transaction(transaction_path) if transaction_path.exists() else None
        registry = guard.load_registry(guard.state_root() / "allocations.json")
        manifest = guard.require_transaction_generation(transaction, manifest_path, registry, identifier)
        if manifest is None or manifest["state"] != "ready" or (transaction and transaction["state"] != "ready"):
            raise ValueError("A ready worktree manifest is required.")
        guard.require_database_path(adapter, bundle.database_registry, "directory")
        database_lock = guard.open_private_lock(bundle.database_registry / ".pwddb.lock")
        fcntl.flock(database_lock, fcntl.LOCK_EX if lifecycle_operation else fcntl.LOCK_SH)
        # A preceding helper may have been running createdb. Observe only after it exits.
        result, status = guard.validate(adapter, selection)
        if status:
            raise ValueError("A ready worktree manifest is required. " + guard.render_human(result).strip())
        yield guard, adapter, bundle
    finally:
        if database_lock is not None:
            os.close(database_lock)
        os.close(descriptor)


def lifecycle(guard, adapter, bundle, action: str, template: str | None) -> None:
    environment = dict(os.environ, **guard.runtime_environment_values(bundle))
    environment["PATH"] += os.pathsep + os.environ.get("PATH", "")
    executable = bundle.executable_directory / "cubrid"
    schema = bundle.installation_root / "demo" / "demodb_schema"
    objects = bundle.installation_root / "demo" / "demodb_objects"
    if template and (not schema.is_file() or not objects.is_file()):
        raise ValueError("Cannot read demodb schema/objects under CUBRID/demo")

    def run(*arguments: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(executable), *arguments], env=environment,
                              cwd=bundle.data_root, text=True, check=True,
                              stdout=subprocess.PIPE if capture else None)

    storage = guard.inspect_database_storage(adapter, bundle.database_name, bundle.database_registry, required=False)
    exists = storage is not None
    name = bundle.database_name
    if action == "ensure" and exists:
        print(f"Database already exists: {name}")
        return
    if action == "create" and exists:
        raise ValueError(f"Database already exists: {name}")
    if action in ("recreate", "delete") and exists:
        status = run("server", "status", capture=True).stdout
        if any(len(row) >= 2 and row[0] in ("Server", "HA-Server") and row[1] == name
               for row in (line.split() for line in status.splitlines())):
            run("server", "stop", name)
        run("deletedb", name)
    if action == "delete":
        print(f"Database absent: {name}")
        return
    arguments = ["createdb", "--db-volume-size=20M", "--log-volume-size=20M"]
    if template:
        arguments.append("--db-page-size=16K")
    arguments += [name, "en_US.utf8", "-F", str(bundle.data_root),
                  "-L", str(bundle.log_root), "-B", str(bundle.lob_root)]
    run(*arguments)
    if template:
        try:
            run("loaddb", "-u", "dba", "-s", str(schema), "-d", str(objects), name)
        except subprocess.CalledProcessError as error:
            raise ValueError(f"demodb load failed; database retained for inspection: {name}") from error
    print(f"Created database: {name}")


def main(*, name_only: bool = False) -> int:
    parser = argparse.ArgumentParser(description="Use the ready worktree manifest's database name and storage.")
    if not name_only:
        parser.add_argument("action", choices=("ensure", "create", "recreate", "delete"))
        parser.add_argument("--load", choices=("demodb",))
    arguments = parser.parse_args()
    try:
        if not name_only and arguments.action == "delete" and arguments.load:
            raise ValueError("--load is only valid for ensure/create/recreate")
        with ready_database(lifecycle_operation=not name_only) as (guard, adapter, bundle):
            if name_only:
                print(bundle.database_name)
            else:
                old_umask = os.umask(0o077)
                try:
                    lifecycle(guard, adapter, bundle, arguments.action, arguments.load)
                finally:
                    os.umask(old_umask)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
