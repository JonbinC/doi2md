export const DEFAULT_API_BASE_URL = "https://api.mdtero.com";

export interface ParseTaskRequest {
  input: string;
}

export interface ParseTaskResponse {
  task_id: string;
  status: string;
  task_api?: string;
  download_api?: string;
  preferred_artifact?: string;
  selected_provider?: string | null;
  parser_strategy?: string | null;
  reason_code?: string | null;
  action_hint?: string | null;
  next_commands?: string[];
}

export interface RawUploadTaskRequest {
  rawFile: Blob;
  filename?: string;
  sourceDoi?: string;
  sourceInput?: string;
}

export type ActionType =
  | "capture_current_tab_html"
  | "native_arxiv_parse"
  | "fetch_structured_xml"
  | "fetch_elsevier_xml"
  | "fetch_wiley_tdm_pdf"
  | "fetch_springer_pdf"
  | "fetch_remote_html"
  | "fetch_epub_asset"
  | "fetch_oa_repository"
  | "fetch_browser_source"
  | "fallback_pdf_parse"
  | "server_parse";

export interface AcquisitionCandidate {
  connector: string;
  priority?: number;
  access?: "open" | "licensed" | "unknown";
  format?: string;
  url?: string;
  html_url?: string;
  pdf_url?: string;
  epub_url?: string;
  handoff?: string;
  tier?: string;
  reason?: string;
  requires_api_key?: boolean;
}

export interface ExtensionRouteRequest {
  input: string;
  page_url?: string;
  page_title?: string;
}

export interface ExtensionRouteResponse {
  input_kind: string;
  input_value: string;
  top_connector: string;
  route_kind: string;
  acquisition_mode: string;
  requires_browser_capture?: boolean;
  allows_current_tab: boolean;
  action_sequence: string[];
  acceptance_rules: Record<string, unknown>;
  fail_closed: boolean;
  user_message?: string;
  matched_connectors: string[];
  provider_id?: string;
  preferred_format?: string;
  format_chain?: string[];
  publisher_family?: string;
  metadata_source?: string;
  access_decision?: "open" | "subscription_or_user_entitled" | "unknown";
  best_oa_url?: string;
  acquisition_candidates?: AcquisitionCandidate[];
  server_entrypoint?: string;
  upload_entrypoint?: string;
  action_hint?: string;
  route_planner_fallback?: boolean;
}

export interface ActionContext {
  input: string;
  tabId?: number;
  tabUrl?: string;
  tabTitle?: string;
}

export interface ActionResult {
  success: boolean;
  taskId?: string;
  rawArtifact?: Blob;
  filename?: string;
  sourceDoi?: string;
  error?: string;
  nextCommand?: string;
  requiresBrowserCapture?: boolean;
  requiresUpload?: boolean;
}

export interface TranslateTaskRequest {
  source_markdown_path: string;
  target_language: string;
  mode: string;
}

export interface TaskArtifactDescriptor {
  path?: string;
  filename?: string;
  media_type?: string;
}

export interface TaskDownloadArtifactDescriptor {
  artifact: string;
  filename?: string;
  media_type?: string;
}

export interface TaskResult {
  preferred_artifact?: string;
  artifacts?: Record<string, TaskArtifactDescriptor>;
  download_artifacts?: TaskDownloadArtifactDescriptor[];
  reason_code?: string | null;
  action_hint?: string | null;
  next_commands?: string[];
  translation_attempts?: TranslationProviderAttempt[];
  warning_code?: string;
  warning_message?: string;
}

export interface TranslationProviderAttempt {
  provider?: string | null;
  status?: string | null;
  reason_code?: string | null;
  provider_error_code?: string | null;
  provider_status_code?: number | null;
  retryable?: boolean | null;
  message?: string | null;
}

export interface TaskRecord {
  task_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  task_api?: string;
  download_api?: string;
  preferred_artifact?: string;
  task_kind: "parse" | "translate";
  paper_input?: string | null;
  input_summary: string;
  stage: "queued" | "parsing" | "translating" | "completed" | "failed";
  progress_percent?: number | null;
  created_at: string;
  result?: TaskResult | null;
  reason_code?: string | null;
  action_hint?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  next_commands?: string[];
}

export type CheckoutProductCode =
  | "standard"
  | "pro"
  | "translation_addon"
  | "recharge_small"
  | "recharge_medium"
  | "recharge_large";

export interface CheckoutSessionRequest {
  product_code: CheckoutProductCode;
  currency: "cny" | "usd";
  tier?: "standard" | "pro";
}

export interface CheckoutSessionResponse {
  id: string;
  url: string;
}
