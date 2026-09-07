import { afterEach, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Routes } from "../src/routes.js";
import type { Attempt, Backend } from "../src/contract.js";
const paths: string[] = []; const stores: Routes[] = [];
const revisions = { direct: "v1", trawl: "v1", jina: "v1" };
function open(now = Date.now, scopes = {}) {
  const dir = mkdtempSync(join(tmpdir(), "fetch-routes-")); paths.push(dir);
  const file = join(dir, "routes.sqlite"); const store = new Routes(file, revisions, scopes, now); stores.push(store);
  return { file, store };
}
const attempt = (backend: Backend, outcome: Attempt["outcome"], reason: Attempt["reason"] = null): Attempt => ({ backend, outcome, reason, revision: "v1", elapsed_ms: 20, http_status: 200, tier: backend === "trawl" ? 3 : null });
function train(store: Routes, url: string) {
  for (let i = 0; i < 2; i++) { store.observe(url, attempt("direct", "failed", "js_shell")); store.observe(url, attempt("trawl", "useful")); }
}
afterEach(() => { for (const store of stores.splice(0)) store.close(); for (const path of paths.splice(0)) rmSync(path, { recursive: true, force: true }); });
it("promotes only after two observations, probes every tenth request, and clears on direct recovery", () => {
  const { store } = open(); const url = "https://example.com/path?q=secret";
  store.observe(url, attempt("direct", "failed", "challenge")); store.observe(url, attempt("trawl", "useful"));
  expect(store.preferred(url)).toBe(null);
  store.observe(url, attempt("direct", "failed", "challenge")); store.observe(url, attempt("trawl", "useful"));
  for (let i = 1; i <= 10; i++) expect(store.preferred(url)).toBe(i === 10 ? null : "trawl");
  store.observe(url, attempt("direct", "useful")); expect(store.preferred(url)).toBe(null);
});
it("persists across restart without full URLs, queries, or page content", () => {
  const { file, store } = open(); train(store, "https://example.com/private-path?token=secret"); store.close();
  const reopened = new Routes(file, revisions); stores.push(reopened);
  expect(reopened.preferred("https://example.com/other")).toBe("trawl");
  const db = new DatabaseSync(file);
  const rows = db.prepare("SELECT * FROM route_stats").all(); db.close();
  expect(JSON.stringify(rows)).not.toMatch(/private-path|token|secret/);
});
it("expires preferences and invalidates changed backend revisions", () => {
  let now = Date.now(); const { store, file } = open(() => now); train(store, "https://example.com");
  expect(store.preferred("https://example.com")).toBe("trawl");
  const updated = new Routes(file, { ...revisions, trawl: "v2" }); stores.push(updated);
  expect(updated.preferred("https://example.com")).toBe(null);
  now += 86400001; expect(store.preferred("https://example.com")).toBe(null);
});
it("uses segment scopes and never trains cancelled or partial attempts", () => {
  const { store } = open(Date.now, { "https://example.com": ["/docs"] }); train(store, "https://example.com/docs/page");
  expect(store.preferred("https://example.com/docs/next")).toBe("trawl");
  expect(store.preferred("https://example.com/docs-other")).toBe(null);
  expect(store.preferred("https://other.example.com/docs/page")).toBe(null);
  for (let i = 0; i < 3; i++) { store.observe("https://example.org/", attempt("direct", "failed", "challenge")); store.observe("https://example.org/", attempt("trawl", "partial")); store.observe("https://example.org/", attempt("trawl", "cancelled")); }
  expect(store.preferred("https://example.org/")).toBe(null);
});
it("degrades on an unavailable database or a competing write lock", () => {
  const missing = new Routes(join(tmpdir(), "nonexistent-web-fetch-directory", "routes.sqlite"), revisions); stores.push(missing);
  expect(missing.preferred("https://example.com")).toBe(null); expect(missing.warning).toMatch(/stateless/);
  const { file, store } = open(); const lock = new DatabaseSync(file); lock.exec("BEGIN IMMEDIATE");
  store.observe("https://example.com", attempt("direct", "useful")); expect(store.warning).toMatch(/stateless/);
  lock.exec("ROLLBACK"); lock.close();
  train(store, "https://example.com"); expect(store.preferred("https://example.com")).toBe("trawl");
});
