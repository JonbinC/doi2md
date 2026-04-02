import { describe, expect, it, vi } from "vitest";

import {
  BRIDGE_NATIVE_HOST,
  initializeBrowserBridge
} from "../src/lib/browser-bridge";

function createEventSink() {
  const listeners: Array<(payload: unknown) => void> = [];
  return {
    addListener(listener: (payload: unknown) => void) {
      listeners.push(listener);
    },
    emit(payload: unknown) {
      listeners.forEach((listener) => listener(payload));
    }
  };
}

function createVoidEventSink() {
  const listeners: Array<() => void> = [];
  return {
    addListener(listener: () => void) {
      listeners.push(listener);
    },
    emit() {
      listeners.forEach((listener) => listener());
    }
  };
}

describe("initializeBrowserBridge", () => {
  it("connects to the native host and announces bridge readiness", async () => {
    const onMessage = createEventSink();
    const onDisconnect = createEventSink();
    const postMessage = vi.fn();
    const connectNative = vi.fn(() => ({
      onMessage,
      onDisconnect,
      postMessage
    }));

    initializeBrowserBridge({
      runtime: { connectNative } as never,
      acquire: vi.fn()
    });

    expect(connectNative).toHaveBeenCalledWith(BRIDGE_NATIVE_HOST);
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "mdtero.bridge.hello",
        runner_state: "idle"
      })
    );
  });

  it("runs the acquire handler for bridge acquisition messages and posts the result", async () => {
    const onMessage = createEventSink();
    const onDisconnect = createEventSink();
    const postMessage = vi.fn();
    const acquire = vi.fn().mockResolvedValue({
      task_id: "task-1",
      status: "succeeded",
      artifact_kind: "html",
      connector: "springer_subscription_connector",
      payload_name: "paper.html"
    });

    initializeBrowserBridge({
      runtime: {
        connectNative: () => ({
          onMessage,
          onDisconnect,
          postMessage
        })
      } as never,
      acquire
    });

    onMessage.emit({
      type: "mdtero.bridge.acquire",
      request: {
        task_id: "task-1",
        action: "open_and_capture_html",
        connector: "springer_subscription_connector",
        input: "10.1000/example"
      }
    });

    await vi.waitFor(() => {
      expect(acquire).toHaveBeenCalledWith(
        expect.objectContaining({
          task_id: "task-1",
          action: "open_and_capture_html"
        })
      );
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          task_id: "task-1",
          status: "succeeded"
        })
      );
    });
  });

  it("maps handler failures into bridge failure responses", async () => {
    const onMessage = createEventSink();
    const onDisconnect = createEventSink();
    const postMessage = vi.fn();
    const acquire = vi.fn().mockRejectedValue(new Error("not yet implemented"));

    initializeBrowserBridge({
      runtime: {
        connectNative: () => ({
          onMessage,
          onDisconnect,
          postMessage
        })
      } as never,
      acquire
    });

    onMessage.emit({
      type: "mdtero.bridge.acquire",
      request: {
        task_id: "task-2",
        action: "open_and_capture_html",
        connector: "wiley_tdm",
        input: "10.1000/example"
      }
    });

    await vi.waitFor(() => {
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          task_id: "task-2",
          status: "failed",
          failure_code: "unsupported_route"
        })
      );
    });
  });

  it("serializes bridge acquisition messages so only one browser acquire runs at a time", async () => {
    const onMessage = createEventSink();
    const onDisconnect = createEventSink();
    const postMessage = vi.fn();
    let releaseFirst: (() => void) | null = null;
    const acquire = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            releaseFirst = () =>
              resolve({
                task_id: "task-1",
                status: "succeeded",
                artifact_kind: "html",
                payload_name: "paper.html"
              });
          })
      )
      .mockResolvedValueOnce({
        task_id: "task-2",
        status: "succeeded",
        artifact_kind: "html",
        payload_name: "paper.html"
      });

    initializeBrowserBridge({
      runtime: {
        connectNative: () => ({
          onMessage,
          onDisconnect,
          postMessage
        })
      } as never,
      acquire
    });

    onMessage.emit({
      type: "mdtero.bridge.acquire",
      request: {
        task_id: "task-1",
        action: "open_and_capture_html",
        input: "https://example.org/one"
      }
    });
    onMessage.emit({
      type: "mdtero.bridge.acquire",
      request: {
        task_id: "task-2",
        action: "open_and_capture_html",
        input: "https://example.org/two"
      }
    });

    await vi.waitFor(() => {
      expect(acquire).toHaveBeenCalledTimes(1);
      expect(acquire).toHaveBeenNthCalledWith(
        1,
        expect.objectContaining({
          task_id: "task-1"
        })
      );
    });

    releaseFirst?.();

    await vi.waitFor(() => {
      expect(acquire).toHaveBeenCalledTimes(2);
      expect(acquire).toHaveBeenNthCalledWith(
        2,
        expect.objectContaining({
          task_id: "task-2"
        })
      );
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          task_id: "task-1",
          status: "succeeded"
        })
      );
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          task_id: "task-2",
          status: "succeeded"
        })
      );
    });
  });

  it("fails soft when native host is not registered yet", async () => {
    const connectNative = vi.fn(() => {
      throw new Error("Specified native messaging host not found.");
    });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    const controller = initializeBrowserBridge({
        runtime: { connectNative } as never,
        runtimeId: "runtime-demo-id",
        acquire: vi.fn()
      });
    expect(warn).toHaveBeenCalledWith(
      "[mdtero-bridge] native host unavailable",
      "runtime-demo-id"
    );
    expect(controller.getStatus()).toEqual({
      state: "unavailable",
      runnerState: "idle"
    });
    warn.mockRestore();
  });

  it("creates a heartbeat alarm and reconnects after disconnect", async () => {
    const firstOnMessage = createEventSink();
    const firstOnDisconnect = createVoidEventSink();
    const firstPostMessage = vi.fn();
    const secondOnMessage = createEventSink();
    const secondOnDisconnect = createVoidEventSink();
    const secondPostMessage = vi.fn();
    const create = vi.fn();
    const onAlarm = createEventSink();
    const connectNative = vi
      .fn()
      .mockReturnValueOnce({
        onMessage: firstOnMessage,
        onDisconnect: firstOnDisconnect,
        postMessage: firstPostMessage
      })
      .mockReturnValueOnce({
        onMessage: secondOnMessage,
        onDisconnect: secondOnDisconnect,
        postMessage: secondPostMessage
      });

    initializeBrowserBridge({
      runtime: {
        connectNative
      } as never,
      alarms: {
        create,
        onAlarm
      } as never,
      acquire: vi.fn()
    });

    expect(create).toHaveBeenCalledWith(
      "mdtero-browser-bridge-heartbeat",
      expect.objectContaining({
        periodInMinutes: 0.5
      })
    );

    firstOnDisconnect.emit();
    onAlarm.emit({ name: "mdtero-browser-bridge-heartbeat" });

    expect(connectNative).toHaveBeenCalledTimes(2);
    expect(secondPostMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "mdtero.bridge.hello"
      })
    );
  });

  it("re-announces bridge readiness on heartbeat even when the port is still alive", async () => {
    const onMessage = createEventSink();
    const onDisconnect = createVoidEventSink();
    const postMessage = vi.fn();
    const create = vi.fn();
    const onAlarm = createEventSink();
    const connectNative = vi.fn().mockReturnValue({
      onMessage,
      onDisconnect,
      postMessage
    });

    initializeBrowserBridge({
      runtime: {
        connectNative
      } as never,
      alarms: {
        create,
        onAlarm
      } as never,
      acquire: vi.fn()
    });

    expect(connectNative).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledTimes(1);

    onAlarm.emit({ name: "mdtero-browser-bridge-heartbeat" });

    expect(connectNative).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledTimes(2);
    expect(postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "mdtero.bridge.hello"
      })
    );
  });

  it("keeps polling for queued work while the bridge stays idle", () => {
    vi.useFakeTimers();

    try {
      const onMessage = createEventSink();
      const onDisconnect = createVoidEventSink();
      const postMessage = vi.fn();
      const connectNative = vi.fn().mockReturnValue({
        onMessage,
        onDisconnect,
        postMessage
      });

      initializeBrowserBridge({
        runtime: {
          connectNative
        } as never,
        acquire: vi.fn()
      });

      expect(postMessage).toHaveBeenCalledTimes(1);

      vi.advanceTimersByTime(5000);

      expect(postMessage).toHaveBeenCalledTimes(2);
      expect(postMessage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          type: "mdtero.bridge.hello",
          runner_state: "idle"
        })
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("suppresses idle polling while an acquisition task is still running", async () => {
    vi.useFakeTimers();

    try {
      const onMessage = createEventSink();
      const onDisconnect = createVoidEventSink();
      const postMessage = vi.fn();
      let resolveAcquire: ((value: unknown) => void) | null = null;
      const acquire = vi.fn(
        () =>
          new Promise((resolve) => {
            resolveAcquire = resolve;
          })
      );

      initializeBrowserBridge({
        runtime: {
          connectNative: () => ({
            onMessage,
            onDisconnect,
            postMessage
          })
        } as never,
        acquire
      });

      onMessage.emit({
        type: "mdtero.bridge.acquire",
        request: {
          task_id: "task-busy",
          action: "open_and_capture_html",
          connector: "springer_subscription_connector",
          input: "10.1000/demo"
        }
      });

      await vi.waitFor(() => {
        expect(acquire).toHaveBeenCalledTimes(1);
      });
      vi.advanceTimersByTime(5000);
      await Promise.resolve();

      expect(postMessage).toHaveBeenCalledTimes(1);

      resolveAcquire?.({
        task_id: "task-busy",
        status: "succeeded",
        connector: "springer_subscription_connector",
        artifact_kind: "html",
        payload_name: "paper.html"
      });

      await vi.waitFor(() => {
        expect(postMessage).toHaveBeenCalledWith(
          expect.objectContaining({
            task_id: "task-busy",
            status: "succeeded"
          })
        );
      });
      await vi.advanceTimersByTimeAsync(250);

      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "mdtero.bridge.hello",
          runner_state: "idle"
        })
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("exposes an explicit ensureConnected hook for runtime wake events", () => {
    const onMessage = createEventSink();
    const onDisconnect = createVoidEventSink();
    const postMessage = vi.fn();
    const connectNative = vi.fn().mockReturnValue({
      onMessage,
      onDisconnect,
      postMessage
    });

    const controller = initializeBrowserBridge({
      runtime: {
        connectNative
      } as never,
      acquire: vi.fn()
    });

    expect(postMessage).toHaveBeenCalledTimes(1);

    controller.ensureConnected();

    expect(connectNative).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledTimes(2);
    expect(postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "mdtero.bridge.hello"
      })
    );
    expect(controller.getStatus()).toEqual({
      state: "connected",
      runnerState: "idle"
    });
  });
});
