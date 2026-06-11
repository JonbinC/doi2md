import { describe, expect, it } from "vitest";

import {
  MDTERO_ACCOUNT_URL,
  isFreshAuthBridgeTimestamp,
  isTrustedMdteroOrigin,
  shouldAcceptMdteroAuthMessage
} from "../src/lib/auth-bridge";

describe("MDTERO_ACCOUNT_URL", () => {
  it("opens the canonical website auth route for extension sign-in", () => {
    expect(MDTERO_ACCOUNT_URL).toBe("https://mdtero.com/auth?source=extension");
    expect(MDTERO_ACCOUNT_URL).not.toContain("/account");
  });
});

describe("isTrustedMdteroOrigin", () => {
  it("allows the production site origin and local development origins", () => {
    expect(isTrustedMdteroOrigin("https://mdtero.com")).toBe(true);
    expect(isTrustedMdteroOrigin("https://www.mdtero.com")).toBe(true);
    expect(isTrustedMdteroOrigin("http://localhost:3000")).toBe(true);
    expect(isTrustedMdteroOrigin("http://127.0.0.1:5173")).toBe(true);
  });

  it("rejects publisher, third-party, and unrelated mdtero subdomain origins", () => {
    expect(isTrustedMdteroOrigin("https://app.mdtero.com")).toBe(false);
    expect(isTrustedMdteroOrigin("https://www.sciencedirect.com")).toBe(false);
    expect(isTrustedMdteroOrigin("https://arxiv.org")).toBe(false);
    expect(isTrustedMdteroOrigin("https://example.com")).toBe(false);
    expect(isTrustedMdteroOrigin("not-a-url")).toBe(false);
  });
});

describe("shouldAcceptMdteroAuthMessage", () => {
  it("only accepts auth bridge messages on trusted origins", () => {
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://mdtero.com",
        data: {
          type: "mdtero.auth.token",
          source: "extension",
          token: "token-1",
          email: "reader@example.com",
          issuedAt: Date.now()
        }
      })
    ).toBe(true);

    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://www.sciencedirect.com",
        eventOrigin: "https://www.sciencedirect.com",
        data: {
          type: "mdtero.auth.token",
          source: "extension",
          token: "token-1",
          email: "reader@example.com",
          issuedAt: Date.now()
        }
      })
    ).toBe(false);
  });

  it("rejects malformed or incomplete messages", () => {
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://mdtero.com",
        data: null
      })
    ).toBe(false);
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://mdtero.com",
        data: { type: "mdtero.auth.token", source: "extension", email: "reader@example.com", issuedAt: Date.now() }
      })
    ).toBe(false);
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://mdtero.com",
        data: {
          type: "mdtero.auth.token",
          token: "token-1",
          email: "reader@example.com",
          issuedAt: Date.now()
        }
      })
    ).toBe(false);
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://mdtero.com",
        data: {
          type: "mdtero.auth.token",
          source: "extension",
          token: "token-1",
          email: "reader@example.com",
          issuedAt: Date.now() - 120_000
        }
      })
    ).toBe(false);
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://example.com",
        data: {
          type: "mdtero.auth.token",
          source: "extension",
          token: "token-1",
          email: "reader@example.com",
          issuedAt: Date.now()
        }
      })
    ).toBe(false);
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://www.mdtero.com",
        data: {
          type: "mdtero.auth.token",
          source: "extension",
          token: "token-1",
          email: "reader@example.com",
          issuedAt: Date.now()
        }
      })
    ).toBe(false);
  });
});

describe("isFreshAuthBridgeTimestamp", () => {
  it("accepts recent auth bridge messages and rejects stale or invalid ones", () => {
    expect(isFreshAuthBridgeTimestamp(1_000, 1_000)).toBe(true);
    expect(isFreshAuthBridgeTimestamp(1_000, 61_001)).toBe(false);
    expect(isFreshAuthBridgeTimestamp(Number.NaN, 1_000)).toBe(false);
  });
});
