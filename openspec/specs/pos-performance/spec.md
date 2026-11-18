# pos-performance Specification

## Purpose

Classify terminal performance consistently from period transaction amounts while allowing administrators to change shared thresholds.

## Requirements

### Requirement: Global rial thresholds
There SHALL be one system-wide pair of performance thresholds, editable only by Supervisors and initially 200,000,000 and 1,000,000,000 rials. Valid thresholds SHALL be nonnegative exact decimals with lower strictly below upper. Updates SHALL be atomic, audited, and take effect on subsequent queries without changing existing selection snapshots.

#### Scenario: Change policy
- **WHEN** a Supervisor saves a valid new threshold pair
- **THEN** all branches' subsequent queries use that pair and historical dispatch snapshots retain their original pair.

#### Scenario: Invalid policy or unauthorized edit
- **WHEN** a manager edits thresholds or a Supervisor supplies lower greater than or equal to upper
- **THEN** the request fails with 403 or 422 respectively and the saved pair stays unchanged.

### Requirement: Query-time amount classification
Performance SHALL be calculated on query from the sum of live transaction amounts wholly inside the selected inclusive date range. An amount below lower SHALL be `low`, from lower through upper inclusive SHALL be `normal`, and above upper SHALL be `high`. Counts SHALL be returned but SHALL NOT affect classification. Terminal rows SHALL NOT store derived performance or use imported labels.

#### Scenario: Exact thresholds
- **WHEN** the selected range totals 199,999,999, 200,000,000, 1,000,000,000, or 1,000,000,001 rials under the initial policy
- **THEN** classifications are low, normal, normal, and high respectively.

#### Scenario: Partial overlap
- **WHEN** a stored summary only partially overlaps the selected range
- **THEN** that summary is excluded instead of prorated.

### Requirement: No-data distinction
A terminal with no counted summary SHALL return `no_data=true`, null totals, and null classification. An observed summary of zero SHALL return zero totals, `no_data=false`, and low classification under the initial policy. Supervisors SHALL be able to select no-data terminals for follow-up.

#### Scenario: No history versus no activity
- **WHEN** one terminal has no summary and another has a zero summary in the selected range
- **THEN** only the first is no-data and the second is classified from its observed zero.

### Requirement: Scoped performance queries
Supervisors and branch managers SHALL query per-terminal series and paginated rankings within their scope. Queries SHALL accept Jalali month or explicit range, default to the last complete Jalali month, and allow at most 24 Jalali calendar months. Responses SHALL identify amount unit, method `period_total_amount`, applied thresholds, range, totals, and latest period end.

#### Scenario: Low and missing-data selection list
- **WHEN** a Supervisor filters rankings by low performance or no data and optionally branch/city/status
- **THEN** eligible matching terminals appear with deterministic amount/device ordering and branch identity for dispatch.

#### Scenario: Range aggregate
- **WHEN** a query spans several complete Jalali months
- **THEN** the threshold applies to the sum for that selected range and the response names that range explicitly.

#### Scenario: Manager scope
- **WHEN** a manager supplies another branch's filter
- **THEN** the response is 403; an inaccessible terminal ID returns 404.
