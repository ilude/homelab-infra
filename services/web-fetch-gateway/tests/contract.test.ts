import { afterEach, describe, expect, it } from "vitest";
import type { Server } from "node:http";
import { authorized, parseInput, type Result } from "../src/contract.js";
import { createGateway } from "../src/server.js";
import { Capacity } from "../src/capacity.js";
const token = "t".repeat(40);
const servers: Server[] = [];
afterEach(async () => { await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => { server.closeAllConnections(); server.close(() => resolve()); }))); });
async function endpoint(retrieve: Parameters<typeof createGateway>[0]["retrieve"], capacity?: Capacity) {
  const server = createGateway({ token, retrieve, capacity }); servers.push(server);
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  return `http://127.0.0.1:${port}`;
}
const success: Result = { ok: true, request_id: "fixture", requested_url: "https://example.com/", final_url: "https://example.com/", fetched_at: new Date().toISOString(), elapsed_ms: 1, attempts: [], backend: "direct", title: null, content: "hi", format: "text", quality: "useful", truncated: false, warnings: [] };
describe("contract", () => {
  it("normalizes defaults and authenticates without accepting prefixes", () => {
    expect(parseInput({ url: "https://example.com" })).toEqual({ url: "https://example.com/", max_chars: 8000, backend: "auto" });
    expect(authorized(`Bearer ${token}`, token)).toBe(true);
    expect(authorized(`Bearer ${token}x`, token)).toBe(false);
    expect(authorized(undefined, token)).toBe(false);
  });
  it.each([null, [], { url: "file:///etc/passwd" }, { url: "https://u:p@example.com" }, { url: "https://example.com", max_chars: 0 }, { url: "https://example.com", max_chars: 1.5 }, { url: "https://example.com", max_chars: 50001 }, { url: "https://example.com", backend: "simple_cloudflare" }, { url: "https://example.com", headers: {} }])("rejects invalid inputs %j", value => {
    expect(() => parseInput(value)).toThrow();
  });
  it("rejects disabled explicit backends", () => {
    expect(() => parseInput({ url: "https://example.com", backend: "trawl" }, ["direct"])).toThrow(/disabled/);
  });
  it("serves health, enforces auth, validates JSON, and returns the content contract", async () => {
    const url = await endpoint(async () => success);
    expect((await fetch(`${url}/healthz`)).status).toBe(200);
    expect((await fetch(`${url}/v1/fetch`, { method: "POST", body: "{}" })).status).toBe(401);
    expect((await fetch(`${url}/v1/fetch`, { method: "POST", headers: { authorization: `Bearer ${token}` }, body: "{" })).status).toBe(400);
    const response = await fetch(`${url}/v1/fetch`, { method: "POST", headers: { authorization: `Bearer ${token}` }, body: JSON.stringify({ url: "https://example.com" }) });
    expect(response.status).toBe(200); expect(await response.json()).toEqual(success);
  });
  it("rejects overload without entering retrieval", async () => {
    const capacity = new Capacity(1); const release = capacity.acquire();
    const url = await endpoint(async () => { throw new Error("must not run"); }, capacity);
    const response = await fetch(`${url}/v1/fetch`, { method: "POST", headers: { authorization: `Bearer ${token}` }, body: "{}" });
    expect(response.status).toBe(503); release(); expect(capacity.used).toBe(0);
  });
});
