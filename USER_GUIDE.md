# User Guide: Testing from the UI

This guide walks you through a full test of the LinkedIn AI Agent from the web app.

> **Important:** auto-submit is on (`APPLY_AUTO_SUBMIT=true` in `backend/.env`). Every Start run sends **real applications** under your LinkedIn account. To approve each application yourself first, set `APPLY_AUTO_SUBMIT=false` and restart the backend.

---

## 1. Start the services

Run these in a WSL terminal from the project folder (`/mnt/d/Job/Projects/linkedin-ai-agent`).

| Service | Command | Check |
|---|---|---|
| PostgreSQL | `docker compose -f infrastructure/docker-compose.yml up -d` | `docker ps` shows `linkedin-postgres` |
| Ollama | `ollama serve` (if not already running) | `curl http://localhost:11434/api/tags` lists `qwen3:4b-instruct-2507-q4_K_M` |
| Backend | `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000` | `curl http://localhost:8000/health` returns `healthy` |
| Frontend | In Windows: `cd frontend` then `npm run dev` | Open `http://localhost:5173` |

If the database is new, run `cd backend && .venv/bin/alembic upgrade head` once.

---

## 2. Sign in

1. Open `http://localhost:5173`.
2. Enter your email and password. Use **Show** in the password field to check what you typed.
3. No account yet? Click **No account? Sign up**. The password needs at least 12 characters.

---

## 3. Upload your resume

1. Click the **paperclip** next to the message box.
2. Choose your resume (PDF or DOCX, up to 5 MB).
3. The app reads the resume once in the background and builds your profile. This takes about 10 seconds.

---

## 4. Check your profile

1. Click **Profile** (top right of the chat panel).
2. Check the fields:
   - **Current role** and **Total experience (years)**. The years are calculated from the job dates in your resume.
   - **Skills**: add or remove skills. Fill in **years** for your main skills. Then questions like "How many years with Spring Boot?" are answered automatically. Skills left empty are asked during the run.
   - **Education**: degree, level (bachelor, master, and so on) and field.
3. Click **Save**. Your edits are never overwritten automatically. **Read resume again** asks before replacing them.

---

## 5. Run the agent

1. Click **Start**.
2. Enter **how many job posts** to process. For a first test, use `2` or `3`.
3. Click **Run**.

A browser window opens on your desktop, and the browser panel on the right shows the same page. For each job, the agent:

1. Searches LinkedIn for Java jobs with the filters Past 24 hours, Easy Apply and Remote.
2. Skips and removes the post if the title doesn't match: backend, fullstack, frontend, Java, software developer or software engineer.
3. Skips and removes the post if you have already applied.
4. Compares the job's required skills and years with your profile. It needs a 75% skills match and enough years.
5. Opens Easy Apply, fills the Contact info, Resume and Questions pages, and submits.
6. Closes the popup with **Not now**, removes the applied post, and goes to the next job.

While it runs, the activity panel shows:
- **Job 2 of 5 · Step: Additional questions**: the current job and step.
- **Job results**: Applied (green), Skipped (grey) and Failed (red), with the job title.

### When the agent asks you a question

A question form appears for anything it is not allowed to guess, such as visa, legal or personal questions, or skills missing from your profile.

1. Answer each question.
2. Submit the form. The run continues from where it paused.

Your answers are saved. The same question is filled automatically next time.

### Stop a run

Click the red **Stop** button.
- **Running**: the agent finishes the current job, then stops. It never stops halfway through a form.
- **Paused on a question**: the open application is discarded and nothing is submitted.

---

## 6. Check the results

1. Click **Logs**.
2. Use the run picker to choose a run. Each run shows its date, status and Applied / Skipped / Failed counts.
3. Filter with **All**, **Applied**, **Skipped** or **Failed**.
4. Every skipped job shows its reason, for example:
   - "Title does not match the role keywords."
   - "Missing skills: Go, Rust (match 50%, needs 75%)."
   - "Needs 8 years of experience; your profile has 5.2."
   - "Already applied."
5. On LinkedIn, **My Jobs → Applied** shows the submitted applications.

---

## 7. Settings (`backend/.env`)

| Setting | Default | Meaning |
|---|---|---|
| `APPLY_AUTO_SUBMIT` | `true` | Submit automatically. Set `false` to approve each application on the Review page. |
| `APPLY_CURRENT_SALARY` | `30 LPA` | Answer for current salary questions |
| `APPLY_EXPECTED_SALARY` | `50 LPA` | Answer for expected salary questions |
| `APPLY_NOTICE_PERIOD` | `Less than 15 days` | Answer for notice period questions |
| `APPLY_TOTAL_EXPERIENCE_YEARS` | `5` | Used only when your profile has no total experience |
| `APPLY_SKILL_EXPERIENCE_YEARS` | `5` | Used for Java / backend / frontend / full stack questions when the profile has no years for that skill |
| `OLLAMA_MODEL` | `qwen3:4b-instruct-2507-q4_K_M` | Local AI model |

Restart the backend after changing `.env`.

---

## 8. Troubleshooting

| What you see | What to do |
|---|---|
| "Not logged in. Sign in to LinkedIn in the agent browser" | Sign in to LinkedIn in the browser window that opened. You have 2 minutes. |
| "LinkedIn jobs search page did not load within 30 seconds" | LinkedIn is limiting the browser. Wait 15 to 30 minutes and try again. |
| LinkedIn shows a security check or a warning | Complete it yourself in the agent browser. The agent never bypasses it. |
| "The file for resume ... is not stored on the server" | Delete the resume and upload it again. |
| "The agent browser was closed, so the run stopped." | Click **Start** again. A new browser opens. |
| The activity panel stops updating | Refresh the page. |
| "No run is active." after Stop | The run had already finished. Check **Logs**. |
| Many jobs skipped for "Missing skills" | Add the skills you have on the **Profile** screen and click **Save**. |
