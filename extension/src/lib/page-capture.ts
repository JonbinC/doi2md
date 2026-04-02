export interface PageCaptureInput {
  url: string;
  title: string;
  html: string;
}

export interface PageCaptureFailureContext {
  sourceUrl: string;
  title: string;
  hasMetadataSignals: boolean;
  hasBodySignals: boolean;
  isPdfEmbedShell: boolean;
}

export type EpubDownloadResult =
  | {
      ok: true;
      payloadBase64: string;
      payloadName: "paper.epub";
      sourceUrl: string;
    }
  | {
      ok: false;
      failureCode: "artifact_download_missing";
      failureMessage: string;
    };

export type XmlFetchResult =
  | {
      ok: true;
      payloadText: string;
      payloadName: "paper.xml";
      sourceUrl: string;
    }
  | {
      ok: false;
      failureCode: "artifact_download_missing";
      failureMessage: string;
    };

export type PageCaptureResult =
  | {
      ok: true;
      html: string;
      payloadName: "paper.html";
      sourceUrl: string;
      pageTitle: string;
    }
  | {
      ok: false;
      failureCode: "challenge_page_detected" | "login_required" | "article_body_missing";
      failureMessage: string;
      failureContext?: PageCaptureFailureContext;
    };

function decodeHtmlAttribute(value: string): string {
  return String(value || "")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, "\"")
    .replace(/&#39;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">");
}

