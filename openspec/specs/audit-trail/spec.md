# audit-trail Specification

## Purpose

Preserve a trustworthy, sanitized history of administrative and authentication actions for Supervisor review.

## Requirements

### Requirement: Transactional action recording
The service SHALL audit city, branch, and user writes, bootstrap, login success/failure, password actions, logout, refresh-token reuse, and SMS challenge delivery/resend/verification outcomes. Business mutations and their audit records SHALL persist or roll back together. Security rejection records SHALL persist with their security state before returning an error. Login success SHALL mean completion of both factors.

#### Scenario: Business action succeeds
- **WHEN** a Supervisor changes a branch name
- **THEN** the change and an audit entry with the actor, action, entity, and changed fields persist together.

#### Scenario: Business mutation fails
- **WHEN** a city update violates uniqueness
- **THEN** neither the update nor a successful-update audit entry persists.

#### Scenario: Rejected login
- **WHEN** an incorrect password produces a 401 response
- **THEN** a `login_failed` audit record remains persisted with a null actor and masked mobile.

#### Scenario: SMS verification failure
- **WHEN** an incorrect SMS code produces a 401 response
- **THEN** the failed verification audit entry and attempt counter remain persisted, without recording the submitted or expected code.

#### Scenario: First factor only
- **WHEN** a correct password results in challenge delivery
- **THEN** audit records the challenge/delivery outcome but does not yet record a successful login.

### Requirement: Audit data safety
Audit entries SHALL contain occurrence time, optional actor identity and role, action, entity identity, changed fields, and available request ID and IP. They SHALL omit passwords, password hashes, temporary passwords, SMS codes and their digests, provider credentials, CSRF secrets, and tokens. Failed-login and SMS destination mobiles SHALL be masked, for example `0912***4567`.

#### Scenario: Password reset audit
- **WHEN** a Supervisor resets a password
- **THEN** the audit identifies the reset action and affected user without storing any password, hash, or token.

### Requirement: Append-only preservation
The application database identity SHALL be unable to update or delete audit entries, or physically delete city, branch, and user business records. Historical actor and entity identities SHALL survive soft deletion.

#### Scenario: Database enforcement
- **WHEN** the application database identity attempts to modify or delete an audit row or physically delete a business row
- **THEN** the database denies the operation.

### Requirement: Supervisor audit retrieval
`GET /api/v1/audit-logs` SHALL provide Supervisor-only paginated retrieval filtered by entity type, entity ID, actor ID, action, and occurrence date range, newest first with deterministic ordering. Ordinary reads SHALL not create audit records.

#### Scenario: Filtered audit history
- **WHEN** a Supervisor requests entries for a user and action within a date range
- **THEN** only matching entries appear with the standard pagination envelope.

#### Scenario: Persian audit dates
- **WHEN** a Supervisor supplies Jalali occurrence-date filters
- **THEN** the service filters the corresponding business-timezone interval and serializes occurrence timestamps and date values in before/after fields using the shared Jalali contract.

#### Scenario: Unauthorized audit read
- **WHEN** a Branch Manager or Employee requests the audit endpoint
- **THEN** it returns 403 `forbidden`.
