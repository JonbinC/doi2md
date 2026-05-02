export type PublisherCapabilityLanguage = "en" | "zh";

export type PublisherCapabilityStatus = "stable" | "demo" | "experimental";
export type PublisherCapabilityRightsMode = "open" | "licensed";
export type PublisherCapabilityAcquisitionMode =
  | "direct_open_fulltext"
  | "official_api"
  | "browser_page_capture"
  | "hybrid";
export type PublisherCapabilityConfigureTarget =
  | "none"
  | "connector_keys"
  | "browser_assisted_sources"
  | "advanced_settings";
export type PublisherCapabilityFallback = "pdf" | "browser_page_capture" | "no_fallback_yet";
export type PublisherCapabilityPresentationGroup = "helper_only" | "api_key" | "browser_assisted";

export interface LocalizedText {
  en: string;
  zh: string;
}

export interface PublisherCapabilityLink {
  href: string;
  label: LocalizedText;
}

export interface PublisherCapabilityEntry {
  id: string;
  label: LocalizedText;
  variantOf: string;
  accessVariant: string;
  presentationGroup: PublisherCapabilityPresentationGroup;
  rightsMode: PublisherCapabilityRightsMode;
  acquisitionMode: PublisherCapabilityAcquisitionMode;
  requiresHelper: boolean;
  requiresBrowser: boolean;
  requiresApiKey: boolean;
  mayNeedInstitutionAccess: boolean;
  whatYouNeed: LocalizedText;
  howMdteroGetsIt: LocalizedText;
  configureTarget: PublisherCapabilityConfigureTarget;
  status: PublisherCapabilityStatus;
  fallbacks: PublisherCapabilityFallback[];
  validationRef: string;
  links: PublisherCapabilityLink[];
}

export interface PublisherCapabilityGroupDefinition {
  id: PublisherCapabilityPresentationGroup;
  label: LocalizedText;
  description: LocalizedText;
}

export interface LocalizedPublisherCapabilityGroup {
  id: PublisherCapabilityPresentationGroup;
  label: string;
  description: string;
  entries: Array<LocalizedPublisherCapabilityEntry>;
}

export interface LocalizedPublisherCapabilityEntry {
  id: string;
  label: string;
  variantOf: string;
  accessVariant: string;
  presentationGroup: PublisherCapabilityPresentationGroup;
  rightsMode: PublisherCapabilityRightsMode;
  acquisitionMode: PublisherCapabilityAcquisitionMode;
  requiresHelper: boolean;
  requiresBrowser: boolean;
  requiresApiKey: boolean;
  mayNeedInstitutionAccess: boolean;
  whatYouNeed: string;
  howMdteroGetsIt: string;
  configureTarget: PublisherCapabilityConfigureTarget;
  status: PublisherCapabilityStatus;
  fallbacks: PublisherCapabilityFallback[];
  validationRef: string;
  links: Array<{ href: string; label: string }>;
}

const GROUPS: PublisherCapabilityGroupDefinition[] = [
  {
    id: "helper_only",
    label: {
      en: "Built-in parsing",
      zh: "内置解析"
    },
    description: {
      en: "Use Mdtero's CLI/API and backend parser for supported open full-text sources.",
      zh: "使用 Mdtero CLI/API 和后端解析器处理受支持的开放全文来源。"
    }
  },
  {
    id: "api_key",
    label: {
      en: "API key",
      zh: "需要 API key"
    },
    description: {
      en: "Add the required publisher key when an official API route needs it.",
      zh: "官方 API 路线需要时，在设置里填写对应出版社 key。"
    }
  },
  {
    id: "browser_assisted",
    label: {
      en: "Extension upload/capture",
      zh: "扩展上传/采集"
    },
    description: {
      en: "Cloud routing decides the route; the extension only executes local upload/capture instructions when raw data must come from the user's machine.",
      zh: "云端路由决定链路；只有 raw data 必须来自用户机器时，扩展才执行本地上传/采集指令。"
    }
  }
];

function localize(text: LocalizedText, language: PublisherCapabilityLanguage) {
  return text[language];
}

function link(href: string, en: string, zh: string): PublisherCapabilityLink {
  return {
    href,
    label: { en, zh }
  };
}

