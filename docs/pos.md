# POS management

POS extends the existing core with eleven tables: terminals, branch/owner histories,
period summaries, tags, visits, visit/tag links, import logs/errors, notifications,
and singleton performance settings. Terminal/summary deletion is soft; runtime
credentials cannot physically delete POS business records. PostgreSQL `btree_gist`
enforces nonoverlapping inclusive history/activity periods, and a database trigger
protects the original visit selection evidence. Actor foreign keys preserve history.

Use owner credentials for `uv run alembic upgrade head`; use the non-owner
`crm_runtime` role for the API. The migration requires extension creation privilege
or preinstalled `btree_gist`/`pg_trgm`. It seeds three visit tags and one global
threshold pair (200,000,000 and 1,000,000,000 rials). Production rollback retains
the tables and original files; do not downgrade a populated database.

Import configuration is `IMPORT_STORAGE_DIR` (default `var/imports`),
`IMPORT_MAX_MB` (1–10, default 10), and `IMPORT_MAX_ROWS` (1–5000, default 5000).
The storage directory must be private, writable by the API, persistent across
restarts, and included in backups. Original downloads are Supervisor-only and
audited; never expose that directory through a web-server static route.

Business dates use Jalali strings and native database dates; amounts are exact
decimal rial values. A terminal's operational status is independent of its
query-time transaction performance. Imported performance labels are ignored.

## Registry, history, and export

`/api/v1/pos/devices` supports POST and paginated GET; `/{id}` supports GET,
PATCH corrections, and DELETE. Supervisor-only POST actions are `/{id}/restore`,
`/{id}/transfer`, and `/{id}/change-owner`. The history routes are
`/{id}/branch-history` and `/{id}/owner-history`, newest period first.

Create requires device_number, owner_name, address, and branch_id. Optional fields
are owner_mobile, owner_national_code, shop_name, account_number (text, max 100),
contact_phone (text, max 30), status, and effective_date. Example synthetic body:

```json
{"device_number":"000123", "owner_name":"Synthetic Owner", "address":"Synthetic store address", "branch_id":"00000000-0000-4000-8000-000000000001", "account_number":"00123456", "effective_date":"1405/07/01"}
```

Transfer takes to_branch_id, optional effective_date/reason. Owner change takes
owner details and optional effective_date. Effective dates cannot be future or
earlier than the current history start. Same-start-date corrections preserve the
superseded values in audit without deleting history. Updates cannot directly
change branch; use transfer. Mobile variants normalize before validation.

Supervisors read all terminals, managers only their branch. Employees access
terminal details through assigned work and cannot use the registry/export.
GET filters: q, branch_id, city_id, status, source, has_open_visit,
no_transactions_since (Jalali date), and Supervisor-only include_deleted.
Pagination is page/page_size; sorts are device_number (default), owner_name,
created_at, status, optionally prefixed with minus. Detail includes current branch
and city, open work, latest completed visit, and latest transaction period end.

GET `/api/v1/pos/devices/export` uses the same scope/filters, produces English
headers, preserves account/terminal/branch identifiers as text, neutralizes
formula-like text, and rejects more than 50,000 rows. It has no pagination limit
that could silently truncate the filtered selection.

## Activity and live performance

GET/POST `/api/v1/pos/devices/{id}/transactions` reads/adds period summaries;
PATCH/DELETE `/api/v1/pos/transactions/{id}` corrects or soft-deletes them.
Writes are Supervisor-only; managers read their current branch's terminals.
Required values are from_date, to_date (Jalali YYYY/MM/DD), transaction_amount
(nonnegative decimal rials, up to two decimal places), and transaction_count
(nonnegative integer). Inclusive periods are at most 366 days and cannot overlap
another live summary. An exact-period import corrects amount/count and audits the
old values; manual duplicate creation returns overlapping_period.

GET `/pos/productivity` ranks terminals, and GET
`/pos/devices/{id}/productivity` includes the counted series. Both accept either
jalali_year/jalali_month or from_date/to_date, at most 24 Jalali months; the default
is the last complete Jalali month. Only summaries wholly inside the requested
range count. The calculation is the total for that range, not an average.
Partial coverage is visible through record_count and covered_days. With no
counted record, totals/performance are null and no_data=true. An observed zero
is not missing data.

