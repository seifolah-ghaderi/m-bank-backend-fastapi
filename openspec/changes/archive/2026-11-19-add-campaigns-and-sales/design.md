# Design

## Context

The existing FastAPI and PostgreSQL backend includes organization, staff authorization, POS, audit, and private notifications. This change uses [the v3 domain model](../../../docs/Bank%20Marketing%20CRM%20%E2%80%94%20v3-Leads%2C%20Customers%20and%20Sales%20Model%20.md) within the scope in [the proposal](proposal.md). The API supplies the data and actions for the client's Convert to Customer form.

## Goals / Non-Goals

- Use PostgreSQL constraints and request transactions for campaign reservations, assignment, and verification.
- Preserve original lead data, visit history, submitted verification evidence, and score attribution.
- Keep this increment within the existing backend and database. Release scope and deferrals are in the proposal.

## Decisions

### Data ownership and campaign lifecycle

Add catalog, lead, campaign, visit, sale, customer, retention and score models using the existing UUIDv7 and audit conventions. Keep lead home branch fixed. Reference existing branches by ID in manual entry. Preserve branch-code validation, POS imports and POS routes.

Give campaign memberships a reservation flag separate from their available, locked or completed work status. Use a partial unique index on lead ID where reserved and an unconditional unique index on campaign ID and lead ID. Reservation begins on Supervisor activation and ends on closure. Activation rechecks draft selections against current lead, branch and customer eligibility. Dates are business-date metadata and explicit Supervisor transitions drive availability. Open work can be completed after one recorded attempt, so a visit with proofs pending can finish without waiting for verification. Closure and work completion stop new visits and sales. Existing drafts and rejected sales can still finish the sales workflow.

Lock the campaign on state transitions, and coordinate activation, lead archival, completion, picks and visit writes through a documented order of campaign, lead, and membership locks as applicable. Lock lead IDs in a stable order when activation touches multiple leads. Translate reservation races to 409. Serialize pickup quota checks per campaign and employee with a transaction-level lock. Reassignments coordinate with the affected employees' quota locks in a stable order. Count picked and finished work from current assignment rows. Preserve the first pick timestamp and audit reassignment separately.

Use one visit summary per membership with append-only attempts, unique by visit and attempt number. Update the summary and append an attempt in one transaction. Keep the initial branch assignment, activation, pickup, visit, sale submission and approval timestamps available for later reporting. Use the configured business timezone and existing Jalali API types.

### API ownership and route contract

All routes here use the existing `/api/v1` prefix, pagination where applicable, and the shared error envelope. Enforce authorization in queries and mutations, including filters and related IDs.

| Resource | Contract |
| --- | --- |
| `/occupations`, `/banking-products`, `/retention-schedules` | Scoped list and Supervisor create/update, including activation controls. |
| `/leads`, `/leads/{id}` | Supervisor create, list and detail, with explicit archive and restore actions. |
| `/campaigns`, `/campaigns/{id}` | Create, list and view campaigns. Supervisor actions edit draft details and selections, activate and close. Branch views expose only permitted work. |
| `/campaigns/{id}/leads` and individual membership actions | List scoped work, pick, reassign, and complete. Record attempts under the membership. Capacity and per-employee override actions live under the campaign branch. |
| `/visits/{id}/sales-form` | Return current authorized visit context, prefilled customer details, applicable held products and the caller's visit drafts. |
| `/sales`, `/sales/{id}`, `/sales/submit` | Create a draft from an owned visit and save or update the shared customer draft through the form. List and view own claims, edit or withdraw eligible claims, and submit selected sales together. |
| `/verifications` and sale decision actions | Paginated Supervisor queue grouped by visit. Approve a single sale or an explicit set of reviewed sale IDs from one visit. Reject a submitted sale with a required reason. |
| `/customers`, `/customers/{id}` | Scoped Supervisor and Branch Manager registry, detail and contact corrections. Load related products, visits, sales and generated tasks through separate scoped queries. |

Customer and sale reads use distinct response schemas for the campaign queue, form, verification, and registry. The unpicked queue's cross-sell field shows held product names without account references. Employees get full form data only for assigned visits or the data needed to work their own sales. Proof and customer details stay in authorized business records. Audit state changes, actor and evidence version references while omitting raw proof, account references and unnecessary contact data from general audit entries and notifications.

### Verification and retention transaction

Maintain one editable customer draft per unconverted lead. On submission, capture an immutable profile revision and link each first-conversion claim to the reviewed version. Preserve proof and decision history with restricted access. The Supervisor verifies submitted data and sends corrections back through rejection, which makes the employee's next submission a new revision. Once a customer exists, subsequent submissions reference that customer. Pending first-conversion claims may continue when their reviewed profile matches the original converted profile. Conflicting claims require correction and resubmission against the verified customer.

For a decision, lock the lead before the target sales, then recheck statuses, product eligibility and reviewed profile. Enforce one customer per lead, unique customer code, one non-withdrawn claim per lead and product, one held product per customer and product, and one score per sale. Use one transaction for all selected claims. Use explicit sale IDs for the queue's approve-all action so a newly submitted sale is outside the reviewed batch. A 409 on one selected claim rolls back all approvals in that batch. Never credit the current lead assignee for someone else's sale.

At the first approval, create the customer, set the lead's conversion marker, and insert one task per active schedule. For a valid batch creating its first customer, decide the first sale by registration time and sale ID. Set the acquiring employee from that sale, and use the business date at approval for the conversion date and due-date offsets. The verified customer retains the first-sale link and approved profile independently of the lead. Create a held product and score for each approved sale and write decision audit and notification records in the same request transaction. Use a unique customer and schedule pair as a backstop for retention generation.

## Risks / Trade-offs

- A manual lead registry makes the feature usable while lead imports are deferred. It also limits initial campaign setup throughput.
- A reservation lasts for the entire active campaign. Supervisors must close completed campaigns before reusing their leads in another active campaign.
- Existing claim correction remains available after closure and reassignment. Authorization must key that action to the original sale author and current branch scope rather than current visit ownership.
- Task generation uses the schedules active at first approval. Schedule changes influence later customers, and no task is generated for older customers on a later cross-sell.

## Migration Plan

Add schema and constraints in dependency order using the migration owner, adding circular sale/customer/product foreign keys after the tables exist. Grant the runtime role the required table privileges and enforce append-only history for attempt, submission and score records. Apply on a clean database and on a database at the current POS migration head. Run the mixed-workflow tests before deployment. If deployment fails before business writes, the prior app can run against the additive schema. Once new business data exists, use a forward fix or restore a verified backup.
