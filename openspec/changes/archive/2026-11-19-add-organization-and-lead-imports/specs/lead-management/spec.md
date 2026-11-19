# Lead Management Spec Delta

## ADDED Requirements

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
