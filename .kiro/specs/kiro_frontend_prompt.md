# Kiro Prompt — LinkedIn AI Agent Frontend

## Project
Existing `linkedin-ai-agent` repository. Build the frontend from scratch.

## Goal
Create a ChatGPT Work-style workspace: the user enters a natural-language prompt on the left, sees real agent execution events and progress, and watches a live Playwright browser preview with a cursor overlay on the right when backend streaming becomes available.

## Stack
React + Vite + TypeScript + Tailwind CSS. Keep dependencies minimal. Reuse the existing FastAPI backend; do not add Next.js or another backend.

## First read
- `.kiro/steering/coding-rules.md`
- Existing repository structure
- `backend/app/main.py`
- Existing FastAPI routes and response schemas, especially `apply.py`

## UX requirements
- Responsive split workspace: left chat and execution timeline; right browser viewer.
- Prompt composer with Send, disabled while unsupported or processing; Stop control only when cancellation is actually supported.
- Message history for the current page session.
- Job scan/match/application activity with clear timestamps, status, and error messages based on real backend responses.
- Pending screening questions and explicit application review/approval UI in later tasks.
- Browser viewer with loading, disconnected, and unavailable states. Do not use an iframe for LinkedIn or pretend an iframe is a live browser.
- Reserve interfaces for future real browser frames and cursor coordinates. Never fabricate browser images, cursor motion, progress, or completed actions.
- Never submit applications without a job-specific explicit approval and verified backend support.

## Break work into small tasks
Create `frontend/tasks.md` with these tasks and concise acceptance criteria:

- **F1 — Scaffold + shell:** Initialize React/Vite/TypeScript/Tailwind frontend (only if absent); responsive two-panel workspace and app shell.
- **F2 — Chat:** Prompt composer, conversation bubbles, local component state, accessible loading/disabled states. No fake agent replies.
- **F3 — Browser viewer:** Preview component, unavailable/loading states, typed frame/cursor contracts, no simulated footage.
- **F4 — Live activity:** Reusable event timeline, status badges, job cards, match score views driven by supplied data.
- **F5 — API integration:** Typed API client using environment-based FastAPI URL; connect only verified existing endpoints, handle errors and long-running calls safely. If SSE/WebSocket streaming is not implemented, show that it is unavailable rather than inventing events.
- **F6 — Questions + approval:** Pending questions, user-confirmed answers, job-specific review and approval interface; disable submission unless the backend safely supports it.

## Execute now: F1 only
1. Inspect the existing frontend folder before creating anything.
2. Create `frontend/tasks.md`.
3. Implement only F1: project scaffold, minimal Tailwind setup, responsive workspace shell with left chat area and right browser panel, plus clear static headings/empty states.
4. Do not wire fake interactions or simulate execution.
5. Do not edit backend files.

## Constraints
- Follow existing architecture and coding rules.
- Minimal files and dependencies; no unnecessary refactoring.
- Code changes only: do not run tests, builds, servers, browsers, linting, debugging, or terminal commands.
- Do not implement F2–F6 yet.
- Stop after F1.

## Final response (80 words maximum)
List exact modified/created paths, what F1 implemented, remaining tasks, and blockers.
