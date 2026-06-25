import {
  buildChromeProxyConfig,
  isExpectedCampusOutlet,
  parseProxyUrl,
  summarizeCampusOutlet
} from "./proxy";
import type { MdteroSettings } from "./storage";

export async function applyProxySettings(
  settings: Pick<MdteroSettings, "proxyEnabled" | "proxyUrl">
): Promise<void> {
  if (!chrome.proxy?.settings) {
    return;
  }

  if (!settings.proxyEnabled || !settings.proxyUrl?.trim()) {
    await chrome.proxy.settings.clear({ scope: "regular" });
    return;
  }

  const parsed = parseProxyUrl(settings.proxyUrl);
  if (!parsed) {
    await chrome.proxy.settings.clear({ scope: "regular" });
    return;
  }

  await chrome.proxy.settings.set({
    value: buildChromeProxyConfig(parsed),
    scope: "regular"
  });
}

export async function verifyCampusProxyOutlet(): Promise<{
  ok: boolean;
  summary: ReturnType<typeof summarizeCampusOutlet>;
  message?: string;
}> {
  try {
    const response = await fetch("https://ifconfig.co/json");
    if (!response.ok) {
      return {
        ok: false,
        summary: {},
        message: `Campus proxy check failed with HTTP ${response.status}.`
      };
    }
    const payload = await response.json();
    const summary = summarizeCampusOutlet(payload);
    if (!isExpectedCampusOutlet(payload)) {
      return {
        ok: false,
        summary,
        message: "Campus proxy outlet is not AS786/Jisc/Nottingham."
      };
    }
    return { ok: true, summary };
  } catch (error) {
    return {
      ok: false,
      summary: {},
      message: (error as Error).message || "Campus proxy check failed."
    };
  }
}

export async function assertCampusProxyIfRequired(settings: MdteroSettings): Promise<void> {
  if (!settings.requireCampusProxy) {
    return;
  }
  if (!settings.proxyEnabled || !settings.proxyUrl?.trim()) {
    throw new Error("Campus proxy is required, but extension proxy settings are missing.");
  }
  const result = await verifyCampusProxyOutlet();
  if (!result.ok) {
    throw new Error(result.message || "Campus proxy outlet check failed.");
  }
}
