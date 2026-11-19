# sales-verification Specification

## Purpose

Capture bank product claims from campaign visits and verify them before creating CRM customer and product records.

## Requirements

### Requirement: Visit conversion form
The current assignee SHALL be able to open a sale form from a recorded visit on locked work in an active campaign. Before conversion, the form SHALL prefill name, phone, address, city and optional national code from the lead or saved customer draft. For a verified customer it SHALL show the verified profile and held products, and accept only new sale details.

#### Scenario: First customer registration
- **WHEN** an employee opens the form for an unconverted lead with no saved draft
- **THEN** the response supplies available lead details and leaves the bank customer code for the employee to enter.

#### Scenario: Unassigned or foreign visit
- **WHEN** an employee opens the form for a visit they do not currently own
- **THEN** the request returns 404 and reveals no customer or sale data.

### Requirement: Draft and submitted sales
The employee SHALL be able to save one or more sale claims from a visit, each with a product and account reference. Submission SHALL require proof of at least five non-whitespace characters after trimming and, for first conversion, a complete profile with a bank customer code. Submission SHALL bind the submitted profile version to each affected sale. A batch submission SHALL succeed or fail as a unit.

#### Scenario: Missing proof on one selected claim
- **WHEN** the employee submits several drafts together and one lacks sufficient proof
- **THEN** validation identifies the invalid claim and all selected sales keep their previous statuses.

#### Scenario: Duplicate product claim
- **WHEN** an employee registers the same product for a lead with a non-withdrawn claim for that product
- **THEN** the request returns 409 and no duplicate claim is created.

### Requirement: Sale ownership and corrections
Employees SHALL view and edit their own drafts and rejected sales, resubmit rejected sales, and withdraw their own draft or rejected sales. Submission and resubmission SHALL preserve history. Closure or completion SHALL stop new registration and allow existing claims to continue through correction and verification. Same-branch reassignment SHALL preserve the original sale author.

#### Scenario: Supervisor rejects a submitted claim
- **WHEN** the Supervisor rejects a sale with a reason
- **THEN** the sale returns to its author for correction or withdrawal and generates no held product or score.

#### Scenario: Original author corrects a claim after reassignment
- **WHEN** an employee edits their rejected sale after its lead has been reassigned within their branch
- **THEN** the employee can correct that sale while other visit records and the new assignee's sales remain inaccessible to them.

### Requirement: Supervisor verification
Only Supervisors SHALL access the submitted-sale queue and approve or reject submitted sales. The queue SHALL group submitted sales by visit and show their proofs and submitted profile versions. A Supervisor SHALL be able to approve one sale or all submitted sales shown for the visit. Approval of the selected batch SHALL be atomic. Approved and withdrawn sales SHALL be final.

#### Scenario: Approve one sale from a visit
- **WHEN** a Supervisor approves one of several submitted sales for an unconverted lead
- **THEN** the system creates the customer, records only that sale's held product and score, and leaves the other submitted sales pending.

#### Scenario: Approve all sales shown for a visit
- **WHEN** a Supervisor confirms all submitted sales shown for the visit and all are still eligible
- **THEN** each selected sale is approved together and any later submissions require a separate decision.

#### Scenario: Selected sale conflict
- **WHEN** a member of an approval batch has changed status, uses a conflicting customer profile or fails a uniqueness check
- **THEN** the batch returns 409 and creates no new approvals or customer-side effects.

### Requirement: Atomic conversion and scoring
Approval SHALL atomically commit the sale decision, verified customer if needed, a held product, one score entry, audit and decision notification, and first-conversion retention tasks if applicable. Each acquired product SHALL score its approval-time value for the registered employee, including cross-sell. No score SHALL persist for a rejected, withdrawn or rolled-back sale.

#### Scenario: Concurrent first approvals
- **WHEN** two valid claims for different products on the same lead are approved concurrently
- **THEN** there is exactly one verified CRM customer, one task per eligible schedule and one product and score per approved claim.

#### Scenario: Approval after a conflicting profile was verified
- **WHEN** a pending claim uses different customer details from the profile established by another approval for the same lead
- **THEN** approval returns 409 and leaves the verified profile unchanged.
