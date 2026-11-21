# retention-generation Specification

## Purpose

Create the initial retention task set when a lead becomes a verified CRM customer.

## Requirements

### Requirement: Retention schedules
Only Supervisors SHALL manage retention schedule labels, positive day offsets, and schedule activation. Active schedules SHALL have distinct day offsets. Schedule edits SHALL affect future conversions and preserve the dates and state of existing tasks. The schedule API SHALL accept the legacy `requires_approval` boolean without applying an approval gate and SHALL return `false` for that field.

#### Scenario: Duplicate active day offset
- **WHEN** a Supervisor activates a schedule with the same offset as another active schedule
- **THEN** the request returns 409 and the schedule is not activated.

#### Scenario: Existing client sends the legacy setting
- **WHEN** a Supervisor creates or updates a schedule with `requires_approval: true`
- **THEN** the request accepts the field, the response reports `requires_approval: false`, and the schedule generates open tasks when active.

### Requirement: First-conversion task generation
First sale approval SHALL generate exactly one open task per active retention schedule. Tasks SHALL start assigned to the acquiring employee and be due the specified number of calendar days after conversion in the business timezone. Later approvals SHALL leave existing tasks unchanged.

#### Scenario: Conversion with mixed schedules
- **WHEN** a lead converts while some schedules are active and another is inactive
- **THEN** each active schedule generates one open task with its calculated due date, and the inactive schedule generates none.

#### Scenario: Additional product is approved
- **WHEN** a later sale for a verified customer is approved
- **THEN** it generates no retention task, even if active schedules changed since conversion.

### Requirement: Activation of existing pending tasks
The system SHALL make tasks previously awaiting publication available as open tasks. It SHALL preserve task IDs, customer and schedule links, assignees, and due dates.

#### Scenario: Upgrade with tasks awaiting publication
- **WHEN** an existing deployment upgrades with a mix of pending and historical tasks
- **THEN** every `pending_approval` task becomes `open` and every existing open, completed, and cancelled task keeps its status.
