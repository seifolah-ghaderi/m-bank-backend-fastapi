# Design

## Context

The existing schedule API manages day offsets and active schedules. First sale approval creates tasks in the conversion transaction. The retention task table stores customer, schedule, assignee, due date, and status, and the customer detail API already lists generated tasks. The workflow can use these records directly.

## Goals / Non-Goals

### Goals

- Make generated tasks available to their assignees immediately and expose a scoped task queue and detail.
- Record each completion on the same task with its actor, visit details, timestamp, and audit event.

### Later changes

Leagues, CRM reports and notifications, retention-visit sales, and employee departure and transfer remain separate workstreams.

## Decisions

### Generation and schedule compatibility

Generate `open` tasks in the existing first-sale approval transaction. Keep the original schedule, assignee, due-date logic, and unique customer/schedule pair. Treat `requires_approval` as a deprecated compatibility field that accepts the existing boolean and always reads and persists as `false`. This keeps the schedule payload shape usable during client upgrades.

### Scoped task API

| Endpoint | Access and behavior |
| --- | --- |
| `GET /api/v1/retention-tasks` | Paginated status filter. Supervisors see all tasks, managers see their branch, and employees see their assigned work in that branch. Employee lists default to open tasks ordered by due date with an explicit filter for completed history. |
| `GET /api/v1/retention-tasks/{task_id}` | Use the same visibility rules. Include the minimum customer contact fields needed to conduct the visit. |
| `POST /api/v1/retention-tasks/{task_id}/complete` | The employee assignee supplies `visit_date`, `result`, and optional `notes`. Supervisors and managers have read access to tasks. |

Scope requests by the verified customer's branch and employee assignment before returning contact information. Keep the queue response focused on task and customer identifiers, assignee, schedule label, due date, and status. For detail, expose the customer's name, phone, address, and city. Keep account references and sale proof within their existing sales and customer APIs.

### Completion and history

Use the existing Jalali date contract and reject dates after the current business date. Use a required trimmed text result of up to 30 characters and optional notes. A fixed set of scored results can be defined when the retention league is specified.

Add nullable `visit_date`, `result`, `notes`, `completed_at`, and `completed_by` columns. Lock the scoped task and recheck its open state inside the request transaction before writing completion and audit data. Record the server timestamp and current assignee ID at completion. Use the completed task as the read-only history record. The verified customer's branch provides historical branch attribution.

## Risks / Trade-offs

- **Legacy schedules request approval** → Normalize the persisted flag and keep accepting it during the transition.
- **Existing tasks lack completion details** → Keep historical records and leave unavailable details null.
- **Overlapping completion requests** → Use a row lock and return a conflict after the first completion commits.

## Migration Plan

Add the completion columns, open existing `pending_approval` tasks, and normalize existing schedule flags to `false`. Preserve task IDs, links, due dates, assignment, and terminal statuses. Remove `pending_approval` from the allowed task states after converting those rows. Deploy the migration and application together. The previous approval state cannot be reconstructed from the upgraded records. If a database rollback is required, preserve any new completion history before reverting the schema.
