import { describe, expect, it } from "vitest";

import {
  isTrustedMdteroOrigin,
  shouldAcceptMdteroAuthMessage
} from "../src/lib/auth-bridge";

describe("isTrustedMdteroOrigin", () => {
  it("allows Mdtero and local development origins", () => {
    expect(isTrustedMdteroOrigin("https://mdtero.com")).toBe(true);
    expect(isTrustedMdteroOrigin("https://app.mdtero.com")).toBe(true);
    expect(isTrustedMdteroOrigin("http://localhost:3000")).toBe(true);
    expect(isTrustedMdteroOrigin("http://127.0.0.1:5173")).toBe(true);
  });

  it("rejects publisher and third-party origins", () => {
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
          token: "token-1",
          email: "reader@example.com"
        }
      })
    ).toBe(true);

    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://www.sciencedirect.com",
        eventOrigin: "https://www.sciencedirect.com",
        data: {
          type: "mdtero.auth.token",
          token: "token-1",
          email: "reader@example.com"
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
        data: { type: "mdtero.auth.token", email: "reader@example.com" }
      })
    ).toBe(false);
    expect(
      shouldAcceptMdteroAuthMessage({
        currentOrigin: "https://mdtero.com",
        eventOrigin: "https://example.com",
        data: {
          type: "mdtero.auth.token",
          token: "token-1",
          email: "reader@example.com"
        }
      })
    ).toBe(false);
  });
});
