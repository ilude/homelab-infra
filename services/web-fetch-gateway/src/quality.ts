import type { Failure } from "./contract.js";

// Structure and title evidence, not isolated words in an article about CAPTCHAs.
export function pageFailure(document: Document, status: number): Failure | null {
  if (status === 404 || status === 410) return "not_found";
  if (status === 429) return "rate_limited";
  const title = document.title.trim();
  const challengeTitle = /^(just a moment|attention required|security verification|verify (?:you are|you're) human|access denied)[.!…\s|:-]*(?:cloudflare)?$/i.test(title);
  const challengeElement = document.querySelector(
    '#challenge-running, #challenge-stage, #cf-challenge-running, form#challenge-form, script[src*="/cdn-cgi/challenge-platform/"]',
  );
  if (challengeTitle || (challengeElement && !document.querySelector("article"))) return "challenge";
  if (status === 401 || status === 403) return "access_limited";
  if (status >= 400) return "extraction_failed";
  const main = document.querySelector("main, article, [role=main], #root, #app, #__next");
  if (document.querySelector("script") && main &&
      (!main.textContent?.trim() || /^(loading|please wait)[.!…\s]*$/i.test(main.textContent.trim()))) return "js_shell";
  const noScript = document.querySelector("noscript")?.textContent ?? "";
  if (/enable javascript|requires javascript/i.test(noScript) && !main?.textContent?.trim()) return "js_shell";
  return null;
}
