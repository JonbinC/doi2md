// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

let mockSettings = {
  apiBaseUrl: "https://api.mdtero.com",
  token: undefined,
  email: undefined,
  uiLanguage: "en",
};

const mockReadSettings = vi.fn(async () => mockSettings);
const mockWriteSettings = vi.fn(async () => undefined);
const mockMergeSettings = vi.fn((current, next) => ({ ...current, ...next }));
const mockResolveUiLanguage = vi.fn((preferred) => preferred ?? "en");
const mockGetUsage = vi.fn(async () => ({ wallet_balance_display: "$12.00", parse_quota_remaining: 4, translation_quota_remaining: 2 }));
const mockGetMyTasks = vi.fn(async () => ({ items: [] }));
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
    getMyTasks: mockGetMyTasks,
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
    };
    mockReadSettings.mockClear();
    mockWriteSettings.mockClear();
    mockMergeSettings.mockClear();
    mockResolveUiLanguage.mockClear();
    mockGetUsage.mockClear();
    mockGetMyTasks.mockClear();
    mockDownloadArtifact.mockClear();
  });

  it("shows signed-out usage guidance without exposing local helper setup", async () => {
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "unknown" } })) as any;

    await loadOptionsModule();

    expect(document.querySelector("#account-status")?.textContent).toBe("Not signed in with website OAuth.");
    expect(document.querySelector("#usage-status")?.textContent).toBe("Balance and quota appear after sign-in.");
    expect(document.querySelector("#helper-status")).toBeNull();
    expect(document.querySelector("#connector-keys-section")).toBeNull();
    expect(document.querySelector("#shadow-status")).toBeNull();
    expect((document.querySelector("#history-section") as HTMLElement | null)?.hidden).toBe(true);
    expect(document.querySelector("#open-account")?.textContent).toBe("Open website OAuth");
    expect(document.querySelector("#connection-guide-title")?.textContent).toBe("Connection guide");
    expect(document.querySelector("#connection-guide-list")?.textContent).toContain("Open website OAuth");
    expect(document.querySelector("#connection-guide-list")?.textContent).toContain("upload a local PDF/EPUB");
    expect(document.querySelector("#password-input")).toBeNull();
    expect(document.querySelector("#code-input")).toBeNull();
  });

  it("shows signed-in usage and empty history messaging when the account has no tasks", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: "token-1",
      email: "reader@example.com",
      uiLanguage: "en",
    };
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "connected" } })) as any;

    await loadOptionsModule();

    expect(document.querySelector("#wiley-tdm-token-label")).toBeNull();
    expect(document.querySelector("#wiley-tdm-token")).toBeNull();
    expect(document.querySelector("#account-status")?.textContent).toBe("Signed in as reader@example.com");
    expect(document.querySelector("#usage-status")?.textContent).toContain("Balance $12.00 · Parse 4 · Translation 2");
    expect(document.querySelector("#helper-status")).toBeNull();
    expect((document.querySelector("#history-section") as HTMLElement | null)?.hidden).toBe(false);
    expect(document.querySelector("#history-list")?.textContent).toContain("No parsing or translation history found yet.");
    expect(document.querySelector("#settings-subtitle")?.textContent).toContain("browser capture, upload, translation, and download settings");
    expect(document.querySelector("#connection-guide-list")?.textContent).toContain("Website OAuth is connected");
    expect(document.querySelector("#connection-guide-list")?.textContent).toContain("Open history below");
    expect(document.querySelector("#publisher-capability-groups")).toBeNull();
  });

  it("renders history artifact download actions with user-facing labels", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: "token-1",
      email: "reader@example.com",
      uiLanguage: "en",
    };
    mockGetMyTasks.mockResolvedValueOnce({
      items: [
        {
          task_id: "task-1",
          status: "succeeded",
          task_kind: "parse",
          created_at: "2026-05-01T00:00:00Z",
          paper_input: "10.48550/arXiv.1706.03762",
          result: {
            artifacts: {
              paper_md: { filename: "vaswani2017attention.md" },
              paper_bundle: { filename: "vaswani2017attention.zip" },
              translated_md: { filename: "vaswani2017attention_CN.md" },
            },
          },
        },
      ],
    });
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "connected" } })) as any;

    await loadOptionsModule();

    expect(document.querySelector("#history-list")?.textContent).toContain("Download Markdown");
    expect(document.querySelector("#history-list")?.textContent).toContain("Download ZIP");
    expect(document.querySelector("#history-list")?.textContent).toContain("Download Translation");
    expect(document.querySelector("#history-list")?.textContent).not.toContain("Download BUNDLE");
  });

  it("renders and downloads history actions from v1 download_artifacts", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: "token-1",
      email: "reader@example.com",
      uiLanguage: "en",
    };
    mockGetMyTasks.mockResolvedValueOnce({
      items: [
        {
          task_id: "task-v1",
          status: "succeeded",
          task_kind: "parse",
          created_at: "2026-05-01T00:00:00Z",
          paper_input: "10.48550/arXiv.1706.03762",
          result: {
            preferred_artifact: "paper_md",
            download_artifacts: [
              { artifact: "paper_md", filename: "vaswani2017attention.md" },
              { artifact: "paper_bundle", filename: "vaswani2017attention.zip" },
            ],
          },
        },
      ],
    });
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "connected" } })) as any;

    await loadOptionsModule();

    expect(document.querySelector("#history-list")?.textContent).toContain("Download Markdown");
    expect(document.querySelector("#history-list")?.textContent).toContain("Download ZIP");

    const markdownButton = Array.from(document.querySelectorAll<HTMLButtonElement>(".history-download-button"))
      .find((button) => button.textContent === "Download Markdown");
    markdownButton?.click();

    await vi.waitFor(() => {
      expect(mockDownloadArtifact).toHaveBeenCalledWith("task-v1", "paper_md", "vaswani2017attention.md");
    });
  });

  it("persists advanced API base and language without publisher key fields", async () => {
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "connected" } })) as any;

    await loadOptionsModule();

    (document.querySelector("#api-base-url") as HTMLInputElement).value = "https://api.example.test";
    (document.querySelector("#ui-language") as HTMLSelectElement).value = "zh";

    (document.querySelector("#save-settings") as HTMLButtonElement).click();
    await flushUi();

    expect(mockWriteSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBaseUrl: "https://api.example.test",
        uiLanguage: "zh",
      })
    );
    expect(JSON.stringify(mockWriteSettings.mock.calls.at(-1)?.[0])).not.toContain("wileyTdmToken");
  });
});
