import type {
  EmailStartRequest,
  EmailVerifyRequest,
  ParseTaskRequest,
  ParseTaskResponse,
  ParseFulltextV2Request,
  ParseHelperBundleV2Request,
  ParserV2ShadowDiagnostics,
  PasswordLoginRequest,
  TaskRecord,
  TranslateTaskRequest
} from "@mdtero/shared";

export interface ApiClientSettings {
  apiBaseUrl: string;
  token?: string;
}

export interface ClientConfigResponse {
  api_version: string;
  skills?: {
    manifest_url?: string;
    install_doc_url?: string;
    recommended_check_interval_hours?: number;
  };
}

export interface UploadedParseTaskPayload {
  xmlFile: Blob;
  filename?: string;
  sourceDoi?: string;
  sourceInput?: string;
}

function buildHelperFirstParseBody(params: {
  fileField: "fulltext_file" | "helper_bundle";
  file: Blob;
  filename: string;
  sourceDoi?: string;
  sourceInput?: string;
}) {
  const body = new FormData();
  body.set(params.fileField, params.file, params.filename);
  if (params.sourceDoi) {
    body.set("source_doi", params.sourceDoi);
  }
  if (params.sourceInput) {
    body.set("source_input", params.sourceInput);
  }
  return body;
}

function fallbackArtifactFilename(artifact: string) {
  if (artifact === "paper_bundle") return "paper_bundle.zip";
  if (artifact === "paper_md") return "paper.md";
  if (artifact === "paper_pdf") return "paper.pdf";
  if (artifact === "paper_xml") return "paper.xml";
  if (artifact === "translated_md") return "translated.md";
  return `${artifact}.bin`;
}

export function createApiClient(
  getSettings: () => Promise<ApiClientSettings>
) {
  async function requireSignedInSettings() {
    const settings = await getSettings();
    if (!settings.token) {
      throw new Error("Sign in required before parsing or translating.");
    }
    return settings;
  }

  function getRuntimeVersion() {
    const runtimeVersion = globalThis.chrome?.runtime?.getManifest?.().version;
    return runtimeVersion ? `extension-${runtimeVersion}` : "extension-dev";
  }

  async function request(path: string, init?: RequestInit, options?: { requireAuth?: boolean }) {
    const settings = options?.requireAuth ? await requireSignedInSettings() : await getSettings();
    const headers = new Headers(init?.headers ?? {});
    if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (settings.token) {
      headers.set("Authorization", `Bearer ${settings.token}`);
    }
    headers.set("X-Client-Channel", "extension");
    headers.set("X-Client-Version", getRuntimeVersion());
    const response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers
    });
    if (!response.ok) {
      const detail = await response
        .clone()
        .json()
        .then((payload) => {
          if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
            return payload.detail.trim();
          }
          return "";
        })
        .catch(() => "");
      throw new Error(detail || `API request failed: ${response.status}`);
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
    loginWithPassword(payload: PasswordLoginRequest) {
      return request("/auth/password/login", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    getUsage() {
      return request("/me/usage", undefined, { requireAuth: true }).then((response) => response.json());
    },
    getParserV2ShadowDiagnostics() {
      return request("/diagnostics/parser-v2/shadow", undefined, { requireAuth: true }).then(
        (response) => response.json() as Promise<ParserV2ShadowDiagnostics>
      );
    },
    getClientConfig() {
      return request("/client-config").then((response) => response.json() as Promise<ClientConfigResponse>);
    },
    getMyTasks() {
      return request("/me/tasks", undefined, { requireAuth: true }).then((response) => response.json() as Promise<{items: TaskRecord[]}>);
    },
    createParseTask(payload: ParseTaskRequest) {
      return request("/tasks/parse", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json() as Promise<ParseTaskResponse>);
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
      }, { requireAuth: true }).then((response) => response.json() as Promise<ParseTaskResponse>);
    },
    createParseFulltextV2Task(payload: ParseFulltextV2Request) {
      const body = buildHelperFirstParseBody({
        fileField: "fulltext_file",
        file: payload.fulltextFile,
        filename: payload.filename ?? "paper.fulltext",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      return request("/tasks/parse-fulltext-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json() as Promise<ParseTaskResponse>);
    },
    createParseHelperBundleV2Task(payload: ParseHelperBundleV2Request) {
      const body = buildHelperFirstParseBody({
        fileField: "helper_bundle",
        file: payload.helperBundleFile,
        filename: payload.filename ?? "helper-bundle.zip",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      if (payload.pdfEngine) {
        body.set("pdf_engine", payload.pdfEngine);
      }
      return request("/tasks/parse-helper-bundle-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json() as Promise<ParseTaskResponse>);
    },
    createTranslateTask(payload: TranslateTaskRequest) {
      return request("/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    getTask(taskId: string) {
      return request(`/tasks/${taskId}`, undefined, { requireAuth: true }).then((response) => response.json() as Promise<TaskRecord>);
    },
    downloadArtifact(taskId: string, artifact: string) {
      return request(`/tasks/${taskId}/download/${artifact}`, undefined, { requireAuth: true }).then(async (response) => ({
        blob: await response.blob(),
        filename: extractFilename(response.headers.get("Content-Disposition"), fallbackArtifactFilename(artifact)),
        mediaType: response.headers.get("Content-Type") ?? "application/octet-stream"
      }));
    }
  };
}