export const PUBLISHER_CAPABILITY_MATRIX: PublisherCapabilityEntry[] = [
  {
    id: "arxiv",
    label: { en: "arXiv", zh: "arXiv" },
    variantOf: "arxiv",
    accessVariant: "open_repository",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Use Mdtero's normal CLI/API path.",
      zh: "使用 Mdtero 常规 CLI/API 路径。"
    },
    howMdteroGetsIt: {
      en: "Direct open full-text retrieval from arXiv.",
      zh: "直接从 arXiv 获取开放全文。"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-arxiv-html-live-1",
    links: []
  },
  {
    id: "pmc_europe_pmc",
    label: { en: "PMC / Europe PMC", zh: "PMC / Europe PMC" },
    variantOf: "pmc",
    accessVariant: "open_access",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Use Mdtero's normal CLI/API path.",
      zh: "使用 Mdtero 常规 CLI/API 路径。"
    },
    howMdteroGetsIt: {
      en: "Structured open-access full text from PMC routes.",
      zh: "通过 PMC 路线获取结构化开放全文。"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:pmc-open-access",
    links: []
  },
  {
    id: "plos",
    label: { en: "PLOS", zh: "PLOS" },
    variantOf: "plos",
    accessVariant: "open_access",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Use Mdtero's normal CLI/API path.",
      zh: "使用 Mdtero 常规 CLI/API 路径。"
    },
    howMdteroGetsIt: {
      en: "Structured open-access full text from PLOS.",
      zh: "从 PLOS 获取结构化开放全文。"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:plos-open-access",
    links: []
  },
  {
    id: "biorxiv_medrxiv",
    label: { en: "bioRxiv / medRxiv", zh: "bioRxiv / medRxiv" },
    variantOf: "biorxiv_medrxiv",
    accessVariant: "preprint_server",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Use Mdtero's normal CLI/API path.",
      zh: "使用 Mdtero 常规 CLI/API 路径。"
    },
    howMdteroGetsIt: {
      en: "Preprint full text from the source site.",
      zh: "从预印本源站获取全文。"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:biorxiv-medrxiv-open",
    links: []
  },
  {
    id: "chemrxiv",
    label: { en: "ChemRxiv", zh: "ChemRxiv" },
    variantOf: "chemrxiv",
    accessVariant: "preprint_server",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Use Mdtero's normal CLI/API path. Upload a PDF if the source cannot provide full text.",
      zh: "使用 Mdtero 常规 CLI/API 路径；源站无法提供全文时上传 PDF。"
    },
    howMdteroGetsIt: {
      en: "Preprint full text from ChemRxiv when available.",
      zh: "在可用时从 ChemRxiv 获取预印本全文。"
    },
    configureTarget: "none",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "checklist:chemrxiv-demo",
    links: []
  },
  {
    id: "mdpi",
    label: { en: "MDPI", zh: "MDPI" },
    variantOf: "mdpi",
    accessVariant: "publisher_open_page",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Use Mdtero's normal CLI/API path. Upload a PDF if the page route is unavailable.",
      zh: "使用 Mdtero 常规 CLI/API 路径；页面路线不可用时上传 PDF。"
    },
    howMdteroGetsIt: {
      en: "Open publisher full text from MDPI pages.",
      zh: "从 MDPI 页面获取开放全文。"
    },
    configureTarget: "none",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "checklist:mdpi-demo",
    links: []
  },
  {
    id: "elsevier",
    label: { en: "Elsevier", zh: "Elsevier" },
    variantOf: "elsevier",
    accessVariant: "api",
    presentationGroup: "api_key",
    rightsMode: "licensed",
    acquisitionMode: "official_api",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Add your Elsevier API key. Some papers may still require institutional access or a user-provided PDF.",
      zh: "填写 Elsevier API key。部分论文仍可能需要机构权限或用户上传 PDF。"
    },
    howMdteroGetsIt: {
      en: "Official full-text API for structured publisher retrieval.",
      zh: "通过官方全文 API 获取结构化出版社内容。"
    },
    configureTarget: "connector_keys",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "acceptance:elsevier-local-api",
    links: [
      link("https://dev.elsevier.com/", "Get Elsevier API key", "申请 Elsevier API key")
    ]
  },
  {
    id: "springer_oa",
    label: { en: "Springer Open Access", zh: "Springer Open Access" },
    variantOf: "springer",
    accessVariant: "open_access",
    presentationGroup: "api_key",
    rightsMode: "open",
    acquisitionMode: "hybrid",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Add your Springer OA API key for the best XML path. Upload a PDF if the source route is unavailable.",
      zh: "填写 Springer OA API key 可优先走 XML 路径；源站路线不可用时上传 PDF。"
    },
    howMdteroGetsIt: {
      en: "Springer OA XML when available, otherwise open full text.",
      zh: "优先获取 Springer OA XML，否则走开放全文。"
    },
    configureTarget: "connector_keys",
    status: "stable",
    fallbacks: ["browser_page_capture", "pdf"],
    validationRef: "acceptance:task-springer-s12011-04820-w",
    links: [
      link("https://dev.springernature.com/", "Get Springer Nature API key", "申请 Springer Nature API key")
    ]
  },
  {
    id: "springer_subscription",
    label: { en: "Springer subscription pages", zh: "Springer 订阅页面" },
    variantOf: "springer",
    accessVariant: "subscription_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Let Mdtero plan the route first. If the plan needs local raw data, use the extension to upload an authorized PDF or capture browser-context raw data.",
      zh: "先让 Mdtero 云端规划链路；如果计划需要本地 raw data，再用扩展上传授权 PDF 或采集浏览器上下文 raw data。"
    },
    howMdteroGetsIt: {
      en: "Backend route planning and parsing first; extension upload/capture only executes the backend's local raw-data instruction.",
      zh: "后端先负责路由规划和解析；扩展上传/采集只执行后端下发的本地 raw-data 指令。"
    },
    configureTarget: "browser_assisted_sources",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-springer-s12011-04820-w",
    links: []
  },
  {
    id: "wiley",
    label: { en: "Wiley", zh: "Wiley" },
    variantOf: "wiley",
    accessVariant: "publisher_tdm",
    presentationGroup: "api_key",
    rightsMode: "licensed",
    acquisitionMode: "official_api",
    requiresHelper: false,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Add your Wiley TDM token. Institutional sign-in or DOI-level entitlement may still be required.",
      zh: "填写 Wiley TDM token。某些 DOI 仍可能要求机构登录或相应授权。"
    },
    howMdteroGetsIt: {
      en: "Wiley TDM PDF retrieval first, then local browser or on-device fallback if that route is unavailable.",
      zh: "优先走 Wiley TDM PDF 接口；如果该链路不可用，再回退到本地浏览器或设备侧获取。"
    },
    configureTarget: "connector_keys",
    status: "experimental",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-wiley-validation-1",
    links: []
  },
  {
    id: "taylor_francis",
    label: { en: "Taylor & Francis", zh: "Taylor & Francis" },
    variantOf: "taylor_francis",
    accessVariant: "publisher_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Let Mdtero plan the route first. If the plan needs local raw data, use the extension to upload an authorized PDF or capture browser-context raw data.",
      zh: "先让 Mdtero 云端规划链路；如果计划需要本地 raw data，再用扩展上传授权 PDF 或采集浏览器上下文 raw data。"
    },
    howMdteroGetsIt: {
      en: "Backend route planning and parsing first; extension upload/capture only executes the backend's local raw-data instruction.",
      zh: "后端先负责路由规划和解析；扩展上传/采集只执行后端下发的本地 raw-data 指令。"
    },
    configureTarget: "browser_assisted_sources",
    status: "experimental",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-tf-html-live-3",
    links: []
  }
];

