import { DEFAULT_API_BASE_URL } from "@mdtero/shared";

export type UiLanguage = "en" | "zh";

export interface MdteroSettings {
  apiBaseUrl: string;
  token?: string;
  email?: string;
  uiLanguage?: UiLanguage;
  elsevierApiKey?: string;
  springerOpenAccessApiKey?: string;
}

export interface PopupState {
  input: string;
  parseTaskId?: string;
  parseArtifactKey?: string;
  parseFilename?: string;
  parseMarkdownPath?: string;
  translatedTaskId?: string;
  translatedFilename?: string;
  pendingTaskId?: string;
  pendingTaskKind?: "parse" | "translate";
}

export interface RecentTaskSummary {
  input: string;
  label: string;
  parseTaskId?: string;
  parseArtifactKey?: string;
  parseFilename?: string;
  translatedTaskId?: string;
  translatedFilename?: string;
}

export const SETTINGS_KEY = "mdtero_settings";
export const POPUP_STATE_KEY = "mdtero_popup_state";
export const RECENT_TASKS_KEY = "mdtero_recent_tasks";

export function resolveUiLanguage(
  preferred?: UiLanguage,
  browserLanguage?: string
): UiLanguage {
  if (preferred === "en" || preferred === "zh") {
    return preferred;
  }
  return browserLanguage?.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function mergeSettings(
  current: MdteroSettings,
  next: Partial<MdteroSettings>
): MdteroSettings {
  return {
    ...current,
    ...next
  };
}

export async function readSettings(): Promise<MdteroSettings> {
  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  const current = stored[SETTINGS_KEY] ?? { apiBaseUrl: DEFAULT_API_BASE_URL };
  return {
    apiBaseUrl: current.apiBaseUrl ?? DEFAULT_API_BASE_URL,
    token: current.token,
    email: current.email,
    elsevierApiKey: current.elsevierApiKey,
    springerOpenAccessApiKey: current.springerOpenAccessApiKey,
    uiLanguage: resolveUiLanguage(current.uiLanguage, globalThis.navigator?.language)
  };
}

export async function writeSettings(next: MdteroSettings): Promise<void> {
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
}

export async function readPopupState(): Promise<PopupState | undefined> {
  const stored = await chrome.storage.local.get(POPUP_STATE_KEY);
  return stored[POPUP_STATE_KEY];
}

export async function writePopupState(next: PopupState): Promise<void> {
  await chrome.storage.local.set({ [POPUP_STATE_KEY]: next });
}

export async function readRecentTasks(): Promise<RecentTaskSummary[]> {
  const stored = await chrome.storage.local.get(RECENT_TASKS_KEY);
  return stored[RECENT_TASKS_KEY] ?? [];
}

export async function writeRecentTasks(next: RecentTaskSummary[]): Promise<void> {
  await chrome.storage.local.set({ [RECENT_TASKS_KEY]: next });
}

export function upsertRecentTasks(
  current: RecentTaskSummary[],
  next: RecentTaskSummary,
  limit = 5
): RecentTaskSummary[] {
  const deduped = current.filter((item) => item.input !== next.input);
  return [next, ...deduped].slice(0, limit);
}

export function summarizePopupState(
  state: PopupState | undefined,
  detectedInput: string
): Omit<PopupState, "input" | "parseMarkdownPath"> | undefined {
  if (!state || state.input !== detectedInput) {
    return undefined;
  }
  const { input: _input, parseMarkdownPath: _parseMarkdownPath, ...summary } = state;
  return summary;
}

export function getPendingPopupTask(
  state: PopupState | undefined,
  detectedInput: string
): { taskId: string; kind: "parse" | "translate" } | undefined {
  if (!state || state.input !== detectedInput || !state.pendingTaskId || !state.pendingTaskKind) {
    return undefined;
  }
  return {
    taskId: state.pendingTaskId,
    kind: state.pendingTaskKind
  };
}

export function getReconnectablePendingTranslationTask(
  state: PopupState | undefined,
  detectedInput: string,
  parseMarkdownPath: string
): { taskId: string; kind: "translate" } | undefined {
  if (
    !state ||
    state.input !== detectedInput ||
    state.pendingTaskKind !== "translate" ||
    !state.pendingTaskId ||
    state.parseMarkdownPath !== parseMarkdownPath
  ) {
    return undefined;
  }

  return {
    taskId: state.pendingTaskId,
    kind: "translate"
  };
}
