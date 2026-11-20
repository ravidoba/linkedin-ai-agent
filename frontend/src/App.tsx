
import { useEffect, useRef, useState } from "react";
import ChatPanel from "./components/chat/ChatPanel";
import BrowserViewer from "./components/browser/BrowserViewer";
import AuthForm from "./components/auth/AuthForm";
import { useBackendHealth } from "./hooks/useBackendHealth";
import {
  ApiError,
  clearAccessToken,
  getAccessToken,
  getCurrentUser,
  logout,
  type AuthUser,
} from "./services/api";

const HEALTH_DOT = {
  checking: "bg-[#A3A3A3]",
  connected: "bg-green-500",
  disconnected: "bg-red-500",
} as const;

const PANEL_STORAGE_KEY = "linkedin-agent-left-panel-width";
const DEFAULT_LEFT_PERCENT = 50;
const MIN_PANEL_PX = 320;
const DIVIDER_PX = 6;
const DESKTOP_BREAKPOINT = 1024;

function clampPanelWidth(percent: number, containerWidth: number): number {
  const usableWidth = Math.max(0, containerWidth - DIVIDER_PX);

  if (usableWidth < MIN_PANEL_PX * 2) {
    return 50;
  }

  const minPercent = (MIN_PANEL_PX / usableWidth) * 100;
  return Math.max(minPercent, Math.min(100 - minPercent, percent));
}

function getSavedPanelWidth(): number {
  try {
    const value = Number(localStorage.getItem(PANEL_STORAGE_KEY));
    return Number.isFinite(value) && value > 0 && value < 100
      ? value
      : DEFAULT_LEFT_PERCENT;
  } catch {
    return DEFAULT_LEFT_PERCENT;
  }
}

export default function App() {
  const [session, setSession] = useState<"checking" | "authed" | "anon">(
    getAccessToken() ? "checking" : "anon",
  );
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    if (session !== "checking") return;

    const controller = new AbortController();

    getCurrentUser(controller.signal)
      .then((u) => {
        if (controller.signal.aborted) return;
        setUser(u);
        setSession("authed");
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.kind === "http") {
          clearAccessToken();
        }
        setSession("anon");
      });

    return () => controller.abort();
  }, [session]);

  if (session === "checking") {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0D0D0D] text-sm text-[#A3A3A3]">
        Loading...
      </div>
    );
  }

  if (session === "anon") {
    return <AuthForm onAuthenticated={() => setSession("checking")} />;
  }

  return (
    <Dashboard
      user={user}
      onLogout={() => {
        logout();
        setUser(null);
        setSession("anon");
      }}
    />
  );
}

