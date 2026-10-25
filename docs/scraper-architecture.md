# Website scraper review and collection architecture

Update, 27 September 2026: the subsequent user decision replaced n8n-first
orchestration with an independent Python worker and Python panel. The implementation
now lives in `backend/app/services/{discovery,fetching,extraction,collection}.py`.
The review below is the original assessment; its statements about collection not
being implemented describe that earlier point. See [current MVP status](mvp-readiness.md).

Reviewed on 27 September 2026 against upstream commit
`e6d068d7251a7a1aba2653ba84ae2d89fb38720e`:
[damash-ai-projects/website-scraper](https://gitlab.com/damash-ai-projects/website-scraper).

## Decision

Keep the current application and its candidate import boundary. Build any future
live collection worker independently, using the general separation of fetching,
text extraction, evidence storage, and structured candidate extraction. Do not
vendor the upstream implementation or add its dependencies to the application.
This review introduces documentation only; live collection remains unimplemented.

The upstream `LICENSE` calls itself MIT but also explicitly requires informing
the author and obtaining explicit approval before using the software. No upstream
source code has been copied into this project, installed, or executed. Direct
reuse would first require resolving that additional condition.

## Findings from source inspection

| Component | Useful idea | Limitation in the reviewed implementation |
| --- | --- | --- |
| `src/web_scraper/scraper.py` | Breadth-first traversal and selectable HTTP/browser fetchers | Traversal is duplicated across three implementations; no page, depth, total-time, or response-size budget. Domain comparison uses substring matching, so `example.com.attacker.test` can match `example.com`. Redirect targets and private network destinations are not restricted. |
| HTML/PDF extraction | Convert source pages into text while retaining the URL | No structured person extraction or evidence-to-field mapping. PDF failures become document text. HTML retrieval depends on a preliminary HEAD response, which some sites do not support. |
| Browser fetchers | Support pages that require JavaScript | A new browser is launched for each HTML page; Selenium cleanup is not protected by `finally`. |
| `src/data_processing/data_cleaner.py` | Separate normalization from fetching | Only whitespace normalization is implemented. |
| `src/storage/local_storage.py` | Separate persistence from crawling | Reads and rewrites a shared JSON file without concurrency control; does not fit our PostgreSQL transactions. |
| `src/vector_store/faiss_store.py` | Optional retrieval over collected documents | Embeddings are character-code placeholders, not semantic representations. The index is in memory. Missing FAISS neighbors (`-1`) are not excluded and can return the last document. |
| `src/main.py` | Expose collection through an API | Crawl runs within the HTTP request; no durable job lifecycle or endpoint authentication. Crawl exceptions may be swallowed below the API and still produce a success message. |
| `tests/test_scraper.py` | A starting point for testing | Calls an async function without awaiting it, then expects a list; it does not validate the crawl. |

These are static inspection findings; upstream dependencies and tests were not run.
The project collects pages from a supplied URL. It does not discover relevant
people across the web from a research brief, so a discovery step is still needed.

## Proposed flow for this project

```text
Research brief
    -> n8n: discover relevant public source URLs
    -> collection worker: bounded fetch and HTML/PDF text extraction
    -> evidence storage: URL, fetched time, content hash, text, outcome
    -> candidate extractor: evidence-backed structured profiles
    -> CandidateCreate validation
    -> existing authenticated candidate import API
    -> existing deduplication and deterministic scoring
    -> collection completion -> human review -> export
```

Keep `SearchService` and the demo `/run` behavior unchanged until live discovery
and collection are actually implemented. A page collector should have a separate
contract: fetching a URL returns source evidence, not a fabricated candidate.
The existing `AIService.classify` method classifies supplied profiles; it is not
a page-to-candidate extractor and should not silently take on that responsibility.

### Worker boundaries

- **Discovery:** n8n obtains seed URLs from a configured search provider or an
  explicit list. Record the originating research request and source of each URL.
- **Fetching:** start with HTTP; add an optional Playwright adapter only for
  sources requiring JavaScript. Use one traversal implementation with interchangeable
  fetchers, rather than maintaining a crawler per backend.
- **Traversal:** opt in to following links. Start with a 20-page, depth-2,
  120-second job budget, 15-second request timeout, and 5 MiB document limit.
  Bound the pending queue as well as visited pages. These are proposed defaults,
  not settings currently implemented in the app.
- **Network boundary:** permit HTTP(S) only, validate exact allowed hostnames,
  normalize fragments and duplicate URLs, and validate every redirect. Block
  private, loopback, link-local, and metadata destinations at connection time;
  use worker network restrictions as well as URL checks to address DNS rebinding.
  Apply the same restrictions to browser subrequests if browser fetching is added.
- **Site behavior:** respect robots rules and source access restrictions, identify
  the crawler, limit per-host request rates, honor `Retry-After`, and bound retries.
- **Evidence:** preserve requested and final URL, fetch time (separate from source
  publication date), content type, content hash, extraction outcome, and text.
  Store raw evidence separately from candidates; an extraction failure is an
  error outcome, not source content. Retrying a source should reuse a stable job
  identity and avoid duplicating unchanged evidence.
- **Candidate extraction:** treat page content as untrusted input. Emit only
  supported profile fields with supporting source URLs; leave absent fields
  blank. Validate output through `CandidateCreate`. Do not invent contact details,
  copy crawler text into review notes, or infer human approval.
- **Execution:** use a worker outside the interactive API request. Persist job
  state and per-URL outcomes so timeouts, retries, partial results, and restarts
  are visible. An all-failed crawl must not be reported as completed collection.

### Existing integration points

1. Create or select a research request.
2. Submit validated candidates to
   `POST /api/v1/research-requests/{id}/candidates/bulk` in batches of at most 500.
   Include `sources` for every candidate and use the service Bearer credential.
3. Let `backend/app/services/candidates.py` handle transactional imports,
   source merging, preservation of human decisions, and local rescoring.
4. Call `POST /api/v1/research-requests/{id}/complete` only after the workflow's
   collection success criteria have been met. This moves the request to review;
   it does not approve candidates. Define partial-failure reporting before
   implementing the worker: the current API has no collection-job/outcome model.

See [the n8n contract](n8n.md) for payloads and authentication. Do not change the
service-key restriction on candidate status. Neither collected text nor a higher
confidence score proves that a profile has been verified.

## Implementation order and acceptance checks

1. Add a bounded HTTP collection worker and evidence contract with fixture-based
   tests for redirects, private destinations, duplicate links, size/time budgets,
   unsupported content, and partial failures.
2. Add evidence-backed candidate extraction and an n8n workflow. Check malformed
   output rejection, repeated-import deduplication, retained review decisions,
   source traceability, and the all-failed workflow case.
3. Exercise a small real-source research request end to end and measure relevance
   and source accuracy through human review before claiming live-search quality.
4. Add PDF/browser adapters when required by actual sources. Consider semantic
   retrieval only once there is a demonstrated need to search stored evidence;
   FAISS/Azure/Selenium are not prerequisites for the first collection workflow.
