export async function sendTabMessageWithInjection(tabId: number, message: unknown): Promise<any> {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (firstError) {
    if (!canInjectContentScript(firstError)) {
      throw firstError;
    }
    await chrome.scripting.executeScript({
      target: { tabId },
      files: [getContentScriptFile()],
    });
    return chrome.tabs.sendMessage(tabId, message);
  }
}

export function getContentScriptFile(): string {
  const scripts = chrome.runtime.getManifest?.().content_scripts || [];
  for (const script of scripts) {
    const firstFile = script.js?.[0];
    if (firstFile && firstFile.includes("content.js")) {
      return firstFile;
    }
  }
  return "content.js";
}

export function canInjectContentScript(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error || "");
  return (
    /receiving end does not exist/i.test(message) ||
    /could not establish connection/i.test(message) ||
    /no tab with id/i.test(message)
  );
}
