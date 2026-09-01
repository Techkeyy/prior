from __future__ import annotations

from sibyl_memory_client import MemoryClient

from prior.settings import (
    acp_enabled,
    acp_ready,
    base_rpc_url,
    host,
    local_provider_enabled,
    memory_db_path,
    port,
)


def snapshot() -> dict:
    checks = []
    db = memory_db_path()
    try:
        client = MemoryClient.local(db, tenant_id="ws_doctor")
        client.set_state("doctor", {"ok": True})
        checks.append({"name": "sibyl-memory", "status": "PASS", "detail": str(db)})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "sibyl-memory", "status": "FAIL", "detail": str(exc)})

    if acp_ready():
        checks.append({"name": "virtuals-acp", "status": "PASS", "detail": "credentials present"})
    elif acp_enabled():
        checks.append(
            {
                "name": "virtuals-acp",
                "status": "FAIL",
                "detail": "ACP_ENABLED is true but wallet/entity credentials are missing",
            }
        )
    else:
        checks.append(
            {
                "name": "virtuals-acp",
                "status": "WARN",
                "detail": "ACP not configured. Hire will fail unless PRIOR_LOCAL_PROVIDER is on.",
            }
        )

    if local_provider_enabled():
        checks.append(
            {
                "name": "local-provider",
                "status": "WARN",
                "detail": "Local research provider is on. This is not a Virtuals ACP job.",
            }
        )
    else:
        checks.append({"name": "local-provider", "status": "PASS", "detail": "off"})

    checks.append({"name": "base-rpc", "status": "WARN", "detail": f"configured {base_rpc_url()} (not probed here)"})
    overall = "FAIL" if any(item["status"] == "FAIL" for item in checks) else "READY WITH WARNINGS"
    if all(item["status"] == "PASS" for item in checks):
        overall = "READY"
    return {
        "overall": overall,
        "listen": f"{host()}:{port()}",
        "checks": checks,
    }


def main() -> None:
    import json

    print(json.dumps(snapshot(), indent=2))
