# Campaigns and sales API

All routes are under `/api/v1` and follow the [shared API contracts](api.md).

## Catalog

Authenticated staff can list active options at `GET /occupations` and
`GET /banking-products`. Supervisors can include inactive entries with
`include_inactive=true`, create entries with POST to the collection, and update
them with PATCH to the item. Occupations take a normalized name, and products
take a name, a normalized code, and a nonnegative integer `score_value`.
Send `is_active: false` to retire an option while keeping historical references.

## Manual leads

`POST /leads` requires branch and city UUIDs, first and last names, and an
Iranian mobile. National code, occupation UUID, address, referrer and additional
information are optional. Related branch, city and occupation entries must be
active. Duplicate normalized mobile or national codes return 409.

Only Supervisors can create, list and view registry leads. `GET /leads` supports
`branch_id`, `city_id`, `occupation_id`, and normalized name search with `q`.
`GET /leads/{id}` returns the lead's source data.

Use `POST /leads/{id}/archive` and `POST /leads/{id}/restore` to change
archival state. Archived rows are hidden by default. Supervisors can search all
with `include_archived=true` and find just archived rows with `archived=true`.
A customer, current campaign reservation or nonfinal sale blocks archival with 409.

## Campaigns

Supervisors create campaigns at `POST /campaigns` with title, Jalali start
and end dates, and optional `include_customers` for cross-sell. Drafts can
be edited or soft-deleted. Preview eligible leads under
`GET /campaigns/{id}/selection/preview` with the same lead filters as the
registry. Submit `filters`, explicit `lead_ids`, or `remove_ids` to
`POST /campaigns/{id}/selection` to update draft membership. An empty
`filters` object selects all eligible leads.

`POST /campaigns/{id}/activate` rechecks eligibility, reserves selected leads,
and reports branches without eligible employees. If a lead is reserved in another
campaign the entire activation fails with 409. The reservation survives completion
of lead work and is released by `POST /campaigns/{id}/close`. Dates are
business metadata. Availability follows the explicit status transition.

`GET /campaigns/{id}/leads` returns scoped membership IDs, status, and lead
summary. Employees see unpicked branch leads and their own assignments.
Use `POST /campaigns/{id}/leads/{membership_id}/pick` to claim work.
Managers can POST to the corresponding `reassign` action with an
`employee_id`. `GET /campaigns/{id}/branches/{branch_id}/capacity` shows
computed and effective quotas and current counts. Employees see their own
capacity. Managers can PATCH the employee ID below that route with `quota`
and `reason`.

POST to `/campaigns/{id}/leads/{membership_id}/visits` with the reported Jalali
`visit_date`, a result of `pending`, `interested`, `not_interested`, or
`no_response`, and optional notes. Each POST appends an attempt. GET returns
the summary and paginated attempt history. POST to the membership's
`complete` action after recording an attempt to finish the lead's campaign work.

## Convert to Customer and sale claims

The assigned employee opens `GET /visits/{id}/sales-form` on active, locked work.
For a first sale, values are prefilled from the source lead or saved draft. Supply
the bank-issued `customer_code`, confirm the name, phone, address, and city, and
optionally record national code. PATCH the same form path to save customer fields.
For an already verified customer, the form returns the verified profile and held
product names.

`POST /sales` takes `visit_id`, `banking_product_id`, `account_number`, optional
`proof_text`, and optional `description` and `customer_profile`. Each request
registers one draft. Save several drafts from the same visit and send their
`sale_ids` to `POST /sales/submit` to submit together. Each needs at least five
non-whitespace proof characters. The first conversion also needs a complete
customer profile. Batch submission either saves all selected claims or returns
an error without submitting any.

Authors can GET their sale list or sale by ID, PATCH draft or rejected claims,
and POST to `/sales/{id}/withdraw` for drafts and rejections. Existing claims
can proceed after reassignment, completion or closure. New registration stops
when work is completed or the campaign closes.

`GET /verifications` returns the Supervisor queue grouped by visit. Review the
immutable `submission` and pass its `id` as `submission_id` with a reason to
`POST /sales/{id}/reject`. A resubmission gets a new submission ID. Sale decision
notifications go to the author and carry only a sale reference.

Use `POST /sales/{sale_id}/approve` with `submission_id` to decide one sale.
To approve all reviewed sales from a visit, POST to
`/verifications/visits/{visit_id}/approve` with
`{"sales": [{"sale_id": "...", "submission_id": "..."}]}`. The caller supplies
each reviewed revision. The whole batch fails if any revision is no longer
eligible. Sales submitted after the review can be approved separately.

## Verified customers and retention

Supervisors and Branch Managers can GET `/customers` with `branch_id`,
`city_id`, `product_id`, `customer_since_from`, `customer_since_to` and
`q` for name or phone. Managers see their own branch. Customer detail
includes held products, sale summaries, campaign visits and generated
retention tasks. Product account references in this registry are visible to
Supervisors. PATCH `/customers/{id}` to correct name, phone, address or city.
Employees access the customer details needed for assigned work through the
sales form or retention task detail.

Supervisors manage `/retention-schedules` with GET, POST and item PATCH.
Each schedule takes a label, positive `days_after_conversion`, and optional
`is_active`. The API accepts the legacy `requires_approval` boolean and returns
`false` for it.

## Retention tasks

First sale approval creates one open task per active schedule and assigns each
task to the employee who acquired the customer. Each due date adds the
schedule's calendar-day offset to the conversion date in the business timezone.
Subsequent approvals generate no additional tasks. The migration opens tasks
previously awaiting approval and preserves their IDs, assignees, and due dates.

- `GET /retention-tasks` lists paginated tasks by due date. Supervisors see all
  tasks, and Branch Managers see only their branch's tasks. Employees see
  their own open tasks by default and use `?status=completed` for their history.
  Supervisors and Branch Managers can filter by `open`, `completed`, or `cancelled`.
- `GET /retention-tasks/{task_id}` shows the task and the customer's name,
  phone, address, and city ID within the same role scope. Out-of-scope task
  IDs return 404.
- `POST /retention-tasks/{task_id}/complete` is the assigned employee's only
  task action. Send a Jalali `visit_date` on or before the current business
  date, a `result` of 1–30 characters after trimming, and optional `notes`.
  Completion records the server timestamp and employee, writes an audit
  event, and moves the task to completed history. A repeated completion
  returns 409. Supervisor and Branch Manager task access is read-only.
