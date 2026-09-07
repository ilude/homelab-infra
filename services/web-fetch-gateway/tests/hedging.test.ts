import { expect, it } from "vitest";
import { BrowserCapacity, Capacity } from "../src/capacity.js";
import { createRetriever } from "../src/retrieve.js";
it("caps accepted requests and makes release idempotent", () => {
  const capacity = new Capacity(8); const releases = Array.from({ length: 8 }, () => capacity.acquire());
  expect(() => capacity.acquire()).toThrow(/capacity/);
  for (const release of releases) { release(); release(); }
  expect(capacity.used).toBe(0);
});
it("retains browser capacity until explicit release and quarantines uncertain cleanup", () => {
  const capacity = new BrowserCapacity(); const release = capacity.acquire();
  expect(() => capacity.acquire()).toThrow(/capacity/);
  capacity.quarantined = true; release();
  expect(() => capacity.acquire()).toThrow(/quarantined/);
});
it("deploys sequential mode: a slow direct success does not launch a competing browser", async () => {
  let browsers = 0;
  const raw = { body: "hello", url: "https://example.com/", contentType: "text/plain", status: 200 };
  const retrieve = createRetriever({ revisions: { direct: "1", trawl: "1", jina: "1" }, validate: async () => {}, adapters: {
    direct: async () => { await new Promise(resolve => setTimeout(resolve, 20)); return raw; },
    trawl: async () => { browsers++; return raw; },
  } });
  expect(await retrieve({ url: raw.url, max_chars: 8000, backend: "auto" }, new AbortController().signal)).toMatchObject({ ok: true, backend: "direct" });
  expect(browsers).toBe(0);
});
