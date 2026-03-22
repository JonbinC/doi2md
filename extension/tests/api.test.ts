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
          progress_percent: 50,
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
    expect(detail.progress_percent).toBe(50);
    expect(detail.created_at).toBe("2026-03-16T12:05:00+00:00");
  });
});
