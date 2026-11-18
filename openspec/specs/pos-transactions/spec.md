# pos-transactions Specification

## Purpose

Preserve terminal transaction totals and counts for explicit periods, supporting audited corrections and consistent performance queries.

## Requirements

### Requirement: Period transaction values
Every transaction summary SHALL identify a non-deleted terminal and inclusive native-date period with amount in rials and an integer transaction count. Amount SHALL be nonnegative with at most two fractional digits; count SHALL be nonnegative and fit a signed 64-bit integer. Periods SHALL be ordered and at most 366 inclusive days. Retired terminals SHALL accept late records.

#### Scenario: Amount and count validation
- **WHEN** a row supplies a negative amount, fractional count, or missing count
- **THEN** it is rejected with a field-level validation error rather than substituting zero.

#### Scenario: Zero activity
- **WHEN** a valid period has amount zero and count zero
- **THEN** it is stored as an observed zero-activity period rather than missing data.

### Requirement: Idempotent correction and non-overlap
Imports SHALL match on terminal plus exact period. A differing amount or count SHALL update that record and audit old/new values; identical values SHALL be unchanged. Any different overlapping live period SHALL be rejected with `overlapping_period`, including under concurrent imports or manual writes. Later duplicates of the same terminal/period within a file SHALL be row errors.

#### Scenario: Correct count only
- **WHEN** reimporting the same terminal/period with unchanged amount and a corrected count
- **THEN** the existing summary is updated once and the previous count is retained in audit.

#### Scenario: Concurrent overlapping periods
- **WHEN** two requests write different overlapping periods for one terminal
- **THEN** at most one succeeds and the other reports `overlapping_period` without leaking database details.

### Requirement: Manual maintenance and history
Only Supervisors SHALL create, edit amount/count/dates, or soft-delete summaries. Supervisors SHALL read all transaction history; managers SHALL read history only for terminals currently in their branch. History SHALL exclude deleted records, be paginated newest period first, and support Jalali date filters. Changing transactions SHALL NOT change terminal branch, owner, status, or saved follow-up snapshots.

#### Scenario: Correct after dispatch
- **WHEN** a Supervisor corrects a summary previously used for dispatch
- **THEN** subsequent performance queries use the correction and the dispatched snapshot remains unchanged.

#### Scenario: Employee history request
- **WHEN** an employee requests a terminal transaction-history endpoint
- **THEN** the request returns 403; assigned visit detail can still show its selection snapshot.
