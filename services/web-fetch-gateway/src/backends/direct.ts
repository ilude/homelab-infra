import { FetchError } from "../contract.js";
import { readHttp } from "../http.js";
import type { RawContent } from "../extract.js";

export async function direct(value: string, signal: AbortSignal): Promise<RawContent> {
  let current = value;
  for (let redirects = 0; redirects <= 5; redirects++) {
    const raw = await readHttp(current, { signal });
    const location = (raw as RawContent & { location?: string }).location;
    if (![301, 302, 303, 307, 308].includes(raw.status) || !location) return raw;
    current = new URL(location, current).href;
  }
  throw new FetchError("extraction_failed", "Redirect limit exceeded");
}
