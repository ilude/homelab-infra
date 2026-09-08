import http from "node:http";
import { gzipSync } from "node:zlib";
import { afterEach, expect, it, vi } from "vitest";
import { readHttp } from "../src/http.js";
import * as transport from "../src/http.js";
import { direct } from "../src/backends/direct.js";
import { trawlBackend } from "../src/backends/trawl.js";
const servers: http.Server[] = [];
afterEach(async () => { vi.restoreAllMocks(); await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => { server.closeAllConnections(); server.close(() => resolve()); }))); });
async function fixture(handler: http.RequestListener) {
  const server = http.createServer(handler); servers.push(server);
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${(server.address() as { port: number }).port}`;
}
it("reads bounded decoded bytes and rejects private targets in public mode", async () => {
  const url = await fixture((_req, res) => { res.setHeader("content-encoding", "gzip"); res.end(gzipSync("hello")); });
  expect((await readHttp(url, { publicOnly: false, signal: AbortSignal.timeout(1000) })).body).toBe("hello");
  await expect(readHttp(url, { signal: AbortSignal.timeout(1000) })).rejects.toMatchObject({ code: "restricted_destination" });
  await expect(readHttp(url, { publicOnly: false, signal: AbortSignal.timeout(1000), maxBytes: 3 })).rejects.toMatchObject({ code: "unsupported_content" });
});
it("bounds decoded compressed bodies", async () => {
  const url = await fixture((_req, res) => { res.setHeader("content-encoding", "gzip"); res.end(gzipSync("x".repeat(1000))); });
  await expect(readHttp(url, { publicOnly: false, signal: AbortSignal.timeout(1000), maxBytes: 100 })).rejects.toMatchObject({ code: "unsupported_content" });
});
it("checks a redirected destination and limits redirect chains", async () => {
  const original = transport.readHttp;
  const spy = vi.spyOn(transport, "readHttp").mockResolvedValueOnce({ body: "", url: "https://example.com/", status: 302, contentType: "text/html", location: "http://127.0.0.1/" } as Awaited<ReturnType<typeof readHttp>>);
  spy.mockImplementation(original);
  await expect(direct("https://example.com/", AbortSignal.timeout(1000))).rejects.toMatchObject({ code: "restricted_destination" });
  spy.mockImplementation(async url => ({ body: "", url, status: 302, contentType: "text/html", location: "/again" }));
  await expect(direct("https://example.com/", AbortSignal.timeout(1000))).rejects.toThrow(/Redirect limit/);
});
it("aborts pending HTTP responses", async () => {
  const url = await fixture(() => {});
  await expect(readHttp(url, { publicOnly: false, signal: AbortSignal.timeout(20) })).rejects.toMatchObject({ name: "AbortError" });
});
it("maps only allowed Trawl fields and verifies its browser slot is idle", async () => {
  let received: Record<string, unknown> = {};
  const url = await fixture((req, res) => {
    res.setHeader("content-type", "application/json");
    if (req.url === "/stats") { res.end(JSON.stringify({ busy: 0, available: 1, queueDepth: 0 })); return; }
    let body = ""; req.on("data", chunk => { body += chunk; }); req.on("end", () => {
      received = JSON.parse(body);
      res.end(JSON.stringify({ html: "<article>hello</article>", url: "https://8.8.8.8/", statusCode: 200, tier: 3, cookies: ["secret"], timings: [{ html: "secret" }] })); // public-safety: allow-ip -- synthetic public target returned by local fixture
    });
  });
  const backend = trawlBackend(url);
  const result = await backend.fetch("https://8.8.8.8/", AbortSignal.timeout(1000), 500); // public-safety: allow-ip -- local backend fixture; no target request
  expect(received).toEqual({ url: "https://8.8.8.8/", skipHttp: true, maxTier: 3, maxTimeout: 500 }); // public-safety: allow-ip -- fixture assertion
  expect(result).toEqual({ body: "<article>hello</article>", url: "https://8.8.8.8/", status: 200, contentType: "text/html", tier: 3 }); // public-safety: allow-ip -- fixture assertion
  await backend.settled(); expect(backend.capacity.used).toBe(0); expect(backend.capacity.quarantined).toBe(false);
});
