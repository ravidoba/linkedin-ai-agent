---
inclusion: always
---

# LinkedIn AI Agent — Focused Coding Rules

You are a focused coding agent working on the **existing** `linkedin-ai-agent` project.

## Existing stack
- Python, FastAPI
- PostgreSQL, SQLAlchemy
- Playwright with an existing persistent browser profile
- Ollama local AI
- Existing resume matching and browser agent services

## Core objective
Implement **only the single task explicitly requested**. Prefer the smallest change compatible with the existing architecture.

## Before editing
1. Inspect only the files directly relevant to the task.
2. Check whether the requested functionality already exists. Reuse or minimally extend it instead of duplicating it.
3. Preserve existing public interfaces, naming conventions, folder structure, database models, and configuration unless the task requires a change.

## Implementation standards
1. Change the fewest files and lines reasonably possible.
2. Use existing dependencies; do not add frameworks, packages, abstractions, or folders without an explicit requirement.
3. Write readable, maintainable Python with type hints and appropriate async/await usage consistent with nearby code.
4. Handle expected errors without silently hiding failures.
5. Never hardcode credentials, cookies, secrets, personal data, or configuration values.
6. Never fabricate resume details or answers to job screening questions. Unknown answers must be flagged for user input.
7. Respect LinkedIn/platform restrictions, user consent, and required approvals; do not bypass anti-automation controls.
8. Do not change unrelated working code or implement future tasks.

## Scope and efficiency
- One small task at a time; target a scope of roughly 5–10 minutes, not a guaranteed duration.
- Avoid broad repository exploration, speculative design, and lengthy explanations.
- If a required detail cannot be established from directly relevant code, state the exact blocker and stop rather than guessing.

## Code only — prohibited actions
- Do not run tests, debugging, linting, type checking, or formatting commands.
- Do not run terminal commands or scripts.
- Do not start servers, browsers, or the application.
- Do not generate test files.
- Do not submit real LinkedIn applications.
- Do not refactor unrelated modules.

## Stop and report
Stop immediately after implementing the current task. Do not start the next task.

Final response: **80 words maximum**, containing only:
- Exact project-relative file paths changed
- Brief description of what was implemented
- Blockers, if any

The user will handle testing and debugging separately.
