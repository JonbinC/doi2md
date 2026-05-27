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
    expect(document.querySelector("#cli-handoff-guide-title")?.textContent).toBe("Extension + CLI handoff");
    expect(document.querySelector("#cli-handoff-guide-note")?.textContent).toContain("publisher challenge");
    expect(document.querySelector("#cli-handoff-guide-note")?.textContent).toContain("mdtero setup --json");
    expect(document.querySelector("#cli-handoff-guide-note")?.textContent).toContain("one-command RAG bootstrap");
    expect(document.querySelector("#cli-handoff-guide-note")?.textContent).toContain("server project id");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero doctor --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("uv tool install git+https://github.com/JonbinC/doi2md.git");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero setup");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero setup --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero config academic");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero discover \"<topic>\" --limit 5 --interactive");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero parse <doi-or-url> --trace --wait --timeout 300 --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero status <task-id> --wait --timeout 300 --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero download <task-id> paper_md --output-dir ./mdtero-output --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero project ingest --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero project parse --wait --timeout 300 --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero project refresh --wait --timeout 300 --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero rag build --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero rag status --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero rag query \"<question>\" --build-if-needed --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero mcp briefing --json");
    expect(document.querySelector("#cli-handoff-guide-command")?.textContent).toContain("mdtero mcp serve");
    expect(document.querySelector("#cli-handoff-guide-boundary")?.textContent).toContain("does not install Python dependencies");
    expect(document.querySelector("#cli-handoff-guide-boundary")?.textContent).toContain("mdtero config academic");
    expect(document.querySelector("#input-route-card")).not.toBeNull();
    expect(document.querySelector("#input-route-title")?.textContent).toBe("Input routes");
    expect(document.querySelector("#input-route-note")?.textContent).toContain("shortest path to a Markdown artifact");
    expect(document.querySelector("#input-route-pill")?.textContent).toBe("Extension + CLI");
    const routeText = document.querySelector("#input-route-list")?.textContent || "";
    expect(routeText).toContain("DOI or URL");
    expect(routeText).toContain("PDF / EPUB file");
    expect(routeText).toContain("Browser extension");
    expect(routeText).toContain("RAG / MCP");
    expect(routeText).toContain("mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json");
    expect(routeText).toContain("mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json");
    expect(routeText).toContain("backend MinerU-first path");
    expect(routeText).toContain("OAuth, campus network, cookies");
    expect(routeText).toContain("mdtero rag query \"What are the strongest findings?\" --build-if-needed --json");
    expect(routeText).toContain("without asking you to copy a server project id");
    expect(routeText).toContain("FastMCP");
    expect(document.querySelector("#server-api-contract-card")).not.toBeNull();
    expect(document.querySelector("#server-api-contract-title")?.textContent).toBe("Server API contract");
    expect(document.querySelector("#server-api-contract-note")?.textContent).toContain("/api/v1 routes");
    const serverApiText = document.querySelector("#server-api-contract-list")?.textContent || "";
    expect(serverApiText).toContain("route");
    expect(serverApiText).toContain("/api/v1/route");
    expect(serverApiText).toContain("upload");
    expect(serverApiText).toContain("/api/v1/tasks/upload");
    expect(serverApiText).toContain("/api/v1/tasks/{task_id}/download/{artifact}");
    expect(serverApiText).toContain("/api/v1/projects/{project_id}/tasks/{task_id}/import");
    expect(serverApiText).toContain("/api/v1/projects/{project_id}/rag/query");
    expect(document.querySelector("#mcp-server-config-card")).not.toBeNull();
    expect(document.querySelector("#mcp-server-config-title")?.textContent).toBe("Agent MCP server");
    expect(document.querySelector("#mcp-server-config-note")?.textContent).toContain("mdtero mcp serve");
    expect(document.querySelector("#mcp-server-config-meta")?.textContent).toContain("FastMCP");
    expect(document.querySelector("#mcp-server-config-meta")?.textContent).toContain("stdio");
    const mcpConfig = JSON.parse(document.querySelector("#mcp-server-config-command")?.textContent || "{}");
    expect(mcpConfig.mcpServers.mdtero).toEqual({
      command: "mdtero",
      args: ["mcp", "serve"],
      cwd: "<local-mdtero-project-root>",
    });
    expect(document.querySelector("#cli-onboarding-title")?.textContent).toBe("CLI setup checklist");
    expect(document.querySelector("#cli-onboarding-note")?.textContent).toContain("local acquisition");
    expect(document.querySelector("#cli-onboarding-pill")?.textContent).toBe("Python / uv");
    const checklistText = document.querySelector("#cli-onboarding-list")?.textContent || "";
    expect(checklistText).toContain("uv tool install git+https://github.com/JonbinC/doi2md.git");
    expect(checklistText).toContain("mdtero setup");
    expect(checklistText).toContain("mdtero setup --json");
    expect(checklistText).toContain("mdtero config academic");
    expect(checklistText).toContain("mdtero discover \"<topic>\" --limit 5 --interactive");
    expect(checklistText).toContain("mdtero parse <doi-or-url> --trace --wait --timeout 300 --json");
    expect(checklistText).toContain("mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json");
    expect(checklistText).toContain("mdtero rag query \"What are the strongest findings?\" --build-if-needed --json");
    expect(checklistText).toContain("create or bind the server project");
    expect(checklistText).toContain("mdtero agent install --interactive");
    expect(checklistText).toContain("Backend Voyage RAG is driven by the CLI project");
    expect(checklistText).toContain("citation_contract requires final answers to preserve citations and source_nodes");
    expect(checklistText).toContain("mdtero mcp briefing --json");
    expect(checklistText).toContain("mdtero mcp serve");
    expect(checklistText).toContain("FastMCP stdio server");
    expect(checklistText).toContain("RAG readiness, and citation_contract to local agents");
    expect(checklistText).not.toContain("native helper");
    expect(checklistText).not.toContain("publisher API");
    expect(document.querySelector("#password-input")).toBeNull();
    expect(document.querySelector("#code-input")).toBeNull();
  });

  it("copies the full CLI handoff guide from options", async () => {
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "unknown" } })) as any;

    await loadOptionsModule();

    (document.querySelector("#copy-cli-handoff-guide") as HTMLButtonElement).click();
    await vi.waitFor(() => {
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero doctor --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("uv tool install git+https://github.com/JonbinC/doi2md.git"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero setup --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero config academic"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero project ingest --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero project refresh --wait --timeout 300 --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero rag build --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero rag status --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero rag query \"<question>\" --build-if-needed --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("Preserve citation_contract.required_for_final_answer"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("final RAG answers keep citations and source_nodes"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero mcp briefing --json"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("mdtero mcp serve"));
    });
    expect(document.querySelector("#copy-cli-handoff-guide")?.textContent).toBe("CLI handoff copied.");
  });

  it("copies individual input route commands from options", async () => {
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "unknown" } })) as any;

    await loadOptionsModule();

    const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>(".input-route-copy"));
    expect(buttons).toHaveLength(4);
    buttons[1].click();

    await vi.waitFor(() => {
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith("mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json");
    });
    expect(buttons[1].textContent).toBe("Route copied.");
  });

  it("copies the shared server API contract from options", async () => {
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "unknown" } })) as any;

    await loadOptionsModule();

    (document.querySelector("#copy-server-api-contract") as HTMLButtonElement).click();
    await vi.waitFor(() => {
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("route: /api/v1/route"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("upload: /api/v1/tasks/upload"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("project_import: /api/v1/projects/{project_id}/tasks/{task_id}/import"));
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("rag_query: /api/v1/projects/{project_id}/rag/query"));
    });
    expect(document.querySelector("#copy-server-api-contract")?.textContent).toBe("API contract copied.");
  });

  it("copies a parseable MCP server config for local agents", async () => {
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    globalThis.chrome = createChromeMock(async () => ({ result: { state: "unknown" } })) as any;

    await loadOptionsModule();

    (document.querySelector("#copy-mcp-server-config") as HTMLButtonElement).click();
    await vi.waitFor(() => {
      expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining('"mcpServers"'));
    });
    const copied = vi.mocked(window.navigator.clipboard.writeText).mock.calls.at(-1)?.[0] as string;
    expect(JSON.parse(copied).mcpServers.mdtero).toEqual({
      command: "mdtero",
      args: ["mcp", "serve"],
      cwd: "<local-mdtero-project-root>",
    });
    expect(document.querySelector("#copy-mcp-server-config")?.textContent).toBe("MCP config copied.");
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
    expect(document.querySelector("#cli-handoff-guide-note")?.textContent).toContain("current-page parse");
    expect(document.querySelector("#cli-onboarding-list")?.textContent).toContain("mdtero mcp briefing");
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
