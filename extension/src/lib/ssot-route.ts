import type {
  ActionType,
  ExtensionRouteRequest,
  ExtensionRouteResponse,
  ParseTaskResponse,
} from "@mdtero/shared";

import { executeAction } from "./action-executor";
import { buildCliParseCommand } from "./cli-handoff";

export interface SsotPageContext {
  tabId?: number;
  tabUrl?: string;
  tabTitle?: string;
}

export interface SsotExecutionContext extends SsotPageContext {
  input: string;
}

export interface RouteClientLike {
  fetchRoutePlan(payload: ExtensionRouteRequest): Promise<ExtensionRouteResponse>;
}

export interface ParseClientLike {
  createParseTask(payload: { input: string }): Promise<ParseTaskResponse>;
  createRawUploadTask(payload: {
    rawFile: Blob;
    filename?: string;
    sourceDoi?: string;
    sourceInput?: string;
    artifactKind?: string;
  }): Promise<ParseTaskResponse>;
}

export async function fetchRoutePlanFromSsot(
  routeClient: RouteClientLike,
  input: string,
  pageContext?: Omit<SsotPageContext, "tabId">,
): Promise<ExtensionRouteResponse> {
  return routeClient.fetchRoutePlan({
    input,
    page_url: pageContext?.tabUrl,
    page_title: pageContext?.tabTitle,
  });
}

export async function executeSsotActionSequence(
  parseClient: ParseClientLike,
  routePlan: ExtensionRouteResponse,
  context: SsotExecutionContext,
): Promise<{
  success: boolean;
  taskId?: string;
  task?: ParseTaskResponse;
  error?: string;
  nextCommand?: string;
  requiresBrowserCapture?: boolean;
  requiresUpload?: boolean;
}> {
  if (routePlan.route_planner_fallback || routePlan.action_sequence.includes("server_parse")) {
    try {
      const task = await parseClient.createParseTask({ input: context.input });
      return { success: true, taskId: task.task_id, task };
    } catch (error) {
      return {
        success: false,
        error: String(error),
        nextCommand: buildCliParseCommand(context.input),
      };
    }
  }

  for (const action of routePlan.action_sequence) {
    const result = await executeAction(action as ActionType, context, {
      top_connector: routePlan.top_connector,
      fail_closed: routePlan.fail_closed,
      user_message: routePlan.user_message,
      best_oa_url: routePlan.best_oa_url,
      acquisition_candidates: routePlan.acquisition_candidates,
      client_handoff_candidates: routePlan.client_handoff_candidates,
      publisher_capabilities: routePlan.publisher_capabilities,
    });

    if (result.success) {
      if (result.rawArtifact) {
        try {
          const task = await parseClient.createRawUploadTask({
            rawFile: result.rawArtifact,
            filename: result.filename || "paper.fulltext",
            sourceDoi: result.sourceDoi,
            sourceInput: context.input,
            artifactKind: result.artifactKind || inferArtifactKindFromFilename(result.filename),
          });
          return { success: true, taskId: task.task_id, task };
        } catch (error) {
          if (routePlan.fail_closed) {
            return { success: false, error: String(error), nextCommand: result.nextCommand || buildCliParseCommand(context.input) };
          }
          continue;
        }
      }

      if (result.taskId) {
        return { success: true, taskId: result.taskId };
      }

      continue;
    }

    if (result.requiresBrowserCapture || result.requiresUpload) {
      return {
        success: false,
        requiresBrowserCapture: result.requiresBrowserCapture,
        requiresUpload: result.requiresUpload,
        error: result.error,
        nextCommand: result.nextCommand || buildCliParseCommand(context.input),
      };
    }

    if (routePlan.fail_closed) {
      return { success: false, error: result.error || "Action failed", nextCommand: result.nextCommand || buildCliParseCommand(context.input) };
    }
  }

  return { success: false, error: "No executable action succeeded", nextCommand: buildCliParseCommand(context.input) };
}

function inferArtifactKindFromFilename(filename?: string): string | undefined {
  const normalized = String(filename || "").trim().toLowerCase();
  if (normalized.endsWith(".pdf")) return "pdf";
  if (normalized.endsWith(".epub")) return "epub";
  if (normalized.endsWith(".html") || normalized.endsWith(".htm")) return "html";
  if (normalized.endsWith(".xml") || normalized.endsWith(".nxml") || normalized.endsWith(".tei")) return "xml";
  return undefined;
}
