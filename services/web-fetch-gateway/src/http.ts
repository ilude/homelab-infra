import http from "node:http";
import https from "node:https";
import { createBrotliDecompress, createGunzip, createInflate } from "node:zlib";
import { Transform } from "node:stream";
import { publicDestination } from "./destinations.js";
import { FetchError, parseUrl } from "./contract.js";
import { MAX_BYTES, type RawContent } from "./extract.js";

export type HttpOptions = {
  signal: AbortSignal; publicOnly?: boolean; method?: string; body?: string;
  maxBytes?: number; headers?: Record<string, string>;
};
function limiter(max: number): Transform {
  let bytes = 0;
  return new Transform({ transform(chunk: Buffer, _encoding, callback) {
    bytes += chunk.length;
    callback(bytes > max ? new FetchError("unsupported_content", "Response exceeds byte limit") : null, chunk);
  } });
}
export async function readHttp(value: string, options: HttpOptions): Promise<RawContent> {
  const url = parseUrl(value);
  const destination = options.publicOnly === false ? null : await publicDestination(url.href);
  options.signal.throwIfAborted();
  const address = destination?.addresses[0];
  const maxBytes = options.maxBytes ?? MAX_BYTES;
  return new Promise((resolve, reject) => {
    const req = (url.protocol === "https:" ? https : http).request(url, {
      method: options.method ?? "GET", signal: options.signal,
      ...(address ? { family: address.family, lookup: (_host, _opts, callback) => callback(null, address.address, address.family) } : {}),
      headers: { "user-agent": "Mozilla/5.0 web-fetch-gateway/0.1", "accept-encoding": "identity", ...options.headers },
    }, response => {
      void (async () => {
        try {
          if (Number(response.headers["content-length"]) > maxBytes)
            throw new FetchError("unsupported_content", "Response exceeds byte limit");
          const bounded = limiter(maxBytes);
          response.on("error", error => bounded.destroy(error));
          let stream = response.pipe(bounded);
          const encoding = response.headers["content-encoding"];
          const decoder = encoding === "gzip" ? createGunzip() : encoding === "br" ? createBrotliDecompress() : encoding === "deflate" ? createInflate() : null;
          if (decoder) {
            bounded.on("error", error => decoder.destroy(error));
            stream = bounded.pipe(decoder);
          }
          const chunks: Buffer[] = []; let length = 0;
          for await (const chunk of stream) {
            const buffer = Buffer.from(chunk); length += buffer.length;
            if (length > maxBytes) throw new FetchError("unsupported_content", "Decoded response exceeds byte limit");
            chunks.push(buffer);
          }
          resolve({ body: Buffer.concat(chunks).toString("utf8"), url: url.href,
            status: response.statusCode ?? 502, contentType: response.headers["content-type"] ?? "",
            retryAfter: response.headers["retry-after"],
            ...((response.headers.location) ? { location: response.headers.location } : {}),
          });
        } catch (error) { response.destroy(); reject(error); }
      })();
    });
    req.on("error", reject);
    req.end(options.body);
  });
}
