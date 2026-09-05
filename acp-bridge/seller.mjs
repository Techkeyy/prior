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
  const { AssetToken, ACP_SELECTORS } = mod;
  const { agent, chain } = await createAgent(mod, "seller");
  const price = 0;

  async function processSession(session) {
    try {
      await session.fetchJob().catch(() => {});
      const onChainStatus = (session.job?.status || "").toUpperCase();
      const hasBudgetEvent = (session.entries || []).some(
        (e) => e.kind === "system" && e.event?.type === "budget.set"
      );

      if (onChainStatus === "OPEN" && !hasBudgetEvent && !session._budgetSetting) {
        session._budgetSetting = true;
        console.error(`[SELLER] Setting budget for job ${session.jobId}...`);
        const token = AssetToken.usdc(price, chain.id);
        const myAddr = await agent.getAddress();
        const { hasFund } = session.detectConfiguredHooks(ACP_SELECTORS.setBudget);
        if (hasFund) {
          await session.setBudgetWithFundRequest(token, token, myAddr);
        } else {
          await session.setBudget(token);
        }
        console.error(`[SELLER] Budget set for job ${session.jobId}`);
      } else if (onChainStatus === "FUNDED" && !session._submitting) {
        session._submitting = true;
        console.error(`[SELLER] Job ${session.jobId} funded. Running research...`);
        let entries = session.entries || [];
        if (!entries.length || !entries.some((e) => e.kind === "message")) {
          try {
            entries = await agent.getTransport().getHistory(session.chainId, session.jobId);
          } catch {}
        }
        const requirementEntry = [...(entries || [])]
          .reverse()
          .find((item) => item.kind === "message" && (item.contentType === "requirement" || item.contentType === "text"));
        let requirement = {};
        if (requirementEntry?.content) {
          try {
            requirement = JSON.parse(requirementEntry.content);
          } catch {
            requirement = { raw: requirementEntry.content, goal: requirementEntry.content };
          }
        } else if (session.job?.description) {
          requirement = { raw: session.job.description, goal: session.job.description };
        }
        const report = await runResearch(requirement);
        console.error(`[SELLER] Submitting deliverable for job ${session.jobId}...`);
        await session.submit(report);
        try {
          await agent.sendMessage(session.chainId, session.jobId.toString(), report, "deliverable");
        } catch (err) {
          console.error("Deliverable message send:", String(err?.message || err));
        }
        console.error(`[SELLER] Deliverable submitted for job ${session.jobId}`);
      }
    } catch (err) {
      console.error(`[SELLER PROCESS ERROR ${session.jobId}]`, String(err?.stack || err?.message || err));
    }
  }

  agent.on("entry", async (session) => {
    await processSession(session);
  });

  await agent.start();
  console.error("PRIOR seller listening (ACP v2). Credentials are not printed.");

  setInterval(async () => {
    for (const s of agent.sessions || []) {
      await processSession(s);
    }
  }, 4000);
}

main().catch((err) => fail(String(err?.stack || err)));
