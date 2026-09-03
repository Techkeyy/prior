from __future__ import annotations

from sibyl_memory_client import MemoryClient

from prior.settings import (
    acp_enabled,
    acp_ready,
    base_rpc_url,
    build_commit,
    host,
    local_provider_enabled,
    memory_db_path,
    missing_virtuals_credentials,
    port,
    seller_ready,
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

    missing = missing_virtuals_credentials()
    if acp_ready():
        checks.append({"name": "virtuals-acp-buyer", "status": "PASS", "detail": "buyer v2 credentials present"})
    elif acp_enabled():
        checks.append(
            {
                "name": "virtuals-acp-buyer",
                "status": "FAIL",
                "detail": "ACP_ENABLED is true but missing: " + ", ".join(missing),
            }
        )
    else:
        checks.append(
            {
                "name": "virtuals-acp-buyer",
                "status": "WARN",
                "detail": "ACP off. Missing: " + ", ".join(missing or ["ACP_ENABLED"]),
            }
        )

    if seller_ready():
        checks.append({"name": "virtuals-acp-seller", "status": "PASS", "detail": "seller v2 credentials present"})
    else:
        checks.append(
            {
                "name": "virtuals-acp-seller",
                "status": "WARN",
                "detail": "seller missing: " + ", ".join(missing_virtuals_credentials(role="seller")),
            }
        )

    if local_provider_enabled() and not acp_enabled():
        checks.append(
            {
                "name": "local-provider",
                "status": "WARN",
                "detail": "LOCAL PROVIDER is on. This is a development provider, not Virtuals.",
            }
        )
    else:
        checks.append({"name": "local-provider", "status": "PASS", "detail": "not the active hire path"})

    checks.append({"name": "base-rpc", "status": "WARN", "detail": f"configured {base_rpc_url()} (not probed here)"})
    overall = "FAIL" if any(item["status"] == "FAIL" for item in checks) else "READY WITH WARNINGS"
    if all(item["status"] == "PASS" for item in checks):
        overall = "READY"
    return {
        "overall": overall,
        "build_commit": build_commit(),
        "listen": f"{host()}:{port()}",
        "checks": checks,
    }


def main() -> None:
    import json

    print(json.dumps(snapshot(), indent=2))


if __name__ == "__main__":
    main()
