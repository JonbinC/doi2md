import { describe, expect, it } from "vitest";

import {
  getPendingPopupTask,
  getReconnectablePendingTranslationTask,
  mergeSettings,
  resolveUiLanguage,
  summarizePopupState,
  upsertRecentTasks
} from "../src/lib/storage";

describe("mergeSettings", () => {
  it("preserves token and email when only apiBaseUrl changes", () => {
    expect(
      mergeSettings(
        {
          apiBaseUrl: "http://old",
          token: "token-1",
          email: "user@example.com",
          uiLanguage: "en"
        },
        { apiBaseUrl: "http://new" }
      )
    ).toEqual({
      apiBaseUrl: "http://new",
      token: "token-1",
      email: "user@example.com",
      uiLanguage: "en"
    });
  });

  it("summarizes stored popup state for the same detected input", () => {
    expect(
      summarizePopupState(
        {
          input: "10.1016/j.conbuildmat.2026.145877",
          parseTaskId: "task-1",
          parseFilename: "tang2026simulation.zip",
          translatedTaskId: "task-2",
          translatedFilename: "tang2026simulation.zh.md"
        },
        "10.1016/j.conbuildmat.2026.145877"
      )
    ).toEqual({
      parseTaskId: "task-1",
      parseFilename: "tang2026simulation.zip",
      translatedTaskId: "task-2",
      translatedFilename: "tang2026simulation.zh.md"
    });
  });

  it("resolves browser language into a compact ui language", () => {
    expect(resolveUiLanguage(undefined, "zh-CN")).toBe("zh");
    expect(resolveUiLanguage(undefined, "en-GB")).toBe("en");
    expect(resolveUiLanguage("zh", "en-US")).toBe("zh");
  });

  it("keeps recent tasks user-facing, deduplicated, and capped", () => {
    const recent = upsertRecentTasks(
      [
        {
          input: "10.1016/j.old.2025.1",
          label: "old2025paper",
          parseTaskId: "task-old",
          parseFilename: "old2025paper.zip"
        },
        {
          input: "10.1016/j.same.2026.1",
          label: "same2026paper",
          parseTaskId: "task-same-1",
          parseFilename: "same2026paper.zip"
        }
      ],
      {
        input: "10.1016/j.same.2026.1",
        label: "same2026paper",
        parseTaskId: "task-same-2",
        parseFilename: "same2026paper.zip",
        translatedTaskId: "task-same-translate",
        translatedFilename: "same2026paper.zh.md"
      },
      2
    );

    expect(recent).toEqual([
      {
        input: "10.1016/j.same.2026.1",
        label: "same2026paper",
        parseTaskId: "task-same-2",
        parseFilename: "same2026paper.zip",
        translatedTaskId: "task-same-translate",
        translatedFilename: "same2026paper.zh.md"
      },
      {
        input: "10.1016/j.old.2025.1",
        label: "old2025paper",
        parseTaskId: "task-old",
        parseFilename: "old2025paper.zip"
      }
    ]);
  });

  it("restores a pending translate task for the same detected input", () => {
    expect(
      getPendingPopupTask(
        {
          input: "10.1016/j.conbuildmat.2026.145877",
          parseTaskId: "task-1",
          parseFilename: "tang2026simulation.zip",
          parseMarkdownPath: "/tmp/tang2026simulation/paper.md",
          pendingTaskId: "task-translate-1",
          pendingTaskKind: "translate"
        },
        "10.1016/j.conbuildmat.2026.145877"
      )
    ).toEqual({
      taskId: "task-translate-1",
      kind: "translate"
    });
  });

  it("reuses the same pending translation for the same parsed markdown path", () => {
    expect(
      getReconnectablePendingTranslationTask(
        {
          input: "10.1016/j.conbuildmat.2026.145877",
          parseMarkdownPath: "/tmp/tang2026simulation/paper.md",
          pendingTaskId: "task-translate-1",
          pendingTaskKind: "translate"
        },
        "10.1016/j.conbuildmat.2026.145877",
        "/tmp/tang2026simulation/paper.md"
      )
    ).toEqual({
      taskId: "task-translate-1",
      kind: "translate"
    });

    expect(
      getReconnectablePendingTranslationTask(
        {
          input: "10.1016/j.conbuildmat.2026.145877",
          parseMarkdownPath: "/tmp/tang2026simulation/paper.md",
          pendingTaskId: "task-translate-1",
          pendingTaskKind: "translate"
        },
        "10.1016/j.conbuildmat.2026.145877",
        "/tmp/other/paper.md"
      )
    ).toBeUndefined();
  });
});
