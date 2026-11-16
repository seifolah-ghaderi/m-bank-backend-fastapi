# Organization and user APIs

All routes use `/api/v1`. Cities/branches support GET list/detail, POST create,
PATCH update, and DELETE soft deletion. Only Supervisors write. City fields are
`name` and `is_active`; branch fields are `city_id`, `code`, `name`, `address`,
`phone`, and `is_active`. Branch codes normalize to uppercase letters/digits/hyphens,
2–20 characters; city names are 2–100 and branch names 2–150 characters.

Cities are visible to every authenticated role. Branch Managers/Employees see only
their branch; out-of-scope IDs return 404. Lists accept `q`, `is_active`, and
`include_inactive`, plus `city_id`/`branch_id` for branches. Omitted inactive filtering
includes inactive rows for Supervisors and excludes them for others. Explicit
`include_inactive=false` provides active lookups. A manager's conflicting branch
filter returns 403. Allowed sorts: `name`, `created_at`, with optional `-` prefix;
default `name`, ID tie-breaker. Pagination follows [API contracts](api.md).

Branch output includes city identity, derived optional manager, and
`active_employee_count`. Manager is derived from the one non-deleted Branch Manager
user (including inactive managers); no separate manager column exists. Moving a
branch changes its city without changing user membership. City deletion with
non-deleted branches returns `city_has_branches`; branch deletion with non-deleted
users returns `branch_in_use`. Inactive dependents still count. Deactivation preserves
existing data while an inactive branch rejects new staff assignments.

## Users

`/users` provides GET list and POST create; `/users/{id}` provides GET, PATCH, DELETE.
POST actions `/activate`, `/deactivate`, and `/reset-password` sit below the user ID.
Only Supervisors write. Managers read their own branch; Employees use `/auth/me`
and cannot list/view users here. Lists accept `branch_id`, `city_id`, `role`,
`is_active`, and normalized `q` across full name, mobile, and national code. Allowed
sorts: `created_at`, `first_name`, `last_name`, `mobile`; default `-created_at`.

Create requires names, normalized Iranian mobile, role, and an active branch for
non-Supervisors; national code is optional/checksummed. Supervisors have no branch.
Create/reset returns a generated ten-character `temporary_password` once and sets
`must_change_password`. Subsequent reads contain no password/hash/token material.
Reset unlocks the account. Mobile change, reset, deactivation, and deletion revoke
refresh sessions and invalidate pending SMS challenges. Changing one's own password
also invalidates pending challenges.

Lifecycle conflicts include `cannot_modify_self`, `last_supervisor`, and
`branch_already_has_manager`. Database uniqueness protects manager assignment under
concurrent requests. Demoting a Supervisor requires a branch in the same request;
promoting staff to Supervisor clears branch membership. Soft deletion retains actor
references and permits reuse of live-unique identities; the old user row remains.

## Audit and POS handoff

Supervisor-only `GET /audit-logs` accepts `entity_type`, `entity_id`, `actor_id`,
`action`, Jalali `from_date`/`to_date`, and pagination. Sort supports `occurred_at`
(default descending, ID tie-breaker). Reads do not create audit entries. Business
writes and audit records commit together; failed auth counters/revocations and
their sanitized audit records persist before the error response.

POS management will introduce device counts, device-dependent organization deletion
guards, and `user_has_open_tasks` guards on employee changes. This core API has no
placeholder POS counts, routes, or tables. Notifications, imports, and reports also
remain in that subsequent change.
