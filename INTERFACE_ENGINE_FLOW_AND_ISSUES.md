# InterfaceEngine — Full Flow & Issue Analysis

This document is a deep walkthrough of [InterfaceEngine/main.py](InterfaceEngine/main.py) plus a review of every sender (`engine_service.py` and friends) that pushes data **into** the engine.

---

## 0. Recent Fix Summary (plain English)

All **HIGH** and **MED** severity issues that could be safely addressed have been patched. Here's what changed and why, in one place:

### Batch endpoint (`POST /batch`) now reports partial success ✨ NEW

- The batch endpoint shares `_process_message` with the single-ingest endpoint, so **every fix above applies to batch automatically** (worker crashes, missing-server bail, park-and-resume, no-workers-ready, etc).
- In addition, the **response format** now reports per-item outcomes so a caller can tell exactly which items failed and which were parked for retry.

| Status | Meaning |
| --- | --- |
| `200 OK` | All items delivered. If any were parked for retry, `summary.parked_for_retry > 0` and the message reflects it. |
| `207 Multi-Status` | At least one item failed AND at least one succeeded. Body contains `summary` + a `failures[]` array (capped at 50). |
| `502 Bad Gateway` | Every item failed. Same body shape as 207. |
| `400 Bad Request` | The batch envelope itself is malformed (not a list, missing `system_id`, etc.). |

Example partial-failure body:

```json
{
  "message": "97/100 items delivered; 3 failed; 12 parked for retry",
  "summary": {"total": 100, "succeeded": 97, "failed": 3, "parked_for_retry": 12, "duration_seconds": 4.17},
  "failures": [
    {"index": 14, "path": "/fhir/add-patient", "status": "failed", "http_status": 503, "detail": "No route workers ready for routes: EHR→LIS..."},
    {"index": 51, "path": "/submit-lab-result", "status": "failed", "http_status": 400, "detail": "Missing System-Id header"}
  ]
}
```

One bad item no longer fails the whole batch — `asyncio.gather` runs without `return_exceptions=True` and `_run_one` traps `HTTPException`/`Exception` per item, so siblings continue independently.

### What you'll see differently when you run the engine

