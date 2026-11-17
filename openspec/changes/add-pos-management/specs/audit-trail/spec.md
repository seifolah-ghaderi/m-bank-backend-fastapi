## MODIFIED Requirements

### Requirement: Append-only preservation
The application database identity SHALL be unable to update or delete audit entries, or physically delete city, branch, user, POS terminal, transaction, visit, branch/owner history, or selection-evidence business records. Historical actor and entity identities SHALL survive soft deletion.

#### Scenario: Database enforcement
- **WHEN** the application database identity attempts to modify or delete an audit row or physically delete a business row
- **THEN** the database denies the operation.

#### Scenario: POS database preservation
- **WHEN** the runtime database identity attempts to physically delete a POS transaction, visit, terminal history, or selection snapshot
- **THEN** the database denies the operation.

### Requirement: Supervisor audit retrieval
`GET /api/v1/audit-logs` SHALL provide Supervisor-only paginated retrieval filtered by entity type, entity ID, actor ID, action, and occurrence date range, newest first with deterministic ordering. Ordinary reads SHALL not create audit records except downloads of stored original import files.

#### Scenario: Filtered audit history
- **WHEN** a Supervisor requests entries for a user and action within a date range
- **THEN** only matching entries appear with the standard pagination envelope.

#### Scenario: Persian audit dates
- **WHEN** a Supervisor supplies Jalali occurrence-date filters
- **THEN** the service filters the corresponding business-timezone interval and serializes occurrence timestamps and date values in before/after fields using the shared Jalali contract.

#### Scenario: Unauthorized audit read
- **WHEN** a Branch Manager or Employee requests the audit endpoint
- **THEN** it returns 403 `forbidden`.

#### Scenario: Import original download
- **WHEN** a Supervisor successfully downloads a stored original import file
- **THEN** the file-read action is audited with actor, import identity, and request context without copying file contents into audit.

## ADDED Requirements

### Requirement: POS action audit
POS registry, history, transaction, import, dispatch, assignment, reassignment, cancellation, completion, correction, tag, and threshold mutations SHALL record actor, action, affected entity, and changed values in audit. Successful mutations and their audit entries SHALL persist together. Exact decimal amounts SHALL remain lossless in audit and snapshots.

#### Scenario: Transaction correction provenance
- **WHEN** an imported existing period changes amount or count
- **THEN** its old/new values and import provenance are recoverable through audit.

#### Scenario: Bulk row rollback
- **WHEN** one bulk dispatch or import row fails
- **THEN** that row has no successful-mutation audit entry and successful rows retain their own audit entries.
