import { expect, it } from "vitest";
import { publicAddress, publicDestination } from "../src/destinations.js";
it.each(["127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1", "169.254.169.254", "0.0.0.0", "100.64.0.1", "224.0.0.1", "::", "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "::ffff:a00:1", "2001:db8::1"])("rejects non-public address %s", address => expect(publicAddress(address)).toBe(false)); // public-safety: allow-ip -- synthetic reserved-address rejection cases
it.each(["8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"])("accepts global address %s", address => expect(publicAddress(address)).toBe(true)); // public-safety: allow-ip -- public-address classification fixtures
it("rejects mixed DNS answers and metadata names", async () => {
  await expect(publicDestination("https://example.com", async () => [{ address: "8.8.8.8", family: 4 }, { address: "127.0.0.1", family: 4 }])).rejects.toMatchObject({ code: "restricted_destination" }); // public-safety: allow-ip -- synthetic mixed DNS answers
  for (const url of ["http://localhost/", "http://metadata/", "http://metadata.google.internal/", "http://[::ffff:127.0.0.1]/"]) await expect(publicDestination(url)).rejects.toMatchObject({ code: "restricted_destination" }); // public-safety: allow-ip -- mapped loopback fixture
});
it("returns validated addresses for transport pinning, rejecting a changed DNS answer", async () => {
  const result = await publicDestination("https://example.com/path", async () => [{ address: "8.8.8.8", family: 4 }]); // public-safety: allow-ip -- injected public DNS fixture
  expect(result.addresses).toEqual([{ address: "8.8.8.8", family: 4 }]); // public-safety: allow-ip -- injected public DNS fixture
  await expect(publicDestination(result.url.href, async () => [{ address: "10.0.0.1", family: 4 }])).rejects.toThrow(/non-public/); // public-safety: allow-ip -- injected private DNS fixture
});
