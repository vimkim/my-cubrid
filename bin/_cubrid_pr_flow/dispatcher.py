"""Guarded Pending Action dispatcher (actor auth, live PR freshness, atomic single-use claim)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .db import (
    DEFAULT_REPO,
    HEAD_BOUND_ACTION_KINDS,
    connect_db,
    ensure_schema,
    normalize_action_code,
    utc_now,
    validate_sha,
)
from .notifier import enqueue_notification, flush_outbox


def resolve_gh_bin(cfg: dict) -> str:
    """Resolve gh executable from environment override or config."""
    return os.environ.get("CUBRID_PR_FLOW_GH") or cfg.get("gh_bin") or "gh"


def resolve_runner(cfg: dict) -> str | None:
    """Resolve action runner executable from env or config; None if unconfigured."""
    runner = os.environ.get("CUBRID_PR_FLOW_ACTION_RUNNER") or cfg.get("action_runner") or ""
    runner = str(runner).strip()
    return runner or None


def fetch_live_pr(gh_bin: str, repo: str, pr_number: int) -> dict:
    """Inspect live PR state, draft flag, and headRefOid via gh CLI."""
    try:
        proc = subprocess.run(
            [
                gh_bin,
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "number,url,state,isDraft,headRefOid",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError as exc:
        raise RuntimeError(f"gh executable error: {type(exc).__name__}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("gh pr view timed out") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"gh pr view exited {proc.returncode}" + (f": {detail[:200]}" if detail else ""))

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh pr view returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise RuntimeError("unexpected gh pr view payload")
    head_oid = validate_sha(str(data.get("headRefOid") or ""))
    state = data.get("state")
    is_draft = data.get("isDraft")
    if not isinstance(state, str) or not isinstance(is_draft, bool):
        raise RuntimeError("gh pr view payload missing state or isDraft")
    return {
        "number": data.get("number"),
        "url": data.get("url") or "",
        "state": state.upper(),
        "isDraft": is_draft,
        "headRefOid": head_oid,
    }


def _mark_action_terminal(
    state_dir: Path,
    code: str,
    *,
    state: str,
    reason: str,
    result_obj: dict | None = None,
) -> None:
    now = utc_now()
    conn = connect_db(state_dir)
    try:
        with conn:
            conn.execute(
                """
                UPDATE pending_actions
                   SET state=?,
                       state_reason=?,
                       result_json=?,
                       completed_at=?,
                       updated_at=?
                 WHERE code=? AND state IN ('pending', 'dispatched')
                """,
                (
                    state,
                    reason,
                    json.dumps(result_obj, ensure_ascii=False, sort_keys=True) if result_obj is not None else "",
                    now,
                    now,
                    code,
                ),
            )
    finally:
        conn.close()


def _claim_action_atomically(state_dir: Path, code: str, actor: str) -> tuple[bool, str | None]:
    """Claim a pending action in a single BEGIN IMMEDIATE SQLite transaction."""
    now = utc_now()
    conn = connect_db(state_dir, manual_transactions=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            UPDATE pending_actions
               SET state='dispatched',
                   dispatched_by=?,
                   dispatched_at=?,
                   updated_at=?
             WHERE code=? AND state='pending'
            """,
            (actor, now, now, code),
        )
        if cur.rowcount == 1:
            conn.execute("COMMIT")
            return True, None
        existing = conn.execute(
            "SELECT state, state_reason FROM pending_actions WHERE code=?",
            (code,),
        ).fetchone()
        conn.execute("ROLLBACK")
        if existing is None:
            return False, None
        return False, existing["state"]
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _invoke_runner(runner: str, payload: dict) -> tuple[bool, str, dict]:
    """Invoke external action runner executable with JSON stdin."""
    try:
        proc = subprocess.run(
            [runner],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except OSError as exc:
        return False, f"runner error: {type(exc).__name__}", {}
    except subprocess.TimeoutExpired:
        return False, "action runner timed out", {}

    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return False, "action runner returned invalid JSON", {"returncode": proc.returncode}

    if not isinstance(parsed, dict):
        return False, "action runner returned non-object JSON", {"returncode": proc.returncode}

    ok = proc.returncode == 0 and parsed.get("ok") is True
    summary = str(parsed.get("summary") or parsed.get("error") or f"runner exited {proc.returncode}").strip()
    return ok, summary, parsed


def dispatch_action(
    state_dir: Path,
    cfg: dict,
    *,
    code: str,
    actor: str,
    dry_run: bool = False,
    send_result: bool = False,
    target_override: str | None = None,
) -> tuple[int, dict]:
    """Validate actor, check live PR freshness, claim once, and run configured executor.

    Returns (exit_code, result_dict) using:
      0: succeeded (or dry-run ready)
      1: operational rejection (unauthorized, already_handled, expired, superseded, runner failed)
      2: usage / missing action / live check error / executor unavailable
    """
    try:
        normalized_code = normalize_action_code(code)
    except ValueError as exc:
        return 2, {"ok": False, "code": code, "status": "invalid_code", "reason": str(exc)}

    clean_actor = (actor or "").strip()
    allowed = [str(a).strip() for a in cfg.get("allowed_actors", []) if str(a).strip()]
    if not allowed:
        return 1, {
            "ok": False,
            "code": normalized_code,
            "status": "unauthorized",
            "reason": "no allowed_actors configured (fail-closed); configure allowed_actors with init",
        }
    if not clean_actor or clean_actor not in allowed:
        return 1, {
            "ok": False,
            "code": normalized_code,
            "status": "unauthorized",
            "reason": f"actor {clean_actor!r} is not in allowed_actors",
        }

    conn = connect_db(state_dir)
    try:
        ensure_schema(conn)
        row = conn.execute("SELECT * FROM pending_actions WHERE code=?", (normalized_code,)).fetchone()
        if row is None:
            return 2, {
                "ok": False,
                "code": normalized_code,
                "status": "not_found",
                "reason": f"pending action {normalized_code} not found",
            }
        action = dict(row)
    finally:
        conn.close()

    if action["state"] != "pending":
        return 1, {
            "ok": False,
            "code": normalized_code,
            "kind": action["kind"],
            "status": "already_handled",
            "current_state": action["state"],
            "reason": action["state_reason"] or f"action is already {action['state']}",
        }

    repo = cfg.get("repo") or DEFAULT_REPO
    if action["kind"] in HEAD_BOUND_ACTION_KINDS:
        try:
            live = fetch_live_pr(resolve_gh_bin(cfg), repo, action["pr_number"])
        except RuntimeError as exc:
            return 2, {
                "ok": False,
                "code": normalized_code,
                "kind": action["kind"],
                "status": "live_check_failed",
                "reason": str(exc),
            }

        if live["state"] != "OPEN":
            reason = f"PR #{action['pr_number']} is not OPEN (live state={live['state']})"
            if not dry_run:
                _mark_action_terminal(state_dir, normalized_code, state="expired", reason=reason)
            return 1, {
                "ok": False,
                "code": normalized_code,
                "kind": action["kind"],
                "status": "expired",
                "reason": reason,
            }

        if live["headRefOid"].lower() != action["head_sha"].lower():
            reason = (
                f"PR #{action['pr_number']} head changed: "
                f"expected {action['head_sha'][:10]}, live {live['headRefOid'][:10]}"
            )
            if not dry_run:
                _mark_action_terminal(state_dir, normalized_code, state="superseded", reason=reason)
            return 1, {
                "ok": False,
                "code": normalized_code,
                "kind": action["kind"],
                "status": "superseded",
                "reason": reason,
            }

        if action["kind"] == "open_pr" and live["isDraft"] is False:
            reason = f"PR #{action['pr_number']} is already open (not draft)"
            if not dry_run:
                _mark_action_terminal(state_dir, normalized_code, state="expired", reason=reason)
            return 1, {
                "ok": False,
                "code": normalized_code,
                "kind": action["kind"],
                "status": "expired",
                "reason": reason,
            }

    if dry_run:
        return 0, {
            "ok": True,
            "dry_run": True,
            "code": normalized_code,
            "kind": action["kind"],
            "pr_number": action["pr_number"],
            "head_sha": action["head_sha"],
            "status": "ready",
        }

    runner = resolve_runner(cfg)
    if not runner:
        return 2, {
            "ok": False,
            "code": normalized_code,
            "kind": action["kind"],
            "status": "executor_unavailable",
            "reason": "action executor not configured (set CUBRID_PR_FLOW_ACTION_RUNNER)",
        }

    claimed, current_state = _claim_action_atomically(state_dir, normalized_code, clean_actor)
    if not claimed:
        return 1, {
            "ok": False,
            "code": normalized_code,
            "kind": action["kind"],
            "status": "already_handled",
            "current_state": current_state or "unknown",
            "reason": "action was already claimed by a concurrent dispatch",
        }

    runner_input = {
        "code": normalized_code,
        "kind": action["kind"],
        "pr_number": action["pr_number"],
        "head_sha": action["head_sha"],
        "ticket": action["ticket"],
        "payload": json.loads(action["payload_json"] or "{}"),
        "actor": clean_actor,
        "repo": repo,
    }
    ok, summary, runner_result = _invoke_runner(runner, runner_input)
    final_state = "succeeded" if ok else "failed"
    _mark_action_terminal(
        state_dir,
        normalized_code,
        state=final_state,
        reason=summary,
        result_obj=runner_result,
    )

    flush_info = None
    if send_result:
        report_url = str(runner_result.get("report_url") or "").strip()
        title_prefix = "완료" if ok else "실패"
        enqueue_notification(
            state_dir,
            cfg,
            dedupe_key=f"action-result:{normalized_code}:{final_state}",
            kind="action_result",
            title=f"{normalized_code} ({action['kind']}) {title_prefix}",
            summary=summary,
            pr_number=action["pr_number"],
            head_sha=action["head_sha"],
            ticket=action["ticket"],
            target=target_override or "",
            report_url=report_url,
            extra_payload={"action_code": normalized_code, "status": final_state},
        )
        flush_info = flush_outbox(state_dir, cfg, target_override=target_override)

    response = {
        "ok": ok,
        "code": normalized_code,
        "kind": action["kind"],
        "pr_number": action["pr_number"],
        "head_sha": action["head_sha"],
        "status": final_state,
        "summary": summary,
        "result": runner_result,
    }
    if flush_info is not None:
        response["flush"] = flush_info
    return (0 if ok else 1), response
