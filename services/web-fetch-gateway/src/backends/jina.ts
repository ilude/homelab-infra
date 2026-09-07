import { publicDestination } from "../destinations.js";
import { direct } from "./direct.js";
import { FetchError } from "../contract.js";
import type { RawContent } from "../extract.js";

export async function jina(url: string, signal: AbortSignal): Promise<RawContent> {
  await publicDestination(url);
  const raw = await direct(`https://r.jina.ai/${url}`, signal);
  if (raw.status >= 400) return { ...raw, url };
  // Reader's plain-text envelope may report target errors under API HTTP 200.
  const targetStatus = raw.body.match(/^Warning: Target URL returned error (\d{3})/m);
  if (targetStatus) throw new FetchError(Number(targetStatus[1]) === 404 ? "not_found" : "access_limited", "Jina reported a target error");
  const source = raw.body.match(/^URL Source:\s*(\S+)/m)?.[1] ?? url;
  await publicDestination(source);
  if (/^Title:\s*(Just a moment|Attention Required|Security Verification)/im.test(raw.body))
    throw new FetchError("challenge", "Jina returned a challenge page");
  return { ...raw, url: source, contentType: "text/markdown" };
}
