#!/usr/bin/env python3
"""Request reviews from the CUBRID dev2 teammates for a GitHub PR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import urlsplit


FALLBACK_TEAMMATES = (
    "hgryoo",
    "hornetmj",
    # "hyahong",
    "vimkim",
    "H2SU",
    "YeunjunLee",
    "youngjun9072",
    "InChiJun",
    "lht1199",
)
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "cubrid-dev2-team.toml"
GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class UserError(RuntimeError):
    """An error that can be shown without a traceback."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Request reviews from all dev2 teammates for a GitHub pull request."
    )
    parser.add_argument(
        "pr",
        nargs="?",
        help=(
            "PR URL, number, or branch; defaults to the PR associated with "
            "the current worktree"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"team TOML file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the reviewers and edit command without modifying GitHub",
    )
    return parser.parse_args()


def validate_pr_url(pr_url: str) -> None:
    parsed = urlsplit(pr_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    valid_path = (
        len(path_parts) == 4
        and path_parts[2] == "pull"
        and path_parts[3].isdigit()
        and int(path_parts[3]) > 0
    )
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not valid_path:
        raise UserError(
            "expected a GitHub PR URL like https://github.com/CUBRID/cubrid/pull/123"
        )


def validate_teammates(value: object, source: Path) -> list[str]:
    if not isinstance(value, list) or not value:
        raise UserError(f"{source}: 'teammates' must be a non-empty TOML array")

    teammates: list[str] = []
    seen: set[str] = set()
    for login in value:
        if not isinstance(login, str) or not GITHUB_LOGIN_RE.fullmatch(login):
            raise UserError(f"{source}: invalid GitHub login in 'teammates': {login!r}")
        key = login.casefold()
        if key not in seen:
            teammates.append(login)
            seen.add(key)
    return teammates


def load_teammates(config_path: Path) -> tuple[list[str], str]:
    if not config_path.is_file():
        return list(FALLBACK_TEAMMATES), "built-in fallback"

    try:
        with config_path.open("rb") as config_file:
            config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise UserError(f"could not read {config_path}: {exc}") from exc

    return validate_teammates(config.get("teammates"), config_path), str(config_path)


def run_gh(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise UserError("GitHub CLI ('gh') is not installed or not in PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout).strip()
        raise UserError(f"gh failed: {detail or f'exit status {exc.returncode}'}") from exc
    return result.stdout.strip()


def resolve_pr_url(pr: str | None) -> str:
    if pr is not None:
        try:
            validate_pr_url(pr)
        except UserError:
            pass
        else:
            return pr

    arguments = ["pr", "view"]
    if pr is not None:
        arguments.append(pr)
    arguments.extend(["--json", "url"])

    output = run_gh(arguments)
    try:
        pr_url = json.loads(output)["url"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise UserError("could not determine the PR URL from gh output") from exc
    if not isinstance(pr_url, str) or not pr_url:
        raise UserError("could not determine the PR URL from gh output")
    validate_pr_url(pr_url)
    return pr_url


def get_pr_author(pr_url: str) -> str:
    output = run_gh(["pr", "view", pr_url, "--json", "author"])
    try:
        author = json.loads(output)["author"]["login"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise UserError("could not determine the PR author from gh output") from exc
    if not isinstance(author, str) or not author:
        raise UserError("could not determine the PR author from gh output")
    return author


def main() -> int:
    args = parse_args()
    try:
        pr_url = resolve_pr_url(args.pr)
        teammates, source = load_teammates(args.config)

        print(f"Pull request: {pr_url}")
        print(f"Reviewer source: {source}")
        print(f"Configured reviewers ({len(teammates)}): {', '.join(teammates)}")

        if args.dry_run:
            command = ["gh", "pr", "edit", pr_url, "--add-reviewer", ",".join(teammates)]
            print("Dry run; command:")
            print(" ".join(command))
            print("The PR author will be excluded during an actual run.")
            return 0

        author = get_pr_author(pr_url)
        reviewers = [login for login in teammates if login.casefold() != author.casefold()]
        if not reviewers:
            raise UserError("no eligible reviewers remain after excluding the PR author")
        if len(reviewers) != len(teammates):
            print(f"Skipping PR author: {author}")

        run_gh(["pr", "edit", pr_url, "--add-reviewer", ",".join(reviewers)])
        print(f"Requested reviews from {len(reviewers)} teammate(s): {', '.join(reviewers)}")
        return 0
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
