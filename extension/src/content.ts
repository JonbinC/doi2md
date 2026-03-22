import { detectPaperInput } from "./lib/detect";
import { shouldAcceptMdteroAuthMessage } from "./lib/auth-bridge";

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
