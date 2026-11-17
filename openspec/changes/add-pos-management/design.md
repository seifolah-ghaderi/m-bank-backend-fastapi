# Design

## Context

See proposal.md for motivation and the eleven capability deltas for contracts. The existing FastAPI backend has six business/security tables, async SQLAlchemy request transactions, centralized scope, Jalali Pydantic boundary types, sanitized audit, an administration advisory lock, and real-PostgreSQL tests. `docs/organization.md` explicitly defers device counts, branch guards, and employee open-work guards to POS. No POS model, import engine, notification feature, or openpyxl dependency exists yet.

The Phase 1 source is the architecture baseline. This change replaces its registry-upsert default, amount-only summaries, average-monthly placeholder, and direct visit creation with the approved contracts. Existing OpenSpec Jalali/web/SMS contracts remain authoritative over older core descriptions. Phase 2 remains a draft: its future asynchronous lead import can reuse provenance tables but its verified customer conversion is independent of terminal owner/account data.

## Goals / Non-Goals

**Goals:** Keep one application/database; enforce work invariants under concurrency; make imports retryable and errors actionable; share one query expression for live performance; preserve selection evidence without persisting derived terminal classifications.

**Non-Goals:** UI, CSV parsing in this first XLSX delivery, automatic visit selection, automatic employee allocation, a generic task framework, imported performance labels, leads/customers/sales, Core Banking, external notification delivery, Redis/Celery, and scheduled overdue alerts.

## Decisions

### 1. Feature layout and shared infrastructure

Use the Phase 1 `app/features/pos/` layout: device, transaction, import, and visit routers/services plus `productivity.py` and `import_columns.py`; add a small settings router/service in the same feature. Notifications and reports have their own feature packages. Put XLSX helpers in `app/core/excel.py`, reusable transaction-safe notification insertion in `app/core/notifications.py`, and POS lifecycle queries in `app/core/lifecycle.py`. Avoid cross-feature service imports; POS import may call POS device/transaction services within its feature.

Extend existing models/schemas, shared constraint-error mapping, core/dates month-bound helpers, and core/audit Decimal serialization. Keep existing schemas and request IDs/errors/pagination/Jalali outputs. Extend the existing Scope implementation explicitly for visits: employee scope is `assigned_to`, never generic branch scope. Business routers remain thin. Direct SQL or model checks in core prevent org/users services from importing the POS service.

Alternative: a generic workflow/import framework would add abstractions before Phase 2 is implemented; keep reusable primitives without building a job platform.

### 2. Eleven new tables and core integrations

Add `pos_devices`, `pos_device_branch_history`, `pos_device_owner_history`, `pos_monthly_transactions`, `pos_tags`, `pos_visits`, `pos_visit_tag_links`, `import_logs`, `import_row_errors`, `notifications`, and `pos_performance_settings` in reviewed migrations, leaving existing six tables intact. Continue UUIDv7 actor metadata and soft deletion where specified.

- Devices keep canonical `device_number` (sample alias `pos_code`), branch FK, owner/contact fields, optional `account_number` text and `contact_phone`, operational status, source, and last import reference. Account number is at most 100 characters and contact phone at most 30; neither is a verified customer identity. Add those fields to owner history because account/contact may change on handover. Do not add any source or calculated classification column to devices.
- Preserve the existing spec's live-unique device number index, branch/status and trigram indexes. Deleted matches are explicit import errors; restoring into a reused live number fails.
- History uses inclusive native dates, one open row, and GiST exclusions using btree_gist. For a later effective date close the old row one day before it and open the replacement. For another change on the same start date update the open row in place and record before/after in append-only audit; never delete history or create a negative range. Return effective date and actor history plus the audit link.
- Summaries use `numeric(20,2)` rial amount, bigint count, inclusive date checks, source/import provenance, soft deletion, and an exclusion on terminal/range for live rows. Exact-period matching precedes the overlap guard. Terminal history stays attached to its device; manager transaction access uses the device's current branch. Visits retain their branch-at-dispatch separately. This resolves the source's reference to a transaction branch_id that was absent from its schema.
- Settings use one seeded singleton row with lower/upper numeric thresholds and a version increment per edit; validate 0 <= lower < upper. The policy is a database record editable through Supervisor APIs, not an environment-only default.
- `pos_visits` represents the entire lifecycle; no separate queue table is needed. Add pending state, nullable employee assignment fields, `selected_by/selected_at`, immutable `branch_id`, and typed snapshot columns: range start/end, nullable amount/count, no-data flag, classification, thresholds, policy version, unit/method. Snapshot Decimal values remain exact. A database trigger rejects changing snapshot/selection/dispatch-branch columns after insert; visit completion/correction can only update permitted work fields.
- Partial unique index on device where state in (`pending_assignment`, `assigned`); state checks require null assignment fields while pending, assignment metadata while assigned/completed, completion fields when completed, cancellation metadata when cancelled. Tags use a unique code and historical links survive deactivation.
- Imports store type (`pos_devices`, `pos_transactions`, `pos_combined`), fixed effective mode, checksum/storage key, selected period, counters, status/times, and metadata. Combined counters separately report registry created/skipped and activity created/updated/unchanged. Ordinary row outcome counts sum to total nonempty rows; a row can be successful while its registry component is skipped.

