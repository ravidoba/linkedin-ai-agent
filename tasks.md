# Test and Bug-Fix Tasks

Goal: automate the "LinkedIn Job Apply Manual Flow" (see `README.md`). The user clicks Start in the UI, answers a few questions, and the app runs the flow. The UI shows the job number, the current step, whether each job was applied or skipped, and user-friendly logs.

The application is already built. These tasks test it and fix bugs.

## How to run this file

1. Run only the one task the user names. Do not start the next task.
2. Run the task, check its "Done when" line, and fix bugs until it passes.
3. Make at most 2 fix attempts per task. If it still fails, stop. Report the error and what was tried, then ask the user whether to continue.
4. When the task passes, stop. Report the changed files in one or two lines and wait for the user to name the next task.
5. Change only what the task needs. Do not refactor unrelated code.
6. Start runs submit complete applications automatically (`APPLY_AUTO_SUBMIT=true`, the user's choice). Ask the user only before starting each next task.
7. Never invent answers to screening questions. Unknown questions go to the user in the UI.
8. If LinkedIn shows a login, captcha, or security check, stop and ask the user to handle it manually. Do not bypass it.
9. Keep temporary test scripts outside `backend/`: the backend runs with `--reload`, and a new or deleted `.py` file there restarts it.

Status: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked.

---

## Phase 0: Remove existing tests

- [x] **0.1** Find and delete all existing backend test files and folders.
  Done when: no backend test files remain, and the backend source is untouched.
- [x] **0.2** Find and delete all existing frontend test files and folders.
  Done when: no frontend test files remain, and the frontend source is untouched.
- [x] **0.3** Remove only the test config, scripts, or imports that now break the build.
  Done when: the backend and frontend still install and import without test-related errors.

## Phase 1: Application startup

- [x] **1.1** Start the backend and connect to PostgreSQL.
  Done when: the server runs with no startup errors and the database connection works.
- [x] **1.2** Start the frontend and load it in the browser.
  Done when: the UI loads and can reach the backend.
- [x] **1.3** Check that Ollama is reachable from the backend.
  Done when: the backend gets a response from the configured Ollama model.

## Phase 2: Start button and user input

- [x] **2.1** The UI shows a Start button.
  Done when: the button is visible and clickable.
- [x] **2.2** Clicking Start asks the user: "How many job posts do you want to process?"
  Done when: a number input appears, rejects empty, zero, and negative values, and accepts a positive whole number.
- [x] **2.3** The UI sends the number to the backend, and the backend creates a run record.
  Done when: a run with the entered job count is saved in the database and its id is returned to the UI.

## Phase 3: Browser and search

- [x] **3.1** The backend opens the browser with the existing persistent profile.
  Done when: a browser window opens and reuses the saved profile.
- [x] **3.2** Open linkedin.com and confirm the user is logged in.
  Done when: the LinkedIn home page loads while logged in. If not logged in, the UI asks the user to log in manually.
- [x] **3.3** Type `Java` in the search box and search.
  Done when: search results for Java appear.
- [x] **3.4** Click the Jobs tab.
  Done when: the Jobs results view is showing.
- [x] **3.5** Set Date posted to Past 24 hours and click Show results.
  Done when: the filter is applied and the results refresh.
- [x] **3.6** Turn on the Easy Apply filter.
  Done when: only Easy Apply jobs are listed.
- [x] **3.7** Set Workplace type to Remote.
  Done when: only Remote jobs are listed.

## Phase 4: Job list and keyword check

- [x] **4.1** Read the first job in the list and extract its title.
  Done when: the title is read correctly and logged.
- [x] **4.2** Check the title against the keywords: backend, fullstack, frontend, Java, software developer, software engineer.
  Done when: matching titles are marked "match" and others "no match", case-insensitive.
- [x] **4.3** For a non-matching job, dismiss the post and move to the next one.
  Done when: the post is removed, the job is logged as "skipped", and the next job is selected.
- [x] **4.4** Stop after the number of jobs the user entered.
  Done when: the run ends after N processed jobs, and the run is marked complete.

## Phase 5: Easy Apply steps

- [x] **5.1** For a matching job, click Easy Apply.
  Done when: the Easy Apply dialog opens.
- [x] **5.2** Contact info step: click Next.
  Done when: the dialog moves to the next step.
- [x] **5.3** Resume step: click Next.
  Done when: the dialog moves to the next step.
- [x] **5.4** Experience questions: enter `5`.
  Done when: any experience-related field is filled with `5`.
- [x] **5.5** Yes/No questions: select `Yes` (option A: only for covered skills, remote work and start date; legal, visa, personal and other-skill questions go to the user).
  Done when: every covered Yes/No question is set to Yes.
- [x] **5.6** Work experience and Education steps: click Next.
  Done when: both steps are passed without edits.
- [x] **5.7** Fill fixed answers: current salary `30 LPA`, expected salary `50 LPA`, notice period `Less than 15 days`, total work experience `5 Years`.
  Done when: each field holds the correct value.
- [x] **5.8** For any other question, ask the user in the UI and wait for the answer.
  Done when: the UI shows the question, the run pauses, the user's answer is filled in, and the run resumes.
- [x] **5.9** If a Review button appears, click it.
  Done when: the review page opens.
- [x] **5.10** If a Submit application button appears, click it automatically (`APPLY_AUTO_SUBMIT=true`; set it to `false` to approve each application on the Review page).
  Done when: the application is submitted and the job is logged as "applied".
- [x] **5.11** In the popup (Not Now / Update Profile), click Not Now.
  Done when: the popup closes without updating the profile.
- [x] **5.12** Dismiss the applied post with its cross icon.
  Done when: the post is removed from the list.
- [x] **5.13** Move to the next job and repeat from Phase 4.
  Done when: the next job is picked up automatically.

## Phase 6: Live progress in the UI

- [x] **6.1** Show the current job number out of the total, for example "Job 2 of 5".
  Done when: the number updates as each job starts.
- [x] **6.2** Show the current step inside the job, for example "Contact info", "Resume", "Questions", "Review", "Submit".
  Done when: the step text changes as the flow moves.
- [x] **6.3** Show the result of each job: Applied, Skipped, or Failed, with the job title.
  Done when: every processed job has a visible result.
- [x] **6.4** Updates reach the UI live, without a manual refresh.
  Done when: changes appear within a few seconds using the existing update mechanism.

## Phase 7: Logs

- [x] **7.1** The backend saves a log entry for each job and step, with a timestamp.
  Done when: log rows for a run exist in the database.
- [x] **7.2** The UI shows the logs in plain, readable language.
  Done when: each entry reads like "Job 3: title matched, clicked Easy Apply", not raw errors or stack traces.
- [x] **7.3** The user can filter logs by Applied, Skipped, and Failed.
  Done when: each filter shows only the matching jobs.
- [x] **7.4** The user can open the logs of past runs.
  Done when: a previous run's logs load correctly.

## Phase 8: End-to-end checks

- [x] **8.1** Run the full flow with 1 job.
  Done when: Start, input, search, keyword check, apply or skip, and logs all work in one run.
- [x] **8.2** Run the full flow with 3 to 5 jobs.
  Done when: all jobs are processed, the run completes, and the counts shown match the logs.
- [x] **8.3** Handle errors cleanly: a missing button, a LinkedIn page change, or the browser closing.
  Done when: the job is logged as "Failed" with a readable reason and the run continues or stops cleanly.
- [x] **8.4** Add a Stop button for a running run.
  Done when: clicking Stop ends the run safely and the run is marked "stopped".

## Phase 9: Resume profile and faster matching

Goal: read the resume once into a profile, read each job's requirements once (saved by LinkedIn job ID), and match them with plain code instead of sending the full resume to the AI model for every job.

- [x] **9.1** Add a `resume_profiles` table linked to the resume: skills with years per skill, total experience in years, education, current role, and an `edited_by_user` flag. Add an Alembic migration.
  Done when: the migration applies and a profile row can be saved and read back.
- [x] **9.2** On resume upload, ask the AI model once to fill the profile from the resume text, and save it. Re-uploading a resume rebuilds the profile.
  Done when: uploading a resume creates its profile, and no matching code reads the full resume text any more.
- [x] **9.3** Add a Profile screen in the UI that shows the profile and lets the user edit and save it. User edits always win over the AI's version, and a re-read never overwrites them without asking.
  Done when: the user can change a skill's years, save, reload the page, and see the change.
- [x] **9.4** For each job, ask the AI model only for the job's requirements (required skills, years of experience, education) from the description. Save them on the job row, keyed by the LinkedIn job ID (`jobs.linkedin_job_id`), so a job seen again is not read again.
  Done when: a job's requirements are saved, and seeing the same job ID again skips the AI call.
- [x] **9.5** Replace the per-job AI resume scoring with plain-code matching of job requirements against the profile. Keep the existing rules: match at least 75% and experience requirement met, else skip with a clear reason (for example "Missing skills: Kafka, Go" or "Needs 8 years, profile has 5"). A job whose requirements could not be read is skipped as "needs review", not dismissed.
  Done when: matching gives the same result every time for the same job, and every skip shows a readable reason.
- [x] **9.6** Answer screening questions from the profile: "years with <skill>" uses the profile's years for that skill, and education questions use the profile's education. The existing rules stay: legal, visa and personal questions, and skills not in the profile, still go to the user. Fixed answers (salary, notice period) stay in `.env`.
  Done when: a "years with Spring Boot" question is filled from the profile, and a skill missing from the profile goes to the user.
- [x] **9.7** Already-applied jobs (found in the database or shown as "Applied" on LinkedIn): dismiss the post with its cross icon, log "Skipped: already applied", and move to the next job without opening it.
  Done when: an applied job's card is removed from the list and logged as skipped.
- [x] **9.8** End-to-end check: run 5 jobs and compare with run 18 (before this phase).
  Done when: the run completes, matching takes less time per job than before, and every skipped job shows a clear reason.
