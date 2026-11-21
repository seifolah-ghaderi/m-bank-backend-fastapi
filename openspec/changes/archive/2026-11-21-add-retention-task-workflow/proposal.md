# Proposal

## Why

First sale approval already generates retention tasks. Employees need a way to find their tasks, record visits, and complete the work, and Branch Managers need visibility into their branch's workload and results.

## What Changes

- Open every task automatically when it is generated from an active retention schedule. **BREAKING** for workflows that depended on a publication approval step. Preserve compatibility with existing schedule clients by accepting the legacy `requires_approval` field and returning `false`.
- Open existing `pending_approval` tasks in a migration and preserve their assignees, due dates, and IDs.
- Add scoped task list and detail APIs. Supervisors can view all tasks, Branch Managers can view their own branch's tasks, and employees can view their own open tasks and completed history.
- Let only the assigned employee complete an open task with a visit date and result. Keep completed tasks as read-only history and audit completion.
- Cover the workflow with PostgreSQL API integration tests. Update the API documentation after validation.

## Capabilities

### New Capabilities

- `retention-tasks` covers task visibility, employee completion, and task history.

### Modified Capabilities

- `retention-generation` opens tasks automatically and retires the approval setting.

## Impact

Adds task APIs, completion fields, an Alembic migration for existing tasks, and API integration coverage. The task API exposes employee completion as the only task action. Supervisor schedule administration continues. Leagues, retention-visit sales, notifications, reports, and employee departure and transfer are separate changes.
