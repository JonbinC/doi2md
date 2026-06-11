import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionRouteResponse } from "@mdtero/shared";

const executeAction = vi.fn();

vi.mock("../src/lib/action-executor", () => ({
  executeAction,
}));

function buildRoutePlan(overrides: Partial<ExtensionRouteResponse> = {}): ExtensionRouteResponse {
  return {
    input_kind: "doi",
    input_value: "10.1000/demo",
    top_connector: "wiley_tdm",
    route_kind: "browser_capture_required",
    acquisition_mode: "browser_extension",
    requires_browser_capture: true,
    allows_current_tab: true,
    action_sequence: ["fetch_browser_source"],
    acceptance_rules: {},
    fail_closed: true,
    matched_connectors: ["wiley_tdm"],
    ...overrides,
  };
}

describe("ssot-route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("forwards page context when fetching route plans", async () => {
    const routeClient = {
      fetchRoutePlan: vi.fn().mockResolvedValue(buildRoutePlan()),
    };

    const { fetchRoutePlanFromSsot } = await import("../src/lib/ssot-route");
    await fetchRoutePlanFromSsot(routeClient, "10.1000/demo", {
      tabUrl: "https://example.org/paper",
      tabTitle: "Example Paper",
    });

    expect(routeClient.fetchRoutePlan).toHaveBeenCalledWith({
      input: "10.1000/demo",
      page_url: "https://example.org/paper",
      page_title: "Example Paper",
    });
  });

  it("submits raw artifacts returned by action execution", async () => {
    const rawArtifact = new Blob(["demo"], { type: "text/html" });
    executeAction.mockResolvedValue({
      success: true,
      rawArtifact,
      filename: "paper.html",
      sourceDoi: "10.1000/demo",
    });

    const task = {
      task_id: "task-123",
      status: "queued",
      next_commands: ["mdtero status task-123 --wait --timeout 300 --json"],
    };
    const parseClient = {
      createParseTask: vi.fn(),
      createRawUploadTask: vi.fn().mockResolvedValue(task),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(parseClient, buildRoutePlan(), {
      input: "10.1000/demo",
      tabId: 7,
      tabUrl: "https://example.org/paper",
      tabTitle: "Example Paper",
    });

    expect(executeAction).toHaveBeenCalledWith(
      "fetch_browser_source",
      expect.objectContaining({
        input: "10.1000/demo",
        tabId: 7,
      }),
      expect.objectContaining({
        top_connector: "wiley_tdm",
      }),
    );
    expect(parseClient.createRawUploadTask).toHaveBeenCalledWith({
      rawFile: rawArtifact,
      filename: "paper.html",
      sourceDoi: "10.1000/demo",
      sourceInput: "10.1000/demo",
      artifactKind: "html",
    });
    expect(result).toEqual({
      success: true,
      taskId: "task-123",
      task,
    });
  });

  it("passes client handoff candidates and publisher capabilities into action execution", async () => {
    executeAction.mockResolvedValue({
      success: false,
      requiresBrowserCapture: true,
      error: "Use browser PDF gateway.",
    });

    const parseClient = {
      createParseTask: vi.fn(),
      createRawUploadTask: vi.fn(),
    };

    const routePlan = buildRoutePlan({
      action_sequence: ["fallback_pdf_parse"],
      client_handoff_candidates: [
        {
          transport: "browser_extension",
          capture_mode: "download_artifact",
          artifact_kind: "pdf",
          artifact_url: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149",
          requires_user_rights: true,
        },
      ],
      publisher_capabilities: {
        access_mode: "institution_browser",
        browser_extension_useful: true,
      },
    });

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    await executeSsotActionSequence(parseClient, routePlan, {
      input: "10.1109/demo",
    });

    expect(executeAction).toHaveBeenCalledWith(
      "fallback_pdf_parse",
      expect.objectContaining({ input: "10.1109/demo" }),
      expect.objectContaining({
        client_handoff_candidates: routePlan.client_handoff_candidates,
        publisher_capabilities: routePlan.publisher_capabilities,
      }),
    );
  });

  it("fails closed when raw artifact submission fails on a fail-closed route", async () => {
    executeAction.mockResolvedValue({
      success: true,
      rawArtifact: new Blob(["demo"], { type: "text/html" }),
    });

    const parseClient = {
      createParseTask: vi.fn(),
      createRawUploadTask: vi.fn().mockRejectedValue(new Error("submit failed")),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(
      parseClient,
      buildRoutePlan({ fail_closed: true }),
      { input: "10.1000/demo" },
    );

    expect(result.success).toBe(false);
    expect(result.error).toContain("submit failed");
    expect(result.nextCommand).toBe("mdtero parse 10.1000/demo --trace --wait --timeout 300 --json");
  });

  it("uses shell-safe CLI handoff when server-parse fallback submission fails", async () => {
    const parseClient = {
      createParseTask: vi.fn().mockRejectedValue(new Error("server parse unavailable")),
      createRawUploadTask: vi.fn(),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(
      parseClient,
      buildRoutePlan({
        top_connector: "server_parse",
        route_kind: "server",
        acquisition_mode: "server_parse",
        requires_browser_capture: false,
        allows_current_tab: false,
        action_sequence: ["server_parse"],
        route_planner_fallback: true,
      }),
      { input: "https://example.org/paper?q=a b's" },
    );

    expect(result).toEqual({
      success: false,
      error: "Error: server parse unavailable",
      nextCommand: "mdtero parse 'https://example.org/paper?q=a b'\"'\"'s' --trace --wait --timeout 300 --json",
    });
  });

  it("continues to the next action when raw artifact submission fails on a non-fail-closed route", async () => {
    executeAction
      .mockResolvedValueOnce({
        success: true,
        rawArtifact: new Blob(["demo"], { type: "text/html" }),
      })
      .mockResolvedValueOnce({
        success: true,
        taskId: "fallback-task",
      });

    const parseClient = {
      createParseTask: vi.fn(),
      createRawUploadTask: vi.fn().mockRejectedValue(new Error("submit failed")),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(
      parseClient,
      buildRoutePlan({
        fail_closed: false,
        action_sequence: ["fetch_browser_source", "capture_current_tab_html"],
      }),
      { input: "10.1000/demo" },
    );

    expect(executeAction).toHaveBeenCalledTimes(2);
    expect(result).toEqual({
      success: true,
      taskId: "fallback-task",
    });
  });

  it("propagates requires-upload and browser-capture failures without extra submission", async () => {
    executeAction.mockResolvedValue({
      success: false,
      requiresUpload: true,
      error: "PDF upload required",
      nextCommand: "mdtero parse 10.1000/demo --trace --wait --timeout 300 --json",
    });

    const parseClient = {
      createParseTask: vi.fn(),
      createRawUploadTask: vi.fn(),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(parseClient, buildRoutePlan(), {
      input: "10.1000/demo",
    });

    expect(parseClient.createRawUploadTask).not.toHaveBeenCalled();
    expect(result).toEqual({
      success: false,
      requiresBrowserCapture: undefined,
      requiresUpload: true,
      error: "PDF upload required",
      nextCommand: "mdtero parse 10.1000/demo --trace --wait --timeout 300 --json",
    });
  });

  it("normalizes local raw acquisition failures to browser-capture failures for the extension UI", async () => {
    executeAction.mockResolvedValue({
      success: false,
      requiresBrowserCapture: true,
      error: "Open the article page and retry browser capture.",
      nextCommand: "mdtero parse 10.1000/demo --trace --wait --timeout 300 --json",
    });

    const parseClient = {
      createParseTask: vi.fn(),
      createRawUploadTask: vi.fn(),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(parseClient, buildRoutePlan(), {
      input: "10.1000/demo",
    });

    expect(parseClient.createRawUploadTask).not.toHaveBeenCalled();
    expect(result).toEqual({
      success: false,
      requiresBrowserCapture: true,
      requiresUpload: undefined,
      error: "Open the article page and retry browser capture.",
      nextCommand: "mdtero parse 10.1000/demo --trace --wait --timeout 300 --json",
    });
  });

  it("backfills CLI handoff when a fail-closed action returns no command", async () => {
    executeAction.mockResolvedValue({
      success: false,
      error: "Capture failed without a next command",
    });

    const parseClient = {
      createParseTask: vi.fn(),
      createRawUploadTask: vi.fn(),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(parseClient, buildRoutePlan({ fail_closed: true }), {
      input: "https://example.org/paper?q=a b",
    });

    expect(result).toEqual({
      success: false,
      error: "Capture failed without a next command",
      nextCommand: "mdtero parse 'https://example.org/paper?q=a b' --trace --wait --timeout 300 --json",
    });
  });

  it("submits server-parse fallback routes through v1 task creation", async () => {
    const task = { task_id: "task-server", status: "queued" };
    const parseClient = {
      createParseTask: vi.fn().mockResolvedValue(task),
      createRawUploadTask: vi.fn(),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(
      parseClient,
      buildRoutePlan({
        top_connector: "server_parse",
        route_kind: "server",
        acquisition_mode: "server_parse",
        requires_browser_capture: false,
        allows_current_tab: false,
        action_sequence: ["server_parse"],
        route_planner_fallback: true,
      }),
      { input: "10.1000/demo" },
    );

    expect(executeAction).not.toHaveBeenCalled();
    expect(parseClient.createParseTask).toHaveBeenCalledWith({ input: "10.1000/demo" });
    expect(parseClient.createRawUploadTask).not.toHaveBeenCalled();
    expect(result).toEqual({ success: true, taskId: "task-server", task });
  });
});
