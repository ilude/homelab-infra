import { expect, it } from "vitest";
import { boundContent, extract, MAX_BYTES } from "../src/extract.js";
const html = (body: string, status = 200) => ({ body, status, url: "https://example.com/guide/", contentType: "text/html" });
it("preserves useful short HTML and resolves links", () => {
  const result = extract(html('<title>Short</title><main><p>Hello <a href="../next">next</a>.</p></main>'));
  expect(result.quality).toBe("useful"); expect(result.content).toContain("https://example.com/next");
});
it.each(["text/plain", "text/markdown", "application/json", "application/xml", "text/csv"])("preserves short %s", contentType => {
  expect(extract({ ...html("{}"), contentType }).content).toBe("{}");
});
it("rejects challenge structures, not discussion of challenges", () => {
  expect(() => extract(html(`<title>Just a moment...</title><form id="challenge-form">${"Verification instructions ".repeat(200)}</form>`))).toThrow(/challenge/);
  expect(extract(html("<title>CAPTCHA design</title><article>How CAPTCHA works and why it can block scraping.</article>")).quality).toBe("useful");
});
it("recognizes an empty JS root without rejecting short genuine pages", () => {
  expect(() => extract(html('<div id="root"></div><script src="/app.js"></script>'))).toThrow(/js_shell/);
  expect(() => extract(html('<main>Loading...</main><script src="/app.js"></script>'))).toThrow(/js_shell/);
});
it("labels explicitly partial content", () => {
  expect(extract(html('<article data-content-partial="true">Preview text</article>')).quality).toBe("partial");
});
it("bounds bytes before DOM parsing and characters after quality classification", () => {
  expect(() => extract(html("x".repeat(MAX_BYTES + 1)))).toThrow(/2 MiB/);
  expect(boundContent("hello", 3)).toEqual({ content: "hel", truncated: true });
});
it.each([[404, "not_found"], [429, "rate_limited"], [403, "access_limited"]])("classifies target status %i", (status, code) => {
  try { extract(html("<article>Error</article>", Number(status))); throw new Error("expected rejection"); }
  catch (error) { expect(error).toMatchObject({ code }); }
});
