import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  apiRequest,
  sendAgentPrompt,
  type AgentReply,
  type AgentResume,
} from "../../services/api";
import PromptComposer from "./PromptComposer";
import NeedsInputForm from "./NeedsInputForm";
import { useResume } from "../../hooks/useResume";
import AgentActivityTimeline from "../activity/AgentActivityTimeline";
import type {
  AgentActivityEvent,
  AgentExecutionState,
} from "../activity/types";

interface ChatPanelProps {
  activityEvents?: AgentActivityEvent[];
  executionState?: AgentExecutionState;
}

export default function ChatPanel({
  activityEvents,
  executionState,
}: ChatPanelProps) {
  const resume = useResume();

  const [events, setEvents] = useState<AgentActivityEvent[]>([]);
  const [sending, setSending] = useState(false);
  const [lastReply, setLastReply] = useState<AgentReply | null>(null);
  const [notice, setNotice] = useState("");

  const inFlight = useRef(false);
  const pollingRef = useRef(false);
  const lastActivityId = useRef(0);
  const conversationId = useRef(crypto.randomUUID()).current;

  useEffect(() => {
    let active = true;

    async function pollActivity() {
      if (pollingRef.current) return;

      pollingRef.current = true;

      try {
        const result = (await apiRequest(
          `/browser/activity?after=${lastActivityId.current}`,
        )) as { events?: AgentActivityEvent[] };

        if (!active || !Array.isArray(result.events)) return;

        const incoming = result.events
          .filter((event) => Number.isFinite(Number(event.id)))
          .map((event) => ({
            ...event,
            id: String(event.id),
          }));

        if (incoming.length === 0) return;

        lastActivityId.current = Math.max(
          lastActivityId.current,
          ...incoming.map((event) => Number(event.id)),
        );

        setEvents((previous) => {
          const merged = new Map<string, AgentActivityEvent>();

          for (const event of previous) {
            merged.set(event.id, event);
          }

          for (const event of incoming) {
            merged.set(event.id, event);
          }

          return Array.from(merged.values()).slice(-200);
        });
      } catch {
        // Retry on the next polling interval.
      } finally {
        pollingRef.current = false;
      }
    }

    void pollActivity();

    const timer = window.setInterval(() => {
      void pollActivity();
    }, 1200);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  async function run(
    prompt: string,
    resumeData?: AgentResume,
  ): Promise<boolean> {
    if (inFlight.current || sending || resume.busy) {
      return false;
    }

    inFlight.current = true;
    setSending(true);
    setNotice("");

    try {
      const reply = await sendAgentPrompt(
        prompt,
        resume.activeResume?.id ?? null,
        conversationId,
        undefined,
        resumeData,
      );

      setLastReply(reply);
      setNotice(reply.response || `Agent status: ${reply.status}`);

      return reply.status !== "error";
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.reload();
        return false;
      }

      setNotice(
        error instanceof ApiError && error.kind === "timeout"
          ? "Request timed out. The agent may still be running on the backend. Check Agent Activity before retrying."
          : error instanceof Error
            ? `Request failed: ${error.message}`
            : "Request failed.",
      );

      return false;
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  }

  function handleResume(data: AgentResume) {
    if (inFlight.current || sending) return;
    void run("Continue the paused application", data);
  }

  const status = lastReply?.status;

  const displayedEvents = activityEvents ?? events;
  const latest = displayedEvents[displayedEvents.length - 1];

  const derivedState: AgentExecutionState = sending
    ? "running"
    : status === "needs_input" ||
        status === "awaiting_approval"
      ? "waiting"
      : status === "error"
        ? "failed"
        : latest?.status === "running"
          ? "running"
          : latest?.status === "waiting"
            ? "waiting"
            : latest?.status === "failed"
              ? "failed"
              : latest
                ? "completed"
                : "idle";

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-[#171717] text-[#F5F5F5]">
      {/* Agent Activity uses all available remaining height */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <AgentActivityTimeline
          events={displayedEvents}
          executionState={executionState ?? derivedState}
        />
      </div>

      {/* Required screening questions */}
      {!sending &&
        status === "needs_input" &&
        lastReply && (
          <div className="max-h-[35%] shrink-0 overflow-y-auto border-t border-[#353535]">
            <NeedsInputForm
              questions={lastReply.pending_questions}
              missingFields={lastReply.missing_fields}
              disabled={sending}
              onSubmit={(data) => handleResume(data)}
            />
          </div>
        )}

      {/* Explicit submission approval */}
      {!sending && status === "awaiting_approval" && (
        <div className="shrink-0 border-t border-[#353535] px-3 py-2">
          <button
            type="button"
            onClick={() => handleResume({ approve: true })}
            className="rounded border border-[#353535] px-3 py-2 text-sm hover:bg-[#353535]"
          >
            Approve &amp; submit application
          </button>
        </div>
      )}

      {/* Compact response / error notice */}
      {notice && (
        <div
          role="status"
          className="max-h-16 shrink-0 overflow-y-auto border-t border-[#353535] px-3 py-1 text-xs text-[#A3A3A3]"
        >
          {notice}
        </div>
      )}

      {/* Compact composer pinned to bottom */}
      <div className="z-10 w-full shrink-0 border-t border-[#353535] bg-[#171717]">
        <PromptComposer
          onSend={(text) => run(text)}
          sending={sending}
          resume={resume}
        />
      </div>
    </section>
  );
}