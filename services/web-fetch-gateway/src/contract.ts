import { timingSafeEqual } from "node:crypto";

export const BACKENDS = ["direct", "trawl", "jina"] as const;
export type Backend = typeof BACKENDS[number];
export type Failure = "invalid_request" | "restricted_destination" | "not_found"
  | "rate_limited" | "challenge" | "js_shell" | "access_limited"
  | "unsupported_content" | "timeout" | "backend_unavailable"
  | "extraction_failed" | "overloaded";
export type Attempt = {
  backend: Backend; revision: string; elapsed_ms: number;
  outcome: "useful" | "partial" | "failed" | "cancelled";
  reason: Failure | null; http_status: number | null; tier: number | null;
};
export type Receipt = {
  request_id: string; requested_url: string; final_url: string | null;
  fetched_at: string; elapsed_ms: number; attempts: Attempt[];
};
export type Result = Receipt & (
  | { ok: true; backend: Backend; title: string | null; content: string;
      format: "markdown" | "text"; truncated: boolean;
      quality: "useful" | "partial"; warnings: string[] }
  | { ok: false; error: { code: Failure; message: string } }
);
export type FetchInput = { url: string; max_chars: number; backend: Backend | "auto" };
export class FetchError extends Error {
  constructor(public readonly code: Failure, message: string) { super(message); }
}
export function parseUrl(value: string): URL {
  let url: URL;
  try { url = new URL(value); } catch { throw new FetchError("invalid_request", "Invalid URL"); }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
    throw new FetchError("invalid_request", "Use HTTP(S) without embedded credentials");
  return url;
}
export function parseInput(value: unknown, enabled: readonly Backend[] = BACKENDS): FetchInput {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new FetchError("invalid_request", "Expected a JSON object");
  const fields = value as Record<string, unknown>;
  if (Object.keys(fields).some(k => !["url", "max_chars", "backend"].includes(k)))
    throw new FetchError("invalid_request", "Unknown request field");
  if (typeof fields.url !== "string" || fields.url.length > 8192)
    throw new FetchError("invalid_request", "A bounded URL is required");
  const url = parseUrl(fields.url).href;
  const max_chars = fields.max_chars ?? 8000;
  const backend = fields.backend ?? "auto";
  if (!Number.isInteger(max_chars) || Number(max_chars) < 1 || Number(max_chars) > 50000)
    throw new FetchError("invalid_request", "max_chars must be an integer from 1 to 50000");
  if (backend !== "auto" && !enabled.includes(backend as Backend))
    throw new FetchError("invalid_request", "Unknown or disabled backend");
  return { url, max_chars: Number(max_chars), backend: backend as FetchInput["backend"] };
}
export function authorized(header: string | undefined, token: string): boolean {
  if (!token || !header?.startsWith("Bearer ")) return false;
  const actual = Buffer.from(header.slice(7)); const expected = Buffer.from(token);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
export function statusFor(result: Result): number {
  if (result.ok) return 200;
  if (result.error.code === "invalid_request") return 400;
  if (["overloaded", "backend_unavailable"].includes(result.error.code)) return 503;
  if (result.error.code === "timeout") return 504;
  return 422;
}
export function failure(error: unknown): FetchError {
  if (error instanceof FetchError) return error;
  if (error instanceof Error && ["AbortError", "TimeoutError"].includes(error.name))
    return new FetchError("timeout", "Acquisition cancelled or timed out");
  // Do not expose backend addresses, credentials, or raw third-party errors.
  return new FetchError("backend_unavailable", "Backend transport unavailable");
}
