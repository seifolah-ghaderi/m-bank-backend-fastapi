# pos-reports Specification

## Purpose

Provide branch-scoped operational summaries of terminal coverage and POS follow-up workload without exposing other staff or branches.

## Requirements

### Requirement: Supervisor and manager summary
The POS summary SHALL return terminal counts by operational status, pending-assignment and assigned counts, overdue assigned work, visits completed in the last 30 business dates, results/tag counts for that interval, and terminals with no transaction period ending in the last three complete Jalali months. Supervisors SHALL also receive counts per branch; managers SHALL receive only their own branch's aggregates.

#### Scenario: Pending branch workload
- **WHEN** a branch receives dispatches that have not been assigned
- **THEN** its manager sees those in pending-assignment counts separately from employee-assigned work.

#### Scenario: Cross-branch report filter
- **WHEN** a manager supplies a different branch filter
- **THEN** the request returns 403 without disclosing another branch's aggregates.

### Requirement: Employee summary isolation
Employee summaries SHALL contain only their own assigned, overdue, completed, and result/tag visit statistics. They SHALL NOT expose registry totals, other employee workloads, pending branch work, or other branches' data. Cancelled work SHALL NOT count as completed and soft-deleted terminals SHALL be excluded from current registry counts.

#### Scenario: Employee requests summary
- **WHEN** an employee requests POS summary data
- **THEN** all returned metrics are scoped to that employee's visits and contain no branch-wide registry totals.
