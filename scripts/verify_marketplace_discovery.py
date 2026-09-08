"""READ-ONLY live marketplace discovery gate evidence.

User-shaped request -> live Virtuals browse -> normalize/filter/rank/select
-> exact outgoing payload preview. Proves memory propagation and truthful
no-match WITHOUT creating any ACP job (no create-job, fund, complete, or
reject bridge call is ever issued).

Isolation: all PRIOR stores point at a temp dir. Secrets from .env are used
for the read-only lookup and never printed. Wallet addresses are truncated
in console output and the saved evidence file.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_DIR = Path(tempfile.mkdtemp(prefix="prior-marketplace-gate-"))
os.environ["PRIOR_DATA_DIR"] = str(QA_DIR)
# Memory/identity paths must be pinned explicitly: settings loads the repo
# .env on import, whose PRIOR_MEMORY_DB would otherwise override the temp
# dir and share state across runs. Every store stays inside QA_DIR.
os.environ["PRIOR_MEMORY_DB"] = str(QA_DIR / "sibyl-memory.db")
os.environ["PRIOR_IDENTITY_DB"] = str(QA_DIR / "identity.db")
os.environ["PRIOR_LOCAL_PROVIDER"] = "false"

sys.path.insert(0, str(ROOT / "src"))
from dotenv import dotenv_values  # noqa: E402

for key, value in dotenv_values(ROOT / ".env").items():
    if value and key not in os.environ:
        os.environ[key] = value

os.environ["ACP_ENABLED"] = "true"

from prior import lessons as lessons_mod  # noqa: E402
from prior import memory as memory_mod  # noqa: E402
from prior import service  # noqa: E402
from prior.domain import Lesson  # noqa: E402
from prior.marketplace import (  # noqa: E402
    NoCompatibleProvider,
    build_capability_query,
    select_provider_for_spec,
)
from prior.providers import virtuals as virtuals_mod  # noqa: E402

WRITE_COMMANDS = {"create-job", "fund", "complete", "reject"}
bridge_commands: list[str] = []
_real_bridge = virtuals_mod._bridge


def _logging_bridge(args: list[str]) -> dict:
    bridge_commands.append(args[0] if args else "")
    return _real_bridge(args)


virtuals_mod._bridge = _logging_bridge
import prior.marketplace as marketplace_mod  # noqa: E402


def trunc(address: str) -> str:
    address = str(address or "")
    return address[:6] + "..." + address[-4:] if len(address) > 10 else "..."


def main() -> int:
    ws = "ws_marketplace_gate"
    evidence: dict = {"bridge_commands": [], "cases": []}

    # Case A: generic research request, live discovery.
    text_a = "Research the top five AI wallet companies and compare their features, pricing, strengths, and weaknesses."
    job_a = service.specify(ws, text_a)
    live_snapshot: list[dict] = []

    def _snapshotting(keyword: str) -> list[dict]:
        agents = marketplace_mod.discover_live(keyword)
        live_snapshot.extend(agents)
        return agents

    try:
        sel_a = select_provider_for_spec(job_a.spec, job_a.contract, discover=_snapshotting)
        q = sel_a.query
        case_a = {
            "request": text_a,
            "selected": True,
            "marketplace_query": q.to_dict(),
            "agents_seen": sel_a.agents_seen,
            "compatible_total": sel_a.compatible_total,
            "rejected_count": len(sel_a.rejections),
            "rejected_sample": [
                {"candidate": label.split(" / ")[0][:40], "reason": reason}
                for label, reason in sel_a.rejections[:8]
            ],
            "selected_provider": sel_a.candidate.agent_name,
            "selected_wallet": trunc(sel_a.candidate.wallet_address),
            "selected_offering": sel_a.candidate.offering_name,
            "task_evidence": sel_a.candidate.task_evidence,
            "score": sel_a.score,
            "score_breakdown": sel_a.score_breakdown,
        }
    except NoCompatibleProvider as exc:
        q = exc.query
        case_a = {
            "request": text_a,
            "selected": False,
            "truthful_no_match": True,
            "message": str(exc),
            "agents_seen": exc.candidates_seen,
            "rejected_count": len(exc.rejections),
        }
    evidence["cases"].append({"name": "A generic research, live discovery", **case_a})

    # Case B: lesson recall (deterministic, local) plus propagation replay.
    # The lesson-bearing wallet contract is replayed against the live Case-A
    # snapshot, so clause survival is proven deterministically while every
    # marketplace byte stays live.
    lesson = Lesson(
        id="L_gate_compare",
        workspace_id=ws,
        job_type="research",
        issue="comparison missing side-by-side summary",
        requirement="Include an explicit side-by-side comparison whenever multiple products are requested.",
        reason="gate fixture",
        status="active",
        created_at=lessons_mod.now_iso(),
    )
    memory_mod.write_lesson(ws, lesson)
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    text_b = "Research the top five decentralized exchanges and compare their features and pricing."
    job_b = service.specify(ws, text_b)
    applied_dex = [lesson.requirement for lesson in job_b.contract.applied_lessons]
    # Reworded wallet request: re-specifying identical text would return the
    # existing open job by design (_reusable_job), not a fresh contract.
    text_a2 = "Research the top 5 AI wallet companies and compare features, prices, strengths and weaknesses."
    job_w = service.specify(ws, text_a2)
    applied_wallet = [lesson.requirement for lesson in job_w.contract.applied_lessons]
    replay = {"replayed": False}
    live_attempt: dict = {"attempted": True}
    try:
        sel_b = select_provider_for_spec(job_b.spec, job_b.contract)
        preview = sel_b.requirement_preview
        payload_learned = preview.get("learned_requirements") or []
        brief_blob = " ".join(
            str(value) for value in (preview.get("requirement_data") or {}).values()
            if isinstance(value, str))
        live_attempt = {
            "attempted": True,
            "selected": True,
            "selected_provider": sel_b.candidate.agent_name,
            "selected_offering": sel_b.candidate.offering_name,
            "task_evidence": sel_b.candidate.task_evidence,
            "clause_in_executable_input": clause in brief_blob,
        }
    except NoCompatibleProvider as exc:
        live_attempt = {
            "attempted": True,
            "selected": False,
            "truthful_no_match": True,
            "message": str(exc),
            "agents_seen": exc.candidates_seen,
        }
    if live_snapshot and clause in applied_wallet:
        snapshot = list(live_snapshot)
        try:
            sel_r = select_provider_for_spec(
                job_w.spec, job_w.contract, discover=lambda keyword: snapshot)
            blob_r = " ".join(
                str(value) for value in sel_r.requirement_preview["requirement_data"].values()
                if isinstance(value, str))
            replay = {
                "replayed": True,
                "lesson_replay_on_live_snapshot": True,
                "selected_provider": sel_r.candidate.agent_name,
                "selected_offering": sel_r.candidate.offering_name,
                "clause_in_executable_input": clause in blob_r,
                "clause_in_payload": clause in (sel_r.requirement_preview.get("learned_requirements") or []),
            }
        except NoCompatibleProvider as exc:
            replay = {"replayed": True, "selected": False,
                      "truthful_no_match": True, "message": str(exc)}
    case_b = {
        "request": text_b,
        "clause_recalled_for_dex": clause in applied_dex,
        "clause_recalled_for_wallet": clause in applied_wallet,
        "live_attempt": live_attempt,
        "replay": replay,
    }
    evidence["cases"].append({"name": "B learned clause propagation", **case_b})

    # Case E: truthful no-match with fixture data (no bridge writes possible).
    def _fixture_no_match(keyword: str) -> list[dict]:
        return [{
            "id": "ghost", "name": "Ghost Agent", "description": "research",
            "walletAddress": "0x0000000000000000000000000000000000000001",
            "lastActiveAt": "", "rating": None, "isHidden": False,
            "offerings": [{
                "name": "Hidden Research",
                "description": "research",
                "requirements": {"required": ["quantum_entanglement_proof"]},
                "isHidden": True,
            }],
        }]

    try:
        select_provider_for_spec(job_a.spec, job_a.contract, discover=_fixture_no_match)
        case_e = {"no_match": False}
    except NoCompatibleProvider as exc:
        case_e = {"no_match": True, "message": str(exc),
                  "candidates_seen": exc.candidates_seen,
                  "rejections": [{"candidate": label[:40], "reason": reason}
                                 for label, reason in exc.rejections[:5]]}
    evidence["cases"].append({"name": "E truthful no-match", **case_e})

    # Case F: live end-to-end propagation probe on a security-research
    # request. The market decides: selection proves clause survival live,
    # no-match is recorded truthfully. Every probed request is reported.
    text_f = "Research Base wallet security practices and compare the leading approaches."
    job_f = service.specify(ws, text_f)
    applied_f = [lesson.requirement for lesson in job_f.contract.applied_lessons]
    case_f: dict = {"request": text_f, "clause_recalled": clause in applied_f}
    try:
        sel_f = select_provider_for_spec(job_f.spec, job_f.contract)
        blob_f = " ".join(
            str(value) for value in sel_f.requirement_preview["requirement_data"].values()
            if isinstance(value, str))
        case_f.update({
            "selected": True,
            "selected_provider": sel_f.candidate.agent_name,
            "selected_wallet": trunc(sel_f.candidate.wallet_address),
            "selected_offering": sel_f.candidate.offering_name,
            "task_evidence": sel_f.candidate.task_evidence,
            "subject_evidence": sel_f.candidate.subject_evidence,
            "schema_notes": sel_f.candidate.schema_notes,
            "score_breakdown": sel_f.score_breakdown,
            "clause_in_executable_input": clause in blob_f,
            "clause_in_payload": clause in (sel_f.requirement_preview.get("learned_requirements") or []),
        })
    except NoCompatibleProvider as exc:
        case_f.update({"selected": False, "truthful_no_match": True,
                       "agents_seen": exc.candidates_seen})
    evidence["cases"].append({"name": "F live selection probe", **case_f})

    evidence["bridge_commands"] = sorted(set(bridge_commands))
    writes = sorted(set(bridge_commands) & WRITE_COMMANDS)
    evidence["acp_job_created"] = False
    evidence["write_commands_issued"] = writes

    print("=== LIVE DISCOVERY EVIDENCE (read-only) ===")
    print(f"request A: {text_a}")
    if case_a.get("selected"):
        print(f"marketplace query: {q.primary_keyword} | task={q.task_capabilities} | subjects={q.subject_terms[:8]}")
        print(f"agents seen: {sel_a.agents_seen} | compatible: {sel_a.compatible_total} | rejected: {len(sel_a.rejections)}")
        for row in case_a["rejected_sample"][:5]:
            print(f"  rejected: {row['candidate']} -- {row['reason']}")
        print(f"selected: {sel_a.candidate.agent_name} [{trunc(sel_a.candidate.wallet_address)}] / {sel_a.candidate.offering_name}")
        print(f"task evidence: {sel_a.candidate.task_evidence} | score: {sel_a.score} {sel_a.score_breakdown}")
        print(f"subject evidence: {sel_a.candidate.subject_evidence}")
    else:
        print(f"request A truthful no-match: {case_a.get('message')} (agents seen: {case_a.get('agents_seen')})")
    if case_b.get("live_attempt", {}).get("selected"):
        attempt = case_b["live_attempt"]
        print(f"request B live selected: {attempt['selected_provider']} / {attempt['selected_offering']}")
        print(f"request B clause in executable input: {attempt['clause_in_executable_input']}")
    else:
        print(f"request B live truthful no-match; clause recalled: {case_b.get('clause_recalled_for_dex')}")
    print(f"replay on live snapshot: {replay}")
    if case_f.get("selected"):
        print(f"request F live selected: {case_f['selected_provider']} / {case_f['selected_offering']}")
        print(f"request F task evidence: {case_f['task_evidence']}")
        print(f"request F subject evidence: {case_f['subject_evidence']}")
        print(f"request F clause in executable input: {case_f['clause_in_executable_input']}")
    else:
        print("request F live truthful no-match")
    print(f"no-match truthful: {case_e.get('no_match')}")
    print(f"bridge commands used: {sorted(set(bridge_commands))}")
    print(f"ACP write commands issued: {writes if writes else 'NONE'}")
    print("ACP JOB CREATED: NO")

    out = ROOT / "evidence" / "marketplace-discovery.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"evidence saved: {out}")

    propagation_ok = (
        replay.get("replayed") and replay.get("clause_in_executable_input")
        and replay.get("clause_in_payload"))
    if case_b.get("live_attempt", {}).get("selected"):
        propagation_ok = propagation_ok or (
            case_b["live_attempt"].get("clause_in_executable_input") is True)
    if case_f.get("selected"):
        propagation_ok = propagation_ok or (
            case_f.get("clause_in_executable_input") is True)
    ok = (case_b.get("clause_recalled_for_dex", False)
          and case_b.get("clause_recalled_for_wallet", False)
          and case_f.get("clause_recalled", False)
          and propagation_ok
          and case_e.get("no_match") is True and not writes)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
