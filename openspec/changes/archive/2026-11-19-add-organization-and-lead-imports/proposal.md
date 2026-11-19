# Proposal

## Why

Supervisors need to load the bank's city and branch directory before importing the leads they will use in campaigns. The supplied workbooks use city names to connect records, and the lead workbook leaves branch assignment to Supervisors.

## What Changes

- Import the city and branch workbook in two passes. Create or resolve cities first, then create branches under the resolved city IDs. Store each workbook `branch_code` as the existing branch `Code` used by POS imports.
- Import leads from XLSX using normalized city names and valid Iranian mobile numbers. Imported leads start without a branch. Supervisors assign a branch manually before those leads become eligible for campaign selection.
- Preserve incoming file provenance, provide import status and row-level error reports, and make repeat uploads safe. Document canonical columns and aliases for both sample workbooks.
- **BREAKING** for lead registry clients that assume every row has a branch UUID. Imported leads can return `branch_id: null`. Manual entry continues to require an active branch.

## Capabilities

### New Capabilities

- `crm-imports` covers Supervisor XLSX intake, import histories, status, original files, and row outcomes for organization and lead imports.

### Modified Capabilities

- `organization-management` gains city-first spreadsheet population and branch code compatibility with POS imports.
- `lead-management` gains city-linked lead import, identity matching, an unassigned lead filter, and manual first branch assignment.
- `marketing-campaigns` requires an assigned active branch at selection and rechecks it at activation.

## Impact

Adds Supervisor import and lead assignment APIs, import job processing, private workbook and error report storage, a nullable lead branch relationship, and migration and API tests. Builds on current organization lookups, XLSX utilities, and audit conventions. The source sheets are `docs/sample_data/branch_and_cities.xlsx` and `docs/sample_data/leads_import.xlsx`. The latter provides the header contract and needs valid synthetic mobile replacements for successful test rows.

Acceptance uses functional API and PostgreSQL integration tests, migration checks, lint, and OpenSpec validation. Performance and smoke tests are outside the acceptance scope.

## Follow-up backlog

- Protect open campaign work during employee departure, transfer, and role changes. Specify audited recovery for draft and rejected sales while retaining the original author and score attribution.
- Publish, reassign, execute, and archive retention tasks. Specify task notifications and retention-visit sales after the task workflow exists.
- Add campaign-start notifications and scoped campaign, branch, employee, product sales, and retention reports. Build the derived lead pipeline and specify marketing and retention league rules.
- Decide whether to support direct customer sales, late campaign sales, and approved-sale reversals. Define permissions, attribution, and any compensating score and product history.
- Consider bulk stale-lead archival, web and mobile clients, mobile push, and production SMS provider verification in their own workstreams.
