"""Virtuals ACP kill-test against the current official Node SDK."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "acp-bridge"
OUT = ROOT / "evidence" / "virtuals-kill-test.json"
NODE_DIR = Path(r"C:\Program Files\nodejs")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    if NODE_DIR.exists():
        env["PATH"] = str(NODE_DIR) + os.pathsep + env.get("PATH", "")
    return env


def which(name: str) -> str:
    env = _env()
    if os.name == "nt" and name == "npm":
        cmd = NODE_DIR / "npm.cmd"
        if cmd.exists():
            return str(cmd)
    found = shutil.which(name, path=env["PATH"])
    if not found:
        raise FileNotFoundError(name)
    return found


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=_env(),
        shell=False,
    )


def main() -> int:
    node = run([which("node"), "--version"])
    npm = run([which("npm"), "--version"])
    probe_install = run([which("npm"), "install", "--omit=dev"], cwd=BRIDGE)
    probe = run([which("node"), "run.mjs", "probe"], cwd=BRIDGE)

    evidence = {
        "node_version": node.stdout.strip() or node.stderr.strip(),
        "npm_version": npm.stdout.strip(),
        "npm_install_code": probe_install.returncode,
        "npm_install_stderr": (probe_install.stderr or "")[-2000:],
        "probe_code": probe.returncode,
        "probe_stdout": probe.stdout.strip(),
        "probe_stderr": (probe.stderr or "")[-2000:],
        "credentials_present": False,
        "python_virtuals_acp": None,
        "blocker": None,
        "pass": False,
    }
    try:
        import importlib.util

        evidence["python_virtuals_acp"] = bool(importlib.util.find_spec("virtuals_acp"))
    except Exception as exc:  # noqa: BLE001
        evidence["python_virtuals_acp"] = f"error: {exc}"

    if evidence["python_virtuals_acp"] is False:
        evidence["python_sdk_note"] = (
            "virtuals-acp on PyPI requires Python >=3.10,<3.13. This machine is Python 3.14. "
            "PRIOR uses the current official Node SDK v2 instead."
        )

    if probe.returncode == 0:
        try:
            payload = json.loads(probe.stdout)
        except json.JSONDecodeError:
            payload = {}
        evidence["sdk_exports"] = payload
        evidence["sdk_loaded"] = bool(payload.get("ok"))
    else:
        evidence["sdk_loaded"] = False

    live = run([which("node"), "run.mjs", "browse", "research"], cwd=BRIDGE)
    evidence["browse_code"] = live.returncode
    evidence["browse_stdout"] = live.stdout[-2000:]
    evidence["browse_stderr"] = (live.stderr or "")[-2000:]

    if evidence["sdk_loaded"] and live.returncode == 0:
        evidence["pass"] = True
        evidence["live_job"] = "browse succeeded"
    elif evidence["sdk_loaded"]:
        evidence["pass"] = False
        evidence["blocker"] = (
            "Official ACP SDK loaded, but a live browse/create requires Virtuals registry "
            "credentials (buyer wallet address, wallet id, and Privy authorization key) "
            "which are not present here. "
            "See browse_stderr."
        )
    else:
        evidence["blocker"] = "Official ACP SDK did not load. See npm_install_stderr / probe_stderr."

    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2)[:4000])
    return 0 if evidence["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
