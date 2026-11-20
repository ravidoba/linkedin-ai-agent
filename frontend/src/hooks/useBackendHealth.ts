import { useEffect, useState } from "react";
import { getHealth } from "../services/api";

export type BackendHealthState =
  | { status: "checking" }
  | { status: "connected" }
  | { status: "disconnected"; reason: string };

const POLL_INTERVAL_MS = 15_000;

/** Reports the real result of GET /health; polls periodically. */
export function useBackendHealth(): BackendHealthState {
  const [state, setState] = useState<BackendHealthState>({ status: "checking" });

  useEffect(() => {
    const controller = new AbortController();

    const check = async () => {
      try {
        const health = await getHealth(controller.signal);
        if (controller.signal.aborted) return;
        setState(
          health.status === "healthy"
            ? { status: "connected" }
            : { status: "disconnected", reason: `Backend reported "${health.status}".` },
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          status: "disconnected",
          reason: error instanceof Error ? error.message : "Unknown error.",
        });
      }
    };

    void check();
    const timer = setInterval(() => void check(), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  return state;
}
