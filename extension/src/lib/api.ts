import type {
  ParseTaskRequest,
  ParseTaskResponse,
  RawUploadTaskRequest,
  TaskRecord,
  TranslateTaskRequest,
  ExtensionRouteRequest,
  ExtensionRouteResponse
} from "@mdtero/shared";
import { normalizeCliHandoffCommand } from "./cli-handoff";
import { redactSensitiveText } from "./redact";

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
  xmlFile?: Blob;
  paperFile?: Blob;
  filename?: string;
  sourceDoi?: string;
  sourceInput?: string;
}

function buildFulltextUploadBody(params: {
  file: Blob;
  filename: string;
  sourceDoi?: string;
  sourceInput?: string;
}) {
  const body = new FormData();
  body.set("paper_file", params.file, params.filename);
  if (params.sourceDoi) {
    body.set("source_doi", params.sourceDoi);
  }
  if (params.sourceInput) {
    body.set("source_input", params.sourceInput);
  }
  return body;
}

function fallbackArtifactFilename(artifact: string, preferredFilename?: string | null) {
  if (preferredFilename && preferredFilename.trim()) {
    return preferredFilename.trim();
  }
  if (artifact === "paper_bundle") return "paper_bundle.zip";
  if (artifact === "paper_md") return "paper.md";
  if (artifact === "paper_pdf") return "paper.pdf";
  if (artifact === "paper_xml") return "paper.xml";
  if (artifact === "translated_md") return "translated.md";
  return `${artifact}.bin`;
}

async function readErrorDetail(response: Response): Promise<string> {
  const payload = await response
    .clone()
    .json()
    .catch(() => null);
  return describeErrorPayload(payload);
}

