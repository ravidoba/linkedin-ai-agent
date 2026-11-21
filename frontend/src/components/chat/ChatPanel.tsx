import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  apiRequest,
  sendAgentPrompt,
  stopRun,
  type AgentReply,
  type AgentResume,
} from "../../services/api";
import PromptComposer from "./PromptComposer";
import NeedsInputForm from "./NeedsInputForm";
import { useResume } from "../../hooks/useResume";
import AgentActivityTimeline from "../activity/AgentActivityTimeline";
import RunLogs from "../activity/RunLogs";
import ProfilePanel from "../profile/ProfilePanel";
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
  const [askingJobCount, setAskingJobCount] = useState(false);
  const [jobCount, setJobCount] = useState("");
  const [showLogs, setShowLogs] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [stopping, setStopping] = useState(false);

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
        )) as { events?: AgentActivityEvent[]; last_id?: number };

        if (!active || !Array.isArray(result.events)) return;

        // The backend's event ids restart at 1 after a backend restart; without
        // this reset, new events would stay hidden until the page is reloaded.
        if (
          typeof result.last_id === "number" &&
          result.last_id < lastActivityId.current
        ) {
          lastActivityId.current = 0;
          setEvents([]);
          return; // the next poll fetches the new events from the start
        }

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
    jobCount?: number,
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
        jobCount,
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

  const parsedJobCount = Number(jobCount);
  const jobCountValid =
    /^\d+$/.test(jobCount.trim()) && parsedJobCount > 0;

  function handleStart() {
    if (!jobCountValid || inFlight.current || sending) return;
    // Mirrors the manual flow in README.md; submission still needs approval.
    const prompt =
      `Apply to Java jobs: scan ${parsedJobCount} job postings, ` +
      "posted in the past 24 hours, remote only, Easy Apply.";
    void run(prompt, undefined, parsedJobCount).then((success) => {
      if (success) {
        setAskingJobCount(false);
        setJobCount("");
      }
    });
  }

  const status = lastReply?.status;
  const runPaused = status === "needs_input" || status === "awaiting_approval";

  async function handleStop() {
    setStopping(true);
    try {
      const result = await stopRun();
      if (result === "stopped") {
        setLastReply(null); // hide the question / approval forms of the ended run
        setNotice("Run stopped. The paused application was not submitted.");
      } else if (result === "stopping") {
        setNotice("Stopping after the current job. Nothing is submitted halfway.");
      } else {
        setNotice("No run is active.");
      }
    } catch (error) {
      setNotice(
        error instanceof Error ? `Could not stop the run: ${error.message}` : "Could not stop the run.",
      );
    } finally {
      setStopping(false);
    }
  }

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
        {showProfile ? (
          <ProfilePanel
            resumeId={resume.activeResume?.id ?? null}
            onClose={() => setShowProfile(false)}
          />
        ) : showLogs ? (
          <RunLogs onClose={() => setShowLogs(false)} />
        ) : (
          <AgentActivityTimeline
            events={displayedEvents}
            executionState={executionState ?? derivedState}
          />
        )}
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

      {/* Start the automated apply flow */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-[#353535] px-3 py-2 text-sm">
        {!askingJobCount ? (
          <button
            type="button"
            disabled={sending || resume.busy}
            onClick={() => setAskingJobCount(true)}
            className="rounded border border-[#353535] px-3 py-1.5 hover:bg-[#353535] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Start
          </button>
        ) : (
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              handleStart();
            }}
          >
            <label htmlFor="job-count-input">
              How many job posts do you want to process?
            </label>
            <input
              id="job-count-input"
              type="number"
              min={1}
              step={1}
              value={jobCount}
              onChange={(event) => setJobCount(event.target.value)}
              className="w-20 rounded border border-[#353535] bg-[#262626] px-2 py-1"
              autoFocus
            />
            <button
              type="submit"
              disabled={!jobCountValid || sending || resume.busy}
              className="rounded border border-[#353535] px-3 py-1.5 hover:bg-[#353535] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Run
            </button>
            <button
              type="button"
              onClick={() => {
                setAskingJobCount(false);
                setJobCount("");
              }}
              className="px-2 py-1.5 text-[#A3A3A3] hover:text-white"
            >
              Cancel
            </button>
          </form>
        )}
        {(sending || runPaused) && (
          <button
            type="button"
            onClick={() => void handleStop()}
            disabled={stopping}
            className="rounded border border-red-400/50 px-3 py-1.5 text-red-300 hover:bg-red-900/30 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {stopping ? "Stopping..." : "Stop"}
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setShowProfile((open) => !open);
            setShowLogs(false);
          }}
          aria-pressed={showProfile}
          className="ml-auto rounded border border-[#353535] px-3 py-1.5 hover:bg-[#353535]"
        >
          {showProfile ? "Hide profile" : "Profile"}
        </button>
        <button
          type="button"
          onClick={() => {
            setShowLogs((open) => !open);
            setShowProfile(false);
          }}
          aria-pressed={showLogs}
          className="rounded border border-[#353535] px-3 py-1.5 hover:bg-[#353535]"
        >
          {showLogs ? "Hide logs" : "Logs"}
        </button>
      </div>

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