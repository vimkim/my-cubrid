#!/usr/bin/env python3
"""Refresh and apply dotfiles, then update clean CUBRID tool checkouts."""

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# Paths are relative to the user's home and preserve the existing checkouts.
# Add tools only when their installation command installs local tools, not content.
# Owner's workflow decision (2026-10-22): exclude grill-tui,
# gh-pr-comments-fetch, cubrid-dev2-pr, and volmap from both daily updaters.
# See CUBRID.md and vimkim/dotfiles docs/daily-update.md for the decision.
PROJECTS = {
    "cubrid-conf-tui": "gh/cubrid-conf-tui",
    "cubrid-build-coordinator": "gh/cubrid-build-coordinator",
    "cubrid-workenv": "gh/cubrid-workenv",
    "cubrid-jira": "gh/cubrid-jira",
    "cubrid-ci": "gh/cubrid-ci",
    "cubrid-qahome": "gh/cubrid-qahome-fetcher",
    "csql-with-history": "gh/csql-with-history",
}

# Reuse each accepted project's existing installation interface.
INSTALL_COMMANDS = {
    "cubrid-ci": ("just", "--justfile", "./justfile", "install"),
    "cubrid-qahome": ("uv", "tool", "install", "--reinstall", "."),
}


class Skipped(Exception):
    """The checkout or installed state must be preserved."""


class Failed(Exception):
    """An update operation failed."""


def git(project, *args):
    return subprocess.run(
        ["git", "-C", str(project), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def update_dotfiles(*, dry_run=False):
    print("\n── dotfiles ──", flush=True)
    command = ["daily-update", "--dotfiles-only"]
    print(shlex.join(command), flush=True)
    if dry_run:
        print("# git fetch + git merge --ff-only, then chezmoi-apply-unmodified", flush=True)
        return
    if not shutil.which(command[0]):
        raise Failed("daily-update is not installed or not on PATH; install it from dotfiles")
    result = subprocess.run(command, check=False)
    if result.returncode == 2:
        raise Skipped("partial/skipped (daily-update --dotfiles-only exit 2)")
    if result.returncode:
        raise Failed(f"daily-update --dotfiles-only exited {result.returncode}")


def refresh(project, *, github=None, dry_run=False):
    if project.is_symlink() or not (project / ".git").is_dir():
        raise Skipped("requires an independent primary checkout")
    root = git(project, "rev-parse", "--show-toplevel")
    if root.returncode or Path(root.stdout.strip()) != project.resolve():
        raise Skipped("requires an independent primary checkout")
    status = git(project, "status", "--porcelain", "--untracked-files=all")
    if status.returncode:
        raise Failed("cannot inspect checkout")
    if status.stdout:
        raise Skipped("dirty checkout")
    branch = git(project, "symbolic-ref", "--quiet", "--short", "HEAD")
    upstream = git(project, "rev-parse", "--abbrev-ref", "@{upstream}")
    if (
        branch.returncode
        or upstream.returncode
        or branch.stdout.strip() != "main"
        or upstream.stdout.strip() != "origin/main"
    ):
        raise Skipped("requires main tracking origin/main")
    if github:
        origin = git(project, "config", "--get", "remote.origin.url")
        if origin.returncode or origin.stdout.strip() not in {
            f"https://github.com/{github}",
            f"https://github.com/{github}.git",
            f"git@github.com:{github}",
            f"git@github.com:{github}.git",
        }:
            raise Skipped("unexpected origin")
    commands = (
        ["git", "fetch", "--", "origin", "refs/heads/main:refs/remotes/origin/main"],
        ["git", "merge", "--ff-only", "--", "origin/main"],
    )
    for command in commands:
        print(shlex.join(command), flush=True)
        if dry_run:
            continue
        if command[1] == "merge":
            ancestor = git(project, "merge-base", "--is-ancestor", "HEAD", "origin/main")
            if ancestor.returncode == 1:
                raise Skipped("ahead or diverged checkout")
            if ancestor.returncode:
                raise Failed("cannot compare checkout with origin/main")
        if subprocess.run(command, cwd=project, check=False).returncode:
            raise Failed(f"{command[1]} failed")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh and apply dotfiles, then fetch, fast-forward and install personal CUBRID tools.",
        epilog=(
            "Requires clean primary checkouts on main tracking origin/main. "
            "Defaults: " + ", ".join(f"~/{path}" for path in PROJECTS.values()) + ". "
            "Pass directories to update other tools."
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
    defaults = {Path.home() / path: name for name, path in PROJECTS.items()}
    projects = args.projects or list(defaults)
    projects = list(dict.fromkeys(path.expanduser().absolute() for path in projects))

    if args.list:
        for project in projects:
            print(project)
        return 0

    commands = {
        project: INSTALL_COMMANDS.get(
            defaults.get(project), ("just", "--justfile", "./justfile", "sync")
        )
        for project in projects
    }
    if not args.dry_run:
        for tool in dict.fromkeys(command[0] for command in commands.values()):
            if not shutil.which(tool):
                print(f"daily-update-cubrid: {tool} is not installed or not on PATH", file=sys.stderr)
                return 1
    if not shutil.which("git"):
        print("daily-update-cubrid: git is not installed or not on PATH", file=sys.stderr)
        return 1

    failed = []
    skipped = []
    try:
        update_dotfiles(dry_run=args.dry_run)
    except Skipped as error:
        print(f"SKIPPED: {error}", flush=True)
        skipped.append("dotfiles")
    except (Failed, OSError) as error:
        print(f"FAILED: {error}", flush=True)
        failed.append("dotfiles")
    for project in projects:
        print(f"\n── {project.name} ──", flush=True)
        # Pin the recipe file so just never discovers an unrelated parent recipe.
        command = list(commands[project])
        uses_just = command[0] == "just"
        if not project.is_dir() or (uses_just and not (project / "justfile").is_file()):
            print(
                f"FAILED: missing project directory or local justfile: {project}",
                flush=True,
            )
            failed.append(project)
            continue
        print(f"cd {shlex.quote(str(project))}", flush=True)
        try:
            name = defaults.get(project)
            refresh(
                project,
                github=f"vimkim/{name}" if name else None,
                dry_run=args.dry_run,
            )
            # Refresh can remove the recipe. Never discover a parent justfile.
            if uses_just and not (project / "justfile").is_file():
                raise Failed("missing local justfile after refresh")
            print(shlex.join(command), flush=True)
            if args.dry_run:
                continue
            result = subprocess.run(command, cwd=project, check=False)
            if result.returncode == 2 and uses_just and command[-1] == "sync":
                raise Skipped("partial/skipped (sync exit 2)")
            if result.returncode:
                raise Failed(f"installation exited {result.returncode}")
        except Skipped as error:
            print(f"SKIPPED: {error}", flush=True)
            skipped.append(project)
            continue
        except (Failed, OSError) as error:
            print(f"FAILED: {error}", flush=True)
            failed.append(project)
            continue
        print(f"{project.name}: updated", flush=True)

    if skipped:
        print("\nSkipped steps: " + ", ".join(str(path) for path in skipped))
    if failed:
        print(
            "\nFailed steps: " + ", ".join(str(path) for path in failed),
            file=sys.stderr,
        )
        return 1
    print("\nPreview complete." if args.dry_run else "\nCUBRID tool upkeep complete.")
    return 2 if skipped else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ndaily-update-cubrid: interrupted", file=sys.stderr)
        sys.exit(130)
