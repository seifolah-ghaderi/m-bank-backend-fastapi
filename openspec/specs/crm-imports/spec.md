# crm-imports Specification

## Purpose

Load organization and lead spreadsheets with traceable outcomes that Supervisors can review and correct.

## Requirements

### Requirement: Supervisor spreadsheet submission
Only Supervisors SHALL upload organization and lead XLSX files and download templates. The system SHALL validate workbook format, header mapping and configured limits before mutating business records. Lead uploads SHALL return 202 with a durable import ID and expose progress through the import detail.

#### Scenario: Conflicting column aliases
- **WHEN** a workbook contains two headers that map to one field
- **THEN** the system rejects the file before creating cities, branches or leads.

#### Scenario: Queued lead upload
- **WHEN** a Supervisor submits a valid lead workbook
- **THEN** the response contains the import ID and the Supervisor can poll until processing finishes.

#### Scenario: Unauthorized user
- **WHEN** a Branch Manager or Employee attempts to upload or inspect a CRM import
- **THEN** the request is forbidden and reveals no import data.

### Requirement: Import provenance and row outcomes
The system SHALL record workbook type, uploader, original file, timestamps, status and row outcomes. Supervisors SHALL be able to list imports, view counts and download the original file and a row error report. The system SHALL preserve accepted results when other rows fail and distinguish completed, completed with errors, and failed imports.

#### Scenario: Partially accepted workbook
- **WHEN** an upload contains valid rows and invalid rows
- **THEN** the valid rows are retained and the report identifies each rejected row by spreadsheet row number and error code.

#### Scenario: Interrupted lead import
- **WHEN** a lead import is interrupted and processing resumes
- **THEN** committed results remain visible and each spreadsheet row contributes only one final outcome.
