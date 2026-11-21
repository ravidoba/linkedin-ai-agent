# LinkedIn AI Agent

A FastAPI application that matches your resume to LinkedIn jobs and helps you apply. A Playwright browser agent drives LinkedIn through a persistent browser profile, and a local Ollama model handles the AI work.

## Tech stack

- Python, FastAPI
- PostgreSQL, SQLAlchemy
- Playwright (persistent browser profile)
- Ollama (local AI)

## What it does

- Matches your resume against LinkedIn job postings. (Planned, Phase 9 in `tasks.md`: read the resume once into an editable profile and match each job's requirements against it, instead of sending the full resume to the AI model for every job.)
- Uses a browser agent to open and fill in applications.
- Flags screening questions it cannot answer from your resume, so you can provide the answer.
- Submits a complete application automatically (`APPLY_AUTO_SUBMIT=true`, the default). Set it to `false` in `backend/.env` to approve each application on the Review page instead.

## LinkedIn Job Apply Manual Flow

This is the manual flow the agent is meant to automate.

1. Open the browser.
2. Open the LinkedIn website.
3. In the search box, enter `Java`.
4. Click the **Jobs** tab.
5. Under **Date posted**, select **Past 24 hours**, then click **Show results**.
6. Turn on the **Easy Apply** filter.
7. Under **Workplace type**, select **Remote**.
8. Take the first job in the results list and check its role:
   - If the role matches one of these keywords, click **Easy Apply**: `backend`, `fullstack`, `frontend`, `Java`, `software developer`, `software engineer`.
   - Otherwise, dismiss the post and repeat for the next job.

### Easy Apply steps

1. **Contact info:** click Next.
2. **Resume:** click Next.
3. **Additional questions:**
   - Any experience-related question: enter `5`.
   - Any Yes/No question: select `Yes`.
   - Work experience: click Next.
   - Education: click Next.
   - Current salary: `30 LPA`.
   - Expected salary: `50 LPA`.
   - Notice period: `Less than 15 days`.
   - Total work experience: `5 Years`.
   - Any other question: ask the user in the UI and use their input.
4. If a **Review** button appears, click it.
5. If a **Submit application** button appears, click it.
6. In the popup that follows (**Not Now** / **Update Profile**), select **Not Now**.
7. Dismiss the applied post by clicking its cross icon.
8. Repeat from the next job in the list.

## Principles

- No credentials, cookies, or secrets in code. Use environment variables.
- Resume details and screening answers are never fabricated.
- Respects LinkedIn restrictions and does not bypass anti-automation controls.

## Setup

TODO: add install, environment variable, database, and run instructions once confirmed against the project files.
