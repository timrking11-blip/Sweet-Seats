"""SS-RESEARCH-0.3 offline increment: request -> approval -> reservation -> provider -> validation -> export.

Approval store and budget ledger are in-memory contract models of the future durable runner; they do not
implement authentication or persistence. The provider is any transport callable; the CLI replays mocked
Claude responses and makes zero network calls.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from adapters import claude_research as claude
from jobs.research_contracts import (FOOTER, MARKER, ContractError, digest, timestamp, validate_report,
                                     validate_request)

VERSION = claude.VERSION
Transport = Callable[[dict], dict]


class ApprovalStore:
    """Protected approval state. Callers look approvals up by digest; they never submit approval objects."""

    def __init__(self, trusted_actors: set[str]):
        self._trusted, self._records = set(trusted_actors), {}

    def record(self, actor_id: str, bound_digest: str, expires_at: str) -> str:
        if actor_id not in self._trusted:
            raise ContractError("untrusted approver")
        approval_id = str(uuid.uuid4())
        self._records[bound_digest] = {"approval_id": approval_id, "actor_id": actor_id, "digest": bound_digest,
                                       "expires_at": expires_at, "consumed": False}
        return approval_id

    def get(self, bound_digest: str) -> dict:
        record = self._records.get(bound_digest)
        if record is None:
            raise ContractError("no execution approval for this exact request")
        if record["consumed"]:
            raise ContractError("execution approval already consumed")
        return {k: record[k] for k in ("approval_id", "actor_id", "digest", "expires_at")}

    def consume(self, bound_digest: str) -> None:
        self._records[bound_digest]["consumed"] = True


class BudgetLedger:
    """Reservations per logical request, enforced against hourly and daily aggregates."""

    def __init__(self, hourly_cents: int, daily_cents: int):
        self.hourly, self.daily, self.entries = hourly_cents, daily_cents, {}

    def _committed(self, since: datetime) -> int:
        return sum(e["actual"] if e["status"] == "settled" else e["reserved"]
                   for e in self.entries.values() if e["at"] >= since)

    def reserve(self, key: str, cents: int, now: datetime) -> dict:
        entry = self.entries.get(key)
        if entry is not None:
            if entry["status"] == "reserved":
                return entry  # a runner retry reuses the reservation; it never stacks a new one
            raise ContractError(f"request has a {entry['status']} charge; reconcile before repeating")
        for since, cap in ((now - timedelta(hours=1), self.hourly), (now - timedelta(days=1), self.daily)):
            if self._committed(since) + cents > cap:
                raise ContractError("aggregate budget exceeded")
        entry = {"reservation_id": str(uuid.uuid4()), "reserved": cents, "actual": None,
                 "status": "reserved", "at": now, "overrun": False}
        self.entries[key] = entry
        return entry

    def settle(self, key: str, actual: int) -> dict:
        entry = self.entries[key]
        entry.update(actual=actual, status="settled", overrun=actual > entry["reserved"])
        return entry

    def mark_unresolved(self, key: str) -> None:
        self.entries[key]["status"] = "unresolved"


def execute(request: dict, profile: dict, store: ApprovalStore, ledger: BudgetLedger, policy: dict,
            completed: set[str], transport: Transport, now: datetime) -> dict:
    profile_digest = claude.validate_profile(profile)
    if request.get("execution_profile_digest") != profile_digest or profile_digest not in policy["approved_profiles"]:
        raise ContractError("execution profile not approved for this request")
    request_digest = digest(request)
    key = validate_request(request, store.get(request_digest), policy, now, version=VERSION,
                           extra_fields=frozenset({"execution_profile_digest"}))
    if key in completed:
        raise ContractError("request already completed; a rerun needs a new revision and approval")
    ceiling = claude.ceiling_cents(profile)
    if ceiling > request["budget_cents"]:
        raise ContractError("profile worst case exceeds approved request budget")
    reservation = ledger.reserve(key, ceiling, now)
    store.consume(request_digest)

    params, messages = claude.build_request_params(profile, request["brief"]), []
    try:
        for _ in range(1 + profile["max_continuations"]):
            message = transport(params)
            messages.append(message)
            if message.get("stop_reason") != "pause_turn":
                break
            # Resume the server-side loop by resending the paused assistant turn; no extra user message.
            params = dict(params, messages=params["messages"] + [{"role": "assistant", "content": message["content"]}])
    except Exception as exc:
        ledger.mark_unresolved(key)  # dispatch outcome unknown: may have billed
        raise ContractError("provider outcome ambiguous; reconcile before repeating") from exc

    usage = claude.total_usage(messages)
    entry = ledger.settle(key, claude.actual_cents(usage, profile))
    completed_at = now.isoformat().replace("+00:00", "Z")
    body = claude.normalize(messages, profile, completed_at)
    report = {"contract_version": VERSION, "report_id": str(uuid.uuid4()), "report_version": 1,
              "run_id": str(uuid.uuid4()), "request_key": key, "request_digest": request_digest,
              "execution_profile_digest": profile_digest,
              "provider": {"provider": profile["provider"], "interface": profile["interface"],
                           "model": profile["model"], "response_ids": body.pop("response_ids"),
                           "stop_reasons": body.pop("stop_reasons")},
              "created_at": completed_at, "retention_until": request["retention_until"],
              "allowed_use": request["allowed_use"], **body,
              "cost": {"reservation_id": reservation["reservation_id"], "reserved_cents": entry["reserved"],
                       "actual_cents": entry["actual"], "overrun": entry["overrun"], "usage": usage,
                       "pricing_verified_at": profile["pricing"]["verified_at"]},
              "review_status": "pending_human_review"}
    claude.validate_report_schema(report)
    validate_report(report, request)
    completed.add(key)
    return report


def render_markdown(report: dict) -> str:
    lines = [MARKER, f"# Research review export {report['report_id']}", "",
             f"Request `{report['request_key']}` · profile `{report['execution_profile_digest'][:12]}` · "
             f"{report['provider']['model']} · status **{report['review_status']}**", "",
             "## Executive summary", report["executive_summary"], "", "## Claims (all unverified)"]
    lines += [f"- [{c['id']}] ({c['kind']}, {c['confidence']}) {c['text']} — evidence: "
              f"{', '.join(c['evidence_ids']) or 'none'}" for c in report["claims"]]
    for title, field in (("Alternatives", "alternatives"), ("Risks and unknowns", "risks_unknowns"),
                         ("Next actions", "next_actions")):
        lines += ["", f"## {title}"] + [f"- {item}" for item in report[field]]
    lines += ["", "## Evidence (rights unverified)"]
    lines += [f"- [{e['id']}] {e['title']} <{e['url']}> ({e['origin']}, {e['retrieved_at']})" for e in report["evidence"]]
    cost = report["cost"]
    lines += ["", f"Cost: {cost['actual_cents']}¢ actual of {cost['reserved_cents']}¢ reserved"
              f"{' — OVERRUN' if cost['overrun'] else ''}; pricing verified: {cost['pricing_verified_at'] or 'no'}.",
              "", FOOTER]
    return "\n".join(lines)


def write_review_export(report: dict, out_dir: Path) -> list[Path]:
    """Saved review export only; no Linear comment or other publication."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / f"{report['report_id']}.json", out_dir / f"{report['report_id']}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return [json_path, md_path]


def replay(responses: list[dict]) -> Transport:
    queue = list(responses)
    return lambda params: queue.pop(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    policy, now = fixture["policy"], timestamp(fixture["now"])
    store = ApprovalStore(set(policy["trusted_actors"]))
    for approval in fixture["approvals"]:
        store.record(approval["actor_id"], approval["digest"], approval["expires_at"])
    ledger = BudgetLedger(policy["hourly_budget_cents"], policy["daily_budget_cents"])
    report = execute(fixture["request"], fixture["profile"], store, ledger, policy, set(),
                     replay(fixture["mock_responses"]), now)
    paths = write_review_export(report, args.export_dir)
    print(json.dumps({"synthetic": True, "network_calls": 0, "report_id": report["report_id"],
                      "cost": report["cost"], "exported": [str(p) for p in paths]}, indent=2))


if __name__ == "__main__":
    main()
