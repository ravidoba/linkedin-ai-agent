import type { BrowserConnectionStatus, BrowserFrame, CursorPosition } from "./types";

interface BrowserCanvasProps {
  status: BrowserConnectionStatus;
  frame?: BrowserFrame;
  cursor?: CursorPosition;
  errorMessage?: string;
  interactive?: boolean;
  onClickAt?: (x: number, y: number) => void;
  onScroll?: (deltaY: number) => void;
}

function clampPercent(value: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, (value / total) * 100));
}

function placeholderText(status: BrowserConnectionStatus, errorMessage?: string): string {
  switch (status) {
    case "connecting":
      return "Connecting to browserâ€¦";
    case "loading":
      return "Waiting for the first browser frameâ€¦";
    case "error":
      return errorMessage ?? "The browser connection failed.";
    case "connected":
      return "Connected, but no frame has been received yet.";
    default:
      return "The browser is not connected.";
  }
}

export default function BrowserCanvas({ status, frame, cursor, errorMessage, interactive = false, onClickAt, onScroll }: BrowserCanvasProps) {
  const hasFrame = frame !== undefined && frame.width > 0 && frame.height > 0;

  if (!hasFrame) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 px-4 text-center">
        <p className="text-sm font-medium text-[#F5F5F5]">Browser preview unavailable</p>
        <p className={`text-sm ${status === "error" ? "text-red-400" : "text-[#A3A3A3]"}`}>
          {placeholderText(status, errorMessage)}
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-[#0D0D0D] p-2">
      <div
        className="relative max-h-full max-w-full"
        style={{ aspectRatio: `${frame.width} / ${frame.height}`, width: "100%" }}
      >
        <img
          onClick={(e) => {
            if (!interactive || !onClickAt) return;
            const rect = e.currentTarget.getBoundingClientRect();
            onClickAt(((e.clientX - rect.left) / rect.width) * frame.width, ((e.clientY - rect.top) / rect.height) * frame.height);
          }}
          onWheel={(e) => { if (interactive) { e.preventDefault(); onScroll?.(e.deltaY); } }}
          src={frame.src}
          alt="Live browser screenshot"
          className={`h-full w-full select-none object-contain ${interactive ? "cursor-crosshair" : ""}`}
          draggable={false}
        />
        {cursor && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-red-500 shadow"
            style={{
              left: `${clampPercent(cursor.x, frame.width)}%`,
              top: `${clampPercent(cursor.y, frame.height)}%`,
            }}
          />
        )}
      </div>
    </div>
  );
}
