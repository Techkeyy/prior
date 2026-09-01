"""Execute a real B20 factory read on Base. Does not invent a payment."""

from __future__ import annotations

import json
import sys

from prior.base_action import read_b20_factory, save_evidence


def main() -> int:
    mainnet = read_b20_factory(url="https://mainnet.base.org")
    sepolia = read_b20_factory(url="https://sepolia.base.org")
    evidence = {
        "pass": bool(mainnet.get("ok") and sepolia.get("ok")),
        "mainnet": mainnet,
        "sepolia": sepolia,
    }
    path = save_evidence(evidence)
    print(json.dumps({"evidence": str(path), **evidence}, indent=2)[:3000])
    return 0 if evidence["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