Initial classification: below 200,000,000 rials is low; 200,000,000 through
1,000,000,000 inclusive is normal; above 1,000,000,000 is high. Transaction count
does not affect classification. GET `/pos/performance-settings` reads the policy;
Supervisor-only PATCH replaces lower_threshold and upper_threshold atomically,
requiring 0 <= lower < upper and incrementing policy_version. Amounts in JSON
are decimal strings. Later queries use the current global policy across branches.

Rank filters are performance, no_data, branch_id, city_id, status. Sorts are
transaction_amount (default), productivity (amount alias), transaction_count,
device_number, optionally descending with minus. Missing amounts sort last.
Managers cannot request another branch. Every response names the period, unit
rials, method period_total_amount, thresholds/version, and last period end.

## XLSX imports

English headers are the canonical contract for templates and new files:

| File | Required headers |
| --- | --- |
| Devices | device_number, branch_code, owner_name, address |
| Transactions | device_number, transaction_amount, transaction_count |
| Combined | Both sets above |

Registry optional headers: owner_mobile, owner_national_code, shop_name,
account_number, contact_phone, status. Activity periods are supplied either as
multipart jalali_year/jalali_month together or row from_date/to_date columns.
For year 1405, month 7, the derived range is 1405/07/01–1405/07/30; conflicting
row dates fail. Real Excel date cells are accepted as dates; textual dates use
the Jalali API contract. Amounts support separators/Persian digits, counts must
be whole nonnegative integers, and account/branch/terminal numbers remain text.

Existing sample aliases are recognized: pos_code, sum_of_trans, counts_of_trans,
نام مشتری, شماره همراه, شماره تماس, شماره حساب, آدرس. نام شعبه is informational;
branch_code is authoritative. طبقه بندی پایانه and external classification aliases
are ignored. Duplicate aliases for one field fail the whole file. Other unknown
columns are reported as warnings. The sample mobile placeholders are not valid
production numbers; tests use synthetic valid mobiles with the same headers.

Supervisor-only routes under `/api/v1/pos/imports`:

- POST `/devices`, `/transactions`, `/combined`: multipart file plus optional
  period fields. Device mode is create_only; transaction mode upsert; combined
  applies both. Omit mode or send that fixed value; registry upsert is rejected.
- GET `/templates/devices`, `/templates/transactions`, `/templates/combined`:
  download English-header XLSX templates with synthetic example rows.
- GET the imports root: paginated logs, filters import_type, status, user_id,
  from_date/to_date. GET `/{id}` includes counters and first 20 errors.
- GET `/{id}/errors`: paginated JSON row errors, or format=xlsx for original
  row values plus row number/error information. GET `/{id}/file` returns the
  exact saved original and audits the download.

Existing live registry keys skip without overwriting owner, branch, or contact
details. Deleted-only matches are errors and require restore first. New rows
need an active existing branch; imports never create branches. Duplicate keys
later in a file fail. Invalid optional nonempty mobile/national code fails a
new-terminal row; blank optional fields are allowed.

Activity matches terminal plus exact inclusive period: create a new period,
update amount/count when changed, or report unchanged. Different overlapping
periods fail. Unknown terminals fail transaction-only import. In combined mode,
a skipped existing terminal can still receive new/corrected activity; a failed
activity rolls back a newly created terminal/history from that row. A source
branch differing from an existing terminal produces a warning and no transfer.

Each nonempty row contributes one row outcome. Response fields are total_rows,
created, updated, unchanged, skipped, failed, success_count, component_counts,
warnings, errors_preview, errors_url, file_url, and duplicate_of. For combined
files, separate registry_created/registry_skipped and
activity_created/activity_updated/activity_unchanged counters explain components;
the top-level outcome follows activity. Valid skipped/unchanged rows are successes.
All-valid input completes; mixed outcomes complete_with_errors; no accepted rows
with failures gives failed. Repeating a checksum is a hint, not a blocker.

Parsing/header/size validation precedes business changes. A durable processing
log and exact original are saved before the file transaction. Row savepoints
preserve valid rows; unexpected failure rolls the file transaction back and
records failed status with zero successes. After a crash, stop/check import
workers and inspect stale work with:

```sh
uv run python -m app.cli fail-stale-pos-imports --older-than-minutes 60
```

It is a dry run and lists stale unlocked logs plus orphan file names. After
confirming no importer is active, add `--apply --confirm-no-active-imports` to
mark interrupted work failed. Live row locks are skipped. Originals and orphan
files are never deleted by recovery. Use this command on the intended environment
only, with its environment variables loaded. Reupload corrected files to retry.

