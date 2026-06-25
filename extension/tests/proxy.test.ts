import { describe, expect, it } from "vitest";

import {
  buildChromeProxyConfig,
  isExpectedCampusOutlet,
  parseProxyUrl,
  summarizeCampusOutlet
} from "../src/lib/proxy";

describe("parseProxyUrl", () => {
  it("parses http, https, and socks proxy URLs", () => {
    expect(parseProxyUrl("http://127.0.0.1:7890")).toEqual({
      scheme: "http",
      host: "127.0.0.1",
      port: 7890
    });
    expect(parseProxyUrl("https://proxy.example:8443")).toEqual({
      scheme: "https",
      host: "proxy.example",
      port: 8443
    });
    expect(parseProxyUrl("socks5h://100.127.22.74:20815")).toEqual({
      scheme: "socks5",
      host: "100.127.22.74",
      port: 20815
    });
    expect(parseProxyUrl("socks4a://127.0.0.1:1080")).toEqual({
      scheme: "socks4",
      host: "127.0.0.1",
      port: 1080
    });
  });

  it("rejects unsupported schemes", () => {
    expect(() => parseProxyUrl("ftp://127.0.0.1:21")).toThrow(/Unsupported proxy scheme/);
  });
});

describe("buildChromeProxyConfig", () => {
  it("builds fixed-server proxy rules with localhost bypass", () => {
    expect(
      buildChromeProxyConfig({
        scheme: "socks5",
        host: "127.0.0.1",
        port: 1080
      })
    ).toEqual({
      mode: "fixed_servers",
      rules: {
        singleProxy: {
          scheme: "socks5",
          host: "127.0.0.1",
          port: 1080
        },
        bypassList: ["127.0.0.1", "localhost", "<local>"]
      }
    });
  });
});

describe("campus outlet checks", () => {
  it("accepts the expected Nottingham Jisc outlet", () => {
    const payload = {
      ip: "194.176.XX.XX",
      asn: "AS786",
      asn_org: "Jisc Services Limited",
      city: "Nottingham",
      country: "GB"
    };
    expect(isExpectedCampusOutlet(payload)).toBe(true);
    expect(summarizeCampusOutlet(payload)).toMatchObject({
      asn: "AS786",
      city: "Nottingham"
    });
  });

  it("rejects unrelated outlets", () => {
    expect(
      isExpectedCampusOutlet({
        asn: "AS42689",
        asn_org: "Some ISP",
        city: "Coventry"
      })
    ).toBe(false);
  });
});
