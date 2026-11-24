"""SQLite schema, configuration, locking, and state transitions for cubrid-pr-flow."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Iterator

VALID_ACTION_KINDS = (
    "open_pr",
    "rerun_ci",
    "draft_jira_issue",
    "publish_jira_issue",
)
HEAD_BOUND_ACTION_KINDS = frozenset(("open_pr", "rerun_ci"))

VALID_NOTIFICATION_KINDS = (
    "ci_failed",
    "ci_analyzed",
    "review_failed",
    "review_passed",
    "ask_open_pr",
    "ask_rerun_ci",
    "ask_draft_jira",
    "ask_publish_jira",
    "action_result",
    "tc_wait_timeout",
    "generic",
)

VALID_CI_STATES = ("pending", "running", "passed", "failed", "no_verdict", "superseded")
VALID_REVIEW_STATES = ("pending", "running", "passed", "failed", "incomplete", "superseded")
VALID_ANALYZE_STATES = ("none", "running", "done", "failed", "superseded")
VALID_ACTION_STATES = ("pending", "dispatched", "succeeded", "failed", "expired", "superseded")
VALID_NOTIFICATION_STATES = ("pending", "claimed", "sent", "unknown", "failed")

DEFAULT_REPO = "CUBRID/cubrid"
DEFAULT_DISCORD_TARGET = "discord:#general"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
ACTION_CODE_RE = re.compile(r"^ACT-([1-9][0-9]*)$")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pr_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_number INTEGER NOT NULL,
    head_sha TEXT NOT NULL,
    ticket TEXT NOT NULL DEFAULT '',
    pr_url TEXT NOT NULL DEFAULT '',
    ci_request_id INTEGER,
    ci_state TEXT NOT NULL DEFAULT 'pending',
    review_state TEXT NOT NULL DEFAULT 'pending',
    analyze_state TEXT NOT NULL DEFAULT 'none',
    open_prompt_sent INTEGER NOT NULL DEFAULT 0,
    superseded_by_sha TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(pr_number, head_sha)
);

CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    head_sha TEXT NOT NULL,
    ticket TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'pending',
    state_reason TEXT NOT NULL DEFAULT '',
    dispatched_by TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dispatched_at TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_pr_state
    ON pending_actions(pr_number, state);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    pr_number INTEGER,
    head_sha TEXT NOT NULL DEFAULT '',
    ticket TEXT NOT NULL DEFAULT '',
    action_code TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    rendered_text TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_notifications_state
    ON notifications(state, id);
"""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state_dir() -> Path:
    """Resolve the default state directory from XDG_STATE_HOME."""
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base).expanduser() / "cubrid-pr-flow"


def validate_sha(value: str, *, required: bool = True) -> str:
    """Validate and normalize a 40-character hexadecimal Git SHA."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        if required:
            raise ValueError("head_sha is required")
        return ""
    if not SHA_RE.fullmatch(cleaned):
        raise ValueError(f"invalid 40-char head_sha: {value!r}")
    return cleaned


def validate_positive_int(value: int | str | None, label: str) -> int:
    """Validate a positive integer argument."""
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


def normalize_action_code(raw: str) -> str:
    """Normalize and validate an action code such as ACT-12."""
    cleaned = (raw or "").strip().upper()
    if not ACTION_CODE_RE.fullmatch(cleaned):
        raise ValueError(f"invalid action code {raw!r}; expected ACT-<number>")
    return cleaned


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    """Atomically write text to path with restrictive permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-pr-flow-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


@contextmanager
def exclusive_lock(state_dir: Path, name: str) -> Iterator[None]:
    """Acquire a non-blocking exclusive flock on state_dir/<name>.lock."""
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = state_dir / f"{name}.lock"
    handle = open(lock_path, "a", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"{name} is already running") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def config_path(state_dir: Path) -> Path:
    """Return path to config.json inside state_dir."""
    return state_dir / "config.json"


def db_path(state_dir: Path) -> Path:
    """Return path to flow.sqlite3 inside state_dir."""
    return state_dir / "flow.sqlite3"