function describeErrorPayload(payload: unknown): string {
  if (!payload || typeof payload !== "object") {
    return "";
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (!detail || typeof detail !== "object") {
    return "";
  }
  const parts: string[] = [];
  const record = detail as Record<string, unknown>;
  const message = firstString(record.error_message, record.message, record.detail);
  const reasonCode = firstString(record.reason_code, record.error_code);
  const actionHint = firstString(record.action_hint);
  const nextCommands = nextCommandsFromErrorDetail(record.next_commands);
  if (message) parts.push(message);
  if (reasonCode) parts.push(`Reason: ${reasonCode}`);
  if (actionHint) parts.push(`Next: ${actionHint}`);
  if (nextCommands.length === 1) {
    parts.push(`Command: ${nextCommands[0]}`);
  } else if (nextCommands.length > 1) {
    parts.push(`Commands: ${nextCommands.map((command, index) => `${index + 1}. ${command}`).join(" ")}`);
  }
  return redactSensitiveText(parts.join(" "));
}

function nextCommandsFromErrorDetail(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const commands = value
    .map((command) => normalizeCliHandoffCommand(String(command || "").trim()))
    .filter((command) => command.length > 0);
  return Array.from(new Set(commands));
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
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
      const detail = await readErrorDetail(response);
      throw new Error(detail || `API request failed: ${response.status}`);
    }
    return response;
  }

  function extractFilename(contentDisposition: string | null, fallback: string) {
    const match = contentDisposition?.match(/filename="([^"]+)"/i);
    return match?.[1] ?? fallback;
  }

  return {
    getUsage() {
      return request("/me/usage", undefined, { requireAuth: true }).then((response) => response.json());
    },
    getClientConfig() {
      return request("/client-config").then((response) => response.json() as Promise<ClientConfigResponse>);
    },
    getMyTasks() {
      return request("/me/tasks", undefined, { requireAuth: true }).then((response) => response.json() as Promise<{items: TaskRecord[]}>);
    },
    createParseTask(payload: ParseTaskRequest) {
      return request("/api/v1/tasks/parse", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json() as Promise<ParseTaskResponse>);
    },
    createUploadedParseTask(payload: UploadedParseTaskPayload) {
      const body = new FormData();
      const upload = payload.paperFile ?? payload.xmlFile;
      if (!upload) {
        throw new Error("No file was provided for upload.");
      }
      body.set("paper_file", upload, payload.filename ?? "paper.fulltext");
      if (payload.sourceDoi) {
        body.set("source_doi", payload.sourceDoi);
      }
      if (payload.sourceInput) {
        body.set("source_input", payload.sourceInput);
      }
      return request("/api/v1/tasks/upload", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json() as Promise<ParseTaskResponse>);
    },
    createRawUploadTask(payload: RawUploadTaskRequest) {
      const body = buildFulltextUploadBody({
        file: payload.rawFile,
        filename: payload.filename ?? "paper.fulltext",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      return request("/api/v1/tasks/upload", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json() as Promise<ParseTaskResponse>);
    },
    createTranslateTask(payload: TranslateTaskRequest) {
      return request("/api/v1/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    getTask(taskId: string) {
      return request(`/api/v1/tasks/${taskId}`, undefined, { requireAuth: true }).then((response) => response.json() as Promise<TaskRecord>);
    },
    downloadArtifact(taskId: string, artifact: string, preferredFilename?: string | null) {
      return request(`/api/v1/tasks/${taskId}/download/${artifact}`, undefined, { requireAuth: true }).then(async (response) => ({
        blob: await response.blob(),
        filename: extractFilename(
          response.headers.get("Content-Disposition"),
          fallbackArtifactFilename(artifact, preferredFilename)
        ),
        mediaType: response.headers.get("Content-Type") ?? "application/octet-stream"
      }));
    }
  };
}

// Router SSOT API functions

export function createRouterSSOTClient(
  getSettings: () => Promise<ApiClientSettings>
) {
  async function requireSignedInSettings() {
    const settings = await getSettings();
    if (!settings.token) {
      throw new Error("Sign in required before fetching route plan.");
    }
    return settings;
  }

  function getRuntimeVersion() {
    const runtimeVersion = globalThis.chrome?.runtime?.getManifest?.().version;
    return runtimeVersion ? `extension-${runtimeVersion}` : "extension-dev";
  }

  async function request(path: string, init?: RequestInit) {
    const settings = await requireSignedInSettings();
    const headers = new Headers(init?.headers ?? {});
    
    if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    
    headers.set("Authorization", `Bearer ${settings.token}`);
    headers.set("X-Client-Channel", "extension");
    headers.set("X-Client-Version", getRuntimeVersion());

    const response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers,
    });

    if (response.status === 404 && path === "/api/v1/route") {
      return new Response(JSON.stringify({
        input_kind: "unknown",
        input_value: "",
        top_connector: "server_parse",
        route_kind: "server",
        acquisition_mode: "server_parse",
        requires_browser_capture: false,
        allows_current_tab: false,
        action_sequence: ["server_parse"],
        acceptance_rules: {},
        fail_closed: true,
        matched_connectors: ["server_parse"],
        requires_raw_upload: false,
        action_hint: "The backend route planner is not available; submit the DOI or URL directly to /api/v1/tasks/parse.",
        server_entrypoint: "/api/v1/tasks/parse",
        upload_entrypoint: "/api/v1/tasks/upload",
        route_planner_fallback: true
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    if (!response.ok) {
      const detail = await readErrorDetail(response);
      throw new Error(detail || `API request failed: ${response.status}`);
    }

    return response;
  }

  return {
    /**
     * Fetch canonical route plan from backend SSOT.
     * Extension should use this instead of local routing rules.
     */
    fetchRoutePlan(payload: ExtensionRouteRequest) {
      return request("/api/v1/route", {
        method: "POST",
        body: JSON.stringify(payload),
      }).then((response) => response.json() as Promise<ExtensionRouteResponse>);
    },
  };
}

export function routeRequiresBrowserCapture(routePlan: ExtensionRouteResponse): boolean {
  return Boolean(routePlan.requires_browser_capture);
}

export function routeAllowsCurrentTabCapture(routePlan: ExtensionRouteResponse): boolean {
  return routePlan.allows_current_tab;
}
