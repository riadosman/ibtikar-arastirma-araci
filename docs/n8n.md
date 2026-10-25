# n8n integration contract

The Python panel and worker run without n8n. For orchestration, n8n calls the same API:

- `POST /research-requests/{id}/collect` queues the built-in live collection (202).
  Duplicate starts while a job is active return 409.
- `GET /research-requests/{id}/collection?summary=true` returns the latest job, progress and
  counters; without `summary` it returns every source document with its outcome.
- `POST /research-requests/{id}/collection/cancel` stops a queued job immediately or a running job
  after its current source (found candidates are kept).

Job statuses: `QUEUED`, `RUNNING`, `COMPLETED`, `PARTIAL`, `NO_RESULTS`, `FAILED`, `CANCELLED`.
A job interrupted by a worker restart returns to `QUEUED` and resumes automatically
(`attempts` increases, at most `COLLECTION_MAX_ATTEMPTS`). Do not call `/complete` while a job is active.

Maintain your automation separately. The app exposes the API; it does not create or execute your n8n workflow.

Use an n8n **HTTP Request** node with JSON content and a Header Auth credential:

```http
Authorization: Bearer <value of N8N_API_KEY>
Content-Type: application/json
```

Default host API base: `http://localhost:8100/api/v1`. From a separate Docker Desktop n8n container use `http://host.docker.internal:8100/api/v1` if its network can reach host-bound ports; otherwise explicitly connect it to the Compose network and use `http://backend:8000/api/v1`. Do not use `localhost` to refer to another container. The app binds ports to host loopback by default; remote deployments need deliberate networking configuration.

The host name n8n uses must be listed in `ALLOWED_HOSTS` (defaults include `localhost`, `127.0.0.1`, `backend` and `host.docker.internal`); otherwise the API answers `400 Invalid host header`.

## Retries and idempotency

Send an `Idempotency-Key` header (8–128 characters: letters, digits, `._:-`) on every POST that
creates data — create research, add candidate, bulk import, collect, Sheets export. Use a value that
is stable across n8n retries of the same item, for example `{{$execution.id}}-{{$runIndex}}-{{$itemIndex}}`.

- Same key + same body: the stored first response is returned (same IDs, nothing duplicated).
- Same key + different body: 422 `validation_error`.
- Same key while the first request is still running: 409 `conflict` (retry later).
- Keys are kept for 7 days.

Candidate imports are also safe without a key: the same person with the same source URL merges.
Send `X-Request-ID` (8–128 characters) to correlate n8n executions with backend logs and audit records.

Enable **Retry On Fail** in the HTTP Request node only for responses with `"retryable": true`
(409, 429, 502, 503, 504), with exponential backoff and `Retry-After` for 429.

## 1. Create a request

`POST /research-requests`

```json
{
  "title": "Computer Vision Experts",
  "description": "Find potential panel speakers with university or industry experience.",
  "field": "Artificial Intelligence",
  "location": "Istanbul",
  "target_type": "Speaker",
  "requested_quantity": 20,
  "keywords": ["Computer Vision", "Machine Learning"],
  "notes": "Public professional evidence only."
}
```

Save the returned `id` in the workflow. Creating a request returns HTTP 201. Use `GET /research-requests/{id}` to inspect progress and statistics.

## 2. Submit sourced candidates

`POST /research-requests/{id}/candidates`

```json
{
  "full_name": "Example Person",
  "headline": "Computer Vision Researcher",
  "job_title": "Researcher",
  "organization": "Example University",
  "organization_type": "university",
  "field": "Artificial Intelligence",
  "location": "Istanbul",
  "website": "https://example.com",
  "public_email": "example@example.com",
  "bio": "Researches computer vision.",
  "expertise": ["Computer Vision", "Machine Learning"],
  "source_url": "https://example.com/profile",
  "source_name": "Example University",
  "source_type": "university",
  "source_date": "2026-09-01T00:00:00Z",
  "relevance_score": 88,
  "confidence_score": 85
}
```

