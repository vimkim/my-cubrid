"""Idempotent outbox enqueue, flush via `hermes send`, and unknown resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

from .db import (
    DEFAULT_DISCORD_TARGET,
    DEFAULT_REPO,
    VALID_ACTION_KINDS,
    VALID_NOTIFICATION_KINDS,
    connect_db,
    ensure_schema,
    exclusive_lock,
    row_to_dict,
    utc_now,
    validate_positive_int,
    validate_sha,
)
from .render import render_card


def resolve_hermes_bin(cfg: dict) -> str:
    """Resolve the hermes executable from environment override or config."""
    return (
        os.environ.get("CUBRID_PR_FLOW_HERMES")
        or cfg.get("hermes_bin")
        or "hermes"
    )


def resolve_discord_target(cfg: dict, override: str | None = None) -> str:
    """Resolve the target Discord channel."""
    target = (
        override
        or os.environ.get("CUBRID_PR_FLOW_DISCORD_TARGET")
        or cfg.get("discord_target")
        or DEFAULT_DISCORD_TARGET
    ).strip()
    if not target:
        raise ValueError("discord_target must not be empty")
    return target


def enqueue_notification(
    state_dir: Path,
    cfg: dict,
    *,
    dedupe_key: str,
    kind: str,
    title: str,
    summary: str = "",
    pr_number: int | None = None,
    head_sha: str = "",
    ticket: str = "",
    target: str = "",
    report_url: str = "",
    comment_url: str = "",
    question: str = "",
    action_kind: str = "",
    action_payload: dict | None = None,
    probable_causes: list[str] | None = None,
    extra_payload: dict | None = None,
) -> dict:
    """Atomically enqueue a notification and optional pending action with dedupe_key idempotency."""
    clean_dedupe = (dedupe_key or "").strip()
    if not clean_dedupe:
        raise ValueError("dedupe_key is required")
    if kind not in VALID_NOTIFICATION_KINDS:
        raise ValueError(f"invalid notification kind: {kind}")
    if not (title or "").strip():
        raise ValueError("title is required")

    pr_num = validate_positive_int(pr_number, "pr_number") if pr_number is not None else None
    sha = validate_sha(head_sha, required=bool(action_kind))
    clean_ticket = (ticket or "").strip()
    clean_action_kind = (action_kind or "").strip()
    if clean_action_kind:
        if clean_action_kind not in VALID_ACTION_KINDS:
            raise ValueError(f"invalid action_kind: {clean_action_kind}")
        if pr_num is None:
            raise ValueError("pr_number is required when creating a pending action")

    resolved_target = resolve_discord_target(cfg, target or None)
    repo = cfg.get("repo") or DEFAULT_REPO
    now = utc_now()

    payload_obj = {
        "title": title.strip(),
        "summary": summary.strip(),
        "report_url": report_url.strip(),
        "comment_url": comment_url.strip(),
        "question": question.strip(),
        "probable_causes": probable_causes or [],
        "extra": extra_payload or {},
    }

    conn = connect_db(state_dir)
    try:
        ensure_schema(conn)
        with conn:
            existing_notif = conn.execute(
                "SELECT * FROM notifications WHERE dedupe_key=?",
                (clean_dedupe,),
            ).fetchone()
            if existing_notif is not None:
                existing_action = None
                if existing_notif["action_code"]:
                    existing_action = row_to_dict(
                        conn.execute(
                            "SELECT * FROM pending_actions WHERE code=?",
                            (existing_notif["action_code"],),
                        ).fetchone()
                    )
                return {
                    "created": False,
                    "notification": dict(existing_notif),
                    "action": existing_action,
                }

            action_dict = None
            action_code = ""
            if clean_action_kind:
                action_dedupe = f"action:{clean_dedupe}"
                existing_act = conn.execute(
                    "SELECT * FROM pending_actions WHERE dedupe_key=?",
                    (action_dedupe,),
                ).fetchone()
                if existing_act is not None:
                    action_dict = dict(existing_act)
                    action_code = action_dict["code"]
                else:
                    temp_code = f"PENDING-{clean_dedupe}"
                    cur = conn.execute(
                        """
                        INSERT INTO pending_actions (
                            code, kind, pr_number, head_sha, ticket, payload_json,
                            dedupe_key, state, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                        """,
                        (
                            temp_code,
                            clean_action_kind,
                            pr_num,
                            sha,
                            clean_ticket,
                            json.dumps(action_payload or {}, ensure_ascii=False, sort_keys=True),
                            action_dedupe,
                            now,
                            now,
                        ),
                    )
                    row_id = cur.lastrowid
                    action_code = f"ACT-{row_id}"
                    conn.execute(
                        "UPDATE pending_actions SET code=? WHERE id=?",
                        (action_code, row_id),
                    )
                    action_dict = dict(
                        conn.execute(
                            "SELECT * FROM pending_actions WHERE id=?",
                            (row_id,),
                        ).fetchone()
                    )

            rendered = render_card(
                kind=kind,
                title=title.strip(),
                summary=summary.strip(),
                pr_number=pr_num,
                head_sha=sha,
                ticket=clean_ticket,
                repo=repo,
                report_url=report_url.strip(),
                comment_url=comment_url.strip(),
                question=question.strip(),
                action_code=action_code,
                probable_causes=probable_causes,
            )
            cur = conn.execute(
                """
                INSERT INTO notifications (
                    dedupe_key, kind, pr_number, head_sha, ticket, action_code,
                    target, payload_json, rendered_text, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    clean_dedupe,
                    kind,
                    pr_num,
                    sha,
                    clean_ticket,
                    action_code,
                    resolved_target,
                    json.dumps(payload_obj, ensure_ascii=False, sort_keys=True),
                    rendered,
                    now,
                    now,
                ),
            )
            notif_dict = dict(
                conn.execute(
                    "SELECT * FROM notifications WHERE id=?",
                    (cur.lastrowid,),
                ).fetchone()
            )
        return {
            "created": True,
            "notification": notif_dict,
            "action": action_dict,
        }
    finally:
        conn.close()


