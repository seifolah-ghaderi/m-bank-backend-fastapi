# CRM spreadsheet imports

Use the following Supervisor-only XLSX templates under `/api/v1/imports`.

- `GET /templates/organization` for cities and branches.
- `GET /templates/leads` for leads.

Upload a multipart `file` to `POST /organization` or `POST /leads`. Put the
headers on row 1 of the first visible sheet. Blank data rows and other sheets
are skipped. Duplicate headers that resolve to the same field, missing required
headers, unreadable workbooks, or files over the applicable limits are rejected.
Unknown named columns are reported as warnings.

`GET /imports` in the API v1 namespace lists CRM imports. Each entry includes
its current status and counts. Under `/api/v1/imports/{id}`, use GET for detail,
`GET /errors` for row numbers and error codes, `GET /errors?format=xlsx` for
a spreadsheet of errors, and `GET /file` for the original workbook. Access is
limited to Supervisors. Original-file downloads are audited.

## Cities and branches

Upload `branch_and_cities.xlsx` with columns `branch_code`, `branch_name`,
and `city`. The organization upload processes synchronously. It resolves or
creates distinct cities first, then creates valid branches with their city IDs.
The result counts branch rows and reports distinct city outcomes separately.
A valid city can be created even if its branch row fails. An identical existing
branch is unchanged. Conflicting or inactive records require correction before
retrying.

The workbook code becomes the existing branch `Code` used by POS. Supply the
same code in later POS uploads. Use text for identifiers that start with zero.
Explicit Excel zero-padding is also supported. A plain numeric cell cannot
recover leading zeroes that were lost before upload. The organization upload
uses the existing `IMPORT_MAX_MB` and `IMPORT_MAX_ROWS` limits.

## Leads

Import the city directory first. Each row must have `city`, `first_name`,
`last_name`, and a valid Iranian `mobile`. The sample headers `شهرستان`,
`نام`, `نام خانوادگی`, and `تلفن` map to those columns. `شماره همراه` is
another mobile alias. Landline-only rows fail mobile validation. Format
identifiers as text to retain leading zeroes. Numeric mobiles that lost the
local zero are accepted when they normalize to a valid mobile.

Optional columns are `national_code`, `occupation`, `address`, `referrer`,
and `additional_info`. `آدرس` maps to address. `نام فروشگاه` and `فعالیت`
are retained in the lead's additional information. A canonical occupation
name that cannot be resolved is reported as a warning. `کد` and a workbook
branch code are ignored. An unknown or inactive city is a row error.
Matching existing leads are unchanged. The import reports conflicting or
repeated identities and preserves existing assignments and customer links.

A valid upload returns HTTP 202 with an import ID. Poll
`GET /api/v1/imports/{id}` for status and committed progress. Lead uploads
allow up to 50 MiB and 100,000 nonempty rows. The Nginx deployment allows a
52 MiB request body only on the lead upload path to accommodate multipart
overhead.

`docker compose up --build -d` starts the `lead-worker` service with automatic
restarts, the API's runtime database account, and the same import volume. Apply
the database migrations as part of deployment. For a local Python environment,
run `uv run python -m app.cli process-lead-imports` with the same `DATABASE_URL`
and `IMPORT_STORAGE_DIR` as the API. Add `--once` to attempt at most one ready job.

The worker resumes from the last committed 500-row chunk after an interruption.
After processing errors, it retries after 5 and 30 seconds and can process
other jobs in the meantime. After a third processing error it reports `failed`
with `error_code: processing_error` and retains committed leads and their row
outcomes. The status response includes `retry_count` and `next_attempt_at`.
Use the `lead-worker` logs to investigate failed or stalled jobs.

## Assign leads to branches

Imported leads return `branch_id: null` and are visible to Supervisors in
`GET /api/v1/leads?unassigned=true`. Use
`POST /api/v1/leads/{id}/assign-branch` with `{"branch_id":"<UUID>"}` to assign
an active branch. The assignment preserves the lead's imported city and is
audited. Repeating the same assignment is safe. A lead cannot be assigned
while archived or moved to a different branch through this action.

Campaign selection excludes unassigned leads. After assignment, eligible
leads can be added to a draft using the existing selection workflow. Manual
lead creation still requires a branch.
