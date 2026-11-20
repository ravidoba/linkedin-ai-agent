import type { BrowserConnectionStatus } from "./types";

interface BrowserToolbarProps {
  url?: string;
  status: BrowserConnectionStatus;
  isExpanded: boolean;
  onToggleExpand: () => void;
  manualControl?: boolean;
  onToggleControl?: () => void;
  controlBusy?: boolean;
}

const STATUS_STYLES: Record<BrowserConnectionStatus, { label: string; dot: string }> = {
  disconnected: { label: "Disconnected", dot: "bg-[#A3A3A3]" },
  connecting: { label: "Connecting", dot: "bg-amber-500" },
  connected: { label: "Connected", dot: "bg-green-500" },
  loading: { label: "Loading", dot: "bg-[#F5F5F5]" },
  error: { label: "Error", dot: "bg-red-500" },
};

export default function BrowserToolbar({
  url,
  status,
  isExpanded,
  onToggleExpand,
  manualControl,
  onToggleControl,
  controlBusy,
}: BrowserToolbarProps) {
  const { label, dot } = STATUS_STYLES[status];
  return (
    <div className="flex items-center gap-2 border-b border-[#353535] bg-[#171717] px-3 py-2">
      <div
        className="min-w-0 flex-1 truncate rounded-md bg-[#262626] px-3 py-1 text-xs text-[#A3A3A3]"
        title={url}
        aria-label="Current browser URL"
      >
        {url ?? "No URL"}
      </div>
      <span role="status" className="flex shrink-0 items-center gap-1.5 text-xs text-[#A3A3A3]">
        <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
        {label}
      </span>
      {onToggleControl && status === "connected" && (
        <button type="button" disabled={controlBusy} onClick={onToggleControl}
          className="shrink-0 rounded-md border border-[#353535] px-2 py-1 text-xs text-[#F5F5F5] hover:bg-[#353535] disabled:opacity-50">
          {manualControl ? "Return control" : "Take over"}
        </button>
      )}
      <button
        type="button"
        onClick={onToggleExpand}
        aria-pressed={isExpanded}
        className="shrink-0 rounded-md border border-[#353535] px-2 py-1 text-xs text-[#F5F5F5] hover:bg-[#353535]"
      >
        {isExpanded ? "Exit fullscreen" : "Fullscreen"}
      </button>
    </div>
  );
}
