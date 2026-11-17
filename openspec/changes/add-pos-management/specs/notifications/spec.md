## Purpose

Keep staff informed of POS follow-up changes through private, transactionally consistent in-app notifications.

## ADDED Requirements

### Requirement: Transactional POS event delivery
The system SHALL create in-app notifications in the same transaction as dispatch, assignment, reassignment, cancellation, and completion. Dispatch SHALL notify the current branch manager when present; assignment SHALL notify the assignee; reassignment SHALL notify old/new assignees; cancellation SHALL notify the assignee when present; completion SHALL notify the assigning manager.

#### Scenario: Rolled-back business action
- **WHEN** assignment fails or its transaction rolls back
- **THEN** no notification for that assignment persists.

#### Scenario: Dispatch without manager
- **WHEN** a branch has no manager during dispatch
- **THEN** pending work persists without an employee notification or fabricated recipient and remains visible in the branch queue.

### Requirement: Private notification access
Authenticated users SHALL list only their own paginated notifications, filter read state, obtain their unread count, mark one read, and mark all their notifications read. Another recipient's notification ID SHALL return 404. Repeated read operations SHALL be idempotent and retain the initial read time.

#### Scenario: Foreign notification
- **WHEN** a user attempts to view or mark another user's notification read
- **THEN** the request returns 404 and the notification is unchanged.

### Requirement: Event references and channels
Notifications SHALL carry event type, title, optional body, event time, and related visit/device IDs with channel `in_app`. Access to a notification SHALL NOT bypass current authorization on referenced objects. This change SHALL send no push, email, or external message.

#### Scenario: Former assignee follows a link
- **WHEN** an employee follows an old notification after their visit was reassigned
- **THEN** notification access succeeds for its recipient but visit access follows current scope and returns 404.
