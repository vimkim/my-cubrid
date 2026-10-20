#!/usr/bin/env python3
"""Refresh personal CUBRID tools through each checkout's just sync recipe."""

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# Add personal tool checkouts here once their sync recipe installs local commands.
# Keep sites and other projects whose sync recipe publishes content out of this list.
PROJECTS = ("cubrid-conf-tui", "cubrid-build-coordinator", "cubrid-workenv")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install or refresh personal CUBRID tools by running just sync.",
        epilog=(
            "Uses the current local source; update checkouts separately when needed. "
            "Defaults: ~/gh/cubrid-conf-tui, ~/gh/cubrid-build-coordinator, "
            "and ~/gh/cubrid-workenv. "
            "Pass directories to sync other tools."
        ),
    )
    parser.add_argument(
        "projects",
        nargs="*",
        type=Path,
        metavar="DIRECTORY",
        help="project directories (replaces the default project list)",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--list", action="store_true", help="list selected checkouts")
    action.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show commands without running them",
    )
    args = parser.parse_args()
    projects = args.projects or [Path.home() / "gh" / name for name in PROJECTS]
    projects = list(dict.fromkeys(path.expanduser().absolute() for path in projects))

    if args.list:
        for project in projects:
            print(project)
        return 0

    just = shutil.which("just")
    if not just and not args.dry_run:
        print(
            "daily-update-cubrid: just is not installed or not on PATH", file=sys.stderr
        )
        return 1

    failed = []
    for project in projects:
        print(f"\n── {project.name} ──", flush=True)
        # Pin the recipe file so just never discovers an unrelated parent recipe.
        if not project.is_dir() or not (project / "justfile").is_file():
            print(
                f"FAILED: missing project directory or local justfile: {project}",
                flush=True,
            )
            failed.append(project)
            continue
        command = [just or "just", "--justfile", "./justfile", "sync"]
        print(f"cd {shlex.quote(str(project))} && {shlex.join(command)}", flush=True)
        if args.dry_run:
            continue
        try:
            result = subprocess.run(command, cwd=project, check=False)
        except OSError as error:
            print(f"FAILED: {error}", flush=True)
            failed.append(project)
            continue
        if result.returncode:
            print(f"FAILED: just sync exited {result.returncode}", flush=True)
            failed.append(project)
        else:
            print(f"{project.name}: updated", flush=True)

    if failed:
        print(
            "\nFailed projects: " + ", ".join(str(path) for path in failed),
            file=sys.stderr,
        )
        return 1
    print("\nPreview complete." if args.dry_run else "\nCUBRID tools updated.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ndaily-update-cubrid: interrupted", file=sys.stderr)
        sys.exit(130)
