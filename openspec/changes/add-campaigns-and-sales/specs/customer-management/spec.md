# customer-management Specification

## Purpose

Maintain verified CRM customer profiles, their held products and their relationship to the original lead.

## ADDED Requirements

### Requirement: Verified CRM customer identity
The system SHALL create one CRM customer per lead on first sale approval, with the verified bank customer code, name, phone, address and city, plus national code when provided. The bank customer code SHALL be unique. The record SHALL retain its lead, branch at conversion, first approved sale, acquisition employee and conversion time. Customer and held-product history SHALL be preserved.

#### Scenario: Verified details differ from the lead
- **WHEN** a Supervisor approves the first sale with verified customer details that differ from imported or manually entered lead details
- **THEN** the new customer uses the verified values and the lead retains its original identity and contact details.

#### Scenario: Duplicate customer code
- **WHEN** approval would establish a customer code already held by another customer
- **THEN** approval returns 409 `customer_code_exists` and the claim stays submitted.

### Requirement: Held products
The system SHALL create one held product per approved sale and allow each product at most once per customer. The product record SHALL preserve the bank account reference, source sale and approval date.

#### Scenario: Cross-sell adds a product
- **WHEN** a new product is approved for an existing customer during a cross-sell campaign
- **THEN** the existing profile is reused and only the newly approved product is added to its holdings.

### Requirement: Customer lookup and corrections
Supervisors SHALL search and view all customers, and Branch Managers SHALL search and view only customers in their branch. Supervisors and the customer's Branch Manager SHALL be able to correct contact details with an audit record. Employees SHALL access a customer only through an authorized campaign or their own sale context, with the fields needed for that workflow.

#### Scenario: Manager requests another branch's customer
- **WHEN** a manager requests customer details using an ID from another branch
- **THEN** the response is 404 and reveals no profile, sales, products or retention history.

#### Scenario: Search by customer information
- **WHEN** an authorized user searches the customer registry
- **THEN** results are paginated within scope and support name or phone search and filtering by branch, city, held product and conversion date.
