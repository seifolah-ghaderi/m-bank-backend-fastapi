# retention-generation Specification

## Purpose

Create the initial retention task set when a lead becomes a verified CRM customer.

## Requirements

### Requirement: Retention schedules
Only Supervisors SHALL manage retention schedule labels, positive day offsets, activation and whether later publication requires approval. Active schedules SHALL have distinct day offsets. Schedule edits SHALL affect future conversions and preserve previously generated task dates and initial state.

#### Scenario: Duplicate active day offset
- **WHEN** a Supervisor activates a schedule with the same offset as another active schedule
- **THEN** the request returns 409 and the schedule is not activated.

### Requirement: First-conversion task generation
First sale approval SHALL generate exactly one task per active retention schedule. Tasks SHALL start assigned to the acquiring employee and be due the specified number of calendar days after conversion in the business timezone. Initial state SHALL be open or pending approval according to the schedule. Later approvals SHALL leave existing tasks unchanged.

#### Scenario: Conversion with mixed schedules
- **WHEN** a lead converts while one active schedule requires publication approval, another does not and a third schedule is inactive
- **THEN** the system generates one pending-approval task and one open task with their respective due dates, and creates no task for the inactive schedule.

#### Scenario: Additional product is approved
- **WHEN** a later sale for a verified customer is approved
- **THEN** it generates no retention task, even if active schedules changed since conversion.
