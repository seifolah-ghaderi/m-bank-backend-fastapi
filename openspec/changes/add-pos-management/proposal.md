# Proposal

## Why

The core backend is complete, but staff cannot yet register POS terminals, import their monthly activity, or organize visits. The bank needs a traceable flow from transaction-based selection by a Supervisor to branch assignment and employee visit results.

## What Changes

- Add the terminal registry, branch/owner history, manual maintenance, soft deletion/restore, and scoped Excel export.
- Add logged spreadsheet imports for registry, transactions, and combined files. Registry rows create new terminals and skip existing ones; matching transaction periods update amount/count with audit. Ignore external performance classifications completely.
- Accept sample header aliases, preserve identifier leading zeros, normalize Iranian mobile variants, and accept an upload-level Jalali month when dates are absent.
- Calculate low/normal/high performance on query from total transaction amounts in rials, using Supervisor-managed global thresholds of 200 million and 1 billion. Distinguish no data from recorded zero.
- Add Supervisor dispatch to owning branches, manager-only employee assignment from that queue, visit execution/tags/archive, and immutable selection snapshots.
- Add in-app notifications, role-scoped POS reports, and POS-dependent user/branch lifecycle guards.
- Reconcile the Phase 1 architecture and POS contracts with these approved decisions. Keep Phase 2 lead/customer conversion separate.

## Capabilities

### New Capabilities

- `pos-registry`: Terminal identity, maintenance, branch/owner history, visibility, and export.
- `pos-imports`: Logged, recoverable registry/transaction imports, templates, aliases, and error reports.
- `pos-transactions`: Period amount/count records, corrections, overlap protection, and history.
- `pos-performance`: Query-time classification, global thresholds, ranking, and missing-data semantics.
- `pos-visits`: Supervisor dispatch, branch queue, employee assignment, immutable selection evidence, and visit lifecycle.
- `notifications`: Recipient-scoped in-app events and read state.
- `pos-reports`: Role-scoped terminal and visit summary statistics.

### Modified Capabilities

- `api-foundation`: Explicitly normalize local mobile numbers without a leading zero and international prefixes retaining the local zero.
- `organization-management`: Add device counts and block deletion of branches containing terminals.
- `user-management`: Protect employees with assigned POS work from incompatible lifecycle changes.
- `audit-trail`: Audit POS writes/settings/import downloads and extend database preservation to POS business history.

## Impact

Extend `app/features/pos`, `notifications`, and `reports`, shared Excel/date/audit helpers, models/schemas, organization/user guards, and reviewed Alembic migrations. Add openpyxl and multipart upload support; retain FastAPI, PostgreSQL 16, uv, synchronous bounded POS imports, and the existing web/Jalali API conventions. New APIs live under `/api/v1/pos` and `/api/v1/notifications`. No UI, Core Banking integration, Phase 2 customer creation, background job platform, or external notification channels are included. Main OpenSpec specs remain unchanged until sync/archive.
