import { useState, type FormEvent } from "react";
import type { AgentResume, PendingQuestion } from "../../services/api";

interface NeedsInputFormProps {
  questions: PendingQuestion[];
  missingFields: string[];
  disabled: boolean;
  onSubmit: (resume: AgentResume) => void;
}

const FIELD_CLASS =
  "w-full rounded border border-[#353535] bg-[#0D0D0D] px-2 py-1.5 text-sm text-[#F5F5F5] disabled:opacity-50";

/** Collects answers for the backend's pending questions and missing applicant fields. */
export default function NeedsInputForm({ questions, missingFields, disabled, onSubmit }: NeedsInputFormProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [fields, setFields] = useState<Record<string, string>>({});

  // Must send something: an empty payload would start a new search instead of resuming.
  const complete =
    questions.every((q) => (answers[q.question] ?? "").trim()) &&
    (questions.length > 0 || Object.values(fields).some((v) => v.trim()));

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (disabled || !complete) return;
    const applicant_data = Object.fromEntries(
      Object.entries(fields).filter(([, v]) => v.trim()).map(([k, v]) => [k, v.trim()]),
    );
    onSubmit({
      answers: questions.map((q) => ({
        question: q.question,
        answer: (answers[q.question] ?? "").trim(),
        input_type: q.input_type,
      })),
      applicant_data,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="shrink-0 border-t border-[#353535] px-4 py-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#A3A3A3]">
        Input needed to continue
      </h3>
      <p className="mb-2 text-xs text-[#A3A3A3]">
        Your answers are saved and this same application continues. It has not been submitted yet.
      </p>
      <div className="flex max-h-60 flex-col gap-3 overflow-y-auto">
        {questions.map((q) => (
          <label key={q.question} className="flex flex-col gap-1 text-sm">
            {q.question}
            {q.options.length > 0 ? (
              <select
                className={FIELD_CLASS}
                disabled={disabled}
                value={answers[q.question] ?? ""}
                onChange={(e) => setAnswers((a) => ({ ...a, [q.question]: e.target.value }))}
              >
                <option value="">Select…</option>
                {q.options.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : q.input_type === "textarea" ? (
              <textarea
                className={FIELD_CLASS}
                rows={3}
                disabled={disabled}
                value={answers[q.question] ?? ""}
                onChange={(e) => setAnswers((a) => ({ ...a, [q.question]: e.target.value }))}
              />
            ) : (
              <input
                className={FIELD_CLASS}
                disabled={disabled}
                value={answers[q.question] ?? ""}
                onChange={(e) => setAnswers((a) => ({ ...a, [q.question]: e.target.value }))}
              />
            )}
          </label>
        ))}
        {missingFields.map((name) => (
          <label key={name} className="flex flex-col gap-1 text-sm">
            {name.replace(/_/g, " ")}
            <input
              className={FIELD_CLASS}
              disabled={disabled}
              value={fields[name] ?? ""}
              onChange={(e) => setFields((f) => ({ ...f, [name]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      <button
        type="submit"
        disabled={disabled || !complete}
        className="mt-3 rounded border border-[#353535] px-3 py-1.5 text-sm hover:bg-[#353535] disabled:opacity-50"
      >
        Submit answers &amp; continue
      </button>
    </form>
  );
}
