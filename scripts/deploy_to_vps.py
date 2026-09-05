import subprocess
import os
import sys
import tempfile
from pathlib import Path
from dotenv import dotenv_values

SSH_KEY = r"C:\Users\HomePC\.ssh\villa-vps-deploy_ed25519"
VPS_HOST = "root@103.195.188.198"

def run_remote(cmd, input_data=None):
    ssh_cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        VPS_HOST,
        cmd
    ]
    res = subprocess.run(
        ssh_cmd,
        input=input_data,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True
    )
    if res.returncode != 0:
        print(f"Remote command failed: {cmd}\nStderr: {res.stderr}")
        sys.exit(1)
    return res.stdout

def run_scp(src, dst):
    scp_cmd = [
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        src,
        f"{VPS_HOST}:{dst}"
    ]
    res = subprocess.run(
        scp_cmd,
        text=True,
        capture_output=True
    )
    if res.returncode != 0:
        print(f"SCP failed from {src} to {dst}\nStderr: {res.stderr}")
        sys.exit(1)

def get_head_sha():
    res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return res.stdout.strip()

def main():
    head_sha = get_head_sha()
    print(f"Deploying HEAD SHA: {head_sha}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = Path(tmpdir) / "prior-deploy.tar.gz"
        print(f"Creating git archive at {tar_path}...")
        subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(tar_path), "HEAD"], check=True)

        print("Uploading archive to VPS /tmp/prior-deploy.tar.gz...")
        run_scp(str(tar_path), "/tmp/prior-deploy.tar.gz")

    print("Extracting archive on VPS...")
    run_remote("""
        tar -xzf /tmp/prior-deploy.tar.gz -C /opt/prior
        chown -R prior:prior /opt/prior
        rm -f /tmp/prior-deploy.tar.gz
    """)

    print("Installing python package on VPS...")
    run_remote("""
        /opt/prior/.venv/bin/pip install -e /opt/prior
    """)

    print("Installing acp-bridge npm packages on VPS...")
    run_remote("""
        cd /opt/prior/acp-bridge && npm install
    """)

    print("Syncing /etc/prior/prior.env securely...")
    local_env = dotenv_values(".env") if Path(".env").exists() else {}
    
    server_env = {
        "PRIOR_DATA_DIR": "/opt/prior/data",
        "PRIOR_MEMORY_DB": "/opt/prior/data/prior.db",
        "PRIOR_HOST": "127.0.0.1",
        "PRIOR_PORT": "8789",
        "PRIOR_BUILD_COMMIT": head_sha,
        "PRIOR_LOCAL_PROVIDER": "local",
        "ACP_ENABLED": "true",
        "BASE_RPC_URL": local_env.get("BASE_RPC_URL", "https://mainnet.base.org"),
        "BASE_CHAIN_ID": local_env.get("BASE_CHAIN_ID", "8453"),
        "ACP_BRIDGE_DIR": "/opt/prior/acp-bridge",
    }
    
    for k in ["BUYER_WALLET_ADDRESS", "BUYER_WALLET_ID", "BUYER_SIGNER_PRIVATE_KEY",
              "SELLER_WALLET_ADDRESS", "SELLER_WALLET_ID", "SELLER_SIGNER_PRIVATE_KEY",
              "VIRTUALS_ENV"]:
        if k in local_env and local_env[k]:
            server_env[k] = local_env[k]

    env_lines = []
    for k, v in server_env.items():
        env_lines.append(f"{k}={v}")
    env_content = "\n".join(env_lines) + "\n"

    run_remote("cat > /etc/prior/prior.env && chmod 600 /etc/prior/prior.env", input_data=env_content)
    print("Updated /etc/prior/prior.env successfully (secrets not logged).")

    print("Restarting prior.service and prior-acp-seller.service...")
    out = run_remote("""
        systemctl restart prior.service
        systemctl restart prior-acp-seller.service
        sleep 2
        systemctl status prior.service --no-pager
        systemctl status prior-acp-seller.service --no-pager
    """)
    print(out.encode("ascii", errors="replace").decode("ascii"))

    print("Checking local curl on VPS...")
    health = run_remote("curl -s http://127.0.0.1:8789/healthz")
    print(f"VPS /healthz: {health.strip()}")
    api_health = run_remote("curl -s http://127.0.0.1:8789/api/health")
    print(f"VPS /api/health: {api_health.strip()}")

if __name__ == "__main__":
    main()

