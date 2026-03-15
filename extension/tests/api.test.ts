import { beforeEach, describe, expect, it, vi } from "vitest";

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

  it("creates translation tasks against the private API", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ task_id: "task-456", status: "queued" }), { status: 200 }));

    const client = createApiClient(() =>
      Promise.resolve({
        apiBaseUrl: "http://127.0.0.1:8000",
        token: "demo-token"
      })
    );

    await client.createTranslateTask({
      source_markdown_path: "/tmp/zhou2025performance/paper.md",
      target_language: "zh",
      mode: "standard"
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/tasks/translate",
      expect.objectContaining({
        method: "POST"
      })
    );
  });
});
