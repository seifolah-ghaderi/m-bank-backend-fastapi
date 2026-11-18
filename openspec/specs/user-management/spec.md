# user-management Specification

## Purpose

Allow Supervisors to administer staff accounts while preserving branch boundaries, account history, and administrative access.

## Requirements

### Requirement: User fields and role assignment
Users SHALL have normalized first and last names of 2–100 characters, a normalized unique mobile, optional unique validated national code, active state, and one of `supervisor`, `branch_manager`, or `employee`. Uniqueness SHALL apply to non-deleted users. Supervisors SHALL have no branch; other roles SHALL require an active, non-deleted branch for new assignments.

#### Scenario: Invalid role and branch combination
- **WHEN** a new Supervisor has a branch or a new Employee or Branch Manager lacks an eligible branch
- **THEN** the service returns 422 without creating the user.

#### Scenario: Manager conflict
- **WHEN** a user is created or promoted as manager of a branch already having a non-deleted manager
- **THEN** it returns 409 `branch_already_has_manager`, including under concurrent requests.

#### Scenario: Reuse deleted identity
- **WHEN** a new user uses the mobile or national code of a soft-deleted user
- **THEN** creation succeeds if all other rules hold and the historical user remains unchanged.

### Requirement: Supervisor account administration
Only Supervisors SHALL create or update users, activate, deactivate, reset passwords, or soft-delete them through the `/api/v1/users` APIs. Create and reset SHALL generate a ten-character temporary password satisfying password policy, return it once, and require a password change. Reset SHALL unlock the account and revoke all refresh tokens.

#### Scenario: Create staff account
- **WHEN** a Supervisor submits valid staff details
- **THEN** the response contains the temporary password once and the user has `must_change_password=true`.

#### Scenario: Reset password
- **WHEN** a Supervisor resets a locked user's password
- **THEN** lockout state resets, refresh tokens and pending SMS challenges are revoked, and the temporary password is returned once.

#### Scenario: Secret exposure prevented
- **WHEN** any user representation is retrieved after creation or reset
- **THEN** it contains no password hash, token data, or temporary password.

### Requirement: Staff visibility and search
Supervisors SHALL list and view all non-deleted users. Branch Managers SHALL list and view non-deleted users of their own branch read-only. Employees SHALL have no user-list or detail access and SHALL obtain their own account through `/auth/me`. Lists SHALL support branch, city, role, active state, and normalized `q` search over names, mobile, and national code.

#### Scenario: Manager accesses another branch
- **WHEN** a Branch Manager requests a user from another branch by ID
- **THEN** it returns 404 `not_found`, and list searches reveal no such user.

#### Scenario: Employee requests user list
- **WHEN** an Employee requests `/api/v1/users`
- **THEN** it returns 403 `forbidden`.

### Requirement: Administrative lifecycle guards
The service SHALL reject self-deactivation, self-deletion, self-demotion, and self-move with 409 `cannot_modify_self`. It SHALL reject deactivation, deletion, or demotion of the last active Supervisor with 409 `last_supervisor`, including concurrent administration attempts.

#### Scenario: Self-deactivation
- **WHEN** a Supervisor attempts to deactivate their own account
- **THEN** it returns `cannot_modify_self` and changes nothing.

#### Scenario: Concurrent Supervisor removals
- **WHEN** concurrent operations would remove all active Supervisors
- **THEN** at least one active Supervisor remains and the conflicting operation returns a lifecycle conflict.

### Requirement: User updates and deactivation
The service SHALL revoke all refresh tokens and invalidate pending SMS challenges on mobile change, password reset, deactivation, or soft deletion. Role changes to Supervisor SHALL clear the branch; changes from Supervisor SHALL require a branch in the same request. Moving a user SHALL require an active destination branch and preserve historical references.

#### Scenario: Mobile changed
- **WHEN** a Supervisor changes another user's mobile
- **THEN** the new normalized mobile becomes the login identifier, existing refresh tokens are revoked, and challenges sent to the previous mobile cannot authenticate.

#### Scenario: User soft deletion
- **WHEN** an eligible user is deleted
- **THEN** the response is 204, deletion actor and timestamp are recorded, refresh tokens and pending SMS challenges are revoked, and the user disappears from ordinary queries without physical deletion.

#### Scenario: Promote Employee
- **WHEN** a Supervisor promotes an Employee to Supervisor
- **THEN** branch membership is cleared atomically with the role change.

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
