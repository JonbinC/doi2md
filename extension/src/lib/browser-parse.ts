import {
  buildElsevierLocalAcquireGuidance,
  requiresElsevierLocalAcquire,
} from "./elsevier";
import { normalizeSpringerInput } from "./springer";

interface ParseClientLike {
  createParseTask(payload: { input: string }): Promise<unknown>;
  createUploadedParseTask(payload: {
    paperFile: Blob;
    filename?: string;
    sourceInput?: string;
  }): Promise<unknown>;
  createParseFulltextV2Task(payload: {
    fulltextFile: Blob;
    filename?: string;
    sourceDoi?: string;
    sourceInput?: string;
  }): Promise<unknown>;
}

interface BrowserPageContext {
  tabId?: number;
  tabUrl?: string;
}

interface BrowserParseMessage {
  input: string;
  pageContext?: BrowserPageContext;
}

interface BrowserFileMessage {
  file: Blob;
  filename?: string;
  artifactKind?: "pdf" | "epub";
}

export async function runBrowserParseRequest(
  client: ParseClientLike,
  message: BrowserParseMessage,
): Promise<unknown> {
  if (requiresElsevierLocalAcquire(message.input)) {
    throw new Error(buildElsevierLocalAcquireGuidance());
  }

  const currentTabRawUploadTask = await tryCreateCurrentTabRawUploadTask(client, {
    input: message.input,
    pageContext: message.pageContext,
  });
  if (currentTabRawUploadTask) {
    return currentTabRawUploadTask;
  }

  return client.createParseTask({ input: message.input });
}

export async function runBrowserFileParseRequest(
  client: ParseClientLike,
  message: BrowserFileMessage,
): Promise<unknown> {
  const filename = String(message.filename || "").trim() || "paper.bin";
  return client.createUploadedParseTask({
    paperFile: message.file,
    filename,
    sourceInput: filename,
  });
}

function inferSourceDoi(input: string): string | undefined {
  const trimmed = String(input || "").trim();
  return /^10\.\S+/i.test(trimmed) ? trimmed : undefined;
}

function isArxivAbsReference(value?: string): boolean {
  const lowered = String(value || "").trim().toLowerCase();
  return lowered.includes("arxiv.org/abs/") || lowered.includes("arxiv:");
}

function shouldSkipArxivCurrentTabCapture(message: {
  input: string;
  pageContext?: { tabUrl?: string };
}): boolean {
  if (isArxivAbsReference(message.input)) {
    return true;
  }
  return isArxivAbsReference(message.pageContext?.tabUrl);
}

function describeCurrentTabCaptureFailure(params: {
  failureCode?: string;
  failureMessage?: string;
}) {
  const failureCode = String(params.failureCode || "").trim().toLowerCase();
  const failureMessage = String(params.failureMessage || "").trim();

  if (failureCode === "login_required") {
    return "This page still requires institutional or account sign-in. Open the article in your browser, finish login, then retry capture.";
  }
  if (failureCode === "challenge_page_detected") {
    return "This page is still behind a browser challenge. Finish the verification in the page, wait for the article to load, then retry capture.";
  }
  if (failureCode === "article_body_missing") {
    return "No article body was detected on the current page. Open the HTML full-text page instead of a PDF or download shell, then retry capture.";
  }
  if (failureCode === "content_script_unavailable") {
    return "Browser page capture is not ready yet. Reload the paper page or reopen the extension, then try again.";
  }

  return failureMessage || "Browser page capture did not succeed on the current page.";
}

async function tryCreateCurrentTabRawUploadTask(
  client: ParseClientLike,
  message: {
    input: string;
    pageContext?: BrowserPageContext;
  },
) {
  const tabId = message.pageContext?.tabId;
  if (!tabId) {
    return null;
  }
  if (shouldSkipArxivCurrentTabCapture(message)) {
    return null;
  }

  const response = await chrome.tabs.sendMessage(tabId, {
    type: "mdtero.capture_current_tab.request",
  });
  if (response?.xml?.ok && response.xml.payloadText) {
    return client.createParseFulltextV2Task({
      fulltextFile: new Blob([response.xml.payloadText], { type: "application/xml" }),
      filename: response.xml.payloadName || "paper.xml",
      sourceDoi:
        inferSourceDoi(message.input) ||
        normalizeSpringerInput(message.input, message.pageContext?.tabUrl) ||
        undefined,
      sourceInput: message.input,
    });
  }

  const capture = response?.capture;
  if (!response?.ok) {
    throw new Error(
      describeCurrentTabCaptureFailure({
        failureCode: "content_script_unavailable",
      }),
    );
  }
  if (!capture?.ok || !capture.html) {
    throw new Error(
      describeCurrentTabCaptureFailure({
        failureCode: capture?.failureCode,
        failureMessage: capture?.failureMessage,
      }),
    );
  }

  return client.createParseFulltextV2Task({
    fulltextFile: new Blob([capture.html], { type: "text/html" }),
    filename: capture.payloadName || "paper.html",
    sourceDoi: inferSourceDoi(message.input),
    sourceInput: message.input,
  });
}
