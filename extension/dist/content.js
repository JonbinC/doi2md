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
  const htmlMatch = input.html.match(DOI_PATTERN);
  if (htmlMatch) {
    return { kind: "doi", value: htmlMatch[0] };
  }
  return null;
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
function normalizeXmlCandidateUrl(params) {
  let candidate = String(params.candidate || "").trim();
  if (!candidate) {
    return null;
  }
  if (candidate.startsWith("http://")) {
    candidate = `https://${candidate.slice("http://".length)}`;
  }
  try {
    const parsed = new URL(candidate);
    const isLegacySpringerJats = parsed.hostname === "api.springer.com" && parsed.pathname.replace(/\/+$/, "") === "/xmldata/jats";
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
function extractXmlCandidateUrls(params) {
  const html = String(params.html || "");
  const pageUrl = String(params.pageUrl || "");
  const candidates = [];
  const doi = matchMetaContent2(html, ["citation_doi", "prism.doi", "prism:doi", "dc.identifier", "dc:identifier"])?.match(
    /10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i
  )?.[0];
  if (doi && params.springerOpenAccessApiKey && /springer/i.test(pageUrl)) {
    pushUniqueCandidate(
      candidates,
      `https://api.springernature.com/openaccess/jats?q=doi:${encodeURIComponent(doi)}&api_key=${encodeURIComponent(params.springerOpenAccessApiKey)}`
    );
  }
  const explicitXml = matchMetaContent2(html, ["citation_xml_url", "citation_springer_api_url"]);
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
  const isPdfEmbedShell = hasPdfEmbedShellSignals || hasPdfDownloadOnlySignals && !hasArticleSignals;
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
async function downloadEpubArtifact(artifactUrl) {
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
    data && typeof data === "object" && "type" in data && "token" in data && "email" in data && data.type === "mdtero.auth.token" && typeof data.token === "string" && typeof data.email === "string" && data.token && data.email
  );
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

// src/lib/bridge-wake.ts
var BRIDGE_SUPPORTED_URL_PATTERNS = [
  "arxiv.org",
  "dl.acm.org",
  "ieeexplore.ieee.org",
  "nature.com",
  "pubs.acs.org",
  "pubs.rsc.org",
  "sciencedirect.com/science/article/pii/",
  "techrxiv.org",
  "link.springer.com",
  "mdpi.com",
  "springer.com",
  "springernature.com",
  "onlinelibrary.wiley.com",
  "tandfonline.com"
];
function isBridgeSupportedPage(url) {
  const normalized = String(url || "").trim().toLowerCase();
  return BRIDGE_SUPPORTED_URL_PATTERNS.some((pattern) => normalized.includes(pattern));
}
function announceBridgePageReady(runtime, url) {
  if (!runtime?.sendMessage || !url || !isBridgeSupportedPage(url)) {
    return;
  }
  void runtime.sendMessage({
    type: "mdtero.bridge.page_ready",
    url
  }).catch(() => {
  });
}

// src/content.ts
announceBridgePageReady(chrome.runtime, window.location.href);
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
      pageUrl: window.location.href,
      springerOpenAccessApiKey: String(message.springerOpenAccessApiKey || "")
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