## Follow-up dispatch and employee visits

The Supervisor selects terminals and a performance period, then POSTs
`/api/v1/pos/visits/dispatch` with pos_device_ids (up to 200), period fields, and
optional instructions. The response is one created/error result per terminal.
Each eligible terminal routes to its current active branch in pending_assignment;
low, normal, high, and no-data terminals can all be selected. Retired/deleted
terminals are rejected. A second pending/assigned work item is a conflict.
POST `/pos/visits` cannot directly create employee work and returns forbidden.

Each visit stores server-calculated selection_snapshot: from_date, to_date,
amount, count, no_data, performance, lower_threshold, upper_threshold,
policy_version, unit, method. Null totals distinguish no data from observed zero.
This evidence stays immutable after imports, policy edits, transfer, assignment,
or completion corrections; a live productivity query uses the latest data.

Managers use GET `/pos/visits?status=pending_assignment` for their branch queue.
Only that branch's manager can POST `/{id}/assign` with assigned_to, optional
due_date (not past), and instructions. Supervisor cannot bypass this step.
POST `/pos/visits/bulk-assign` takes visit_ids (pending work, up to 200) and the
same assignment fields; one bad item does not block others. A branch without a
manager retains pending work until an eligible manager is appointed.

POST `/{id}/reassign` changes the same-branch eligible employee. POST
`/{id}/cancel` takes cancel_reason and is available to Supervisor/owning manager.
Transfer automatically cancels pending/assigned work with device_transferred,
retaining original branch and evidence. Completed/cancelled are archived and
reject further assignment/cancel/complete. An inactive branch blocks new
dispatch/assignment but its existing assignees can complete work.

Only the assignee can POST `/{id}/complete` with result (visited,
owner_unavailable, shop_closed, device_not_found), tag_codes, description, and
optional visited_at. Time cannot precede assignment or be future. Tags must be
unique active codes. Seed tags are broken_device, new_service_requested,
maintenance_required; tags never change operational terminal status. Supervisor
can PATCH a completed visit's result/tag_codes/description with audit; the
original evidence/time remain protected. Tag-link corrections deactivate links
and retain history rather than physically deleting them.

GET `/pos/visits` and `/{id}` are scoped to all for Supervisor, own branch for
manager, own assignee identity for employee (including historical visits after
a permitted branch move). Employee lists default to assigned, due date ascending
with nulls last. Filters: status, archived, assigned_to, branch_id, pos_device_id,
result, tag, overdue, assigned_from/assigned_to_date, completed_from/completed_to,
due_from/due_to. Other roles default to newest selected_at. Sort fields are
selected_at, assigned_at, completed_at, due_date. Pending branch work never
appears in employee lists/counts. Detail contains terminal contacts/address,
instructions, branch, snapshot, and latest completed visit tags.

GET `/pos/tags` is available to all roles (active by default); only Supervisor
can include_inactive, POST a tag, or PATCH its name/is_active. Historical links
remain after tag deactivation. Assigned visits block employee deactivation,
deletion, role/branch changes with user_has_open_tasks and task_count; reassign
or cancel first. Pending work without an assignee does not block employee changes.

In-app events commit with their business action: dispatch notifies the current
branch manager when present, assignment the employee, reassignment old/new
employees, cancellation the assignee (or manager for pending work), and
completion the assigning manager. There is no external notification delivery.
GET `/api/v1/notifications`, `/unread-count`, and `/{id}` expose only the current
recipient. POST `/{id}/read` and `/read-all` are idempotent; read_at retains its
initial time. Old notification links still enforce the current visit scope.

## Summary reports

GET `/api/v1/pos/reports/summary` returns assigned, overdue, completed_in_30_days,
visits_by_result, tag_counts, and the inclusive local-date window. Supervisor and
manager responses additionally contain pending_assignment, devices_by_status,
and devices_no_transactions_in_last_3_months with the exact recency range.
Only Supervisor sees devices_per_branch. Optional branch_id is Supervisor-wide
or must match the current manager/employee branch; mismatches return forbidden.

The completion window is today and the previous 29 business-timezone calendar
dates. Recency means a non-deleted transaction period ending within the last
three complete Jalali months; an explicit zero summary is still data. Deleted
terminals do not count in the current registry. Visit statistics use the original
task branch and assignee, retaining history after terminal transfer. Employee
responses contain only that employee's visit statistics, with no branch queue or
registry totals. Cancelled tasks never count as completed.
