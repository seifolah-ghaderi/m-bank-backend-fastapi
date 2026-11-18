# pos-registry Specification

## Purpose

Maintain POS terminal identity, current ownership and branch membership with recoverable history and role-scoped access.

## Requirements

### Requirement: Terminal registration and identity
Only Supervisors SHALL create terminals manually. Each terminal SHALL have a normalized live-unique device number, owner name, address, eligible branch, source, and operational status. Device numbers SHALL be trimmed uppercase text of 3–50 letters, digits, hyphens or underscores, with Persian/Arabic digits normalized and leading zeros preserved.

#### Scenario: Import business key alias
- **WHEN** a terminal is identified using spreadsheet column `pos_code`
- **THEN** that value identifies the same business key exposed as `device_number`.

#### Scenario: Duplicate identity
- **WHEN** concurrent creations use the same normalized non-deleted device number
- **THEN** at most one succeeds and the other returns 409 `device_number_in_use`.

### Requirement: Owner and contact details
Terminals SHALL require an owner name of 2–200 characters and address of 5–1000 characters. Optional fields SHALL include normalized owner mobile, validated national code, shop name, account number, and contact phone. Account numbers SHALL remain text without numeric conversion or customer creation.

#### Scenario: Optional mobile validation
- **WHEN** a non-empty owner mobile cannot normalize to a valid Iranian mobile
- **THEN** manual entry returns field validation errors and an import reports a row error.

#### Scenario: Independent terminal owner
- **WHEN** a terminal with an owner and bank account is created
- **THEN** no lead, verified customer, or customer product is created.

### Requirement: Operational status
Terminal status SHALL be one of `active`, `inactive`, `under_maintenance`, or `retired`, independently of calculated performance. Retired terminals SHALL accept late transaction data but reject new follow-up dispatch. Visit tags SHALL NOT change operational status automatically.

#### Scenario: Low performance is not deactivation
- **WHEN** an active terminal has zero transactions for a queried period
- **THEN** its calculated performance is low and its operational status remains active.

### Requirement: Scoped terminal retrieval and export
Supervisors SHALL list, view, search, and export all terminals; managers SHALL do so only for their own branch. Employees SHALL access terminal details only through their assigned visits. Lists SHALL support branch, city, status, source, open-work, and transaction-recency filters with standard pagination. Export SHALL use the same scope and filters and allow at most 50,000 rows.

#### Scenario: Foreign terminal
- **WHEN** a manager requests another branch's terminal
- **THEN** the response is 404 and no detail or export data is disclosed.

#### Scenario: Employee registry request
- **WHEN** an employee requests the terminal registry or export
- **THEN** the response is 403.

### Requirement: Historical branch and ownership changes
Supervisors SHALL transfer terminals to active branches and record owner handovers with non-future effective dates no earlier than the current history start. Changes SHALL preserve prior history and audit. A transfer SHALL cancel pending or assigned follow-up work atomically, retaining its original branch and snapshot. Corrections SHALL update current details and be audited.

#### Scenario: Transfer with open work
- **WHEN** a terminal with pending or assigned work is transferred
- **THEN** that work is cancelled with reason `device_transferred`, its branch/snapshot stay unchanged, and a new branch history begins.

#### Scenario: Same-day handover
- **WHEN** a second handover occurs on the current history start date
- **THEN** no negative or overlapping date range is written and the superseded state remains recoverable in audit.

### Requirement: Soft deletion and restore
Only Supervisors SHALL soft-delete and restore terminals. Deletion SHALL reject pending or assigned work with 409 `device_has_open_visit`. Restore SHALL reject a number already held by another live terminal. Transactions, visits, and histories SHALL survive deletion, while normal lists exclude deleted terminals.

#### Scenario: Historical preservation
- **WHEN** an eligible terminal is soft-deleted and later restored
- **THEN** its existing transaction and visit history remains attached to the same terminal identity.
