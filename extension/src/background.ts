import { createApiClient } from "./lib/api";
import { fetchElsevierXml, requiresElsevierLocalAcquire } from "./lib/elsevier";
import { readSettings, writeSettings } from "./lib/storage";

const client = createApiClient(readSettings);

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

  if (message?.type === "mdtero.parse.request") {
    (async () => {
      if (requiresElsevierLocalAcquire(message.input)) {
        if (!message.elsevierApiKey) {
          throw new Error("Elsevier API Key is required for Elsevier / ScienceDirect parsing.");
        }
        const uploaded = await fetchElsevierXml(message.input, message.elsevierApiKey);
        return client.createUploadedParseTask({
          xmlFile: uploaded.xmlBlob,
          filename: uploaded.filename,
          sourceDoi: uploaded.sourceDoi,
          sourceInput: uploaded.sourceInput
        });
      }
      return client.createParseTask({ input: message.input, elsevier_api_key: message.elsevierApiKey });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
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
    client
      .createTranslateTask({
        source_markdown_path: message.sourceMarkdownPath,
        target_language: message.targetLanguage,
        mode: message.mode
      })
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  return false;
});
