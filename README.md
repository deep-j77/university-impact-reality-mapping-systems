# University Impact & Reality Mapping System — AI-Powered Student Early Warning & Analytics Platform

Major-project upgrade of the original minor project (see `README_ORIGINAL.md`). The
original Flask + CSV app's core idea — an explainable, rule-based trigger engine for
burnout/learning-gap/outcome/policy risks — is preserved and now sits alongside a
proper relational schema, real auth, a supplementary ML risk model, a generative AI
layer, role-based dashboards, and DB-driven PDF reports.

## Status: All 9 phases complete

- [x] Phase 1 — MySQL schema + migration from legacy CSVs
- [x] Phase 2 — Auth rebuild (bcrypt password hashing, JWT, role-based access)
- [x] Phase 3 — Core REST APIs (students, subjects, marks, attendance, assignments, performance, admin)
- [x] Phase 4 — ML risk model (RandomForest, augments the rule-based trigger engine)
- [x] Phase 5 — Generative AI layer (explanations, recommendations, chatbot via Anthropic API)
- [x] Phase 6 — Admin / Faculty / Student dashboards + Chart.js visualizations
- [x] Phase 7 — Upgraded PDF reports (DB + AI driven)
- [x] Phase 8 — Docs, polish, end-to-end testing pass
- [x] Phase 9 — CSV / Excel data export (this delivery)

Everything below has been run and verified end-to-end against a local SQLite test DB
(migration → training → every route → PDF generation → RBAC boundaries) before delivery.
Production use should point at real MySQL as documented below.

---

## Architecture

```
CSV (legacy)              MySQL (13 tables)
     │                          │
     └──► migrate_csv_to_mysql.py
                                 │
                    Flask app (blueprints)
        ┌───────┬───────┬────────┬────────┬────────┐
      auth   students  risk     ai      reports   dashboard
       │        │        │       │         │          │
    JWT/bcrypt  CRUD  RandomForest  Anthropic   ReportLab   aggregate
              (subjects,  (ml/)     API (ai_layer/)  PDFs     JSON for
               marks,                                          charts
               attendance,
               assignments,
               performance)
                                 │
                    Frontend (plain HTML/JS + Chart.js)
        login/signup → dashboard-admin / -faculty / -student
```

## What's in each phase

**Phase 1 (from the previous delivery, unchanged):** `backend/models.py` (13 tables),
`backend/migrate_csv_to_mysql.py`, `backend/config.py`, DB wiring in `app.py`.

**Phase 2 — Auth (`backend/auth.py`, `backend/routes/auth.py`):**
Passwords are bcrypt-hashed. `/api/auth/login` issues a JWT (HS256, configurable
expiry). `@require_auth` validates the token and attaches `g.current_user`;
`@require_role(...)` gates by ADMIN/FACULTY/STUDENT; `student_owns_or_staff(...)`
lets staff through but restricts a STUDENT token to their own record. The old
`X-User-ID` / `X-Role` header scheme is gone — everything now reads
`Authorization: Bearer <token>`.

**Phase 3 — Core REST APIs (`backend/routes/`):** full CRUD for `students`,
`subjects`, `attendance`, `marks`, `assignments` (+ submissions/grading),
`performance`, plus `admin` routes for threshold tuning and staff provisioning.
The original minor project's `/students/triggers` and `/summary` endpoints are
preserved at the same relative paths (now under `/api/students/...`) so the
rule-based trigger engine (`backend/risk_engine.py`) stays intact and explainable
— it does not depend on the ML model.

**Phase 4 — ML risk model (`backend/ml/risk_model.py`, `backend/train_risk_model.py`,
`backend/routes/risk.py`):** a RandomForest classifier over 8 engineered features
(avg attendance, attendance variance, avg marks, marks variance, late/missed
submission ratio, CGPA, backlogs, subject count), predicting a LOW/MEDIUM/HIGH/
CRITICAL risk level with a continuous risk score and human-readable reasons +
recommendations.

