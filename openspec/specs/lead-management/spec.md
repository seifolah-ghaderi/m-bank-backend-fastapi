# lead-management Specification

## Purpose

Maintain the branch-owned source records used to select and contact leads in marketing campaigns.

## Requirements

### Requirement: Manual lead entry
Only Supervisors SHALL create leads. A lead SHALL have first name, last name, normalized Iranian mobile, an active branch and an active city. National code, occupation, address, referrer and additional information are optional. A supplied national code SHALL pass checksum validation and a supplied occupation SHALL be active. The lead's branch SHALL stay fixed.

#### Scenario: Manual creation without a spreadsheet
- **WHEN** a Supervisor supplies the required fields and a valid active branch and city
- **THEN** the system creates a lead that can be selected for a draft campaign.

#### Scenario: Duplicate identity
- **WHEN** a supplied mobile or national code already identifies another lead, including an archived lead
- **THEN** the request returns 409 and no duplicate lead is created.

### Requirement: Supervisor lead discovery and archive
Supervisors SHALL list and search leads by normalized name and filter by branch, city, occupation and archived state. Default lists and campaign selection SHALL omit archived leads. Supervisors SHALL be able to archive and restore eligible leads, preserving historical relationships and auditing the action.

#### Scenario: Archive an eligible lead
- **WHEN** a Supervisor archives a lead with no active campaign membership, nonfinal sale or verified customer
- **THEN** it is hidden from default selection and remains visible in archived searches.

#### Scenario: Archive a lead with current work
- **WHEN** a Supervisor tries to archive a lead in an active campaign, with a draft, submitted or rejected sale, or with a verified customer
- **THEN** the request returns 409 and the lead stays available to authorized workflows.

### Requirement: City-linked spreadsheet leads
The lead import SHALL require first name, last name, a valid normalized Iranian mobile and a city name resolving to an existing active city. Each new lead SHALL store the resolved city ID and have no branch until a Supervisor assigns one. The sample `کد` column SHALL be ignored by default.

#### Scenario: City exists and mobile is valid
- **WHEN** a lead row supplies the required values and the normalized city name matches an active city
- **THEN** the import creates an unassigned lead under that city's ID, regardless of how many branches are in the city.

#### Scenario: Missing city or invalid mobile
- **WHEN** a row has an unknown or inactive city, or has a phone value that fails mobile validation
- **THEN** the import reports the failing field for that row and creates no lead or city from it.

### Requirement: Repeat lead import and identity conflicts
Lead import SHALL match on normalized mobile and, when supplied, validated national code. It SHALL preserve existing leads and customer relationships. Identity conflicts and repeated identities later in the same workbook SHALL be reported by row.

#### Scenario: Previously imported lead
- **WHEN** an upload repeats an existing lead with compatible identity and the same resolved city
- **THEN** the row is recorded as unchanged and its existing data, branch, archival status and customer links are preserved.

#### Scenario: Conflicting match
- **WHEN** mobile and national code identify different leads, a supplied identity value conflicts with the matched lead's stored identity, or the resolved city differs
- **THEN** the row reports a conflict and makes no changes.

### Requirement: Manual first branch assignment
Only Supervisors SHALL filter the lead registry for unassigned leads and assign the first active branch to an unarchived unassigned lead. Assignment SHALL preserve the city and be audited. After assignment, the branch SHALL stay fixed.

#### Scenario: Assign an imported lead
- **WHEN** a Supervisor selects an active branch for an unassigned, unarchived lead
- **THEN** the lead stores that branch ID and its original city remains visible.

#### Scenario: Change or clear an existing branch
- **WHEN** a Supervisor attempts to change or clear a lead's existing branch
- **THEN** the assignment is rejected and the existing branch is preserved.
