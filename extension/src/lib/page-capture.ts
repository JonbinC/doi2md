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

export type PdfDownloadResult =
  | {
      ok: true;
      payloadBase64: string;
      payloadName: "paper.pdf";
      sourceUrl: string;
    }
  | {
      ok: false;
      failureCode: "artifact_download_missing";
      failureMessage: string;
    };

export interface PdfCandidateInput {
  pageUrl: string;
  html: string;
}

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

export type HtmlFetchResult =
  | {
      ok: true;
      payloadText: string;
      payloadName: "paper.html";
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

function normalizeXmlCandidateUrl(candidateValue: string): string | null {
  let candidate = String(candidateValue || "").trim();
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
}): string[] {
  const html = String(params.html || "");
  const candidates: string[] = [];

  const explicitXml = matchMetaContent(html, ["citation_xml_url", "citation_springer_api_url"]);
  if (explicitXml) {
    const normalized = normalizeXmlCandidateUrl(explicitXml);
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

export function isLikelyHtmlDocument(text: string): boolean {
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
      failureMessage: "The tab is open, but Mdtero received a challenge or blocked page instead of article content."
    };
  }
  if (accessShell === "login") {
    return {
      ok: false,
      failureCode: "login_required",
      failureMessage: "The tab is open, but Mdtero received a login, access, or subscription page instead of the article. Open the full-text or PDF view in this browser session, or upload the PDF/XML/EPUB."
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
  const hasBodySignals = hasAnyMarker(lowered, BODY_MARKERS);
  const hasPdfEmbedShellSignals = hasAnyMarker(rawLowered, PDF_SHELL_MARKERS);
  const hasPdfDownloadOnlySignals = hasAnyMarker(rawLowered, PDF_DOWNLOAD_LINK_MARKERS);
  const hasArticleSignals = hasMetadataSignals && hasBodySignals;
  const isPdfEmbedShell = hasPdfEmbedShellSignals || (hasPdfDownloadOnlySignals && !hasArticleSignals);

  if (isPdfEmbedShell || !hasArticleSignals) {
    return {
      ok: false,
      failureCode: "article_body_missing",
      failureMessage: "The tab is open, but Mdtero could not find a parsable article body in the captured page. Open the full-text/PDF view or upload the PDF/XML/EPUB.",
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
  const result = await downloadBinaryArtifact(artifactUrl, {
    accept: "application/epub+zip,application/octet-stream,*/*;q=0.8",
    artifactLabel: "EPUB",
    payloadName: "paper.epub",
    validate: () => true,
  });
  return result as EpubDownloadResult;
}

export async function downloadPdfArtifact(artifactUrl: string): Promise<PdfDownloadResult> {
  return downloadPdfArtifactFromUrl(artifactUrl, new Set(), 0);
}

export async function downloadCurrentPagePdfArtifact(input: PdfCandidateInput): Promise<PdfDownloadResult> {
  const candidates = inferCurrentPagePdfCandidateUrls(input);
  let lastFailure = "Browser page context could not infer a downloadable PDF artifact from the current page.";

  for (const candidate of candidates) {
    const result = await downloadPdfArtifact(candidate);
    if (result.ok) {
      return result;
    }
    lastFailure = result.failureMessage;
  }

  return {
    ok: false,
    failureCode: "artifact_download_missing",
    failureMessage: lastFailure
  };
}

export function inferCurrentPagePdfCandidateUrls(input: PdfCandidateInput): string[] {
  const pageUrl = String(input.pageUrl || "").trim();
  const html = String(input.html || "");
  const candidates: string[] = [];

  for (const candidate of inferIeeePdfUrls(pageUrl, html)) {
    pushUniqueCandidate(candidates, candidate);
  }
  pushUniqueCandidate(candidates, inferScienceDirectPdfUrl(pageUrl));
  for (const candidate of inferCnkiPdfUrls(pageUrl, html)) {
    pushUniqueCandidate(candidates, candidate);
  }
  for (const candidate of extractPdfUrlsFromHtml(pageUrl, html)) {
    pushUniqueCandidate(candidates, candidate);
  }

  return candidates;
}

function inferIeeePdfUrls(pageUrl: string, html: string): string[] {
  const candidates: string[] = [];
  try {
    const parsed = new URL(pageUrl);
    if (!parsed.hostname.endsWith("ieeexplore.ieee.org")) {
      return [];
    }
    if (/\/stampPDF\/getPDF\.jsp/i.test(parsed.pathname)) {
      pushUniqueCandidate(candidates, parsed.toString());
    }
    if (/\/stamp\/stamp\.jsp/i.test(parsed.pathname)) {
      pushUniqueCandidate(candidates, parsed.toString());
    }
    const documentMatch = parsed.pathname.match(/\/(?:abstract\/)?document\/(\d+)/i);
    const arnumber = documentMatch?.[1] || parsed.searchParams.get("arnumber") || "";
    if (arnumber) {
      pushUniqueCandidate(candidates, buildIeeeStampPdfUrl(arnumber));
    }
  } catch {
    return candidates;
  }
  const metaPdf = matchMetaContent(html, ["citation_pdf_url"]);
  if (metaPdf) {
    pushUniqueCandidate(candidates, normalizeCandidateUrl(metaPdf, pageUrl));
  }
  for (const candidate of extractUrlsBySelectors(pageUrl, html, [
    "a[href*='stamp/stamp.jsp']",
    "a[href*='stampPDF']",
    "iframe[src*='stampPDF']",
    "iframe[src*='stamp/stamp.jsp']",
    "embed[src*='stampPDF']",
    "object[data*='stampPDF']"
  ])) {
    pushUniqueCandidate(candidates, candidate);
  }
  return candidates;
}

function buildIeeeStampPdfUrl(arnumber: string): string {
  return `https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=${encodeURIComponent(arnumber)}&ref=`;
}

function inferScienceDirectPdfUrl(pageUrl: string): string {
  try {
    const parsed = new URL(pageUrl);
    if (!parsed.hostname.endsWith("sciencedirect.com")) {
      return "";
    }
    if (parsed.pathname.includes("/pdfft")) {
      return parsed.toString();
    }
    const piiMatch = parsed.pathname.match(/\/science\/article\/pii\/([^/?#]+)/i);
    if (!piiMatch?.[1]) {
      return "";
    }
    parsed.pathname = `/science/article/pii/${piiMatch[1]}/pdfft`;
    parsed.search = "?isDTMRedir=true&download=true";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "";
  }
}

function inferCnkiPdfUrls(pageUrl: string, html: string): string[] {
  try {
    const parsed = new URL(pageUrl);
    if (!parsed.hostname.endsWith("cnki.net")) {
      return [];
    }
  } catch {
    return [];
  }
  return extractUrlsBySelectors(pageUrl, html, [
    "#pdfDown",
    ".btn-dlpdf a",
    "a[href*=\"pdf\"]",
    "a[href*=\"Pdf\"]"
  ]);
}

function extractPdfUrlsFromHtml(pageUrl: string, html: string): string[] {
  const urls: string[] = [];
  const metaPdf = matchMetaContent(html, ["citation_pdf_url"]);
  if (metaPdf) {
    pushUniqueCandidate(urls, normalizeCandidateUrl(metaPdf, pageUrl));
  }
  for (const candidate of extractUrlsBySelectors(pageUrl, html, [
    "iframe[src*='/pdf']",
    "iframe[src*='.pdf']",
    "iframe[src*='stampPDF']",
    "embed[src*='/pdf']",
    "embed[src*='.pdf']",
    "object[data*='/pdf']",
    "object[data*='.pdf']"
  ])) {
    pushUniqueCandidate(urls, candidate);
  }
  for (const candidate of extractUrlsBySelectors(pageUrl, html, [
    "a.download-link",
    "a[data-test=\"pdf-link\"]",
    "a[href*=\"/pdfft\"]",
    "a[href*=\"stampPDF\"]",
    "a[href*=\"stamp.jsp\"]",
    "a[href*=\"/pdf\"]",
    "a[href*=\".pdf\"]"
  ])) {
    pushUniqueCandidate(urls, candidate);
  }
  return urls.filter((url) => looksLikePdfCandidateUrl(url));
}

function extractUrlsBySelectors(pageUrl: string, html: string, selectors: string[]): string[] {
  if (typeof DOMParser === "undefined") {
    return extractHrefCandidatesWithRegex(pageUrl, html);
  }
  const document = new DOMParser().parseFromString(html, "text/html");
  const urls: string[] = [];
  for (const selector of selectors) {
    document.querySelectorAll(selector).forEach((node) => {
      const value =
        node.getAttribute("href") ||
        node.getAttribute("src") ||
        node.getAttribute("data") ||
        node.getAttribute("data-href") ||
        node.getAttribute("data-url") ||
        node.getAttribute("data-pdf-url") ||
        "";
      const normalized = normalizeCandidateUrl(value, pageUrl);
      if (normalized) {
        pushUniqueCandidate(urls, normalized);
      }
    });
  }
  return urls;
}

function extractHrefCandidatesWithRegex(pageUrl: string, html: string): string[] {
  const urls: string[] = [];
  const pattern = /(?:href|data-href|data-url|data-pdf-url)=["']([^"']+)["']/gi;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(html)) !== null) {
    const normalized = normalizeCandidateUrl(match[1], pageUrl);
    if (normalized) {
      pushUniqueCandidate(urls, normalized);
    }
  }
  return urls;
}

function normalizeCandidateUrl(value: string, pageUrl: string): string {
  const normalized = decodeHtmlAttribute(String(value || "").trim());
  if (!normalized || normalized === "#" || /^javascript:/i.test(normalized)) {
    return "";
  }
  try {
    return new URL(normalized, pageUrl).toString();
  } catch {
    return "";
  }
}

function looksLikePdfCandidateUrl(url: string): boolean {
  const lowered = String(url || "").toLowerCase();
  return lowered.includes("/pdfft") || lowered.includes("stamppdf") || lowered.includes("stamp.jsp") || lowered.includes("/pdf") || lowered.includes(".pdf");
}

async function downloadPdfArtifactFromUrl(
  artifactUrl: string,
  visited: Set<string>,
  depth: number
): Promise<PdfDownloadResult> {
  const normalizedUrl = String(artifactUrl || "").trim();
  if (!normalizedUrl || visited.has(normalizedUrl) || depth > 2) {
    return {
      ok: false,
      failureCode: "artifact_download_missing",
      failureMessage: "Browser page context could not download the PDF artifact."
    };
  }
  visited.add(normalizedUrl);

  const response = await fetch(normalizedUrl, {
    credentials: "include",
    headers: {
      Accept: "application/pdf,application/octet-stream,text/html,*/*;q=0.8"
    }
  });

  if (!response.ok) {
    return {
      ok: false,
      failureCode: "artifact_download_missing",
      failureMessage: `Browser page context could not download the PDF artifact (${response.status}).`
    };
  }

  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  if (looksLikePdfBytes(bytes)) {
    return {
      ok: true,
      payloadBase64: arrayBufferToBase64(buffer),
      payloadName: "paper.pdf",
      sourceUrl: normalizedUrl
    };
  }

  const text = bytesToText(bytes);
  if (isLikelyHtmlDocument(text)) {
    for (const candidate of inferPdfCandidateUrlsFromGatewayHtml(response.url || normalizedUrl, text)) {
      const result = await downloadPdfArtifactFromUrl(candidate, visited, depth + 1);
      if (result.ok) {
        return result;
      }
    }
  }

  return {
    ok: false,
    failureCode: "artifact_download_missing",
    failureMessage: "Browser page context downloaded a response that was not a valid PDF artifact."
  };
}

function inferPdfCandidateUrlsFromGatewayHtml(pageUrl: string, html: string): string[] {
  const candidates: string[] = [];
  for (const candidate of inferIeeePdfUrls(pageUrl, html)) {
    pushUniqueCandidate(candidates, candidate);
  }
  for (const candidate of extractPdfUrlsFromHtml(pageUrl, html)) {
    pushUniqueCandidate(candidates, candidate);
  }
  return candidates;
}

function bytesToText(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes.subarray(0, Math.min(bytes.length, 262144)));
}

async function downloadBinaryArtifact(
  artifactUrl: string,
  options: {
    accept: string;
    artifactLabel: string;
    payloadName: "paper.epub" | "paper.pdf";
    validate: (bytes: Uint8Array) => boolean;
  }
): Promise<EpubDownloadResult | PdfDownloadResult> {
  const response = await fetch(artifactUrl, {
    credentials: "include",
    headers: {
      Accept: options.accept
    }
  });

  if (!response.ok) {
    return {
      ok: false,
      failureCode: "artifact_download_missing",
      failureMessage: `Browser page context could not download the ${options.artifactLabel} artifact (${response.status}).`
    };
  }

  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  if (!options.validate(bytes)) {
    return {
      ok: false,
      failureCode: "artifact_download_missing",
      failureMessage: `Browser page context downloaded a response that was not a valid ${options.artifactLabel} artifact.`
    };
  }

  return {
    ok: true,
    payloadBase64: arrayBufferToBase64(buffer),
    payloadName: options.payloadName,
    sourceUrl: artifactUrl
  };
}

function looksLikePdfBytes(bytes: Uint8Array): boolean {
  if (bytes.length < 5) {
    return false;
  }
  return bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46 && bytes[4] === 0x2d;
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

export async function fetchHtmlArtifact(candidateUrls: string[]): Promise<HtmlFetchResult> {
  let lastFailure = "Browser page context could not download a usable HTML payload.";

  for (const candidate of candidateUrls.map((item) => String(item || "").trim()).filter(Boolean)) {
    try {
      const response = await fetch(candidate, {
        credentials: "include",
        headers: {
          Accept: "text/html,application/xhtml+xml,*/*;q=0.8"
        }
      });
      if (!response.ok) {
        lastFailure = `Browser page context could not download the HTML artifact (${response.status}).`;
        continue;
      }
      const text = await response.text();
      const capture = buildPageCaptureResult({
        url: response.url || candidate,
        title: "",
        html: text
      });
      if (capture.ok) {
        return {
          ok: true,
          payloadText: capture.html,
          payloadName: capture.payloadName,
          sourceUrl: capture.sourceUrl
        };
      }
      lastFailure = capture.failureMessage;
    } catch (error) {
      lastFailure = error instanceof Error ? error.message : String(error);
    }
  }

  return {
    ok: false,
    failureCode: "artifact_download_missing",
    failureMessage: lastFailure
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
