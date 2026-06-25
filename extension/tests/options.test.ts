// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

let mockSettings = {
  apiBaseUrl: "https://api.mdtero.com",
  token: undefined as string | undefined,
  email: undefined as string | undefined,
  uiLanguage: "en" as "en" | "zh",
  elsevierApiKey: undefined as string | undefined,
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

function createChromeMock() {
  return {
    tabs: {
      create: vi.fn(async () => undefined),
    },
    runtime: {
      getManifest: () => ({ version: "0.1.5" }),
      sendMessage: vi.fn(async () => ({ ok: true, result: { ok: true, summary: { asn: "AS786", city: "Nottingham" } } })),
    },
    storage: {
      local: {
        get: vi.fn(async () => ({})),
        set: vi.fn(async () => undefined),
      },
      onChanged: {
        addListener: vi.fn(),
      },
    },
  };
}

async function flushUi() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function loadOptionsModule(htmlPath = "src/options/index.html") {
  vi.resetModules();
  document.documentElement.innerHTML = readFileSync(resolve(htmlPath), "utf8");
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
    };
    mockReadSettings.mockClear();
    mockWriteSettings.mockClear();
    mockMergeSettings.mockClear();
    mockResolveUiLanguage.mockClear();
    mockGetUsage.mockClear();
    mockGetMyTasks.mockClear();
    mockDownloadArtifact.mockClear();
    globalThis.chrome = createChromeMock() as any;
  });

  it("shows extension-focused signed-out guidance and direct Elsevier key setup", async () => {
    await loadOptionsModule();

    expect(document.querySelector("#account-status")?.textContent).toBe("Not signed in with website OAuth.");
    expect(document.querySelector("#usage-status")?.textContent).toBe("Balance and quota appear after sign-in.");
    expect(document.querySelector("#open-account")?.textContent).toBe("Open website OAuth");
    expect(document.querySelector("#connection-guide-title")?.textContent).toBe("Connection guide");
    expect(document.querySelector("#connection-guide-list")?.textContent).toContain("upload a local PDF/EPUB");
    expect(document.querySelector("#elsevier-settings-title")?.textContent).toBe("Elsevier access");
    expect(document.querySelector("#proxy-settings-card")).toBeNull();
    expect(document.querySelector("#elsevier-settings-note")?.textContent).toContain("Article Retrieval XML");
    expect(document.querySelector("#elsevier-key-status")?.textContent).toBe("Not configured");
    expect(document.querySelector("#elsevier-api-key-note")?.textContent).toContain("Stored only in this browser");
    expect((document.querySelector("#history-section") as HTMLElement | null)?.hidden).toBe(true);
    expect(document.querySelector("#helper-status")).toBeNull();
    expect(document.querySelector("#connector-keys-section")).toBeNull();
    expect(document.querySelector("#password-input")).toBeNull();
    expect(document.querySelector("#code-input")).toBeNull();
  });

  it("keeps CLI, MCP, RAG, and API contract material out of the options surface", async () => {
    await loadOptionsModule();

    const optionsText = document.body.textContent || "";
    expect(document.querySelector("#cli-handoff-guide-card")).toBeNull();
    expect(document.querySelector("#input-route-card")).toBeNull();
    expect(document.querySelector("#server-api-contract-card")).toBeNull();
    expect(document.querySelector("#mcp-server-config-card")).toBeNull();
    expect(document.querySelector("#cli-onboarding-card")).toBeNull();
    expect(optionsText).not.toContain("uv tool install");
    expect(optionsText).not.toContain("mdtero mcp");
    expect(optionsText).not.toContain("FastMCP");
    expect(optionsText).not.toContain("RAG");
    expect(optionsText).not.toContain("/api/v1/projects");
  });

  it("shows signed-in usage and empty history messaging when the account has no tasks", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: "token-1",
      email: "reader@example.com",
      uiLanguage: "en",
      elsevierApiKey: "elsevier-user-key",
    };

    await loadOptionsModule();

    expect(document.querySelector("#account-status")?.textContent).toBe("Signed in as reader@example.com");
    expect(document.querySelector("#usage-status")?.textContent).toContain("Balance $12.00 · Parse 4 · Translation 2");
    expect(document.querySelector("#elsevier-key-status")?.textContent).toBe("Configured");
    expect((document.querySelector("#history-section") as HTMLElement | null)?.hidden).toBe(false);
    expect(document.querySelector("#history-list")?.textContent).toContain("No parsing or translation history found yet.");
    expect(document.querySelector("#settings-subtitle")?.textContent).toContain("browser-side paper capture");
    expect(document.querySelector("#connection-guide-list")?.textContent).toContain("Website OAuth is connected");
    expect(document.querySelector("#publisher-capability-groups")).toBeNull();
  });

  it("renders history artifact download actions with user-facing labels", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: "token-1",
      email: "reader@example.com",
      uiLanguage: "en",
      elsevierApiKey: undefined,
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
              paper_epub: { filename: "vaswani2017attention.epub" },
              paper_html: { filename: "vaswani2017attention.html" },
            },
          },
        },
      ],
    });

    await loadOptionsModule();

    expect(document.querySelector("#history-list")?.textContent).toContain("Download Markdown");
    expect(document.querySelector("#history-list")?.textContent).toContain("Download ZIP");
    expect(document.querySelector("#history-list")?.textContent).toContain("Download Translation");
    expect(document.querySelector("#history-list")?.textContent).toContain("Download EPUB");
    expect(document.querySelector("#history-list")?.textContent).toContain("Download HTML");
    expect(document.querySelector("#history-list")?.textContent).not.toContain("Download BUNDLE");
  });

  it("renders and downloads history actions from v1 download_artifacts", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: "token-1",
      email: "reader@example.com",
      uiLanguage: "en",
      elsevierApiKey: undefined,
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
              { artifact: "paper_epub", filename: "vaswani2017attention.epub" },
              { artifact: "paper_html", filename: "vaswani2017attention.html" },
            ],
          },
        },
      ],
    });

    await loadOptionsModule();

    const markdownButton = Array.from(document.querySelectorAll<HTMLButtonElement>(".history-download-button"))
      .find((button) => button.textContent === "Download Markdown");
    markdownButton?.click();

    await vi.waitFor(() => {
      expect(mockDownloadArtifact).toHaveBeenCalledWith("task-v1", "paper_md", "vaswani2017attention.md");
    });
  });

  it("persists API base, language, and user-owned Elsevier key", async () => {
    await loadOptionsModule();

    (document.querySelector("#api-base-url") as HTMLInputElement).value = "https://api.example.test";
    (document.querySelector("#elsevier-api-key") as HTMLInputElement).value = "elsevier-user-key";
    (document.querySelector("#ui-language") as HTMLSelectElement).value = "zh";

    (document.querySelector("#save-settings") as HTMLButtonElement).click();
    await flushUi();

    expect(mockWriteSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBaseUrl: "https://api.example.test",
        uiLanguage: "zh",
        elsevierApiKey: "elsevier-user-key",
      })
    );
    expect(document.querySelector("#elsevier-api-key-feedback")?.textContent).toContain("saved");
    expect(JSON.stringify(mockWriteSettings.mock.calls.at(-1)?.[0])).not.toContain("wileyTdmToken");
  });

  it("toggles and clears the Elsevier key from the visible settings card", async () => {
    mockSettings = {
      apiBaseUrl: "https://api.mdtero.com",
      token: undefined,
      email: undefined,
      uiLanguage: "en",
      elsevierApiKey: "elsevier-user-key",
    };

    await loadOptionsModule();

    const input = document.querySelector("#elsevier-api-key") as HTMLInputElement;
    expect(input.type).toBe("password");
    (document.querySelector("#toggle-elsevier-key") as HTMLButtonElement).click();
    expect(input.type).toBe("text");

    (document.querySelector("#clear-elsevier-key") as HTMLButtonElement).click();
    await flushUi();

    expect(mockWriteSettings).toHaveBeenCalledWith(expect.objectContaining({ elsevierApiKey: undefined }));
    expect(input.value).toBe("");
    expect(document.querySelector("#elsevier-key-status")?.textContent).toBe("Not configured");
    expect(document.querySelector("#elsevier-api-key-feedback")?.textContent).toContain("cleared");
  });

  it("shows campus proxy controls only in the development options surface", async () => {
    await loadOptionsModule("src/options/index.dev.html");

    expect(document.querySelector("#proxy-settings-title")?.textContent).toBe("Campus proxy");
    expect(document.querySelector("#proxy-url")?.getAttribute("placeholder")).toBe("socks5h://127.0.0.1:1080");
    expect(document.querySelector("#save-proxy-settings")?.textContent).toBe("Save proxy");
  });
});
