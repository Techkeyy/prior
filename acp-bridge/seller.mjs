/**
 * PRIOR research seller for ACP v2.
 * Drop in SELLER_WALLET_ADDRESS / SELLER_WALLET_ID / SELLER_SIGNER_PRIVATE_KEY
 * then run: node seller.mjs
 *
 * On job.created: setBudget
 * On job.funded: run PRIOR research and session.submit
 */
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { createAgent, fail, loadSdk, requiredEnv } from "./lib.mjs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

function pythonBin() {
  const win = resolve(ROOT, ".venv", "Scripts", "python.exe");
  const nix = resolve(ROOT, ".venv", "bin", "python");
  if (existsSync(win)) return win;
  if (existsSync(nix)) return nix;
  return "python";
}

function runResearch(requirement) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(pythonBin(), ["-m", "prior.research_cli"], {
      cwd: ROOT,
      env: { ...process.env, PYTHONPATH: resolve(ROOT, "src") },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `research_cli exited ${code}`));
        return;
      }
      resolvePromise(stdout);
    });
    child.stdin.write(JSON.stringify(requirement));
    child.stdin.end();
  });
}

async function main() {
  requiredEnv("SELLER_WALLET_ADDRESS");
  requiredEnv("SELLER_WALLET_ID");
  requiredEnv("SELLER_SIGNER_PRIVATE_KEY");
  const mod = await loadSdk();
  const { AssetToken } = mod;
  const { agent, chain } = await createAgent(mod, "seller");
  const price = Number(process.env.ACP_JOB_PRICE_USDC || "0.01");

  agent.on("entry", async (session, entry) => {
    if (entry?.kind !== "system") return;
    const type = entry.event?.type;
    try {
      if (type === "job.created") {
        await session.setBudget(AssetToken.usdc(price, chain.id));
        return;
      }
      if (type === "job.funded") {
        const requirementEntry = [...(session.entries || [])]
          .reverse()
          .find((item) => item.kind === "message" && item.contentType === "requirement");
        let requirement = {};
        try {
          requirement = JSON.parse(requirementEntry?.content || "{}");
        } catch {
          requirement = { raw: requirementEntry?.content || "" };
        }
        const report = await runResearch(requirement);
        await session.submit(report);
      }
    } catch (err) {
      console.error("seller handler failed", String(err?.message || err));
    }
  });

  await agent.start();
  console.error("PRIOR seller listening (ACP v2). Credentials are not printed.");
}

main().catch((err) => fail(String(err?.stack || err)));