def _send_via_hermes(hermes_bin: str, target: str, text: str, msg_dir: Path) -> tuple[bool, str]:
    """Send a rendered text body through `hermes send --file ... --json`."""
    msg_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp_path = tempfile.mkstemp(dir=msg_dir, prefix="msg-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp_path, 0o600)
        try:
            proc = subprocess.run(
                [hermes_bin, "send", "--to", target, "--file", tmp_path, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except OSError as exc:
            return False, f"hermes executable error: {type(exc).__name__}"
        except subprocess.TimeoutExpired:
            return False, "hermes send timed out"

        if proc.returncode != 0:
            return False, f"hermes send exited {proc.returncode}"
        try:
            ack = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return False, "hermes send returned invalid JSON"
        if isinstance(ack, dict) and (ack.get("success") is True or ack.get("ok") is True):
            return True, ""
        return False, "hermes send did not confirm success"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def flush_outbox(state_dir: Path, cfg: dict, *, target_override: str | None = None) -> dict:
    """Deliver pending outbox rows via `hermes send`, marking uncertain outcomes as unknown."""
    hermes_bin = resolve_hermes_bin(cfg)
    msg_dir = state_dir / "messages"
    sent: list[dict] = []
    unknown: list[dict] = []

    with exclusive_lock(state_dir, "flush"):
        conn = connect_db(state_dir)
        try:
            ensure_schema(conn)
            now = utc_now()
            with conn:
                conn.execute(
                    """
                    UPDATE notifications
                       SET state='unknown',
                           reason='interrupted submission',
                           updated_at=?
                     WHERE state='claimed'
                    """,
                    (now,),
                )
            rows = conn.execute(
                "SELECT * FROM notifications WHERE state='pending' ORDER BY id ASC"
            ).fetchall()

            for row in rows:
                claim_time = utc_now()
                with conn:
                    claimed = conn.execute(
                        """
                        UPDATE notifications
                           SET state='claimed', updated_at=?
                         WHERE id=? AND state='pending'
                        """,
                        (claim_time, row["id"]),
                    )
                if claimed.rowcount != 1:
                    continue

                target = target_override or row["target"] or resolve_discord_target(cfg)
                ok, reason = _send_via_hermes(hermes_bin, target, row["rendered_text"], msg_dir)
                done_time = utc_now()
                if ok:
                    with conn:
                        conn.execute(
                            """
                            UPDATE notifications
                               SET state='sent', reason='', sent_at=?, updated_at=?
                             WHERE id=?
                            """,
                            (done_time, done_time, row["id"]),
                        )
                    sent.append({"id": row["id"], "dedupe_key": row["dedupe_key"], "target": target})
                else:
                    with conn:
                        conn.execute(
                            """
                            UPDATE notifications
                               SET state='unknown', reason=?, updated_at=?
                             WHERE id=?
                            """,
                            (reason, done_time, row["id"]),
                        )
                    unknown.append(
                        {
                            "id": row["id"],
                            "dedupe_key": row["dedupe_key"],
                            "target": target,
                            "reason": reason,
                        }
                    )
        finally:
            conn.close()

    return {
        "sent_count": len(sent),
        "unknown_count": len(unknown),
        "sent": sent,
        "unknown": unknown,
    }


def resolve_notification(
    state_dir: Path,
    *,
    dedupe_key: str,
    outcome: str,
    reason: str,
) -> dict:
    """Resolve an unknown notification to sent or pending after operator inspection."""
    if outcome not in ("sent", "pending"):
        raise ValueError("outcome must be 'sent' or 'pending'")
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("reason is required")

    with exclusive_lock(state_dir, "flush"):
        conn = connect_db(state_dir)
        try:
            ensure_schema(conn)
            now = utc_now()
            sent_at = now if outcome == "sent" else ""
            with conn:
                cur = conn.execute(
                    """
                    UPDATE notifications
                       SET state=?,
                           reason=?,
                           sent_at=CASE WHEN ? != '' THEN ? ELSE sent_at END,
                           updated_at=?
                     WHERE dedupe_key=? AND state='unknown'
                    """,
                    (
                        outcome,
                        f"operator resolution: {clean_reason}",
                        sent_at,
                        sent_at,
                        now,
                        dedupe_key.strip(),
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError(f"unknown notification not found for dedupe_key={dedupe_key!r}")
                row = conn.execute(
                    "SELECT * FROM notifications WHERE dedupe_key=?",
                    (dedupe_key.strip(),),
                ).fetchone()
            return dict(row)
        finally:
            conn.close()
