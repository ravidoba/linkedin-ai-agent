
import {
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type FormEvent,
} from "react";
import ResumeStatus from "./ResumeStatus";
import type { useResume } from "../../hooks/useResume";

interface PromptComposerProps {
  onSend: (text: string) => Promise<boolean>;
  sending: boolean;
  resume: ReturnType<typeof useResume>;
}

const MAX_HEIGHT_PX = 120;

export default function PromptComposer({
  onSend,
  sending,
  resume,
}: PromptComposerProps) {
  const [value, setValue] = useState("");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canSend =
    value.trim().length > 0 &&
    !resume.busy &&
    !sending;

  const attachDisabled =
    resume.busy || !resume.signedIn;

  useLayoutEffect(() => {
    const element = textareaRef.current;
    if (!element) return;

    element.style.height = "auto";
    element.style.height = `${Math.min(
      element.scrollHeight,
      MAX_HEIGHT_PX,
    )}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();

    if (!text || !canSend) return;

    void onSend(text).then((success) => {
      if (success) {
        setValue("");
      }
    });
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  const handleKeyDown = (
    event: KeyboardEvent<HTMLTextAreaElement>,
  ) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full shrink-0 bg-[#171717] px-3 py-2 sm:px-5"
    >
      <div className="mx-auto w-full max-w-[800px]">
        <label
          htmlFor="prompt-input"
          className="sr-only"
        >
          Message the agent
        </label>

        <div className="flex min-w-0 flex-col gap-1 rounded-[20px] border border-[#353535] bg-[#262626] px-3 pb-1 pt-2 shadow-lg transition-colors focus-within:border-[#666666]">
          {/* Resume attachment */}
          <div className="min-w-0">
            <ResumeStatus resume={resume} />
          </div>

          {/* Compact text input */}
          <textarea
            id="prompt-input"
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(event) =>
              setValue(event.target.value)
            }
            onKeyDown={handleKeyDown}
            placeholder="Message the agent..."
            aria-label="Message the agent"
            className="block max-h-[120px] min-h-[28px] w-full resize-none overflow-y-auto bg-transparent px-2 py-1 text-sm leading-5 text-[#F5F5F5] placeholder:text-[#A3A3A3] focus:outline-none"
          />

          {/* Compact bottom action bar */}
          <div className="flex items-center justify-between gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];

                if (file) {
                  resume.selectFile(file);
                }

                event.target.value = "";
              }}
            />

            <button
              type="button"
              onClick={() =>
                fileInputRef.current?.click()
              }
              disabled={attachDisabled}
              aria-label="Attach resume (PDF or DOCX)"
              title="Attach resume (PDF or DOCX)"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#D4D4D4] transition-colors hover:bg-[#404040] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M21.4 11.1l-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5" />
              </svg>
            </button>

            <button
              type="submit"
              disabled={!canSend}
              aria-label="Send"
              title="Send (Enter)"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#F5F5F5] text-[#0D0D0D] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-30"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          </div>
        </div>

        <p className="mt-1 text-center text-[10px] text-[#888888]">
          {sending
            ? "Waiting for the agent..."
            : "Enter to send · Shift+Enter for a new line"}
        </p>
      </div>
    </form>
  );
}