Extend branch output with live device count and block deletion with any live terminal. Deactivation keeps existing work completable but rejects new terminal placement/dispatch/assignment. Add employee assigned-work guard on deactivation/deletion/role or branch change; do not block ordinary profile edits or password reset.

### 3. Import pipeline and transaction boundaries

Retain the Phase 1 bounded synchronous XLSX contract (10 MB, 5,000 data rows, first visible sheet), read-only openpyxl and cached formula values. No CSV input in this delivery; sample references to CSV motivate text-safe identifiers, not a second parser. Add openpyxl and python-multipart to uv dependencies.

Provide separate `/pos/imports/devices`, `/transactions`, and `/combined` multipart endpoints and corresponding templates. Registry mode is create_only, transaction mode is upsert, and combined applies both; reject contradictory mode parameters instead of restoring legacy registry upsert. Normalize headers in one alias registry. Map sample Persian owner/mobile/contact/account/address names and English terminal/amount/count aliases. Treat branch name as display-only, and classification aliases as intentionally ignored without unknown-column warnings. Other extras produce warnings. Raw source files remain untouched as provenance; classification does not enter application fields or snapshots.

Convert identifier cells to text exactly: no float-based Decimal/money conversion, no scientific notation strings, preserve existing text zeros and honor simple zero-padding number formats. Never invent leading zeros when Excel already lost them: unmatched branch codes are row errors. Reject nonintegral/precision-damaged numeric identifiers rather than guessing. Amount parsing supports separators/Persian digits; count parsing supports whole nonnegative numbers only. Mobile normalization accepts the user's three forms plus the existing valid international forms, stripping a country prefix once and ensuring exactly one domestic zero before validation. Invalid supplied optional values are errors; blank optional values remain null. Sanitized copies of sample fixtures must replace the deliberately invalid nine-digit mobile placeholders; do not assert all original sample rows import successfully.

Upload year/month applies a server-derived complete Jalali month, including Esfand leap-year behavior. Without it, require row period columns. If both are present require exact agreement. API text dates follow the existing Jalali boundary; true Excel date cells are native Gregorian dates converted for storage/output. Never guess a text calendar by year. Reports/error raw data retain the original source representation.

Validate format/header/row limits before business mutations. Store an original under a random safe key plus SHA-256 and create a processing log in a separate short committed transaction. Then use one business transaction for the file, with a savepoint per row; completed business rows, per-row errors, counters, and final status commit together. Services flush only. If an unexpected failure rolls back the file transaction, finalize its durable log as failed in a separate transaction without claiming rolled-back successes. A process crash leaves processing; `python -m app.cli fail-stale-pos-imports --older-than-minutes N` explicitly marks interrupted records failed after the operator confirms no live importer is running. Do not silently resume partial state. Orphan stored files are listed by the same command in dry-run mode; deletion is outside normal recovery.

For registry matching, validate the business key and detect duplicates first, then skip an existing live terminal before validating changed registry details. For new terminals enforce the full create contract and active branch; never auto-create branches. A combined row uses the same savepoint for any new registry/history plus its activity; a failed transaction rolls the row back together. An existing terminal's registry skip does not block its activity, and transaction/combined imports never transfer an existing device even if the source branch differs. Report such a difference as a warning; current authoritative branch wins. Failed-only files are failed; files with valid skipped/unchanged rows and no errors are completed; any accepted rows plus failures are completed_with_errors. Repeated file checksum is a hint, not a block.

