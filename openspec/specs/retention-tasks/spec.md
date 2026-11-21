# retention-tasks Specification

## Purpose

Give employees an actionable retention queue and preserve completed visits for branch and Supervisor review.

## Requirements

### Requirement: Scoped retention task visibility
The system SHALL provide paginated list and detail APIs for retention tasks. Supervisors SHALL see tasks across the organization. Branch Managers SHALL see only their branch's tasks. Employees SHALL see only their assigned open tasks and completed history. Direct access outside the caller's scope SHALL return 404.

#### Scenario: View branch tasks
- **WHEN** a Branch Manager lists tasks for their branch
- **THEN** the response contains only tasks belonging to customers of that branch and includes open work and historical results.

#### Scenario: Open the employee queue
- **WHEN** an employee lists tasks without a status filter
- **THEN** the response contains only their open tasks, ordered by due date by default, and the employee can select completed history with the status filter.

#### Scenario: Inspect an assigned task
- **WHEN** an authorized user opens a task detail
- **THEN** it includes the task, its due date, assignee, and the customer's name and contact details needed for the visit. Completed tasks also include their visit result and completion details.
- **AND** the response omits banking product account references and sale proofs.

#### Scenario: Access another employee's or branch's task
- **WHEN** an employee requests a coworker's task or a Branch Manager requests a task from another branch
- **THEN** the response is 404 and reveals no task or customer data.

### Requirement: Employee completion of an open task
The system SHALL allow only the current employee assignee to complete an open task. Completion SHALL require a Jalali visit date on or before the current business date and a nonblank result, and SHALL allow optional notes. Completion SHALL store the visit details, server timestamp and employee ID, and create an audit record in the same transaction.

#### Scenario: Complete an assigned visit
- **WHEN** the assignee submits a valid visit date and result for an open task
- **THEN** the task becomes completed, leaves the open queue, and appears in completed history with the submitted visit details and server-set completion metadata.

#### Scenario: Invalid completion
- **WHEN** the assignee submits a future visit date or a blank result
- **THEN** the API returns 422 and the task stays open.

#### Scenario: Unauthorized completion
- **WHEN** a Branch Manager or Supervisor attempts completion
- **THEN** the API returns 403 and task data stays unchanged.

#### Scenario: Another employee attempts completion
- **WHEN** an employee attempts to complete a task they do not own
- **THEN** the API returns 404 and task data stays unchanged.

### Requirement: Read-only retention task history
Completed retention tasks SHALL remain available within the caller's scope. Employee completion SHALL be the sole task action. The system SHALL preserve the original completion details and audit event when another completion is attempted on the same task.

#### Scenario: Duplicate completion
- **WHEN** the assignee repeats completion or submits two concurrent valid completion requests
- **THEN** at most one completion is accepted, a request against the completed task returns 409, and the task has one set of completion details and one completion audit event.
