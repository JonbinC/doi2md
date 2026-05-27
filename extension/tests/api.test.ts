import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TaskRecord } from "@mdtero/shared";
import { MdteroApiError, createApiClient, createRouterSSOTClient, isMdteroApiError } from "../src/lib/api";

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
      "http://127.0.0.1:8000/api/v1/tasks/task-123/download/paper_bundle",
      expect.any(Object)
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

  it("uploads local XML as v1 multipart parse input", async () => {
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
      "http://127.0.0.1:8000/api/v1/tasks/upload",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData)
      })
    );
  });

  it("surfaces v1 task endpoint failures without falling back to legacy task routes", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not Found" }), {
        status: 404,
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

    await expect(client.createParseTask({ input: "10.1000/demo" })).rejects.toThrow("Not Found");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8000/api/v1/tasks/parse", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("synthesizes a v1 server-parse route plan when v1 route is not deployed", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }));

    const client = createRouterSSOTClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    const route = await client.fetchRoutePlan({ input: "10.1000/demo" }) as any;

    expect(route.route_planner_fallback).toBe(true);
    expect(route.acquisition_mode).toBe("server_parse");
    expect(route.action_sequence).toEqual(["server_parse"]);
    expect(route.server_entrypoint).toBe("/api/v1/tasks/parse");
    expect(route.upload_entrypoint).toBe("/api/v1/tasks/upload");
  });

  it("uploads raw artifact payloads through the v1 upload route", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ task_id: "task-v2", status: "queued" }), { status: 200 }));

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await client.createRawUploadTask({
      rawFile: new Blob(["<html></html>"], { type: "text/html" }),
      filename: "paper.html",
      sourceInput: "https://example.org/paper"
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/api/v1/tasks/upload",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData)
      })
    );

    const fulltextBody = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(fulltextBody.get("paper_file")).toBeTruthy();
    expect(fulltextBody.get("source_input")).toBe("https://example.org/paper");
  });

  it("surfaces backend detail messages for failed requests", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "This publisher source must be acquired with browser capture or local CLI credentials first." }), {
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
    ).rejects.toThrow("This publisher source must be acquired with browser capture or local CLI credentials first.");
  });

  it("redacts signed URLs and tokens from backend error detail", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({
        detail: {
          message: "MinerU failed at https://mineru.oss-cn-shanghai.aliyuncs.com/file.pdf?OSSAccessKeyId=abc&Signature=sig&security-token=tok",
          reason_code: "mineru_urlapi_timeout",
          action_hint: "Retry with Bearer voyage-secret-token or api_key=raw-key"
        }
      }), {
        status: 503,
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

    await expect(client.createParseTask({ input: "10.1000/demo" })).rejects.toThrow(
      /MinerU failed at \[redacted-url\]/
    );
    await expect(client.createParseTask({ input: "10.1000/demo" })).rejects.toThrow(
      /Bearer \[redacted\]/
    );
    await expect(client.createParseTask({ input: "10.1000/demo" })).rejects.not.toThrow(
      /Signature=sig|security-token=tok|voyage-secret-token|raw-key/
    );
  });

  it("surfaces structured backend reason codes, action hints, and next commands", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            error_message: "MinerU URL API timed out while fetching the uploaded PDF.",
            reason_code: "mineru_urlapi_timeout",
            action_hint: "Retry later or upload the PDF again from the browser extension.",
            next_commands: ["mdtero parse --file paper.pdf --wait --timeout 300 --json"]
          }
        }),
        {
          status: 504,
          headers: {
            "Content-Type": "application/json"
          }
        }
      )
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await expect(client.downloadArtifact("task-123", "paper_md")).rejects.toThrow(
      "MinerU URL API timed out while fetching the uploaded PDF. Reason: mineru_urlapi_timeout Next: Retry later or upload the PDF again from the browser extension. Command: mdtero parse --file paper.pdf --trace --wait --timeout 600 --json"
    );
  });

  it("preserves structured error metadata for extension handoff", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            error_message: "Artifact is not available for this failed task.",
            reason_code: "artifact_not_available",
            action_hint: "Inspect task status, then retry parse from the CLI.",
            next_commands: [
              "mdtero status task-123 --wait --timeout 300 --json",
              "mdtero parse --file paper.pdf --json"
            ]
          }
        }),
        {
          status: 404,
          headers: { "Content-Type": "application/json" }
        }
      )
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    let caught: unknown;
    try {
      await client.downloadArtifact("task-123", "paper_md");
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(MdteroApiError);
    expect(isMdteroApiError(caught)).toBe(true);
    expect((caught as MdteroApiError).status).toBe(404);
    expect((caught as MdteroApiError).reasonCode).toBe("artifact_not_available");
    expect((caught as MdteroApiError).actionHint).toBe("Inspect task status, then retry parse from the CLI.");
    expect((caught as MdteroApiError).nextCommands).toEqual([
      "mdtero status task-123 --wait --timeout 300 --json",
      "mdtero parse --file paper.pdf --trace --wait --timeout 600 --json"
    ]);
  });

  it("preserves multi-step backend next commands in extension error handoff", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            error_message: "Project RAG is not ready.",
            reason_code: "server_project_not_linked",
            action_hint: "Create and bind a server project before querying RAG.",
            next_commands: [
              "mdtero project create-server --json",
              "mdtero project ingest --json",
              "mdtero rag build --wait --json",
              "mdtero rag status --json"
            ]
          }
        }),
        {
          status: 409,
          headers: {
            "Content-Type": "application/json"
          }
        }
      )
    );

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await expect(client.getTask("task-123")).rejects.toThrow(
      "Project RAG is not ready. Reason: server_project_not_linked Next: Create and bind a server project before querying RAG. Commands: 1. mdtero project create-server --json 2. mdtero project ingest --json 3. mdtero rag build --wait --json 4. mdtero rag status --json"
    );
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
