import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TaskRecord } from "@mdtero/shared";
import { createApiClient } from "../src/lib/api";

describe("createApiClient", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("calls the configured private API base URL", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await client.getUsage();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/me/usage",
      expect.objectContaining({
        headers: expect.any(Headers)
      })
    );
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer demo-token");
    expect(headers.get("X-Client-Channel")).toBe("extension");
    expect(headers.get("X-Client-Version")).toBe("extension-dev");
  });

  it("downloads task artifacts with filename metadata", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response("zip-data", {
        status: 200,
        headers: {
          "Content-Disposition": 'attachment; filename="zhou2025performance.zip"',
          "Content-Type": "application/zip"
        }
      })
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const artifact = await client.downloadArtifact("task-123", "paper_bundle");

    expect(artifact.filename).toBe("zhou2025performance.zip");
    expect(artifact.mediaType).toBe("application/zip");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/tasks/task-123/download/paper_bundle",
      expect.any(Object)
    );
  });

  it("logs in with password through the dedicated auth route", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ token: "password-token" }), { status: 200 })
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000"
      })
    );

    const result = await client.loginWithPassword({
      email: "reader@example.com",
      password: "Reader2026"
    });

    expect(result.token).toBe("password-token");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/auth/password/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          email: "reader@example.com",
          password: "Reader2026"
        })
      })
    );
  });

  it("falls back to artifact-specific filenames when download headers omit one", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response("# translated", {
        status: 200,
        headers: {
          "Content-Type": "text/markdown"
        }
      })
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const artifact = await client.downloadArtifact("task-123", "translated_md");

    expect(artifact.filename).toBe("translated.md");
    expect(artifact.mediaType).toBe("text/markdown");
  });

  it("prefers task artifact metadata filenames when download headers omit one", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response("# parsed", {
        status: 200,
        headers: {
          "Content-Type": "text/markdown"
        }
      })
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const artifact = await client.downloadArtifact("task-123", "paper_md", "zhou2025performance.md");

    expect(artifact.filename).toBe("zhou2025performance.md");
    expect(artifact.mediaType).toBe("text/markdown");
  });

  it("exposes the shared client-config route for extension upgrade checks", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ api_version: "2026-03-22" }), { status: 200 }));

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const config = await client.getClientConfig();

    expect(config.api_version).toBe("2026-03-22");
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("X-Client-Version")).toBe("extension-dev");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/client-config",
      expect.objectContaining({
        headers: expect.any(Headers)
      })
    );
  });

  it("uploads local XML as multipart parse input", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ task_id: "task-upload", status: "queued" }), { status: 200 }));

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await client.createUploadedParseTask({
      xmlFile: new Blob(["<xml />"], { type: "application/xml" }),
      filename: "paper.xml",
      sourceDoi: "10.1016/j.energy.2026.140192",
      sourceInput: "10.1016/j.energy.2026.140192"
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/tasks/parse-upload",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData)
      })
    );
  });

  it("uploads helper-first payloads through the v2 parse routes", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ task_id: "task-v2", status: "queued" }), { status: 200 }));

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await client.createParseFulltextV2Task({
      fulltextFile: new Blob(["<html></html>"], { type: "text/html" }),
      filename: "paper.html",
      sourceInput: "https://example.org/paper"
    });
    await client.createParseHelperBundleV2Task({
      helperBundleFile: new Blob(["zip"], { type: "application/zip" }),
      filename: "helper-bundle.zip",
      sourceDoi: "10.1016/j.energy.2026.140192",
      pdfEngine: "grobid"
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/tasks/parse-fulltext-v2",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData)
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8000/tasks/parse-helper-bundle-v2",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData)
      })
    );

    const fulltextBody = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(fulltextBody.get("fulltext_file")).toBeTruthy();
    expect(fulltextBody.get("source_input")).toBe("https://example.org/paper");

    const helperBundleBody = fetchMock.mock.calls[1]?.[1]?.body as FormData;
    expect(helperBundleBody.get("helper_bundle")).toBeTruthy();
    expect(helperBundleBody.get("source_doi")).toBe("10.1016/j.energy.2026.140192");
    expect(helperBundleBody.get("pdf_engine")).toBe("grobid");
  });

  it("loads parser-v2 shadow diagnostics through the authenticated diagnostics route", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          aggregate: { connectors_total: 5, enabled_total: 1 },
          connectors: [{ connector: "springer_subscription_connector", enabled: true, priority: 10 }]
        }),
        { status: 200 }
      )
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const diagnostics = await client.getParserV2ShadowDiagnostics();

    expect(diagnostics.aggregate.enabled_total).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/diagnostics/parser-v2/shadow",
      expect.objectContaining({
        headers: expect.any(Headers)
      })
    );
  });

  it("loads source connectivity environment diagnostics through the authenticated diagnostics route", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          browser_bridge: { dependency: "browser_bridge", status: "ready", reason_codes: [], details: {} },
          local_helper: { dependency: "local_helper", status: "ready", reason_codes: [], details: {} },
          credentials: []
        }),
        { status: 200 }
      )
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const diagnostics = await client.getSourceConnectivityEnvironmentSummary();

    expect(diagnostics.local_helper.status).toBe("ready");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/diagnostics/source-connectivity/environment",
      expect.objectContaining({
        headers: expect.any(Headers)
      })
    );
  });

  it("posts source connectivity explain requests through the authenticated diagnostics route", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          input_kind: "doi",
          input_value: "10.1002/sam.11700",
          route_summary: {
            top_connector: "wiley_tdm",
            route_kind: "html_helper_first",
            fallback_chain: ["pdf"]
          },
          access_summary: { availability: "user_entitled" },
          environment_summary: {
            browser_bridge: { dependency: "browser_bridge", status: "ready", reason_codes: [], details: {} },
            local_helper: { dependency: "local_helper", status: "ready", reason_codes: [], details: {} },
            credentials: []
          },
          provider_probe: {
            status: "blocked",
            reason_codes: ["route_ready_waiting_for_user_capture"],
            attribution: "user_environment",
            details: {}
          },
          recommended_next_step: {
            action: "open_in_edge_and_capture",
            message: "Open the article in Edge and retry capture."
          }
        }),
        { status: 200 }
      )
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const diagnostics = await client.explainSourceConnectivity({
      input: "10.1002/sam.11700"
    });

    expect(diagnostics.route_summary.top_connector).toBe("wiley_tdm");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/diagnostics/source-connectivity/explain",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          input: "10.1002/sam.11700"
        }),
        headers: expect.any(Headers)
      })
    );
  });

  it("surfaces backend detail messages for failed requests", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Elsevier and ScienceDirect inputs must be acquired locally first." }), {
        status: 400,
        headers: {
          "Content-Type": "application/json"
        }
      })
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await expect(
      client.createParseTask({ input: "10.1016/j.energy.2026.140192" })
    ).rejects.toThrow("Elsevier and ScienceDirect inputs must be acquired locally first.");
  });

  it("refuses parse requests when the user is not signed in", async () => {
    const fetchMock = vi.mocked(fetch);

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000"
      })
    );

    await expect(
      client.createParseTask({ input: "10.1000/example" })
    ).rejects.toThrow("Sign in required");
    await expect(
      client.createUploadedParseTask({
        xmlFile: new Blob(["<xml />"], { type: "application/xml" }),
        filename: "paper.xml",
        sourceInput: "10.1000/example"
      })
    ).rejects.toThrow("Sign in required");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns typed task metadata for history and detail endpoints", async () => {
    const fetchMock = vi.mocked(fetch);
    const fetchResponses = [
      new Response(
        JSON.stringify({
          items: [
            {
              task_id: "task-1",
              status: "succeeded",
              task_kind: "parse",
              input_summary: "10.1000/example",
              stage: "completed",
              progress_percent: 100,
              created_at: "2026-03-16T12:00:00+00:00",
              result: null,
              error_code: null,
              error_message: null
            }
          ]
        }),
        { status: 200 }
      ),
      new Response(
        JSON.stringify({
          task_id: "task-2",
          status: "running",
          task_kind: "translate",
          input_summary: "zhou2025performance",
          stage: "translating",
          progress_percent: null,
          created_at: "2026-03-16T12:05:00+00:00",
          result: null,
          error_code: null,
          error_message: null
        }),
        { status: 200 }
      )
    ];
    fetchMock.mockImplementation(async () => fetchResponses.shift() as Response);

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const history = await client.getMyTasks();
    const firstTask: TaskRecord = history.items[0];
    const detail: TaskRecord = await client.getTask("task-2");

    expect(firstTask.task_kind).toBe("parse");
    expect(firstTask.input_summary).toBe("10.1000/example");
    expect(firstTask.stage).toBe("completed");
    expect(firstTask.progress_percent).toBe(100);
    expect(firstTask.created_at).toBe("2026-03-16T12:00:00+00:00");
    expect(detail.task_kind).toBe("translate");
    expect(detail.input_summary).toBe("zhou2025performance");
    expect(detail.stage).toBe("translating");
    expect(detail.progress_percent).toBeNull();
    expect(detail.created_at).toBe("2026-03-16T12:05:00+00:00");
  });
});
