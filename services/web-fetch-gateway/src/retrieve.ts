import { randomUUID } from "node:crypto";
import { BACKENDS, FetchError, failure, type Attempt, type Backend, type FetchInput, type Receipt, type Result } from "./contract.js";
import { boundContent, extract, type Content, type RawContent } from "./extract.js";
import { publicDestination } from "./destinations.js";
import type { Routes } from "./routes.js";

export type Adapter = (url: string, signal: AbortSignal, budgetMs: number) => Promise<RawContent>;
export type RetrievalOptions = {
  adapters: Partial<Record<Backend, Adapter>>; revisions: Record<Backend, string>; routes?: Routes;
  deadlineMs?: number; reserveMs?: number; caps?: Partial<Record<Backend, number>>;
  validate?: (url: string) => Promise<unknown>;
};
async function abortable<T>(work: Promise<T>, signal: AbortSignal): Promise<T> {
  let cancel: () => void = () => {};
  const aborted = new Promise<never>((_, reject) => {
    cancel = () => reject(signal.reason);
    signal.addEventListener("abort", cancel, { once: true });
  });
  const pending = Promise.race([work, aborted]);
  if (signal.aborted) cancel();
  try { return await pending; }
  finally { signal.removeEventListener("abort", cancel); }
}
export function createRetriever(options: RetrievalOptions) {
  const cooldowns = new Map<string, number>();
  const outages = new Map<Backend, number>();
  return async (input: FetchInput, caller: AbortSignal): Promise<Result> => {
    const start = performance.now(); const deadlineMs = options.deadlineMs ?? 45000;
    const end = start + deadlineMs;
    const signal = AbortSignal.any([caller, AbortSignal.timeout(deadlineMs)]);
    const receipt: Receipt = { request_id: randomUUID(), requested_url: input.url,
      final_url: null, fetched_at: new Date().toISOString(), elapsed_ms: 0, attempts: [] };
    const finish = <T extends object>(fields: T): Receipt & T => ({ ...receipt, elapsed_ms: Math.round(performance.now() - start), ...fields });
    let partial: { raw: RawContent; content: Content; backend: Backend } | undefined;
    let last = new FetchError("extraction_failed", "No usable content");
    let notFound = false;
    try {
      signal.throwIfAborted();
      await abortable((options.validate ?? publicDestination)(input.url), signal);
      const preferred = input.backend === "auto" ? options.routes?.preferred(input.url) : null;
      const order: Backend[] = input.backend === "auto"
        ? [...new Set<Backend>([...(preferred ? [preferred] : []), ...BACKENDS])]
        : [input.backend];
      for (const backend of order) {
        signal.throwIfAborted();
        const adapter = options.adapters[backend];
        if (!adapter) {
          if (input.backend !== "auto") throw new FetchError("invalid_request", "Backend disabled");
          continue;
        }
        if (notFound && backend === "trawl") continue;
        const reserve = input.backend === "auto" && backend !== "jina" ? options.reserveMs ?? 10000 : 0;
        const budget = Math.min(options.caps?.[backend] ?? ({ direct: 10000, trawl: 25000, jina: 8000 })[backend], end - performance.now() - reserve);
        if (budget <= 0) continue;
        const attemptStart = performance.now();
        const attempt: Attempt = { backend, revision: options.revisions[backend], elapsed_ms: 0,
          outcome: "failed", reason: null, http_status: null, tier: null };
        const key = `${backend}|${new URL(input.url).origin}`;
        let raw: RawContent | undefined;
        try {
          if ((outages.get(backend) ?? 0) > Date.now()) throw new FetchError("backend_unavailable", "Backend outage cooldown active");
          if ((cooldowns.get(key) ?? 0) > Date.now()) throw new FetchError("rate_limited", "Backend cooling down for this origin");
          const attemptSignal = AbortSignal.any([signal, AbortSignal.timeout(Math.max(1, Math.floor(budget)))]);
          raw = await abortable(adapter(input.url, attemptSignal, budget), attemptSignal);
          attempt.http_status = raw.status; attempt.tier = raw.tier ?? null;
          receipt.final_url = raw.url;
          if (raw.status === 429) {
            const seconds = Number(raw.retryAfter);
            const until = raw.retryAfter && Number.isFinite(seconds) ? Date.now() + Math.max(0, seconds) * 1000 : Date.parse(raw.retryAfter ?? "");
            cooldowns.set(key, Number.isFinite(until) ? until : Date.now() + 30000);
          }
          const content = extract(raw);
          attemptSignal.throwIfAborted();
          if (performance.now() >= Math.min(end, attemptStart + budget)) throw new FetchError("timeout", "Acquisition deadline exceeded");
          attempt.outcome = content.quality;
          if (content.quality === "useful") {
            attempt.elapsed_ms = Math.round(performance.now() - attemptStart);
            options.routes?.observe(raw.url, attempt);
            receipt.attempts.push(attempt);
            return finish({ ok: true as const, backend, ...content, ...boundContent(content.content, input.max_chars),
              warnings: [...content.warnings, ...(options.routes?.warning ? [options.routes.warning] : [])] });
          }
          partial ??= { raw, content, backend };
        } catch (error) {
          last = failure(error); attempt.reason = last.code;
          if (backend !== "direct" && !signal.aborted && ["backend_unavailable", "overloaded"].includes(last.code)
              && (outages.get(backend) ?? 0) <= Date.now()) outages.set(backend, Date.now() + 30000);
          if (caller.aborted) attempt.outcome = "cancelled";
          if (last.code === "not_found") notFound = true;
        }
        attempt.elapsed_ms = Math.round(performance.now() - attemptStart);
        receipt.attempts.push(attempt);
        if (raw && !signal.aborted) options.routes?.observe(raw.url, attempt);
      }
      signal.throwIfAborted();
      if (partial) {
        receipt.final_url = partial.raw.url;
        return finish({ ok: true as const, backend: partial.backend, ...partial.content,
          ...boundContent(partial.content.content, input.max_chars),
          warnings: [...partial.content.warnings, ...(options.routes?.warning ? [options.routes.warning] : [])] });
      }
    } catch (error) { last = failure(error); }
    return finish({ ok: false as const, error: { code: last.code, message: last.message } });
  };
}