function matchMetaContent(html: string, metaNames: string[]): string | null {
  for (const metaName of metaNames) {
    const variants = Array.from(
      new Set([
        metaName,
        metaName.replace(/\./g, ":"),
        metaName.replace(/:/g, ".")
      ].filter(Boolean))
    );
    for (const variant of variants) {
      const escaped = variant.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const patterns = [
        new RegExp(`<meta[^>]+name=["']${escaped}["'][^>]+content=["']([^"']+)["']`, "i"),
        new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+name=["']${escaped}["']`, "i")
      ];
      for (const pattern of patterns) {
        const match = html.match(pattern);
        if (match?.[1]) {
          return decodeHtmlAttribute(match[1]);
        }
      }
    }
  }
  return null;
}

function pushUniqueCandidate(target: string[], candidate: string): void {
  const normalized = String(candidate || "").trim();
  if (!normalized || target.includes(normalized)) {
    return;
  }
  target.push(normalized);
}

function normalizeXmlCandidateUrl(params: {
  candidate: string;
  springerOpenAccessApiKey?: string;
}): string | null {
  let candidate = String(params.candidate || "").trim();
  if (!candidate) {
    return null;
  }
  if (candidate.startsWith("http://")) {
    candidate = `https://${candidate.slice("http://".length)}`;
  }

  try {
    const parsed = new URL(candidate);
    const isLegacySpringerJats =
      parsed.hostname === "api.springer.com" &&
      parsed.pathname.replace(/\/+$/, "") === "/xmldata/jats";

    if (params.springerOpenAccessApiKey) {
      if (parsed.searchParams.has("api_key")) {
        parsed.searchParams.set("api_key", params.springerOpenAccessApiKey);
      }
      return parsed.toString();
    }

    if (isLegacySpringerJats) {
      const apiKey = parsed.searchParams.get("api_key") || "";
      if (!apiKey.trim()) {
        return null;
      }
    }

    return parsed.toString();
  } catch {
    return candidate;
  }
}

export function extractXmlCandidateUrls(params: {
  html: string;
  pageUrl: string;
  springerOpenAccessApiKey?: string;
}): string[] {
  const html = String(params.html || "");
  const pageUrl = String(params.pageUrl || "");
  const candidates: string[] = [];
  const doi = matchMetaContent(html, ["citation_doi", "prism.doi", "prism:doi", "dc.identifier", "dc:identifier"])?.match(
    /10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i
  )?.[0];

  if (doi && params.springerOpenAccessApiKey && /springer/i.test(pageUrl)) {
    pushUniqueCandidate(
      candidates,
      `https://api.springernature.com/openaccess/jats?q=doi:${encodeURIComponent(doi)}&api_key=${encodeURIComponent(params.springerOpenAccessApiKey)}`
    );
  }

  const explicitXml = matchMetaContent(html, ["citation_xml_url", "citation_springer_api_url"]);
  if (explicitXml) {
    const normalized = normalizeXmlCandidateUrl({
      candidate: explicitXml,
      springerOpenAccessApiKey: params.springerOpenAccessApiKey
    });
    if (normalized) {
      pushUniqueCandidate(candidates, normalized);
    }
  }

  return candidates;
}

const CHALLENGE_MARKERS = [
  "just a moment",
  "access denied",
  "captcha",
  "cf-browser-verification",
  "window._cf_chl_opt",
  "__cf_chl_tk=",
  "/cdn-cgi/challenge-platform/",
  "ctype: 'managed'",
  "verify you are human",
  "checking if the site connection is secure",
  "enable javascript and cookies to continue",
  "pardon the interruption"
];

const LOGIN_MARKERS = [
  "sign in",
  "institutional access",
  "shibboleth",
  "openathens",
  "access through your institution",
  "login via your institution",
  "institutional login",
  "institutional sign in",
  "your institution does not have access",
  "purchase a subscription to gain access"
];

const PDF_SHELL_MARKERS = [
  'id="pdf-iframe"',
  'type="application/pdf"',
  "/doi/pdfdirect/",
  "/epdf",
  "/doi/pdf/"
];

const PDF_DOWNLOAD_LINK_MARKERS = [
  "download pdf"
];

const METADATA_MARKERS = [
  "citation_title",
  "citation_doi",
  "dc.identifier",
  "dc:identifier",
  "dc.title",
  "dc:title",
  "prism.doi",
  "prism:doi"
];

const BODY_MARKERS = [
  "<main",
  "<article",
  "article-section__content",
  "article__body",
  "article-body",
  "article-content",
  "article__content",
  "fulltext-view",
  "hlfld-fulltext",
  "main-content",
  "main-content__body",
  "c-article-body",
  "c-article-section",
  "article-section",
  "references-list",
  "reference-section",
  "references",
  "ltx_document",
  "ltx_abstract"
];

const ARTICLE_XML_MARKERS = [
  "<article",
  "<body",
  "<sec",
  "<jats:",
  "full-text-retrieval-response",
  "originaltext"
];

export function classifyAccessShell(html: string): "challenge" | "login" | null {
  const lowered = String(html || "").toLowerCase();
  if (CHALLENGE_MARKERS.some((marker) => lowered.includes(marker))) {
    return "challenge";
  }
  if (
    LOGIN_MARKERS.some((marker) => lowered.includes(marker)) ||
    (lowered.includes("password") && lowered.includes("sign in"))
  ) {
    return "login";
  }
  return null;
}

export function isLikelyChallengeOrLoginShell(html: string): boolean {
  return classifyAccessShell(html) !== null;
}

function isLikelyHtmlDocument(text: string): boolean {
  const lowered = String(text || "").trim().toLowerCase();
  return lowered.startsWith("<!doctype html") || lowered.startsWith("<html") || lowered.includes("<html");
}

function hasAnyMarker(text: string, markers: string[]): boolean {
  return markers.some((marker) => text.includes(marker));
}

function stripTagBlock(html: string, tagName: string): string {
  return html.replace(new RegExp(`<${tagName}\\b[^>]*>[\\s\\S]*?<\\/${tagName}>`, "gi"), "");
}

function stripSelfClosingTag(html: string, tagName: string): string {
  return html.replace(new RegExp(`<${tagName}\\b[^>]*\\/?>`, "gi"), "");
}

function stripTaggedNodesByAttributeMarker(html: string, markers: string[]): string {
  let cleaned = html;
  for (const marker of markers) {
    const escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    cleaned = cleaned.replace(
      new RegExp(
        `<([a-z0-9:-]+)\\b[^>]*(?:id|class)=["'][^"']*${escaped}[^"']*["'][^>]*>[\\s\\S]*?<\\/\\1>`,
        "gi"
      ),
      ""
    );
    cleaned = cleaned.replace(
      new RegExp(
        `<([a-z0-9:-]+)\\b[^>]*(?:id|class)=["'][^"']*${escaped}[^"']*["'][^>]*\\/?>`,
        "gi"
      ),
      ""
    );
  }
  return cleaned;
}

function stripStronglyHiddenNodes(html: string): string {
  return html.replace(
    /<([a-z0-9:-]+)\b(?=[^>]*(?:aria-hidden=["']true["']|hidden\b))(?=[^>]*style=["'][^"']*(?:display\s*:\s*none|visibility\s*:\s*hidden)[^"']*["'])[^>]*>[\s\S]*?<\/\1>/gi,
    ""
  );
}

function stripExtensionResourceNodes(html: string): string {
  return html.replace(
    /<([a-z0-9:-]+)\b[^>]*(?:src|href)=["']chrome-extension:\/\/[^"']+["'][^>]*>(?:[\s\S]*?<\/\1>)?/gi,
    ""
  );
}

export function sanitizeCapturedHtml(html: string): string {
  let cleaned = String(html || "");
  for (const tagName of ["script", "style", "noscript", "iframe", "object", "embed"]) {
    cleaned = stripTagBlock(cleaned, tagName);
  }
  for (const tagName of ["iframe", "object", "embed"]) {
    cleaned = stripSelfClosingTag(cleaned, tagName);
  }
  cleaned = stripTaggedNodesByAttributeMarker(cleaned, [
    "glarity",
    "tp-extension",
    "tcb-extension",
    "crx-",
    "shadowll"
  ]);
  cleaned = stripTagBlock(cleaned, "shadow-host");
  cleaned = stripSelfClosingTag(cleaned, "shadow-host");
  cleaned = stripExtensionResourceNodes(cleaned);
  cleaned = stripStronglyHiddenNodes(cleaned);
  return cleaned.trim();
}

function isLikelyStructuredArticleXml(text: string): boolean {
  const lowered = String(text || "").trim().toLowerCase();
  if (!lowered.startsWith("<") && !lowered.startsWith("<?xml")) {
    return false;
  }
  if (isLikelyHtmlDocument(lowered) || isLikelyChallengeOrLoginShell(lowered)) {
    return false;
  }
  return hasAnyMarker(lowered, ARTICLE_XML_MARKERS);
}

export function buildPageCaptureResult(input: PageCaptureInput): PageCaptureResult {
  const html = String(input.html || "");
  const accessShell = classifyAccessShell(`${input.title}\n${html}`);
  if (accessShell === "challenge") {
    return {
      ok: false,
      failureCode: "challenge_page_detected",
      failureMessage: "Page loaded but did not expose article content."
    };
  }
  if (accessShell === "login") {
    return {
      ok: false,
      failureCode: "login_required",
      failureMessage: "Page loaded but still requires user sign-in or institutional access."
    };
  }

  const sanitizedHtml = sanitizeCapturedHtml(html);
  const normalizedUrl = String(input.url || "").toLowerCase();
  if (normalizedUrl.includes("arxiv.org/abs/")) {
    return {
      ok: false,
      failureCode: "article_body_missing",
      failureMessage: "arXiv abstract pages do not contain the full text. Open the /html/ page instead, then retry capture.",
      failureContext: {
        sourceUrl: input.url,
        title: input.title,
        hasMetadataSignals: true,
        hasBodySignals: false,
        isPdfEmbedShell: false
      }
    };
  }

  const lowered = sanitizedHtml.toLowerCase();
  const rawLowered = html.toLowerCase();
  const hasMetadataSignals = hasAnyMarker(lowered, METADATA_MARKERS);
  const hasBodySignals = hasAnyMarker(lowered, BODY_MARKERS) || lowered.includes("abstract");
  const hasPdfEmbedShellSignals = hasAnyMarker(rawLowered, PDF_SHELL_MARKERS);
  const hasPdfDownloadOnlySignals = hasAnyMarker(rawLowered, PDF_DOWNLOAD_LINK_MARKERS);
  const hasArticleSignals = hasMetadataSignals && hasBodySignals;
  const isPdfEmbedShell = hasPdfEmbedShellSignals || (hasPdfDownloadOnlySignals && !hasArticleSignals);

  if (isPdfEmbedShell || !hasArticleSignals) {
    return {
      ok: false,
      failureCode: "article_body_missing",
      failureMessage: "Page loaded but no article body markers were detected.",
      failureContext: {
        sourceUrl: input.url,
        title: input.title,
        hasMetadataSignals,
        hasBodySignals,
        isPdfEmbedShell
      }
    };
  }

  return {
    ok: true,
    html: sanitizedHtml,
    payloadName: "paper.html",
    sourceUrl: input.url,
    pageTitle: input.title
  };
}

export async function downloadEpubArtifact(artifactUrl: string): Promise<EpubDownloadResult> {
  const response = await fetch(artifactUrl, {
    credentials: "include"
  });

  if (!response.ok) {
    return {
      ok: false,
      failureCode: "artifact_download_missing",
      failureMessage: `Browser page context could not download the EPUB artifact (${response.status}).`
    };
  }

  return {
    ok: true,
    payloadBase64: arrayBufferToBase64(await response.arrayBuffer()),
    payloadName: "paper.epub",
    sourceUrl: artifactUrl
  };
}

export async function fetchXmlArtifact(candidateUrls: string[]): Promise<XmlFetchResult> {
  for (const candidate of candidateUrls.map((item) => String(item || "").trim()).filter(Boolean)) {
    const response = await fetch(candidate, {
      credentials: "include"
    });
    if (!response.ok) {
      continue;
    }
    const text = await response.text();
    const normalized = text.trim();
    if (!normalized) {
      continue;
    }
    if (!normalized.startsWith("<")) {
      continue;
    }
    if (isLikelyHtmlDocument(normalized) || isLikelyChallengeOrLoginShell(normalized)) {
      continue;
    }
    if (isLikelyStructuredArticleXml(normalized)) {
      return {
        ok: true,
        payloadText: normalized,
        payloadName: "paper.xml",
        sourceUrl: candidate
      };
    }
  }

  return {
    ok: false,
    failureCode: "artifact_download_missing",
    failureMessage: "Browser page context could not download an XML payload."
  };
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}
