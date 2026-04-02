import type { PdfEngine } from "@mdtero/shared";

import {
  buildElsevierLocalAcquireGuidance,
  fetchElsevierXml,
  requiresElsevierLocalAcquire,
} from "./elsevier";
import {
  buildHelperBundleBlob,
  inferBrowserHelperBundleAccess,
  inferBrowserHelperBundleConnector,
} from "./helper-bundle";
import { fetchSpringerOpenAccessJats, normalizeSpringerInput } from "./springer";

interface ParseClientLike {
  createParseTask(payload: { input: string }): Promise<unknown>;
  createParseFulltextV2Task(payload: {
    fulltextFile: Blob;
    filename?: string;
    sourceDoi?: string;
    sourceInput?: string;
  }): Promise<unknown>;
  createParseHelperBundleV2Task(payload: {
    helperBundleFile: Blob;
    filename?: string;
    sourceDoi?: string;
    sourceInput?: string;
    pdfEngine?: PdfEngine;
  }): Promise<unknown>;
}

interface LegacyPageContext {
  tabId?: number;
  tabUrl?: string;
}

interface LegacyParseMessage {
  input: string;
  elsevierApiKey?: string;
  springerOpenAccessApiKey?: string;
  pageContext?: LegacyPageContext;
}

interface LegacyFileMessage {
  file: Blob;
  filename?: string;
  artifactKind?: "pdf" | "epub";
  pdfEngine?: PdfEngine;
}

export async function runLegacyParseRequest(
  client: ParseClientLike,
  message: LegacyParseMessage,
): Promise<unknown> {
  if (requiresElsevierLocalAcquire(message.input)) {
    if (!message.elsevierApiKey) {
      throw new Error(buildElsevierLocalAcquireGuidance());
    }
    const uploaded = await fetchElsevierXml(message.input, message.elsevierApiKey);
    const helperBundle = buildHelperBundleBlob({
      connector: "elsevier_article_retrieval_api",
      artifactKind: "structured_xml",
      payload: await uploaded.xmlBlob.arrayBuffer(),
      payloadName: uploaded.filename,
      extraFiles: uploaded.bundleExtraFiles,
      sourceDoi: uploaded.sourceDoi,
      access: "licensed",
    });
    return client.createParseHelperBundleV2Task({
      helperBundleFile: helperBundle,
      filename: "helper-bundle.zip",
      sourceDoi: uploaded.sourceDoi,
      sourceInput: uploaded.sourceInput,
    });
  }

  const springerSourceDoi = normalizeSpringerInput(message.input, message.pageContext?.tabUrl);
  if (springerSourceDoi && message.springerOpenAccessApiKey) {
    try {
      const uploaded = await fetchSpringerOpenAccessJats(
        message.input,
        message.springerOpenAccessApiKey,
        message.pageContext?.tabUrl,
      );
      return client.createParseFulltextV2Task({
        fulltextFile: uploaded.xmlBlob,
        filename: uploaded.filename,
        sourceDoi: uploaded.sourceDoi,
        sourceInput: uploaded.sourceInput,
      });
    } catch {
      // Fall through to current-tab or generic parse.
    }
  }

  const currentTabBundleTask = await tryCreateCurrentTabHelperBundleTask(client, {
    input: message.input,
    springerOpenAccessApiKey: message.springerOpenAccessApiKey,
    pageContext: message.pageContext,
  });
  if (currentTabBundleTask) {
    return currentTabBundleTask;
  }

  return client.createParseTask({ input: message.input });
}

export async function runLegacyFileParseRequest(
  client: ParseClientLike,
  message: LegacyFileMessage,
): Promise<unknown> {
  const filename = String(message.filename || "").trim() || "paper.bin";
  const artifactKind = message.artifactKind === "epub" ? "epub" : "pdf";
  const sourceType =
    artifactKind === "pdf"
      ? "browser_extension_local_upload_pdf"
      : "browser_extension_local_upload_epub";

  const helperBundle = buildHelperBundleBlob({
    connector: "local_file_upload",
    artifactKind,
    payload: await message.file.arrayBuffer(),
    payloadName: filename,
    sourceType,
    sourceUrl: `file://${filename}`,
    acquisitionMode: "browser_extension_local_upload",
    userPrivateRetention: true,
  });

  return client.createParseHelperBundleV2Task({
    helperBundleFile: helperBundle,
    filename: "helper-bundle.zip",
    sourceInput: filename,
    pdfEngine: artifactKind === "pdf" ? message.pdfEngine : undefined,
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

async function tryCreateCurrentTabHelperBundleTask(
  client: ParseClientLike,
  message: {
    input: string;
    springerOpenAccessApiKey?: string;
    pageContext?: LegacyPageContext;
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
    springerOpenAccessApiKey: message.springerOpenAccessApiKey,
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

  const connector = inferBrowserHelperBundleConnector(
    message.input,
    message.pageContext?.tabUrl || capture.sourceUrl,
  );
  const helperBundle = buildHelperBundleBlob({
    connector,
    artifactKind: "html",
    payload: capture.html,
    payloadName: capture.payloadName || "paper.html",
    sourceDoi: inferSourceDoi(message.input),
    sourceUrl: message.pageContext?.tabUrl || capture.sourceUrl || undefined,
    access: inferBrowserHelperBundleAccess(connector),
  });

  return client.createParseHelperBundleV2Task({
    helperBundleFile: helperBundle,
    filename: "helper-bundle.zip",
    sourceDoi: inferSourceDoi(message.input),
    sourceInput: message.input,
  });
}
