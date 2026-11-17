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
| D3 | A separate, thin customers table; a row is created only when the first sale of a lead is approved. | A customer is always valid and verified; the hot table stays small; batch imports and lead archiving never touch customers |
| D4 | Products belong to customers, not leads. A held product is a customer\_products row, created only on approval. A lead owns no bank product; it has only sales that are waiting for or have failed verification. | Product owner decision: every relationship of a customer must be valid |
| D5 | Sales stay as history after approval or rejection. An approved sale points to the customer\_products row it created. | Audit and rejection history |
| D6 | Customers are excluded from acquisition campaigns by default. A Supervisor can include them explicitly (for a cross-sell campaign). | Product owner decision |
| D7 | Adding a product to an existing customer uses the same sale, verification and approval flow through any of three entry points: a cross-sell campaign visit, a retention-task visit, or directly on the customer. The schema supports all three; which ones ship first is open (question Q1). | Avoids a second verification process |
| D8 | Pipeline stage (opportunity, pending verification, and so on) is derived from visits and sales, not stored. Stored on the lead: only is\_customer. | A stored stage can drift out of sync |
| D9 | One score ledger (score\_transactions) holds every scoring source. Approval writes the entry in the same transaction. | Leagues and rankings read one table |
| D10 | Retention tasks are generated once, at conversion, counted from customer\_since. Later product approvals do not generate new ones. | Retention follows the customer, not each product |
| D11 | Leads are deduplicated at import by normalized mobile number, then national code. | Batch imports repeat people across periods |

## 2. Domain at a glance

&#91;embedded content: lead to customer flow · 9 tables, 1 approval step\]

Leads feed campaigns and visits, but a sale is only a claim until a Supervisor approves it. Approval creates the customer, the products it holds and the score in one step, and the lead row itself never changes.

## 3. Lifecycles and workflows

A sale moves from draft to submitted to approved or rejected, and the first approval of a lead converts it into a customer in one database transaction.

### Sale lifecycle

