import { expect, it } from "vitest";
import { createRetriever, type Adapter } from "../src/retrieve.js";
import type { Backend } from "../src/contract.js";
import { Routes } from "../src/routes.js";
const revisions = { direct: "1", trawl: "1", jina: "1" };
const input = { url: "https://example.com/", backend: "auto" as const, max_chars: 8000 };
const useful = { body: "useful", url: input.url, status: 200, contentType: "text/plain" };
function setup(adapters: Partial<Record<Backend, Adapter>>, rest = {}) {
  return createRetriever({ adapters, revisions, validate: async () => {}, ...rest });
}
it("uses direct content without browser work", async () => {
  let browsers = 0;
  const result = await setup({ direct: async () => useful, trawl: async () => { browsers++; return useful; } })(input, new AbortController().signal);
  expect(result.ok).toBe(true); expect(result.attempts).toHaveLength(1); expect(browsers).toBe(0);
});
it("escalates challenges and reports only the useful browser content", async () => {
  const result = await setup({ direct: async () => ({ ...useful, contentType: "text/html", body: '<title>Just a moment...</title><form id="challenge-form">Wait</form>' }), trawl: async () => ({ ...useful, tier: 3 }) })(input, new AbortController().signal);
  expect(result).toMatchObject({ ok: true, backend: "trawl", content: "useful" });
  expect(result.attempts.map(a => a.reason)).toEqual(["challenge", null]);
});
it("keeps explicit backends strict and skips browsers after 404 while preserving Jina", async () => {
  let browsers = 0, jinaCalls = 0;
  const retrieve = setup({ direct: async () => ({ ...useful, status: 404 }), trawl: async () => { browsers++; return useful; }, jina: async () => { jinaCalls++; return useful; } });
  expect(await retrieve({ ...input, backend: "direct" }, new AbortController().signal)).toMatchObject({ ok: false, error: { code: "not_found" } });
  expect(jinaCalls).toBe(0);
  expect(await retrieve(input, new AbortController().signal)).toMatchObject({ ok: true, backend: "jina" });
  expect(browsers).toBe(0); expect(jinaCalls).toBe(1);
});
it("returns labeled partial content only after alternatives fail", async () => {
  const result = await setup({ direct: async () => ({ ...useful, contentType: "text/html", body: '<article data-content-partial="true">Preview</article>' }), jina: async () => { throw new Error("unavailable"); } })(input, new AbortController().signal);
  expect(result).toMatchObject({ ok: true, quality: "partial", backend: "direct" });
  expect(result.attempts).toHaveLength(2);
});
it("bounds an uncooperative adapter and reserves time for Jina", async () => {
  let jinaCalls = 0;
  const retrieve = setup({ direct: () => new Promise(() => {}), jina: async () => { jinaCalls++; return useful; } }, { deadlineMs: 100, reserveMs: 50, caps: { direct: 20 } });
  expect(await retrieve(input, new AbortController().signal)).toMatchObject({ ok: true, backend: "jina" });
  expect(jinaCalls).toBe(1);
});
it("cancellation never becomes a learned or useful outcome", async () => {
  const controller = new AbortController();
  const retrieve = setup({ direct: async () => { controller.abort(); return useful; } });
  expect(await retrieve(input, controller.signal)).toMatchObject({ ok: false, error: { code: "timeout" } });
});
it("learns against the final origin, not a redirecting source", async () => {
  const routes = new Routes(":memory:", revisions);
  const finalUrl = "https://example.org/article";
  try {
    const retrieve = setup({
      direct: async () => ({ ...useful, url: finalUrl, contentType: "text/html", body: '<title>Just a moment...</title>' }),
      trawl: async () => ({ ...useful, url: finalUrl }),
    }, { routes });
    await retrieve(input, new AbortController().signal); await retrieve(input, new AbortController().signal);
    expect(routes.preferred(input.url)).toBe(null);
    const result = await retrieve({ ...input, url: finalUrl }, new AbortController().signal);
    expect(result.attempts.map(a => a.backend)).toEqual(["trawl"]);
  } finally { routes.close(); }
});
it("honors Retry-After without penalizing another origin", async () => {
  let calls = 0;
  const retrieve = setup({ direct: async url => { calls++; return { ...useful, url, status: 429, retryAfter: "60" }; } });
  await retrieve(input, new AbortController().signal); await retrieve(input, new AbortController().signal);
  expect(calls).toBe(1);
  await retrieve({ ...input, url: "https://example.org/" }, new AbortController().signal);
  expect(calls).toBe(2);
});
