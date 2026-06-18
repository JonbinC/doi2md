// src/lib/detect.ts
var DOI_PATTERN = /10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i;
var ARXIV_PATTERN = /arxiv\.org\/(abs|pdf|html)\/([a-z\-]+\/\d{7}|[0-9]{4}\.[0-9]{4,5})(?:\.pdf)?/i;
function matchMetaContent(html, metaNames) {
  for (const metaName of metaNames) {
    const escaped = metaName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const patterns = [
      new RegExp(`<meta[^>]+name=["']${escaped}["'][^>]+content=["']([^"']+)["']`, "i"),
      new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+name=["']${escaped}["']`, "i"),
      new RegExp(`<meta[^>]+property=["']${escaped}["'][^>]+content=["']([^"']+)["']`, "i"),
      new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+property=["']${escaped}["']`, "i")
    ];
    for (const pattern of patterns) {
      const match = html.match(pattern);
      if (match?.[1]) {
        return match[1];
      }
    }
  }
  return null;
}
function detectPaperInput(input) {
  const arxivMatch = input.url.match(ARXIV_PATTERN);
  if (arxivMatch) {
    return { kind: "arxiv", value: input.url };
  }
  const urlMatch = input.url.match(DOI_PATTERN);
  if (urlMatch) {
    return { kind: "doi", value: urlMatch[0] };
  }
  const metaDoi = matchMetaContent(input.html, ["citation_doi", "prism.doi", "dc.identifier"]);
  if (metaDoi && DOI_PATTERN.test(metaDoi)) {
    const match = metaDoi.match(DOI_PATTERN);
    if (match) {
      return { kind: "doi", value: match[0] };
    }
  }
  if (input.url.includes("sciencedirect.com/science/article/pii/")) {
    return { kind: "sciencedirect", value: input.url };
  }
  if (isIeeeArticlePage(input.url)) {
    return { kind: "ieee", value: input.url };
  }
  if (isCnkiArticlePage(input.url)) {
    return { kind: "cnki", value: input.url };
  }
  const htmlMatch = input.html.match(DOI_PATTERN);
  if (htmlMatch) {
    return { kind: "doi", value: htmlMatch[0] };
  }
  return null;
}
function isCnkiArticlePage(url) {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.hostname.endsWith("cnki.net") && /\/kcms2\/article\/(?:abstract|detail)/i.test(parsed.pathname);
  } catch {
    return false;
  }
}
function isIeeeArticlePage(url) {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.hostname.endsWith("ieeexplore.ieee.org") && /\/(?:abstract\/)?document\/\d+|\/stamp\/(?:stamp\.jsp)|\/stampPDF\/getPDF\.jsp/i.test(parsed.pathname);
  } catch {
    return false;
  }
}

