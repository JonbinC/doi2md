export const BRIDGE_NATIVE_HOST = "com.mdtero.browser_bridge";

export interface BrowserBridgeAcquireRequest {
  task_id: string;
  action: string;
  connector?: string;
  input?: string;
  source_doi?: string | null;
  source_url?: string | null;
  artifact_url?: string | null;
  timeouts?: {
    page_load_ms?: number;
    settle_ms?: number;
  };
}

export interface BrowserBridgeAcquireResponse {
  task_id: string;
  status: "succeeded" | "failed";
  connector?: string;
  artifact_kind?: string;
  payload_name?: string;
  payload_text?: string;
  payload_base64?: string;
  source_url?: string;
  page_title?: string;
  failure_code?: string;
  failure_message?: string;
}

interface ListenerEvent<T> {
  addListener(listener: (payload: T) => void): void;
}

interface NativePortLike {
  onMessage: ListenerEvent<unknown>;
  onDisconnect: ListenerEvent<unknown>;
  postMessage(message: unknown): void;
}

interface RuntimeLike {
  connectNative(hostName: string): NativePortLike;
}

interface AlarmLike {
  name?: string;
}

interface AlarmEventLike {
  addListener(listener: (alarm: AlarmLike) => void): void;
}

interface AlarmsLike {
  create(name: string, alarmInfo: { periodInMinutes: number }): void;
  onAlarm: AlarmEventLike;
}

interface BrowserBridgeOptions {
  runtime: RuntimeLike;
  alarms?: AlarmsLike;
  runtimeId?: string;
  acquire: (request: BrowserBridgeAcquireRequest) => Promise<BrowserBridgeAcquireResponse>;
}

export interface BrowserBridgeController {
  ensureConnected(): void;
  getStatus(): {
    state: "connected" | "unavailable" | "disconnected";
    runnerState: "idle" | "busy";
  };
}

const BRIDGE_HEARTBEAT_ALARM = "mdtero-browser-bridge-heartbeat";
const BRIDGE_HEARTBEAT_PERIOD_MINUTES = 0.5;
const BRIDGE_IDLE_POLL_DELAY_MS = 5000;
const BRIDGE_POST_TASK_POLL_DELAY_MS = 250;

function isAcquireEnvelope(
  payload: unknown
): payload is { type: "mdtero.bridge.acquire"; request: BrowserBridgeAcquireRequest } {
  return Boolean(
    payload &&
      typeof payload === "object" &&
      (payload as Record<string, unknown>).type === "mdtero.bridge.acquire" &&
      (payload as Record<string, unknown>).request &&
      typeof (payload as Record<string, unknown>).request === "object"
  );
}

function toBridgeFailure(
  request: BrowserBridgeAcquireRequest,
  error: unknown
): BrowserBridgeAcquireResponse {
  return {
    task_id: request.task_id,
    status: "failed",
    connector: request.connector,
    failure_code: "unsupported_route",
    failure_message: error instanceof Error ? error.message : "Browser acquisition failed."
  };
}

export function initializeBrowserBridge(options: BrowserBridgeOptions) {
  let port: NativePortLike | null = null;
  let runnerState: "idle" | "busy" = "idle";
  let bridgeState: "connected" | "unavailable" | "disconnected" = "disconnected";
  let idlePollTimer: ReturnType<typeof globalThis.setTimeout> | null = null;

  const clearIdlePoll = () => {
    if (idlePollTimer !== null) {
      globalThis.clearTimeout(idlePollTimer);
      idlePollTimer = null;
    }
  };

  const announceHello = (targetPort: NativePortLike) => {
    targetPort.postMessage({
      type: "mdtero.bridge.hello",
      runtime_id: options.runtimeId,
      runner_state: runnerState,
      capabilities: ["open_and_capture_html", "open_and_download_epub", "open_and_fetch_xml", "capture_current_tab"]
    });
  };

  const scheduleIdlePoll = (delayMs = BRIDGE_IDLE_POLL_DELAY_MS) => {
    clearIdlePoll();
    if (runnerState !== "idle") {
      return;
    }
    idlePollTimer = globalThis.setTimeout(() => {
      idlePollTimer = null;
      if (runnerState === "idle") {
        ensureConnected();
      }
    }, delayMs);
  };

  const connect = () => {
    if (port) {
      return port;
    }
    try {
      port = options.runtime.connectNative(BRIDGE_NATIVE_HOST);
    } catch {
      bridgeState = "unavailable";
      if (options.runtimeId) {
        console.warn("[mdtero-bridge] native host unavailable", options.runtimeId);
      }
      return null;
    }

    bridgeState = "connected";

    const connectedPort = port;
    connectedPort.onMessage.addListener((payload) => {
      if (!isAcquireEnvelope(payload)) {
        return;
      }
      runnerState = "busy";
      clearIdlePoll();
      Promise.resolve(options.acquire(payload.request))
        .then((response) => {
          connectedPort.postMessage(response);
        })
        .catch((error) => {
          connectedPort.postMessage(toBridgeFailure(payload.request, error));
        })
        .finally(() => {
          runnerState = "idle";
          scheduleIdlePoll(BRIDGE_POST_TASK_POLL_DELAY_MS);
        });
    });

    connectedPort.onDisconnect.addListener(() => {
      if (port === connectedPort) {
        port = null;
      }
      runnerState = "idle";
      bridgeState = "disconnected";
      clearIdlePoll();
    });

    announceHello(connectedPort);
    scheduleIdlePoll();

    return connectedPort;
  };

  const ensureConnected = () => {
    const activePort = connect();
    if (activePort) {
      announceHello(activePort);
      scheduleIdlePoll();
    }
  };

  if (options.alarms) {
    options.alarms.create(BRIDGE_HEARTBEAT_ALARM, {
      periodInMinutes: BRIDGE_HEARTBEAT_PERIOD_MINUTES
    });
    options.alarms.onAlarm.addListener((alarm) => {
      if (alarm?.name === BRIDGE_HEARTBEAT_ALARM) {
        ensureConnected();
      }
    });
  }

  connect();

  return {
    ensureConnected,
    getStatus() {
      return {
        state: bridgeState,
        runnerState
      };
    }
  };
}
