"""Prove Base RPC reachability. Do not fabricate a payment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "base-kill-test.json"

NETWORKS = {
    "base-sepolia": {"url": "https://sepolia.base.org", "chain_id": 84532},
    "base-mainnet": {"url": "https://mainnet.base.org", "chain_id": 8453},
}


def eth_call(url: str, method: str, params: list) -> dict:
    response = httpx.post(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    results = {}
    for name, net in NETWORKS.items():
        try:
            payload = eth_call(net["url"], "eth_chainId", [])
            block = eth_call(net["url"], "eth_blockNumber", [])
            chain_hex = payload.get("result")
            chain_id = int(chain_hex, 16) if chain_hex else None
            results[name] = {
                "ok": chain_id == net["chain_id"],
                "url": net["url"],
                "expected_chain_id": net["chain_id"],
                "observed_chain_id": chain_id,
                "block_number_hex": block.get("result"),
            }
        except Exception as exc:  # noqa: BLE001
            results[name] = {"ok": False, "url": net["url"], "error": str(exc)}

    evidence = {
        "pass": all(item.get("ok") for item in results.values()),
        "networks": results,
        "product_action": (
            "Preferred Base action is the Virtuals ACP job payment/escrow on Base, "
            "once ACP credentials exist. This probe only proves the RPCs are live. "
            "No self-transfer was sent."
        ),
    }
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