> **Read this before presenting the ML model as "trained on real outcomes":** there
> is no historical ground-truth dataset (dropout/fail/pass records) anywhere in this
> project — neither the original CSV nor the new DB ever tracked real outcomes. The
> model is trained on **weak labels** derived from the rule engine's trigger counts
> (0 triggers -> LOW, 1 -> MEDIUM, 2 -> HIGH, 3+ -> CRITICAL). This is a legitimate and
> common approach for a capstone without access to real labeled data — it lets the
> model learn smoothed, probabilistic, interaction-aware boundaries instead of hard
> if/else cutoffs — but say so explicitly in your report. Don't claim real outcome
> labels. This is documented again in the docstring of `ml/risk_model.py`. If the ML
> model hasn't been trained yet (`train_risk_model.py` not run), `/api/risk/.../assess`
> automatically falls back to a rule-engine-derived score so the endpoint still works.

**Phase 5 — Generative AI layer (`backend/ai_layer/ai_service.py`,
`backend/routes/ai.py`):** three capabilities via the Anthropic API —
plain-language risk explanations for faculty, actionable recommendations, and a
chatbot scoped to a student's own academic data (no open-ended web access). If
`ANTHROPIC_API_KEY` is unset or a call fails for any reason, every function
degrades to a deterministic templated response built from the same data instead
of erroring — `used_llm: false` in the response tells you which path ran. Verified
in testing: with no API key configured, explain/recommend/chat all returned sane
fallback text instead of crashing.

