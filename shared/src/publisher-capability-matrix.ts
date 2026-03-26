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
      en: "Helper only",
      zh: "只需本地 helper"
    },
    description: {
      en: "Install the local helper and parse directly from supported open full-text sources.",
      zh: "安装本地 helper 后，直接从受支持的开放全文来源解析。"
    }
  },
  {
    id: "api_key",
    label: {
      en: "Helper + API key",
      zh: "需要 helper 和 API key"
    },
    description: {
      en: "Install the local helper and add the required publisher key in settings.",
      zh: "安装本地 helper，并在设置里填写所需的出版社 key。"
    }
  },
  {
    id: "browser_assisted",
    label: {
      en: "Helper + browser extension",
      zh: "需要 helper 和浏览器扩展"
    },
    description: {
      en: "Keep the article page open locally when Mdtero needs browser-assisted capture.",
      zh: "当 Mdtero 需要浏览器辅助抓取时，请在本地保持文章页面打开。"
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
      en: "Install the local helper.",
      zh: "安装本地 helper。"
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
      en: "Install the local helper.",
      zh: "安装本地 helper。"
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
      en: "Install the local helper.",
      zh: "安装本地 helper。"
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
      en: "Install the local helper.",
      zh: "安装本地 helper。"
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
      en: "Install the local helper.",
      zh: "安装本地 helper。"
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
      en: "Install the local helper.",
      zh: "安装本地 helper。"
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
      en: "Install the local helper and add your Elsevier API key. Some papers may still require institutional access.",
      zh: "安装本地 helper，并填写 Elsevier API key。部分论文仍可能需要机构权限。"
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
      en: "Install the local helper. Add your Springer OA API key for the best XML path.",
      zh: "安装本地 helper。填写 Springer OA API key 可优先走 XML 路径。"
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
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "安装本地 helper，并在浏览器中保持文章页面打开。可能需要机构登录。"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from the live article page.",
      zh: "通过实时文章页进行浏览器辅助抓取。"
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
    accessVariant: "publisher_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "安装本地 helper，并在浏览器中保持文章页面打开。可能需要机构登录。"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from Wiley article pages.",
      zh: "通过 Wiley 文章页进行浏览器辅助抓取。"
    },
    configureTarget: "browser_assisted_sources",
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
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "安装本地 helper，并在浏览器中保持文章页面打开。可能需要机构登录。"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from Taylor & Francis pages.",
      zh: "通过 Taylor & Francis 页面进行浏览器辅助抓取。"
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
