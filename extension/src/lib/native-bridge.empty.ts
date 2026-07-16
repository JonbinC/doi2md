export const HOST_BRIDGE_NAME = "";

export function isHostBridgeAvailable(): boolean {
  return false;
}

export async function sendHostBridgeMessage(_message: Record<string, unknown>): Promise<Record<string, unknown>> {
  throw new Error("Host bridge is disabled in this build.");
}

export async function pingHostBridge(): Promise<Record<string, unknown>> {
  throw new Error("Host bridge is disabled in this build.");
}

export async function dequeueHostBridgeJobs(_limit = 1): Promise<Array<Record<string, unknown>>> {
  return [];
}

export async function completeHostBridgeJob(_params: {
  jobId: string;
  taskId?: string;
  error?: string;
  result?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  throw new Error("Host bridge is disabled in this build.");
}
