from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BUYER_CREDENTIAL_NAMES = (
    "BUYER_WALLET_ADDRESS",
    "BUYER_WALLET_ID",
    "BUYER_SIGNER_PRIVATE_KEY",
)
SELLER_CREDENTIAL_NAMES = (
    "SELLER_WALLET_ADDRESS",
    "SELLER_WALLET_ID",
    "SELLER_SIGNER_PRIVATE_KEY",
)


def memory_db_path() -> Path:
    raw = os.getenv("PRIOR_MEMORY_DB", str(DATA_DIR / "sibyl-memory.db"))
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def jobs_path() -> Path:
    return DATA_DIR / "jobs.json"


def host() -> str:
    return os.getenv("PRIOR_HOST", "127.0.0.1")


def port() -> int:
    return int(os.getenv("PRIOR_PORT", "8787"))


def local_provider_enabled() -> bool:
    return os.getenv("PRIOR_LOCAL_PROVIDER", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def acp_enabled() -> bool:
    return os.getenv("ACP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _present(name: str) -> bool:
    value = os.getenv(name)
    return bool(value and value.strip())


def acp_env() -> dict[str, str | None]:
    names = BUYER_CREDENTIAL_NAMES + SELLER_CREDENTIAL_NAMES + ("ACP_NETWORK", "ACP_JOB_PRICE_USDC")
    out: dict[str, str | None] = {}
    for name in names:
        raw = os.getenv(name)
        out[name] = raw if raw and raw.strip() else None
    if not out.get("ACP_NETWORK"):
        out["ACP_NETWORK"] = "base-mainnet"
    return out


def missing_virtuals_credentials(*, role: str = "buyer") -> list[str]:
    names = BUYER_CREDENTIAL_NAMES if role == "buyer" else SELLER_CREDENTIAL_NAMES
    return [name for name in names if not _present(name)]


def acp_ready() -> bool:
    return acp_enabled() and not missing_virtuals_credentials(role="buyer")


def seller_ready() -> bool:
    return not missing_virtuals_credentials(role="seller")


def base_rpc_url() -> str:
    return os.getenv("BASE_RPC_URL", "https://sepolia.base.org")


def base_chain_id() -> int:
    return int(os.getenv("BASE_CHAIN_ID", "84532"))
