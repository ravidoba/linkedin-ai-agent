import { useState, type FormEvent } from "react";
import type { useResume } from "../../hooks/useResume";
import ErrorNotice from "../common/ErrorNotice";

type ResumeState = ReturnType<typeof useResume>;

function formatSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

const CHIP =
  "flex min-w-0 items-center gap-2 rounded-lg border border-[#404040] bg-[#303030] px-2 py-1";

const BTN =
  "shrink-0 rounded-md border border-[#404040] px-2 py-0.5 text-[#F5F5F5] hover:bg-[#454545] disabled:cursor-not-allowed disabled:opacity-50";

const FIELD =
  "min-w-0 flex-1 rounded-md border border-[#353535] bg-[#171717] px-2 py-1 text-[#F5F5F5] placeholder:text-[#A3A3A3] focus:border-[#A3A3A3] focus:outline-none";

export default function ResumeStatus({
  resume,
}: {
  resume: ResumeState;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const {
    signedIn,
    activeResume,
    selectedFile,
    busy,
    error,
    success,
  } = resume;

  const handleSignIn = (event: FormEvent) => {
    event.preventDefault();
    void resume.signIn(email, password);
  };

  return (
    <div className="space-y-1 text-xs">
      {!signedIn && (
        <form
          onSubmit={handleSignIn}
          className="flex flex-wrap items-center gap-2"
        >
          <span className="text-[#A3A3A3]">
            Session expired. Sign in to upload a resume:
          </span>

          <input
            type="email"
            required
            autoComplete="username"
            aria-label="Email"
            placeholder="Email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className={FIELD}
          />

          <input
            type="password"
            required
            autoComplete="current-password"
            aria-label="Password"
            placeholder="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={FIELD}
          />

          <button
            type="submit"
            disabled={busy}
            className={BTN}
          >
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
      )}

      {selectedFile ? (
        <div className={`${CHIP} max-w-[360px]`}>
          <span
            className="min-w-0 flex-1 truncate text-[#F5F5F5]"
            title={selectedFile.name}
          >
            {selectedFile.name}
            <span className="ml-1 text-[#A3A3A3]">
              · {formatSize(selectedFile.size)}
              · {busy ? "Uploading..." : "Not uploaded"}
            </span>
          </span>

          <button
            type="button"
            onClick={() => void resume.upload()}
            disabled={busy || !signedIn}
            className={BTN}
          >
            Retry
          </button>

          <button
            type="button"
            onClick={resume.removeFile}
            disabled={busy}
            className="shrink-0 rounded-full p-1 text-[#A3A3A3] hover:bg-[#454545] hover:text-white disabled:opacity-40"
            aria-label="Remove pending attachment"
            title="Remove attachment"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      ) : (
        signedIn &&
        (activeResume ? (
          <div className="flex h-10 max-w-[360px] items-center gap-2 rounded-lg border border-[#404040] bg-[#303030] px-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#B91C1C] text-white">
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                aria-hidden="true"
              >
                <path d="M6 2h8l4 4v16H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z" />
                <path d="M14 2v5h5M8 12h8M8 16h6" />
              </svg>
            </div>

            <div className="min-w-0 flex-1">
              <p
                className="truncate text-xs font-medium leading-4 text-[#F5F5F5]"
                title={activeResume.filename}
              >
                {activeResume.filename}
              </p>

              <p className="text-[10px] leading-3 text-[#A3A3A3]">
                {activeResume.filename
                  .toLowerCase()
                  .endsWith(".pdf")
                  ? "PDF"
                  : "DOCX"}{" "}
                · Uploaded
              </p>
            </div>

            <button
              type="button"
              onClick={() =>
                void resume.removeActiveResume()
              }
              disabled={busy}
              aria-label="Permanently delete uploaded resume"
              title="Permanently delete resume"
              className="shrink-0 rounded-full p-1 text-[#A3A3A3] hover:bg-[#454545] hover:text-white disabled:opacity-40"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        ) : null)
      )}

      {error && (
        <ErrorNotice
          message={error}
          onDismiss={resume.dismissError}
          onRetry={resume.retryLoad}
        />
      )}

      {success && (
        <div
          role="status"
          className="break-words text-[10px] text-[#A3A3A3]"
        >
          {success}
        </div>
      )}
    </div>
  );
}