This is a placeholder, not a verified real identity. Most profile fields are optional. At least one source is mandatory. `sources` can replace or supplement the shorthand source fields:

```json
{
  "full_name": "Example Person",
  "organization": "Example University",
  "sources": [
    {"url": "https://example.com/profile", "name": "University profile", "source_type": "university"},
    {"url": "https://example.org/speakers/example", "name": "Conference program", "source_type": "conference"}
  ]
}
```

Single import returns `{created, merged, candidate_ids, candidate}`. Bulk import returns `{created, merged, candidate_ids}`:

`POST /research-requests/{id}/candidates/bulk`

```json
{
  "candidates": [
    {"full_name": "Example Person", "organization": "Example University", "source_url": "https://example.com/profile"},
    {"full_name": "Another Example", "organization": "Example Lab", "source_url": "https://example.org/profile"}
  ]
}
```

Bulk size: 1–500, total body at most `MAX_REQUEST_BYTES` (5 MB default, else 413). Invalid entries reject the whole payload; imports are transactional. Repeated imports use request-scoped deduplication and preserve human review status and notes; reviewed candidates (approved, rejected, contacted, archived) only gain new sources. A personal email, a personal LinkedIn URL (`linkedin.com/in/...`) or name plus organization improves matching; shared mailboxes such as `info@` and company pages are never treated as identity. Scores are validated as 0–100 but recomputed from the request and evidence; caller scores are not treated as verification.

Each source may carry `evidence` (up to 2000 characters, the sentence that supports the candidate); with the shorthand fields use `source_evidence`. Reviewers see it next to the source link.

## 3. Complete collection

`POST /research-requests/{id}/complete`, with no body.

Sets the request to `READY_FOR_REVIEW`, preserving a previously human-completed request. It does **not** approve candidates. Humans review in the application.

## 4. Read and enrich

- `GET /research-requests/{id}/candidates?page=1&page_size=20&status=NEW`
- `GET /candidates/{id}`
- `PATCH /candidates/{id}` with a partial profile, sources, or notes.

Filters: `q`, `status`, `awaiting_review`, `min_score`, `sort`, `direction`, `page`, `page_size`. Sort columns: `full_name`, `organization`, `relevance_score`, `confidence_score`, `created_at`. Page size is at most 100. Lists return `{items, total, page, page_size}`.

All status changes require a logged-in human; a service-key PATCH containing `status` returns 403. Once a person has reviewed a candidate, the service key may only change `notes` (other fields return 409). Imports cannot carry an approval status. Sending a `sources` list on PATCH replaces the source collection; retain links you want to preserve. Unsupported fields produce 422.

Candidate responses include `quality`: `source_count`, `source_domains`, `first_seen_at`, `last_seen_at`, `verification_status` (`UNVERIFIED`, `HUMAN_APPROVED`, `HUMAN_REJECTED`) and `confidence_reason`.

## Error handling

Every error body is `{"detail": ..., "code": ..., "retryable": true|false, "request_id": ...}`.

| Status | code | Meaning | Retry? |
| --- | --- | --- | --- |
| 400 | `bad_request` | Unknown Host header or malformed request | No |
| 401 | `authentication_required` | Missing/invalid API key or expired browser session | No |
| 403 | `permission_denied` | Action requires a human, an administrator or a non-viewer | No |
| 404 | `not_found` | Request or candidate not found | No |
| 409 | `conflict` | Already running, reviewed candidate, or idempotent request in progress | Later |
| 413 | `payload_too_large` | Body above `MAX_REQUEST_BYTES` | No — split the payload |
| 422 | `validation_error` | Invalid input; `detail` lists field locations and messages | No — fix the payload |
| 429 | `rate_limited` | Too many requests; respect `Retry-After` | Yes |
| 502/503 | `external_service_error` | Optional provider (AI, Google) failed | Yes |
| 500 | `internal_error` | Bug; report the `request_id` | No |

Log the returned `X-Request-ID` to correlate with backend logs. Swagger UI and `/openapi.json` (when `ENABLE_API_DOCS=true`) contain the complete request schemas.
