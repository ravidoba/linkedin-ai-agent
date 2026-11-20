
const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

const DEFAULT_TIMEOUT_MS = 10_000;

export type ApiErrorKind =
  | "config"
  | "network"
  | "timeout"
  | "http"
  | "invalid_response"
  | "cancelled";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

const TOKEN_KEY = "access_token";

/** Bearer token is kept in sessionStorage only (cleared when the tab closes). */
export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

/** Extracts a readable message from FastAPI errors. */
async function readErrorDetail(response: Response): Promise<string | undefined> {
  try {
    const data: unknown = await response.json();
    const detail = (data as { detail?: unknown } | null)?.detail;

    if (typeof detail === "string") return detail;

    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d as { msg?: unknown })?.msg)
        .filter((m): m is string => typeof m === "string");

      if (msgs.length) return msgs.join("; ");
    }
  } catch {
    // Body was not JSON.
  }

  return undefined;
}

const LOG_BODY_ALLOWED = ["/health"];

function logApi(
  level: "log" | "error",
  tag: string,
  method: string,
  path: string,
  ...rest: unknown[]
): void {
  if (!import.meta.env.DEV) return;
  console[level](tag, method, path.split("?")[0], ...rest);
}

const STATUS_MESSAGES: Record<number, string> = {
  400: "Bad request.",
  401: "Unauthorized. Please sign in again.",
  403: "Access denied.",
  404: "Resource not found.",
  422: "Validation error. Please check your input.",
  429: "Too many requests. Please wait a moment and try again.",
};

function httpErrorMessage(status: number, detail: string | undefined): string {
  if (status >= 500) return "Backend server error. Please try again later.";

  const safe =
    detail && detail.length <= 300 && !/traceback|\n|bearer\s|eyJ/i.test(detail)
      ? detail
      : undefined;

  return safe ?? STATUS_MESSAGES[status] ?? `Request failed with HTTP ${status}.`;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  /** JSON-serialised unless it is FormData. */
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

/** Reusable JSON fetch helper with timeout and typed errors. */
export async function apiRequest(
  path: string,
  options: RequestOptions = {},
): Promise<unknown> {
  if (!API_BASE_URL) {
    throw new ApiError("config", "VITE_API_BASE_URL is not set.");
  }

  const {
    method = "GET",
    body,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal,
    headers,
  } = options;

  const controller = new AbortController();
  let timedOut = false;

  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  signal?.addEventListener("abort", () => controller.abort(), { once: true });

  const token = getAccessToken();
  const isForm = body instanceof FormData;
  const startedAt = performance.now();
  const elapsed = () => `${Math.round(performance.now() - startedAt)}ms`;
  const bodyLoggable = LOG_BODY_ALLOWED.includes(path.split("?")[0]);

  logApi("log", "[API REQUEST]", method, path);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body !== undefined && !isForm
          ? { "Content-Type": "application/json" }
          : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body:
        body === undefined
          ? undefined
          : isForm
            ? body
            : JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      if (response.status === 401 && token) {
        clearAccessToken();
        logApi("error", "[API FAILED]", method, path, response.status, elapsed());

        throw new ApiError(
          "http",
          "Session expired. Please sign in again.",
          401,
        );
      }

      const detail = await readErrorDetail(response);

      logApi(
        "error",
        "[API FAILED]",
        method,
        path,
        response.status,
        elapsed(),
        bodyLoggable ? detail : undefined,
      );

      throw new ApiError(
        "http",
        httpErrorMessage(response.status, detail),
        response.status,
      );
    }

    try {
      const data: unknown = await response.json();

      logApi(
        "log",
        "[API SUCCESS]",
        method,
        path,
        response.status,
        elapsed(),
        bodyLoggable ? data : "[body not logged]",
      );

      return data;
    } catch {
      logApi("error", "[API FAILED]", method, path, response.status, elapsed(), "invalid JSON");

      throw new ApiError(
        "invalid_response",
        "Response was not valid JSON.",
        response.status,
      );
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;

    const message = timedOut
      ? `Request timed out after ${timeoutMs} ms.`
      : controller.signal.aborted
        ? "Request was cancelled."
        : "Network Error";

    logApi("error", "[API ERROR]", method, path, message, elapsed());

    if (timedOut) throw new ApiError("timeout", message);
    if (controller.signal.aborted) throw new ApiError("cancelled", message);

    throw new ApiError("network", "Could not reach the backend.");
  } finally {
    clearTimeout(timer);
  }
}

export interface HealthResponse {
  status: string;
  service: string;
}

/** GET /health */
export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const data = await apiRequest("/health", { signal });

  if (
    typeof data !== "object" ||
    data === null ||
    typeof (data as HealthResponse).status !== "string" ||
    typeof (data as HealthResponse).service !== "string"
  ) {
    throw new ApiError("invalid_response", "Unexpected /health response shape.");
  }

  return data as HealthResponse;
}

/** POST /auth/login */
export async function login(email: string, password: string): Promise<void> {
  const data = await apiRequest("/auth/login", {
    method: "POST",
    body: { email, password },
  });

  const token = (data as { access_token?: unknown } | null)?.access_token;

  if (typeof token !== "string" || !token) {
    throw new ApiError("invalid_response", "Unexpected /auth/login response shape.");
  }

  sessionStorage.setItem(TOKEN_KEY, token);
}

