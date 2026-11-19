# Tasks

## 1. Import foundation

- [x] 1.1 Add CRM import records, private file storage, row outcome persistence, and Supervisor history, detail, original-file and error-report endpoints. Verify scope, audited downloads, safe XLSX cell output, and counts with API tests.
- [x] 1.2 Add workbook header and file preflight, both template downloads, and upload contract documentation. Test English and Persian headers, duplicate aliases, empty sheets, size limits, and malformed workbooks with synthetic fixtures.

## 2. Cities and branches

- [x] 2.1 Implement the organization city pass and branch pass using existing normalized names, branch Code, organization constraints, and audit behavior. Verify unique city creation, correct city UUIDs, existing-record reuse, partial success, and duplicate, inactive, and conflicting rows.
- [x] 2.2 Document the organization workbook profile and identifier formatting. Verify that a branch imported from a numeric or explicitly padded code is found by a POS registry upload, and run existing POS import regression tests.

## 3. Lead imports

- [x] 3.1 Make the lead branch foreign key and registry output nullable for imported leads while preserving required branch validation for manual creation. Verify migration from the prior head, existing assigned lead reads, and manual-create validation.
- [x] 3.2 Implement city lookup, mobile validation, Persian sample alias mapping, ignored code reporting, and create-only identity matching. Verify unknown and inactive city errors, valid mobile normalization, invalid telephone errors, optional fields, repeat imports, and identity conflicts within and across files.
- [x] 3.3 Implement the durable lead queue, worker, resumable chunk outcomes, and route-specific upload bounds. Document worker and proxy setup. Verify 202 responses, polling, partial errors, and interruption/retry with no duplicated committed rows.
- [x] 3.4 Document the lead workbook format and operational order after organization import. Verify a fixture built from the sample headers with synthetic valid mobiles creates city-linked unassigned leads.

## 4. Branch assignment and campaign eligibility

- [x] 4.1 Add Supervisor unassigned filtering and audited first branch assignment. Document the nullable field and assignment action. Verify inactive branches, archived leads, city preservation, same-branch retries, conflicting assignments, and unauthorized roles.
- [x] 4.2 Verify that preview, filter selection, and explicit ID selection exclude unassigned leads. Test eligibility after assignment, activation revalidation, and existing branch scope.

## 5. Functional integration verification

Performance and smoke tests are outside the acceptance scope.

- [x] 5.1 Run a functional PostgreSQL API regression test from city and branch import through POS branch lookup and from lead upload through manual assignment and campaign activation. Include mixed valid and invalid rows.
- [x] 5.2 Apply migrations on fresh and prior-head PostgreSQL databases, run the project tests and Ruff checks, and validate the completed OpenSpec change.
