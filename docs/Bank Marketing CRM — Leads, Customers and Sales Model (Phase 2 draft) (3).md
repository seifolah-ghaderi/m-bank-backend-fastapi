# Bank Marketing CRM — Leads, Customers and Sales Model (Phase 2 draft)

Nov 16, 2026 · @seif

## 1. Scope, status and decisions

This spec defines how imported leads become verified bank customers, and how products, visits and retention attach to them. It continues the Phase 1 spec (core modules and POS) and reuses its conventions: UUIDv7 keys, BaseMixin and soft delete, the audit log, the error format and the Supervisor, Branch Manager and Employee roles. Status: draft. The domain model is agreed; endpoints and screens are not yet specified.

### Scope

- In: lead import and archiving, campaigns and lead selection, campaign leads (picking, locking, reassignment), visits, product sales and their verification, customers and the products they hold, retention task generation, and the score entries written on approval.
- Out: league ranking calculation, notification channels beyond in-app, POS (Phase 1), any integration with the Core Banking System.

### Decision log

| Id | Decision | Reason |
| --- | --- | --- |
| D1 | The app records a sale claim, never a bank customer. The employee creates the real customer and activates products in the bank's own system; this app stores the product and account number, and the Supervisor verifies them there. | The app is not connected to Core Banking |
| D2 | A lead is a permanent identity record. Conversion never alters or replaces it. | Original lead data must stay available; history is never deleted |
| D3 | A separate customers table; a row is created only when the first sale of a lead is approved. It carries the customer's own name, address and phone. | A customer is always valid and verified; the hot table stays small; batch imports and lead archiving never touch customers |
| D4 | Products belong to customers, not leads. A held product is a customer\_products row, created only on approval. A lead owns no bank product; it has only sales that are waiting for or have failed verification. | Product owner decision: every relationship of a customer must be valid |
| D5 | Sales stay as history after approval or rejection. An approved sale points to the customer\_products row it created. | Audit and rejection history |
| D6 | Customers are excluded from acquisition campaigns by default. A Supervisor can include them explicitly (for a cross-sell campaign). | Product owner decision |
| D7 | Adding a product to an existing customer uses the same sale, verification and approval flow through any of three entry points: a cross-sell campaign visit, a retention-task visit, or directly on the customer. The schema supports all three; which ones ship first is open (question Q1). | Avoids a second verification process |
| D8 | Pipeline stage (opportunity, pending verification, and so on) is derived from visits and sales, not stored. Stored on the lead: only is\_customer. | A stored stage can drift out of sync |
| D9 | One score ledger (score\_transactions) holds every scoring source. Approval writes the entry in the same transaction. | Leagues and rankings read one table |
| D10 | Retention tasks are generated once, at conversion, counted from customer\_since. Later product approvals do not generate new ones. | Retention follows the customer, not each product |
| D11 | Leads are deduplicated at import by normalized mobile number, then national code. | Batch imports repeat people across periods |
| D12 | A customer has its own identity: bank customer code, first name, last name, address, phone and city. The employee enters them with the first sale, the Supervisor verifies them, and they may differ from the lead's imported data. | Imported lead data can be wrong; the bank's record is what counts |
| D13 | Every product sale needs a proof, a free text written by the employee, before it can be submitted. | Gives the Supervisor evidence when checking the bank system |
| D14 | Lead picking is capped per employee. The cap is not a fixed or configured number: the backend computes it when needed as the branch's assigned leads divided by its active employees, rounded up, so it follows staff changes by itself; a Branch Manager can override it for one employee. | Keeps the work balanced inside a branch |
| D15 | Every action that can feed a KPI gets a server-set timestamp that is never overwritten: lead assigned to a branch, picked, visited, sale registered, submitted, verified (section 4). | KPIs need dates that cannot be edited afterwards |
| D16 | A branch code is numeric (2 to 10 digits) and is the key used in imports. Phase 1 branches.code changes to match. | It is the bank's own branch code |
| D17 | A lead can be visited several times in a campaign. There is still one visit record per lead per campaign, which summarizes the latest visit, and every visit adds a row to visit\_attempts, so earlier results and descriptions are never overwritten. | Keeps the one-visit rule and the full history KPIs need |
| D18 | Registering a sale has two cases. If the lead is not yet a customer, the employee fills the customer draft (bank customer code, name, address, phone, city) together with the sale (product, account number, proof). If the customer already exists, the employee only attaches the new product sale. | One verification flow; the customer exists only after approval |
| D19 | A customer has a code issued by the bank (customer\_code), typed by the employee, verified by the Supervisor and unique in the system. Account numbers stay on each product. | It is the bank's own identifier of the customer |

## 2. Domain at a glance

&#91;embedded content: lead to customer flow · 9 tables, 1 approval step\]

Leads feed campaigns and visits, but a sale is only a claim until a Supervisor approves it. Approval creates the customer, the products it holds and the score in one step, and the lead row itself never changes.

## 3. Lifecycles and workflows

A sale moves from draft to submitted to approved or rejected, and the first approval of a lead converts it into a customer in one database transaction.

### Sale lifecycle

| From | Action | To | Who |
| --- | --- | --- | --- |
| (new) | Register a product on a visit, with account number and proof | draft | The employee who owns the visit |
| draft | Submit (one sale, or all drafts of a visit at once); needs the proof text, and for the lead's first sale the customer details | submitted | Same employee |
| draft or rejected | Withdraw | withdrawn | Same employee |
| submitted | Approve | approved | Supervisor |
| submitted | Reject, with a required reason | rejected | Supervisor |
| rejected | Edit and resubmit | submitted | Same employee |

