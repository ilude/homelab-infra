import { DatabaseSync } from "node:sqlite";
import type { Attempt, Backend } from "./contract.js";

const DAY = 86400000;
type Row = {
  origin: string; scope_prefix: string; backend: Backend; revision: string;
  window_started_at: number; useful_count: number; challenge_count: number;
  shell_count: number; latency_ewma_ms: number | null; last_success_at: number | null;
  last_failure: string | null; expires_at: number;
};
export class Routes {
  private db?: DatabaseSync;
  private probes = new Map<string, number>();
  warning: string | undefined;
  constructor(path: string, private revisions: Record<Backend, string>,
    private scopes: Record<string, string[]> = {}, private now = Date.now) {
    try {
      this.db = new DatabaseSync(path);
      this.db.exec("PRAGMA busy_timeout=250; PRAGMA journal_mode=WAL;");
      const version = this.db.prepare("PRAGMA user_version").get()?.user_version;
      if (version !== 0 && version !== 1) throw new Error("Unsupported route schema");
      this.db.exec(`CREATE TABLE IF NOT EXISTS route_stats (
        origin TEXT NOT NULL, scope_prefix TEXT NOT NULL, backend TEXT NOT NULL,
        revision TEXT NOT NULL, window_started_at INTEGER NOT NULL,
        useful_count INTEGER NOT NULL DEFAULT 0, challenge_count INTEGER NOT NULL DEFAULT 0,
        shell_count INTEGER NOT NULL DEFAULT 0, latency_ewma_ms REAL,
        last_success_at INTEGER, last_failure TEXT, expires_at INTEGER NOT NULL,
        PRIMARY KEY(origin, scope_prefix, backend, revision)); PRAGMA user_version=1;`);
      this.db.prepare("DELETE FROM route_stats WHERE expires_at < ?").run(this.now() - 7 * DAY);
    } catch { this.warning = "Route database unavailable; stateless routing"; this.db?.close(); this.db = undefined; }
  }
  private scope(value: string): [string, string] {
    const url = new URL(value);
    const prefixes = (this.scopes[url.origin] ?? []).filter(prefix =>
      prefix.startsWith("/") && !/[?#]/.test(prefix) &&
      (url.pathname === prefix || url.pathname.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`)));
    return [url.origin, prefixes.sort((a, b) => b.length - a.length)[0] ?? "/"];
  }
  private safe<T>(fallback: T, operation: (db: DatabaseSync) => T): T {
    if (!this.db) return fallback;
    try { const result = operation(this.db); this.warning = undefined; return result; }
    catch { this.warning = "Route database unavailable; stateless routing"; return fallback; }
  }
  preferred(value: string): Backend | null {
    return this.safe(null, db => {
      const [origin, scope] = this.scope(value); const now = this.now();
      const rows = db.prepare("SELECT * FROM route_stats WHERE origin=? AND scope_prefix=? AND expires_at>? AND window_started_at>?")
        .all(origin, scope, now, now - DAY) as unknown as Row[];
      const current = rows.filter(row => row.revision === this.revisions[row.backend]);
      const direct = current.find(row => row.backend === "direct");
      if (!direct || direct.challenge_count + direct.shell_count < 2) return null;
      const winner = current.filter(row => row.backend === "trawl" && row.useful_count >= 2)
        .sort((a, b) => (a.latency_ewma_ms ?? Infinity) - (b.latency_ewma_ms ?? Infinity))[0];
      if (!winner) return null;
      const key = `${origin}|${scope}`;
      const count = (this.probes.get(key) ?? 0) + 1;
      this.probes.set(key, count);
      return count % 10 === 0 ? null : winner.backend;
    });
  }
  observe(finalUrl: string, attempt: Attempt): void {
    if (attempt.outcome === "cancelled" || attempt.outcome === "partial") return;
    if (attempt.outcome !== "useful" && !["challenge", "js_shell"].includes(attempt.reason ?? "")) return;
    this.safe(undefined, db => {
      const [origin, scope] = this.scope(finalUrl); const now = this.now();
      db.exec("BEGIN IMMEDIATE");
      try {
        let row = db.prepare("SELECT * FROM route_stats WHERE origin=? AND scope_prefix=? AND backend=? AND revision=?")
          .get(origin, scope, attempt.backend, attempt.revision) as unknown as Row | undefined;
        if (!row || row.window_started_at <= now - DAY) row = {
          origin, scope_prefix: scope, backend: attempt.backend, revision: attempt.revision,
          window_started_at: now, useful_count: 0, challenge_count: 0, shell_count: 0,
          latency_ewma_ms: null, last_success_at: null, last_failure: null, expires_at: now + DAY,
        };
        if (attempt.outcome === "useful") {
          row.useful_count++; row.last_success_at = now;
          row.latency_ewma_ms = row.latency_ewma_ms === null ? attempt.elapsed_ms : .2 * attempt.elapsed_ms + .8 * row.latency_ewma_ms;
          if (attempt.backend === "direct") { row.challenge_count = 0; row.shell_count = 0; }
        } else {
          if (attempt.reason === "challenge") row.challenge_count++;
          if (attempt.reason === "js_shell") row.shell_count++;
          row.last_failure = attempt.reason;
        }
        row.expires_at = now + DAY;
        db.prepare(`INSERT OR REPLACE INTO route_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?)`).run(
          row.origin, row.scope_prefix, row.backend, row.revision, row.window_started_at,
          row.useful_count, row.challenge_count, row.shell_count, row.latency_ewma_ms,
          row.last_success_at, row.last_failure, row.expires_at);
        db.exec("COMMIT");
      } catch (error) { db.exec("ROLLBACK"); throw error; }
    });
  }
  close(): void { this.db?.close(); this.db = undefined; }
}
