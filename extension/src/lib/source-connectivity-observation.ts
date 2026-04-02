export interface SourceConnectivityObservation {
  browser_bridge: {
    ready: boolean;
    state: string;
    runnerState: string;
  };
  local_helper: {
    ready: boolean;
    state: string;
    runnerState: string;
  };
}

export function buildSourceConnectivityObservation(status: {
  state?: string;
  runnerState?: string;
} | null | undefined): SourceConnectivityObservation {
  const state = status?.state ?? "unavailable";
  const runnerState = status?.runnerState ?? "idle";
  const ready = state === "connected";
  return {
    browser_bridge: {
      ready,
      state,
      runnerState,
    },
    local_helper: {
      ready,
      state,
      runnerState,
    }
  };
}