Export/template/error-report writers use write-only XLSX and harmless text cells for formula-like values. Bound ZIP expansion and sheet processing, reject corrupt/encrypted workbooks, resolve storage paths beneath IMPORT_STORAGE_DIR, and audit original downloads. Filesystem writes cannot roll back with PostgreSQL; finish file placement before committing the processing log and retain provenance after later business failure.

### 4. Calendar and performance query semantics

Reuse native date persistence and Jalali boundary types. Add a reusable Jalali year/month-to-native-range helper and range validation with a 24-Jalali-month maximum. Default performance range is the last complete Jalali month; this is a proposed default replacing the old six-month average to align monthly thresholds and sample uploads. Explicit multi-month queries compare the total for the entire named range with the same thresholds; there is no monthly averaging or prorating. Return coverage/record count so partial available data is visible; no rows means no_data, not an inferred zero.

Use one grouped SQL aggregate over live summaries fully contained in the range, left-joined to scoped devices. Sum amount/count; no matching row yields nulls, explicit zero yields 0. CASE uses amount < lower for low, <= upper for normal, else high. Return policy/version, bounds, unit=rials, method=period_total_amount, latest period end, and per-device series. Query-time values never populate device fields. Rankings allow performance/no_data/branch/city/status filters; deterministic order uses nulls last and device number/ID ties. Index and EXPLAIN the ranking at 50,000 devices/2 million summaries; no N+1 per-device history queries.

### 5. Dispatch evidence, assignment, and locking

POST `/pos/visits/dispatch` takes selected IDs (up to 200), one month/range, and optional selector instructions; the server determines current branches, totals, and policy. It creates one pending visit per successful terminal. GET `/pos/visits?status=pending_assignment` serves the scoped branch queue. POST `/pos/visits/{id}/assign` is owning-manager only. POST `/pos/visits/bulk-assign` accepts pending visit IDs (not terminal IDs) and a branch employee, applying the same guards with per-item savepoints. Reassign/cancel/complete and Supervisor completed correction follow the visit spec. Supervisor can dispatch/cancel/correct but cannot bypass the branch manager's employee-assignment step.

Compute all dispatch snapshot aggregates and the settings pair/version in one SQL statement for a consistent MVCC view, after lifecycle locking. Do not accept client-supplied snapshot fields. Save immutable typed snapshot columns on the visit and expose them as a structured response. Selection snapshot remains distinct from a live-performance response. All performance classes and no-data can be dispatched; low/no-data filters aid selection without imposing an unapproved rule that forbids other classes.

Extend the existing transaction-level administration advisory lock `72851901` to POS lifecycle mutations and related organization/user changes. Acquire it before any actor/user/branch/device/visit locks. Re-read acting user role/branch and target eligibility after acquiring it. Within it use consistent user -> branch -> device -> visit ordering, sorted IDs for bulk rows. Dispatch, assign/reassign/cancel/complete/correct, transfer/owner/status/delete/restore, branch lifecycle changes, and registry creation participate. This deliberately serializes lifecycle writes for the initial 100-user target and prevents races with the already serialized employee administration path. Authentication retains its existing user-before-challenge/token locking and never acquires the lifecycle lock after a user lock.

Transaction-only imports take sorted device locks for exact-period matching and summary edits; do not acquire the lifecycle advisory lock after a device lock. Combined/registry imports acquire the lifecycle lock first and may hold it across the bounded file transaction. Threshold edits lock only the singleton and audit, avoiding reverse lifecycle-lock ordering. PostgreSQL unique/exclusion constraints remain final guards. Map known conflicts to domain errors inside row savepoints; do not keep using an aborted SQLAlchemy session. Later optimizing lifecycle serialization requires preserving this concurrency contract and tests; it is not a prerequisite for this scope.

For transfers cancel pending and assigned work before updating device branch; keep old visit branch/evidence. For same-device status becoming retired, retain already-open work (the rule blocks new dispatch only). Employee pending tasks never leak through branch-wide scope. Closed visits are visible to the historical assignee even after their permitted branch move; manager visibility uses visit branch-at-dispatch.

### 6. Notifications, reports, and audit