// src/lib/page-capture.ts
function decodeHtmlAttribute(value) {
  return String(value || "").replace(/&amp;/gi, "&").replace(/&quot;/gi, '"').replace(/&#39;/gi, "'").replace(/&lt;/gi, "<").replace(/&gt;/gi, ">");
}
function matchMetaContent2(html, metaNames) {
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
function pushUniqueCandidate(target, candidate) {
  const normalized = String(candidate || "").trim();
  if (!normalized || target.includes(normalized)) {
    return;
  }
  target.push(normalized);
}
function normalizeXmlCandidateUrl(candidateValue) {
  let candidate = String(candidateValue || "").trim();
  if (!candidate) {
    return null;
  }
  if (candidate.startsWith("http://")) {
    candidate = `https://${candidate.slice("http://".length)}`;
  }
  try {
    const parsed = new URL(candidate);
    const isLegacySpringerJats = parsed.hostname === "api.springer.com" && parsed.pathname.replace(/\/+$/, "") === "/xmldata/jats";
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
function extractXmlCandidateUrls(params) {
  const html = String(params.html || "");
  const candidates = [];
  const explicitXml = matchMetaContent2(html, ["citation_xml_url", "citation_springer_api_url"]);
  if (explicitXml) {
    const normalized = normalizeXmlCandidateUrl(explicitXml);
    if (normalized) {
      pushUniqueCandidate(candidates, normalized);
    }
  }
  return candidates;
}
var CHALLENGE_MARKERS = [
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
var LOGIN_MARKERS = [
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
var PDF_SHELL_MARKERS = [
  'id="pdf-iframe"',
  'type="application/pdf"',
  "/doi/pdfdirect/",
  "/epdf",
  "/doi/pdf/"
];
var PDF_DOWNLOAD_LINK_MARKERS = [
  "download pdf"
];
var METADATA_MARKERS = [
  "citation_title",
  "citation_doi",
  "dc.identifier",
  "dc:identifier",
  "dc.title",
  "dc:title",
  "prism.doi",
  "prism:doi"
];
var BODY_MARKERS = [
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
var ARTICLE_XML_MARKERS = [
  "<article",
  "<body",
  "<sec",
  "<jats:",
  "full-text-retrieval-response",
  "originaltext"
];
function classifyAccessShell(html) {
  const lowered = String(html || "").toLowerCase();
  if (CHALLENGE_MARKERS.some((marker) => lowered.includes(marker))) {
    return "challenge";
  }
  if (LOGIN_MARKERS.some((marker) => lowered.includes(marker)) || lowered.includes("password") && lowered.includes("sign in")) {
    return "login";
  }
  return null;
}
function isLikelyChallengeOrLoginShell(html) {
  return classifyAccessShell(html) !== null;
}
function isLikelyHtmlDocument(text) {
  const lowered = String(text || "").trim().toLowerCase();
  return lowered.startsWith("<!doctype html") || lowered.startsWith("<html") || lowered.includes("<html");
}
function hasAnyMarker(text, markers) {
  return markers.some((marker) => text.includes(marker));
}
function stripTagBlock(html, tagName) {
  return html.replace(new RegExp(`<${tagName}\\b[^>]*>[\\s\\S]*?<\\/${tagName}>`, "gi"), "");
}
function stripSelfClosingTag(html, tagName) {
  return html.replace(new RegExp(`<${tagName}\\b[^>]*\\/?>`, "gi"), "");
}
function stripTaggedNodesByAttributeMarker(html, markers) {
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
function stripStronglyHiddenNodes(html) {
  return html.replace(
    /<([a-z0-9:-]+)\b(?=[^>]*(?:aria-hidden=["']true["']|hidden\b))(?=[^>]*style=["'][^"']*(?:display\s*:\s*none|visibility\s*:\s*hidden)[^"']*["'])[^>]*>[\s\S]*?<\/\1>/gi,
    ""
  );
}
function stripExtensionResourceNodes(html) {
  return html.replace(
    /<([a-z0-9:-]+)\b[^>]*(?:src|href)=["']chrome-extension:\/\/[^"']+["'][^>]*>(?:[\s\S]*?<\/\1>)?/gi,
    ""
  );
}
function sanitizeCapturedHtml(html) {
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
function isLikelyStructuredArticleXml(text) {
  const lowered = String(text || "").trim().toLowerCase();
  if (!lowered.startsWith("<") && !lowered.startsWith("<?xml")) {
    return false;
  }
  if (isLikelyHtmlDocument(lowered) || isLikelyChallengeOrLoginShell(lowered)) {
    return false;
  }
  return hasAnyMarker(lowered, ARTICLE_XML_MARKERS);
}
function buildPageCaptureResult(input) {
  const html = String(input.html || "");
  const accessShell = classifyAccessShell(`${input.title}
${html}`);
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
  const isPdfEmbedShell = hasPdfEmbedShellSignals || hasPdfDownloadOnlySignals && !hasArticleSignals;
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
async function downloadEpubArtifact(artifactUrl) {
  const result = await downloadBinaryArtifact(artifactUrl, {
    accept: "application/epub+zip,application/octet-stream,*/*;q=0.8",
    artifactLabel: "EPUB",
    payloadName: "paper.epub",
    validate: () => true
  });
  return result;
}
async function downloadPdfArtifact(artifactUrl) {
  return downloadPdfArtifactFromUrl(artifactUrl, /* @__PURE__ */ new Set(), 0);
}
async function downloadCurrentPagePdfArtifact(input) {
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
function inferCurrentPagePdfCandidateUrls(input) {
  const pageUrl = String(input.pageUrl || "").trim();
  const html = String(input.html || "");
  const candidates = [];
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
function inferIeeePdfUrls(pageUrl, html) {
  const candidates = [];
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
  const metaPdf = matchMetaContent2(html, ["citation_pdf_url"]);
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
function buildIeeeStampPdfUrl(arnumber) {
  return `https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=${encodeURIComponent(arnumber)}&ref=`;
}
function inferScienceDirectPdfUrl(pageUrl) {
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
function inferCnkiPdfUrls(pageUrl, html) {
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
    'a[href*="pdf"]',
    'a[href*="Pdf"]'
  ]);
}
function extractPdfUrlsFromHtml(pageUrl, html) {
  const urls = [];
  const metaPdf = matchMetaContent2(html, ["citation_pdf_url"]);
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
    'a[data-test="pdf-link"]',
    'a[href*="/pdfft"]',
    'a[href*="stampPDF"]',
    'a[href*="stamp.jsp"]',
    'a[href*="/pdf"]',
    'a[href*=".pdf"]'
  ])) {
    pushUniqueCandidate(urls, candidate);
  }
  return urls.filter((url) => looksLikePdfCandidateUrl(url));
}
function extractUrlsBySelectors(pageUrl, html, selectors) {
  if (typeof DOMParser === "undefined") {
    return extractHrefCandidatesWithRegex(pageUrl, html);
  }
  const document2 = new DOMParser().parseFromString(html, "text/html");
  const urls = [];
  for (const selector of selectors) {
    document2.querySelectorAll(selector).forEach((node) => {
      const value = node.getAttribute("href") || node.getAttribute("src") || node.getAttribute("data") || node.getAttribute("data-href") || node.getAttribute("data-url") || node.getAttribute("data-pdf-url") || "";
      const normalized = normalizeCandidateUrl(value, pageUrl);
      if (normalized) {
        pushUniqueCandidate(urls, normalized);
      }
    });
  }
  return urls;
}
function extractHrefCandidatesWithRegex(pageUrl, html) {
  const urls = [];
  const pattern = /(?:href|data-href|data-url|data-pdf-url)=["']([^"']+)["']/gi;
  let match;
  while ((match = pattern.exec(html)) !== null) {
    const normalized = normalizeCandidateUrl(match[1], pageUrl);
    if (normalized) {
      pushUniqueCandidate(urls, normalized);
    }
  }
  return urls;
}
function normalizeCandidateUrl(value, pageUrl) {
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
function looksLikePdfCandidateUrl(url) {
  const lowered = String(url || "").toLowerCase();
  return lowered.includes("/pdfft") || lowered.includes("stamppdf") || lowered.includes("stamp.jsp") || lowered.includes("/pdf") || lowered.includes(".pdf");
}
async function downloadPdfArtifactFromUrl(artifactUrl, visited, depth) {
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
function inferPdfCandidateUrlsFromGatewayHtml(pageUrl, html) {
  const candidates = [];
  for (const candidate of inferIeeePdfUrls(pageUrl, html)) {
    pushUniqueCandidate(candidates, candidate);
  }
  for (const candidate of extractPdfUrlsFromHtml(pageUrl, html)) {
    pushUniqueCandidate(candidates, candidate);
  }
  return candidates;
}
function bytesToText(bytes) {
  return new TextDecoder().decode(bytes.subarray(0, Math.min(bytes.length, 262144)));
}
async function downloadBinaryArtifact(artifactUrl, options) {
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
function looksLikePdfBytes(bytes) {
  if (bytes.length < 5) {
    return false;
  }
  return bytes[0] === 37 && bytes[1] === 80 && bytes[2] === 68 && bytes[3] === 70 && bytes[4] === 45;
}
async function fetchXmlArtifact(candidateUrls) {
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
async function fetchHtmlArtifact(candidateUrls) {
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
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 32768;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

// src/lib/auth-bridge.ts
var TRUSTED_SITE_ORIGINS = /* @__PURE__ */ new Set([
  "https://mdtero.com",
  "https://www.mdtero.com"
]);
var TRUSTED_LOCAL_DEV_HOST_PATTERNS = [
  /^localhost$/i,
  /^127\.0\.0\.1$/i
];
function isMdteroAuthTokenPayload(data) {
  return Boolean(
    data && typeof data === "object" && "type" in data && "token" in data && "email" in data && data.type === "mdtero.auth.token" && data.source === "extension" && typeof data.token === "string" && typeof data.email === "string" && typeof data.issuedAt === "number" && data.token && data.email && isFreshAuthBridgeTimestamp(Number(data.issuedAt))
  );
}
function isFreshAuthBridgeTimestamp(issuedAt, now = Date.now()) {
  if (!Number.isFinite(issuedAt)) {
    return false;
  }
  const ageMs = Math.abs(now - issuedAt);
  return ageMs <= 6e4;
}
function isTrustedMdteroOrigin(origin) {
  try {
    const url = new URL(origin);
    if (TRUSTED_SITE_ORIGINS.has(url.origin)) {
      return true;
    }
    return url.protocol === "http:" && TRUSTED_LOCAL_DEV_HOST_PATTERNS.some((pattern) => pattern.test(url.hostname));
  } catch {
    return false;
  }
}
function shouldAcceptMdteroAuthMessage(event) {
  if (!isTrustedMdteroOrigin(event.currentOrigin)) {
    return false;
  }
  if (!isTrustedMdteroOrigin(event.eventOrigin)) {
    return false;
  }
  if (event.currentOrigin !== event.eventOrigin) {
    return false;
  }
  return isMdteroAuthTokenPayload(event.data);
}

// src/content.ts
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "mdtero.download_epub.request") {
    downloadEpubArtifact(String(message.artifactUrl || "")).then((download) => sendResponse({ ok: true, download })).catch(
      (error) => sendResponse({
        ok: true,
        download: {
          ok: false,
          failureCode: "artifact_download_missing",
          failureMessage: error.message
        }
      })
    );
    return true;
  }
  if (message?.type === "mdtero.download_pdf.request") {
    downloadPdfArtifact(String(message.artifactUrl || "")).then((download) => sendResponse({ ok: true, download })).catch(
      (error) => sendResponse({
        ok: true,
        download: {
          ok: false,
          failureCode: "artifact_download_missing",
          failureMessage: error.message
        }
      })
    );
    return true;
  }
  if (message?.type === "mdtero.download_current_page_pdf.request") {
    downloadCurrentPagePdfArtifact({
      pageUrl: window.location.href,
      html: document.documentElement.outerHTML
    }).then((download) => sendResponse({ ok: true, download })).catch(
      (error) => sendResponse({
        ok: true,
        download: {
          ok: false,
          failureCode: "artifact_download_missing",
          failureMessage: error.message
        }
      })
    );
    return true;
  }
  if (message?.type === "mdtero.fetch_xml.request") {
    const candidates = [
      String(message.artifactUrl || ""),
      String(message.sourceUrl || ""),
      window.location.href
    ].filter(Boolean);
    fetchXmlArtifact(candidates).then((xml) => sendResponse({ ok: true, xml })).catch(
      (error) => sendResponse({
        ok: true,
        xml: {
          ok: false,
          failureCode: "artifact_download_missing",
          failureMessage: error.message
        }
      })
    );
    return true;
  }
  if (message?.type === "mdtero.fetch_html.request") {
    const candidates = Array.isArray(message.candidateUrls) ? message.candidateUrls.map((item) => String(item || "")).filter(Boolean) : [];
    fetchHtmlArtifact(candidates).then((html) => sendResponse({ ok: true, html })).catch(
      (error) => sendResponse({
        ok: true,
        html: {
          ok: false,
          failureCode: "artifact_download_missing",
          failureMessage: error.message
        }
      })
    );
    return true;
  }
  if (message?.type === "mdtero.capture_html.request") {
    sendResponse({
      ok: true,
      capture: buildPageCaptureResult({
        url: window.location.href,
        title: document.title,
        html: document.documentElement.outerHTML
      })
    });
    return false;
  }
  if (message?.type === "mdtero.capture_current_tab.request") {
    const html = document.documentElement.outerHTML;
    const capture = buildPageCaptureResult({
      url: window.location.href,
      title: document.title,
      html
    });
    const xmlCandidates = extractXmlCandidateUrls({
      html,
      pageUrl: window.location.href
    });
    if (xmlCandidates.length === 0) {
      sendResponse({
        ok: true,
        capture
      });
      return false;
    }
    fetchXmlArtifact(xmlCandidates).then(
      (xml) => sendResponse({
        ok: true,
        capture,
        xml
      })
    ).catch(
      () => sendResponse({
        ok: true,
        capture
      })
    );
    return true;
  }
  if (message?.type !== "mdtero.detect.request") {
    return false;
  }
  const detected = detectPaperInput({
    url: window.location.href,
    html: document.documentElement.outerHTML
  });
  sendResponse({ ok: true, detected });
  return false;
});
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (!shouldAcceptMdteroAuthMessage({
    currentOrigin: window.location.origin,
    eventOrigin: event.origin,
    data: event.data
  })) {
    return;
  }
  chrome.runtime.sendMessage({
    type: "mdtero.auth.save_token",
    token: event.data.token,
    email: event.data.email
  }).catch(() => {
  });
});
//# sourceMappingURL=content.js.map
