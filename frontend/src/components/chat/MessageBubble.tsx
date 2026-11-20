import type { AgentJob } from "../../services/api";

export interface ChatMessage {
  id: string;
  /** "system" is a UI notice, never an agent or AI reply. */
  role: "user" | "system" | "assistant";
  content: string;
  createdAt: number;
  /** Real jobs returned by the backend (search/match results or the job being applied to). */
  jobs?: AgentJob[];
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const time = new Date(message.createdAt);
  const isUser = message.role === "user";

  return (
    <li className={`flex min-w-0 flex-col ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-[#303030] text-[#F5F5F5]"
            : "border border-[#353535] bg-transparent text-[#F5F5F5]"
        }`}
      >
        {message.content}
        {message.jobs && message.jobs.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1.5 border-t border-[#353535] pt-2">
            {message.jobs.map((job, i) => (
              <li key={job.job_id ?? i} className="text-xs text-[#A3A3A3]">
                {job.url ? (
                  <a href={job.url} target="_blank" rel="noreferrer" className="text-[#F5F5F5] underline">
                    {job.title || "Untitled job"}
                  </a>
                ) : (
                  <span className="text-[#F5F5F5]">{job.title || "Untitled job"}</span>
                )}
                {[job.company, job.location].filter(Boolean).map((v) => ` · ${v}`)}
                {typeof job.match_score === "number" && ` · Match ${job.match_score}%`}
              </li>
            ))}
          </ul>
        )}
      </div>
      <time dateTime={time.toISOString()} className="mt-1 text-xs text-[#A3A3A3]">
        {isUser ? "You" : message.role === "assistant" ? "Agent" : "System"} ·{" "}
        {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
      </time>
    </li>
  );
}