function Dashboard({
  user,
  onLogout,
}: {
  user: AuthUser | null;
  onLogout: () => void;
}) {
  const health = useBackendHealth();

  const containerRef = useRef<HTMLElement | null>(null);
  const draggingRef = useRef(false);

  const [leftPercent, setLeftPercent] = useState(getSavedPanelWidth);
  const [isDesktop, setIsDesktop] = useState(
    () => window.innerWidth >= DESKTOP_BREAKPOINT,
  );
  const [isDragging, setIsDragging] = useState(false);

  const label =
    health.status === "checking"
      ? "Checking backend..."
      : health.status === "connected"
        ? "Backend connected"
        : "Backend disconnected";

  useEffect(() => {
    const media = window.matchMedia(
      `(min-width: ${DESKTOP_BREAKPOINT}px)`,
    );

    const update = () => setIsDesktop(media.matches);
    update();

    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!isDesktop) return;

    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(() => {
      setLeftPercent((previous) =>
        clampPanelWidth(previous, container.clientWidth),
      );
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, [isDesktop]);

  useEffect(() => {
    if (!isDragging) return;

    const previousCursor = document.body.style.cursor;
    const previousSelection = document.body.style.userSelect;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const handleMove = (event: PointerEvent) => {
      if (!draggingRef.current || !containerRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      const usableWidth = rect.width - DIVIDER_PX;

      if (usableWidth <= 0) return;

      const nextPercent =
        ((event.clientX - rect.left) / usableWidth) * 100;

      setLeftPercent(
        clampPanelWidth(nextPercent, rect.width),
      );
    };

    const handleStop = () => {
      draggingRef.current = false;
      setIsDragging(false);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleStop);
    window.addEventListener("pointercancel", handleStop);
    window.addEventListener("blur", handleStop);

    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousSelection;

      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleStop);
      window.removeEventListener("pointercancel", handleStop);
      window.removeEventListener("blur", handleStop);
    };
  }, [isDragging]);

  useEffect(() => {
    if (isDragging) return;

    try {
      localStorage.setItem(
        PANEL_STORAGE_KEY,
        String(leftPercent),
      );
    } catch {
      // Storage may be unavailable.
    }
  }, [leftPercent, isDragging]);

  const startDragging = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDesktop) return;

    event.preventDefault();
    draggingRef.current = true;
    setIsDragging(true);
  };

  const adjustWithKeyboard = (
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if (!isDesktop) return;

    const containerWidth = containerRef.current?.clientWidth ?? 0;

    let next = leftPercent;

    if (event.key === "ArrowLeft") next -= 2;
    else if (event.key === "ArrowRight") next += 2;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = 100;
    else return;

    event.preventDefault();

    setLeftPercent(clampPanelWidth(next, containerWidth));
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#0D0D0D] text-[#F5F5F5]">
      <header className="flex items-center justify-between gap-2 border-b border-[#353535] bg-[#171717] px-4 py-3">
        <div className="flex items-center gap-2">
          <img
            src="/favicon.svg"
            alt=""
            aria-hidden="true"
            className="h-7 w-7"
          />
          <h1 className="text-lg font-semibold">
            LinkedIn AI Agent
          </h1>
        </div>

        <span
          role="status"
          className="flex items-center gap-1.5 text-xs text-[#A3A3A3]"
          title={
            health.status === "disconnected"
              ? health.reason
              : undefined
          }
        >
          <span
            className={`h-2 w-2 rounded-full ${HEALTH_DOT[health.status]}`}
            aria-hidden="true"
          />
          {label}
          {health.status === "disconnected" && (
            <span className="text-red-400">
              ({health.reason})
            </span>
          )}
        </span>

        <div className="flex items-center gap-2 text-xs text-[#A3A3A3]">
          {user && <span>{user.email}</span>}
          <button
            type="button"
            onClick={onLogout}
            className="rounded border border-[#353535] px-2 py-1 text-[#F5F5F5] hover:bg-[#353535]"
          >
            Log out
          </button>
        </div>
      </header>

      <main
        ref={containerRef}
        className={
          isDesktop
            ? "flex min-h-0 min-w-0 flex-1 overflow-hidden"
            : "grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)_minmax(0,1fr)] overflow-hidden"
        }
      >
        <div
          className="min-h-0 min-w-0 overflow-hidden"
          style={
            isDesktop
              ? {
                  width: `calc((100% - ${DIVIDER_PX}px) * ${leftPercent / 100})`,
                  flexShrink: 0,
                }
              : undefined
          }
        >
          <ChatPanel key={user?.email ?? "anon"} />
        </div>

        {isDesktop && (
          <div
            role="separator"
            aria-label="Resize chat and browser panels"
            aria-orientation="vertical"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(leftPercent)}
            tabIndex={0}
            onPointerDown={startDragging}
            onKeyDown={adjustWithKeyboard}
            onDoubleClick={() => setLeftPercent(50)}
            title="Drag to resize panels. Double-click to reset."
            className={`group relative z-10 shrink-0 cursor-col-resize touch-none bg-[#353535] outline-none hover:bg-[#737373] focus-visible:bg-[#A3A3A3] ${
              isDragging ? "bg-[#A3A3A3]" : ""
            }`}
            style={{ width: DIVIDER_PX }}
          >
            <div className="absolute inset-y-0 -left-1 -right-1" />
          </div>
        )}

        <div
          className="min-h-0 min-w-0 overflow-hidden"
          style={isDesktop ? { flex: "1 1 0%" } : undefined}
        >
          <BrowserViewer />
        </div>
      </main>
    </div>
  );
}
