# Frontend Tasks

Stack: React + Vite + TypeScript + Tailwind CSS. Backend: existing FastAPI app.

- [x] **F1 — Scaffold + shell**
  - Vite/React/TS/Tailwind project exists under `frontend/`.
  - Responsive two-panel workspace: left chat/timeline, right browser viewer.
  - Static headings and empty states only; no fake interactions.

- [x] **F2 — Chat**
  - Prompt composer, conversation bubbles, local component state.
  - Accessible loading/disabled states; Stop only if cancellation is supported.
  - No fake agent replies.

- [x] **Resume upload (chat)**
  - Paperclip button, PDF/DOCX picker, filename/size, Upload/Remove/replace, uploading/error/success states.
  - Uses existing `POST /resumes/` (multipart, Bearer auth) and `GET /resumes/` (newest = active resume; the apply workflow also uses the newest). No backend changes.
  - Auth: `POST /auth/login`; token kept in sessionStorage only. Expired sessions (401) clear the token and prompt sign-in.
  - Blockers: no registration UI (create the user via `/auth/register` first). Upload progress is an indicator only (fetch has no upload progress events). Matching routes take an explicit `resume_id`; they are not wired to the UI.

- [x] **F3 — Browser viewer**
  - Preview component with loading, disconnected, unavailable states.
  - Typed frame and cursor contracts; no simulated footage or iframe.

- [x] **F4 — Live activity**
  - Reusable event timeline, status badges, job cards, match score views.
  - Driven only by supplied data.

- [x] **F5 — API integration**
  - Integrated: `GET /health` (header status). Backend CORS added (`http://localhost:5173` + `CORS_ALLOWED_ORIGINS`).
  - Chat prompts stay local and show "Prompt execution is not yet supported"; `/apply/run` is never called.
  - `src/services/workflowMapping.ts` maps real `/apply/run` statuses to activity types (unused until F6).
  - Missing backend capabilities: natural-language agent endpoint, SSE/WebSocket event stream (streaming unavailable), browser frame/cursor stream, unauthenticated login flow in the frontend, per-step progress from `/apply/run` (single blocking call).
  - Typed API client using env-based FastAPI URL.
  - Connect only verified existing endpoints; handle errors and long calls.
  - If SSE/WebSocket is absent, show streaming as unavailable.

- [ ] **F6 — Questions + approval**
  - Pending questions, user-confirmed answers.
  - Job-specific review and approval UI.
  - Submission disabled unless the backend safely supports it.
