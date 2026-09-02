"""Base onchain reads used by PRIOR.

Preferred commercial action is still a real ACP payment on Base.
This module performs a documented B20 factory read so the Base path is
a real chain call, not a logo. It does not invent a transaction hash.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from prior.settings import ROOT, base_rpc_url

# Official B20 factory precompile. Same on Base mainnet and Base Sepolia.
# https://docs.base.org/base-chain/specs/upgrades/beryl/b20
B20_FACTORY = "0xB20f000000000000000000000000000000000000"
POLICY_REGISTRY = "0x8453000000000000000000000000000000000002"

# 4-byte keccak256 function selectors
IS_B20_SELECTOR = "0xfa19b927"  # isB20(address)
POLICY_EXISTS_SELECTOR = "0x330f5637"  # policyExists(uint64)


def _eth_call(to: str, data: str, url: str | None = None) -> str:
    rpc = url or base_rpc_url()
    response = httpx.post(
        rpc,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to, "data": data}, "latest"],
        },
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return str(payload.get("result") or "")


def read_b20_factory(*, url: str | None = None) -> dict:
    """Call B20Factory.isB20(factory). Product reason: confirm the hire
    network is Base with the native token factory before treating a payment
    as Base-native.
    """
    factory_data = IS_B20_SELECTOR + ("0" * 24) + B20_FACTORY[2:]
    factory_result = _eth_call(B20_FACTORY, factory_data, url=url)
    policy_data = POLICY_EXISTS_SELECTOR + ("0" * 64)
    policy_result = _eth_call(POLICY_REGISTRY, policy_data, url=url)
    return {
        "ok": bool(factory_result) and bool(policy_result),
        "factory": B20_FACTORY,
        "policy_registry": POLICY_REGISTRY,
        "isB20_factory": factory_result,
        "policyExists_0": policy_result,
        "rpc": url or base_rpc_url(),
        "product_reason": (
            "PRIOR hires settle on Base. These calls read the official B20 factory "
            "and Policy Registry precompiles. They are not an ACP payment."
        ),
        "qualifies_as": "B20 read",
        "not_claimed": "ACP payment / wallet transfer",
    }


def save_evidence(payload: dict, path: Path | None = None) -> Path:
    out = path or (ROOT / "evidence" / "base-b20-read.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out
