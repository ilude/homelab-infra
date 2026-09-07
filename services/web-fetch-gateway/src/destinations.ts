import dns from "node:dns/promises";
import ipaddr from "ipaddr.js";
import { FetchError, parseUrl } from "./contract.js";

export type Address = { address: string; family: number };
export type Resolver = (hostname: string) => Promise<Address[]>;
export const resolve: Resolver = hostname => dns.lookup(hostname, { all: true });
export function publicAddress(address: string): boolean {
  try {
    const parsed = ipaddr.process(address);
    return parsed.range() === "unicast";
  } catch { return false; }
}
export async function publicDestination(value: string, resolver: Resolver = resolve): Promise<{ url: URL; addresses: Address[] }> {
  const url = parseUrl(value);
  const host = url.hostname.replace(/^\[|\]$/g, "").replace(/\.$/, "").toLowerCase();
  if (host === "localhost" || host.endsWith(".localhost") || host === "metadata"
      || host === "metadata.google.internal")
    throw new FetchError("restricted_destination", "Local or metadata destination is not allowed");
  const addresses = ipaddr.isValid(host)
    ? [{ address: host, family: ipaddr.parse(host).kind() === "ipv4" ? 4 : 6 }]
    : await resolver(host);
  if (!addresses.length || addresses.some(record => !publicAddress(record.address)))
    throw new FetchError("restricted_destination", "Destination includes a non-public address");
  return { url, addresses: [...addresses].sort((a, b) => a.family - b.family) };
}
