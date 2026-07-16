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
  elsevierApiKey?: string;
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
  if (shouldSubmitServerParse(routePlan)) {
    return submitServerParse(parseClient, context.input);
  }

  let lastActionError: string | undefined;
  let lastNextCommand: string | undefined;

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

    if (action === "fetch_elsevier_xml") {
      const serverResult = await submitServerParse(parseClient, context.input);
      if (serverResult.success) {
        return serverResult;
      }
      return {
        ...serverResult,
        error: `${result.error || "Elsevier XML fetch failed"}; backend fallback failed: ${serverResult.error}`,
      };
    }

    lastActionError = result.error || lastActionError;
    lastNextCommand = result.nextCommand || lastNextCommand;
    // Planned action_sequence is an ordered attempt list. Keep walking the
    // remaining actions even when fail_closed is true; fail-closed applies to
    // inventing undocumented fallbacks after the sequence is exhausted, and to
    // raw-upload submission failures above.
  }

  return {
    success: false,
    error: lastActionError || "No executable action succeeded",
    nextCommand: lastNextCommand || buildCliParseCommand(context.input),
  };
}

async function submitServerParse(parseClient: ParseClientLike, input: string) {
  try {
    const task = await parseClient.createParseTask({ input });
    return { success: true, taskId: task.task_id, task };
  } catch (error) {
    return {
      success: false,
      error: String(error),
      nextCommand: buildCliParseCommand(input),
    };
  }
}

function shouldSubmitServerParse(routePlan: ExtensionRouteResponse): boolean {
  if (routePlan.route_planner_fallback || routePlan.action_sequence.includes("server_parse")) {
    return true;
  }
  return routePlan.action_sequence.some((action) => SERVER_SIDE_CREDENTIAL_ACTIONS.has(action));
}

const SERVER_SIDE_CREDENTIAL_ACTIONS = new Set([
  "fetch_wiley_tdm_pdf",
]);

function inferArtifactKindFromFilename(filename?: string): string | undefined {
  const normalized = String(filename || "").trim().toLowerCase();
  if (normalized.endsWith(".pdf")) return "pdf";
  if (normalized.endsWith(".epub")) return "epub";
  if (normalized.endsWith(".html") || normalized.endsWith(".htm")) return "html";
  if (normalized.endsWith(".xml") || normalized.endsWith(".nxml") || normalized.endsWith(".tei")) return "xml";
  return undefined;
}