export interface AuthUser {
  id: number;
  full_name: string;
  email: string;
}

/** POST /auth/register */
export async function register(
  fullName: string,
  email: string,
  password: string,
): Promise<void> {
  await apiRequest("/auth/register", {
    method: "POST",
    body: {
      full_name: fullName,
      email,
      password,
    },
  });
}

/** GET /auth/me */
export async function getCurrentUser(signal?: AbortSignal): Promise<AuthUser> {
  const data = await apiRequest("/auth/me", { signal });
  const u = data as Partial<AuthUser> | null;

  if (!u || typeof u.id !== "number" || typeof u.email !== "string") {
    throw new ApiError("invalid_response", "Unexpected /auth/me response shape.");
  }

  return {
    id: u.id,
    full_name: u.full_name ?? "",
    email: u.email,
  };
}

/** Client-side logout. */
export function logout(): void {
  clearAccessToken();
}

export interface ResumeSummary {
  id: number;
  filename: string;
  created_at: string;
}

function parseResume(data: unknown): ResumeSummary {
  const r = data as Partial<ResumeSummary> | null;

  if (
    !r ||
    typeof r.id !== "number" ||
    typeof r.filename !== "string" ||
    typeof r.created_at !== "string"
  ) {
    throw new ApiError("invalid_response", "Unexpected resume response shape.");
  }

  return {
    id: r.id,
    filename: r.filename,
    created_at: r.created_at,
  };
}

/** POST /resumes/ */
export async function uploadResume(
  file: File,
  signal?: AbortSignal,
): Promise<ResumeSummary> {
  const form = new FormData();
  form.append("file", file);

  const data = await apiRequest("/resumes/", {
    method: "POST",
    body: form,
    timeoutMs: 60_000,
    signal,
  });

  return parseResume(data);
}

/** Permanently delete a resume from backend database and storage. */
export async function deleteResume(resumeId: number): Promise<void> {
  const data = await apiRequest(`/resumes/${resumeId}`, {
    method: "DELETE",
  });

  const result = data as {
    deleted?: unknown;
    resume_id?: unknown;
  } | null;

  if (result?.deleted !== true || result.resume_id !== resumeId) {
    throw new ApiError(
      "invalid_response",
      "Unexpected resume deletion response.",
    );
  }
}

export interface PendingQuestion {
  question: string;
  input_type: string;
  options: string[];
  control_id?: string;
}

export interface AgentJob {
  job_id?: string;
  title?: string;
  company?: string;
  location?: string;
  url?: string;
  match_score?: number | null;
}

export interface WorkflowSummary {
  scanned: number;
  applied: number;
  skipped: number;
  failed: number;
  uncertain?: number;
}

export interface WorkflowResult {
  status: string;
  message: string;
  summary?: WorkflowSummary | null;
  error_type?: string | null;
  job: AgentJob | null;
  jobs: AgentJob[];
  pending_questions: PendingQuestion[];
  filled_fields: string[];
  missing_fields: string[];
  skipped_jobs: string[];
  application_id: number | null;
}

export interface AgentReply {
  response: string;
  status: string;
  conversation_id: string | null;
  results: WorkflowResult[];
  errors: string[];
  pending_questions: PendingQuestion[];
  missing_fields: string[];
  error_type: string | null;
}

const AGENT_TIMEOUT_MS: number =
  Number(import.meta.env.VITE_AGENT_TIMEOUT_MS) || 30 * 60_000;

export interface AgentResume {
  answers?: {
    question: string;
    answer: string;
    input_type: string;
  }[];
  applicant_data?: Record<string, string>;
  approve?: boolean;
}

/** POST /ai/agent */
export async function sendAgentPrompt(
  message: string,
  resumeId: number | null,
  conversationId: string,
  signal?: AbortSignal,
  resume?: AgentResume,
): Promise<AgentReply> {
  const data = await apiRequest("/ai/agent", {
    method: "POST",
    body: {
      message,
      ...(resumeId !== null ? { resume_id: resumeId } : {}),
      conversation_id: conversationId,
      ...resume,
    },
    timeoutMs: AGENT_TIMEOUT_MS,
    signal,
  });

  const r = data as Partial<AgentReply> | null;

  if (!r || typeof r.response !== "string" || typeof r.status !== "string") {
    throw new ApiError(
      "invalid_response",
      "Unexpected /ai/agent response shape.",
    );
  }

  return {
    response: r.response,
    status: r.status,
    conversation_id: r.conversation_id ?? null,
    results: Array.isArray(r.results) ? r.results : [],
    errors: Array.isArray(r.errors) ? r.errors : [],
    pending_questions: Array.isArray(r.pending_questions)
      ? r.pending_questions
      : [],
    missing_fields: Array.isArray(r.missing_fields)
      ? r.missing_fields
      : [],
    error_type:
      typeof r.error_type === "string" ? r.error_type : null,
  };
}

/**
 * GET /resumes/
 * The newest resume is treated as active.
 */
export async function getActiveResume(
  signal?: AbortSignal,
): Promise<ResumeSummary | null> {
  const data = await apiRequest("/resumes/", { signal });

  if (!Array.isArray(data)) {
    throw new ApiError(
      "invalid_response",
      "Unexpected /resumes/ response shape.",
    );
  }

  return data.length > 0 ? parseResume(data[0]) : null;
}
