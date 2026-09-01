/**
 * Long-running buyer listener for ACP v2.
 * Auto-funds when the seller sets a budget.
 * Drop in BUYER_WALLET_ADDRESS / BUYER_WALLET_ID / BUYER_SIGNER_PRIVATE_KEY
 * then run: node buyer.mjs
 */
import { createAgent, fail, loadSdk, requiredEnv } from "./lib.mjs";

async function main() {
  requiredEnv("BUYER_WALLET_ADDRESS");
  requiredEnv("BUYER_WALLET_ID");
  requiredEnv("BUYER_SIGNER_PRIVATE_KEY");
  const mod = await loadSdk();
  const { agent } = await createAgent(mod, "buyer");

  agent.on("entry", async (session, entry) => {
    if (entry?.kind !== "system") return;
    const type = entry.event?.type;
    try {
      if (type === "budget.set") {
        await session.fund();
      }
    } catch (err) {
      console.error("buyer handler failed", String(err?.message || err));
    }
  });

  await agent.start();
  console.error("PRIOR buyer listening (ACP v2). Credentials are not printed.");
}

main().catch((err) => fail(String(err?.stack || err)));
