## ADDED Requirements

### Requirement: Assigned POS work lifecycle guard
Deactivating, soft-deleting, moving branches, or changing the role of an employee with assigned POS visits SHALL fail with 409 `user_has_open_tasks`, including the task count. Work SHALL be reassigned or cancelled first. Pending branch work with no assignee and completed/cancelled visits SHALL NOT block employee changes. Concurrent assignment and user changes SHALL preserve assignee eligibility.

#### Scenario: Employee has assigned visit
- **WHEN** a Supervisor attempts to move or deactivate an employee with an assigned POS visit
- **THEN** the action returns `user_has_open_tasks` with its count and neither user nor visit changes.

#### Scenario: Only archived work
- **WHEN** an employee has only completed/cancelled visits and a lifecycle change otherwise passes existing guards
- **THEN** it succeeds and historical employee references remain intact.

#### Scenario: Assignment race
- **WHEN** a manager assigns work concurrently with that employee's deactivation or branch move
- **THEN** either assignment prevents the incompatible user change or the changed employee is rejected as an assignee; no invalid assigned work remains.
