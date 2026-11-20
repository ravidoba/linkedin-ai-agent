import type { ActivityStatus, ActivityType } from "../components/activity/types";

/** Real `status` values returned by POST /ai/agent and /apply/run (see backend apply_workflow._result). */
export type WorkflowStatus =
  | "search_results"
  | "no_match"
  | "needs_input"
  | "pending_questions"
  | "awaiting_approval"
  | "applied"
  | "error";

const MAPPING: Record<WorkflowStatus, { type: ActivityType; status: ActivityStatus }> = {
  search_results: { type: "searching_jobs", status: "completed" },
  no_match: { type: "searching_jobs", status: "completed" },
  needs_input: { type: "pending_questions", status: "waiting" },
  pending_questions: { type: "pending_questions", status: "waiting" },
  awaiting_approval: { type: "awaiting_approval", status: "waiting" },
  applied: { type: "application_submitted", status: "completed" },
  error: { type: "error", status: "failed" },
};

/** Maps a real workflow status to an activity type/status; undefined for unknown values. */
export function mapWorkflowStatus(
  status: string,
): { type: ActivityType; status: ActivityStatus } | undefined {
  return MAPPING[status as WorkflowStatus];
}
