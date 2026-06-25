export const SUPPORTED_PROXY_SCHEMES = [
  "http",
  "https",
  "socks4",
  "socks4a",
  "socks5",
  "socks5h"
] as const;

export type SupportedProxyScheme = (typeof SUPPORTED_PROXY_SCHEMES)[number];

export type ParsedProxy = {
  scheme: "http" | "https" | "socks4" | "socks5";
  host: string;
  port: number;
};

export type CampusOutletSummary = {
  ip?: string;
  asn?: string;
  asn_org?: string;
  city?: string;
  country?: string;
};

export function parseProxyUrl(raw?: string | null): ParsedProxy | null {
  const cleaned = String(raw || "").trim();
  if (!cleaned) {
    return null;
  }

  let url: URL;
  try {
    url = new URL(cleaned);
  } catch {
    throw new Error("Proxy URL is invalid.");
  }

  const scheme = url.protocol.replace(":", "").toLowerCase();
  if (!SUPPORTED_PROXY_SCHEMES.includes(scheme as SupportedProxyScheme)) {
    throw new Error(`Unsupported proxy scheme: ${scheme || "missing"}`);
  }

  const host = url.hostname.trim();
  if (!host) {
    throw new Error("Proxy URL must include a host.");
  }

  const port = url.port
    ? Number(url.port)
    : scheme === "https"
      ? 443
      : scheme.startsWith("socks")
        ? 1080
        : 80;

  const chromeScheme: ParsedProxy["scheme"] =
    scheme === "socks4a"
      ? "socks4"
      : scheme === "socks5h"
        ? "socks5"
        : scheme === "socks4" || scheme === "socks5" || scheme === "http" || scheme === "https"
          ? scheme
          : "http";

  return {
    scheme: chromeScheme,
    host,
    port
  };
}

export function buildChromeProxyConfig(parsed: ParsedProxy): chrome.proxy.ProxyConfig {
  return {
    mode: "fixed_servers",
    rules: {
      singleProxy: {
        scheme: parsed.scheme,
        host: parsed.host,
        port: parsed.port
      },
      bypassList: ["127.0.0.1", "localhost", "<local>"]
    }
  };
}

export function maskProxyUrl(raw?: string | null): string | null {
  const cleaned = String(raw || "").trim();
  if (!cleaned) {
    return null;
  }
  try {
    const url = new URL(cleaned);
    if (url.username) {
      return `${url.protocol}//***@${url.hostname}${url.port ? `:${url.port}` : ""}`;
    }
    return cleaned;
  } catch {
    return "***";
  }
}

export function summarizeCampusOutlet(payload: unknown): CampusOutletSummary {
  if (!payload || typeof payload !== "object") {
    return {};
  }
  const record = payload as Record<string, unknown>;
  return {
    ip: typeof record.ip === "string" ? record.ip : undefined,
    asn: typeof record.asn === "string" ? record.asn : undefined,
    asn_org: typeof record.asn_org === "string"
      ? record.asn_org
      : typeof record.org === "string"
        ? record.org
        : undefined,
    city: typeof record.city === "string" ? record.city : undefined,
    country: typeof record.country === "string" ? record.country : undefined
  };
}

export function isExpectedCampusOutlet(payload: unknown): boolean {
  const summary = summarizeCampusOutlet(payload);
  const asn = String(summary.asn || "").toUpperCase();
  const org = String(summary.asn_org || "").toLowerCase();
  const city = String(summary.city || "").toLowerCase();
  return asn === "AS786" && org.includes("jisc") && city === "nottingham";
}
