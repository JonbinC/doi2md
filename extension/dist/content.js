// src/lib/detect.ts
var DOI_PATTERN = /10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i;
function detectPaperInput(input) {
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
//# sourceMappingURL=content.js.map
