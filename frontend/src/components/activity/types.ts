export type ActivityStatus = "pending" | "running" | "completed" | "failed" | "waiting";

export type ActivityType =
  | "searching_jobs"
  | "reading_job_description"
  | "matching_resume"
  | "dismissing_job"
  | "opening_easy_apply"
  | "filling_fields"
  | "pending_questions"
  | "awaiting_approval"
  | "application_submitted"
  | "error";

export interface ActivityJobDetails {
  jobId?: string;
  title?: string;
  company?: string;
  location?: string;
  url?: string;
}

/** A single real event reported by the backend agent. */
export interface AgentActivityEvent {
  id: string;
  type: ActivityType;
  status: ActivityStatus;
  /** Epoch milliseconds. */
  timestamp: number;
  /** Optional backend-provided message or error text. */
  message?: string;
  job?: ActivityJobDetails;
  /** Only set when the backend supplied a real match score (0-100). */
  matchScore?: number;
}

export type AgentExecutionState = "idle" | "running" | "waiting" | "completed" | "failed";