| From | Action | To | Who |
| --- | --- | --- | --- |
| (new) | Register a product on a visit, with account number | draft | The employee who owns the visit |
| draft | Submit (one sale, or all drafts of a visit at once) | submitted | Same employee |
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
4. If the lead has no customers row: create it (lead\_id, branch\_id copied from the lead, customer\_since as today in the business timezone, acquired\_by as the sale's employee, first\_sale\_id), set leads.is\_customer to true, and generate retention tasks from every active retention schedule, due on customer\_since plus the schedule's days, assigned to acquired\_by.
5. Create the customer\_products row (customer, product, account number, started\_at, source\_sale\_id) and store its id on the sale.
6. Insert one score\_transactions row with the employee and the points copied from the product's current score value, so later changes to a product's score do not alter history.
7. Write the audit rows and send verification\_approved to the employee.

When the customer already exists (a later product), steps 1 to 3, 5, 6 and 7 run; no customer row and no retention tasks are created.

### Rejection loop

- Reject stores rejection\_reason and returns the sale to the employee with the notification verification\_rejected.
- The employee corrects the product, account number or description and resubmits. resubmit\_count increases by one and the earlier rejection stays in the audit log.
- A lead whose every sale is rejected or withdrawn stays a lead.

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

This phase adds 10 tables to the Phase 1 schema. BaseMixin and SoftDeleteMixin mean the same as in Phase 1 section 4 (id, created\_at, updated\_at, created\_by, updated\_by; deleted\_at, deleted\_by). Master tables occupations (name, is\_active) and banking\_products (name, code, score\_value, is\_active) are referenced here and defined with the master data. The import\_logs table from Phase 1 gains import\_type leads.

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

### campaign\_leads

| Column | Type | Rules |
| --- | --- | --- |
| campaign\_id | uuid | FK campaigns, not null |
| lead\_id | uuid | FK leads, not null |
| branch\_id | uuid | FK branches, not null; copy of the lead's branch for fast branch queries |
| status | varchar(10) | not null, default available; check in (available, locked, completed) |
| locked\_by | uuid | FK users, null; the employee who picked the lead (changed by a manager's reassignment) |
| locked\_at, completed\_at | timestamptz | null |
| is\_open | boolean | not null, default false; true only while the campaign is active and the lead is not completed |
| version | integer | not null, default 0; optimistic lock for picking |

Constraints: unique (campaign\_id, lead\_id); uq\_campaign\_leads\_one\_open\_per\_lead: unique (lead\_id) where is\_open. Activating a campaign sets is\_open on all its leads and fails with 409 listing the conflicting leads if any is open elsewhere; closing a campaign or completing a lead clears is\_open. This is how the one-active-campaign rule is enforced in the database.

### visits

| Column | Type | Rules |
| --- | --- | --- |
| campaign\_lead\_id | uuid | FK campaign\_leads, not null, unique; one visit per lead per campaign, updated in place |
| employee\_id | uuid | FK users, not null; who performed the visit |
| visit\_date | date | not null |
| result | varchar(20) | not null, default pending; check in (pending, interested, not\_interested, no\_response) |
| description, additional\_info | text | null |

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
| description | text | null |
| status | varchar(10) | not null, default draft; check in (draft, submitted, approved, rejected, withdrawn) |
| submitted\_at | timestamptz | null |
| verified\_by, verified\_at | uuid, timestamptz | null |
| rejection\_reason | varchar(500) | null; required when status is rejected |
| resubmit\_count | smallint | not null, default 0 |
| customer\_product\_id | uuid | FK customer\_products, null; set on approval |

Constraints and indexes:

- ck\_sales\_anchor: source\_type visit requires visit\_id and no retention\_task\_id; retention\_task requires retention\_task\_id and no visit\_id; direct requires neither.
- uq\_sales\_one\_per\_lead\_product: unique (lead\_id, banking\_product\_id) where status is not withdrawn. One live sale per product per lead, across all campaigns.
- Supervisor queue: (status, submitted\_at). Others: (employee\_id, status), (customer\_id), (visit\_id).
- The service must check that lead\_id equals the lead of the visit's campaign lead; a plain foreign key cannot.

### customers

BaseMixin only. Customers are never deleted.

| Column | Type | Rules |
| --- | --- | --- |
| lead\_id | uuid | FK leads, not null, unique; one customer per lead; personal data stays on the lead |
| branch\_id | uuid | FK branches, not null; the lead's branch at conversion |
| customer\_since | date | not null; the approval date in the business timezone |
| acquired\_by | uuid | FK users, not null; the employee of the first approved sale |
| first\_sale\_id | uuid | FK product\_sales, not null |

Indexes: (branch\_id, customer\_since), (acquired\_by).

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

## 5. Business rules and invariants

Each rule below is written so it can become a test. The last column says where it is enforced; rules enforced only in the service need an integration test, while database rules also need a test that the constraint rejects bad data.

| Id | Rule | Enforced by |
| --- | --- | --- |
| R1 | A lead belongs to at most one active campaign at a time | Database (unique on lead\_id where is\_open) and the activation check |
| R2 | One visit per lead per campaign; a repeat visit updates the same record | Database (unique campaign\_lead\_id) |
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
| R14 | An employee can pick only leads of their own branch; a picked lead is locked to that employee until the work is completed; a Branch Manager can reassign it | Service and version check |
| R15 | A sale can be registered only by the employee who owns the visit, the assignee of the retention task, or an employee of the customer's branch for a direct sale | Service |
| R16 | Only a Supervisor approves or rejects a sale, and rejection needs a reason | Service |
| R17 | A lead keeps its branch; moving a lead to another branch is not supported in this phase | Service |
| R18 | Leads, customers, customer products, sales and visits are never physically deleted; only archive, soft delete and status changes exist | Database privileges and service |

## 6. Finding a customer's relations

A customer's identity, branch and city come from one-to-one joins; products, visits and retention tasks are one-to-many, so they are loaded separately rather than in one wide join.

### Join map

| To find | Path |
| --- | --- |
| Branch | customers.branch\_id (the branch at conversion; equals leads.branch\_id because leads never move) |
| City | customers.lead\_id, then leads.city\_id, then cities |
| Name, mobile, national code, occupation | customers.lead\_id, then leads, then occupations |
| Products held | customer\_products.customer\_id |
| Pending or rejected products | product\_sales where customer\_id or lead\_id matches and status is draft, submitted or rejected |
| Visits | leads, then campaign\_leads.lead\_id, then visits.campaign\_lead\_id, then campaigns |
| Retention tasks | retention\_tasks.customer\_id |
| Who acquired the customer | customers.acquired\_by, then users |
| Scores earned | score\_transactions where source\_id is a product\_sales or retention\_tasks id of this customer |

### Queries

Customer header, one row:

```sql
SELECT c.id, c.customer_since, l.first_name, l.last_name, l.mobile,
       b.name AS branch, ci.name AS city, o.name AS occupation,
       u.first_name || ' ' || u.last_name AS acquired_by
FROM customers c
JOIN leads l       ON l.id  = c.lead_id
JOIN branches b    ON b.id  = c.branch_id
JOIN cities ci     ON ci.id = l.city_id
LEFT JOIN occupations o ON o.id = l.occupation_id
JOIN users u       ON u.id  = c.acquired_by
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
SELECT c.id, l.first_name, l.last_name FROM customers c JOIN leads l ON l.id = c.lead_id
WHERE c.branch_id = :branch_id;

SELECT DISTINCT c.id FROM customers c
JOIN customer_products cp ON cp.customer_id = c.id
WHERE cp.banking_product_id = :product_id;
```

### Indexes for these queries

```sql
CREATE INDEX ix_customers_branch        ON customers (branch_id, customer_since);
CREATE INDEX ix_customer_products_cust  ON customer_products (customer_id);
CREATE INDEX ix_customer_products_prod  ON customer_products (banking_product_id);
CREATE INDEX ix_campaign_leads_lead     ON campaign_leads (lead_id);
CREATE INDEX ix_retention_customer      ON retention_tasks (customer_id);
CREATE INDEX ix_sales_lead_status       ON product_sales (lead_id, status);
```

### Read model for the API

- GET /customers filters by branch\_id, city\_id, product\_id and customer\_since range, scoped by role (a Branch Manager sees only their branch).
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
| branch\_code | Yes | An active branch code |
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

### Assumptions

| Id | Assumption |
| --- | --- |
| A1 | The bank's own customer number is not tracked; the account number on each sale is the only bank reference. If the bank can supply a customer number, add customers.bank\_customer\_number. |
| A2 | Every lead has a mobile number, and it identifies the person. Rows without one are not imported. |
| A3 | customer\_since is the approval date, and retention due dates count from it. |
| A4 | Re-importing an archived lead restores it. |
| A5 | A lead keeps its branch for life (R17). |
| A6 | Scores belong to a league by date range, so score rows carry no league id. |
| A7 | The product's score is copied into the ledger at approval, so later score changes do not rewrite history. |
| A8 | Lead import runs as a background job with polling, unlike the synchronous POS import, because of batch size. |
| A9 | Customers and their products are never archived or deleted. |
