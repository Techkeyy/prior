import json
from pathlib import Path

from httpx import Client

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    c = Client(base_url="http://127.0.0.1:8787", timeout=90.0)
    r = c.post("/api/jobs", json={"text": "Research the top five AI wallet companies."})
    r.raise_for_status()
    job = r.json()
    print("specify", job["status"], "baseline", job["contract"]["baseline"])
    r2 = c.post(f"/api/jobs/{job['id']}/hire")
    print("hire", r2.status_code)
    r2.raise_for_status()
    hired = r2.json()
    findings = ((hired.get("deliverable") or {}).get("value") or {}).get("findings") or []
    print(
        "hire_status",
        hired["status"],
        "source",
        (hired.get("provider") or {}).get("source"),
        "findings",
        len(findings),
    )
    r3 = c.post(
        f"/api/jobs/{job['id']}/reject",
        json={"reason": "Important factual claims should include source links."},
    )
    r3.raise_for_status()
    rej = r3.json()
    print("proposed", (rej.get("proposed_lesson") or {}).get("requirement"))
    r4 = c.post(f"/api/jobs/{job['id']}/lessons", json={"action": "add"})
    r4.raise_for_status()
    print("add", r4.json().get("proposed_lesson", {}).get("status"))
    mem = c.get("/api/memory").json()
    print("memory_count", mem.get("count"))
    r6 = c.post("/api/jobs", json={"text": "Research the top five decentralized exchanges."})
    r6.raise_for_status()
    j2 = r6.json()
    print("job2_baseline", j2["contract"]["baseline"])
    print("job2_lessons", [item["requirement"] for item in j2["contract"]["applied_lessons"]])
    (ROOT / "evidence" / "live-loop.json").write_text(
        json.dumps(
            {
                "job1": {
                    "id": job["id"],
                    "baseline": job["contract"]["baseline"],
                    "hire_source": (hired.get("provider") or {}).get("source"),
                    "findings": len(findings),
                },
                "job2": {
                    "id": j2["id"],
                    "baseline": j2["contract"]["baseline"],
                    "applied": j2["contract"]["applied_lessons"],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
