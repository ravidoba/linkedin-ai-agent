import type { ActivityStatus, ActivityType, AgentActivityEvent } from "./types";

export const TYPE_LABELS: Record<ActivityType, string> = {
  searching_jobs: "Searching jobs",
  reading_job_description: "Reading job description",
  matching_resume: "Matching resume",
  dismissing_job: "Dismissing job",
  opening_easy_apply: "Opening Easy Apply",
  filling_fields: "Filling application fields",
  pending_questions: "Pending screening questions",
  awaiting_approval: "Awaiting user approval",
  application_submitted: "Application submitted",
  error: "Error",
};

const STATUS_STYLES: Record<ActivityStatus, { label: string; badge: string; dot: string }> = {
  pending: { label: "Pending", badge: "bg-[#262626] text-[#A3A3A3]", dot: "bg-[#A3A3A3]" },
  running: { label: "Running", badge: "bg-[#353535] text-[#F5F5F5]", dot: "bg-[#F5F5F5]" },
  completed: { label: "Completed", badge: "bg-green-900/40 text-green-300", dot: "bg-green-500" },
  failed: { label: "Failed", badge: "bg-red-900/40 text-red-300", dot: "bg-red-500" },
  waiting: { label: "Waiting", badge: "bg-amber-900/40 text-amber-300", dot: "bg-amber-500" },
};

interface ActivityStepProps {
  event: AgentActivityEvent;
  isActive: boolean;
}

export default function ActivityStep({ event, isActive }: ActivityStepProps) {
  const { label, badge, dot } = STATUS_STYLES[event.status];
  const time = new Date(event.timestamp);
  const jobLine = [event.job?.title, event.job?.company, event.job?.location]
    .filter(Boolean)
    .join(" · ");

  return (
    <li
      className="flex gap-3"
      aria-current={isActive ? "step" : undefined}
    >
      <span
        className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${dot} ${
          isActive && event.status === "running" ? "animate-pulse" : ""
        }`}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-[#F5F5F5]">{TYPE_LABELS[event.type]}</span>
          <span className={`rounded-full px-2 py-0.5 text-xs ${badge}`}>{label}</span>
          {isActive && <span className="text-xs font-medium text-[#F5F5F5]">Current step</span>}
          {typeof event.matchScore === "number" && (
            <span className="text-xs text-[#A3A3A3]">Match: {event.matchScore}%</span>
          )}
        </div>
        {jobLine && <p className="truncate text-xs text-[#A3A3A3]">{jobLine}</p>}
        {event.message && (
          <p
            className={`break-words text-xs ${
              event.status === "failed" ? "text-red-400" : "text-[#A3A3A3]"
            }`}
          >
            {event.message}
          </p>
        )}
        <time dateTime={time.toISOString()} className="text-xs text-[#A3A3A3]">
          {time.toLocaleTimeString()}
        </time>
      </div>
    </li>
  );
}
