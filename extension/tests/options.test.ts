// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

let mockSettings = {
  apiBaseUrl: "https://api.mdtero.com",
  token: undefined,
  email: undefined,
  uiLanguage: "en",
  elsevierApiKey: undefined,
  springerOpenAccessApiKey: undefined,
};

const mockReadSettings = vi.fn(async () => mockSettings);
const mockWriteSettings = vi.fn(async () => undefined);
const mockMergeSettings = vi.fn((current, next) => ({ ...current, ...next }));
const mockResolveUiLanguage = vi.fn((preferred) => preferred ?? "en");
const mockGetUsage = vi.fn(async () => ({ wallet_balance_display: "$12.00", parse_quota_remaining: 4, translation_quota_remaining: 2 }));
const mockGetParserV2ShadowDiagnostics = vi.fn(async () => ({ routes: [] }));
const mockGetMyTasks = vi.fn(async () => ({ items: [] }));
const mockStartEmailAuth = vi.fn(async () => ({}));
const mockVerifyEmailAuth = vi.fn(async () => ({ token: "verified-token" }));
const mockLoginWithPassword = vi.fn(async () => ({ token: "login-token" }));
const mockDownloadArtifact = vi.fn(async () => ({ blob: new Blob(["demo"]), filename: "paper.md" }));

vi.mock("../src/lib/storage", () => ({
  readSettings: mockReadSettings,
  writeSettings: mockWriteSettings,
  mergeSettings: mockMergeSettings,
  resolveUiLanguage: mockResolveUiLanguage,
}));

vi.mock("../src/lib/api", () => ({
  createApiClient: () => ({
    getUsage: mockGetUsage,
    getParserV2ShadowDiagnostics: mockGetParserV2ShadowDiagnostics,
    getMyTasks: mockGetMyTasks,
    startEmailAuth: mockStartEmailAuth,
    verifyEmailAuth: mockVerifyEmailAuth,
    loginWithPassword: mockLoginWithPassword,
    downloadArtifact: mockDownloadArtifact,
  }),
}));

vi.mock("../src/lib/download", () => ({
  triggerBlobDownload: vi.fn(),
}));

function createChromeMock(sendMessageImpl: () => Promise<unknown>) {
  return {
    runtime: {
      sendMessage: vi.fn(sendMessageImpl),
      getManifest: () => ({ version: "0.1.5" }),
    },
    storage: {
      local: {
        get: vi.fn(async () => ({})),
        set: vi.fn(async () => undefined),
      },
    },
  };
}

async function flushUi() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function loadOptionsModule() {
  vi.resetModules();
  document.documentElement.innerHTML = readFileSync(resolve("src/options/index.html"), "utf8");
  await import("../src/options/index.ts");
  await flushUi();
}

describe("extension options page", () => {
  beforeEach(() => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: undefined,
      email: undefined,
      uiLanguage: "en",
      elsevierApiKey: undefined,
      springerOpenAccessApiKey: undefined,
    };
    mockReadSettings.mockClear();
    mockWriteSettings.mockClear();
    mockMergeSettings.mockClear();
    mockResolveUiLanguage.mockClear();
    mockGetUsage.mockClear();
    mockGetParserV2ShadowDiagnostics.mockClear();
    mockGetMyTasks.mockClear();
    mockStartEmailAuth.mockClear();
    mockVerifyEmailAuth.mockClear();
    mockLoginWithPassword.mockClear();
    mockDownloadArtifact.mockClear();
  });

  it("shows signed-out usage guidance and an actionable helper message when the helper is unavailable", async () => {
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "unknown" } })) as any;

    await loadOptionsModule();

    expect(document.querySelector("#account-status")?.textContent).toBe("Not signed in.");
    expect(document.querySelector("#usage-status")?.textContent).toBe("Balance and quota appear after sign-in.");
    expect(document.querySelector("#helper-status")?.textContent).toBe(
      "Local helper not detected yet. Install or restart mdtero to enable browser-assisted capture."
    );
    expect(document.querySelector("#shadow-status")?.textContent).toBe(
      "Sign in to view experimental connector shadow status."
    );
    expect((document.querySelector("#history-section") as HTMLElement | null)?.hidden).toBe(true);
  });

  it("shows signed-in usage and empty history messaging when the account has no tasks", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: "token-1",
      email: "reader@example.com",
      uiLanguage: "en",
      elsevierApiKey: undefined,
      springerOpenAccessApiKey: undefined,
    };
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "connected" } })) as any;

    await loadOptionsModule();

    expect(document.querySelector("#account-status")?.textContent).toBe("Signed in as reader@example.com");
    expect(document.querySelector("#usage-status")?.textContent).toContain("Balance $12.00 · Parse 4 · Translation 2");
    expect(document.querySelector("#helper-status")?.textContent).toBe("Local helper ready for browser-assisted capture.");
    expect((document.querySelector("#history-section") as HTMLElement | null)?.hidden).toBe(false);
    expect(document.querySelector("#history-list")?.textContent).toContain("No parsing or translation history found yet.");
  });
});
