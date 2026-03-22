// src/lib/detect.ts
var DOI_PATTERN = /10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i;
var ARXIV_PATTERN = /arxiv\.org\/(abs|pdf|html)\/([a-z\-]+\/\d{7}|[0-9]{4}\.[0-9]{4,5})/i;
function detectPaperInput(input) {
  const arxivMatch = input.url.match(ARXIV_PATTERN);
  if (arxivMatch) {
    return { kind: "arxiv", value: input.url };
  }
  const urlMatch = input.url.match(DOI_PATTERN);
  if (urlMatch) {
    return { kind: "doi", value: urlMatch[0] };
  }
  const metaDoiMatch = input.html.match(/citation_doi"\s+content="([^"]+)"/i);
  if (metaDoiMatch) {
    return { kind: "doi", value: metaDoiMatch[1] };
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

// src/lib/auth-bridge.ts
var TRUSTED_HOST_PATTERNS = [
  /^([a-z0-9-]+\.)*mdtero\.com$/i,
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
    return TRUSTED_HOST_PATTERNS.some((pattern) => pattern.test(url.hostname));
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
  return isMdteroAuthTokenPayload(event.data);
}

// src/content.ts
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
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
