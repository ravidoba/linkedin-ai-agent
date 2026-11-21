
import { useEffect, useRef } from "react";
import ActivityStep, { TYPE_LABELS } from "./ActivityStep";
import type {
  AgentActivityEvent,
  AgentExecutionState,
} from "./types";

export interface AgentActivityTimelineProps {
  events?: AgentActivityEvent[];
  executionState?: AgentExecutionState;
}

const ACTIVE_STATUSES = new Set(["running", "waiting"]);

const RESULT_STYLES: Record<NonNullable<AgentActivityEvent["result"]>, string> = {
  Applied: "bg-green-900/40 text-green-300",
  Skipped: "bg-[#353535] text-[#D4D4D4]",
  Failed: "bg-red-900/40 text-red-300",
};

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
  // Latest job progress ("Job N of M") of the current run only: stop at the
  // backend's "Starting ... workflow" event so a previous run's count is not shown.
  let progress: AgentActivityEvent["progress"];
  let runStart = 0;
  for (let i = events.length - 1; i >= 0; i--) {
    if (!progress && events[i].progress) progress = events[i].progress;
    if (events[i].message?.startsWith("Starting ")) {
      runStart = i;
      break;
    }
  }
  // Per-job outcomes (Applied / Skipped / Failed) of the current run.
  const jobResults = events.slice(runStart).filter((event) => event.result);
  // Current step: the form step name when reported, else the latest event's label.
  const currentStep = progress && lastEvent
    ? lastEvent.step ?? TYPE_LABELS[lastEvent.type]
    : undefined;

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
      {progress && (
        <div
          role="status"
          className="shrink-0 border-b border-[#353535] px-4 py-2 text-sm font-medium text-[#F5F5F5]"
        >
          Job {progress.current} of {progress.total}
          {currentStep && (
            <span className="font-normal text-[#A3A3A3]"> · Step: {currentStep}</span>
          )}
        </div>
      )}
      {jobResults.length > 0 && (
        <ul
          aria-label="Job results"
          className="max-h-32 shrink-0 overflow-y-auto border-b border-[#353535] px-4 py-2 text-xs"
        >
          {jobResults.map((event) => (
            <li key={event.id} className="flex min-w-0 items-center gap-2 py-0.5">
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 ${RESULT_STYLES[event.result!]}`}
              >
                {event.result}
              </span>
              <span className="shrink-0 text-[#A3A3A3]">
                Job {event.progress?.current ?? "?"}
              </span>
              <span className="truncate text-[#F5F5F5]">
                {[event.job?.title, event.job?.company].filter(Boolean).join(" · ") ||
                  "Untitled job"}
              </span>
            </li>
          ))}
        </ul>
      )}
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
