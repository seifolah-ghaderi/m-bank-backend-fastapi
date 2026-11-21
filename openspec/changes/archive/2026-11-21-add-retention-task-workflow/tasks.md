# Tasks

## 1. Automatic task activation

- [x] 1.1 Add nullable visit and completion fields to retention tasks. Normalize legacy schedule flags, open pending tasks, and remove the pending state from the task constraint. Verify the Alembic migration on both a fresh database and a prior-revision database with open, pending, completed, and cancelled tasks.
- [x] 1.2 Open tasks in the existing first-sale approval transaction and keep the legacy schedule field compatible. Update the PostgreSQL sale-conversion integration assertions to cover active and inactive schedules, original assignee and due dates, legacy input, and no duplicate tasks after another product approval.

## 2. Task visibility and completion

- [x] 2.1 Add paginated list and detail endpoints under `/api/v1/retention-tasks` with role and branch scoping. Verify Supervisor visibility, read-only branch visibility for managers, assignee-only employee visibility, open and completed filters, and detail response privacy in API integration tests.
- [x] 2.2 Add employee-only completion with Jalali visit date, result, optional notes, server completion metadata, and an audit record. Verify input validation, authorization, read-only history, and one successful completion and audit record under concurrent requests.

## 3. Workflow validation and documentation

- [x] 3.1 Exercise first sale approval, automatic task appearance in the employee queue, manager read access, employee completion, and history in a PostgreSQL API integration test. Use the repository's in-process API integration harness for the full workflow. Run the relevant regression tests and Ruff checks.
- [x] 3.2 After validation, update `docs/marketing.md` with automatic activation, legacy field behavior, task routes, role access, completion input, and the history filter. Check the documented behavior against the tested API.
