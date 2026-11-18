# pos-imports Specification

## Purpose

Import terminal registry and period activity files with deterministic matching, durable provenance, and actionable row errors.

## Requirements

### Requirement: Bounded supervised upload
Only Supervisors SHALL upload registry, transaction, or combined `.xlsx` files. Uploads SHALL be limited to 10 MB and 5,000 nonempty data rows, read the first visible sheet with row 1 as headers, and process synchronously. Unsupported files, missing required headers, or ambiguous aliases SHALL fail before business rows are changed.

#### Scenario: Unsupported or excessive input
- **WHEN** a file has an invalid format, exceeds 10 MB, or exceeds 5,000 data rows
- **THEN** the API rejects it with `invalid_file`, `file_too_large`, or `too_many_rows` respectively.

### Requirement: Canonical columns and aliases
Imports SHALL normalize header case, whitespace, Persian variants, and underscores/spaces. They SHALL accept `pos_code` as `device_number`, `sum_of_trans` as `transaction_amount`, `counts_of_trans` as `transaction_count`, and the sample Persian owner, mobile, contact, account, and address headers. `branch_code` SHALL match an existing branch with leading zeros preserved.

#### Scenario: Sample-compatible registry
- **WHEN** headers contain `branch_code`, `pos_code`, `نام مشتری`, `شماره همراه`, `شماره تماس`, `شماره حساب`, and `آدرس`
- **THEN** those columns map to the canonical terminal fields; branch name is informational and cannot override branch-code matching.

#### Scenario: Ambiguous header mapping
- **WHEN** both `pos_code` and `device_number` map to the same field in one sheet
- **THEN** the file fails with `ambiguous_columns` instead of choosing one silently.

### Requirement: External classification exclusion
The `طبقه بندی پایانه` column and equivalent external performance-classification aliases SHALL be ignored. Their values SHALL NOT populate terminal attributes, performance calculations, or follow-up snapshots. The unchanged original file MAY retain the source column solely as import provenance.

#### Scenario: Conflicting external label
- **WHEN** a source row says valuable but its imported transaction amount is below the low threshold
- **THEN** query-time classification follows transactions and configured thresholds only.

### Requirement: Create-only terminal matching
Registry import SHALL create new device numbers, skip existing live terminals without changing details or branch, and reject soft-deleted matches with `device_deleted`. New terminals SHALL require an active branch, owner name, and address, and start branch/owner history on the business date. Duplicate normalized device numbers later in a file SHALL fail with `duplicate_in_file`.

#### Scenario: Existing terminal with changed source values
- **WHEN** a registry row matches an existing live terminal but supplies another branch or owner
- **THEN** the row is counted as skipped and no terminal, transfer, or owner-change mutation occurs.

#### Scenario: Invalid new-terminal row
- **WHEN** a new terminal has an unknown/inactive branch or invalid nonempty optional mobile
- **THEN** that row fails with a field error while other valid rows continue.

### Requirement: Upload-level monthly period
Transaction and combined uploads SHALL accept `jalali_year` and `jalali_month` together to derive the inclusive first/last days of that Jalali month. Without those parameters, each transaction row SHALL supply valid `from_date` and `to_date`. A row with explicit dates conflicting with an upload-level month SHALL fail with `period_mismatch`.

#### Scenario: Month without file dates
- **WHEN** year 1405 and month 7 accompany a transaction file without date columns
- **THEN** every valid transaction row uses `1405/07/01` through `1405/07/30`, stored as native dates.

#### Scenario: Invalid calendar month
- **WHEN** the supplied month is 13 or only one of year and month is supplied
- **THEN** the upload fails validation before importing any transaction.

### Requirement: Transaction and combined imports
Transaction rows SHALL require terminal code, nonnegative rial amount, and nonnegative integer count. Same terminal/period records SHALL be updated if either amount or count differs and unchanged otherwise. Combined imports SHALL create-or-skip registry data and import activity independently of an existing-terminal skip, but atomically within each row.

#### Scenario: Existing terminal in combined import
- **WHEN** a combined row matches a live terminal and contains a valid new activity period
- **THEN** registry data is skipped and the transaction is created with separate registry/activity counters.

#### Scenario: Invalid activity for newly created terminal
- **WHEN** a combined row would create a terminal but its transaction is invalid
- **THEN** neither the terminal nor its transaction/history persists for that row.

#### Scenario: Unknown transaction terminal
- **WHEN** a transaction-only row refers to a missing or deleted terminal
- **THEN** the row fails with `unknown_device` and creates no terminal.

### Requirement: Durable import outcomes
Each accepted upload SHALL preserve the original file, checksum, uploader, selected period, type, counters, times, and durable status. Valid rows SHALL persist despite other row failures. Responses SHALL include the first 20 errors, warnings, duplicate-file hints, and links to full JSON/XLSX errors and original download. All-skipped or unchanged valid files SHALL complete successfully.

#### Scenario: Partial success and retry
- **WHEN** some rows fail and others succeed
- **THEN** status is `completed_with_errors`, original row numbers/raw values are retained, and corrected failed rows can be reimported without duplicating valid data.

#### Scenario: Failed processing or restart
- **WHEN** processing crashes after an import log was created
- **THEN** its original file and processing trace remain available and an operator can mark stale processing failed through the documented recovery command.

### Requirement: Safe templates and generated files
The system SHALL provide XLSX registry, transaction, and combined templates and error reports. Original downloads SHALL be Supervisor-only and audited. Exports and error reports SHALL neutralize formula-like text, preserve identifier text, and never evaluate uploaded formulas or expose arbitrary filesystem paths.

#### Scenario: Formula-like source text
- **WHEN** an owner/address value begins with a spreadsheet formula marker
- **THEN** generated XLSX output represents it as harmless text rather than an executable formula.
