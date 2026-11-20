import { useEffect, useState } from "react";
import BrowserCanvas from "./BrowserCanvas";
import BrowserToolbar from "./BrowserToolbar";
import type { BrowserConnectionStatus, BrowserFrame, CursorPosition } from "./types";
import { getAccessToken } from "../../services/api";

export interface BrowserViewerProps {
  status?: BrowserConnectionStatus;
  url?: string;
  frame?: BrowserFrame;
  cursor?: CursorPosition;
  errorMessage?: string;
}

interface FrameReply {
  status: "disconnected" | "loading" | "connected";
  url?: string;
  frame?: BrowserFrame;
  manual_control?: boolean;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export default function BrowserViewer({
  status: suppliedStatus,
  url: suppliedUrl,
  frame: suppliedFrame,
  cursor,
  errorMessage,
}: BrowserViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [liveStatus, setLiveStatus] = useState<BrowserConnectionStatus>("disconnected");
  const [liveUrl, setLiveUrl] = useState<string>();
  const [liveFrame, setLiveFrame] = useState<BrowserFrame>();
  const [liveError, setLiveError] = useState<string>();
  const [manual, setManual] = useState(false);
  const [controlBusy, setControlBusy] = useState(false);
  const [inputText, setInputText] = useState("");

  useEffect(() => {
    // Explicitly supplied viewer data takes precedence over polling.
    if (suppliedStatus !== undefined || suppliedFrame !== undefined) return;
    let stopped = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    async function poll() {
      controller = new AbortController();
      try {
        const token = getAccessToken();
        if (!token || !API_BASE_URL) {
          if (!stopped) {
            setLiveStatus("disconnected");
            setLiveFrame(undefined);
          }
          return;
        }
        const response = await fetch(`${API_BASE_URL}/browser/frame`, {
          headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`Browser preview HTTP ${response.status}`);
        const data = (await response.json()) as FrameReply;
        if (stopped) return;
        if (data.status === "connected" && data.frame?.src) {
          setLiveFrame(data.frame);
          setLiveUrl(data.url);
          setLiveStatus("connected");
          setManual(Boolean(data.manual_control));
        } else if (data.status === "loading") {
          setLiveStatus("loading");
        } else {
          setLiveStatus("disconnected");
          setLiveFrame(undefined);
          setLiveUrl(undefined);
        }
        setLiveError(undefined);
      } catch (error) {
        if (stopped) return;
        setLiveStatus("error");
        setLiveError(error instanceof Error ? error.message : "Browser preview unavailable");
      } finally {
        if (!stopped) timeout = setTimeout(poll, 1200);
      }
    }
    void poll();
    return () => {
      stopped = true;
      if (timeout) clearTimeout(timeout);
      controller?.abort();
    };
  }, [suppliedStatus, suppliedFrame]);

  useEffect(() => {
    if (!isExpanded) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsExpanded(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isExpanded]);

  async function postAction(path: string, body?: object) {
    const token = getAccessToken();
    if (!token || !API_BASE_URL) throw new Error("Sign in to control browser");
    const res = await fetch(`${API_BASE_URL}/browser/${path}`, {
      method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error((data as { detail?: string }).detail || `Browser action failed (${res.status})`);
    }
  }

  async function toggleControl() {
    setControlBusy(true);
    try {
      await postAction(manual ? "release" : "takeover");
      setManual(!manual);
      setLiveError(undefined);
    } catch (e) { setLiveError(e instanceof Error ? e.message : "Control failed"); }
    finally { setControlBusy(false); }
  }
  async function action(payload: object) {
    try { await postAction("action", payload); setLiveError(undefined); }
    catch (e) { setLiveError(e instanceof Error ? e.message : "Action failed"); }
  }

  const status = suppliedStatus ?? liveStatus;
  const frame = suppliedFrame ?? liveFrame;
  const url = suppliedUrl ?? liveUrl;

  return (
    <section
      aria-labelledby="browser-heading"
      className={
        isExpanded
          ? "fixed inset-0 z-50 flex flex-col bg-[#0D0D0D] text-[#F5F5F5]"
          : "flex min-h-0 min-w-0 flex-col overflow-hidden bg-[#0D0D0D] text-[#F5F5F5]"
      }
    >
      <h2 id="browser-heading" className="shrink-0 px-4 py-3 text-sm font-semibold text-[#F5F5F5]">
        Browser Viewer
      </h2>
      <BrowserToolbar
        url={url}
        status={status}
        isExpanded={isExpanded}
        onToggleExpand={() => setIsExpanded((v) => !v)}
        manualControl={manual}
        onToggleControl={() => void toggleControl()}
        controlBusy={controlBusy}
      />
      {liveError && <p role="alert" className="px-3 py-1 text-xs text-red-400">{liveError}</p>}
      {manual && (
        <div className="flex flex-wrap items-center gap-2 border-b border-[#353535] px-3 py-2">
          <input aria-label="Type into browser" value={inputText} onChange={(e) => setInputText(e.target.value)}
            placeholder="Text for focused browser field" className="min-w-0 flex-1 rounded bg-[#262626] px-2 py-1 text-xs" />
          <button className="rounded border px-2 py-1 text-xs" onClick={() => { void action({action: "type", text: inputText}); setInputText(""); }}>Type</button>
          {(["Enter", "Tab", "Escape", "Backspace"] as const).map((key) => (
            <button key={key} className="rounded border px-2 py-1 text-xs" onClick={() => void action({action: "key", key})}>{key}</button>
          ))}
        </div>
      )}
      <BrowserCanvas status={status} frame={frame} cursor={cursor} errorMessage={errorMessage ?? liveError}
        interactive={manual}
        onClickAt={(x,y) => void action({action:"click",x,y})}
        onScroll={(delta_y) => void action({action:"scroll",delta_y})} />
    </section>
  );
}
