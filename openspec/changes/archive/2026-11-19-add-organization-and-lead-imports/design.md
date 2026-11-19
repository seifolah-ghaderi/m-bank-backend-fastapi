# Design

## Context

The organization API stores cities by normalized name and branches by globally unique live `Code`. POS import resolves that code directly. The lead model currently requires both a city and a branch. Campaign selection joins leads to active branches, and sale conversion uses the lead's assigned branch. See [proposal.md](proposal.md) and the [delta specs](specs).

## Goals / Non-Goals

- Reuse the existing city, branch, and lead records. Keep POS imports and existing manual entry contracts compatible.
- Make branch assignment an explicit step between lead import and campaign selection.
- Reuse XLSX and private storage conventions. Keep any long-running lead work durable across API and worker restarts.
- Keep branch transfers, updates to existing imported data, campaigns already in progress, and retention operations outside this import workflow.

## Decisions

### Workbook profiles

| Profile | Required columns | Sample aliases and optional values |
| --- | --- | --- |
| Cities and branches | `branch_code`, `branch_name`, `city` | These are the headers in `branch_and_cities.xlsx`. Use the existing city name and branch code validation. |
| Leads | `city`, `first_name`, `last_name`, `mobile` | `شهرستان`, `نام`, `نام خانوادگی`, and `تلفن` or `شماره همراه` map to the required fields. `آدرس` maps to address. Preserve `نام فروشگاه` and `فعالیت` as labeled source details. Optional canonical fields include `national_code`, `occupation`, `address`, `referrer`, and `additional_info`. |

Read row 1 of the first visible sheet and ignore trailing blank sheets. Normalize Persian and English headers with the existing text utilities. Reject duplicate aliases for one field. Treat `کد` and any lead-file branch code as ignored columns and report that in the import summary. A canonical occupation name resolves only to an active existing occupation. An unmatched optional occupation stays unset and is reported as a warning. Preserve optional source details within existing validation bounds.

Use the existing Iranian mobile rules for text and safe whole-number Excel cells, including supported representations that lost a local leading zero. A landline or invalid value is a row error. Preserve explicit zero padding in identifier columns and reject ambiguous Excel representations such as fractional identifiers or numeric identifiers beyond Excel's exact decimal precision. Share the branch-code normalization path with POS where needed. Match using the resulting string code and retain the current API's alphanumeric codes and exact code identity.

### City and branch processing

Process the organization workbook in two passes. Resolve normalized city names to non-deleted active cities and create each missing valid city once. Finish this city pass before writing branch rows. A valid city can be retained if its branch row later fails. Branch writes reuse normal organization validation and audit behavior and store the resolved city UUID. Treat an identical live branch as unchanged. Record conflicts for a different city or name on the same code, a different code on the same city and name, inactive matches, and duplicate branch codes later in the same workbook. Do not overwrite or reactivate conflicts. Keep both row outcomes and city component counts so a city shared by multiple rows is counted once.

### Lead processing and first assignment

Resolve `city` by normalized name to an active existing city UUID. Unknown cities are row errors and can be corrected by importing the directory or correcting the workbook before retrying. Create a lead with a null branch. Match repeats using normalized mobile and optional validated national code, checking both for inconsistent identity. Use create-only semantics and keep prior lead fields, customer links, archival status, and branch. Flag a conflicting city. A supplied national code can match an existing lead whose mobile agrees. A supplied national code missing from a mobile match does not fill it. Reject repeated normalized mobile or national code later in a workbook. Apply existing database uniqueness on concurrent inserts and classify a race as unchanged or an identity conflict using the same rules.

Keep `POST /api/v1/leads` requiring a branch. Extend the Supervisor registry with `unassigned=true` and add `POST /api/v1/leads/{id}/assign-branch` with a branch UUID. The Supervisor chooses an active branch, and the lead retains its own city. An assignment to the same existing branch can be retried safely. A different branch or a request to clear it is rejected. Lock and recheck the lead and destination within the assignment transaction. Keep campaign membership branch IDs required and guard all selection paths, including preview and explicit IDs. Preserve activation checks and existing customer and sale branch assumptions.

### API and durable processing

Use `/api/v1/imports/organization` and `/api/v1/imports/leads` for Supervisor uploads, and the shared CRM history under `/api/v1/imports` for list, detail, errors, and original-file downloads. Serve templates at `/api/v1/imports/templates/{type}`. Keep POS import routes and their history responses compatible. Reuse safe workbook parsing, private storage, audit, and reporting where the contracts match. Scope CRM histories and artifacts to the CRM import types and Supervisor access.

Use existing bounded synchronous import settings for organization uploads. For leads, use a persistent PostgreSQL-backed queue and a separately runnable worker that processes bounded chunks and commits outcomes with the accepted data. Start with the v3 draft limits of 50 MB and 100,000 data rows, process in chunks of 500, and align the deployment request-body limit for the lead upload path. Preflight workbook structure and row limits before business writes. Store each row outcome by import ID and row number. Reclaim interrupted work safely and resume without repeating committed rows. Record aggregate counts, stable errors and warnings, and intermediate progress. Retain the source workbook in private storage, audit original downloads, and emit formula-like values as literal text in generated reports.

## Risks / Trade-offs

- Sheet telephone samples are unsuitable for successful lead creation. Use synthetic valid mobiles with the sample headers for the success path and cover invalid telephone values as errors. Keep actual contact values out of general logs and test fixtures.
- An interrupted organization import can leave valid cities already persisted. Report city and branch outcomes separately and allow an idempotent re-upload.
- A numeric Excel cell with no explicit padding cannot reveal a lost leading zero. Keep exact stored code matching and document text-formatted identifiers for padded codes.
- A nullable lead branch affects registry consumers. Roll out compatible clients that can display unassigned rows, and keep campaign membership, POS, and verified customer branch fields required.

## Migration Plan

Add CRM import job and outcome storage or extend shared import records with compatible type and status constraints. Make the lead branch foreign key nullable while keeping existing values and references. Verify fresh and prior-head upgrades. If imports have created unassigned leads, a rollback to a schema requiring branches needs those leads to receive an explicit branch first or requires restoring the predeployment snapshot.
