import type {
  EmailStartRequest,
  EmailVerifyRequest,
  ParseTaskRequest,
  TaskRecord,
  TranslateTaskRequest
} from "@mdtero/shared";

export interface ApiClientSettings {
  apiBaseUrl: string;
  token?: string;
}

export interface UploadedParseTaskPayload {
  xmlFile: Blob;
  filename?: string;
  sourceDoi?: string;
  sourceInput?: string;
}

export function createApiClient(
  getSettings: () => Promise<ApiClientSettings>
) {
  async function request(path: string, init?: RequestInit) {
    const settings = await getSettings();
    const headers = new Headers(init?.headers ?? {});
    if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (settings.token) {
      headers.set("Authorization", `Bearer ${settings.token}`);
    }
    const response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers
    });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }
    return response;
  }

  function extractFilename(contentDisposition: string | null, fallback: string) {
    const match = contentDisposition?.match(/filename="([^"]+)"/i);
    return match?.[1] ?? fallback;
  }

  return {
    startEmailAuth(payload: EmailStartRequest) {
      return request("/auth/email/start", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    verifyEmailAuth(payload: EmailVerifyRequest) {
      return request("/auth/email/verify", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    getUsage() {
      return request("/me/usage").then((response) => response.json());
    },
    getMyTasks() {
      return request("/me/tasks").then((response) => response.json() as Promise<{items: TaskRecord[]}>);
    },
    createParseTask(payload: ParseTaskRequest) {
      return request("/tasks/parse", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    createUploadedParseTask(payload: UploadedParseTaskPayload) {
      const body = new FormData();
      body.set("xml_file", payload.xmlFile, payload.filename ?? "paper.xml");
      if (payload.sourceDoi) {
        body.set("source_doi", payload.sourceDoi);
      }
      if (payload.sourceInput) {
        body.set("source_input", payload.sourceInput);
      }
      return request("/tasks/parse-upload", {
        method: "POST",
        body
      }).then((response) => response.json());
    },
    createTranslateTask(payload: TranslateTaskRequest) {
      return request("/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    getTask(taskId: string) {
      return request(`/tasks/${taskId}`).then((response) => response.json() as Promise<TaskRecord>);
    },
    downloadArtifact(taskId: string, artifact: string) {
      return request(`/tasks/${taskId}/download/${artifact}`).then(async (response) => ({
        blob: await response.blob(),
        filename: extractFilename(response.headers.get("Content-Disposition"), `${artifact}.bin`),
        mediaType: response.headers.get("Content-Type") ?? "application/octet-stream"
      }));
    }
  };
}
