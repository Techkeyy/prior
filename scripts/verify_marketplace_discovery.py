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
    sel_a = select_provider_for_spec(job_a.spec, job_a.contract)
    q = sel_a.query
    case_a = {
        "request": text_a,
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
        "score": sel_a.score,
        "score_breakdown": sel_a.score_breakdown,
    }
    evidence["cases"].append({"name": "A generic research, live discovery", **case_a})

    # Case B: active learned clause must survive into the provider payload.
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
    text_b = "Research the top five decentralized exchanges and compare their features and pricing."
    job_b = service.specify(ws, text_b)
    applied = [lesson.requirement for lesson in job_b.contract.applied_lessons]
    sel_b = select_provider_for_spec(job_b.spec, job_b.contract)
    payload_learned = sel_b.requirement_preview.get("learned_requirements") or []
    description = str(sel_b.requirement_preview.get("job_description") or "")
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    case_b = {
        "request": text_b,
        "contract_clauses": applied,
        "payload_learned": payload_learned,
        "clause_in_contract": clause in applied,
        "clause_in_payload": clause in payload_learned,
        "clause_in_job_description": clause in description,
        "selected_provider": sel_b.candidate.agent_name,
        "selected_wallet": trunc(sel_b.candidate.wallet_address),
        "selected_offering": sel_b.candidate.offering_name,
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

    evidence["bridge_commands"] = sorted(set(bridge_commands))
    writes = sorted(set(bridge_commands) & WRITE_COMMANDS)
    evidence["acp_job_created"] = False
    evidence["write_commands_issued"] = writes

    print("=== LIVE DISCOVERY EVIDENCE (read-only) ===")
    print(f"request A: {text_a}")
    print(f"marketplace query: {q.primary_keyword} | required={q.required_terms[:8]}")
    print(f"agents seen: {sel_a.agents_seen} | compatible: {sel_a.compatible_total} | rejected: {len(sel_a.rejections)}")
    for row in case_a["rejected_sample"][:5]:
        print(f"  rejected: {row['candidate']} -- {row['reason']}")
    print(f"selected: {sel_a.candidate.agent_name} [{trunc(sel_a.candidate.wallet_address)}] / {sel_a.candidate.offering_name}")
    print(f"score: {sel_a.score} {sel_a.score_breakdown}")
    print(f"request B clause in contract: {case_b['clause_in_contract']}")
    print(f"request B clause in payload: {case_b['clause_in_payload']}")
    print(f"request B clause in job_description: {case_b['clause_in_job_description']}")
    print(f"no-match truthful: {case_e.get('no_match')}")
    print(f"bridge commands used: {sorted(set(bridge_commands))}")
    print(f"ACP write commands issued: {writes if writes else 'NONE'}")
    print("ACP JOB CREATED: NO")

    out = ROOT / "evidence" / "marketplace-discovery.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"evidence saved: {out}")

    ok = (case_b["clause_in_contract"] and case_b["clause_in_payload"]
          and case_e.get("no_match") is True and not writes)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
