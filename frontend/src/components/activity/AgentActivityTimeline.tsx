
import { useEffect, useRef } from "react";
import ActivityStep from "./ActivityStep";
import type {
  AgentActivityEvent,
  AgentExecutionState,
} from "./types";

export interface AgentActivityTimelineProps {
  events?: AgentActivityEvent[];
  executionState?: AgentExecutionState;
}

const ACTIVE_STATUSES = new Set(["running", "waiting"]);

export default function AgentActivityTimeline({
  events = [],
  executionState = "idle",
}: AgentActivityTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousCountRef = useRef(0);

  useEffect(() => {
    const container = scrollRef.current;

    if (!container) return;

    if (events.length > previousCountRef.current) {
      container.scrollTop = container.scrollHeight;
    }

    previousCountRef.current = events.length;
  }, [events.length]);

  const lastEvent = events[events.length - 1];

  const activeId =
    lastEvent &&
    executionState !== "idle" &&
    ACTIVE_STATUSES.has(lastEvent.status)
      ? lastEvent.id
      : undefined;

  return (
    <section
      aria-label="Agent activity"
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-[#171717]"
    >
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
      >
        {events.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <p className="text-sm font-medium text-[#F5F5F5]">
              No agent activity yet
            </p>

            <p className="mt-2 max-w-md text-sm text-[#A3A3A3]">
              Agent execution steps will appear here when
              the backend reports activity.
            </p>
          </div>
        ) : (
          <ol className="flex flex-col gap-4 pb-4">
            {events.map((event) => (
              <ActivityStep
                key={event.id}
                event={event}
                isActive={event.id === activeId}
              />
            ))}
          </ol>
        )}
      </div>

    </section>
  );
}