**Phase 6 — Dashboards (`frontend/dashboard-{admin,faculty,student}.html`):**
role-gated pages (redirect to `login.html` if the JWT/role doesn't match) built
on Chart.js:
- **Admin:** trigger summary cards, risk-level doughnut chart, avg-CGPA-by-department
  bar chart, live threshold tuning form, model retrain button, staff account
  provisioning, full student/trigger table with PDF download links.
- **Faculty:** avg-marks-by-subject chart, HIGH/CRITICAL at-risk list, per-student
  "Assess risk (ML)" and "AI explain" actions inline in the student table.
- **Student:** their own attendance/marks/CGPA-trend charts, risk badge, a chat
  widget wired to the Phase 5 chatbot, and a PDF download button.

**Phase 7 — PDF reports (`backend/reports_gen/pdf_report.py`,
`backend/routes/reports.py`):** same ReportLab foundation as the original
project's single route, rebuilt to pull performance trend, subject-wise marks,
subject-wise attendance, and the latest risk assessment from the database, with
an optional AI-generated summary section (`?include_ai=1`) sourced from the most
recent stored `AIPrediction` of type `RISK_EXPLANATION`.

**Phase 8 — this document + the testing pass described below.**

**Phase 9 — Data export (`backend/export_gen/export_service.py`,
`backend/routes/export.py`):** CSV/Excel download endpoints layered on top of
existing data — nothing about Phases 1–8 was changed to add this. Every
export is built from a pandas DataFrame (or a dict of DataFrames for
multi-sheet Excel workbooks), reusing the same rule engine (`risk_engine.py`)
and ML risk data (`RiskAssessment` rows) that already power the dashboards
and PDF reports, so exported numbers always match what's on screen.
- `GET /api/export/students` (ADMIN/FACULTY) — full roster: department,
  semester, avg attendance/marks, CGPA, backlogs, rule-engine triggers, and
  latest ML risk level/score. One row per student.
- `GET /api/export/at-risk` (ADMIN/FACULTY) — HIGH/CRITICAL students only,
  with risk score, contributing reasons, and recommendations, sorted
  highest-risk first — ready to hand to advising/counseling staff.
- `GET /api/export/analytics` (ADMIN only, Excel only) — one workbook with
  four sheets: All Students, At-Risk, By Department, Trigger Summary — the
  same numbers shown across the admin dashboard, bundled for reporting to
  university administration.
- `GET /api/export/student/<id>` (the student themselves, or ADMIN/FACULTY)
  — one student's own performance history, subject-wise marks, subject-wise
  attendance, and risk assessment history, as a 4-sheet workbook (or a
  single-sheet CSV, since CSV has no concept of multiple sheets — `?format=csv`
  returns just the Performance sheet).

All four endpoints take `?format=csv` or `?format=xlsx` (default `xlsx`;
`/analytics` is xlsx-only since it's inherently multi-sheet). Column widths
in Excel output are auto-sized for readability. Buttons for all of these are
wired into the Admin, Faculty, and Student dashboards (an "Export Data"
panel on Admin/Faculty, an "Export my data" panel on Student), using a new
shared `downloadFile()` helper in `frontend/api.js`.

---

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your local MySQL credentials + (optionally) ANTHROPIC_API_KEY

# Create the `university_impact` database in MySQL first, e.g.:
#   mysql -u root -p -e "CREATE DATABASE university_impact;"

python migrate_csv_to_mysql.py    # creates tables + imports legacy data + seeds demo data
python train_risk_model.py        # trains & saves the Phase 4 ML model (rerun after new data)
python app.py                     # runs the API on http://127.0.0.1:5000
```

Then open `frontend/index.html` in a browser (or serve the folder with e.g.
`python -m http.server 8080` from inside `frontend/`). It redirects to
`login.html` if you're not signed in, or straight to the right role dashboard if
you are.

### Quick local test without MySQL

Set `USE_SQLITE=1` in `.env` to run against a local `backend/dev.db` SQLite file
instead of MySQL — useful for a quick demo/grading run. Everything (migration,
training, all routes, PDF generation) was verified against this mode before
delivery. Switch it off (or delete the line) for your real MySQL deployment.

### AI layer (optional)

Set `ANTHROPIC_API_KEY` in `.env` to enable real LLM-generated explanations,
recommendations, and chatbot replies. Leave it blank and the app still works —
you'll get the templated fallback responses described in Phase 5 above.

Verify the backend is running:
```bash
curl http://127.0.0.1:5000/
curl http://127.0.0.1:5000/health/db
```

## Seeded accounts after migration

| Login | Password | Role |
|---|---|---|
| admin@legacy.import | admin123 | ADMIN |
| s001@legacy.import ... s015@legacy.import | student123 (or original per-user password) | STUDENT |
| faculty1@demo.import | faculty123 | FACULTY (new demo account, not from legacy data) |

New students can also self-register via `signup.html` / `POST /api/auth/register`.
Additional ADMIN/FACULTY accounts are provisioned by an existing admin via the
admin dashboard or `POST /api/admin/users`.

## Data provenance — please read before demoing or writing this up

- **Real data:** student IDs, department/cohort (`university` field), semester,
  overall CGPA, and login credentials all come from your original CSVs.
  Passwords are the same as before, now bcrypt-hashed instead of plaintext.
- **Synthetic demo data:** subject-level marks, attendance, assignments, and
  submissions are generated (seeded, `random.seed(42)` for reproducibility)
  because the original project never tracked data at that granularity. They're
  loosely jittered around each student's real CGPA/attendance so dashboards
  look sane, but individual subject numbers are not real.
- **ML model labels:** see the Phase 4 section above — trained on rule-engine-
  derived weak labels, not real historical outcomes.

Say all three, plainly, if you demo or write this up in your report.

## API reference (all under `/api`, JWT required unless noted)

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` (public), `POST /auth/login` (public), `GET /auth/me` |
| Students | `GET/POST /students`, `GET/PUT/DELETE /students/<id>`, `GET /students/triggers`, `GET /students/summary` |
| Subjects | `GET/POST /subjects`, `GET/PUT/DELETE /subjects/<id>` |
| Attendance | `GET/POST /attendance/<student_id>`, `PUT /attendance/record/<id>` |
| Marks | `GET/POST /marks/<student_id>`, `PUT /marks/record/<id>` |
| Assignments | `GET/POST /assignments`, `GET /assignments/<id>/submissions`, `POST /assignments/<id>/submit/<student_id>`, `PUT /assignments/submission/<id>/grade` |
| Performance | `GET/POST /performance/<student_id>` |
| Admin | `GET/PUT /admin/thresholds`, `GET/POST /admin/users`, `DELETE /admin/users/<id>` |
| Risk (ML) | `POST /risk/<student_id>/assess`, `GET /risk/<student_id>/latest`, `GET /risk/<student_id>/history`, `GET /risk/at-risk`, `POST /risk/retrain` |
| AI | `POST /ai/<student_id>/explain`, `POST /ai/<student_id>/recommendations`, `POST /ai/<student_id>/chat` |
| Dashboards | `GET /dashboard/admin`, `GET /dashboard/faculty`, `GET /dashboard/student` |
| Reports | `GET /reports/<student_id>?include_ai=1` (PDF download) |
| Export | `GET /export/students?format=csv\|xlsx`, `GET /export/at-risk?format=csv\|xlsx`, `GET /export/analytics?format=xlsx`, `GET /export/student/<student_id>?format=csv\|xlsx` |

Role gates: ADMIN-only (thresholds, staff provisioning, delete student, retrain
model, `/export/analytics`); ADMIN+FACULTY (student/subject/marks/attendance
CRUD, risk assessment, AI explain/recommend, faculty dashboard,
`/export/students`, `/export/at-risk`); STUDENT is restricted to their own
record everywhere via `student_owns_or_staff`, including `/export/student/<id>`.

## Testing performed before this delivery

Run against a local SQLite instance (`USE_SQLITE=1`), all via live HTTP calls to
a running Flask process (not just unit-level):
- Migration: 15 legacy students + 6 legacy users imported correctly, demo
  subjects/marks/attendance/assignments seeded, admin + demo faculty accounts created.
- ML training: `train_risk_model.py` ran successfully on the 15-student dataset
  and saved a usable model (accuracy on such a small demo dataset is naturally
  low — expected, not a bug — the model is functional and the pipeline is correct).
- Auth: admin, faculty, and student logins all issued valid JWTs; new student
  self-registration worked end-to-end.
- RBAC: student blocked (403) from listing all students and from another
  student's record; student allowed (200) into their own record; faculty
  blocked (403) from an admin-only route (`POST /admin/users`).
- Risk engine + ML: `/students/triggers`, `/students/summary`, `/risk/.../assess`,
  and `/risk/at-risk` all returned correct, consistent data across all 15 students.
- AI layer fallback: with no `ANTHROPIC_API_KEY` set, `/ai/.../explain` and
  `/ai/.../chat` both returned correct templated fallback text (`used_llm: false`)
  instead of erroring.
- Dashboards: `/dashboard/admin`, `/dashboard/faculty`, `/dashboard/student` all
  returned well-formed JSON matching what the frontend charts expect.
- Reports: PDF generated successfully (valid PDF 1.4, non-empty) via
  `/reports/<id>?include_ai=1`, including the AI summary section.
- Admin actions: threshold read/update round-tripped correctly.
- Export (Phase 9): verified via live HTTP calls against the same SQLite test
  DB, after running risk assessments for 10 students —
  `/export/students` (CSV, 200, non-empty; Excel, 200, correct headers/rows),
  `/export/at-risk` (Excel, 200, only HIGH/CRITICAL rows present, sorted by
  score descending), `/export/analytics` (Excel, 200, all 4 sheets present
  with correct row/column counts), `/export/student/<id>` (Excel, 4 sheets —
  Performance/Marks/Attendance/Risk History — all populated; CSV, 200,
  returns the Performance sheet). Role gates confirmed: FACULTY got 403 on
  `/export/analytics` but 200 on `/export/students`; STUDENT got 403 on
  `/export/students` but 200 on their own `/export/student/S001`.
- Frontend: every `api()` call path across all 7 HTML pages was cross-checked
  against the registered Flask blueprint routes — all match.

## Known limitations (be upfront about these)

- Demo dataset is tiny (15 students), so ML metrics (precision/recall in
  `ml/risk_model_meta.json` after training) will look weak — that's a data-volume
  artifact, not a modeling bug. Retrain after adding more real student records.
- The synthetic subject-level data described above is randomized, not real —
  don't present exact per-subject figures as genuine academic history.
- The Flask dev server (`python app.py`) is for development/demo only; use a
  production WSGI server (gunicorn/uwsgi) behind a reverse proxy for real deployment.
