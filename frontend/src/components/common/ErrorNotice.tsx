interface ErrorNoticeProps {
  message: string;
  onDismiss: () => void;
  /** Only pass for safe, idempotent actions. */
  onRetry?: () => void;
}

/** Lightweight dismissible error notification, announced to assistive tech via role="alert". */
export default function ErrorNotice({ message, onDismiss, onRetry }: ErrorNoticeProps) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-red-400/40 bg-[#171717] px-2.5 py-1.5 text-xs text-red-400"
    >
      <span className="min-w-0 flex-1 break-words">{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="shrink-0 underline hover:text-red-300">
          Retry
        </button>
      )}
      <button type="button" onClick={onDismiss} aria-label="Dismiss error" className="shrink-0 hover:text-red-300">
        ✕
      </button>
    </div>
  );
}
