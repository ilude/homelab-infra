import { Readability } from "@mozilla/readability";
import { JSDOM } from "jsdom";
import TurndownService from "turndown";
import { gfm } from "turndown-plugin-gfm";
import { FetchError } from "./contract.js";
import { pageFailure } from "./quality.js";

export const MAX_BYTES = 2 * 1024 * 1024;
export type RawContent = {
  body: string; url: string; status: number; contentType: string;
  tier?: number; retryAfter?: string;
};
export type Content = {
  title: string | null; content: string; format: "markdown" | "text";
  quality: "useful" | "partial"; warnings: string[];
};
export function extract(raw: RawContent): Content {
  if (Buffer.byteLength(raw.body) > MAX_BYTES)
    throw new FetchError("unsupported_content", "Content exceeds the 2 MiB limit");
  if (raw.status === 404 || raw.status === 410) throw new FetchError("not_found", "Target not found");
  if (raw.status === 429) throw new FetchError("rate_limited", "Target rate limited");
  const type = raw.contentType.toLowerCase().split(";")[0].trim();
  if (/^(text\/(plain|markdown|csv)|application\/(json|[^;]+\+json|xml)|text\/xml)$/.test(type)) {
    if (raw.status >= 400) throw new FetchError("access_limited", "Target returned an error");
    if (!raw.body.trim()) throw new FetchError("extraction_failed", "Empty response");
    return { title: null, content: raw.body, format: type === "text/markdown" ? "markdown" : "text", quality: "useful", warnings: [] };
  }
  if (type && !["text/html", "application/xhtml+xml"].includes(type))
    throw new FetchError("unsupported_content", "Unsupported target content type");
  const dom = new JSDOM(raw.body, { url: raw.url });
  try {
    const doc = dom.window.document;
    const reason = pageFailure(doc, raw.status);
    if (reason) throw new FetchError(reason, `Page classified as ${reason}`);
    // Resolve relative links before conversion. JSDOM executes no page scripts/resources.
    for (const node of doc.querySelectorAll("a[href], img[src]")) {
      const attr = node.tagName === "A" ? "href" : "src";
      try { node.setAttribute(attr, new URL(node.getAttribute(attr)!, raw.url).href); } catch { node.removeAttribute(attr); }
    }
    const article = new Readability(doc.cloneNode(true) as Document).parse();
    doc.querySelectorAll("script,style,noscript,nav,header,footer,aside").forEach(el => el.remove());
    const main = doc.querySelector("main,article,[role=main],.content,#content") ?? doc.body;
    const converter = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced" });
    converter.use(gfm);
    const content = converter.turndown(article?.content || main?.innerHTML || "").replace(/\n{3,}/g, "\n\n").trim();
    if (!content) throw new FetchError("extraction_failed", "No readable content");
    const partial = !!doc.querySelector('[data-content-truncated="true"], [data-content-partial="true"]');
    return { title: article?.title || doc.title || null, content, format: "markdown",
      quality: partial ? "partial" : "useful", warnings: partial ? ["Page explicitly indicates partial content"] : [] };
  } finally { dom.window.close(); }
}
export function boundContent(content: string, limit: number): { content: string; truncated: boolean } {
  return { content: content.slice(0, limit), truncated: content.length > limit };
}
