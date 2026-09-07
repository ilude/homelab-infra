import http from "node:http";
import { pathToFileURL } from "node:url";
import { randomUUID } from "node:crypto";
import { authorized, failure, parseInput, statusFor, type Backend, type FetchInput, type Result } from "./contract.js";
import { Capacity } from "./capacity.js";
import { createRetriever } from "./retrieve.js";
import { direct } from "./backends/direct.js";
import { jina } from "./backends/jina.js";
import { trawlBackend } from "./backends/trawl.js";
import { Routes } from "./routes.js";

export function createGateway(options: {
  token: string; retrieve: (input: FetchInput, signal: AbortSignal) => Promise<Result>;
  enabled?: Backend[]; capacity?: Capacity;
}) {
  if (options.token.length < 32) throw new Error("Gateway token must have at least 32 characters");
  const capacity = options.capacity ?? new Capacity(8);
  return http.createServer({ headersTimeout: 5000, requestTimeout: 60000, keepAliveTimeout: 5000 }, (req, res) => {
    const send = (status: number, value: unknown) => {
      if (res.destroyed) return;
      res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
      res.end(JSON.stringify(value));
    };
    if (req.method === "GET" && ["/healthz", "/readyz"].includes(req.url ?? "")) { send(200, { ok: true }); return; }
    if (req.method !== "POST" || req.url !== "/v1/fetch") { send(404, { error: "not_found" }); return; }
    if (!authorized(req.headers.authorization, options.token)) { send(401, { error: "unauthorized" }); req.resume(); return; }
    const controller = new AbortController();
    res.on("close", () => { if (!res.writableEnded) controller.abort(); });
    void (async () => {
      let release: (() => void) | undefined;
      try {
        release = capacity.acquire();
        const chunks: Buffer[] = []; let bytes = 0;
        for await (const chunk of req) {
          bytes += chunk.length;
          if (bytes > 16384) { send(400, { error: "Request body too large" }); req.resume(); return; }
          chunks.push(Buffer.from(chunk));
        }
        let decoded: unknown;
        try { decoded = JSON.parse(Buffer.concat(chunks).toString("utf8")); }
        catch { send(400, { error: "Invalid JSON" }); return; }
        const input = parseInput(decoded, options.enabled);
        const result = await options.retrieve(input, controller.signal);
        send(statusFor(result), result);
      } catch (error) {
        const problem = failure(error);
        const result: Result = { ok: false, request_id: randomUUID(), requested_url: "", final_url: null,
          fetched_at: new Date().toISOString(), elapsed_ms: 0, attempts: [],
          error: { code: problem.code, message: problem.message } };
        send(statusFor(result), result);
      } finally { release?.(); }
    })();
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const revision = process.env.GATEWAY_REVISION ?? "development";
  const revisions = { direct: revision, jina: revision, trawl: `${process.env.TRAWL_REVISION ?? "disabled"}/${revision}` };
  const routes = new Routes(process.env.ROUTES_DB ?? "/state/routes.sqlite", revisions);
  const trawl = process.env.TRAWL_URL ? trawlBackend(process.env.TRAWL_URL) : undefined;
  const retrieve = createRetriever({ routes, revisions, adapters: { direct, jina, ...(trawl ? { trawl: trawl.fetch } : {}) } });
  const server = createGateway({ token: process.env.WEB_FETCH_GATEWAY_TOKEN ?? "", retrieve,
    enabled: trawl ? ["direct", "trawl", "jina"] : ["direct", "jina"] });
  server.listen(Number(process.env.PORT ?? 8080), process.env.HOST ?? "0.0.0.0");
  for (const signal of ["SIGTERM", "SIGINT"] as const) process.once(signal, () => {
    server.close(() => { routes.close(); process.exit(0); });
    setTimeout(() => process.exit(1), 5000).unref();
  });
}
