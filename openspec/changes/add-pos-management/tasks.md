# Tasks

## 1. Schema and shared foundations

- [x] 1.1 Add openpyxl and multipart dependencies and import settings; verify `uv sync`, lockfile consistency, and bounded settings validation tests.
- [x] 1.2 Add POS registry/history/summary/tag/visit/import/notification/settings models with actor fields and constraints; verify metadata matches the design's eleven new tables.
- [x] 1.3 Generate and manually review Alembic migration(s), btree_gist provisioning, seeded settings/tags, partial/exclusion constraints, snapshot trigger, and runtime grants; verify fresh upgrade and upgrade from the core schema using PostgreSQL tests.
- [x] 1.4 Extend tests/test_schema.py's exact table set and runtime privilege tests; verify business DELETE, audit mutation, snapshot mutation, and overlapping ranges are rejected while normal runtime writes succeed.
- [x] 1.5 Extend shared mobile normalization and Jalali month/range helpers; verify all confirmed mobile variants, invalid values, leading zeros, year rollover, and leap/non-leap Esfand tests.
- [x] 1.6 Serialize Decimal audit/snapshot values losslessly and retain secret filtering; verify amount/date round trips and redaction regression tests.
- [x] 1.7 Document the new schema, migration prerequisites, and import configuration in operations/API guidance and .env.example; verify documented names match validated settings.

## 2. Terminal registry and organization integration

- [x] 2.1 Implement terminal schemas and create/list/detail/correction/delete/restore routes/services with current branch scoping; verify role isolation, normalized uniqueness, contact/account text, filters, pagination, and deleted-number conflict tests.
- [x] 2.2 Implement branch/owner history and effective-dated transfer/handover, including audited same-day corrections; verify nonoverlap, no physical deletion, and historical identity tests.
- [x] 2.3 Extend the shared lifecycle lock to terminal and relevant org/user mutations, recheck actor eligibility, add branch device counts/deletion guards, and enforce inactive-branch placement rules; verify branch deletion versus terminal creation/transfer race tests.
- [x] 2.4 Implement scoped write-only XLSX export and identifier/formula-safe output helpers; verify exported content/scope and row-limit failures by opening generated workbooks.
- [x] 2.5 Document registry/history/export APIs and account/contact fields in docs; verify examples use synthetic data and Jalali dates.

## 3. Transaction summaries and live performance

- [x] 3.1 Implement amount/count period schemas, manual CRUD/history, exact-period correction, device locking, exclusion-error mapping, and soft deletion; verify count-only correction, overlap/concurrency, retired-device, and scope tests.
- [x] 3.2 Implement singleton policy GET/PATCH with Supervisor-only edits and versioned audit; verify exact initial values, invalid threshold ordering, role checks, and atomic pair updates.
- [x] 3.3 Implement shared grouped SQL performance aggregate, classification, coverage/record count, per-device series, ranking filters/sorts, and month/range defaults; verify both boundaries, zero versus no data, partial overlaps, deleted summaries, total-range semantics, and manager isolation.
- [x] 3.4 Document transaction/productivity/settings endpoints, rial units, current-policy behavior, last-complete-Jalali-month default, and multi-month totals; verify examples against API responses.

## 4. Import engine and sample compatibility