export function getPublisherCapabilityEntry(id: string) {
  return PUBLISHER_CAPABILITY_MATRIX.find((entry) => entry.id === id);
}

export function localizePublisherCapabilityEntry(
  entry: PublisherCapabilityEntry,
  language: PublisherCapabilityLanguage
): LocalizedPublisherCapabilityEntry {
  return {
    id: entry.id,
    label: localize(entry.label, language),
    variantOf: entry.variantOf,
    accessVariant: entry.accessVariant,
    presentationGroup: entry.presentationGroup,
    rightsMode: entry.rightsMode,
    acquisitionMode: entry.acquisitionMode,
    requiresHelper: entry.requiresHelper,
    requiresBrowser: entry.requiresBrowser,
    requiresApiKey: entry.requiresApiKey,
    mayNeedInstitutionAccess: entry.mayNeedInstitutionAccess,
    whatYouNeed: localize(entry.whatYouNeed, language),
    howMdteroGetsIt: localize(entry.howMdteroGetsIt, language),
    configureTarget: entry.configureTarget,
    status: entry.status,
    fallbacks: [...entry.fallbacks],
    validationRef: entry.validationRef,
    links: entry.links.map((item) => ({
      href: item.href,
      label: localize(item.label, language)
    }))
  };
}

export function getPublisherCapabilityGroups(
  language: PublisherCapabilityLanguage
): LocalizedPublisherCapabilityGroup[] {
  return GROUPS.map((group) => ({
    id: group.id,
    label: localize(group.label, language),
    description: localize(group.description, language),
    entries: PUBLISHER_CAPABILITY_MATRIX.filter((entry) => entry.presentationGroup === group.id).map((entry) =>
      localizePublisherCapabilityEntry(entry, language)
    )
  })).filter((group) => group.entries.length > 0);
}
