# MVP validation

## Search recovery and live progress — 30 September 2026

- 45 backend unit/integration tests passed. Added regressions for non-academic
  professions, numbered Turkish biographies, unsupported names, automatic fallback,
  unique target counts, live summaries, and preserving reviewed people after failures.
- `scripts/e2e_collection.py` passed against a disposable database and a real browser,
  API, worker and extractor, with deterministic external search/fetch fixtures.
  Covered form creation, duplicate-run rejection, incremental candidates, transient
  polling failure recovery, mobile layout, leaving/returning, automatic fallback,
  no-results and inaccessible-source outcomes.
- Live deployed panel smoke and PostgreSQL API smoke passed, including review and
  CSV/XLSX/JSON export. Alembic comparison found no pending schema changes.
- The previously failing gastronomy request was rerun using the panel button.
  It completed automatically with 10 source-backed, unapproved candidates in 8 seconds.
  No candidates were inserted manually. This is one live retrieval check, not a
  guarantee of search-provider availability, profile accuracy, or suitability.
- The UI shows elapsed time, actual source counts, current source, incremental
  candidates and reconnect status. Searches continue when the page is closed.
- Empty extraction is `NO_RESULTS`, not an infrastructure failure. Alternative
  queries are tried within the existing 180-second / 20-source budget. Reaching
  the target avoids further unnecessary fetches. Existing reviewed records survive retries.
- Remaining test warning: Starlette's existing httpx TestClient deprecation.

## Python panel and live collection — 27 September 2026

The active deployment is now the Python panel/API, a Python collection worker,
and PostgreSQL. The Next.js validation below is historical.

- Python panel browser check passed: login, research creation, manual sourced
  candidate, review/approval, CSV contents, mobile width, settings, users, and
  no uncaught browser JavaScript errors. The test request was removed afterward.
- Backend API/service suite: 30 passed locally and in Docker. Ruff passed.
- PostgreSQL API integration check passed: service import, deduplication,
  preserved sources, human-only approval, collection completion, CSV/XLSX/JSON.
- Alembic comparison reports no pending schema differences.
- A custom-format PostgreSQL backup was restored into a newly created disposable
  database and checked for migration version and workspace records; that test
  database was removed. The workspace database was not overwritten.
- A real public-web request discovered 20 sources. Some refused fetching or had
  unsupported policies. Available evidence was retained as a partial result.
  Source-backed person records were retained without approval. This is a
  retrieval/extraction check, not confirmation that all candidates match the brief
  or requested location.
- Initial live extraction exposed navigation headings being treated as names.
  Those validation-only false positives were removed, extraction was restricted
  to supported person/profile markup plus URL/name evidence, and regression
  cases were added. This does not establish a general precision percentage.
- An unrelated page editor present in JSON-LD was also detected and removed from
  the validation request. Structured person extraction now requires matching
  profile-heading or profile-URL evidence; a regression case covers page authors.

Local URLs: http://localhost:3100 and http://localhost:8100/docs. Demo seeding is
disabled in the active Compose setup; existing demo records are preserved.
See [current scope and remaining deployment work](mvp-readiness.md).

## Historical Next.js validation — 25 September 2026

Verified locally on 25 September 2026.

| Check | Result |
| --- | --- |
| Backend API/service suite | 10 passed on Windows and inside the backend container |
| Frontend component suite | 9 passed |
| Next.js production build | Passed locally and in Docker |
| TypeScript check | Passed |
| Python Ruff checks | Passed |
| PostgreSQL integration smoke | Passed |
| Alembic model/schema comparison | No new upgrade operations detected |
| Playwright browser workflow | Passed against the Docker deployment |
| npm production dependency audit | 0 vulnerabilities reported |

Backend coverage includes create/read/update/delete, transactional bulk validation, request-scoped deduplication, source merging, retained reviewer decisions, authenticated n8n collection, prohibited service approval, login/logout/roles/CSRF header checks, search/filter/sort/pagination, spreadsheet formula protection, and CSV/XLSX/JSON/mock Sheets outputs.

The separate PostgreSQL smoke check uses a live service API key and a human browser-style session. It verifies that n8n results become visible through the same API consumed by the UI, stay unapproved, merge their sources, and export after explicit human approval.

The browser workflow verifies login, dashboard, new research, demo collection, candidate search, profile inspection, approval, notes, profile editing, status filtering, a real CSV download, export history, admin users, mobile navigation, lack of horizontal page overflow at 390px, and logout. It checks for uncaught browser errors and cleans up its own request. Dashboard screenshots are saved to `frontend/test-results/` when run.

The local workspace is left running at http://localhost:3100 with API documentation at http://localhost:8100/docs. Credentials are generated in the ignored `.env` file. The seeded workspace contains two requests and 24 fictional candidates after test cleanup.

Live OpenAI calls, real web search, and real Google Sheets writes were not exercised. Search and Sheets ship as mock providers; the optional OpenAI adapter requires credentials. This validation establishes the MVP workflow, not a measured live-search accuracy rate or a production security certification.

One non-failing dependency warning remains in backend tests: Starlette deprecates its current httpx TestClient transport in favor of httpx2. The pinned current stack passes the tests; the warning does not affect the application runtime.
