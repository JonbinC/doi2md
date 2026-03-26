export const DEFAULT_API_BASE_URL = "https://api.mdtero.com";

export interface EmailStartRequest {
  email: string;
}

export interface EmailVerifyRequest {
  email: string;
  code: string;
  preferred_currency?: "cny" | "usd";
}

export interface PasswordRegisterRequest {
  email: string;
  password: string;
  preferred_currency?: "cny" | "usd";
}

export interface PasswordLoginRequest {
  email: string;
  password: string;
  preferred_currency?: "cny" | "usd";
}

export interface PasswordForgotRequest {
  email: string;
}

export interface PasswordResetRequest {
  token: string;
  password: string;
}

export interface ParseTaskRequest {
  input: string;
}

export interface ParseTaskResponse {
  task_id: string;
  status: string;
}

export interface ParseFulltextV2Request {
  fulltextFile: Blob;
  filename?: string;
  sourceDoi?: string;
  sourceInput?: string;
}

export type PdfEngine = "grobid" | "docling" | "mineru";

export interface ParseHelperBundleV2Request {
  helperBundleFile: Blob;
  filename?: string;
  sourceDoi?: string;
  sourceInput?: string;
  pdfEngine?: PdfEngine;
}

export interface TranslateTaskRequest {
  source_markdown_path: string;
  target_language: string;
  mode: string;
}

export interface TaskArtifactDescriptor {
  path: string;
  filename: string;
  media_type: string;
}

export interface TaskResult {
  preferred_artifact?: string;
  artifacts?: Record<string, TaskArtifactDescriptor>;
  warning_code?: string;
  warning_message?: string;
}

export interface TaskRecord {
  task_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  task_kind: "parse" | "translate";
  paper_input?: string | null;
  input_summary: string;
  stage: "queued" | "parsing" | "translating" | "completed" | "failed";
  progress_percent?: number | null;
  created_at: string;
  result?: TaskResult | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface ParserV2ShadowConnectorSnapshot {
  connector: string;
  preset_available?: boolean;
  flag?: string | null;
  enabled: boolean;
  entrypoint?: string | null;
  acquisition_mode?: string | null;
  priority: number;
}

export interface ParserV2ShadowDiagnostics {
  aggregate: {
    connectors_total: number;
    enabled_total: number;
  };
  connectors: ParserV2ShadowConnectorSnapshot[];
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
