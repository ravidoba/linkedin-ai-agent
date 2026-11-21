import { useCallback, useEffect, useState } from "react";
import {
  getRunLogs,
  listRuns,
  type RunLogEntry,
  type RunLogs as RunLogsData,
  type RunSummary,
} from "../../services/api";

interface RunLogsProps {
  runId?: number;
  onClose: () => void;
}

export type ResultFilter = "All" | "Applied" | "Skipped" | "Failed";
const FILTERS: ResultFilter[] = ["All", "Applied", "Skipped", "Failed"];

/** "All" keeps every entry; a result filter keeps only the jobs with that outcome. */
export function filterLogs(logs: RunLogEntry[], filter: ResultFilter): RunLogEntry[] {
  return filter === "All" ? logs : logs.filter((log) => log.result === filter);
}

const RESULT_STYLES: Record<string, string> = {
  Applied: "text-green-300",
  Skipped: "text-[#D4D4D4]",
  Failed: "text-red-300",
};

/** Turn raw technical error text into a short sentence a user can act on. */
export function plainMessage(message: string): string {
  const firstLine = (message || "").split("\n")[0].trim();
  if (/timeout|timed out/i.test(firstLine)) {
    return "LinkedIn took too long to respond. The run stopped safely.";
  }
  if (/target (page|context|browser).*closed|browser has been closed/i.test(firstLine)) {
    return "The agent browser was closed, so the run stopped.";
  }
  if (/net::|connection (refused|reset)|network/i.test(firstLine)) {
    return "A network problem stopped the run. Check your connection and try again.";
  }
  // Any other code exception ("KeyError: 'title'") means nothing to a user.
  if (/\b[A-Z][A-Za-z]*(Error|Exception):/.test(firstLine)) {
    return "An unexpected error stopped the run. The server log has the details.";
  }
  return firstLine.length > 240 ? `${firstLine.slice(0, 237)}...` : firstLine;
}

function describe(log: RunLogEntry): string {
  const parts: string[] = [];
  if (log.job_number) {
    parts.push(log.job_total ? `Job ${log.job_number} of ${log.job_total}` : `Job ${log.job_number}`);
  }
  const job = [log.job_title, log.job_company].filter(Boolean).join(" at ");
  if (job) parts.push(job);
  // Messages already starting with "Job N:" repeat the number shown above.
  const text = plainMessage(log.message).replace(/^Job \d+:\s*/, "");
  return parts.length ? `${parts.join(" · ")}: ${text}` : text;
}

/** e.g. "#12 · 20 Nov, 10:42 · 5 jobs · 2 applied, 2 skipped, 1 failed" */
export function runLabel(run: RunSummary): string {
  const when = run.created_at
    ? new Date(run.created_at).toLocaleString(undefined, {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      })
    : "";
  const outcome = `${run.applied} applied, ${run.skipped} skipped, ${run.failed} failed`;
  return [`#${run.id}`, when, run.status, `${run.job_count} job(s)`, outcome]
    .filter(Boolean)
    .join(" · ");
}

export default function RunLogs({ runId, onClose }: RunLogsProps) {
  const [data, setData] = useState<RunLogsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<ResultFilter>("All");
  // undefined = latest run; a number = a past run picked by the user.
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(runId);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  const logs = data?.logs ?? [];
  const visibleLogs = filterLogs(logs, filter);
  const countOf = (f: ResultFilter) => filterLogs(logs, f).length;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [runList, runLogs] = await Promise.all([
        listRuns(),
        getRunLogs(selectedRunId),
      ]);
      setRuns(runList);
      setData(runLogs);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load logs.");
    } finally {
      setLoading(false);
    }
  }, [selectedRunId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      aria-label="Run logs"
      className="flex h-full min-h-0 flex-col overflow-hidden bg-[#171717] text-[#F5F5F5]"
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-[#353535] px-4 py-2 text-sm">
        {runs.length > 0 ? (
          <label className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-medium">Run</span>
            <select
              aria-label="Choose a run"
              value={data?.run?.id ?? ""}
              onChange={(event) => {
                setFilter("All");
                setSelectedRunId(Number(event.target.value));
              }}
              className="min-w-0 truncate rounded border border-[#353535] bg-[#262626] px-2 py-1 text-xs"
            >
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {runLabel(run)}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className="font-medium">Run logs</span>
        )}
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded border border-[#353535] px-2 py-1 text-xs hover:bg-[#353535] disabled:opacity-40"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-[#353535] px-2 py-1 text-xs hover:bg-[#353535]"
        >
          Close
        </button>
      </header>

      <div
        role="group"
        aria-label="Filter logs by result"
        className="flex shrink-0 flex-wrap gap-1.5 border-b border-[#353535] px-4 py-2 text-xs"
      >
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
            className={`rounded-full border px-2.5 py-0.5 ${
              filter === f
                ? "border-[#F5F5F5] bg-[#353535] text-[#F5F5F5]"
                : "border-[#353535] text-[#A3A3A3] hover:bg-[#262626]"
            }`}
          >
            {f} ({countOf(f)})
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-xs">
        {error && <p className="text-red-400">Could not load logs: {error}</p>}
        {!error && data && !data.run && (
          <p className="text-[#A3A3A3]">No runs yet. Click Start to begin one.</p>
        )}
        {!error && data?.run && logs.length === 0 && (
          <p className="text-[#A3A3A3]">This run has no log entries yet.</p>
        )}
        {!error && logs.length > 0 && visibleLogs.length === 0 && (
          <p className="text-[#A3A3A3]">No {filter.toLowerCase()} jobs in this run.</p>
        )}
        <ol className="flex flex-col gap-1.5">
          {visibleLogs.map((log) => (
            <li key={log.id} className="flex gap-2">
              <time className="shrink-0 text-[#888888]">
                {log.created_at ? new Date(log.created_at).toLocaleTimeString() : ""}
              </time>
              {log.result && (
                <span className={`shrink-0 font-medium ${RESULT_STYLES[log.result] ?? ""}`}>
                  {log.result}
                </span>
              )}
              <span
                className={`break-words ${
                  log.status === "failed" ? "text-red-300" : "text-[#D4D4D4]"
                }`}
              >
                {describe(log)}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
