import type {
  LocalizedPublisherCapabilityEntry,
  PublisherCapabilityFallback,
  PublisherCapabilityLanguage,
  PublisherCapabilityStatus
} from "@mdtero/shared";

export type CapabilityHelperState = "connected" | "busy" | "unavailable" | "disconnected";
export type CapabilityReadiness =
  | "ready"
  | "needs_helper"
  | "needs_api_key"
  | "browser_required"
  | "institution_access";

export interface CapabilityContext {
  helperState: CapabilityHelperState;
  hasElsevierApiKey: boolean;
  hasSpringerOpenAccessApiKey: boolean;
}

const STATUS_LABELS: Record<PublisherCapabilityStatus, Record<PublisherCapabilityLanguage, string>> = {
  stable: { en: "Stable", zh: "稳定" },
  demo: { en: "Demo", zh: "演示" },
  experimental: { en: "Experimental", zh: "实验" }
};

const FALLBACK_LABELS: Record<PublisherCapabilityFallback, Record<PublisherCapabilityLanguage, string>> = {
  pdf: { en: "PDF", zh: "PDF" },
  browser_page_capture: { en: "Browser page capture", zh: "浏览器页面抓取" },
  no_fallback_yet: { en: "No fallback yet", zh: "暂未提供兜底" }
};

const READINESS_LABELS: Record<CapabilityReadiness, Record<PublisherCapabilityLanguage, string>> = {
  ready: { en: "Ready now", zh: "现在可用" },
  needs_helper: { en: "Install helper", zh: "需要安装 helper" },
  needs_api_key: { en: "Add API key", zh: "需要填写 API key" },
  browser_required: { en: "Open in browser when needed", zh: "需要时在浏览器中打开" },
  institution_access: { en: "Institution sign-in may be required", zh: "可能需要机构登录" }
};

export function formatCapabilityStatusLabel(
  status: PublisherCapabilityStatus,
  language: PublisherCapabilityLanguage
) {
  return STATUS_LABELS[status][language];
}

export function formatCapabilityFallbacks(
  fallbacks: PublisherCapabilityFallback[],
  language: PublisherCapabilityLanguage
) {
  return fallbacks.map((item) => FALLBACK_LABELS[item][language]).join(" → ");
}

function hasRequiredApiKey(entry: LocalizedPublisherCapabilityEntry, context: CapabilityContext) {
  if (!entry.requiresApiKey) {
    return true;
  }
  if (entry.id === "elsevier") {
    return context.hasElsevierApiKey;
  }
  if (entry.id === "springer_oa") {
    return context.hasSpringerOpenAccessApiKey;
  }
  return false;
}

export function resolveCapabilityReadiness(
  entry: LocalizedPublisherCapabilityEntry,
  context: CapabilityContext
): CapabilityReadiness {
  if (context.helperState !== "connected" && context.helperState !== "busy") {
    return "needs_helper";
  }
  if (!hasRequiredApiKey(entry, context)) {
    return "needs_api_key";
  }
  if (entry.requiresBrowser) {
    return "browser_required";
  }
  if (entry.mayNeedInstitutionAccess) {
    return "institution_access";
  }
  return "ready";
}

export function describeCapabilityReadiness(
  readiness: CapabilityReadiness,
  language: PublisherCapabilityLanguage
) {
  return READINESS_LABELS[readiness][language];
}