Approved and withdrawn are final. Each sale is verified on its own, so a visit with three products can end with two approved and one rejected. Rejected and withdrawn sales never produce a score.

### Conversion transaction (approval)

Approving a sale runs these steps in one transaction; if any step fails the sale stays submitted.

1. Lock the sale row and the lead row (SELECT FOR UPDATE) and check the sale is submitted.
2. Check the customer does not already hold the product. If it does, approval fails with 409 product\_already\_held and the Supervisor must reject the sale.
3. Mark the sale approved and record verified\_by and verified\_at.
4. If the lead has no customers row: create it (lead\_id, branch\_id copied from the lead, customer\_code, first\_name, last\_name, phone, address and city\_id copied from the customer details the employee entered, customer\_since as today in the business timezone, converted\_at as now, acquired\_by as the sale's employee, first\_sale\_id), set leads.is\_customer to true, and generate retention tasks from every active retention schedule, due on customer\_since plus the schedule's days, assigned to acquired\_by.
5. Create the customer\_products row (customer, product, account number, started\_at, source\_sale\_id) and store its id on the sale.
6. Insert one score\_transactions row with the employee and the points copied from the product's current score value, so later changes to a product's score do not alter history.
7. Write the audit rows and send verification\_approved to the employee.

When the customer already exists (a later product), steps 1 to 3, 5, 6 and 7 run; no customer row and no retention tasks are created.

### Rejection loop

- Reject stores rejection\_reason and returns the sale to the employee with the notification verification\_rejected.
- The employee corrects the product, account number or description and resubmits. resubmit\_count increases by one and the earlier rejection stays in the audit log.
- A lead whose every sale is rejected or withdrawn stays a lead.

### Customer details and proof

- The customer's own bank customer code, name, address, phone and city are entered by the employee, because the bank's record can differ from the imported lead. They are stored once per lead in customer\_drafts, pre-filled from the lead, and the employee can edit them until the first sale is approved.
- A lead's first sale cannot be submitted without these details (422 customer\_details\_required). Later sales of the same lead, and sales for an existing customer, reuse them and need nothing extra.
- The Supervisor sees the details beside the sale and may correct a typo before approving; the correction is audited.
- On approval the details are copied into the customers row. The draft stays as history and the lead row is never changed.
- Every sale needs a proof: a free text of at least 5 characters written by the employee, for example how the account was confirmed in the bank system. It may be empty while the sale is a draft, is required to submit, and can be edited when a rejected sale is resubmitted. The Supervisor reads it during verification.

### Registering a sale: new customer or existing customer

| Case | The employee fills | Result |
| --- | --- | --- |
| The lead is not a customer yet | The customer draft (bank customer code, name, address, phone, city) and the sale (product, account number, proof) | A draft customer record and a draft sale, submitted together; nothing becomes a customer until a Supervisor approves |
| The lead is already a customer | Only the sale (product, account number, proof) | The sale attaches to the existing customer; approval adds one product, with no new customer and no retention tasks |

Endpoints of this flow:

- PUT /leads/{lead\_id}/customer-draft saves the draft; it returns 409 lead\_is\_customer when the lead already is a customer.
- POST /sales creates a draft sale with lead\_id, banking\_product\_id, account\_number, proof\_text and its source (visit\_id, retention\_task\_id, or neither for a direct sale).
- PATCH /sales/{id} edits a draft or rejected sale; POST /sales/{id}/withdraw withdraws it.
- POST /sales/submit takes sale\_ids and checks proof, customer details (first sale only), customer\_code uniqueness and duplicate products in one call.
- GET /verifications is the Supervisor queue; POST /sales/{id}/approve and POST /sales/{id}/reject decide each sale.

### Adding a product to an existing customer

All three entry points create a normal sale with customer\_id set, go through the same verification, and on approval add a customer\_products row only.

| Path | Entry point | Sale is anchored to | What it needs |
| --- | --- | --- | --- |
| A. Cross-sell campaign | A Supervisor includes customers in a campaign; the employee visits as usual | visit\_id | The include\_customers option in lead selection |
| B. Retention visit | The employee registers a product while completing a retention task | retention\_task\_id | The retention result form accepts products |
| C. Direct | The employee opens the customer and registers a product | Neither; source\_type is direct | POST /customers/{id}/sales, restricted to the customer's branch |

A check constraint requires exactly one anchor that matches source\_type. Which paths ship first is an open decision (Q1). Whether cross-sell approvals score is open as well (Q2).

### Campaign exclusion

- Selecting leads for a campaign skips leads where is\_customer is true, unless the Supervisor sends include\_customers true.
- The rule that a lead belongs to at most one active campaign applies to included customers too.
- A customer inside a cross-sell campaign is marked as a customer in the employee's list, with the products already held, so employees do not offer them again.

### Activation, assignment and capacity-based picking

Leads are added to a campaign while it is a draft; each one is assigned to its own branch and stamped with assigned\_to\_branch\_at. Employees see them only after activation.

1. Activation checks the one-active-campaign rule (section 4, campaign\_leads), sets activated\_at on the campaign and is\_open on its leads.
2. Nothing is stored per employee at activation. Whenever a pick is attempted, or an employee or manager opens the capacity view, the backend computes the quota from live data: the branch's leads in the campaign divided by the branch's active employees, rounded up.
3. A branch that has leads but no active employee is listed in the activation result. Its leads cannot be picked until the Supervisor adds an employee to it.
4. An employee picks a lead of their own branch. The backend counts the leads this employee has already picked in the campaign (campaign\_leads rows with locked\_by equal to the employee) and refuses the pick with 409 quota\_reached when the count has reached the quota, or lead\_unavailable if someone else was first. A successful pick sets locked\_by and locked\_at (the pickup date used for KPIs). To stop two simultaneous picks from exceeding the quota, the pick takes a transaction-level advisory lock on the campaign and employee before counting.
5. The quota follows staff changes by itself: a new employee lowers it for future picks, a deactivated one raises it. An employee who has already picked more than the new quota simply cannot pick more. Nothing is rewritten.
6. A Branch Manager can set a quota override for one employee in one campaign, with a reason (stored in campaign\_quota\_overrides). The override replaces the computed value for that employee only; other employees' quotas are not adjusted.
7. A Branch Manager can reassign a picked lead to another employee of the branch even if that employee is at quota. Counts follow locked\_by, so nothing else needs updating.

The capacity view, GET /campaigns/{id}/branches/{branch\_id}/capacity, returns for every active employee of the branch: the computed quota, the picked count, the finished count, the remaining capacity, and whether an override applies.

| Branch leads | Active employees | Quota per employee |
| --- | --- | --- |
| 120 | 8 | 15 |
| 50 | 6 | 9 (50 divided by 6, rounded up) |
| 10 | 0 | None; the leads wait until an employee exists |

### Derived pipeline stage

Dashboards compute the stage from related rows; it is never stored.

| Stage | Rule |
| --- | --- |
| new | Not part of any campaign yet |
| in\_campaign | Has a campaign lead that is available or locked, with no visit result yet |
| opportunity | Latest visit result is Interested and the lead has no sale |
| not\_interested | Latest visit result is Not Interested or No Response and no open campaign |
| pending\_verification | Has at least one submitted sale |
| needs\_correction | Has a rejected sale and no submitted one |
| customer | is\_customer is true |

## 4. Data model

This phase adds 13 tables to the Phase 1 schema. BaseMixin and SoftDeleteMixin mean the same as in Phase 1 section 4 (id, created\_at, updated\_at, created\_by, updated\_by; deleted\_at, deleted\_by). Master tables occupations (name, is\_active) and banking\_products (name, code, score\_value, is\_active) are referenced here and defined with the master data. The import\_logs table from Phase 1 gains import\_type leads.

### leads

BaseMixin and SoftDeleteMixin.

| Column | Type | Rules |
| --- | --- | --- |
| branch\_id | uuid | FK branches, not null; the owning branch, set at import and not changed by conversion |
| city\_id | uuid | FK cities, not null |
| occupation\_id | uuid | FK occupations, null |
| first\_name, last\_name | varchar(100) | not null |
| mobile | varchar(11) | not null; normalized 09XXXXXXXXX; unique among non-deleted leads |
| national\_code | varchar(10) | null; checksum validated; unique when present |
| address | text | null |
| referrer | varchar(200) | null |
| additional\_info | text | null |
| is\_customer | boolean | not null, default false; set in the conversion transaction only |
| first\_import\_id, last\_import\_id | uuid | FK import\_logs, null |
| archived\_at, archived\_by | timestamptz, uuid | null; archived leads are hidden from selection and lists but kept |

Indexes: (branch\_id) where archived\_at and deleted\_at are null; (branch\_id, is\_customer); (city\_id, is\_customer); trigram GIN on first\_name plus last\_name.

### campaigns

| Column | Type | Rules |
| --- | --- | --- |
| title | varchar(200) | not null |
| start\_date, end\_date | date | not null; check end\_date >= start\_date |
| status | varchar(10) | not null, default draft; check in (draft, active, closed) |
| include\_customers | boolean | not null, default false; true makes it a cross-sell campaign |
| activated\_at, closed\_at | timestamptz | null; set by the server when the status changes; activated\_at is when employees first see the leads |

### campaign\_leads

| Column | Type | Rules |
| --- | --- | --- |
| campaign\_id | uuid | FK campaigns, not null |
| lead\_id | uuid | FK leads, not null |
| branch\_id | uuid | FK branches, not null; copy of the lead's branch for fast branch queries |
| assigned\_to\_branch\_at | timestamptz | not null, default now(); when the lead was assigned to its branch in this campaign; never changed |
| status | varchar(10) | not null, default available; check in (available, locked, completed) |
| locked\_by | uuid | FK users, null; the employee who picked the lead (changed by a manager's reassignment) |
| locked\_at, completed\_at | timestamptz | null; locked\_at is when the employee picked the lead (the pickup date for KPIs), set once on pick |
| is\_open | boolean | not null, default false; true only while the campaign is active and the lead is not completed |
| version | integer | not null, default 0; optimistic lock for picking |

Constraints: unique (campaign\_id, lead\_id); uq\_campaign\_leads\_one\_open\_per\_lead: unique (lead\_id) where is\_open. Activating a campaign sets is\_open on all its leads and fails with 409 listing the conflicting leads if any is open elsewhere; closing a campaign or completing a lead clears is\_open. This is how the one-active-campaign rule is enforced in the database.

### campaign\_quota\_overrides

A pick quota is normally computed from live data and never stored (section 3). This table holds only a Branch Manager's override of the quota for one employee in one campaign.

| Column | Type | Rules |
| --- | --- | --- |
| campaign\_id | uuid | FK campaigns, not null |
| employee\_id | uuid | FK users, not null |
| quota | integer | not null; check >= 0; replaces the computed quota for this employee in this campaign |
| reason | varchar(255) | not null |

BaseMixin applies; created\_by is the Branch Manager who set the override. Constraint: unique (campaign\_id, employee\_id). No column counts picks: the picked count is the number of campaign\_leads rows of the campaign whose locked\_by is the employee.

### visits

| Column | Type | Rules |
| --- | --- | --- |
| campaign\_lead\_id | uuid | FK campaign\_leads, not null, unique; one visit per lead per campaign, updated in place |
| employee\_id | uuid | FK users, not null; who performed the visit |
| visit\_date | date | not null; typed by the employee, not in the future |
| visit\_count | smallint | not null, default 1; raised each time a repeat visit updates the record |
| last\_visited\_at | timestamptz | not null; server time of the latest visit update; the first visit time is created\_at |
| result | varchar(20) | not null, default pending; check in (pending, interested, not\_interested, no\_response); a copy of the latest attempt's result |
| description, additional\_info | text | null |

### visit\_attempts

One row per visit made to a lead in a campaign. Rows are never edited or deleted. The visits row above is the summary of the latest attempt: its result, description and visit\_date always equal the latest attempt's, and visit\_count and last\_visited\_at change in the same transaction. The first attempt's created\_at equals visits.created\_at.

| Column | Type | Rules |
| --- | --- | --- |
| visit\_id | uuid | FK visits, not null |
| attempt\_no | smallint | not null; 1 for the first visit |
| employee\_id | uuid | FK users, not null; who made this visit |
| visit\_date | date | not null; typed by the employee, not in the future |
| result | varchar(20) | not null; same values as visits.result |
| description, additional\_info | text | null |

BaseMixin applies, and created\_at is the server time of the attempt, the KPI timestamp of that visit. Constraint: unique (visit\_id, attempt\_no).

### product\_sales

A sale is a claim until approved. It belongs to the lead until approval and also records the customer once one exists.

| Column | Type | Rules |
| --- | --- | --- |
| lead\_id | uuid | FK leads, not null, indexed |
| customer\_id | uuid | FK customers, null; set when the sale targets an existing customer, or at first approval |
| source\_type | varchar(15) | not null; check in (visit, retention\_task, direct) |
| visit\_id | uuid | FK visits, null |
| retention\_task\_id | uuid | FK retention\_tasks, null |
| banking\_product\_id | uuid | FK banking\_products, not null |
| employee\_id | uuid | FK users, not null; who registered the sale |
| account\_number | varchar(100) | not null; the account or other bank reference typed by the employee |
| proof\_text | text | null while draft; at least 5 characters and required to submit; written by the employee as evidence for the Supervisor |
| description | text | null |
| status | varchar(10) | not null, default draft; check in (draft, submitted, approved, rejected, withdrawn) |
| registered\_at | timestamptz | not null, default now(); server time the sale was really registered; never changed |
| submitted\_at | timestamptz | null; the first submission, set once |
| last\_submitted\_at | timestamptz | null; the latest submission or resubmission |
| verified\_by, verified\_at | uuid, timestamptz | null; the latest decision; every decision is also in the audit log with its time |
| rejection\_reason | varchar(500) | null; required when status is rejected |
| resubmit\_count | smallint | not null, default 0 |
| customer\_product\_id | uuid | FK customer\_products, null; set on approval |

Constraints and indexes:

- ck\_sales\_anchor: source\_type visit requires visit\_id and no retention\_task\_id; retention\_task requires retention\_task\_id and no visit\_id; direct requires neither.
- uq\_sales\_one\_per\_lead\_product: unique (lead\_id, banking\_product\_id) where status is not withdrawn. One live sale per product per lead, across all campaigns.
- Supervisor queue: (status, submitted\_at). Others: (employee\_id, status), (customer\_id), (visit\_id).
- The service must check that lead\_id equals the lead of the visit's campaign lead; a plain foreign key cannot.
- ck\_sales\_proof: a sale in status submitted, approved or rejected must have a proof\_text of at least 5 characters; the service also requires it when a draft is submitted.

### customers

BaseMixin only. Customers are never deleted. The identity fields belong to the customer and can be corrected only by a Supervisor or the branch's Branch Manager, audited.

| Column | Type | Rules |
| --- | --- | --- |
| lead\_id | uuid | FK leads, not null, unique; one customer per lead; the imported lead data stays untouched |
| branch\_id | uuid | FK branches, not null; the lead's branch at conversion |
| customer\_since | date | not null; the approval date in the business timezone |
| acquired\_by | uuid | FK users, not null; the employee of the first approved sale |
| first\_sale\_id | uuid | FK product\_sales, not null |
| first\_name, last\_name | varchar(100) | not null; entered by the employee, verified by the Supervisor; may differ from the lead |
| phone | varchar(20) | not null; a mobile or landline number |
| address | text | not null |
| city\_id | uuid | FK cities, not null; the customer's own city |
| national\_code | varchar(10) | null; checksum validated |
| converted\_at | timestamptz | not null; server time of the first approval (a KPI date); never changed |
| customer\_code | varchar(50) | not null, unique; the customer's code in the bank's system, typed by the employee and verified by the Supervisor |

Indexes: unique (customer\_code), (branch\_id, customer\_since), (acquired\_by), (phone); trigram GIN on first\_name plus last\_name.

### customer\_drafts

The customer's own details as the employee entered them, before any approval. One row per lead; the customers row copies it at the first approval (section 3). BaseMixin, no soft delete.

| Column | Type | Rules |
| --- | --- | --- |
| lead\_id | uuid | FK leads, not null, unique |
| first\_name, last\_name | varchar(100) | not null; pre-filled from the lead |
| phone | varchar(20) | not null; a mobile or landline number |
| address | text | not null; pre-filled from the lead |
| city\_id | uuid | FK cities, not null |
| national\_code | varchar(10) | null; checksum validated |
| entered\_by | uuid | FK users, not null; the employee who last edited it |
| converted\_at | timestamptz | null; set when a customers row was created from it |
| customer\_code | varchar(50) | null while the draft is incomplete; required to submit the lead's first sale; must not equal any existing customer's code (409 customer\_code\_exists) |

### customer\_products

The products a customer actually holds. Rows exist only after approval.

| Column | Type | Rules |
| --- | --- | --- |
| customer\_id | uuid | FK customers, not null |
| banking\_product\_id | uuid | FK banking\_products, not null |
| account\_number | varchar(100) | not null; copied from the approved sale |
| started\_at | date | not null; the approval date |
| source\_sale\_id | uuid | FK product\_sales, not null, unique |

Constraint: unique (customer\_id, banking\_product\_id), so a customer never holds the same product twice. Corrections after the fact are Supervisor-only and audited.

### retention\_schedules

| Column | Type | Rules |
| --- | --- | --- |
| label | varchar(100) | not null |
| days\_after\_conversion | integer | not null; check > 0; unique among active schedules |
| requires\_approval | boolean | not null, default false |
| is\_active | boolean | not null, default true |

### retention\_tasks

| Column | Type | Rules |
| --- | --- | --- |
| customer\_id | uuid | FK customers, not null |
| retention\_schedule\_id | uuid | FK retention\_schedules, not null |
| assigned\_to | uuid | FK users, not null; starts as customers.acquired\_by; a manager may reassign |
| due\_date | date | not null; customer\_since plus the schedule's days |
| status | varchar(20) | not null; check in (pending\_approval, open, completed, cancelled) |
| approved\_by, approved\_at | uuid, timestamptz | null; set when a Supervisor publishes a task whose schedule requires approval |
| visited\_at, completed\_at | timestamptz | null |
| result, description | varchar(30), text | null; result values are defined in the retention spec |

Constraint: unique (customer\_id, retention\_schedule\_id). Index (assigned\_to, status, due\_date). Tasks are created as open, or as pending\_approval when the schedule requires approval, and completed tasks are the archive.

### score\_transactions

One ledger for every scoring source; it replaces separate employee and retention score tables.

| Column | Type | Rules |
| --- | --- | --- |
| employee\_id | uuid | FK users, not null |
| source\_type | varchar(20) | not null; check in (product\_sale, retention\_task) |
| source\_id | uuid | not null |
| points | integer | not null; negative values are reserved for reversals |
| occurred\_at | timestamptz | not null |
| note | varchar(255) | null |

Constraint: unique (source\_type, source\_id), so a source can never be scored twice. Index (employee\_id, occurred\_at). A score belongs to a league by date: a league includes the entries whose occurred\_at falls in its period, the Marketing League reads source\_type product\_sale and the Retention League reads retention\_task. Ledger rows are append-only, like audit rows.

### Event timestamps for KPIs

Every action that can feed a KPI gets a timestamp set by the server, never accepted from a client. All are timestamptz in UTC; reports group by day in the business timezone and use a Jalali calendar table for Persian periods. Timestamps that mark a first event are never overwritten; the latest-event ones are overwritten, and every earlier value stays in the audit log with its time.

| Event | Column | Set when |
| --- | --- | --- |
| Lead assigned to a branch for a campaign | campaign\_leads.assigned\_to\_branch\_at | The lead is added to the campaign |
| Campaign opened to employees | campaigns.activated\_at | The campaign is activated |
| Lead picked by an employee | campaign\_leads.locked\_at | The employee picks it; a manager's reassignment does not change it |
| First visit recorded | visits.created\_at | The first time a visit is saved for the lead and campaign |
| Latest visit | visits.last\_visited\_at and visit\_count | Every update from a repeat visit |
| Visit date as reported | visits.visit\_date | Typed by the employee; the only date here that comes from the client |
| Sale registered | product\_sales.registered\_at | The sale row is created (the real registration time) |
| Sale first submitted | product\_sales.submitted\_at | First submission |
| Sale last submitted | product\_sales.last\_submitted\_at | Each resubmission |
| Sale verified | product\_sales.verified\_at | Each approval or rejection (latest) |
| Customer created | customers.converted\_at and customer\_since | First approval |

KPIs these dates support:

- Assignment to pickup: locked\_at minus assigned\_to\_branch\_at (or minus activated\_at, whichever is later).
- Pickup to first visit: visits.created\_at minus locked\_at.
- First visit to sale registration: registered\_at minus the visit's created\_at.
- Registration to verification: verified\_at minus registered\_at; resubmissions: resubmit\_count.
- Assignment to conversion: customers.converted\_at minus assigned\_to\_branch\_at.
- Picks against quota per employee: the computed quota and the picked count taken from campaign\_leads.

## 5. Business rules and invariants

Each rule below is written so it can become a test. The last column says where it is enforced; rules enforced only in the service need an integration test, while database rules also need a test that the constraint rejects bad data.

| Id | Rule | Enforced by |
| --- | --- | --- |
| R1 | A lead belongs to at most one active campaign at a time | Database (unique on lead\_id where is\_open) and the activation check |
| R2 | One visit per lead per campaign; a repeat visit adds a row to visit\_attempts and refreshes the summary on the same record, so earlier visits are kept | Database (unique campaign\_lead\_id) |
| R3 | A lead has at most one live sale per product, across all campaigns | Database (partial unique on lead\_id and product) |
| R4 | A customer holds each product at most once | Database (unique on customer\_id and product) |
| R5 | A customers row exists only after an approved sale, and first\_sale\_id points to that sale | Conversion transaction and foreign key |
| R6 | Only the conversion transaction creates customers and customer\_products or sets leads.is\_customer; no other endpoint writes them | Service |
| R7 | A score exists only for an approved sale, and a source is scored at most once | Database (unique source) and service |
| R8 | Rejected and withdrawn sales never score and never create customer\_products | Service |
| R9 | A rejected sale goes back to the employee who registered it; only that employee can edit, resubmit or withdraw it | Service |
| R10 | Conversion never changes the lead's personal data; it only sets is\_customer | Service |
| R11 | Retention tasks are generated only at a customer's first approval, one per active schedule | Database (unique customer and schedule) and service |
| R12 | A retention task starts assigned to acquired\_by; a Branch Manager can reassign it to an employee of the same branch | Service |
| R13 | Lead selection for a campaign skips customers unless the campaign has include\_customers set by a Supervisor | Service |
| R14 | An employee can pick only leads of their own branch, and only while their picked count is below their quota (R20); a picked lead is locked to that employee until the work is completed; a Branch Manager can reassign it | Service and version check |
| R15 | A sale can be registered only by the employee who owns the visit, the assignee of the retention task, or an employee of the customer's branch for a direct sale | Service |
| R16 | Only a Supervisor approves or rejects a sale, and rejection needs a reason | Service |
| R17 | A lead keeps its branch; moving a lead to another branch is not supported in this phase | Service |
| R18 | Leads, customers, customer products, sales and visits are never physically deleted; only archive, soft delete and status changes exist | Database privileges and service |
| R19 | A customer's bank code, name, address, phone and city belong to the customer and may differ from the lead; the employee enters them in customer\_drafts, the Supervisor verifies them, and they reach the customers row only at approval | Service |
| R20 | An employee's quota in a campaign is computed by the backend when needed, never stored or hard-coded, as the branch's leads divided by its active employees, rounded up, unless a Branch Manager override exists; a pick beyond the quota is refused with quota\_reached; a Branch Manager can override a quota or reassign beyond it; the picked count is always counted from campaign\_leads, never stored | Service, with an advisory lock per campaign and employee |
| R21 | A sale cannot be submitted without a proof\_text of at least 5 characters, and a lead's first sale cannot be submitted without the customer details, including the bank customer code | Database check on submitted sales, and service |
| R22 | KPI timestamps are set by the server and never taken from a client; the first-event ones (assigned\_to\_branch\_at, locked\_at, registered\_at, the visit's created\_at, converted\_at) are never overwritten | Service and database defaults |
| R23 | A branch code is 2 to 10 digits and unique among non-deleted branches (Phase 1 section 4) | Database check and unique index |
| R24 | A repeat visit never overwrites an earlier one: every visit is a row in visit\_attempts, and the visit record only summarizes the latest | Database (unique visit and attempt number) and service |
| R25 | A customer\_code is unique and is required for a lead's first sale; a sale for an existing customer needs no customer details, only the product, account number and proof | Database (unique) and service |

## 6. Finding a customer's relations

A customer's own identity, branch and city are columns of the customer and the original lead is one join away; products, visits and retention tasks are one-to-many, so they are loaded separately rather than in one wide join.

### Join map

| To find | Path |
| --- | --- |
| Branch | customers.branch\_id (the branch at conversion; equals leads.branch\_id because leads never move) |
| City | customers.city\_id, then cities (the customer's own city; the imported city is leads.city\_id) |
| Name, phone, address, national code | Columns of customers |
| Original imported data (name, mobile, occupation, referrer) | customers.lead\_id, then leads, then occupations |
| Customer details before approval | customer\_drafts.lead\_id |
| Products held | customer\_products.customer\_id |
| Pending or rejected products, with their proof | product\_sales where customer\_id or lead\_id matches and status is draft, submitted or rejected |
| Visits | leads, then campaign\_leads.lead\_id, then visits.campaign\_lead\_id, then campaigns |
| Retention tasks | retention\_tasks.customer\_id |
| Who acquired the customer | customers.acquired\_by, then users |
| Scores earned | score\_transactions where source\_id is a product\_sales or retention\_tasks id of this customer |
| Bank customer code | customers.customer\_code (unique) |
| Visit history | visits, then visit\_attempts.visit\_id (one row per visit made) |

### Queries

Customer header, one row:

```sql
SELECT c.id, c.customer_code, c.customer_since, c.converted_at,
       c.first_name, c.last_name, c.phone, c.address,
       b.code AS branch_code, b.name AS branch, ci.name AS city,
       u.first_name || ' ' || u.last_name AS acquired_by
FROM customers c
JOIN branches b ON b.id  = c.branch_id
JOIN cities ci  ON ci.id = c.city_id
JOIN users u    ON u.id  = c.acquired_by
WHERE c.id = :customer_id;
```

Products held:

```sql
SELECT p.name, cp.account_number, cp.started_at
FROM customer_products cp
JOIN banking_products p ON p.id = cp.banking_product_id
WHERE cp.customer_id = :customer_id
ORDER BY cp.started_at;
```

Visits, with their campaign:

```sql
SELECT cmp.title, v.visit_date, v.result, v.description,
       e.first_name || ' ' || e.last_name AS employee
FROM customers c
JOIN campaign_leads cl ON cl.lead_id = c.lead_id
JOIN campaigns cmp     ON cmp.id = cl.campaign_id
JOIN visits v          ON v.campaign_lead_id = cl.id
JOIN users e           ON e.id = v.employee_id
WHERE c.id = :customer_id
ORDER BY v.visit_date;
```

Customers of a branch, or holding a product (every row is already verified, so no status filter is needed):

```sql
SELECT c.id, c.first_name, c.last_name, c.phone FROM customers c
WHERE c.branch_id = :branch_id;

SELECT DISTINCT c.id FROM customers c
JOIN customer_products cp ON cp.customer_id = c.id
WHERE cp.banking_product_id = :product_id;
```

### Indexes for these queries

```sql
CREATE INDEX ix_customers_branch        ON customers (branch_id, customer_since);
CREATE INDEX ix_customers_phone         ON customers (phone);
CREATE INDEX ix_customers_name_trgm     ON customers USING gin ((first_name || ' ' || last_name) gin_trgm_ops);
CREATE INDEX ix_customer_products_cust  ON customer_products (customer_id);
CREATE INDEX ix_customer_products_prod  ON customer_products (banking_product_id);
CREATE INDEX ix_campaign_leads_lead     ON campaign_leads (lead_id);
CREATE INDEX ix_campaign_leads_pick     ON campaign_leads (campaign_id, branch_id, status);
CREATE INDEX ix_campaign_leads_picker   ON campaign_leads (campaign_id, locked_by);
CREATE INDEX ix_retention_customer      ON retention_tasks (customer_id);
CREATE INDEX ix_sales_lead_status       ON product_sales (lead_id, status);
```

### Read model for the API

- GET /customers filters by branch\_id, city\_id, product\_id and customer\_since range, and searches name and phone with q, scoped by role (a Branch Manager sees only their branch).
- GET /customers/{id} returns one nested object: header, products held, pending sales, visits and retention tasks. Load the one-to-many parts with SQLAlchemy selectinload, which issues one extra query per collection, instead of a single join that multiplies products by visits.
- For dashboards, create a database view v\_customers that pre-joins the header columns, so reports do not repeat the join.

## 7. Lead import, deduplication and archiving

Leads arrive in large batches at set periods, so the import must recognise people already in the system, never overwrite what employees and customers rely on, and let old junk be archived instead of deleted.

### Engine

The same rules as Phase 1 section 9 apply: .xlsx only, the original file stored, an import\_logs row created first, row errors in import\_row\_errors, valid rows saved even when others fail, and an .xlsx error report. Differences for leads:

- Batches can reach tens of thousands of rows, so leads import runs as a background job: the upload returns 202 with the import id and the client polls GET /imports/{id} until the status is completed, completed\_with\_errors or failed. Limits: 50 MB and 100,000 rows.
- Rows are processed in chunks of 500: validate in Python, load existing leads for the chunk with one query (mobile = ANY), then insert and update in bulk. A failing row is reported and does not stop the chunk.
- Only a Supervisor can import leads.

### Columns

| Header | Required | Rule |
| --- | --- | --- |
| first\_name, last\_name | Yes | 2 to 100 characters, normalized text |
| mobile | Yes | Normalized mobile (Phase 1 section 5) |
| branch\_code | Yes | An active branch code, digits only; compared by numeric value, so Excel cells that lost leading zeros still match |
| city | Yes | Matches a city by normalized name |
| national\_code | No | Checksum validated |
| occupation | No | Matches an occupation by normalized name |
| address, referrer, additional\_info | No | Free text with the usual length limits |

### Matching and deduplication

1. The match key is the normalized mobile number. If a non-deleted lead has it, the row refers to that existing lead.
2. If there is no mobile match and national\_code is present, a lead with the same national code is the match.
3. If the mobile matches one lead and the national code matches a different one, the row fails with ambiguous\_match.
4. A new person creates a lead with first\_import\_id and last\_import\_id set to this import.
5. An existing lead is never overwritten. In the default mode fill\_missing, only empty fields (address, occupation, referrer, national\_code, additional\_info) are filled; last\_import\_id is updated. If a field was filled the row counts as updated, otherwise unchanged. In create\_only mode an existing lead is skipped.
6. branch\_id and city\_id of an existing lead are never changed. A different branch\_code fails with branch\_mismatch (rule R17).
7. An existing lead that is already a customer keeps is\_customer and all customer data. The row is processed as above and counted in existing\_customers, so the Supervisor sees how many customers were in the file.
8. An archived existing lead is restored (archived\_at cleared) because a new batch signals it is relevant again; this counts as updated and adds the warning archived\_lead\_restored.
9. A soft-deleted lead with the same mobile fails with lead\_deleted.
10. A mobile number that appears again later in the same file fails with duplicate\_in\_file; the first row wins.

### Row errors and warnings

| Code | Kind | Meaning |
| --- | --- | --- |
| missing\_required | Error | A required cell is empty |
| invalid\_mobile, invalid\_national\_code | Error | Format or checksum failed |
| unknown\_branch, inactive\_branch | Error | Branch code not found, or branch inactive |
| unknown\_city | Error | City not found |
| branch\_mismatch | Error | Existing lead belongs to another branch |
| ambiguous\_match | Error | Mobile and national code point at different leads |
| duplicate\_in\_file | Error | Same mobile earlier in the file |
| lead\_deleted | Error | A deleted lead holds this mobile |
| unknown\_occupation | Warning | The lead is imported with no occupation |
| archived\_lead\_restored | Warning | An archived lead came back |

The result reports created, updated, unchanged, skipped, failed, warnings and existing\_customers.

### Archiving

- Archiving hides a lead from campaign selection, employee lists and default lead lists, but keeps every row and relation. Archived leads remain searchable with include\_archived.
- A Supervisor archives leads by filter (for example, never part of a campaign and last imported more than 12 months ago). The same rule runs as a command, cli.py archive-stale-leads, which is a dry run unless --apply is given; the age comes from LEAD\_ARCHIVE\_AFTER\_MONTHS.
- A lead that is a customer cannot be archived: 409 lead\_is\_customer.
- Leads are never physically deleted (rule R18).

### Scale

- Partial indexes on archived\_at is null keep lists fast as junk grows; big lists use keyset pagination (where id is greater than the last id) instead of OFFSET.
- Partitioning is not needed below roughly 20 million leads; if it comes, partition by import period, not by hash.

## 8. Assumptions and open questions

### Open questions

| Id | Question | Recommendation |
| --- | --- | --- |
| Q1 | Which entry points for adding a product to an existing customer ship first: A cross-sell campaign, B retention visit, C direct? | A and B first, because they reuse the existing employee flows. Add C only if sales outside campaigns and retention are needed. The schema already supports all three. |
| Q2 | Does an approved cross-sell sale earn the product's normal score? | Yes, since only verified sales score and the rule is the same for every approved sale. |
| Q3 | Can an approved sale be reversed later (wrong account, bank cancellation)? | Add a revoked status, mark the customer product closed, and write a negative score\_transactions row. Never delete. |
| Q4 | Can an employee register sales on a visit after its campaign has closed? | Yes for a fixed window after closing, for example 30 days, so late account openings are not lost. |
| Q5 | If a manager reassigns a lead after sales were registered, who gets the credit? | Each sale scores the employee who registered it; acquired\_by is the employee of the first approved sale. |
| Q6 | Should a lead ever move to another branch, for example when a customer relocates? | Not in this phase. If needed, add a lead branch history like the POS one. |
| Q7 | What are the retention visit result values and the Retention League scoring? | Defined in the retention and league spec. |
| Q8 | Should the quota cap an employee's total picks in a campaign, or only the leads picked and not yet finished? | Total picks, as in D14. Add a separate cap on open leads only if employees pick leads and leave them untouched. |
| Q9 | Besides the system time a sale was registered, do you also want the date the account was opened in the bank, typed by the employee? | Add an optional account\_opened\_on date to the sale; the system registration time stays the KPI date. |
| Q10 | Who may correct a customer's name, address or phone after conversion? | The Supervisor and the customer's Branch Manager, with every change audited. |
| Q11 | What happens to the leads of a branch that has no active employee when a campaign starts? | Report the branch at activation and let the Supervisor add an employee; do not move the leads to another branch (R17). |
| Q12 | Is the bank customer code always known when the employee registers a lead's first sale, and does it have a fixed format? | Treat it as required and validate only length and characters until the bank confirms the format. |
| Q13 | Who may withdraw or reassign a rejected sale when the employee who registered it has left or is unavailable (R9 allows only that employee)? | A Supervisor, and the Branch Manager for sales of their own branch, with the action audited. |

### Assumptions

| Id | Assumption |
| --- | --- |
| A1 | The bank's customer code is tracked on the customer (customer\_code); account numbers stay on each product. Both are typed by the employee and checked by the Supervisor against the bank system. |
| A2 | Every lead has a mobile number, and it identifies the person. Rows without one are not imported. |
| A3 | customer\_since is the approval date, and retention due dates count from it. |
| A4 | Re-importing an archived lead restores it. |
| A5 | A lead keeps its branch for life (R17). |
| A6 | Scores belong to a league by date range, so score rows carry no league id. |
| A7 | The product's score is copied into the ledger at approval, so later score changes do not rewrite history. |
| A8 | Lead import runs as a background job with polling, unlike the synchronous POS import, because of batch size. |
| A9 | Customers and their products are never archived or deleted. |
| A10 | A customer's phone can be a mobile or a landline number, so it is not validated as a mobile number. |
| A11 | Customer details are entered once per lead, with its first sale, pre-filled from the lead; later sales reuse them. |
| A12 | The first visit time is the visit row's created\_at, which equals the first attempt's; visit\_date is the date the employee reports. |
| A13 | Quotas are computed on demand from live data and count every pick in the campaign, finished or not. |
| A14 | Branch codes are compared by numeric value, while the stored text keeps leading zeros. |
