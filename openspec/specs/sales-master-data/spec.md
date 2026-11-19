# sales-master-data Specification

## Purpose

Maintain the occupations used to classify leads and the scored banking products used in sale claims.

## Requirements

### Requirement: Occupation catalog
Supervisors SHALL create, update and deactivate occupations with unique normalized names. Staff SHALL be able to read active occupations. Historical lead references SHALL remain readable after deactivation.

#### Scenario: Deactivate an occupation
- **WHEN** a Supervisor deactivates an occupation referenced by a lead
- **THEN** it is excluded from new selections and stays attached to the existing lead.

### Requirement: Banking product catalog
Supervisors SHALL create, update and deactivate products with a name, a unique normalized code and a nonnegative integer score. Staff SHALL be able to read active products. Inactive products SHALL be unavailable for new sale claims, and existing claims and held products SHALL retain their references.

#### Scenario: Update the points for a product
- **WHEN** a Supervisor changes a product's score after a sale is approved
- **THEN** existing ledger entries keep their original points and subsequent approvals use the score in effect at approval.

#### Scenario: Product deactivated during verification
- **WHEN** a Supervisor approves a submitted sale for a product deactivated after registration
- **THEN** the claim remains eligible for approval using the product's current score.
