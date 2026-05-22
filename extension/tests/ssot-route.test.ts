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
    route_kind: "html_helper_first",
    acquisition_mode: "browser_extension",
    requires_helper: true,
    allows_current_tab: true,
    action_sequence: ["fetch_helper_source"],
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

  it("submits raw fulltext artifacts returned by action execution", async () => {
    const rawArtifact = new Blob(["demo"], { type: "text/html" });
    executeAction.mockResolvedValue({
      success: true,
      rawArtifact,
      filename: "paper.html",
      sourceDoi: "10.1000/demo",
    });

    const parseClient = {
      createParseFulltextV2Task: vi.fn().mockResolvedValue({ task_id: "task-123" }),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(parseClient, buildRoutePlan(), {
      input: "10.1000/demo",
      tabId: 7,
      tabUrl: "https://example.org/paper",
      tabTitle: "Example Paper",
    });

    expect(executeAction).toHaveBeenCalledWith(
      "fetch_helper_source",
      expect.objectContaining({
        input: "10.1000/demo",
        tabId: 7,
      }),
      expect.objectContaining({
        top_connector: "wiley_tdm",
      }),
    );
    expect(parseClient.createParseFulltextV2Task).toHaveBeenCalledWith({
      fulltextFile: rawArtifact,
      filename: "paper.html",
      sourceDoi: "10.1000/demo",
      sourceInput: "10.1000/demo",
    });
    expect(result).toEqual({
      success: true,
      taskId: "task-123",
    });
  });

  it("fails closed when raw artifact submission fails on a fail-closed route", async () => {
    executeAction.mockResolvedValue({
      success: true,
      rawArtifact: new Blob(["demo"], { type: "text/html" }),
    });

    const parseClient = {
      createParseFulltextV2Task: vi.fn().mockRejectedValue(new Error("submit failed")),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(
      parseClient,
      buildRoutePlan({ fail_closed: true }),
      { input: "10.1000/demo" },
    );

    expect(result.success).toBe(false);
    expect(result.error).toContain("submit failed");
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
      createParseFulltextV2Task: vi.fn().mockRejectedValue(new Error("submit failed")),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(
      parseClient,
      buildRoutePlan({
        fail_closed: false,
        action_sequence: ["fetch_helper_source", "native_arxiv_parse"],
      }),
      { input: "10.1000/demo" },
    );

    expect(executeAction).toHaveBeenCalledTimes(2);
    expect(result).toEqual({
      success: true,
      taskId: "fallback-task",
    });
  });

  it("propagates requires-upload and requires-helper failures without extra submission", async () => {
    executeAction.mockResolvedValue({
      success: false,
      requiresUpload: true,
      error: "PDF upload required",
    });

    const parseClient = {
      createParseFulltextV2Task: vi.fn(),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(parseClient, buildRoutePlan(), {
      input: "10.1000/demo",
    });

    expect(parseClient.createParseFulltextV2Task).not.toHaveBeenCalled();
    expect(result).toEqual({
      success: false,
      requiresBrowserCapture: undefined,
      requiresHelper: undefined,
      requiresUpload: true,
      error: "PDF upload required",
    });
  });

  it("normalizes legacy helper failures to browser-capture failures for the extension UI", async () => {
    executeAction.mockResolvedValue({
      success: false,
      requiresHelper: true,
      error: "Open the article page and retry browser capture.",
    });

    const parseClient = {
      createParseFulltextV2Task: vi.fn(),
    };

    const { executeSsotActionSequence } = await import("../src/lib/ssot-route");
    const result = await executeSsotActionSequence(parseClient, buildRoutePlan(), {
      input: "10.1000/demo",
    });

    expect(parseClient.createParseFulltextV2Task).not.toHaveBeenCalled();
    expect(result).toEqual({
      success: false,
      requiresBrowserCapture: true,
      requiresHelper: true,
      requiresUpload: undefined,
      error: "Open the article page and retry browser capture.",
    });
  });
});
