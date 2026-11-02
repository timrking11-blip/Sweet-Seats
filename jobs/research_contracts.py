"""SS-RESEARCH-0.2: offline validators, never authentication or network execution."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

VERSION = "SS-RESEARCH-0.2"
MARKER = "<!-- sweet-seats:research-report -->"
FOOTER = "Advisory only. Not an approved decision until recorded in the Notion Decision Register."


class ContractError(ValueError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ContractError("invalid timezone-aware timestamp") from exc


def request_key(request: dict) -> str:
    return digest({k: request[k] for k in ("team_id", "project_id", "issue_id", "request_id", "revision", "mode")})


def validate_approval(approval: dict, expected_digest: str, trusted_actors: set[str], now: datetime) -> None:
    # trusted_actors and records must come from the authenticated operator service in production.
    if approval.get("actor_id") not in trusted_actors:
        raise ContractError("untrusted approver")
    if approval.get("digest") != expected_digest:
        raise ContractError("approval content/scope mismatch")
    if timestamp(approval["expires_at"]) <= now:
        raise ContractError("approval expired")
    if not approval.get("approval_id"):
        raise ContractError("approval identity required")


def validate_request(request: dict, approval: dict, policy: dict, now: datetime, *,
                     version: str = VERSION, extra_fields: frozenset = frozenset()) -> str:
    required = {"version", "team_id", "project_id", "issue_id", "request_id", "revision", "mode",
                "brief", "classification", "allowed_use", "budget_cents", "timeout_seconds",
                "expires_at", "retention_until"} | extra_fields
    if set(request) != required:
        raise ContractError("request fields do not match contract")
    if request["version"] != version:
        raise ContractError("unsupported contract version")
    if request["team_id"] not in policy["allowed_teams"] or request["project_id"] not in policy["allowed_projects"]:
        raise ContractError("scope denied")
    try:
        UUID(request["request_id"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ContractError("invalid request identity") from exc
    if type(request["revision"]) is not int or request["revision"] < 1:
        raise ContractError("invalid revision")
    if not isinstance(request["issue_id"], str) or not request["issue_id"]:
        raise ContractError("issue identity required")
    if request["mode"] != "quick":
        raise ContractError("deep research deferred")
    if request["classification"] != "public" or request["allowed_use"] != "internal_research":
        raise ContractError("permission denied")
    if not isinstance(request["brief"], str) or not 0 < len(request["brief"]) <= 8000:
        raise ContractError("invalid reviewed brief")
    for field, limit in (("budget_cents", policy["max_budget_cents"]),
                         ("timeout_seconds", policy["max_timeout_seconds"])):
        if type(request[field]) is not int or not 0 < request[field] <= limit:
            raise ContractError("execution limit denied")
    if timestamp(request["expires_at"]) <= now or timestamp(request["retention_until"]) <= now:
        raise ContractError("request/retention expired")
    validate_approval(approval, digest(request), set(policy["trusted_actors"]), now)
    return request_key(request)


def select_hourly(candidates: list[dict], approvals: dict, completed: set[str], policy: dict,
                  now: datetime) -> list[dict]:
    """Plan at most one pending run. This does not enqueue, research or publish."""
    selected, seen = [], set(completed)
    for candidate in candidates:
        if candidate.get("label") != "research-quick":
            continue
        request = candidate.get("request", {})
        try:
            key = validate_request(request, approvals[digest(request)], policy, now)
        except (ContractError, KeyError, TypeError):
            continue
        if key in seen:
            continue
        seen.add(key)
        selected.append({"key": key, "request_digest": digest(request), "status": "planned"})
        break  # one request per hourly tick; serial execution in the future runner
    return selected


def publication_digest(target: dict, body: str) -> str:
    """Exact final body including marker/footer; no truncation after approval."""
    if set(target) != {"workspace_id", "issue_id"} or not all(target.values()):
        raise ContractError("exact publication target required")
    if not body.startswith(MARKER) or not body.endswith(FOOTER):
        raise ContractError("missing canonical report marker/footer")
    return digest({"target": target, "body": body, "version": VERSION})


def validate_report(report: dict, request: dict) -> None:
    if report.get("request_digest") != digest(request) or report.get("allowed_use") != "internal_research":
        raise ContractError("report lineage/use mismatch")
    evidence = report.get("evidence", [])
    ids = [e.get("id") for e in evidence]
    if not ids or any(not x for x in ids) or len(set(ids)) != len(ids):
        raise ContractError("evidence identities required and unique")
    for item in evidence:
        if not isinstance(item.get("url"), str) or not item["url"].startswith("https://"):
            raise ContractError("source URL required")
        timestamp(item.get("retrieved_at"))
    for claim in report.get("claims", []):
        refs = claim.get("evidence_ids", [])
        if claim.get("kind") not in {"fact", "inference", "recommendation", "unknown"}:
            raise ContractError("claim kind required")
        if claim["kind"] != "unknown" and not refs:
            raise ContractError("claim evidence required")
        if not set(refs).issubset(ids):
            raise ContractError("dangling evidence reference")
    if not report.get("claims"):
        raise ContractError("claims required")
