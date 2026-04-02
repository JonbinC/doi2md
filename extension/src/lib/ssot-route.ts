import type {
  ActionType,
  ExtensionRouteRequest,
  ExtensionRouteResponse,
} from "@mdtero/shared";

import { executeAction } from "./action-executor";

export interface SsotPageContext {
  tabId?: number;
  tabUrl?: string;
  tabTitle?: string;
}

export interface SsotExecutionContext extends SsotPageContext {
  input: string;
  springerOpenAccessApiKey?: string;
  elsevierApiKey?: string;
}

export interface RouteClientLike {
  fetchRoutePlan(payload: ExtensionRouteRequest): Promise<ExtensionRouteResponse>;
}

export interface ParseClientLike {
  createParseHelperBundleV2Task(payload: {
    helperBundleFile: Blob;
    filename?: string;
    sourceDoi?: string;
    sourceInput?: string;
  }): Promise<{ task_id: string }>;
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
  error?: string;
  requiresHelper?: boolean;
  requiresUpload?: boolean;
}> {
  for (const action of routePlan.action_sequence) {
    const result = await executeAction(action as ActionType, context, {
      top_connector: routePlan.top_connector,
      fail_closed: routePlan.fail_closed,
      user_message: routePlan.user_message,
      best_oa_url: routePlan.best_oa_url,
      acquisition_candidates: routePlan.acquisition_candidates,
    });

    if (result.success) {
      if (result.helperBundle) {
        try {
          const task = await parseClient.createParseHelperBundleV2Task({
            helperBundleFile: result.helperBundle,
            filename: result.filename || "helper-bundle.zip",
            sourceDoi: result.sourceDoi,
            sourceInput: context.input,
          });
          return { success: true, taskId: task.task_id };
        } catch (error) {
          if (routePlan.fail_closed) {
            return { success: false, error: String(error) };
          }
          continue;
        }
      }

      if (result.taskId) {
        return { success: true, taskId: result.taskId };
      }

      continue;
    }

    if (result.requiresHelper || result.requiresUpload) {
      return {
        success: false,
        requiresHelper: result.requiresHelper,
        requiresUpload: result.requiresUpload,
        error: result.error,
      };
    }

    if (routePlan.fail_closed) {
      return { success: false, error: result.error || "Action failed" };
    }
  }

  return { success: false, error: "No executable action succeeded" };
}
