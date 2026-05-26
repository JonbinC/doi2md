import { createApiClient, createRouterSSOTClient } from "./lib/api";
import { buildCliFileParseCommand } from "./lib/cli-handoff";
import { runBrowserFileParseRequest } from "./lib/file-upload";
import { executeSsotActionSequence, fetchRoutePlanFromSsot } from "./lib/ssot-route";
import { readSettings, writeSettings } from "./lib/storage";

const client = createApiClient(readSettings);
const routerSSOT = createRouterSSOTClient(readSettings);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "mdtero.auth.save_token") {
    readSettings().then(settings => {
      return writeSettings({
        ...settings,
        token: message.token,
        email: message.email
      });
    }).then(() => sendResponse({ ok: true }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  // Router SSOT: new canonical routing via backend
  if (message?.type === "mdtero.parse.ssot.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }

      // Fetch canonical route plan from backend SSOT
      const routePlan = await fetchRoutePlanFromSsot(
        routerSSOT,
        message.input,
        message.pageContext?.tabUrl ? {
          tabUrl: message.pageContext.tabUrl,
          tabTitle: message.pageContext.tabTitle,
        } : undefined
      );

      const result = await executeSsotActionSequence(
        client,
        routePlan,
        {
          tabId: message.pageContext?.tabId,
          tabUrl: message.pageContext?.tabUrl,
          tabTitle: message.pageContext?.tabTitle,
          input: message.input,
        }
      );

      if (result.success && result.taskId) {
        return result.task ?? { task_id: result.taskId };
      }

      return {
        ok: false,
        error: formatSsotFailure(result),
        nextCommand: result.nextCommand,
      };
    })()
    .then((result) => {
      if (result && typeof result === "object" && "ok" in result && result.ok === false) {
        sendResponse(result);
        return;
      }
      sendResponse({ ok: true, result });
    })
    .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "mdtero.parse.file.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (!message.file) {
        throw new Error("No local file was provided.");
      }
      return runBrowserFileParseRequest(client, {
        file: message.file,
        filename: message.filename,
        artifactKind: message.artifactKind
      });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) =>
        sendResponse({
          ok: false,
          error: error.message,
          nextCommand: buildFileParseCommand(message.filename, message.artifactKind),
        })
      );
    return true;
  }

  if (message?.type === "mdtero.task.get") {
    client
      .getTask(message.taskId)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "mdtero.translate.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (message.sourceMarkdownPath) {
        return client.createTranslateTask({
          source_markdown_path: message.sourceMarkdownPath,
          target_language: message.targetLanguage,
          mode: message.mode
        });
      }
      if (!message.sourceTaskId || !message.sourceArtifactKey) {
        throw new Error("Parse a paper to Markdown first; no source Markdown artifact is available for translation.");
      }
      const artifact = await client.downloadArtifact(
        message.sourceTaskId,
        message.sourceArtifactKey,
        message.sourceFilename
      );
      const sourceMarkdownText = await artifact.blob.text();
      if (!sourceMarkdownText.trim()) {
        throw new Error("The Markdown artifact is empty and cannot be translated.");
      }
      return client.createTranslateTask({
        source_markdown_path: "",
        source_markdown_text: sourceMarkdownText,
        source_markdown_filename: artifact.filename || message.sourceFilename || "paper.md",
        target_language: message.targetLanguage,
        mode: message.mode
      });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  return false;
});

function formatSsotFailure(result: {
  error?: string;
  nextCommand?: string;
  requiresBrowserCapture?: boolean;
  requiresUpload?: boolean;
}) {
  if (result.requiresBrowserCapture) {
    return result.error || "Open the article page in this browser, make sure the full text is loaded, then retry current-page parse or upload the PDF/EPUB directly.";
  }
  if (result.requiresUpload) {
    return result.error || "Upload the PDF/EPUB/XML/HTML file directly so Mdtero can parse it.";
  }
  return result.error || "Action sequence failed";
}

function buildFileParseCommand(filename?: string, artifactKind?: "pdf" | "epub") {
  return buildCliFileParseCommand(filename, artifactKind);
}
