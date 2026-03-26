import { detectPaperInput } from "./lib/detect";
import { buildPageCaptureResult, downloadEpubArtifact, extractXmlCandidateUrls, fetchXmlArtifact } from "./lib/page-capture";
import { shouldAcceptMdteroAuthMessage } from "./lib/auth-bridge";
import { announceBridgePageReady } from "./lib/bridge-wake";

announceBridgePageReady(chrome.runtime, window.location.href);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "mdtero.download_epub.request") {
    downloadEpubArtifact(String(message.artifactUrl || ""))
      .then((download) => sendResponse({ ok: true, download }))
      .catch((error: Error) =>
        sendResponse({
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
    fetchXmlArtifact(candidates)
      .then((xml) => sendResponse({ ok: true, xml }))
      .catch((error: Error) =>
        sendResponse({
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
    fetchXmlArtifact(xmlCandidates)
      .then((xml) =>
        sendResponse({
          ok: true,
          capture,
          xml
        })
      )
      .catch(() =>
        sendResponse({
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

// Listen for token updates from the web app
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (
    !shouldAcceptMdteroAuthMessage({
      currentOrigin: window.location.origin,
      eventOrigin: event.origin,
      data: event.data
    })
  ) {
    return;
  }

  chrome.runtime.sendMessage({
    type: "mdtero.auth.save_token",
    token: event.data.token,
    email: event.data.email
  }).catch(() => {
    // Ignore errors if background script isn't ready
  });
});