- [x] 4.1 Implement bounded first-visible-sheet XLSX parsing, canonical aliases, duplicated-header detection, numeric/text identifier conversion, and ignored classification columns; verify sample headers, leading-zero formats, corrupt workbooks, formula cache behavior, and limit tests.
- [x] 4.2 Implement safe original-file storage, checksum hints, durable processing/failure/finalization boundaries, row errors/savepoints, and reconciled row/component counters; verify fault injection leaves accurate logs and no false successful rows.
- [x] 4.3 Implement create-only registry import and new-terminal history initialization; verify existing rows skip even when other source fields differ, deleted matches fail, duplicates report row numbers, and valid rows survive neighboring failures.
- [x] 4.4 Implement transaction import with amount/count aliases, upload-level Jalali month or explicit row periods, exact-period upsert, and overlap errors; verify month 1405/7, leap-month limits, conflicting dates, count-only changes, and repeat-file outcomes.
- [x] 4.5 Implement combined import with per-row atomic registry/activity handling and component counters; verify existing registry skip still imports activity and a failed new activity rolls back its new terminal/history.
- [x] 4.6 Implement Supervisor-only templates, logs, row errors, XLSX error reports, and audited original download endpoints; verify access isolation, formula-safe output, path confinement, and round-trip correction/reupload.
- [x] 4.7 Add fail-stale-pos-imports recovery CLI with dry-run/status reporting and no automatic original deletion; verify interrupted processing can be marked failed and active work is protected by documented operator checks.
- [x] 4.8 Add synthetic workbook fixtures mirroring both sample files, replacing placeholder mobiles; verify aliases and ignore-classification behavior without committing real banking data. Document upload modes, XLSX-only scope, limits, counters, recovery, and combined-file examples.

## 5. Dispatch queue, notifications, and employee visits

- [x] 5.1 Implement core transactional notification insertion and recipient-only list/count/read/read-all routes; verify privacy, idempotence, rollback, and fresh authorization of linked visits.
- [x] 5.2 Implement Supervisor dispatch with one consistent aggregate/policy snapshot statement, immutable evidence, owning-branch routing, and per-item bulk results; verify multi-branch, no-data, duplicate dispatch, retired/inactive branch, and client-snapshot rejection cases.
- [x] 5.3 Implement scoped branch pending queue and owning-manager assign/bulk-assign using pending visit IDs; verify managers cannot dispatch or bypass selection, only eligible same-branch employees can receive work, and pending work never appears to employees.
- [x] 5.4 Implement reassignment/cancellation and terminal-transfer cancellation of pending/assigned work with notifications; verify loss/gain of assignee access, original branch/evidence preservation, and closed-state conflicts.
- [x] 5.5 Implement employee completion, tag administration, archive retrieval, and Supervisor completed-result correction; verify assignee-only access, timestamp/tag validation, no status automation, and immutable snapshot fields.
- [x] 5.6 Add employee assigned-work lifecycle guards in shared core/users integration; verify deactivation/delete/role/branch changes reject with task counts and archived/pending-only work does not block unrelated users.
- [x] 5.7 Exercise concurrent dispatch, assign versus employee move/deactivation, completion versus transfer, and cancel versus complete with separate database connections; verify lock ordering, no duplicate open work, and consistent final state/audit/notifications.
- [x] 5.8 Document the dispatch-to-branch-to-employee APIs, notification events, branch-without-manager behavior, snapshot fields, and correction permissions; verify examples cannot create employee work without Supervisor selection.

## 6. Reports and operational validation

- [x] 6.1 Implement role-scoped POS summary aggregates, separating pending from assigned work and current registry from historical visit branch data; verify employee-only metrics, date windows, no-data recency, and manager branch filters.
- [x] 6.2 Document report fields and calendar windows and verify documented examples against synthetic query results.
- [x] 6.3 Add an end-to-end PostgreSQL scenario from registry/monthly import through policy query, dispatch, assignment, completion, correction, and policy change; verify original snapshots and audit remain intact while current performance changes.
- [x] 6.4 Run targeted POS tests and the full core regression suite, Ruff lint/format checks, and fresh migration verification; record command results in verification documentation.

## Workflow follow-up

- Review the planning artifacts before applying this change.
- Sync deltas to main OpenSpec specs and archive only after implementation and its validation are complete.

## Verification skipped by user request

On 2026-11-17 the user requested skipping further performance and smoke tests. These checks are excluded from the remaining required task count, not marked as completed.

- 6.5 Profile ranking and summaries on synthetic 50,000-terminal/2-million-summary data with EXPLAIN and measure bounded import/export latency; record query plans, p95 results against the 300 ms list target, and any required index adjustments. **Skipped: user request.**
- 6.6 Verify deployed upload-size errors, persistent import storage, original/error download authorization, and the complete browser API smoke flow; record evidence and confirm the Phase 1 architecture remains consistent with the delivered contracts. **Skipped: user request.**