A core notify helper inserts in the same transaction as business changes; notification APIs operate on current recipient only, with read-all/read-one idempotence. Event types: pos_visit_dispatched (branch manager), pos_visit_assigned, pos_visit_unassigned, pos_visit_cancelled, and pos_visit_completed. Pending cancellation notifies the branch manager when present; no manager means no fake recipient, and the queue remains discoverable to a later manager. Notification links perform fresh resource authorization.

Reports aggregate within supervisor/branch/employee scope before counting. Include pending queue separately. Historical completed counts use visit branch/assignee, not the device's possibly changed current branch. Employee output omits registry-wide fields. Keep pending task counts distinct from overdue assigned tasks.

Audit every successful POS/import/settings action and original-file download; user read markers follow existing non-business read-state behavior. Add exact Decimal-to-string handling to core/audit, since its current JSON sanitizer handles dates/UUIDs but not Decimal. Keep secret redaction; tag codes use an explicitly named safe `tag_code` field rather than removing the existing `code` secret filter. Grant runtime only required insert/select/update privileges, no POS business deletes or audit mutation. Snapshot immutability uses a database trigger alongside service checks. Import error rows/files contain source banking details and remain Supervisor-only.

### 7. API and compatibility choices

Retain the source's device/history/export/transaction/productivity/import/tag/notification/report route families. Add `/pos/performance-settings` GET (Supervisor/Manager), PATCH (Supervisor); `/pos/visits/dispatch` (Supervisor), `/pos/visits/{id}/assign` (owning manager), combined import/template routes, and branch queue filters. Canonical performance routes remain `/pos/productivity` and `/pos/devices/{id}/productivity` for source compatibility, but return the new period-total classification contract. No previous deployed POS APIs exist, so these are new contracts rather than breaking implemented routes.

## Risks / Trade-offs

- Bounded file transaction holds lifecycle locks for registry/combined imports -> cap uploads, prevalidate parsing before taking locks, measure real import latency, and document the temporary blocking of lifecycle writes.
- Spreadsheet numeric identifiers can have irrecoverable zeros/precision loss -> preserve text/formats and reject ambiguous damaged values instead of matching the wrong branch/terminal.
- No-data or incomplete monthly coverage can be mistaken for zero activity -> return null/no_data and record count/coverage, with snapshot fields preserving what was known.
- Mutable policy or imported corrections can rewrite the apparent reason for visits -> immutable server-generated evidence with policy version and selected totals.
- Soft-deleted device-number reuse separates identities -> imports match live terminal identity; deleted-only matches fail and history remains linked by UUID.
- Same-day date history cannot express multiple intraday owners with inclusive dates -> current-day row correction plus append-only audit preserves order without physical deletion.
- Scope helper currently defaults to branch fields -> implement/test explicit employee assigned-to scope before exposing visits, including detail and count queries.

## Migration Plan

1. Review generated migrations for all eleven new tables, partial/exclusion constraints, snapshot trigger, seed policy and tags, permissions, and indexes. Install btree_gist using the existing privileged provisioning path. Extend real-database schema tests that currently assert the exact six-table set.
2. Apply migrations with owner credentials; verify runtime POS writes succeed while history/snapshot deletion and audit/snapshot mutation fail. Existing core data and authentication remain usable.
3. Configure IMPORT_STORAGE_DIR and upload bounds, provision a persistent import volume, and document recovery, backups, permissions, and limits in .env.example/operations guidance. Thresholds live in the seeded settings row, not env overrides.
4. Run core regression tests plus POS constraint/scope/import/concurrency suites. Use synthetic copies of sample columns; exercise actual XLSX responses and deployed upload/download paths.
5. Smoke-test registry import, one Jalali month import, boundary classifications, dispatch across branches, manager assignment, completion, and original snapshot after correction/policy changes. Record ranking EXPLAIN evidence using synthetic scale data.
6. On rollback stop using POS routes and retain all new tables/files; deploy a forward fix. Do not downgrade migrations against nonempty production POS data or delete provenance to roll back application code.


## Verification scope revision

On 2026-11-17 the user requested skipping further performance and smoke tests.
Functional implementation, real-PostgreSQL regression tests, migration checks,
and Ruff remain required. Final performance reruns and deployed smoke/persistence
follow-up are optional and excluded from tracked acceptance tasks. Earlier local
profiles and the initial proxy smoke run are preliminary evidence; they do not
claim final persistence revalidation or production deployment.
