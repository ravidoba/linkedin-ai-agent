export type BrowserConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "loading"
  | "error";

/** A real screenshot frame from the browser. width/height are the browser viewport size in pixels. */
export interface BrowserFrame {
  /** Image source (URL or data URL) of the screenshot. */
  src: string;
  width: number;
  height: number;
  /** Capture time as epoch milliseconds. */
  capturedAt?: number;
}

/** Cursor position in browser viewport pixel coordinates (same space as BrowserFrame width/height). */
export interface CursorPosition {
  x: number;
  y: number;
}
