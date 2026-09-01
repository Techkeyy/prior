from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def memory_db_path() -> Path:
    raw = os.getenv("PRIOR_MEMORY_DB", str(DATA_DIR / "sibyl-memory.db"))
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def jobs_path() -> Path:
    path = DATA_DIR / "jobs.json"
    return path


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


def acp_env() -> dict[str, str | None]:
    return {
        "WHITELISTED_WALLET_PRIVATE_KEY": os.getenv("WHITELISTED_WALLET_PRIVATE_KEY") or None,
        "BUYER_AGENT_WALLET_ADDRESS": os.getenv("BUYER_AGENT_WALLET_ADDRESS") or None,
        "BUYER_ENTITY_ID": os.getenv("BUYER_ENTITY_ID") or None,
        "SELLER_AGENT_WALLET_ADDRESS": os.getenv("SELLER_AGENT_WALLET_ADDRESS") or None,
        "SELLER_ENTITY_ID": os.getenv("SELLER_ENTITY_ID") or None,
        "ACP_NETWORK": os.getenv("ACP_NETWORK", "base-mainnet"),
    }


def acp_ready() -> bool:
    env = acp_env()
    return bool(
        acp_enabled()
        and env["WHITELISTED_WALLET_PRIVATE_KEY"]
        and env["BUYER_AGENT_WALLET_ADDRESS"]
        and env["BUYER_ENTITY_ID"]
    )


def base_rpc_url() -> str:
    return os.getenv("BASE_RPC_URL", "https://sepolia.base.org")


def base_chain_id() -> int:
    return int(os.getenv("BASE_CHAIN_ID", "84532"))
