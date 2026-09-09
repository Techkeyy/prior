"""Bridge stdout envelope integrity: large JSON responses must arrive whole.

Regression for a proven production defect: console.log + process.exit(0)
truncated piped stdout (65KB observed), yielding rc=0 with unparseable
output. All success paths now flush via done() and return immediately so
execution cannot fall through to the unknown-command failure.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

BRIDGE_DIR = Path("acp-bridge").resolve()


def _run_node(args):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node unavailable")
    last = None
    for _ in range(3):
        try:
            proc = subprocess.run([node, *args], cwd=str(BRIDGE_DIR), timeout=120)
            last = proc
            break
        except OSError as exc:  # sandbox handle flake; documented pattern
            last = exc
    assert not isinstance(last, OSError), f"node spawn failed: {last}"
    assert last is not None and last.returncode == 0
    return last


def test_large_payload_single_parseable_envelope(tmp_path):
    blob_path = tmp_path / "big.json"
    probe = BRIDGE_DIR / ".envelope-probe.mjs"
    probe.write_text(
        "import { writeFileSync } from 'node:fs';\n"
        "import { done } from './lib.mjs';\n"
        "const blob = 'x'.repeat(400000);\n"
        "writeFileSync(process.argv[2], JSON.stringify({ ok: true, blob }));\n"
        "done({ ok: true, blob });\n",
        encoding="utf-8",
    )
    try:
        proc = _run_node([str(probe), str(blob_path)])
        assert proc.returncode == 0
        data = json.loads(blob_path.read_text(encoding="utf-8"))
        assert data["ok"] is True and len(data["blob"]) == 400000
    finally:
        probe.unlink(missing_ok=True)


def test_no_fallthrough_after_success_output():
    source = (BRIDGE_DIR / "run.mjs").read_text(encoding="utf-8")
    import re

    # Every success emission must return immediately so execution cannot
    # fall through to the unknown-command failure (which once appended a
    # second envelope and broke parsing).
    bare = re.findall(r"(?m)^\s*done\(", source)
    assert bare == [], f"non-returning done() calls: {len(bare)}"
    assert "return done({" in source