1. **It won't silently swallow worker crashes anymore.** If a route_worker dies (bad DB row, missing server, etc.) it logs the full traceback now. (Was [I-1](#i-1-blocker-route-worker-outer-except-was-silent-) — already fixed.)
2. **Requests no longer hang forever.** Every inbound message has a timeout of `~40s` (configurable via `INGEST_AWAIT_TIMEOUT`). If a worker dies, the caller gets a clear timeout error instead of a stuck connection. ([I-2](#i-2-blocker-await-future-could-hang-forever-).)
3. **When the destination is down, messages are saved for later.** Before, the worker either blocked forever or dropped the message. Now we retry a few times (default 3 × 20s), then **park the message in memory**. A new background watcher checks every 15s; the moment the destination comes back online, it replays everything. ([I-5](#i-5-high-inactive-destination-loop-blocks-the-worker-forever-).)
4. **Deleted routes are cleaned up.** Before, if you removed a Route row from the DB, its workers kept running on stale data. Now `route_manager` notices and cancels them. ([I-4](#i-4-high-worker-exits-silently-if-a-route-is-deleted-mid-flight-) + [I-19](#i-19-low-route_manager-never-sees-route-deletes-).)
5. **Bad System-Id headers now return a clean 400.** Before, the code crashed with `AttributeError` deep in the pipeline. ([I-7](#i-7-high-_process_message-doesnt-bail-on-missing-server-).)
6. **The engine no longer answers "200 OK" when it actually did nothing.** If no workers are ready, you get `503 Service Unavailable` with the list of unready routes. ([I-3](#i-3-high-route_queue_missing-returns-200-instead-of-error-).)
7. **Logs survive past midnight.** The single-file handler was wiping every night. Now it keeps 7 days (env var `LOG_BACKUP_COUNT`). ([I-10](#i-10-med-midnightsinglefilehandler-destroys-forensic-history-).)
8. **The Payer simulator stopped blocking its own event loop.** Its `claim_response_to_engine` was using **synchronous** `httpx.post` inside an async function, which froze everything for up to 7 seconds. Fixed to async. ([S-4](#s-4-blocker-payer-uses-sync-httpxpost-inside-async-def-).)
9. **LIS doesn't time out at 7 seconds anymore.** Bumped to 60s + 5s connect to match what the engine actually needs. ([S-2](#s-2-high-lis-uses-7-s-total-timeout-).)
10. **Error messages from the engine are no longer eaten by `.json()` parsing crashes** in EHR/LIS senders. ([S-3](#s-3-high-json-on-a-non-json-error-response-).)
11. **HTTP clients always close on shutdown** — workers wrap their client in `try/finally` so `Ctrl+C` no longer leaks sockets. ([I-13](#i-13-med-httpxasyncclient-per-route-worker--never-closed-under-cancellation-).)
12. **Database sessions can no longer leak** in the main hot paths — `_process_message`, `route_worker`, `route_manager`, and `redelivery_watcher` now use `with session_local() as db:`. ([I-8](#i-8-med-db-sessions-leak-on-exception-).)

### New environment variables (all optional, all have sensible defaults)

| Variable | Default | What it controls |
| --- | --- | --- |
| `INGEST_AWAIT_TIMEOUT` | `HTTP_READ_TIMEOUT + 10` (40 s) | How long an inbound request waits for downstream delivery before returning 502. |
| `INACTIVE_DEST_MAX_RETRIES` | `3` | How many times a worker retries an Inactive destination before parking the message. |
| `INACTIVE_DEST_BACKOFF_SECS` | `20` | Seconds between retries on an Inactive destination. |
| `REDELIVERY_CHECK_INTERVAL` | `15` | How often the watcher checks parked messages for re-delivery. |
| `LOG_BACKUP_COUNT` | `7` | Days of rotated logs to keep (was 0 = nothing). |

### What was NOT fixed (and why)

- **I-6 (HIGH) — mapping rule iteration multiplies counts.** Looks suspicious but may be intentional for repeated HL7 segments. Needs a focused unit test before I'd touch it.
- **I-11 (MED) — global mutable state.** Pure refactor. The code is safe today; punt to later.
- **I-12 (MED) — CORS wide open.** Appropriate for a local simulator; tighten before any public deployment.
- **S-1 (HIGH) — fire-and-forget sender pattern.** This is the biggest data-integrity concern but it's an architectural change (needs an outbox table or sync `await`). Worth a separate discussion.
- **S-7/S-8/S-9 (MED) — hardcoded URL / silent skips / hardcoded zeros.** All require product decisions, not just code edits.
- **All LOW items** — polish; left for later.

---

## 1. High-Level Architecture

```
 ┌──────────────────┐                                   ┌──────────────────┐
 │  EHR / LIS /     │  POST FHIR/HL7 + System-Id        │  InterfaceEngine │
 │  Payer / phr     │  ───────────────────────────────► │  (port 9000)     │
 │  (senders)       │                                   │                  │
 └──────────────────┘                                   │  /batch          │
                                                       │  /{full_path}    │
                                                       │                  │
                                                       │  routes data via │
                                                       │  route_workers   │
                                                       └────────┬─────────┘
                                                                │
                                       transformed FHIR/HL7     ▼
                                                       ┌──────────────────┐
                                                       │ Destination      │
                                                       │ servers (LIS,    │
                                                       │ Payer, phr, EHR) │
                                                       └──────────────────┘
```

The engine is a **content-based router** with HL7↔FHIR transformation. It maintains in-memory `asyncio.Queue` buffers per route and one set of worker tasks per route.

---

## 2. Full Flow of `InterfaceEngine/main.py`

### 2.1 Module-level setup (lines 1–155)

| Range | Purpose |
| --- | --- |
| [1–29](InterfaceEngine/main.py#L1-L29) | Imports — FastAPI, httpx, SQLAlchemy, internal routers, validation helpers |
| [31–33](InterfaceEngine/main.py#L31-L33) | Silence `SAWarning`, ensure `logs/` and `validation_logs/` exist |
| [35–46](InterfaceEngine/main.py#L35-L46) | `HealthRequestFilter` — splits `/health` noise from main logs |
| [48–64](InterfaceEngine/main.py#L48-L64) | `MidnightSingleFileHandler` — wipes the log file at midnight (only one file kept) |
| [67–110](InterfaceEngine/main.py#L67-L110) | Two named loggers (`interface_engine.main`, `interface_engine.mapping`) wired to three rotating handlers: `main.log`, `main_mapping.log`, `health_checks.log` |
| [112–128](InterfaceEngine/main.py#L112-L128) | `lifeSpan` async context manager — spawns 3 background tasks at startup and cancels them on shutdown |
| [130–148](InterfaceEngine/main.py#L130-L148) | FastAPI app construction: CORS (wide-open), DB schema create, rate-limiter, router includes for `/server`, `/route`, `/endpoint`, `/logs`, `/user` |
| [150–154](InterfaceEngine/main.py#L150-L154) | `db_logger` — separate logger that writes structured rows into a DB table via `db_logger.DBHandler` |
| [156–164](InterfaceEngine/main.py#L156-L164) | Root `GET /` health endpoint |
| [166–173](InterfaceEngine/main.py#L166-L173) | Global in-memory state: `active_route_listners`, `route_queue`, `destination_semaphores`, and tunable env vars (`BATCH_CONCURRENCY=25`, `ROUTE_WORKER_CONCURRENCY=15`, `DESTINATION_CONCURRENCY=3`, `HTTP_READ_TIMEOUT=30`) |

### 2.2 Background task: `route_manager()` (lines 188–236)

Spawned at startup via `lifeSpan`.

1. **Loop forever** (every 5 s):
   1. Open a DB session, query **all** `Route` rows, close session.
   2. For each route **not already** in `active_route_listners`:
      - Create an `asyncio.Queue()` under `route_queue[route.route_id]`.
      - Spawn `_ROUTE_WORKER_CONCURRENCY` (default 15) `route_worker` tasks.
      - Track the task list in `active_route_listners[route.route_id]`.
2. On `CancelledError`, cancel every worker and `gather(...return_exceptions=True)`.

### 2.3 Worker task: `route_worker(route, worker_number)` (lines 238–518)

Each worker is dedicated to one route. The setup (lines 247–280):
1. Open DB session, load `dest_endpoint`, `dest_server`, `src_server`, source/dest `EndpointFields`, and `MappingRule`s for the route. Close session.
2. Build three lookup maps:
   - `src_id_to_path` (endpoint_field_id → path)
   - `dest_id_to_path`
   - `dest_path_to_resource`
3. Construct `dest_endpoint_url = f"http://{dest_server.ip}:{dest_server.port}{dest_endpoint.url}"`.
4. Create a long-lived `httpx.AsyncClient`.
5. Acquire a per-destination `asyncio.Semaphore` capped at 3.

Then the worker enters `while True:` (line 282 onward):

1. Block on `route_queue[route.route_id].get()` → unpack `(src_path_to_value, simple_paths, result_future, src_msg)`.
2. Walk `mapping_rules_for_specific_route`:
   - **concat** rules collected into `concat_data` keyed by `dest_field_id`.
   - **split** rules collected into `split_data` keyed by `src_field_id`.
   - **simple** (copy/map/regex/format) rules transformed inline:
     - `increment_segment` bumps repeated segments (`PID-5.1` → `PID[1]-5.1`).
     - Apply `map`, `regex`, or `format` (date format with two fallbacks).
     - Write into `output_data[dest_path]`.
3. Process `concat_data` → join multiple source paths with a delimiter.
4. Process `split_data` → split a single source value into multiple destination paths.
5. `fill_duplicate_missing_values(output_data)` plus `set_null_if_not_available(...)`.
6. Build the outbound message:
   - FHIR → `build_fhir_message(output_data, dest_path_to_resource)` returns dict.
   - HL7 → `build_hl7_message(...)` returns text.
7. **Deliver** (lines 446–500):
   - Re-query `dest_server` for fresh status.
   - **If destination is `Inactive`, sleep 20 s and re-query forever** (no max retries).
   - Set `System-Id`, `Src-System-Id`, `Src-System-Name` headers.
   - Acquire `destination_semaphore`, POST with `json=` for FHIR or raw `content=` for HL7.
   - On 2xx: `db_logger.info(...)`, `result_future.set_result(True)`.
   - On non-2xx: `db_logger.error(...)`, `result_future.set_exception(Exception(err))`.
8. Catch-all exceptions log + close `client` + return — see [Issue I-1](#section-4-issues-and-bugs).

### 2.4 Per-message pipeline: `_process_message(...)` (lines 521–640)

Used by both `POST /batch` and the generic `POST /{full_path:path}`.

1. Look up `Server` by `system_id` header. If missing, **only logs a warning** ([Issue I-7](#section-4-issues-and-bugs)).
2. Look up `Endpoint` by normalized URL + server_id. If missing → `404`.
3. Load all `EndpointFields` for the endpoint and all `Route`s where this is the source endpoint.
4. **FHIR path**:
   - Validate the resource via `validate_unknown_fhir_resource(...)`.
   - If Bundle, walk entries; otherwise extract directly.
   - Build `simple_paths` (raw) and `paths` (increment-segment-aware) plus `bundle_path_to_resource` map.
5. **HL7 path**: split by `\n`, skipping MSH (line 0), call `hl7_extract_paths` per segment.
6. Resolve actual values into `src_path_to_value`:
   - FHIR → `get_fhir_value_by_path` per resource (Bundle-aware).
   - HL7 → `get_hl7_value_by_path` on the full message.
7. For every matching route:
   - If `route.route_id in route_queue` → create a `loop.create_future()`, push the tuple onto the queue, track the future.
   - Else → log `route_queue_missing` warning ([Issue I-3](#section-4-issues-and-bugs)).
8. `await asyncio.wait_for(future, timeout=_HTTP_READ_TIMEOUT + 10)` for each future. Aggregate errors and raise `502` if any.

### 2.5 Public endpoints

| Endpoint | Path | Role |
| --- | --- | --- |
| `GET /` | health | `{"message": "✔ Interface Engine running"}` |
| `POST /batch` | [642–706](InterfaceEngine/main.py#L642-L706) | Accepts a JSON array of `{system_id, "/path": <msg or [msg,...]>}` items. Concurrency capped at `BATCH_CONCURRENCY=25` via a semaphore. |
| `POST /{full_path:path}` | [709–762](InterfaceEngine/main.py#L709-L762) | Generic ingress. Looks up server by `System-Id` header, falls back from JSON to raw text for HL7. |

### 2.6 Startup-time imports also wire in sub-routers

| Prefix | Source |
| --- | --- |
| `/server` | [api/server.py](InterfaceEngine/api/server.py) — server CRUD + `server_health` (30 s loop) + `get_lis_payer` (30 s loop posting connected systems to EHR @ `127.0.0.1:8001`) |
| `/route` | [api/route.py](InterfaceEngine/api/route.py) |
| `/endpoint` | [api/endpoint.py](InterfaceEngine/api/endpoint.py) |
| `/logs` | [api/logs.py](InterfaceEngine/api/logs.py) |
| `/user` | [api/user.py](InterfaceEngine/api/user.py) |

---

## 3. Senders Pushing Data into the Engine

All callers use `asyncio.create_task(send_to_engine(...))` (fire-and-forget) — see [Issue S-1](#section-5-issues-in-senders).

| Sender file | Target URL | Payload | System-Id source |
| --- | --- | --- | --- |
| [EHR/api/patient.py:267](EHR/api/patient.py#L267) | `http://127.0.0.1:9000/fhir/add-patient` | FHIR `Bundle` (Patient + Coverage) | `hospital.hospital_id` |
| [EHR/api/visit_note.py:263](EHR/api/visit_note.py#L263) | `http://127.0.0.1:9000/fhir/add-visit-note` | FHIR `Bundle` | `hospital.hospital_id` |
| [EHR/api/claim.py:165](EHR/api/claim.py#L165) | `http://127.0.0.1:9000/fhir/submit-claim` | FHIR `Claim` | `hospital.hospital_id` |
| [EHR/api/engine_service.py:134](EHR/api/engine_service.py#L134) | `http://127.0.0.1:9000/fhir/send-response-claim` | FHIR `ClaimResponse` | claim's `system_id` |
| [LIS/api/results.py:170](LIS/api/results.py#L170) | `http://127.0.0.1:9000/submit-lab-result` | HL7 `ORU^R01` | `lab.lab_id` |
| [Payer/api/claims.py:248](Payer/api/claims.py#L248) | `http://127.0.0.1:9000/send/claim_response` | HL7 message | `test_req.insurance_id` |

### 3.1 EHR `send_to_engine` ([EHR/api/engine_service.py:29](EHR/api/engine_service.py#L29))
- `httpx.AsyncClient()` per call, `Content-Type: application/json`, 60 s read / 5 s connect timeout.
- Calls `response.json().get("detail", ...)` on any non-200, which **crashes if the engine returns non-JSON** (see [Issue S-3](#section-5-issues-in-senders)).

### 3.2 LIS `send_to_engine` ([LIS/api/engine_service.py:24](LIS/api/engine_service.py#L24))
- `Content-Type: text/plain`, timeout **`7` seconds total** — far too aggressive for the engine's full fan-out.
- Same `response.json()` pitfall.

### 3.3 Payer `claim_response_to_engine` ([Payer/api/engine_service.py:253](Payer/api/engine_service.py#L253))
- **Uses synchronous `httpx.post(...)` inside an `async` function** — blocks the event loop ([Issue S-4](#section-5-issues-in-senders)).
- `response` is referenced in the `except` clause before it's guaranteed bound ([Issue S-5](#section-5-issues-in-senders)).
- Doesn't return anything on non-2xx — the awaiter sees `None`.

### 3.4 PHR (no senders, receive-only)
- [phr/api/engine_service.py](phr/api/engine_service.py) only exposes `/add/patient`, `/get-visit-note`, `/receive-response-claim` for the engine to call.

---

## 4. Issues & Bugs — InterfaceEngine/main.py

> **Severity legend:** `[BLOCKER]` causes data loss / hangs · `[HIGH]` correctness or safety hazard · `[MED]` operational pain · `[LOW]` polish.

### I-1 `[BLOCKER]` Route-worker outer `except` was silent ✅ FIXED
[main.py:515-519](InterfaceEngine/main.py#L515-L519) — the catch-all `except` had no logging, swallowing the exception entirely. Workers could die at startup (e.g. `dest_server` is `None`) and the only symptom was hanging requests. **Patched** in the previous turn to call `logger.exception(...)`.

### I-2 `[BLOCKER]` `await future` could hang forever ✅ FIXED
[main.py:626-633](InterfaceEngine/main.py#L626-L633) — if a worker crashed, the future was never resolved. **Patched** to use `asyncio.wait_for(future, timeout=_HTTP_READ_TIMEOUT + 10)`.

### I-3 `[HIGH]` `route_queue_missing` returns 200 instead of error ✅ FIXED
**Patched** — `_process_message` now raises `503 Service Unavailable` listing the missing routes when `routes` exists but none of them have a queue ready.

### I-4 `[HIGH]` Worker exits silently if a route is deleted mid-flight ✅ FIXED (with I-19)
**Patched** — `route_manager()` now diffs `active_route_listners` against DB-current routes each tick, cancels workers of deleted routes, and removes their queue. `route_worker` also bails immediately if `dest_endpoint`/`dest_server`/`src_server` resolves to `None`.

### I-5 `[HIGH]` "Inactive destination" loop blocks the worker forever ✅ FIXED (park-and-resume)
**Patched** — three new env vars (`INACTIVE_DEST_MAX_RETRIES`, `INACTIVE_DEST_BACKOFF_SECS`, `REDELIVERY_CHECK_INTERVAL`) drive the new behavior:
1. The worker retries the inactive destination up to N times.
2. If still inactive, the message is parked in `pending_redelivery[dest_server_id]` and the future resolves with `{"status": "queued_for_retry", ...}` so the caller doesn't hang.
3. A new background task `redelivery_watcher()` (spawned in `lifeSpan`) polls every `REDELIVERY_CHECK_INTERVAL` seconds, and re-enqueues parked items the moment the destination flips back to `Active`.
4. Parked messages are also recorded into the DB log via `db_logger.warning(...)` for visibility.

> **Trade-off:** parked messages live in memory only. If the engine process restarts, they are lost. A future iteration could persist them to a `pending_delivery` table.

### I-6 `[HIGH]` Mapping rule iteration multiplies by `simple_path_counts` ❌ NOT TOUCHED
Left in place — the behavior may be intentional for repeated segments and needs a dedicated unit test before changing. Flagged for follow-up.

### I-7 `[HIGH]` `_process_message` doesn't bail on missing server ✅ FIXED
**Patched** — now raises `HTTPException(400, "No server registered for System-Id '...'")` immediately when the server lookup returns `None`.

### I-8 `[MED]` DB sessions leak on exception ✅ FIXED (partial)
**Patched** — `_process_message`, `route_worker` setup, `route_manager`, the inactive-destination loop, and `redelivery_watcher` all use `with session_local() as db:`. Some smaller call sites in `api/server.py` (`server_health`, `get_lis_payer`) still use manual `db.close()`; flagged for follow-up.

### I-9 `[MED]` `asyncio.get_event_loop()` is deprecated in 3.10+ ✅ FIXED
**Patched** — replaced with `asyncio.get_running_loop()` in `_process_message` and `redelivery_watcher`.

### I-10 `[MED]` `MidnightSingleFileHandler` destroys forensic history ✅ FIXED
**Patched** — added `LOG_BACKUP_COUNT` env var (default 7) and applied it to all three `MidnightSingleFileHandler` instances. A week of rotated logs is retained.

### I-11 `[MED]` Global mutable state shared across all events ❌ NOT TOUCHED
Architectural refactor — left in place. Safe today because everything runs on a single event loop and there are no `run_in_executor` calls touching this state.

### I-12 `[MED]` CORS wide open ❌ NOT TOUCHED
Deployment decision — appropriate for the local simulator. Tighten before exposing publicly.

### I-13 `[MED]` `httpx.AsyncClient` per route worker — never closed under cancellation ✅ FIXED
**Patched** — `route_worker` now declares `client = None` up front and closes it in a `finally:` block. A dedicated `except asyncio.CancelledError:` re-raises after logging so shutdown stays graceful.

### I-14 `[MED]` `set_null_if_not_available` runs even when transformation already failed ✅ FIXED
**Patched** — added an explanatory comment above the `continue` to make the control flow obvious to future readers. (No restructure needed; the original behavior was correct, just fragile-looking.)

### I-15 `[LOW]` `result_future.set_result/set_exception` not guarded everywhere
If the worker is cancelled between `route_queue.get()` and `set_result/set_exception`, the awaiter hangs. Add `try/finally` to always resolve the future.

### I-16 `[LOW]` `_payload_preview` is referenced for HL7 but bypassed for FHIR
[main.py:566 vs 546](InterfaceEngine/main.py#L546-L566) — FHIR payload is logged in full (`%s`, payload), HL7 is truncated. Either truncate both or log both fully. Full FHIR bundles in logs are expensive.

### I-17 `[LOW]` `dest_server`, `dest_endpoint`, `src_server` could be `None`
[main.py:249-251](InterfaceEngine/main.py#L249-L251) — if any row was deleted, `.ip`, `.port`, `.url`, `.system_id`, `.protocol`, `.name` accesses crash. Add explicit `if dest_server is None: logger.error(...); return`.

### I-18 `[LOW]` `_HTTP_READ_TIMEOUT + 10` is still tight for slow downstreams
40 s might not be enough for a destination that itself fans out. Make this a separate env var (`INGEST_AWAIT_TIMEOUT`) so it can be tuned independently of `httpx`.

### I-19 `[LOW]` `route_manager` never sees route **deletes** ✅ FIXED (with I-4)
**Patched** in the same change as I-4.

### I-20 `[LOW]` `db_logger` uses `extra={"src_message": ..., "dest_message": ..., "op_heading": ...}`
If anyone adds standard fields with those names (`message`, `levelname`), `LogRecord` raises a `KeyError`. Wrap the DB write in `try/except` inside `DBHandler.emit`.

### I-21 `[LOW]` Path `/{full_path:path}` swallows everything
This generic POST handler catches **any** unknown path, including misspellings of `/server`, `/route`, etc., as long as no router matched first. Order of route registration matters; `/batch` is defined before this generic, but `/server/health` for instance is fine because it's a router with a prefix. Worth documenting.

---

## 5. Issues in Senders (`engine_service.py` + callers)

### S-1 `[HIGH]` Fire-and-forget `asyncio.create_task(send_to_engine(...))` loses errors
Every caller uses the same pattern — they commit their DB changes first, then *schedule* the engine call. If the engine returns 502 (destination unreachable), the EHR/LIS/Payer DB already shows "sent" but downstream has nothing. Cases:
- [EHR/api/patient.py:267](EHR/api/patient.py#L267)
- [EHR/api/visit_note.py:263](EHR/api/visit_note.py#L263)
- [EHR/api/claim.py:165](EHR/api/claim.py#L165)
- [EHR/api/engine_service.py:134](EHR/api/engine_service.py#L134)
- [LIS/api/results.py:170](LIS/api/results.py#L170)
- [Payer/api/claims.py:248](Payer/api/claims.py#L248)

Fix options: `await` the call (block the user), persist a "pending" row and retry from a worker, or use an outbox pattern.

### S-2 `[HIGH]` LIS uses **7 s** total timeout ✅ FIXED
**Patched** — switched to `httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))`. Also added a dedicated `httpx.ReadTimeout` handler that raises a clearer error.

### S-3 `[HIGH]` `.json()` on a non-JSON error response ✅ FIXED
**Patched** — both EHR and LIS `send_to_engine` now wrap the `.json()` parsing in a `try/except` and fall back to `response.text` (or the status line) so the original engine error is preserved.

### S-4 `[BLOCKER]` Payer uses **sync** `httpx.post` inside `async def` ✅ FIXED
**Patched** — `claim_response_to_engine` now uses `async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client: await client.post(...)`. The event loop no longer blocks.

### S-5 `[HIGH]` Payer's `except` references unbound `response` ✅ FIXED
**Patched** — `response = None` is initialized before the `try`, and the except block formats it safely (`status=...` if available, otherwise `"no response (request never completed)"`).

### S-6 `[MED]` Payer logs HL7 message as "patient registration" ✅ FIXED
**Patched** — `/submit-claim` now logs `"Received HL7 claim submission"` and `"Extracted values from claim HL7 message"` instead of the registration string.

### S-7 `[MED]` Payer registration fallback hardcodes `localhost:8003`
[Payer/api/engine_service.py:152](Payer/api/engine_service.py#L152) — `http://localhost:8003/reg_patient/...` is hardcoded. Should be an env var or pulled from server config.

### S-8 `[MED]` LIS `take_lab_order` skips silently
[LIS/api/engine_service.py:188-190](LIS/api/engine_service.py#L188-L190) — if `test_code` doesn't exist, the orderline is silently skipped. Combined with the `if not lab_orders: return {"message": "No lab orders..."}` at line 208, you can silently lose every order in a batch.

### S-9 `[MED]` `subscriberId` and `user_id` hardcoded to `0`
[EHR/api/engine_service.py:124](EHR/api/engine_service.py#L124) and [Payer/api/engine_service.py:159](Payer/api/engine_service.py#L159) — looks like placeholder TODOs that shipped.

### S-10 `[LOW]` Typo `sucessfull`
EHR/LIS both return the literal string `"sucessfull"`. Cosmetic but visible in logs.

### S-11 `[LOW]` `_process_message` is invoked but the caller passes `full_path` from a possibly-reassigned local
[main.py:581](InterfaceEngine/main.py#L581) — inside the FHIR Bundle branch, `full_path = f"{res_type}-{p}"` shadows the parameter `full_path`. Later code uses the parameter (or thinks it does). Harmless today but a footgun.

### S-12 `[LOW]` PHR `/add/patient` requires `name[0].text` etc. with no `.get`
[phr/api/engine_service.py:79-86](phr/api/engine_service.py#L79-L86) — uses `db_data["name[0].text"]` (direct subscript). Any missing FHIR field → `KeyError` → 400 with raw stacktrace info in detail.

---

## 6. End-to-End Flow Diagram

```
EHR.add_patient                LIS.upload_result          Payer.claim_status
       │                              │                          │
       │ create_task(send_to_engine)  │ create_task(...)         │ create_task(claim_response_to_engine)
       ▼                              ▼                          ▼
                  POST http://127.0.0.1:9000/<endpoint>
                  Headers: System-Id: <src_system_id>
                              │
                              ▼
       ┌─────────── InterfaceEngine main.py ───────────────┐
       │ ingest()  → lookup Server by System-Id            │
       │           → lookup Endpoint by URL+server_id      │
       │           → _process_message()                    │
       │             ├─ validate (FHIR) or split (HL7)     │
       │             ├─ extract paths + values             │
       │             ├─ enqueue (src_paths, future, msg)   │
       │             │  onto route_queue[route_id]         │
       │             └─ await wait_for(future, ~40s)       │
       │                                                   │
       │ route_worker (×15 per route)                      │
       │   ├─ load mapping rules, endpoint fields          │
       │   ├─ apply copy/map/regex/format/concat/split     │
       │   ├─ fill_duplicate, set_null_if_not_available    │
       │   ├─ build_fhir_message or build_hl7_message      │
       │   ├─ if dest_server.status == "Inactive": wait    │
       │   ├─ semaphore.acquire (max 3 per destination)    │
       │   ├─ httpx POST to dest_endpoint_url              │
       │   └─ resolve future (True / Exception)            │
       └───────────────────────────────────────────────────┘
                              │
                              ▼
            POST to destination (LIS/Payer/phr/EHR)
            Headers: System-Id, Src-System-Id, Src-System-Name
```

---

## 7. Suggested Next Steps (Priority Order)

1. **Fix Payer's sync `httpx.post`** ([S-4](#s-4-blocker-payer-uses-sync-httpxpost-inside-async-def)) — single biggest correctness win, blocks the whole engine pipeline whenever a claim response is sent.
2. **Bump LIS timeout** ([S-2](#s-2-high-lis-uses-7-s-total-timeout)) — currently every lab-result send fails for any moderately busy engine.
3. **Guard `_process_message` against missing server** ([I-7](#i-7-high-_process_message-doesnt-bail-on-missing-server)).
4. **Return error when `route_queue_missing`** ([I-3](#i-3-high-route_queue_missing-returns-200-instead-of-error)) — fixes the silent "we sent nothing but responded 200" case.
5. **Reconcile deleted routes** ([I-4](#i-4-high-worker-exits-silently-if-a-route-is-deleted-mid-flight) & [I-19](#i-19-low-route_manager-never-sees-route-deletes)) — periodic diff between DB and `active_route_listners`, cancel orphaned workers.
6. **Replace fire-and-forget pattern with an outbox** ([S-1](#s-1-high-fire-and-forget-asynciocreate_tasksend_to_engine-loses-errors)) — biggest data-integrity improvement.
7. **Add max retries / DLQ for inactive destinations** ([I-5](#i-5-high-inactive-destination-loop-blocks-the-worker-forever)) — surface dead destinations to operators instead of swallowing them in a 20 s sleep loop.
8. **Switch DB session management to `with session_local() as db:`** ([I-8](#i-8-med-db-sessions-leak-on-exception)).
9. **Tighten the `.json()` error path** ([S-3](#s-3-high-json-on-a-non-json-error-response)) and fix the unbound `response` ([S-5](#s-5-high-payers-except-references-unbound-response)).
10. **Cosmetic / safety**: rotate logs with retention ([I-10](#i-10-med-midnightsinglefilehandler-destroys-forensic-history)), restrict CORS in production ([I-12](#i-12-med-cors-wide-open)), parameterize URLs ([S-7](#s-7-med-payer-registration-fallback-hardcodes-localhost8003)).
