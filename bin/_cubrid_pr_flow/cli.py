"""CLI interface for cubrid-pr-flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .db import (
    VALID_ACTION_KINDS,
    VALID_ANALYZE_STATES,
    VALID_CI_STATES,
    VALID_NOTIFICATION_KINDS,
    VALID_REVIEW_STATES,
    connect_db,
    default_state_dir,
    ensure_schema,
    init_state,
    load_config,
    normalize_action_code,
    supersede_older_heads,
    upsert_pr_run,
    utc_now,
    validate_positive_int,
)
from .dispatcher import dispatch_action
from .notifier import enqueue_notification, flush_outbox, resolve_notification


def _emit_output(data: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            else:
                print(f"{key}: {value}")
    elif isinstance(data, list):
        for item in data:
            print(json.dumps(item, ensure_ascii=False))
    else:
        print(str(data))


def _parse_json_object(raw: str | None, label: str) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Construct the cubrid-pr-flow argument parser."""
    parser = argparse.ArgumentParser(
        prog="cubrid-pr-flow",
        description="Outbox, Pending Action DB, and guarded dispatcher for CUBRID PR automation.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Override state directory (default: $XDG_STATE_HOME/cubrid-pr-flow)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    # init
    p_init = sub.add_parser("init", help="Initialize or update state directory config and SQLite schema")
    p_init.add_argument("--discord-target", help="Default Discord target (e.g. discord:#general or discord:123)")
    p_init.add_argument("--allowed-actor", action="append", default=None, help="Authorized Discord user ID (repeatable)")
    p_init.add_argument("--replace-actors", action="store_true", help="Replace existing allowed_actors instead of appending")
    p_init.add_argument("--hermes-bin", help="Path or name of hermes CLI")
    p_init.add_argument("--gh-bin", help="Path or name of gh CLI")
    p_init.add_argument("--repo", help="GitHub repository (default: CUBRID/cubrid)")
    p_init.add_argument("--json", action="store_true", help="Emit JSON output")

    # pr
    p_pr = sub.add_parser("pr", help="Manage PR run states and head supersession")
    pr_sub = p_pr.add_subparsers(dest="pr_cmd", required=True, metavar="SUBCOMMAND")

    p_pr_up = pr_sub.add_parser("upsert", help="Create or update a (pr, head_sha) run record")
    p_pr_up.add_argument("--pr", type=int, required=True)
    p_pr_up.add_argument("--head", required=True)
    p_pr_up.add_argument("--ticket", default="")
    p_pr_up.add_argument("--pr-url", default="")
    p_pr_up.add_argument("--ci-request-id", type=int, default=None)
    p_pr_up.add_argument("--ci-state", choices=VALID_CI_STATES, default=None)
    p_pr_up.add_argument("--review-state", choices=VALID_REVIEW_STATES, default=None)
    p_pr_up.add_argument("--analyze-state", choices=VALID_ANALYZE_STATES, default=None)
    p_pr_up.add_argument("--json", action="store_true")

    p_pr_sup = pr_sub.add_parser("supersede", help="Supersede older heads and head-bound actions for a PR")
    p_pr_sup.add_argument("--pr", type=int, required=True)
    p_pr_sup.add_argument("--new-head", required=True)
    p_pr_sup.add_argument("--json", action="store_true")

    p_pr_ls = pr_sub.add_parser("list", help="List tracked PR runs")
    p_pr_ls.add_argument("--pr", type=int, default=None)
    p_pr_ls.add_argument("--json", action="store_true")

    # emit
    p_emit = sub.add_parser("emit", help="Enqueue an idempotent Korean notification (and optional Pending Action)")
    p_emit.add_argument("--dedupe-key", required=True)
    p_emit.add_argument("--kind", choices=VALID_NOTIFICATION_KINDS, required=True)
    p_emit.add_argument("--title", required=True)
    p_emit.add_argument("--summary", default="")
    p_emit.add_argument("--pr", type=int, default=None)
    p_emit.add_argument("--head", default="")
    p_emit.add_argument("--ticket", default="")
    p_emit.add_argument("--target", default="")
    p_emit.add_argument("--report-url", default="")
    p_emit.add_argument("--comment-url", default="")
    p_emit.add_argument("--question", default="")
    p_emit.add_argument("--cause", action="append", default=None, help="Suspected cause bullet (repeatable)")
    p_emit.add_argument("--action-kind", choices=VALID_ACTION_KINDS, default="")
    p_emit.add_argument("--action-payload", default="", help="JSON object payload for the pending action")
    p_emit.add_argument("--flush", action="store_true", help="Flush the outbox immediately after enqueueing")
    p_emit.add_argument("--json", action="store_true")

    # flush
    p_flush = sub.add_parser("flush", help="Send pending outbox notifications through hermes send")
    p_flush.add_argument("--target", default=None, help="Override delivery target")
    p_flush.add_argument("--json", action="store_true")

    # resolve
    p_res = sub.add_parser("resolve", help="Resolve an unknown outbox delivery after manual verification")
    p_res.add_argument("--dedupe-key", required=True)
    p_res.add_argument("--outcome", choices=("sent", "pending"), required=True)
    p_res.add_argument("--reason", required=True)
    p_res.add_argument("--json", action="store_true")

    # action
    p_act = sub.add_parser("action", help="Inspect or cancel pending actions")
    act_sub = p_act.add_subparsers(dest="act_cmd", required=True, metavar="SUBCOMMAND")

    p_act_ls = act_sub.add_parser("list", help="List pending actions")
    p_act_ls.add_argument("--state", default="pending", help="Filter by state (or 'all')")
    p_act_ls.add_argument("--pr", type=int, default=None)
    p_act_ls.add_argument("--json", action="store_true")

    p_act_show = act_sub.add_parser("show", help="Show a single action by ACT code")
    p_act_show.add_argument("code")
    p_act_show.add_argument("--json", action="store_true")

    p_act_cancel = act_sub.add_parser("cancel", help="Mark a pending action as expired")
    p_act_cancel.add_argument("code")
    p_act_cancel.add_argument("--reason", default="cancelled by operator")
    p_act_cancel.add_argument("--json", action="store_true")

    # dispatch
    p_disp = sub.add_parser("dispatch", help="Validate actor + freshness and atomically claim/run an action")
    p_disp.add_argument("code", help="Action code (e.g. ACT-1)")
    p_disp.add_argument("--actor", required=True, help="Caller Discord user ID")
    p_disp.add_argument("--dry-run", action="store_true", help="Validate without claiming or executing")
    p_disp.add_argument("--send-result", action="store_true", help="Enqueue and flush result notification")
    p_disp.add_argument("--target", default=None, help="Override Discord target when --send-result is set")
    p_disp.add_argument("--json", action="store_true")

    # status
    p_status = sub.add_parser("status", help="Show summary counts and recent pending actions/outbox rows")
    p_status.add_argument("--json", action="store_true")

    return parser


def _handle_pr(state_dir: Path, args: argparse.Namespace) -> int:
    load_config(state_dir)
    conn = connect_db(state_dir)
    try:
        ensure_schema(conn)
        if args.pr_cmd == "upsert":
            result = upsert_pr_run(
                conn,
                pr_number=args.pr,
                head_sha=args.head,
                ticket=args.ticket,
                pr_url=args.pr_url,
                ci_request_id=args.ci_request_id,
                ci_state=args.ci_state,
                review_state=args.review_state,
                analyze_state=args.analyze_state,
            )
            _emit_output(result, as_json=args.json)
            return 0
        if args.pr_cmd == "supersede":
            result = supersede_older_heads(conn, pr_number=args.pr, new_head_sha=args.new_head)
            _emit_output(result, as_json=args.json)
            return 0
        query = "SELECT * FROM pr_runs"
        params: list[Any] = []
        if args.pr is not None:
            query += " WHERE pr_number=?"
            params.append(validate_positive_int(args.pr, "pr"))
        query += " ORDER BY id DESC"
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        _emit_output(rows, as_json=args.json)
        return 0
    finally:
        conn.close()


def _handle_action(state_dir: Path, args: argparse.Namespace) -> int:
    load_config(state_dir)
    conn = connect_db(state_dir)
    try:
        ensure_schema(conn)
        if args.act_cmd == "list":
            clauses: list[str] = []
            params: list[Any] = []
            if args.state != "all":
                clauses.append("state=?")
                params.append(args.state)
            if args.pr is not None:
                clauses.append("pr_number=?")
                params.append(validate_positive_int(args.pr, "pr"))
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM pending_actions{where} ORDER BY id DESC", params).fetchall()]
            _emit_output(rows, as_json=args.json)
            return 0

        code = normalize_action_code(args.code)
        if args.act_cmd == "show":
            row = conn.execute("SELECT * FROM pending_actions WHERE code=?", (code,)).fetchone()
            if row is None:
                raise KeyError(f"action {code} not found")
            _emit_output(dict(row), as_json=args.json)
            return 0

        now = utc_now()
        with conn:
            cur = conn.execute(
                """
                UPDATE pending_actions
                   SET state='expired', state_reason=?, completed_at=?, updated_at=?
                 WHERE code=? AND state='pending'
                """,
                (args.reason.strip(), now, now, code),
            )
        if cur.rowcount != 1:
            row = conn.execute("SELECT state FROM pending_actions WHERE code=?", (code,)).fetchone()
            if row is None:
                raise KeyError(f"action {code} not found")
            _emit_output({"ok": False, "code": code, "status": "already_handled", "current_state": row["state"]}, as_json=args.json)
            return 1
        row = conn.execute("SELECT * FROM pending_actions WHERE code=?", (code,)).fetchone()
        _emit_output(dict(row), as_json=args.json)
        return 0
    finally:
        conn.close()


def _handle_status(state_dir: Path, as_json: bool) -> int:
    cfg = load_config(state_dir)
    conn = connect_db(state_dir)
    try:
        ensure_schema(conn)
        notif_counts = {
            r["state"]: r["cnt"]
            for r in conn.execute("SELECT state, COUNT(*) AS cnt FROM notifications GROUP BY state").fetchall()
        }
        action_counts = {
            r["state"]: r["cnt"]
            for r in conn.execute("SELECT state, COUNT(*) AS cnt FROM pending_actions GROUP BY state").fetchall()
        }
        run_count = conn.execute("SELECT COUNT(*) FROM pr_runs").fetchone()[0]
        pending_actions = [
            dict(r)
            for r in conn.execute(
                "SELECT code, kind, pr_number, head_sha, ticket, created_at FROM pending_actions WHERE state='pending' ORDER BY id ASC"
            ).fetchall()
        ]
    finally:
        conn.close()

    payload = {
        "state_dir": str(state_dir),
        "repo": cfg.get("repo"),
        "discord_target": cfg.get("discord_target"),
        "allowed_actors_count": len(cfg.get("allowed_actors", [])),
        "pr_runs_count": run_count,
        "notification_counts": notif_counts,
        "action_counts": action_counts,
        "pending_actions": pending_actions,
    }
    _emit_output(payload, as_json=as_json)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint returning process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    state_dir = (args.state_dir or default_state_dir()).expanduser().resolve()

    try:
        if args.cmd == "init":
            cfg = init_state(
                state_dir,
                discord_target=args.discord_target,
                allowed_actors=args.allowed_actor,
                replace_actors=args.replace_actors,
                hermes_bin=args.hermes_bin,
                gh_bin=args.gh_bin,
                repo=args.repo,
            )
            _emit_output({"state_dir": str(state_dir), "config": cfg}, as_json=args.json)
            return 0

        if args.cmd == "pr":
            return _handle_pr(state_dir, args)

        if args.cmd == "emit":
            cfg = load_config(state_dir)
            payload_dict = _parse_json_object(args.action_payload, "action_payload")
            res = enqueue_notification(
                state_dir,
                cfg,
                dedupe_key=args.dedupe_key,
                kind=args.kind,
                title=args.title,
                summary=args.summary,
                pr_number=args.pr,
                head_sha=args.head,
                ticket=args.ticket,
                target=args.target,
                report_url=args.report_url,
                comment_url=args.comment_url,
                question=args.question,
                action_kind=args.action_kind,
                action_payload=payload_dict,
                probable_causes=args.cause,
            )
            if args.flush:
                res["flush"] = flush_outbox(state_dir, cfg, target_override=args.target or None)
            _emit_output(res, as_json=args.json)
            return 0

        if args.cmd == "flush":
            cfg = load_config(state_dir)
            res = flush_outbox(state_dir, cfg, target_override=args.target)
            _emit_output(res, as_json=args.json)
            return 0

        if args.cmd == "resolve":
            load_config(state_dir)
            res = resolve_notification(
                state_dir,
                dedupe_key=args.dedupe_key,
                outcome=args.outcome,
                reason=args.reason,
            )
            _emit_output(res, as_json=args.json)
            return 0

        if args.cmd == "action":
            return _handle_action(state_dir, args)

        if args.cmd == "dispatch":
            cfg = load_config(state_dir)
            rc, res = dispatch_action(
                state_dir,
                cfg,
                code=args.code,
                actor=args.actor,
                dry_run=args.dry_run,
                send_result=args.send_result,
                target_override=args.target,
            )
            _emit_output(res, as_json=args.json)
            return rc

        if args.cmd == "status":
            return _handle_status(state_dir, args.json)

        parser.error(f"unknown command: {args.cmd}")
        return 2
    except KeyError as exc:
        print(f"cubrid-pr-flow: {exc.args[0]}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError) as exc:
        print(f"cubrid-pr-flow: {exc}", file=sys.stderr)
        return 2