def connect_db(state_dir: Path, *, manual_transactions: bool = False) -> sqlite3.Connection:
    """Open flow.sqlite3 with WAL mode, busy timeout, and Row factory."""
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    isolation = None if manual_transactions else ""
    conn = sqlite3.connect(
        db_path(state_dir),
        timeout=10.0,
        isolation_level=isolation,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not exist."""
    conn.executescript(SCHEMA_SQL)


def init_state(
    state_dir: Path,
    *,
    discord_target: str | None = None,
    allowed_actors: list[str] | None = None,
    replace_actors: bool = False,
    hermes_bin: str | None = None,
    gh_bin: str | None = None,
    repo: str | None = None,
) -> dict:
    """Initialize or idempotently update config.json and flow.sqlite3."""
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_dir, 0o700)
    cfg_file = config_path(state_dir)
    if cfg_file.exists():
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("corrupted config.json")
    else:
        cfg = {
            "schema_version": 1,
            "repo": DEFAULT_REPO,
            "discord_target": DEFAULT_DISCORD_TARGET,
            "allowed_actors": [],
            "hermes_bin": "hermes",
            "gh_bin": "gh",
        }

    cfg.setdefault("schema_version", 1)
    cfg.setdefault("repo", DEFAULT_REPO)
    cfg.setdefault("discord_target", DEFAULT_DISCORD_TARGET)
    cfg.setdefault("allowed_actors", [])
    cfg.setdefault("hermes_bin", "hermes")
    cfg.setdefault("gh_bin", "gh")

    if discord_target is not None:
        cleaned = discord_target.strip()
        if not cleaned:
            raise ValueError("discord_target must not be empty")
        cfg["discord_target"] = cleaned
    if repo is not None:
        cleaned_repo = repo.strip()
        if "/" not in cleaned_repo:
            raise ValueError("repo must look like owner/name")
        cfg["repo"] = cleaned_repo
    if hermes_bin is not None:
        cfg["hermes_bin"] = hermes_bin.strip() or "hermes"
    if gh_bin is not None:
        cfg["gh_bin"] = gh_bin.strip() or "gh"

    if allowed_actors is not None:
        normalized = [a.strip() for a in allowed_actors if a and a.strip()]
        if replace_actors:
            cfg["allowed_actors"] = list(dict.fromkeys(normalized))
        else:
            existing = [str(a) for a in cfg.get("allowed_actors", []) if str(a).strip()]
            cfg["allowed_actors"] = list(dict.fromkeys([*existing, *normalized]))

    atomic_write(cfg_file, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", mode=0o600)
    conn = connect_db(state_dir)
    try:
        ensure_schema(conn)
    finally:
        conn.close()
    return cfg


def load_config(state_dir: Path) -> dict:
    """Load initialized config.json and ensure schema exists."""
    cfg_file = config_path(state_dir)
    if not cfg_file.exists():
        raise ValueError(f"state directory is not initialized: {state_dir} (run 'cubrid-pr-flow init' first)")
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError("invalid config.json")
    return cfg


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert an sqlite3.Row to a plain dictionary."""
    if row is None:
        return None
    return dict(row)


def upsert_pr_run(
    conn: sqlite3.Connection,
    *,
    pr_number: int,
    head_sha: str,
    ticket: str = "",
    pr_url: str = "",
    ci_request_id: int | None = None,
    ci_state: str | None = None,
    review_state: str | None = None,
    analyze_state: str | None = None,
) -> dict:
    """Insert or update a (pr_number, head_sha) run record."""
    pr_num = validate_positive_int(pr_number, "pr_number")
    sha = validate_sha(head_sha)
    if ci_state is not None and ci_state not in VALID_CI_STATES:
        raise ValueError(f"invalid ci_state: {ci_state}")
    if review_state is not None and review_state not in VALID_REVIEW_STATES:
        raise ValueError(f"invalid review_state: {review_state}")
    if analyze_state is not None and analyze_state not in VALID_ANALYZE_STATES:
        raise ValueError(f"invalid analyze_state: {analyze_state}")

    now = utc_now()
    with conn:
        existing = conn.execute(
            "SELECT * FROM pr_runs WHERE pr_number=? AND head_sha=?",
            (pr_num, sha),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO pr_runs (
                    pr_number, head_sha, ticket, pr_url, ci_request_id,
                    ci_state, review_state, analyze_state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pr_num,
                    sha,
                    ticket.strip(),
                    pr_url.strip(),
                    ci_request_id,
                    ci_state or "pending",
                    review_state or "pending",
                    analyze_state or "none",
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE pr_runs
                   SET ticket = COALESCE(NULLIF(?, ''), ticket),
                       pr_url = COALESCE(NULLIF(?, ''), pr_url),
                       ci_request_id = COALESCE(?, ci_request_id),
                       ci_state = COALESCE(?, ci_state),
                       review_state = COALESCE(?, review_state),
                       analyze_state = COALESCE(?, analyze_state),
                       updated_at = ?
                 WHERE pr_number=? AND head_sha=?
                """,
                (
                    ticket.strip(),
                    pr_url.strip(),
                    ci_request_id,
                    ci_state,
                    review_state,
                    analyze_state,
                    now,
                    pr_num,
                    sha,
                ),
            )
        row = conn.execute(
            "SELECT * FROM pr_runs WHERE pr_number=? AND head_sha=?",
            (pr_num, sha),
        ).fetchone()
    return dict(row)


def supersede_older_heads(
    conn: sqlite3.Connection,
    *,
    pr_number: int,
    new_head_sha: str,
) -> dict:
    """Mark older heads and their head-bound pending actions as superseded."""
    pr_num = validate_positive_int(pr_number, "pr_number")
    sha = validate_sha(new_head_sha)
    now = utc_now()
    reason = f"PR head moved to {sha[:12]}"
    with conn:
        runs_cur = conn.execute(
            """
            UPDATE pr_runs
               SET ci_state = CASE WHEN ci_state IN ('pending', 'running') THEN 'superseded' ELSE ci_state END,
                   review_state = CASE WHEN review_state IN ('pending', 'running') THEN 'superseded' ELSE review_state END,
                   analyze_state = CASE WHEN analyze_state IN ('none', 'running') THEN 'superseded' ELSE analyze_state END,
                   superseded_by_sha = ?,
                   updated_at = ?
             WHERE pr_number=? AND head_sha != ? AND superseded_by_sha = ''
            """,
            (sha, now, pr_num, sha),
        )
        actions_cur = conn.execute(
            """
            UPDATE pending_actions
               SET state='superseded',
                   state_reason=?,
                   completed_at=?,
                   updated_at=?
             WHERE pr_number=?
               AND head_sha != ?
               AND state='pending'
               AND kind IN ('open_pr', 'rerun_ci')
            """,
            (reason, now, now, pr_num, sha),
        )
    return {
        "pr_number": pr_num,
        "new_head_sha": sha,
        "superseded_runs": runs_cur.rowcount,
        "superseded_actions": actions_cur.rowcount,
    }
