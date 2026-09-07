import { setTimeout as delay } from "node:timers/promises";
import { BrowserCapacity } from "../capacity.js";
import { FetchError } from "../contract.js";
import { publicDestination } from "../destinations.js";
import { MAX_BYTES, type RawContent } from "../extract.js";
import { readHttp } from "../http.js";

export function trawlBackend(base: string, capacity = new BrowserCapacity()) {
  let cleanup: Promise<void> | undefined;
  async function verifyIdle(): Promise<void> {
    const signal = AbortSignal.timeout(30000);
    try {
      while (!signal.aborted) {
        const reply = await readHttp(new URL("/stats", base).href, { publicOnly: false, signal, maxBytes: 8192 });
        const stats = JSON.parse(reply.body) as { busy?: number; available?: number; queueDepth?: number };
        if (reply.status === 200 && stats.busy === 0 && Number(stats.available) >= 1 && stats.queueDepth === 0) return;
        await delay(250, undefined, { signal });
      }
    } catch { /* A closed client connection never establishes browser termination. */ }
    capacity.quarantined = true;
  }
  return {
    capacity,
    async settled() { await cleanup; },
    async fetch(url: string, signal: AbortSignal, budgetMs: number): Promise<RawContent> {
      await publicDestination(url);
      const release = capacity.acquire();
      try {
        const reply = await readHttp(new URL("/scrape", base).href, {
          publicOnly: false, signal, method: "POST", maxBytes: 16 * MAX_BYTES,
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ url, skipHttp: true, maxTier: 3, maxTimeout: Math.max(1, Math.floor(budgetMs)) }),
        });
        const data = JSON.parse(reply.body) as Record<string, unknown>;
        if (reply.status === 429) throw new FetchError("overloaded", "Browser pool saturated");
        if (reply.status === 500 && Array.isArray(data.timings)) throw new FetchError("extraction_failed", "Browser could not acquire this page");
        if (reply.status !== 200) throw new FetchError("backend_unavailable", "Browser API failed");
        if (data.success === false || data.error) throw new FetchError("extraction_failed", "Browser acquisition failed");
        const finalUrl = typeof data.url === "string" ? data.url : url;
        await publicDestination(finalUrl);
        if (typeof data.html !== "string") throw new FetchError("unsupported_content", "Browser returned no HTML");
        if (Buffer.byteLength(data.html) > MAX_BYTES) throw new FetchError("unsupported_content", "Browser HTML exceeds byte limit");
        // Do not forward timings, cookies, headers, or raw body buffers from Trawl.
        return { body: data.html, url: finalUrl,
          status: typeof data.statusCode === "number" ? data.statusCode : 200,
          contentType: "text/html", tier: typeof data.tier === "number" ? data.tier : 3 };
      } finally {
        cleanup = verifyIdle().finally(release);
        // Return content/cancellation promptly while retaining the browser lease.
        void cleanup.catch(() => { capacity.quarantined = true; });
      }
    },
  };
}
